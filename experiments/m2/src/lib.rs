//! Isolated provider experiment. No production imports or persisted secret fixtures.
#![cfg(test)]
mod contract;
#[cfg(feature = "backend-probe")]
mod backend_probe;
use std::io::{Read, Write};
use anyhow::{bail, ensure, Context, Result};
use sequoia_openpgp as sq;
use sq::{cert::prelude::*, parse::{Parse, stream::*}, serialize::{Serialize, stream::*},
         policy::StandardPolicy, types::{SymmetricAlgorithm, AEADAlgorithm, HashAlgorithm},
         crypto::SessionKey, Cert};
use pgp::{composed::{Deserializable, Message as RpMessage, MessageBuilder, SignedPublicKey, SignedSecretKey},
          types::Password};

pub const PROFILE: &str = "M2-EXPERIMENT-RFC9980-AES256-GCM";
const MAX_INPUT: usize = 1024 * 1024;

fn profile(name: &str) -> Result<()> {
    ensure!(name == PROFILE, "unsupported experimental profile");
    Ok(())
}

fn check_certificate(cert: &Cert) -> Result<()> {
    ensure!(cert.primary_key().key().version() == 6 &&
        cert.primary_key().key().pk_algo() == sq::types::PublicKeyAlgorithm::MLDSA65_Ed25519, "unsupported certificate");
    ensure!(cert.keys().subkeys().count() == 1, "experiment requires one encryption subkey");
    for key in cert.keys().subkeys() {
        ensure!(key.key().version() == 6 && key.key().pk_algo() == sq::types::PublicKeyAlgorithm::MLKEM768_X25519, "unsupported subkey");
    }
    Ok(())
}

// Test policy inspection uses Sequoia's parser; rPGP still independently parses,
// decrypts and verifies the complete message. This is not a production registry.
fn inspect_envelope(data: &[u8]) -> Result<usize> {
    ensure!(data.len() <= MAX_INPUT, "limit");
    let pile = sq::PacketPile::from_bytes(data)?;
    let mut recipients = 0;
    let mut encrypted = false;
    for packet in pile.children() {
        match packet {
            sq::Packet::PKESK(k) => {
                ensure!(!encrypted && k.version() == 6 && k.pk_algo() == sq::types::PublicKeyAlgorithm::MLKEM768_X25519, "unsupported PKESK");
                recipients += 1;
            }
            sq::Packet::SEIP(sq::packet::SEIP::V2(s)) => {
                ensure!(!encrypted && s.symmetric_algo() == SymmetricAlgorithm::AES256 &&
                    s.aead() == AEADAlgorithm::GCM && s.chunk_size() == 4096, "unsupported SEIPD");
                encrypted = true;
            }
            _ => bail!("unsupported packet"),
        }
    }
    ensure!(encrypted && (1..=32).contains(&recipients), "invalid envelope");
    Ok(recipients)
}

fn generate() -> Result<Cert> {
    Ok(CertBuilder::new().set_profile(sq::Profile::RFC9580)?
        .set_cipher_suite(CipherSuite::MLDSA65_Ed25519)
        .set_primary_key_flags(sq::types::KeyFlags::empty().set_certification().set_signing())
        .add_userid("M2 synthetic test <m2@example.invalid>")
        .add_transport_encryption_subkey().generate()?.0)
}

fn public(cert: &Cert) -> Result<Vec<u8>> {
    let mut out = Vec::new();
    cert.serialize(&mut out)?;
    ensure!(!Cert::from_bytes(&out)?.is_tsk(), "secret export at public boundary");
    Ok(out)
}

fn secret(cert: &Cert) -> Result<Vec<u8>> {
    let mut out = Vec::new();
    cert.as_tsk().serialize(&mut out)?;
    Ok(out)
}

fn detached_packet(bytes: &[u8]) -> Result<sq::packet::Signature> {
    let pile = sq::PacketPile::from_bytes(bytes)?;
    let packets: Vec<_> = pile.children().collect();
    ensure!(packets.len() == 1, "exactly one detached signature packet required");
    match packets[0] {
        sq::Packet::Signature(signature) => Ok(signature.clone()),
        _ => bail!("not a signature packet"),
    }
}

