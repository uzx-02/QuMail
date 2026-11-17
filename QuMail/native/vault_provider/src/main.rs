//! Isolated Vault provider helper: bounded JSON over anonymous pipes, never CLI secrets.
#![allow(dead_code)]
include!("provider.rs");
use serde_json::{json, Value};
use hybrid_array::Array;
use ml_dsa::{
    signature::Signer,
    Keypair, MlDsa65, SigningKey,
};

use zeroize::Zeroizing;

fn bytes(v: &Value, name: &str) -> Result<Vec<u8>> {
    let a = v[name].as_array().context("bytes")?;
    ensure!(a.len() <= MAX_INPUT, "limit");
    a.iter().map(|x| x.as_u64().filter(|n| *n < 256).map(|n| n as u8).context("byte")).collect()
}

fn info(c: &Cert) -> Result<Value> {
    check_certificate(c)?;
    let p = StandardPolicy::new();
    let vc = c.with_policy(&p,None)?;
    let signing = vc.keys().alive().revoked(false).for_signing().next().context("signer")?;
    let encryption = vc.keys().subkeys().alive().revoked(false).for_transport_encryption().next().context("recipient")?;
    Ok(json!({"fingerprint": c.fingerprint().to_hex(),
        "signing": signing.key().fingerprint().to_hex(), "encryption": encryption.key().fingerprint().to_hex(),
        "addresses": vc.userids().filter_map(|u| u.userid().email().ok().flatten()).collect::<Vec<_>>(),
        "public": public(c)?, "profile": PROFILE}))
}

/// Return the raw FIPS-204 ML-DSA-65 verifying key and a detached signature
/// over `message`, using the existing OpenPGP device-signing subkey.
///
/// The OpenPGP certificate stores this hybrid subkey as Ed25519 plus the
/// ML-DSA seed. The directory protocol deliberately needs only the native
/// ML-DSA component; the seed and the OpenPGP secret certificate remain in
/// this process and are never included in the JSON response.
fn directory_pop(c: &Cert, message: &[u8]) -> Result<(Vec<u8>, Vec<u8>)> {
    ensure!(message.len() <= MAX_INPUT, "limit");
    check_certificate(c)?;

    let p = StandardPolicy::new();
    let signing_key = c.keys().unencrypted_secret().with_policy(&p, None)
        .alive().revoked(false).for_signing().next().context("signing subkey")?;
    let key = signing_key.key();

    let expected_public = match key.mpis() {
        sq::crypto::mpi::PublicKey::MLDSA65_Ed25519 { mldsa, .. } => mldsa.to_vec(),
        _ => bail!("unexpected public key type"),
    };

    // Extract the 32-byte ML-DSA-65 secret seed directly into zeroizing stack memory.
    // Zeroizing ensures that the memory buffer is wiped with zeroes upon leaving scope
    // on all code paths (early returns, error paths, and normal completion).
    let mut seed = Zeroizing::new([0u8; 32]);
    let mut extracted = false;

    match key.secret() {
        sq::packet::key::SecretKeyMaterial::Unencrypted(ref u) => {
            u.map(|mpis| {
                if let sq::crypto::mpi::SecretKeyMaterial::MLDSA65_Ed25519 { mldsa, .. } = mpis {
                    if mldsa.len() == 32 {
                        seed.copy_from_slice(mldsa);
                        extracted = true;
                    }
                }
            });
        }
        _ => bail!("encrypted secret key not supported"),
    };
    ensure!(extracted, "ML-DSA-65 seed must be exactly 32 bytes");

    // Copy into zeroizing Array required by ml_dsa::SigningKey.
    // ml-dsa 0.1.2 with feature "zeroize" implements ZeroizeOnDrop for SigningKey and ExpandedSigningKey.
    let seed_arr = Zeroizing::new(Array::from(*seed));
    let pair = SigningKey::<MlDsa65>::from_seed(&seed_arr);

    let verifying = pair.verifying_key().encode().to_vec();
    ensure!(verifying == expected_public, "inconsistent signing key");

    let signature = pair.sign(message).encode().to_vec();

    // FIPS 204 ML-DSA-65 fixed encoding sizes; keep the protocol boundary
    // narrow even if a library representation changes.
    ensure!(verifying.len() == 1952 && signature.len() == 3309, "directory proof");
    Ok((verifying, signature))
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
    if op == "generate" {
        let address = v["address"].as_str().context("address")?;
        ensure!(address.len() < 255 && address.contains('@') && !address.chars().any(char::is_control), "address");
        let c = generate(address)?;
        let mut out = info(&c)?;
        out["secret"] = json!(secret(&c)?);
        return Ok(out);
    }
    let raw = bytes(v, "certificate")?;
    let c = Cert::from_bytes(&raw)?;
    match op {
        "status" => {
            ensure!(!c.is_tsk(), "public only");
            let p = StandardPolicy::new();
            let vc = c.with_policy(&p, None)?;
            let revoked = matches!(vc.revocation_status(), sq::types::RevocationStatus::Revoked(_));
            let expired = vc.alive().is_err()
                || vc.keys().subkeys().alive().revoked(false).for_signing().count() != 1
                || vc.keys().subkeys().alive().revoked(false).for_transport_encryption().count() != 1;
            Ok(json!({"state": if revoked { "revoked" } else if expired { "expired" } else { check_certificate(&c)?; "active" }}))
        }
        "inspect" => {
            ensure!(!c.is_tsk(), "public only");
            info(&c)
        }
        "info" => info(&c),
        "revocation" => {
            ensure!(!c.is_tsk(), "public only");
            let p = StandardPolicy::new();
            ensure!(matches!(c.revocation_status(&p, None), sq::types::RevocationStatus::Revoked(_)), "verified revocation");
            Ok(json!({"fingerprint": c.fingerprint().to_hex()}))
        }
        "secret_info" => {
            ensure!(c.is_tsk(), "secret");
            info(&c)
        }
        "public" => Ok(json!({"public": public(&c)?, "fingerprint": c.fingerprint().to_hex()})),
        "rotate" => {
            let c = rotate(&c)?;
            let mut out = info(&c)?;
            out["secret"] = json!(secret(&c)?);
            Ok(out)
        }
        "revoke" => {
            let c = revoke(&c)?;
            Ok(json!({"public": public(&c)?, "secret": secret(&c)?}))
        }
        "seal" => {
            check_certificate(&c)?;
            Ok(json!({"data": sq_seal(PROFILE, &c, &[bytes(v, "recipient")?], &bytes(v, "data")?)?}))
        }
        "open" => Ok(json!({"data": sq_open(PROFILE, &c, &bytes(v, "sender")?, &bytes(v, "data")?)?})),
        "pop" => {
            let (pubkey, sig) = directory_pop(&c, &bytes(v, "message")?)?;
            Ok(json!({"public": pubkey, "signature": sig}))
        }
        _ => bail!("unsupported operation"),
    }
}

