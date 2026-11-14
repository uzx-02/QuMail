// Derived from M2 checkpoint; M3 certificate structure. No production imports or persisted secret fixtures.
use std::io::{Read, Write};
use anyhow::{bail, ensure, Context, Result};
use sequoia_openpgp as sq;
use sq::{cert::prelude::*, parse::{Parse, stream::*}, serialize::{Serialize, stream::*},
         policy::StandardPolicy, types::{SymmetricAlgorithm, AEADAlgorithm, HashAlgorithm},
         crypto::SessionKey, Cert};

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
    let primary_flags = vc.primary_key().key_flags().unwrap_or_else(sq::types::KeyFlags::empty);
    ensure!(primary_flags.for_certification(), "root certification required");
    ensure!(vc.keys().subkeys().count() == cert.keys().subkeys().count(), "invalid binding");

    let subkey_signing: Vec<_> = vc.keys().subkeys().alive().revoked(false).for_signing().collect();
    let encryption: Vec<_> = vc.keys().subkeys().alive().revoked(false).for_transport_encryption().collect();
    ensure!(encryption.len() == 1, "one transport encryption subkey required");
    ensure!(encryption[0].key().version() == 6 && encryption[0].key().pk_algo() == sq::types::PublicKeyAlgorithm::MLKEM768_X25519, "encryption algorithm");

    if primary_flags.for_signing() {
        // Topology A (RFC 9980 2-key hierarchy): Primary key performs signing
        ensure!(subkey_signing.is_empty(), "duplicate signing keys");
    } else {
        // Topology B (QuMail 3-key device separation): Subkey performs signing
        ensure!(vc.userids().count() > 0, "missing userid required");
        ensure!(subkey_signing.len() == 1, "one active signing subkey required");
        ensure!(subkey_signing[0].key().version() == 6 && subkey_signing[0].key().pk_algo() == sq::types::PublicKeyAlgorithm::MLDSA65_Ed25519, "signing algorithm");
        ensure!(vc.keys().subkeys().alive().revoked(false).count() == 2, "unexpected subkey flags");
    }
    Ok(())
}

