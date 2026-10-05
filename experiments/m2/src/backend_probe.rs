//! Runs only with the isolated context-accessor Sequoia build; every fault is in
//! a fresh child process. No global OpenSSL mutation in the ordinary proof.
use super::*;
use super::contract::*;
use super::contract::Recipient;
use std::ffi::{c_char,c_int,c_void,CStr};
unsafe extern "C" {
    fn RAND_set_seed_source_type(ctx:*mut c_void,seed:*const c_char,propq:*const c_char)->c_int;
    fn RAND_get0_primary(ctx:*mut c_void)->*mut c_void;
    fn EVP_set_default_properties(ctx:*mut c_void,propq:*const c_char)->c_int;
    fn OSSL_PROVIDER_load(ctx:*mut c_void,name:*const c_char)->*mut c_void;
    fn OSSL_PROVIDER_self_test(provider:*const c_void)->c_int;
    fn OSSL_PROVIDER_unload(provider:*mut c_void)->c_int;
}
fn reasons() -> Vec<String> {
    let mut out=Vec::new();
    unsafe {
        loop {
            let code=openssl_sys::ERR_get_error(); if code==0 {break;}
            let ptr=openssl_sys::ERR_reason_error_string(code);
            out.push(if ptr.is_null() {format!("code:{code}")} else {CStr::from_ptr(ptr).to_string_lossy().into_owned()});
        }
    }
    out
}
fn operation_fails(label:&str,op:impl FnOnce()->bool) -> Result<()> {
    let _=reasons();
    let outcome=std::panic::catch_unwind(std::panic::AssertUnwindSafe(op));
    ensure!(!matches!(outcome,Ok(false)), "{label} unexpectedly succeeded");
    let errors=reasons();
    ensure!(!errors.is_empty(), "{label} did not establish a native error");
    // Only native reason text, never provider debug structures, keys or output.
    eprintln!("{label}: rejected (panic={}); native reasons={errors:?}",outcome.is_err());
    Ok(())
}

