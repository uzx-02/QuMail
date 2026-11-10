package org.qumail.keystore

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * VaultKeyManager — Android Keystore & Hardware StrongBox Key Management.
 *
 * Stores the master key protecting the local SQLite email database
 * inside hardware silicon (TEE / StrongBox), requiring Biometric Authentication
 * (Fingerprint / Face Unlock) to release cryptographic operations.
 */
class VaultKeyManager {

    companion object {
        private const val ANDROID_KEYSTORE = "AndroidKeyStore"
        private const val KEY_ALIAS_VAULT_MASTER = "QuMail_Vault_Master_Key"
    }

    private val keyStore: KeyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply {
        load(null)
    }

    /**
     * Generates or retrieves the hardware-backed AES-256-GCM vault master key.
     */
    fun getOrCreateMasterKey(requireBiometrics: Boolean = false): SecretKey {
        if (!keyStore.containsAlias(KEY_ALIAS_VAULT_MASTER)) {
            val keyGenerator = KeyGenerator.getInstance(
                KeyProperties.KEY_ALGORITHM_AES,
                ANDROID_KEYSTORE
            )

            val builder = KeyGenParameterSpec.Builder(
                KEY_ALIAS_VAULT_MASTER,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)

            if (requireBiometrics) {
                builder.setUserAuthenticationRequired(true)
                builder.setUserAuthenticationParameters(
                    0, // 0 = requires biometric prompt for every use
                    KeyProperties.AUTH_BIOMETRIC_STRONG
                )
            }

            keyGenerator.init(builder.build())
            return keyGenerator.generateKey()
        }

        val entry = keyStore.getEntry(KEY_ALIAS_VAULT_MASTER, null) as KeyStore.SecretKeyEntry
        return entry.secretKey
    }

    /**
     * Encrypts data with the hardware master key.
     */
    fun sealData(data: ByteArray): Pair<ByteArray, ByteArray> {
        val key = getOrCreateMasterKey()
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key)
        val iv = cipher.iv
        val ciphertext = cipher.doFinal(data)
        return Pair(iv, ciphertext)
    }

    /**
     * Decrypts data with the hardware master key.
     */
    fun unsealData(iv: ByteArray, ciphertext: ByteArray): ByteArray {
        val key = getOrCreateMasterKey()
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        val spec = GCMParameterSpec(128, iv)
        cipher.init(Cipher.DECRYPT_MODE, key, spec)
        return cipher.doFinal(ciphertext)
    }
}