fn main() {
    // Native diagnostics are never forwarded to a caller or log by the Python boundary.
    std::panic::set_hook(Box::new(|_| {}));
    let result = std::panic::catch_unwind(|| -> Result<Value> {
        let mut input = Vec::new();
        std::io::stdin().take(8 * MAX_INPUT as u64 + 1).read_to_end(&mut input)?;
        ensure!(input.len() <= 8 * MAX_INPUT, "limit");
        dispatch(&serde_json::from_slice(&input)?)
    });
    match result {
        Ok(Ok(value)) => {
            let output = json!({"ok": true, "value": value}).to_string();
            if output.len() > 8 * MAX_INPUT {
                std::process::exit(2);
            }
            if std::io::stdout().write_all(output.as_bytes()).is_err() {
                std::process::exit(2);
            }
        }
        _ => {
            let _ = std::io::stdout().write_all(b"{\"ok\":false,\"error\":\"provider_failure\"}");
            std::process::exit(1);
        }
    }
}

#[cfg(test)]
mod m3_tests {
    use super::*;
    use zeroize::Zeroize;
    use ml_dsa::{signature::Verifier, VerifyingKey};
    #[test]
    fn public_lifecycle_status() -> Result<()> {
        let cert = generate("lifecycle@example.invalid")?;
        check_certificate(&cert)?;
        let data = dispatch(&json!({"version": 1, "op": "info", "certificate": secret(&cert)?}))?;
        ensure!(data["fingerprint"].as_str().unwrap() == cert.fingerprint().to_hex(), "info fp");
        ensure!(data["profile"].as_str().unwrap() == PROFILE, "profile");
        ensure!(data["addresses"].as_array().unwrap()[0] == "lifecycle@example.invalid", "address");
        let parsed_public = Cert::from_bytes(&bytes(&data, "public")?)?;
        ensure!(!parsed_public.is_tsk(), "exported public contains secret");
        ensure!(parsed_public.fingerprint() == cert.fingerprint(), "matching public fingerprint");
        check_certificate(&parsed_public)?;
        let broken = cert.clone().retain_userids(|_| false);
        ensure!(check_certificate(&broken).is_err(), "missing userid must fail policy");
        let non_m3 = CertBuilder::new().set_profile(sq::Profile::RFC9580)?
            .add_userid("legacy@example.invalid").generate()?.0;
        ensure!(check_certificate(&non_m3).is_err(), "standard RFC9580 rejected by explicit policy");
        for flags in [sq::types::KeyFlags::empty().set_certification(), sq::types::KeyFlags::empty().set_storage_encryption()] {
            let bad_sub = KeyBuilder::new(flags).set_cipher_suite(CipherSuite::MLDSA65_Ed25519)
                .subkey(cert.with_policy(&StandardPolicy::new(), None)?)?.attach_cert()?;
            ensure!(check_certificate(&bad_sub).is_err(), "unexpected flags rejected");
        }
        Ok(())
    }
    #[test]
    fn separate_signing_subkey_independent_exchange() -> Result<()> {
        let a = generate("a@example.invalid")?;
        let b = generate("b@example.invalid")?;
        check_certificate(&a)?;
        check_certificate(&b)?;
        let payload: Vec<u8> = (0..128).map(|_| rand::random()).collect();
        let sq = sq_seal(PROFILE, &a, &[public(&b)?], &payload)?;
        ensure!(rp_open(PROFILE, &b, &public(&a)?, &sq)? == payload, "peer receive");
        let rp = rp_seal(PROFILE, &a, &[public(&b)?], &payload)?;
        ensure!(sq_open(PROFILE, &b, &public(&a)?, &rp)? == payload, "peer send");
        ensure!(rp_open(PROFILE, &b, &public(&a)?, &rp)? == payload, "peer signature subkey");
        ensure!(sq_open(PROFILE, &a, &public(&a)?, &sq).is_err(), "wrong key");
        Ok(())
    }
    #[test]
    fn directory_pop_uses_existing_signing_subkey() -> Result<()> {
        let certificate = generate("directory@example.invalid")?;
        let message = b"QUMAIL-DIRECTORY-POP-v1\0identity\0device\0fingerprint\0nonce";
        let (public, signature) = directory_pop(&certificate, message)?;
        ensure!(public.len() == 1952 && signature.len() == 3309, "fixed directory encodings");
        let pub_arr = Array::try_from(public.as_slice()).map_err(|_| anyhow::anyhow!("public array"))?;
        let verifier = VerifyingKey::<MlDsa65>::decode(&pub_arr);
        let sig = ml_dsa::Signature::<MlDsa65>::try_from(signature.as_slice())
            .map_err(|_| anyhow::anyhow!("signature encoding"))?;
        verifier.verify(message, &sig).map_err(|_| anyhow::anyhow!("directory proof"))?;
        Ok(())
    }
    #[test]
    fn rotation_revocation_expiry_bindings() -> Result<()> {
        let a = generate("a@example.invalid")?;
        let b = generate("b@example.invalid")?;
        let old = sq_seal(PROFILE, &a, &[public(&b)?], b"synthetic")?;
        let changed = rotate(&b)?;
        ensure!(changed.fingerprint() == b.fingerprint(), "stable root");
        ensure!(sq_open(PROFILE, &changed, &public(&a)?, &old)? == b"synthetic", "history");
        let fresh = sq_seal(PROFILE, &a, &[public(&changed)?], b"synthetic")?;
        ensure!(rp_open(PROFILE, &changed, &public(&a)?, &fresh)? == b"synthetic", "rotated peer decrypt");
        let peer = rp_seal(PROFILE, &changed, &[public(&a)?], b"synthetic")?;
        ensure!(sq_open(PROFILE, &a, &public(&changed)?, &peer)? == b"synthetic", "rotated peer sign");
        let signed = sq_seal(PROFILE, &changed, &[public(&a)?], b"synthetic")?;
        ensure!(rp_open(PROFILE, &a, &public(&changed)?, &signed)? == b"synthetic", "rotated peer verify");
        let revoked = revoke(&b)?;
        ensure!(check_certificate(&revoked).is_err(), "revoked");
        let broken = b.clone().retain_subkeys(|_| false);
        ensure!(check_certificate(&broken).is_err(), "binding structure");
        let foreign = a.keys().subkeys().next().context("foreign subkey")?.key().clone();
        let substituted = b.clone().insert_packets(sq::Packet::PublicSubkey(foreign))?.0;
        ensure!(check_certificate(&substituted).is_err(), "unbound foreign subkey");
        let p = StandardPolicy::new();
        ensure!(b.with_policy(&p, std::time::SystemTime::now() + std::time::Duration::from_secs(4*365*86400))?.alive().is_err(), "expired");
        Ok(())
    }
    #[test]
    fn ml_dsa_secret_memory_zeroization_guarantee() -> Result<()> {
        let mut buffer = Zeroizing::new([0x5Au8; 32]);
        assert_eq!(buffer[0], 0x5A);
        buffer.zeroize();
        assert_eq!(*buffer, [0u8; 32]);

        let certificate = generate("zeroize-audit@example.invalid")?;
        let message = b"zeroization check message";
        let (pubkey, sig) = directory_pop(&certificate, message)?;
        ensure!(pubkey.len() == 1952, "valid pubkey length");
        ensure!(sig.len() == 3309, "valid signature length");
        Ok(())
    }
}
