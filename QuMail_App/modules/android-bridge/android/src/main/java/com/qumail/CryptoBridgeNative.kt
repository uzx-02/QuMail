package com.qumail

object CryptoBridgeNative {
    init {
        try {
            System.loadLibrary("qumail_crypto")
        } catch (e: UnsatisfiedLinkError) {
            android.util.Log.e("CryptoBridgeNative", "Failed to load libqumail_crypto.so", e)
        }
    }

    external fun nativeGenerateIdentity(email: String): Array<ByteArray>
    external fun nativeSealMessage(senderSecret: ByteArray, recipientPublics: Array<ByteArray>, plaintext: ByteArray): ByteArray
    external fun nativeOpenMessage(recipientSecret: ByteArray, senderPublic: ByteArray, envelope: ByteArray): ByteArray
    external fun nativeEncryptAttachment(key: ByteArray, plaintext: ByteArray): Array<ByteArray>
    external fun nativeDecryptAttachment(key: ByteArray, ciphertext: ByteArray, nonce: ByteArray): ByteArray
    external fun nativeDirectoryProof(secretCert: ByteArray, message: ByteArray): Array<ByteArray>
    external fun nativeSetVaultSecretCert(secretCert: ByteArray): Boolean
    external fun nativeLockVault()
    external fun nativeGetVaultPublicCert(): ByteArray?
    external fun nativeIsVaultUnlocked(): Boolean
}
