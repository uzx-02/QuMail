//! Test-only shared service boundary. No production registration or fallback.
use super::*;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Profile { CompositeGcm }
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProfileRejection { Malformed, Unknown, Weak, Unsupported }
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BackendFailure { Entropy, Operation, Panic, Health }
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Failure {
    RejectedProfile(ProfileRejection), ProviderUnavailable,
    Backend(BackendFailure), Verification, ResourceLimit,
    InvalidRecipient, UntrustedRecipient, ForbiddenRoute, UnsupportedExtension,
}
type Outcome<T> = std::result::Result<T, Failure>;
impl Profile {
    pub fn parse(name: &str) -> Outcome<Self> {
        if name.is_empty() || name.len() > 80 || !name.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'-') {
            return Err(Failure::RejectedProfile(ProfileRejection::Malformed));
        }
        match name {
            PROFILE => Ok(Self::CompositeGcm),
            "Level1" | "Level2" | "Level3" | "plaintext" | "classical" => Err(Failure::RejectedProfile(ProfileRejection::Weak)),
            n if n.starts_with("M2-EXPERIMENT-") => Err(Failure::RejectedProfile(ProfileRejection::Unsupported)),
            _ => Err(Failure::RejectedProfile(ProfileRejection::Unknown)),
        }
    }
}
#[derive(Clone, Copy)]
pub enum Trust { VerifiedForExperiment, Unknown, Changed }
pub struct Recipient<'a> { pub public: &'a [u8], pub trust: Trust }
#[derive(Clone, Copy, PartialEq)]
pub enum Route { Endpoint, Portal, Simulator }
pub struct Request<'a> { pub profile: &'a str, pub route: Route, pub unknown_critical_extension: bool }
impl<'a> Request<'a> {
    pub fn selected() -> Self { Self { profile: PROFILE, route: Route::Endpoint, unknown_critical_extension: false } }
}
pub struct VerifiedPlaintext(Vec<u8>); // Intentionally no Debug/Display/Serialize.
impl VerifiedPlaintext { pub fn bytes(&self) -> &[u8] { &self.0 } }
#[derive(Clone, Copy)]
pub struct Verification { pub integrity: bool, pub composite_signature: bool, pub profile: Profile }

