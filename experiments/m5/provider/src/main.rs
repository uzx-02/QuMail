//! M5 private-pipe helper. Reuses unchanged audited M3 certificate/crypto code.
#![allow(dead_code)]
include!("../../../m3/provider/src/provider.rs");
use serde_json::{json, Value};
const INNER: usize = 65536;
const ARMORED: usize = 196608;
fn bytes(v: &Value) -> Result<Vec<u8>> {
    let a=v.as_array().context("bytes")?;
    ensure!(a.len()<=ARMORED,"limit");
    a.iter().map(|x| x.as_u64().filter(|n| *n<256).map(|n| n as u8).context("byte")).collect()
}
fn dispatch(v: &Value) -> Result<Value> {
    let version=unsafe { std::ffi::CStr::from_ptr(openssl_sys::OpenSSL_version(0)) }.to_str()?;
    ensure!(version=="OpenSSL 3.5.9 29 Sep 2026" && v["version"]==1,"inputs");
    profile(v["profile"].as_str().context("profile")?)?;
    let c=Cert::from_bytes(&bytes(&v["certificate"])?)?;
    ensure!(c.is_tsk(),"owned secret");
    let data=bytes(&v["data"])?;
    match v["op"].as_str().context("op")? {
        "seal" | "peer_seal" => {
            ensure!(data.len()<=INNER,"inner limit");
            let values=v["recipients"].as_array().context("recipients")?;
            ensure!((1..=4).contains(&values.len()),"recipient limit");
            let recipients=values.iter().map(bytes).collect::<Result<Vec<_>>>()?;
            let packet=if v["op"]=="seal" {sq_seal(PROFILE,&c,&recipients,&data)?}
                       else {rp_seal(PROFILE,&c,&recipients,&data)?};
            ensure!(inspect_envelope(&packet)?==recipients.len(),"recipient count");
            let mut armored=Vec::new();
            let mut writer=sq::armor::Writer::new(&mut armored,sq::armor::Kind::Message)?;
            writer.write_all(&packet)?; writer.finalize()?;
            ensure!(armored.len()<=ARMORED,"output limit");
            Ok(json!({"data":armored}))
        }
        "open" | "peer_open" => {
            ensure!(data.len()<=ARMORED,"envelope limit");
            let mut raw=Vec::new();
            sq::armor::Reader::from_bytes(&data,sq::armor::ReaderMode::Tolerant(Some(sq::armor::Kind::Message)))
                .take(ARMORED as u64+1).read_to_end(&mut raw)?;
            ensure!(raw.len()<=ARMORED,"packet limit");
            ensure!(inspect_envelope(&raw)?<=4,"M5 recipient packet limit");
            let sender=bytes(&v["sender"])?;
            let cert=Cert::from_bytes(&sender)?;
            ensure!(!cert.is_tsk(),"public signer");
            let content=if v["op"]=="open" {sq_open(PROFILE,&c,&sender,&raw)?}
                        else {rp_open(PROFILE,&c,&sender,&raw)?};
            ensure!(content.len()<=INNER,"inner output limit");
            // No response until complete integrity + composite signature verification.
            Ok(json!({"data":content,"signer":cert.fingerprint().to_hex(),"verified":true}))
        }
        _ => bail!("unsupported operation")
    }
}
fn main() {
    std::panic::set_hook(Box::new(|_| {}));
    // Windows executable main has a smaller default stack than Rust's test
    // workers. The independent PQ peer requires an explicit bounded stack.
    // Process isolation still contains abort/overflow; this is not CT assurance.
    let worker=std::thread::Builder::new().stack_size(8*1024*1024).spawn(|| -> Result<Value> {
        let mut raw=Vec::new(); std::io::stdin().take(8*MAX_INPUT as u64+1).read_to_end(&mut raw)?;
        ensure!(raw.len()<=8*MAX_INPUT,"pipe limit");
        dispatch(&serde_json::from_slice(&raw)?)
    });
    let result=worker.ok().and_then(|thread| thread.join().ok());
    match result {
        Some(Ok(value)) => {
            let output=json!({"ok":true,"value":value}).to_string();
            if output.len()>8*MAX_INPUT || std::io::stdout().write_all(output.as_bytes()).is_err() {std::process::exit(2);}
        }
        _ => { let _=std::io::stdout().write_all(b"{\"ok\":false}"); std::process::exit(1); }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn independent_multi_recipient_archive_and_failures() -> Result<()> {
        let a=generate("sender@example.invalid")?; let b=generate("b@example.invalid")?;
        let c=generate("c@example.invalid")?; let wrong=generate("wrong@example.invalid")?;
        let public_recipients=vec![public(&b)?,public(&c)?,public(&a)?];
        for op in ["seal","peer_seal"] {
            let request=json!({"version":1,"op":op,"profile":PROFILE,"certificate":secret(&a)?,
                "recipients":public_recipients,"data":b"private disposable test".to_vec()});
            let encrypted=dispatch(&request)?;
            for receiver in [&a,&b,&c] {
                for open in ["open","peer_open"] {
                    let result=dispatch(&json!({"version":1,"op":open,"profile":PROFILE,
                        "certificate":secret(receiver)?,"sender":public(&a)?,"data":encrypted["data"]}))?;
                    ensure!(bytes(&result["data"])?==b"private disposable test","verified content");
                }
            }
            for (receiver,sender) in [(&wrong,&a),(&b,&wrong)] {
                ensure!(dispatch(&json!({"version":1,"op":"open","profile":PROFILE,
                    "certificate":secret(receiver)?,"sender":public(sender)?,"data":encrypted["data"]})).is_err(),"wrong key");
            }
        }
        Ok(())
    }
    #[test]
    fn forbidden_content_suite_unsigned_and_truncated_rejected() -> Result<()> {
        let a=generate("a@example.invalid")?; let b=generate("b@example.invalid")?;
        let policy=StandardPolicy::new();
        // All construction uses provider encoders, never local packet serialization.
        for (algorithm,sign) in [(SymmetricAlgorithm::AES128,true),(SymmetricAlgorithm::AES256,false)] {
            let keys=b.keys().with_policy(&policy,None).alive().revoked(false).for_transport_encryption();
            let mut output=Vec::new();
            let encrypted=Encryptor::for_recipients(Message::new(&mut output),keys)
                .symmetric_algo(algorithm).aead_algo(AEADAlgorithm::GCM).build()?;
            let stream=if sign {
                let key=a.keys().unencrypted_secret().with_policy(&policy,None).alive().revoked(false).for_signing().next().context("signer")?.key().clone().into_keypair()?;
                Signer::new(encrypted,key)?.hash_algo(HashAlgorithm::SHA512)?.build()?
            } else { encrypted };
            let mut literal=LiteralWriter::new(stream).build()?;
            literal.write_all(b"disposable")?; literal.finalize()?;
            ensure!(sq_open(PROFILE,&b,&public(&a)?,&output).is_err(),"forbidden/unsigned accepted");
        }
        let good=sq_seal(PROFILE,&a,&[public(&b)?],b"disposable")?;
        ensure!(sq_open(PROFILE,&b,&public(&a)?,&good[..good.len()-1]).is_err(),"truncation accepted");
        ensure!(sq_seal("unknown",&a,&[public(&b)?],b"data").is_err(),"profile downgrade");
        for (recipients,payload) in [(vec![public(&b)?;5],vec![0u8;8]),(vec![public(&b)?],vec![0u8;INNER+1])] {
            let packet=sq_seal(PROFILE,&a,&recipients,&payload)?;
            let mut armor=Vec::new();
            let mut writer=sq::armor::Writer::new(&mut armor,sq::armor::Kind::Message)?;
            writer.write_all(&packet)?; writer.finalize()?;
            ensure!(dispatch(&json!({"version":1,"op":"open","profile":PROFILE,"certificate":secret(&b)?,
                "sender":public(&a)?,"data":armor})).is_err(),"receive limit");
        }
        Ok(())
    }
}
