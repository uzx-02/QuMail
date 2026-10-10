//! Isolated M3 helper: bounded JSON over anonymous pipes, never CLI secrets.
#![allow(dead_code)]
include!("provider.rs");
use serde_json::{json, Value};
fn bytes(v: &Value, name: &str) -> Result<Vec<u8>> {
    let a = v[name].as_array().context("bytes")?;
    ensure!(a.len() <= MAX_INPUT, "limit");
    a.iter().map(|x| x.as_u64().filter(|n| *n < 256).map(|n| n as u8).context("byte")).collect()
}
fn info(c: &Cert) -> Result<Value> {
    check_certificate(c)?;
    let p = StandardPolicy::new();
    let vc = c.with_policy(&p,None)?;
    let signing = vc.keys().subkeys().alive().revoked(false).for_signing().next().context("signer")?;
    let encryption = vc.keys().subkeys().alive().revoked(false).for_transport_encryption().next().context("recipient")?;
    Ok(json!({"fingerprint": c.fingerprint().to_hex(),
        "signing": signing.key().fingerprint().to_hex(), "encryption": encryption.key().fingerprint().to_hex(),
        "addresses": vc.userids().filter_map(|u| u.userid().email().ok().flatten()).collect::<Vec<_>>(),
        "public": public(c)?, "profile": PROFILE}))
}
fn revoke(c: &Cert) -> Result<Cert> {
    let mut signer = c.primary_key().key().clone().parts_into_secret()?.into_keypair()?;
    let sig = CertRevocationBuilder::new().set_reason_for_revocation(
        sq::types::ReasonForRevocation::KeyRetired, b"M3 explicit local revocation")?
        .build(&mut signer,c,HashAlgorithm::SHA512)?;
    Ok(c.clone().insert_packets(sig)?.0)
}
fn rotate(c: &Cert) -> Result<Cert> {
    check_certificate(c)?;
    let p = StandardPolicy::new();
    let mut root = c.primary_key().key().clone().parts_into_secret()?.into_keypair()?;
    let mut changed = c.clone();
    for key in c.keys().subkeys().with_policy(&p,None).alive().revoked(false) {
        let sig = SubkeyRevocationBuilder::new().set_reason_for_revocation(
            sq::types::ReasonForRevocation::KeyRetired,b"M3 additive device rotation")?
            .build(&mut root,c,key.key(),HashAlgorithm::SHA512)?;
        changed = changed.insert_packets(sig)?.0;
    }
    for flags in [sq::types::KeyFlags::empty().set_signing(),sq::types::KeyFlags::empty().set_transport_encryption()] {
        let updated = KeyBuilder::new(flags).set_cipher_suite(CipherSuite::MLDSA65_Ed25519)
            .subkey(changed.with_policy(&p,None)?)?
            .set_key_validity_period(std::time::Duration::from_secs(365*86400))?.attach_cert()?;
        changed = updated;
    }
    check_certificate(&changed)?;
    Ok(changed)
}
fn dispatch(v: &Value) -> Result<Value> {
    let version = unsafe { std::ffi::CStr::from_ptr(openssl_sys::OpenSSL_version(0)) }.to_str()?;
    ensure!(version == "OpenSSL 3.5.9 29 Sep 2026", "native input");
    ensure!(v["version"] == 1, "version");
    let op = v["op"].as_str().context("op")?;
    if op=="generate" {
        let address=v["address"].as_str().context("address")?;
        ensure!(address.len()<255 && address.contains('@') && !address.chars().any(char::is_control),"address");
        let c=generate(address)?; let mut out=info(&c)?; out["secret"]=json!(secret(&c)?); return Ok(out);
    }
    let raw=bytes(v,"certificate")?;
    let c=Cert::from_bytes(&raw)?;
    match op {
        "inspect" => { ensure!(!c.is_tsk(),"public only"); info(&c) }
        "revocation" => {
            ensure!(!c.is_tsk(),"public only");
            let p=StandardPolicy::new();
            ensure!(matches!(c.revocation_status(&p,None),sq::types::RevocationStatus::Revoked(_)),"verified revocation");
            Ok(json!({"fingerprint":c.fingerprint().to_hex()}))
        }
        "secret_info" => { ensure!(c.is_tsk(),"secret"); info(&c) }
        "public" => Ok(json!({"public": public(&c)?, "fingerprint":c.fingerprint().to_hex()})),
        "rotate" => { let c=rotate(&c)?; let mut out=info(&c)?; out["secret"]=json!(secret(&c)?); Ok(out) }
        "revoke" => { let c=revoke(&c)?; Ok(json!({"public":public(&c)?,"secret":secret(&c)?})) }
        "seal" => { check_certificate(&c)?; Ok(json!({"data":sq_seal(PROFILE,&c,&[bytes(v,"recipient")?],&bytes(v,"data")?)?})) }
        "open" => Ok(json!({"data":sq_open(PROFILE,&c,&bytes(v,"sender")?,&bytes(v,"data")?)?})),
        _ => bail!("unsupported operation")
    }
}
fn main() {
    // Native diagnostics are never forwarded to a caller or log by the Python boundary.
    std::panic::set_hook(Box::new(|_| {}));
    let result=std::panic::catch_unwind(|| -> Result<Value> {
        let mut input=Vec::new(); std::io::stdin().take(8*MAX_INPUT as u64+1).read_to_end(&mut input)?;
        ensure!(input.len()<=8*MAX_INPUT,"limit");
        dispatch(&serde_json::from_slice(&input)?)
    });
    match result {
        Ok(Ok(value)) => { let output=json!({"ok":true,"value":value}).to_string();
            if output.len()>8*MAX_INPUT { std::process::exit(2); }
            if std::io::stdout().write_all(output.as_bytes()).is_err() { std::process::exit(2); }
        }
        _ => { let _=std::io::stdout().write_all(b"{\"ok\":false,\"error\":\"provider_failure\"}"); std::process::exit(1); }
    }
}
#[cfg(test)]
mod m3_tests {
    use super::*;
    #[test]
    fn separate_signing_subkey_independent_exchange() -> Result<()> {
        let a=generate("a@example.invalid")?; let b=generate("b@example.invalid")?;
        check_certificate(&a)?; check_certificate(&b)?;
        let payload:Vec<u8>=(0..128).map(|_|rand::random()).collect();
        let sq=sq_seal(PROFILE,&a,&[public(&b)?],&payload)?;
        ensure!(rp_open(PROFILE,&b,&public(&a)?,&sq)?==payload,"peer receive");
        let rp=rp_seal(PROFILE,&a,&[public(&b)?],&payload)?;
        ensure!(sq_open(PROFILE,&b,&public(&a)?,&rp)?==payload,"peer send");
        ensure!(rp_open(PROFILE,&b,&public(&a)?,&rp)?==payload,"peer signature subkey");
        ensure!(sq_open(PROFILE,&a,&public(&a)?,&sq).is_err(),"wrong key");
        Ok(())
    }
    #[test]
    fn rotation_revocation_expiry_bindings() -> Result<()> {
        let a=generate("a@example.invalid")?; let b=generate("b@example.invalid")?;
        let old=sq_seal(PROFILE,&a,&[public(&b)?],b"synthetic")?;
        let changed=rotate(&b)?;
        ensure!(changed.fingerprint()==b.fingerprint(),"stable root");
        ensure!(sq_open(PROFILE,&changed,&public(&a)?,&old)?==b"synthetic","history");
        let fresh=sq_seal(PROFILE,&a,&[public(&changed)?],b"synthetic")?;
        ensure!(rp_open(PROFILE,&changed,&public(&a)?,&fresh)?==b"synthetic","rotated peer decrypt");
        let peer=rp_seal(PROFILE,&changed,&[public(&a)?],b"synthetic")?;
        ensure!(sq_open(PROFILE,&a,&public(&changed)?,&peer)?==b"synthetic","rotated peer sign");
        let signed=sq_seal(PROFILE,&changed,&[public(&a)?],b"synthetic")?;
        ensure!(rp_open(PROFILE,&a,&public(&changed)?,&signed)?==b"synthetic","rotated peer verify");
        let revoked=revoke(&b)?; ensure!(check_certificate(&revoked).is_err(),"revoked");
        let broken=b.clone().retain_subkeys(|_|false); ensure!(check_certificate(&broken).is_err(),"binding structure");
        let foreign = a.keys().subkeys().next().context("foreign subkey")?.key().clone();
        let substituted=b.clone().insert_packets(sq::Packet::PublicSubkey(foreign))?.0;
        ensure!(check_certificate(&substituted).is_err(),"unbound foreign subkey");
        let p=StandardPolicy::new();
        ensure!(b.with_policy(&p,std::time::SystemTime::now()+std::time::Duration::from_secs(4*365*86400))?.alive().is_err(),"expired");
        Ok(())
    }
}