// Only public recipient bytes cross this encryption boundary.
fn sq_seal(name: &str, sender: &Cert, recipients: &[Vec<u8>], data: &[u8]) -> Result<Vec<u8>> {
    profile(name)?;
    ensure!(data.len() <= MAX_INPUT && !recipients.is_empty() && recipients.len() <= 32, "limit");
    let p = StandardPolicy::new();
    let certs = recipients.iter().map(Cert::from_bytes).collect::<Result<Vec<_>, _>>()?;
    check_certificate(sender)?;
    for c in &certs { ensure!(!c.is_tsk(), "recipient must be public"); check_certificate(c)?; }
    let mut keys = Vec::new();
    for c in &certs {
        let selected: Vec<_> = c.keys().with_policy(&p,None).supported().alive().revoked(false).for_transport_encryption().collect();
        ensure!(selected.len() == 1, "every recipient requires a usable encryption subkey");
        keys.extend(selected);
    }
    let signer = sender.keys().unencrypted_secret().with_policy(&p,None).for_signing().next().ok_or_else(|| anyhow::anyhow!("signer"))?.key().clone().into_keypair()?;
    let mut out = Vec::new();
    let encrypted = Encryptor::for_recipients(Message::new(&mut out), keys)
        .symmetric_algo(SymmetricAlgorithm::AES256).aead_algo(AEADAlgorithm::GCM).build()?;
    let signed = Signer::new(encrypted, signer)?.hash_algo(HashAlgorithm::SHA512)?.build()?;
    let mut literal = LiteralWriter::new(signed).build()?;
    literal.write_all(data)?;
    literal.finalize()?;
    Ok(out)
}

struct Helper { recipient: Cert, sender: Cert, required_hash: Option<HashAlgorithm> }
impl VerificationHelper for Helper {
    fn get_certs(&mut self, _: &[sq::KeyHandle]) -> sq::Result<Vec<Cert>> { Ok(vec![self.sender.clone()]) }
    fn check(&mut self, structure: MessageStructure) -> sq::Result<()> {
        let mut good = 0;
        for layer in structure {
            match layer {
                MessageLayer::Encryption { sym_algo, aead_algo } => {
                    ensure!(sym_algo == SymmetricAlgorithm::AES256 && aead_algo == Some(AEADAlgorithm::GCM), "unsupported encryption");
                }
                MessageLayer::SignatureGroup { results } => {
                    for result in results {
                        let sig = result.map_err(|_| anyhow::anyhow!("invalid signature"))?;
                        ensure!(sig.sig.pk_algo() == sq::types::PublicKeyAlgorithm::MLDSA65_Ed25519 && sig.sig.version() == 6, "unsupported signature");
                        if let Some(hash) = self.required_hash { ensure!(sig.sig.hash_algo() == hash, "unsupported signature hash"); }
                        good += 1;
                    }
                }
                _ => bail!("unexpected layer"),
            }
        }
        ensure!(good == 1, "exactly one composite signature required");
        Ok(())
    }
}
impl DecryptionHelper for Helper {
    fn decrypt(&mut self, pkesks: &[sq::packet::PKESK], _: &[sq::packet::SKESK], sym: Option<SymmetricAlgorithm>,
        decrypt: &mut dyn FnMut(Option<SymmetricAlgorithm>, &SessionKey) -> bool) -> sq::Result<Option<Cert>> {
        let p = StandardPolicy::new();
        for key in self.recipient.keys().unencrypted_secret().with_policy(&p,None).for_transport_encryption() {
            let mut pair = key.key().clone().into_keypair()?;
            for packet in pkesks {
                if let Some((algo, session)) = packet.decrypt(&mut pair, sym) {
                    if decrypt(algo, &session) { return Ok(Some(self.recipient.clone())); }
                }
            }
        }
        bail!("decryption rejected")
    }
}
fn sq_open(name: &str, recipient: &Cert, sender: &[u8], data: &[u8]) -> Result<Vec<u8>> {
    profile(name)?;
    inspect_envelope(data)?;
    let helper = Helper { recipient: recipient.clone(), sender: Cert::from_bytes(sender)?, required_hash: Some(HashAlgorithm::SHA512) };
    let p = StandardPolicy::new();
    let mut decryptor = DecryptorBuilder::from_bytes(data)?.with_policy(&p,None,helper)?;
    // Buffer until EOF and every integrity/signature check succeeds; never expose partial bytes.
    let mut out = Vec::new();
    (&mut decryptor).take(MAX_INPUT as u64 + 1).read_to_end(&mut out)?;
    ensure!(out.len() <= MAX_INPUT, "limit");
    Ok(out)
}

