// Derived from M2 checkpoint; M3 certificate structure. No production imports or persisted secret fixtures.
use std::io::{Read, Write};
use anyhow::{bail, ensure, Context, Result};
use sequoia_openpgp as sq;
use sq::{cert::prelude::*, parse::{Parse, stream::*}, serialize::{Serialize, stream::*},
         policy::StandardPolicy, types::{SymmetricAlgorithm, AEADAlgorithm, HashAlgorithm},
         crypto::SessionKey, Cert};
use pgp::{composed::{Deserializable, Message as RpMessage, MessageBuilder, SignedPublicKey, SignedSecretKey},
          types::{Password, KeyDetails}};

pub const PROFILE: &str = "M2-EXPERIMENT-RFC9980-AES256-GCM";
const MAX_INPUT: usize = 1024 * 1024;

fn profile(name: &str) -> Result<()> {
    ensure!(name == PROFILE, "unsupported experimental profile");
    Ok(())
}

fn check_certificate(cert: &Cert) -> Result<()> {
    ensure!(cert.primary_key().key().version() == 6 &&
        cert.primary_key().key().pk_algo() == sq::types::PublicKeyAlgorithm::MLDSA65_Ed25519, "unsupported certificate");
    let p = StandardPolicy::new();
    let vc = cert.with_policy(&p, None)?;
    vc.alive()?;
    ensure!(!matches!(vc.revocation_status(), sq::types::RevocationStatus::Revoked(_)), "revoked");
    ensure!(vc.primary_key().key_flags().map(|f| f.for_certification() && !f.for_signing()).unwrap_or(false), "root purpose");
    ensure!(vc.keys().subkeys().count() == cert.keys().subkeys().count(), "invalid binding");
    let signing: Vec<_> = vc.keys().subkeys().alive().revoked(false).for_signing().collect();
    let encryption: Vec<_> = vc.keys().subkeys().alive().revoked(false).for_transport_encryption().collect();
    ensure!(signing.len()==1 && encryption.len()==1, "one active device");
    ensure!(signing[0].key().version()==6 && signing[0].key().pk_algo()==sq::types::PublicKeyAlgorithm::MLDSA65_Ed25519, "signing algorithm");
    ensure!(encryption[0].key().version()==6 && encryption[0].key().pk_algo()==sq::types::PublicKeyAlgorithm::MLKEM768_X25519, "encryption algorithm");
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

fn generate(address: &str) -> Result<Cert> {
    Ok(CertBuilder::new().set_profile(sq::Profile::RFC9580)?
        .set_cipher_suite(CipherSuite::MLDSA65_Ed25519)
        .set_primary_key_flags(sq::types::KeyFlags::empty().set_certification())
        .set_validity_period(std::time::Duration::from_secs(3*365*86400))
        .add_subkey(sq::types::KeyFlags::empty().set_signing(), std::time::Duration::from_secs(365*86400), None)
        .add_userid(address)
        .add_subkey(sq::types::KeyFlags::empty().set_transport_encryption(), std::time::Duration::from_secs(365*86400), None).generate()?.0)
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
    let signer = sender.keys().unencrypted_secret().with_policy(&p,None).alive().revoked(false).for_signing().next().ok_or_else(|| anyhow::anyhow!("signer"))?.key().clone().into_keypair()?;
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
    let p = StandardPolicy::new();
    let signing_fpr = sender.keys().with_policy(&p,None).alive().revoked(false).for_signing().next().context("signer")?.key().fingerprint();
    let signing = key.secret_subkeys.iter().find(|k| k.key.fingerprint().as_bytes()==signing_fpr.as_bytes()).context("peer signing subkey")?;
    builder.sign(&signing.key, Password::empty(), pgp::crypto::hash::HashAlgorithm::Sha512);
    for cert in &certs {
        cert.verify_bindings()?;
        let raw = recipients[certs.iter().position(|c| std::ptr::eq(c,cert)).context("recipient")?].as_slice();
        let sq_cert = Cert::from_bytes(raw)?;
        let fpr = sq_cert.keys().with_policy(&p,None).alive().revoked(false).for_transport_encryption().next().context("recipient key")?.key().fingerprint();
        let sub = cert.public_subkeys.iter().find(|k| k.key.fingerprint().as_bytes()==fpr.as_bytes()).context("peer encryption subkey")?;
        builder.encrypt_to_key(rand::thread_rng(), sub)?;
    }
    Ok(builder.to_vec(rand::thread_rng())?)
}
fn rp_open(name: &str, recipient: &Cert, sender: &[u8], data: &[u8]) -> Result<Vec<u8>> {
    profile(name)?;
    inspect_envelope(data)?;
    let secret_bytes = secret(recipient)?;
    let key = SignedSecretKey::from_bytes(secret_bytes.as_slice())?;
    key.verify_bindings()?;
    let sq_sender = Cert::from_bytes(sender)?;
    let sender = SignedPublicKey::from_bytes(sender)?;
    sender.verify_bindings()?;
    let mut msg = RpMessage::from_bytes(data)?.decrypt(&Password::empty(), &key)?;
    let mut out = Vec::new();
    (&mut msg).take(MAX_INPUT as u64 + 1).read_to_end(&mut out)?;
    ensure!(out.len() <= MAX_INPUT, "limit");
    let p = StandardPolicy::new();
    let fpr = sq_sender.keys().with_policy(&p,None).alive().revoked(false).for_signing().next().context("sender key")?.key().fingerprint();
    let sub = sender.public_subkeys.iter().find(|k| k.key.fingerprint().as_bytes()==fpr.as_bytes()).context("peer verifier")?;
    let sig = msg.verify(&sub.key)?;
    let config = sig.config().ok_or_else(|| anyhow::anyhow!("signature config"))?;
    ensure!(config.pub_alg == pgp::crypto::public_key::PublicKeyAlgorithm::MlDsa65Ed25519 &&
        config.hash_alg == pgp::crypto::hash::HashAlgorithm::Sha512, "unsupported signature");
    Ok(out)
}