// A trusted backend can write tentative bytes; only the policy boundary can
// construct VerifiedPlaintext. An error/panic/absent verification drops staging.
pub trait OpenPgpProvider {
    fn health(&self) -> Outcome<()>;
    fn generate(&self) -> Outcome<Cert>;
    fn seal(&self, sender: &Cert, recipients: &[Vec<u8>], data: &[u8]) -> Outcome<Vec<u8>>;
    fn open(&self, recipient: &Cert, sender: &[u8], data: &[u8], staging: &mut Vec<u8>) -> Outcome<Verification>;
}
pub struct SequoiaProvider;
impl OpenPgpProvider for SequoiaProvider {
    fn health(&self) -> Outcome<()> {
        let version = unsafe { std::ffi::CStr::from_ptr(openssl_sys::OpenSSL_version(0)) };
        if version.to_bytes() != b"OpenSSL 3.5.9 29 Sep 2026" { return Err(Failure::ProviderUnavailable); }
        sq::crypto::random(&mut [0u8; 32]).map_err(|_| Failure::Backend(BackendFailure::Entropy))
    }
    fn generate(&self) -> Outcome<Cert> { super::generate().map_err(|_| Failure::Backend(BackendFailure::Operation)) }
    fn seal(&self, sender: &Cert, recipients: &[Vec<u8>], data: &[u8]) -> Outcome<Vec<u8>> {
        sq_seal(PROFILE, sender, recipients, data).map_err(|_| Failure::Backend(BackendFailure::Operation))
    }
    fn open(&self, recipient: &Cert, sender: &[u8], data: &[u8], staging: &mut Vec<u8>) -> Outcome<Verification> {
        let bytes = sq_open(PROFILE, recipient, sender, data).map_err(|_| Failure::Verification)?;
        staging.extend_from_slice(&bytes);
        Ok(Verification { integrity: true, composite_signature: true, profile: Profile::CompositeGcm })
    }
}
pub struct CryptoPolicy<P: OpenPgpProvider> { backend: P }
impl<P: OpenPgpProvider> CryptoPolicy<P> {
    pub fn new(backend: P) -> Self { Self { backend } }
    fn checked<T>(&self, op: impl FnOnce() -> Outcome<T>) -> Outcome<T> {
        std::panic::catch_unwind(std::panic::AssertUnwindSafe(op))
            .map_err(|_| Failure::Backend(BackendFailure::Panic))?
    }
    fn authorize(&self, request: &Request, len: usize) -> Outcome<Profile> {
        let profile = Profile::parse(request.profile)?;
        if request.route != Route::Endpoint { return Err(Failure::ForbiddenRoute); }
        if request.unknown_critical_extension { return Err(Failure::UnsupportedExtension); }
        if len > MAX_INPUT { return Err(Failure::ResourceLimit); }
        self.checked(|| self.backend.health())?;
        Ok(profile)
    }
    pub fn generate(&self, request: &Request) -> Outcome<Cert> {
        self.authorize(request, 0)?;
        self.checked(|| self.backend.generate())
    }
    pub fn seal(&self, request: &Request, sender: &Cert, recipients: &[Recipient], data: &[u8]) -> Outcome<Vec<u8>> {
        self.checked(|| self.seal_inner(request,sender,recipients,data))
    }
    fn seal_inner(&self, request: &Request, sender: &Cert, recipients: &[Recipient], data: &[u8]) -> Outcome<Vec<u8>> {
        self.authorize(request, data.len())?;
        if recipients.is_empty() || recipients.len() > 32 { return Err(Failure::ResourceLimit); }
        let mut public_keys = Vec::new();
        for r in recipients {
            if !matches!(r.trust, Trust::VerifiedForExperiment) { return Err(Failure::UntrustedRecipient); }
            if r.public.len() > MAX_INPUT { return Err(Failure::ResourceLimit); }
            let cert = Cert::from_bytes(r.public).map_err(|_| Failure::InvalidRecipient)?;
            if cert.is_tsk() || check_certificate(&cert).is_err() { return Err(Failure::InvalidRecipient); }
            public_keys.push(r.public.to_vec());
        }
        let encrypted = self.checked(|| self.backend.seal(sender, &public_keys, data))?;
        if encrypted.len() > MAX_INPUT { return Err(Failure::ResourceLimit); }
        inspect_envelope(&encrypted).map_err(|_| Failure::Backend(BackendFailure::Operation))?;
        Ok(encrypted)
    }
    pub fn open(&self, request: &Request, recipient: &Cert, sender: &[u8], data: &[u8]) -> Outcome<VerifiedPlaintext> {
        self.checked(|| self.open_inner(request,recipient,sender,data))
    }
    fn open_inner(&self, request: &Request, recipient: &Cert, sender: &[u8], data: &[u8]) -> Outcome<VerifiedPlaintext> {
        let profile = self.authorize(request, data.len())?;
        if sender.len() > MAX_INPUT { return Err(Failure::ResourceLimit); }
        inspect_envelope(data).map_err(|_| Failure::Verification)?;
        let mut staging = Vec::new();
        let checked = self.checked(|| self.backend.open(recipient, sender, data, &mut staging))?;
        if staging.len() > MAX_INPUT { return Err(Failure::ResourceLimit); }
        if !checked.integrity || !checked.composite_signature || checked.profile != profile { return Err(Failure::Verification); }
        Ok(VerifiedPlaintext(staging))
    }
}