fn rp_seal(name: &str, sender: &Cert, recipients: &[Vec<u8>], data: &[u8]) -> Result<Vec<u8>> {
    profile(name)?;
    ensure!(data.len() <= MAX_INPUT && !recipients.is_empty() && recipients.len() <= 32, "limit");
    let secret_bytes = secret(sender)?;
    check_certificate(sender)?;
    for recipient in recipients {
        let c = Cert::from_bytes(recipient)?;
        ensure!(!c.is_tsk(), "recipient must be public");
        check_certificate(&c)?;
    }
    let key = SignedSecretKey::from_bytes(secret_bytes.as_slice())?;
    key.verify_bindings()?;
    let certs = recipients.iter().map(|b| SignedPublicKey::from_bytes(b.as_slice())).collect::<Result<Vec<_>,_>>()?;
    let mut builder = MessageBuilder::from_bytes("", data.to_vec()).seipd_v2(
        rand::thread_rng(), pgp::crypto::sym::SymmetricKeyAlgorithm::AES256,
        pgp::crypto::aead::AeadAlgorithm::Gcm, pgp::crypto::aead::ChunkSize::C4KiB);
    builder.sign(&*key, Password::empty(), pgp::crypto::hash::HashAlgorithm::Sha512);
    for cert in &certs {
        cert.verify_bindings()?;
        builder.encrypt_to_key(rand::thread_rng(), &cert.public_subkeys[0])?;
    }
    Ok(builder.to_vec(rand::thread_rng())?)
}
fn rp_open(name: &str, recipient: &Cert, sender: &[u8], data: &[u8]) -> Result<Vec<u8>> {
    profile(name)?;
    inspect_envelope(data)?;
    let secret_bytes = secret(recipient)?;
    let key = SignedSecretKey::from_bytes(secret_bytes.as_slice())?;
    key.verify_bindings()?;
    let sender = SignedPublicKey::from_bytes(sender)?;
    sender.verify_bindings()?;
    let mut msg = RpMessage::from_bytes(data)?.decrypt(&Password::empty(), &key)?;
    let mut out = Vec::new();
    (&mut msg).take(MAX_INPUT as u64 + 1).read_to_end(&mut out)?;
    ensure!(out.len() <= MAX_INPUT, "limit");
    let sig = msg.verify(&sender)?;
    let config = sig.config().ok_or_else(|| anyhow::anyhow!("signature config"))?;
    ensure!(config.pub_alg == pgp::crypto::public_key::PublicKeyAlgorithm::MlDsa65Ed25519 &&
        config.hash_alg == pgp::crypto::hash::HashAlgorithm::Sha512, "unsupported signature");
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    // Payload is generated at runtime and neither persisted nor printed.
    fn payload() -> Vec<u8> { (0..256).map(|_| rand::random::<u8>()).collect() }
    #[test]
    fn independent_exchange_and_negative_cases() -> Result<()> {
        let sender = generate()?;
        let recipient = generate()?;
        let wrong = generate()?;
        let sender_pub = public(&sender)?;
        let recipients = vec![public(&recipient)?];
        let data = payload();
        for seal in [sq_seal, rp_seal] {
            let encrypted = seal(PROFILE, &sender, &recipients, &data)?;
            for open in [sq_open, rp_open] {
                ensure!(open(PROFILE, &recipient, &sender_pub, &encrypted)? == data, "round trip");
                ensure!(open(PROFILE, &wrong, &sender_pub, &encrypted).is_err(), "wrong recipient accepted");
                ensure!(open(PROFILE, &recipient, &public(&wrong)?, &encrypted).is_err(), "wrong signer accepted");
                let mut altered = encrypted.clone();
                *altered.last_mut().unwrap() ^= 1;
                ensure!(open(PROFILE, &recipient, &sender_pub, &altered).is_err(), "alteration accepted");
                ensure!(open(PROFILE, &recipient, &sender_pub, &encrypted[..encrypted.len()-1]).is_err(), "truncation accepted");
                ensure!(open("unknown", &recipient, &sender_pub, &encrypted).is_err(), "profile accepted");
            }
            ensure!(seal("unknown", &sender, &recipients, &data).is_err(), "profile accepted");
        }
        Ok(())
    }

    #[test]
    fn multiple_recipients_and_fresh_envelopes() -> Result<()> {
        let sender = generate()?;
        let a = generate()?;
        let b = generate()?;
        let recipients = vec![public(&a)?, public(&b)?];
        let data = payload();
        for seal in [sq_seal, rp_seal] {
            let one = seal(PROFILE, &sender, &recipients, &data)?;
            let two = seal(PROFILE, &sender, &recipients, &data)?;
            ensure!(one != two && inspect_envelope(&one)? == 2, "freshness/recipient count");
            for open in [sq_open, rp_open] {
                for recipient in [&a, &b] {
                    ensure!(open(PROFILE, recipient, &public(&sender)?, &one)? == data, "multi recipient");
                }
            }
        }
        Ok(())
    }

    #[test]
    fn unsupported_certificates_and_limits() -> Result<()> {
        let sender = generate()?;
        let classic = CertBuilder::new().add_transport_encryption_subkey().generate()?.0;
        for seal in [sq_seal, rp_seal] {
            ensure!(seal(PROFILE, &sender, &[public(&classic)?], &payload()).is_err(), "classical accepted");
            ensure!(seal(PROFILE, &sender, &[vec![0; 32]], &payload()).is_err(), "malformed recipient accepted");
            ensure!(seal(PROFILE, &sender, &[secret(&sender)?], &payload()).is_err(), "secret recipient accepted");
            ensure!(seal(PROFILE, &sender, &[public(&sender)?], &vec![0; MAX_INPUT+1]).is_err(), "oversize accepted");
        }
        for open in [sq_open, rp_open] {
            ensure!(open(PROFILE, &sender, &public(&sender)?, &[0; 32]).is_err(), "malformed accepted");
            ensure!(open(PROFILE, &sender, &public(&sender)?, &vec![0;MAX_INPUT+1]).is_err(), "oversize accepted");
        }
        Ok(())
    }

    #[test]
    fn both_composite_signature_components_required() -> Result<()> {
        use pgp::{composed::DetachedSignature, ser::Serialize as RpSerialize};
        let sender = generate()?;
        let data = payload();
        let bytes = secret(&sender)?;
        let rp_secret = SignedSecretKey::from_bytes(bytes.as_slice())?;
        let rp_public = SignedPublicKey::from_bytes(public(&sender)?.as_slice())?;
        let mut sq_sig = Vec::new();
        let pair = sender.primary_key().key().clone().parts_into_secret()?.into_keypair()?;
        let mut signer = Signer::new(Message::new(&mut sq_sig), pair)?.detached()
            .hash_algo(HashAlgorithm::SHA512)?.build()?;
        signer.write_all(&data)?;
        signer.finalize()?;
        let rp_sig = DetachedSignature::sign_binary_data(rand::thread_rng(), &*rp_secret,
            &Password::empty(), pgp::crypto::hash::HashAlgorithm::Sha512, data.as_slice())?.to_bytes()?;
        for (origin, bytes) in [("Sequoia", sq_sig), ("rPGP", rp_sig)] {
            let signature = detached_packet(&bytes)
                .with_context(|| format!("Sequoia parse detached packet from {origin}; framing prefix {:02x?}", &bytes[..4]))?;
            ensure!(signature.version() == 6 && signature.hash_algo() == HashAlgorithm::SHA512, "signature profile");
            signature.verify_message(sender.primary_key().key(), &data)?;
            DetachedSignature::from_bytes(bytes.as_slice()).context("rPGP parse detached packet")?.verify(&rp_public, &data)?;
            ensure!(signature.verify_message(sender.primary_key().key(), &payload()).is_err(), "changed payload accepted");
            match signature.mpis() {
                sq::crypto::mpi::Signature::MLDSA65_Ed25519 { eddsa, mldsa } => {
                    // Locate provider-parsed bytes, not a locally implemented packet format.
                    for component in [eddsa.as_slice(), mldsa.as_slice()] {
                        let positions: Vec<_> = bytes.windows(component.len()).enumerate().filter(|(_, w)| *w == component).map(|(i,_)| i).collect();
                        ensure!(positions.len() == 1, "component location ambiguous");
                        let mut bad = bytes.clone();
                        bad[positions[0]] ^= 1;
                        ensure!(detached_packet(&bad)?.verify_message(sender.primary_key().key(), &data).is_err(), "component mutation accepted by Sequoia");
                        ensure!(DetachedSignature::from_bytes(bad.as_slice())?.verify(&rp_public, &data).is_err(), "component mutation accepted by rPGP");
                    }
                }
                _ => bail!("unexpected signature algorithm"),
            }
        }
        Ok(())
    }

    #[test]
    fn native_version_and_published_signature_vector() -> Result<()> {
        use pgp::composed::DetachedSignature;
        let version = unsafe { std::ffi::CStr::from_ptr(openssl_sys::OpenSSL_version(0)) }.to_str()?;
        ensure!(version == "OpenSSL 3.5.9 29 Sep 2026", "unexpected native input");
        let root = std::path::PathBuf::from(std::env::var("M2_PUBLIC_VECTORS")?);
        let cert_bytes = std::fs::read(root.join("v6-mldsa-65-sample-pk.asc"))?;
        let sig_bytes = std::fs::read(root.join("v6-mldsa-65-sample-signature.asc"))?;
        let cert = Cert::from_bytes(&cert_bytes)?;
        let rp_cert = SignedPublicKey::from_armor_single(cert_bytes.as_slice())?.0;
        let rp_sig = DetachedSignature::from_armor_single(sig_bytes.as_slice())?.0;
        // Published RFC 9980 A.3.4 vector input, not a generated/private fixture.
        // This is a text signature: use the provider stream API's canonicalization.
        let policy = StandardPolicy::new();
        let helper = Helper { recipient: cert.clone(), sender: cert, required_hash: None };
        DetachedVerifierBuilder::from_bytes(&sig_bytes)?.with_policy(&policy, None, helper)?
            .verify_bytes(b"Testing\n").context("Sequoia published vector verification")?;
        rp_sig.verify(&rp_cert, b"Testing\n").context("rPGP published vector verification")?;
        ensure!(rp_sig.verify(&rp_cert, b"altered vector").is_err(), "invalid vector accepted");
        Ok(())
    }

    #[test]
    fn rpgp_generated_certificate_exchange() -> Result<()> {
        use pgp::{composed::{SecretKeyParamsBuilder, SubkeyParamsBuilder, KeyType, EncryptionCaps},
            types::KeyVersion, ser::Serialize as RpSerialize};
        let params = SecretKeyParamsBuilder::default().version(KeyVersion::V6)
            .key_type(KeyType::MlDsa65Ed25519).can_sign(true).can_certify(true)
            .feature_seipd_v2(true)
            .primary_user_id("M2 peer <peer@example.invalid>".into())
            .subkey(SubkeyParamsBuilder::default().version(KeyVersion::V6)
                .key_type(KeyType::MlKem768X25519).can_encrypt(EncryptionCaps::All).build()?)
            .build()?;
        let key = params.generate(rand::thread_rng())?;
        key.verify_bindings()?;
        let recipient = Cert::from_bytes(&key.to_bytes()?)?;
        let sender = generate()?;
        let data = payload();
        for (from, to) in [(&sender,&recipient), (&recipient,&sender)] {
            for seal in [sq_seal, rp_seal] {
                let enc = seal(PROFILE, from, &[public(to)?], &data).context("encrypt with peer-generated certificate")?;
                for open in [sq_open, rp_open] {
                    ensure!(open(PROFILE, to, &public(from)?, &enc)? == data, "peer-generated cert exchange");
                }
            }
        }
        Ok(())
    }

    #[test]
    fn pgp_mime_protected_header_fixture() -> Result<()> {
        use mailparse::MailHeaderMap;
        let sender = generate()?;
        let recipient = generate()?;
        let subject = format!("{:032x}", rand::random::<u128>());
        let inner = format!(concat!(
            "From: sender@example.invalid\r\nTo: recipient@example.invalid\r\n",
            "Date: Sun, 04 Oct 2026 00:00:00 +0530\r\nMessage-ID: <m2@example.invalid>\r\n",
            "Subject: {}\r\nX-QuMail-Profile: {}\r\n",
            "MIME-Version: 1.0\r\nContent-Type: text/plain; charset=utf-8; hp=\"cipher\"\r\n",
            "HP-Outer: From: sender@example.invalid\r\nHP-Outer: To: recipient@example.invalid\r\n",
            "HP-Outer: Date: Sun, 04 Oct 2026 00:00:00 +0530\r\n",
            "HP-Outer: Message-ID: <m2@example.invalid>\r\nHP-Outer: Subject: [...]\r\n\r\n{}\r\n"
        ), subject, PROFILE, rand::random::<u128>());
        for seal in [sq_seal, rp_seal] {
            let enc = seal(PROFILE, &sender, &[public(&recipient)?], inner.as_bytes())?;
            // RFC 3156 section 2 requires OpenPGP ASCII armor, not bare base64.
            let mut armor = sq::armor::Writer::new(Vec::new(), sq::armor::Kind::Message)?;
            armor.write_all(&enc)?;
            let wrapped = String::from_utf8(armor.finalize()?)?.replace('\n', "\r\n");
            // RFC 3156 section 6.1 combined sign/encrypt; RFC 9788 hp/HP-Outer payload.
            let outer = format!(concat!(
                "From: sender@example.invalid\r\nTo: recipient@example.invalid\r\n",
                "Date: Sun, 04 Oct 2026 00:00:00 +0530\r\nMessage-ID: <m2@example.invalid>\r\n",
                "Subject: [...]\r\nMIME-Version: 1.0\r\n",
                "Content-Type: multipart/encrypted; protocol=\"application/pgp-encrypted\"; boundary=m2\r\n\r\n",
                "--m2\r\nContent-Type: application/pgp-encrypted\r\n\r\nVersion: 1\r\n",
                "--m2\r\nContent-Type: application/octet-stream\r\nContent-Transfer-Encoding: 7bit\r\n\r\n{}\r\n--m2--\r\n"
            ), wrapped);
            ensure!(!outer.contains(&subject), "subject leaked");
            for modified in [false, true] {
                let wire = if modified { outer.replacen("Subject: [...]", "Subject: forged", 1) } else { outer.clone() };
                let mime = mailparse::parse_mail(wire.as_bytes())?;
                ensure!(mime.ctype.mimetype == "multipart/encrypted" && mime.subparts.len() == 2, "MIME shape");
                ensure!(mime.ctype.params.get("protocol").map(String::as_str) == Some("application/pgp-encrypted"), "MIME protocol");
                ensure!(mime.subparts[0].get_body()?.trim() == "Version: 1", "control part");
                let armored = mime.subparts[1].get_body_raw()?;
                ensure!(armored.starts_with(b"-----BEGIN PGP MESSAGE-----"), "required armor");
                let mut ciphertext = Vec::new();
                sq::armor::Reader::from_bytes(&armored, sq::armor::ReaderMode::Tolerant(Some(sq::armor::Kind::Message)))
                    .read_to_end(&mut ciphertext)?;
                for open in [sq_open, rp_open] {
                    let verified = open(PROFILE, &recipient, &public(&sender)?, &ciphertext)?;
                    ensure!(verified == inner.as_bytes(), "protected bytes changed");
                    let protected = mailparse::parse_mail(&verified)?;
                    ensure!(protected.ctype.params.get("hp").map(String::as_str) == Some("cipher"), "header intent");
                    ensure!(protected.headers.get_first_value("Subject").as_deref() == Some(subject.as_str()), "protected subject");
                    ensure!(protected.headers.get_first_value("X-QuMail-Profile").as_deref() == Some(PROFILE), "protected profile");
                    ensure!(protected.headers.get_all_values("HP-Outer").contains(&"Subject: [...]".to_string()), "outer snapshot");
                    // Outer transport changes do not change authenticated inner fields.
                    // A UI mismatch warning is M5/M6, not implemented here.
                }
            }
        }
        Ok(())
    }

    #[test]
    fn rpgp_rng_failure_returns_no_result() -> Result<()> {
        use pgp::composed::{SecretKeyParamsBuilder, KeyType};
        // rPGP accepts an injected RNG. Its infallible fill API panics on failure;
        // this is not a typed provider error or a test of OpenSSL's RNG failure.
        struct FailedRng;
        impl rand::CryptoRng for FailedRng {}
        impl rand::RngCore for FailedRng {
            fn next_u32(&mut self) -> u32 { panic!("injected entropy failure") }
            fn next_u64(&mut self) -> u64 { panic!("injected entropy failure") }
            fn fill_bytes(&mut self, _: &mut [u8]) { panic!("injected entropy failure") }
            fn try_fill_bytes(&mut self, _: &mut [u8]) -> std::result::Result<(),rand::Error> {
                Err(rand::Error::new("injected entropy failure"))
            }
        }
        let params = SecretKeyParamsBuilder::default().version(pgp::types::KeyVersion::V6)
            .key_type(KeyType::MlDsa65Ed25519).can_sign(true).build()?;
        ensure!(std::panic::catch_unwind(|| params.generate(FailedRng)).is_err(), "RNG failure produced a key result");
        ensure!(std::panic::catch_unwind(|| {
            MessageBuilder::from_bytes("", payload()).seipd_v2(FailedRng,
                pgp::crypto::sym::SymmetricKeyAlgorithm::AES256,
                pgp::crypto::aead::AeadAlgorithm::Gcm, pgp::crypto::aead::ChunkSize::C4KiB)
        }).is_err(), "RNG failure produced an encryption builder");
        Ok(())
    }

    #[test]
    fn published_kem_message_vector_rpgp() -> Result<()> {
        // Publicly published RFC test secrets stay in the ignored locked source
        // cache. No generated or user private key is persisted by this proof.
        let root = std::path::PathBuf::from(std::env::var("M2_PUBLIC_VECTORS")?);
        let secret_bytes = std::fs::read(root.join("v6-mldsa-65-sample-sk.asc"))?;
        let public_bytes = std::fs::read(root.join("v6-mldsa-65-sample-pk.asc"))?;
        let message_bytes = std::fs::read(root.join("v6-mldsa-65-sample-message.asc"))?;
        let key = SignedSecretKey::from_armor_single(secret_bytes.as_slice())?.0;
        let cert = SignedPublicKey::from_armor_single(public_bytes.as_slice())?.0;
        key.verify_bindings()?;
        cert.verify_bindings()?;
        let mut msg = RpMessage::from_armor(message_bytes.as_slice())?.0
            .decrypt(&Password::empty(), &key)?;
        let mut verified = Vec::new();
        (&mut msg).take(MAX_INPUT as u64 + 1).read_to_end(&mut verified)?;
        ensure!(verified.len() <= MAX_INPUT, "limit");
        msg.verify(&cert)?;
        ensure!(verified == b"Testing\n", "published message vector mismatch");
        Ok(())
    }
}