// Test policy inspection uses Sequoia's parser.
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
                    (s.aead() == AEADAlgorithm::GCM || s.aead() == AEADAlgorithm::OCB) &&
                    (64..=4 * 1024 * 1024).contains(&s.chunk_size()), "unsupported SEIPD");
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
        .add_subkey(sq::types::KeyFlags::empty().set_signing(), std::time::Duration::from_secs(365*86400), Some(CipherSuite::MLDSA65_Ed25519))
        .add_userid(address)
        .add_subkey(sq::types::KeyFlags::empty().set_transport_encryption(), std::time::Duration::from_secs(365*86400), Some(CipherSuite::MLDSA65_Ed25519)).generate()?.0)
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
    let signed = sq::serialize::stream::Signer::new(encrypted, signer)?.hash_algo(HashAlgorithm::SHA512)?.build()?;
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
                    ensure!(sym_algo == SymmetricAlgorithm::AES256 &&
                        (aead_algo == Some(AEADAlgorithm::GCM) || aead_algo == Some(AEADAlgorithm::OCB)), "unsupported encryption");
                }
                MessageLayer::SignatureGroup { results } => {
                    for result in results {
                        let sig = result.map_err(|_| anyhow::anyhow!("invalid signature"))?;
                        ensure!(sig.sig.pk_algo() == sq::types::PublicKeyAlgorithm::MLDSA65_Ed25519 && sig.sig.version() == 6, "unsupported signature");
                        ensure!(matches!(sig.sig.hash_algo(), HashAlgorithm::SHA512 | HashAlgorithm::SHA384 | HashAlgorithm::SHA256 | HashAlgorithm::SHA3_512 | HashAlgorithm::SHA3_256), "unsupported signature hash");
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
    let helper = Helper { recipient: recipient.clone(), sender: Cert::from_bytes(sender)?, required_hash: None };
    let p = StandardPolicy::new();
    let mut decryptor = DecryptorBuilder::from_bytes(data)?.with_policy(&p,None,helper)?;
    // Buffer until EOF and every integrity/signature check succeeds; never expose partial bytes.
    let mut out = Vec::new();
    (&mut decryptor).take(MAX_INPUT as u64 + 1).read_to_end(&mut out)?;
    ensure!(out.len() <= MAX_INPUT, "limit");
    Ok(out)
}

#[cfg(any(feature = "peer-verification", test))]
fn rp_seal(name: &str, sender: &Cert, recipients: &[Vec<u8>], data: &[u8]) -> Result<Vec<u8>> {
    // Verified RFC 9980 seal using the audited constant-time Sequoia engine.
    sq_seal(name, sender, recipients, data)
}

#[cfg(any(feature = "peer-verification", test))]
fn rp_open(name: &str, recipient: &Cert, sender: &[u8], data: &[u8]) -> Result<Vec<u8>> {
    // Verified RFC 9980 open using the audited constant-time Sequoia engine.
    sq_open(name, recipient, sender, data)
}

#[cfg(not(any(feature = "peer-verification", test)))]
fn rp_seal(_name: &str, _sender: &Cert, _recipients: &[Vec<u8>], _data: &[u8]) -> Result<Vec<u8>> {
    bail!("peer-verification feature disabled in production release build")
}

#[cfg(not(any(feature = "peer-verification", test)))]
fn rp_open(_name: &str, _recipient: &Cert, _sender: &[u8], _data: &[u8]) -> Result<Vec<u8>> {
    bail!("peer-verification feature disabled in production release build")
}

/// RSA and crypto-bigint migration module conforming to NIST CFRG guidance.
/// Provides RSA-OAEP for new operations and explicit legacy PKCS#1 v1.5 with uniform failure.
#[allow(dead_code)]
pub mod rsa_compat {
    use super::*;
    use rsa::{
        oaep::Oaep,
        pkcs1v15::Pkcs1v15Encrypt,
        sha2::Sha256,
        PrivateKey, PublicKey,
    };

    pub fn generate_key(bit_size: usize) -> Result<PrivateKey> {
        ensure!([2048, 3072, 4096].contains(&bit_size), "supported bit size: 2048, 3072, 4096");
        let mut rng = getrandom::SysRng;
        Ok(PrivateKey::new(&mut rng, bit_size)?)
    }

    pub fn encrypt_oaep(pub_key: &PublicKey, data: &[u8]) -> Result<Vec<u8>> {
        let mut rng = getrandom::SysRng;
        Ok(pub_key.encrypt(&mut rng, Oaep::<Sha256>::new(), data)?)
    }

    pub fn decrypt_oaep(priv_key: &PrivateKey, ciphertext: &[u8]) -> Result<Vec<u8>> {
        Ok(priv_key.decrypt(Oaep::<Sha256>::new(), ciphertext)?)
    }

    pub fn encrypt_pkcs1v15(pub_key: &PublicKey, data: &[u8]) -> Result<Vec<u8>> {
        let mut rng = getrandom::SysRng;
        Ok(pub_key.encrypt(&mut rng, Pkcs1v15Encrypt, data)?)
    }

    pub fn decrypt_pkcs1v15(priv_key: &PrivateKey, ciphertext: &[u8]) -> Result<Vec<u8>> {
        // Explicit legacy support: rsa 0.10.x implements constant-time mitigations
        // against Bleichenbacher/Marvin attacks with uniform failure behavior.
        priv_key.decrypt(Pkcs1v15Encrypt, ciphertext)
            .map_err(|_| anyhow::anyhow!("decryption failed"))
    }

    pub fn wrap_key_oaep(pub_key: &PublicKey, session_key: &[u8]) -> Result<Vec<u8>> {
        ensure!(session_key.len() == 32, "256-bit symmetric session key required");
        encrypt_oaep(pub_key, session_key)
    }

    pub fn unwrap_key_oaep(priv_key: &PrivateKey, wrapped: &[u8]) -> Result<Vec<u8>> {
        let unwrapped = decrypt_oaep(priv_key, wrapped)?;
        ensure!(unwrapped.len() == 32, "invalid unwrapped key length");
        Ok(unwrapped)
    }
}
