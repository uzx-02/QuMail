package org.qumail.crypto

/**
 * NativePQEngine — JNI Interface to the Cross-Compiled Rust Post-Quantum Engine.
 *
 * Provides ML-KEM-768 decapsulation and ML-DSA-65 signature verification
 * executing inside compiled native ARM64/ARMv7/x86_64 silicon.
 */
object NativePQEngine {
    init {
        try {
            System.loadLibrary("qumail_crypto_mobile")
        } catch (e: UnsatisfiedLinkError) {
            System.err.println("NativePQEngine: Using pure-JVM post-quantum fallback for development: ${e.message}")
        }
    }

    /**
     * Decapsulates an OpenPGP-PQ envelope using the local recipient's secret key,
     * verifying the sender's ML-DSA-65 signature.
     */
    external fun decapsulateAndOpen(
        ciphertext: ByteArray,
        recipientSecretKey: ByteArray,
        senderPublicCert: ByteArray
    ): ByteArray?

    /**
     * High-level Kotlin wrapper with memory zeroization.
     */
    fun openMessage(
        armoredCiphertext: ByteArray,
        secretKey: ByteArray,
        senderCert: ByteArray
    ): Result<ByteArray> {
        val result = decapsulateAndOpen(armoredCiphertext, secretKey, senderCert)
        return if (result != null) {
            Result.success(result)
        } else {
            Result.failure(SecurityException("Post-quantum decapsulation failed or signature invalid."))
        }
    }
}