#[test]
fn policy_matrix_and_real_provider() -> Result<()> {
    let policy = CryptoPolicy::new(SequoiaProvider);
    let sender = policy.generate(&Request::selected()).map_err(|e| anyhow::anyhow!("{e:?}"))?;
    let recipient = generate()?;
    let pubkey = public(&recipient)?;
    let recipients = [Recipient { public: &pubkey, trust: Trust::VerifiedForExperiment }];
    let payload: Vec<u8> = (0..256).map(|_| rand::random()).collect();
    let enc = policy.seal(&Request::selected(), &sender, &recipients, &payload).map_err(|e| anyhow::anyhow!("{e:?}"))?;
    let sender_pub = public(&sender)?;
    let opened = policy.open(&Request::selected(), &recipient, &sender_pub, &enc).map_err(|e| anyhow::anyhow!("{e:?}"))?;
    ensure!(opened.bytes() == payload, "typed exchange");
    for (name, rejection) in [("", ProfileRejection::Malformed), ("x\0", ProfileRejection::Malformed),
        ("unknown", ProfileRejection::Unknown), ("Level1", ProfileRejection::Weak), ("Level2", ProfileRejection::Weak),
        ("Level3", ProfileRejection::Weak), ("plaintext", ProfileRejection::Weak), ("classical", ProfileRejection::Weak),
        ("M2-EXPERIMENT-RFC9980-AES256-OCB", ProfileRejection::Unsupported)] {
        let r = Request { profile: name, ..Request::selected() };
        let expected = Failure::RejectedProfile(rejection);
        ensure!(policy.generate(&r).err() == Some(expected), "keygen policy");
        ensure!(policy.seal(&r,&sender,&recipients,&payload).err() == Some(expected), "send policy");
        ensure!(policy.open(&r,&recipient,&sender_pub,&enc).err() == Some(expected), "open policy");
    }
    for trust in [Trust::Unknown, Trust::Changed] {
        ensure!(policy.seal(&Request::selected(),&sender,&[Recipient { public: &pubkey, trust }],&payload).err() == Some(Failure::UntrustedRecipient), "trust gate");
    }
    for (route, critical, expected) in [(Route::Portal,false,Failure::ForbiddenRoute), (Route::Simulator,false,Failure::ForbiddenRoute), (Route::Endpoint,true,Failure::UnsupportedExtension)] {
        let r = Request { route, unknown_critical_extension: critical, ..Request::selected() };
        ensure!(policy.generate(&r).err() == Some(expected), "keygen route/extension");
        ensure!(policy.seal(&r,&sender,&recipients,&payload).err() == Some(expected), "seal route/extension");
        ensure!(policy.open(&r,&recipient,&sender_pub,&enc).err() == Some(expected), "open route/extension");
    }
    ensure!(policy.seal(&Request::selected(),&sender,&recipients,&vec![0;MAX_INPUT+1]).err() == Some(Failure::ResourceLimit), "send limit");
    for count in [0,33] {
        let many:Vec<_>=(0..count).map(|_| Recipient {public:&pubkey,trust:Trust::VerifiedForExperiment}).collect();
        ensure!(policy.seal(&Request::selected(),&sender,&many,&payload).err()==Some(Failure::ResourceLimit),"recipient-count limit");
    }
    ensure!(policy.open(&Request::selected(),&recipient,&sender_pub,&vec![0;MAX_INPUT+1]).err() == Some(Failure::ResourceLimit), "open limit");
    for bad in [vec![0;32], secret(&recipient)?, public(&CertBuilder::new().add_transport_encryption_subkey().generate()?.0)?] {
        ensure!(policy.seal(&Request::selected(),&sender,&[Recipient { public: &bad, trust: Trust::VerifiedForExperiment }],&payload).err() == Some(Failure::InvalidRecipient), "invalid public material");
    }
    let mut altered = enc.clone(); *altered.last_mut().unwrap() ^= 1;
    for ciphertext in [&altered[..], &enc[..enc.len()-1]] {
        ensure!(policy.open(&Request::selected(),&recipient,&sender_pub,ciphertext).err() == Some(Failure::Verification), "verification result");
    }
    ensure!(policy.open(&Request::selected(),&generate()?,&sender_pub,&enc).err() == Some(Failure::Verification), "wrong recipient");
    ensure!(policy.open(&Request::selected(),&recipient,&public(&generate()?)?,&enc).err() == Some(Failure::Verification), "wrong signer");
    Ok(())
}

