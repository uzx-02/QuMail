use std::sync::Mutex;
use anyhow::{bail, ensure, Context, Result};
use jni::objects::{JByteArray, JClass, JObject, JObjectArray, JString};
use jni::sys::{jboolean, jbyteArray, jobjectArray, JNI_FALSE, JNI_TRUE};
use jni::JNIEnv;
use zeroize::Zeroizing;
use hybrid_array::Array;
use ml_dsa::{signature::Signer, Keypair, MlDsa65, SigningKey};
use aes_gcm::{aead::{Aead, KeyInit}, Aes256Gcm, Nonce};
use rand::RngCore;

use crate::provider::*;
use sequoia_openpgp as sq;
use sq::{Cert, policy::StandardPolicy, parse::Parse};

struct VaultState {
    secret_cert: Option<Zeroizing<Vec<u8>>>,
    public_cert: Option<Vec<u8>>,
}

static VAULT: Mutex<VaultState> = Mutex::new(VaultState {
    secret_cert: None,
    public_cert: None,
});

fn helper_directory_pop(c: &Cert, message: &[u8]) -> Result<(Vec<u8>, Vec<u8>)> {
    ensure!(message.len() <= 1024 * 1024, "limit");
    check_certificate(c)?;

    let p = StandardPolicy::new();
    let signing_key = c.keys().unencrypted_secret().with_policy(&p, None)
        .alive().revoked(false).for_signing().next().context("signing subkey")?;
    let key = signing_key.key();

    let expected_public = match key.mpis() {
        sq::crypto::mpi::PublicKey::MLDSA65_Ed25519 { mldsa, .. } => mldsa.to_vec(),
        _ => bail!("unexpected public key type"),
    };

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

    let seed_arr = Zeroizing::new(Array::from(*seed));
    let pair = SigningKey::<MlDsa65>::from_seed(&seed_arr);

    let verifying = pair.verifying_key().encode().to_vec();
    ensure!(verifying == expected_public, "inconsistent signing key");

    let signature = pair.sign(message).encode().to_vec();

    ensure!(verifying.len() == 1952 && signature.len() == 3309, "directory proof");
    Ok((verifying, signature))
}

#[no_mangle]
pub extern "system" fn Java_com_qumail_CryptoBridgeNative_nativeGenerateIdentity(
    mut env: JNIEnv,
    _class: JClass,
    email: JString,
) -> jobjectArray {
    let email_str: String = match env.get_string(&email) {
        Ok(s) => s.into(),
        Err(e) => {
            let _ = env.throw_new("java/lang/IllegalArgumentException", format!("Invalid email: {}", e));
            return std::ptr::null_mut();
        }
    };

    let cert = match generate(&email_str) {
        Ok(c) => c,
        Err(e) => {
            let _ = env.throw_new("java/lang/RuntimeException", format!("Keygen failed: {}", e));
            return std::ptr::null_mut();
        }
    };

    let pub_bytes = match public(&cert) {
        Ok(b) => b,
        Err(e) => {
            let _ = env.throw_new("java/lang/RuntimeException", format!("Public export failed: {}", e));
            return std::ptr::null_mut();
        }
    };

    let sec_bytes = match secret(&cert) {
        Ok(b) => Zeroizing::new(b),
        Err(e) => {
            let _ = env.throw_new("java/lang/RuntimeException", format!("Secret export failed: {}", e));
            return std::ptr::null_mut();
        }
    };

    let byte_array_class = match env.find_class("[B") {
        Ok(c) => c,
        Err(_) => return std::ptr::null_mut(),
    };

    let result_array = match env.new_object_array(2, &byte_array_class, &JObject::null()) {
        Ok(a) => a,
        Err(_) => return std::ptr::null_mut(),
    };

    let pub_jbytes = match env.byte_array_from_slice(&pub_bytes) {
        Ok(a) => a,
        Err(_) => return std::ptr::null_mut(),
    };
    let sec_jbytes = match env.byte_array_from_slice(&sec_bytes) {
        Ok(a) => a,
        Err(_) => return std::ptr::null_mut(),
    };

    let _ = env.set_object_array_element(&result_array, 0, &pub_jbytes);
    let _ = env.set_object_array_element(&result_array, 1, &sec_jbytes);

    result_array.into_raw()
}