// A real native fault introduced immediately after an actual successful health
// probe tests the time-of-check/time-of-use error path, not a mock error return.
struct FailAfterHealth;
impl OpenPgpProvider for FailAfterHealth {
    fn health(&self)->std::result::Result<(),Failure> {
        SequoiaProvider.health()?;
        let result=unsafe {EVP_set_default_properties(sq::qumail_m2_probe_context(),c"provider=qumail-m2-unavailable".as_ptr())};
        if result!=1 {return Err(Failure::Backend(BackendFailure::Health));}
        Ok(())
    }
    fn generate(&self)->std::result::Result<Cert,Failure> {SequoiaProvider.generate()}
    fn seal(&self,s:&Cert,r:&[Vec<u8>],d:&[u8])->std::result::Result<Vec<u8>,Failure>{SequoiaProvider.seal(s,r,d)}
    fn open(&self,r:&Cert,s:&[u8],d:&[u8],out:&mut Vec<u8>)->std::result::Result<Verification,Failure>{SequoiaProvider.open(r,s,d,out)}
}
fn child(case:&str)->Result<()> {
    let root=std::path::PathBuf::from(std::env::var("M2_PUBLIC_VECTORS")?);
    let cert=Cert::from_bytes(&std::fs::read(root.join("v6-mldsa-65-sample-sk.asc"))?)?;
    let recipient=public(&cert)?; // Publicly published fixture, no user data.
    let ctx=sq::qumail_m2_probe_context();
    ensure!(!ctx.is_null(),"unexpected default context");
    if case=="late-provider" || case=="late-provider-open" {
        // Cert import is before failure; the typed call owns all later parsing,
        // fingerprinting and encryption. Its outer catch must contain the panic.
        let policy=CryptoPolicy::new(FailAfterHealth);
        let error=if case=="late-provider-open" {
            let wire=sq_seal(PROFILE,&cert,&[recipient.clone()],&[0u8;32])?;
            policy.open(&Request::selected(),&cert,&recipient,&wire).err()
        } else {policy.seal(&Request::selected(),&cert,&[Recipient {public:&recipient,trust:Trust::VerifiedForExperiment}],&[0u8;32]).err()};
        ensure!(error==Some(Failure::Backend(BackendFailure::Panic)),"real provider panic was not typed/contained");
        eprintln!("late native provider fault ({case}): Backend(Panic), no ciphertext/plaintext/success/fallback");
        return Ok(());
    }
    unsafe {
        if case=="entropy" {
            ensure!(RAND_set_seed_source_type(ctx,c"TEST-RAND".as_ptr(),std::ptr::null())==1,"seed control not installed before first use");
            // Creates the TEST-RAND seed context with no entropy/nonce configured.
            ensure!(RAND_get0_primary(ctx).is_null(),"empty test seed unexpectedly instantiated primary");
        } else if case=="provider" {
            ensure!(EVP_set_default_properties(ctx,c"provider=qumail-m2-unavailable".as_ptr())==1,"property control");
        } else { bail!("unknown fault case"); }
    }
    operation_fails("Sequoia random", || sq::crypto::random(&mut [0u8;32]).is_err())?;
    operation_fails("Sequoia key generation", || generate().is_err())?;
    operation_fails("Sequoia encryption", || sq_seal(PROFILE,&cert,&[recipient.clone()],&[0u8;32]).is_err())?;
    let policy=CryptoPolicy::new(SequoiaProvider);
    ensure!(matches!(policy.generate(&Request::selected()),Err(Failure::Backend(_))),"typed key generation accepted failed backend");
    ensure!(matches!(policy.seal(&Request::selected(),&cert,&[Recipient {public:&recipient,trust:Trust::VerifiedForExperiment}],&[0u8;32]),Err(Failure::Backend(_))),"typed encryption accepted failed backend");
    eprintln!("typed boundary: key generation/encryption rejected; no success/output/fallback");
    Ok(())
}
fn isolated(case:&str,test_name:&str)->Result<()> {
    if std::env::var("QUMAIL_M2_FAULT_CHILD").as_deref()==Ok(case) { return child(case); }
    let mut proc=std::process::Command::new(std::env::current_exe()?)
        .args([test_name,"--exact","--nocapture","--test-threads=1"])
        .env("QUMAIL_M2_FAULT_CHILD",case)
        .stdin(std::process::Stdio::null()).stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped()).spawn()?;
    let start=std::time::Instant::now();
    while proc.try_wait()?.is_none() {
        if start.elapsed()>std::time::Duration::from_secs(30) { proc.kill()?; let _=proc.wait(); bail!("fault probe timeout"); }
        std::thread::sleep(std::time::Duration::from_millis(25));
    }
    let output=proc.wait_with_output()?;
    eprint!("{}",String::from_utf8_lossy(&output.stderr));
    ensure!(output.status.success(),"fault child failed");
    Ok(())
}
#[test]
fn real_entropy_failure() -> Result<()> { isolated("entropy","proof::backend_probe::real_entropy_failure") }
#[test]
fn real_provider_failure() -> Result<()> { isolated("provider","proof::backend_probe::real_provider_failure") }
#[test]
fn real_late_provider_panic_is_contained() -> Result<()> { isolated("late-provider","proof::backend_probe::real_late_provider_panic_is_contained") }
#[test]
fn real_late_provider_open_releases_nothing() -> Result<()> { isolated("late-provider-open","proof::backend_probe::real_late_provider_open_releases_nothing") }
#[test]
fn default_provider_health_is_not_fips_self_test() -> Result<()> {
    let ctx=sq::qumail_m2_probe_context();
    let provider=unsafe { OSSL_PROVIDER_load(ctx,c"default".as_ptr()) };
    ensure!(!provider.is_null(),"default provider unavailable");
    let result=unsafe {OSSL_PROVIDER_self_test(provider)};
    unsafe {OSSL_PROVIDER_unload(provider);}
    ensure!(result==1,"default provider returned failure");
    // Source inspection shows no self_test callback in defltprov dispatch.
    // OpenSSL returns 1 when the callback is absent; not a KAT or FIPS claim.
    ensure!(SequoiaProvider.health().is_ok(),"operational random probe");
    eprintln!("default-provider self_test returned 1; absent callback per source, not assurance; operational random probe passed");
    Ok(())
}