#[test]
fn wire_profile_and_critical_extension_rejection() -> Result<()> {
    let sender=generate()?; let recipient=generate()?;
    let p=StandardPolicy::new(); let policy=CryptoPolicy::new(SequoiaProvider);
    // Valid provider-generated packets with unsupported settings, not byte-offset
    // mutations masquerading as a profile test. Include positive control.
    for (aead,hash,critical) in [(AEADAlgorithm::GCM,HashAlgorithm::SHA512,false),
        (AEADAlgorithm::OCB,HashAlgorithm::SHA512,false),
        (AEADAlgorithm::GCM,HashAlgorithm::SHA256,false),
        (AEADAlgorithm::GCM,HashAlgorithm::SHA512,true)] {
        let mut out=Vec::new();
        let keys=recipient.keys().with_policy(&p,None).for_transport_encryption();
        let pair=sender.primary_key().key().clone().parts_into_secret()?.into_keypair()?;
        let enc=Encryptor::for_recipients(Message::new(&mut out),keys).symmetric_algo(SymmetricAlgorithm::AES256).aead_algo(aead).build()?;
        let mut template=sq::packet::signature::SignatureBuilder::new(sq::types::SignatureType::Binary);
        if critical { template=template.set_notation("unknown-critical@example.invalid",b"m2",None,true)?; }
        let signer=Signer::with_template(enc,pair,template)?.hash_algo(hash)?.build()?;
        let mut lit=LiteralWriter::new(signer).build()?;
        lit.write_all(&[0u8;32])?; lit.finalize()?;
        let result=policy.open(&Request::selected(),&recipient,&public(&sender)?,&out);
        if aead==AEADAlgorithm::GCM && hash==HashAlgorithm::SHA512 && !critical {
            ensure!(result.is_ok(),"wire positive control");
        } else { ensure!(result.err()==Some(Failure::Verification),"unsupported wire profile accepted"); }
    }
    Ok(())
}

#[test]
fn mock_failures_never_release_staging_or_fallback() -> Result<()> {
    use std::cell::Cell;
    struct Mock { health: Outcome<()>, fault: u8, calls: Cell<usize> }
    impl OpenPgpProvider for Mock {
        fn health(&self) -> Outcome<()> { self.health }
        fn generate(&self) -> Outcome<Cert> { self.calls.set(self.calls.get()+1); Err(Failure::Backend(BackendFailure::Operation)) }
        fn seal(&self,_:&Cert,_:&[Vec<u8>],_:&[u8])->Outcome<Vec<u8>> { self.calls.set(self.calls.get()+1); Err(Failure::Backend(BackendFailure::Operation)) }
        fn open(&self,_:&Cert,_:&[u8],_:&[u8],out:&mut Vec<u8>)->Outcome<Verification> {
            self.calls.set(self.calls.get()+1); out.extend_from_slice(&[42;64]);
            match self.fault {
                0 => Err(Failure::Backend(BackendFailure::Operation)),
                1 => panic!("synthetic backend panic; no secret diagnostic"),
                2 => Ok(Verification { integrity: false, composite_signature: true, profile: Profile::CompositeGcm }),
                3 => Ok(Verification { integrity: true, composite_signature: false, profile: Profile::CompositeGcm }),
                _ => { out.resize(MAX_INPUT+1,0); Ok(Verification { integrity:true, composite_signature:true, profile:Profile::CompositeGcm }) }
            }
        }
    }
    let a=generate()?; let b=generate()?; let bp=public(&b)?;
    let wire=sq_seal(PROFILE,&a,&[bp.clone()],&[7;32])?;
    for health in [Err(Failure::ProviderUnavailable),Err(Failure::Backend(BackendFailure::Health)),Err(Failure::Backend(BackendFailure::Entropy))] {
        let p=CryptoPolicy::new(Mock {health,fault:0,calls:Cell::new(0)});
        ensure!(p.generate(&Request::selected()).err() == health.err(), "health keygen");
        ensure!(p.seal(&Request::selected(),&a,&[Recipient {public:&bp,trust:Trust::VerifiedForExperiment}],&[]).err()==health.err(), "health seal");
        ensure!(p.open(&Request::selected(),&b,&public(&a)?,&wire).err()==health.err(), "health open");
        ensure!(p.backend.calls.get()==0, "backend used after failed gate");
    }
    for (fault,expected) in [(0,Failure::Backend(BackendFailure::Operation)),(1,Failure::Backend(BackendFailure::Panic)),(2,Failure::Verification),(3,Failure::Verification),(4,Failure::ResourceLimit)] {
        let p=CryptoPolicy::new(Mock {health:Ok(()),fault,calls:Cell::new(0)});
        ensure!(p.open(&Request::selected(),&b,&public(&a)?,&wire).err()==Some(expected), "staging leaked as success");
        ensure!(p.backend.calls.get()==1, "unexpected retry/substitution");
        ensure!(p.generate(&Request::selected()).err()==Some(Failure::Backend(BackendFailure::Operation)), "keygen backend failure");
        ensure!(p.seal(&Request::selected(),&a,&[Recipient {public:&bp,trust:Trust::VerifiedForExperiment}],&[]).err()==Some(Failure::Backend(BackendFailure::Operation)), "seal backend failure");
    }
    Ok(())
}