#[no_mangle]
pub extern "system" fn Java_com_qumail_CryptoBridgeNative_nativeSealMessage(
    mut env: JNIEnv,
    _class: JClass,
    sender_secret: JByteArray,
    recipient_publics: JObjectArray,
    plaintext: JByteArray,
) -> jbyteArray {
    let sec_bytes = match env.convert_byte_array(&sender_secret) {
        Ok(b) => Zeroizing::new(b),
        Err(e) => {
            let _ = env.throw_new("java/lang/IllegalArgumentException", format!("Bad sender secret: {}", e));
            return std::ptr::null_mut();
        }
    };

    let sender_cert = match Cert::from_bytes(&sec_bytes) {
        Ok(c) => c,
        Err(e) => {
            let _ = env.throw_new("java/lang/IllegalArgumentException", format!("Invalid sender cert: {}", e));
            return std::ptr::null_mut();
        }
    };

    let count = match env.get_array_length(&recipient_publics) {
        Ok(l) => l as usize,
        Err(_) => return std::ptr::null_mut(),
    };

    if count == 0 || count > 32 {
        let _ = env.throw_new("java/lang/IllegalArgumentException", "Recipient count must be between 1 and 32");
        return std::ptr::null_mut();
    }

    let mut recipients = Vec::with_capacity(count);
    for i in 0..count {
        let elem = match env.get_object_array_element(&recipient_publics, i as i32) {
            Ok(obj) => JByteArray::from(obj),
            Err(_) => return std::ptr::null_mut(),
        };
        let b = match env.convert_byte_array(&elem) {
            Ok(bytes) => bytes,
            Err(_) => return std::ptr::null_mut(),
        };
        recipients.push(b);
    }

    let pt_bytes = match env.convert_byte_array(&plaintext) {
        Ok(b) => b,
        Err(e) => {
            let _ = env.throw_new("java/lang/IllegalArgumentException", format!("Bad plaintext: {}", e));
            return std::ptr::null_mut();
        }
    };

    let sealed_raw = match sq_seal(PROFILE, &sender_cert, &recipients, pt_bytes.as_slice()) {
        Ok(packet) => packet,
        Err(e) => {
            let _ = env.throw_new("java/lang/RuntimeException", format!("Seal failed: {}", e));
            return std::ptr::null_mut();
        }
    };

    let mut armored = Vec::new();
    let write_res = (|| -> Result<()> {
        let mut writer = sq::armor::Writer::new(&mut armored, sq::armor::Kind::Message)?;
        std::io::Write::write_all(&mut writer, &sealed_raw)?;
        writer.finalize()?;
        Ok(())
    })();

    if let Err(e) = write_res {
        let _ = env.throw_new("java/lang/RuntimeException", format!("Armoring failed: {}", e));
        return std::ptr::null_mut();
    }

    match env.byte_array_from_slice(&armored) {
        Ok(a) => a.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

#[no_mangle]
pub extern "system" fn Java_com_qumail_CryptoBridgeNative_nativeOpenMessage(
    mut env: JNIEnv,
    _class: JClass,
    recipient_secret: JByteArray,
    sender_public: JByteArray,
    envelope: JByteArray,
) -> jbyteArray {
    let sec_bytes = match env.convert_byte_array(&recipient_secret) {
        Ok(b) => Zeroizing::new(b),
        Err(e) => {
            let _ = env.throw_new("java/lang/IllegalArgumentException", format!("Bad recipient secret: {}", e));
            return std::ptr::null_mut();
        }
    };

    let recipient_cert = match Cert::from_bytes(&sec_bytes) {
        Ok(c) => c,
        Err(e) => {
            let _ = env.throw_new("java/lang/IllegalArgumentException", format!("Invalid recipient cert: {}", e));
            return std::ptr::null_mut();
        }
    };

    let sender_bytes = match env.convert_byte_array(&sender_public) {
        Ok(b) => b,
        Err(e) => {
            let _ = env.throw_new("java/lang/IllegalArgumentException", format!("Bad sender public: {}", e));
            return std::ptr::null_mut();
        }
    };

    let env_bytes = match env.convert_byte_array(&envelope) {
        Ok(b) => b,
        Err(e) => {
            let _ = env.throw_new("java/lang/IllegalArgumentException", format!("Bad envelope bytes: {}", e));
            return std::ptr::null_mut();
        }
    };

    let content = match sq_open(PROFILE, &recipient_cert, sender_bytes.as_slice(), env_bytes.as_slice()) {
        Ok(c) => c,
        Err(e) => {
            let _ = env.throw_new("java/lang/RuntimeException", format!("Open / Decrypt failed: {}", e));
            return std::ptr::null_mut();
        }
    };

    match env.byte_array_from_slice(&content) {
        Ok(a) => a.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

#[no_mangle]
pub extern "system" fn Java_com_qumail_CryptoBridgeNative_nativeEncryptAttachment(
    mut env: JNIEnv,
    _class: JClass,
    key: JByteArray,
    plaintext: JByteArray,
) -> jobjectArray {
    let k_bytes = match env.convert_byte_array(&key) {
        Ok(b) => Zeroizing::new(b),
        Err(_) => return std::ptr::null_mut(),
    };
    if k_bytes.len() != 32 {
        let _ = env.throw_new("java/lang/IllegalArgumentException", "Key must be 32 bytes for AES-256-GCM");
        return std::ptr::null_mut();
    }

    let pt = match env.convert_byte_array(&plaintext) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };

    let mut nonce_bytes = [0u8; 12];
    rand::thread_rng().fill_bytes(&mut nonce_bytes);
    let nonce = Nonce::from_slice(&nonce_bytes);

    let cipher = match Aes256Gcm::new_from_slice(&k_bytes) {
        Ok(c) => c,
        Err(e) => {
            let _ = env.throw_new("java/lang/RuntimeException", format!("Cipher init failed: {}", e));
            return std::ptr::null_mut();
        }
    };

    let ciphertext = match cipher.encrypt(nonce, pt.as_ref()) {
        Ok(ct) => ct,
        Err(e) => {
            let _ = env.throw_new("java/lang/RuntimeException", format!("Encryption failed: {}", e));
            return std::ptr::null_mut();
        }
    };

    let byte_array_class = match env.find_class("[B") {
        Ok(c) => c,
        Err(_) => return std::ptr::null_mut(),
    };

    let result_array = match env.new_object_array(2, &byte_array_class, &JObject::null()) {
        Ok(a) => a,
        Err(_) => return std::ptr::null_mut(),
    };

    let ct_jbytes = match env.byte_array_from_slice(&ciphertext) {
        Ok(a) => a,
        Err(_) => return std::ptr::null_mut(),
    };
    let nonce_jbytes = match env.byte_array_from_slice(&nonce_bytes) {
        Ok(a) => a,
        Err(_) => return std::ptr::null_mut(),
    };

    let _ = env.set_object_array_element(&result_array, 0, &ct_jbytes);
    let _ = env.set_object_array_element(&result_array, 1, &nonce_jbytes);

    result_array.into_raw()
}

#[no_mangle]
pub extern "system" fn Java_com_qumail_CryptoBridgeNative_nativeDecryptAttachment(
    mut env: JNIEnv,
    _class: JClass,
    key: JByteArray,
    ciphertext: JByteArray,
    nonce: JByteArray,
) -> jbyteArray {
    let k_bytes = match env.convert_byte_array(&key) {
        Ok(b) => Zeroizing::new(b),
        Err(_) => return std::ptr::null_mut(),
    };
    if k_bytes.len() != 32 {
        let _ = env.throw_new("java/lang/IllegalArgumentException", "Key must be 32 bytes for AES-256-GCM");
        return std::ptr::null_mut();
    }

    let ct = match env.convert_byte_array(&ciphertext) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };

    let n_bytes = match env.convert_byte_array(&nonce) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };
    if n_bytes.len() != 12 {
        let _ = env.throw_new("java/lang/IllegalArgumentException", "Nonce must be 12 bytes");
        return std::ptr::null_mut();
    }

    let nonce = Nonce::from_slice(&n_bytes);

    let cipher = match Aes256Gcm::new_from_slice(&k_bytes) {
        Ok(c) => c,
        Err(e) => {
            let _ = env.throw_new("java/lang/RuntimeException", format!("Cipher init failed: {}", e));
            return std::ptr::null_mut();
        }
    };

    let plaintext = match cipher.decrypt(nonce, ct.as_ref()) {
        Ok(pt) => pt,
        Err(e) => {
            let _ = env.throw_new("java/lang/RuntimeException", format!("Attachment decryption failed: {}", e));
            return std::ptr::null_mut();
        }
    };

    match env.byte_array_from_slice(&plaintext) {
        Ok(a) => a.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

#[no_mangle]
pub extern "system" fn Java_com_qumail_CryptoBridgeNative_nativeDirectoryProof(
    mut env: JNIEnv,
    _class: JClass,
    secret_cert: JByteArray,
    message: JByteArray,
) -> jobjectArray {
    let sec_bytes = match env.convert_byte_array(&secret_cert) {
        Ok(b) => Zeroizing::new(b),
        Err(_) => return std::ptr::null_mut(),
    };

    let cert = match Cert::from_bytes(&sec_bytes) {
        Ok(c) => c,
        Err(e) => {
            let _ = env.throw_new("java/lang/IllegalArgumentException", format!("Bad cert: {}", e));
            return std::ptr::null_mut();
        }
    };

    let msg_bytes = match env.convert_byte_array(&message) {
        Ok(b) => b,
        Err(_) => return std::ptr::null_mut(),
    };

    let (verifying, sig) = match helper_directory_pop(&cert, &msg_bytes) {
        Ok(res) => res,
        Err(e) => {
            let _ = env.throw_new("java/lang/RuntimeException", format!("Directory proof failed: {}", e));
            return std::ptr::null_mut();
        }
    };

    let byte_array_class = match env.find_class("[B") {
        Ok(c) => c,
        Err(_) => return std::ptr::null_mut(),
    };

    let result_array = match env.new_object_array(2, &byte_array_class, &JObject::null()) {
        Ok(a) => a,
        Err(_) => return std::ptr::null_mut(),
    };

    let v_jbytes = match env.byte_array_from_slice(&verifying) {
        Ok(a) => a,
        Err(_) => return std::ptr::null_mut(),
    };
    let s_jbytes = match env.byte_array_from_slice(&sig) {
        Ok(a) => a,
        Err(_) => return std::ptr::null_mut(),
    };

    let _ = env.set_object_array_element(&result_array, 0, &v_jbytes);
    let _ = env.set_object_array_element(&result_array, 1, &s_jbytes);

    result_array.into_raw()
}

#[no_mangle]
pub extern "system" fn Java_com_qumail_CryptoBridgeNative_nativeSetVaultSecretCert(
    mut env: JNIEnv,
    _class: JClass,
    secret_cert: JByteArray,
) -> jboolean {
    let sec_bytes = match env.convert_byte_array(&secret_cert) {
        Ok(b) => Zeroizing::new(b),
        Err(_) => return JNI_FALSE,
    };

    let cert = match Cert::from_bytes(&sec_bytes) {
        Ok(c) => c,
        Err(_) => return JNI_FALSE,
    };

    let pub_bytes = match public(&cert) {
        Ok(b) => b,
        Err(_) => return JNI_FALSE,
    };

    let mut vault = VAULT.lock().unwrap();
    vault.secret_cert = Some(sec_bytes);
    vault.public_cert = Some(pub_bytes);
    JNI_TRUE
}

#[no_mangle]
pub extern "system" fn Java_com_qumail_CryptoBridgeNative_nativeLockVault(
    _env: JNIEnv,
    _class: JClass,
) {
    let mut vault = VAULT.lock().unwrap();
    vault.secret_cert = None;
    vault.public_cert = None;
}

#[no_mangle]
pub extern "system" fn Java_com_qumail_CryptoBridgeNative_nativeGetVaultPublicCert(
    env: JNIEnv,
    _class: JClass,
) -> jbyteArray {
    let vault = VAULT.lock().unwrap();
    if let Some(ref pub_bytes) = vault.public_cert {
        match env.byte_array_from_slice(pub_bytes) {
            Ok(a) => a.into_raw(),
            Err(_) => std::ptr::null_mut(),
        }
    } else {
        std::ptr::null_mut()
    }
}

#[no_mangle]
pub extern "system" fn Java_com_qumail_CryptoBridgeNative_nativeIsVaultUnlocked(
    _env: JNIEnv,
    _class: JClass,
) -> jboolean {
    let vault = VAULT.lock().unwrap();
    if vault.secret_cert.is_some() {
        JNI_TRUE
    } else {
        JNI_FALSE
    }
}
