package com.qumail

import android.util.Base64
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.facebook.react.bridge.ReadableArray

class CryptoBridgeModule(reactContext: ReactApplicationContext) : ReactContextBaseJavaModule(reactContext) {

    override fun getName(): String = "CryptoBridgeModule"

    @ReactMethod
    fun generateIdentity(email: String, promise: Promise) {
        try {
            val result = CryptoBridgeNative.nativeGenerateIdentity(email)
            val pubBase64 = Base64.encodeToString(result[0], Base64.NO_WRAP)
            val secBase64 = Base64.encodeToString(result[1], Base64.NO_WRAP)

            val map = Arguments.createMap()
            map.putString("publicCert", pubBase64)
            map.putString("secretCert", secBase64)
            promise.resolve(map)
        } catch (e: Exception) {
            promise.reject("CRYPTO_GEN_ERROR", e.message, e)
        }
    }

    @ReactMethod
    fun sealMessage(senderSecretBase64: String, recipientPublicsBase64: ReadableArray, plaintextBase64: String, promise: Promise) {
        try {
            val senderSecret = Base64.decode(senderSecretBase64, Base64.DEFAULT)
            val count = recipientPublicsBase64.size()
            val recipients = Array(count) { i ->
                Base64.decode(recipientPublicsBase64.getString(i), Base64.DEFAULT)
            }
            val plaintext = Base64.decode(plaintextBase64, Base64.DEFAULT)

            val sealed = CryptoBridgeNative.nativeSealMessage(senderSecret, recipients, plaintext)
            val sealedBase64 = Base64.encodeToString(sealed, Base64.NO_WRAP)
            promise.resolve(sealedBase64)
        } catch (e: Exception) {
            promise.reject("CRYPTO_SEAL_ERROR", e.message, e)
        }
    }

    @ReactMethod
    fun openMessage(recipientSecretBase64: String, senderPublicBase64: String, envelopeBase64: String, promise: Promise) {
        try {
            val recipientSecret = Base64.decode(recipientSecretBase64, Base64.DEFAULT)
            val senderPublic = Base64.decode(senderPublicBase64, Base64.DEFAULT)
            val envelope = Base64.decode(envelopeBase64, Base64.DEFAULT)

            val opened = CryptoBridgeNative.nativeOpenMessage(recipientSecret, senderPublic, envelope)
            val openedBase64 = Base64.encodeToString(opened, Base64.NO_WRAP)
            promise.resolve(openedBase64)
        } catch (e: Exception) {
            promise.reject("CRYPTO_OPEN_ERROR", e.message, e)
        }
    }

    @ReactMethod
    fun encryptAttachment(keyBase64: String, plaintextBase64: String, promise: Promise) {
        try {
            val key = Base64.decode(keyBase64, Base64.DEFAULT)
            val plaintext = Base64.decode(plaintextBase64, Base64.DEFAULT)

            val result = CryptoBridgeNative.nativeEncryptAttachment(key, plaintext)
            val map = Arguments.createMap()
            map.putString("ciphertext", Base64.encodeToString(result[0], Base64.NO_WRAP))
            map.putString("nonce", Base64.encodeToString(result[1], Base64.NO_WRAP))
            promise.resolve(map)
        } catch (e: Exception) {
            promise.reject("CRYPTO_ATTACH_ENC_ERROR", e.message, e)
        }
    }

    @ReactMethod
    fun decryptAttachment(keyBase64: String, ciphertextBase64: String, nonceBase64: String, promise: Promise) {
        try {
            val key = Base64.decode(keyBase64, Base64.DEFAULT)
            val ciphertext = Base64.decode(ciphertextBase64, Base64.DEFAULT)
            val nonce = Base64.decode(nonceBase64, Base64.DEFAULT)

            val decrypted = CryptoBridgeNative.nativeDecryptAttachment(key, ciphertext, nonce)
            promise.resolve(Base64.encodeToString(decrypted, Base64.NO_WRAP))
        } catch (e: Exception) {
            promise.reject("CRYPTO_ATTACH_DEC_ERROR", e.message, e)
        }
    }

    @ReactMethod
    fun directoryProof(secretCertBase64: String, messageBase64: String, promise: Promise) {
        try {
            val secretCert = Base64.decode(secretCertBase64, Base64.DEFAULT)
            val message = Base64.decode(messageBase64, Base64.DEFAULT)

            val result = CryptoBridgeNative.nativeDirectoryProof(secretCert, message)
            val map = Arguments.createMap()
            map.putString("verifyingKey", Base64.encodeToString(result[0], Base64.NO_WRAP))
            map.putString("signature", Base64.encodeToString(result[1], Base64.NO_WRAP))
            promise.resolve(map)
        } catch (e: Exception) {
            promise.reject("CRYPTO_PROOF_ERROR", e.message, e)
        }
    }

    @ReactMethod
    fun setVaultSecretCert(secretCertBase64: String, promise: Promise) {
        try {
            val secretCert = Base64.decode(secretCertBase64, Base64.DEFAULT)
            val ok = CryptoBridgeNative.nativeSetVaultSecretCert(secretCert)
            promise.resolve(ok)
        } catch (e: Exception) {
            promise.reject("CRYPTO_VAULT_ERROR", e.message, e)
        }
    }

    @ReactMethod
    fun lockVault(promise: Promise) {
        try {
            CryptoBridgeNative.nativeLockVault()
            promise.resolve(null)
        } catch (e: Exception) {
            promise.reject("CRYPTO_VAULT_ERROR", e.message, e)
        }
    }

    @ReactMethod
    fun getVaultPublicCert(promise: Promise) {
        try {
            val pub = CryptoBridgeNative.nativeGetVaultPublicCert()
            if (pub != null) {
                promise.resolve(Base64.encodeToString(pub, Base64.NO_WRAP))
            } else {
                promise.resolve(null)
            }
        } catch (e: Exception) {
            promise.reject("CRYPTO_VAULT_ERROR", e.message, e)
        }
    }

    @ReactMethod
    fun isVaultUnlocked(promise: Promise) {
        try {
            promise.resolve(CryptoBridgeNative.nativeIsVaultUnlocked())
        } catch (e: Exception) {
            promise.reject("CRYPTO_VAULT_ERROR", e.message, e)
        }
    }
}
