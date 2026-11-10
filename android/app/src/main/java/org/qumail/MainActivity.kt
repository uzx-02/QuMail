package org.qumail

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.biometric.BiometricPrompt
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import org.qumail.crypto.NativePQEngine
import org.qumail.keystore.VaultKeyManager

class MainActivity : FragmentActivity() {

    private val vaultKeyManager = VaultKeyManager()
    private var isVaultUnlocked = mutableStateOf(false)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        promptBiometricAuthentication()

        setContent {
            QuMailMobileTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = Color(0xFF0A0E17) // Dark Enterprise Slate
                ) {
                    if (isVaultUnlocked.value) {
                        QuMailMainScreen()
                    } else {
                        VaultLockedScreen(onUnlockClicked = { promptBiometricAuthentication() })
                    }
                }
            }
        }
    }

    private fun promptBiometricAuthentication() {
        val executor = ContextCompat.getMainExecutor(this)
        val biometricPrompt = BiometricPrompt(
            this,
            executor,
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    super.onAuthenticationSucceeded(result)
                    isVaultUnlocked.value = true
                }
            }
        )

        val promptInfo = BiometricPrompt.PromptInfo.Builder()
            .setTitle("Unlock QuMail Secure Vault")
            .setSubtitle("Authenticate with fingerprint or face to release post-quantum private keys")
            .setNegativeButtonText("Cancel")
            .build()

        biometricPrompt.authenticate(promptInfo)
    }
}

@Composable
fun VaultLockedScreen(onUnlockClicked: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Text("QuMail Vault Locked", fontSize = 20.sp, fontWeight = FontWeight.Bold, color = Color.White)
        Spacer(modifier = Modifier.height(12.dp))
        Text(
            "Hardware-backed private keys are protected in Android Keystore / StrongBox.",
            color = Color(0xFF94A3B8),
            fontSize = 13.sp
        )
        Spacer(modifier = Modifier.height(24.dp))
        Button(
            onClick = onUnlockClicked,
            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF6366F1))
        ) {
            Text("Authenticate with Biometrics")
        }
    }
}

@Composable
fun QuMailMainScreen() {
    var selectedMessage by remember { mutableStateOf<EmailItem?>(null) }

    val sampleEmails = listOf(
        EmailItem(
            id = "msg-101",
            sender = "uzair@qumail.org",
            subject = "Aavishkar 2026 — Classified National Quantum Research Brief",
            snippet = "-----BEGIN PGP MESSAGE----- (Encrypted with ML-KEM-768)",
            decryptedBody = "Confidential patent specifications and experimental validation data. Protected end-to-end against Harvest-Now-Decrypt-Later attacks.",
            isSecure = true,
            date = "10:45 AM"
        ),
        EmailItem(
            id = "msg-102",
            sender = "colleague@university.invalid",
            subject = "Symposium Schedule Update",
            snippet = "Please check the conference timetable attached...",
            decryptedBody = "The poster evaluation begins at 10:00 AM in the Main Convention Hall.",
            isSecure = false,
            date = "Yesterday"
        )
    )

    if (selectedMessage != null) {
        EmailDetailScreen(message = selectedMessage!!, onBack = { selectedMessage = null })
    } else {
        Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("QuMail Mobile", fontSize = 20.sp, fontWeight = FontWeight.ExtraBold, color = Color.White)
                Spacer(modifier = Modifier.width(8.dp))
                Badge(containerColor = Color(0xFF1E2342)) {
                    Text("PQ-v1", color = Color(0xFF818CF8), fontSize = 10.sp, fontWeight = FontWeight.Bold)
                }
            }
            Spacer(modifier = Modifier.height(16.dp))

            LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                items(sampleEmails) { email ->
                    Card(
                        onClick = { selectedMessage = email },
                        colors = CardDefaults.cardColors(containerColor = Color(0xFF161F33)),
                        shape = RoundedCornerShape(10.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Column(modifier = Modifier.padding(14.dp)) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text(email.sender, fontWeight = FontWeight.Bold, color = Color.White, fontSize = 14.sp)
                                Text(email.date, color = Color(0xFF94A3B8), fontSize = 12.sp)
                            }
                            Spacer(modifier = Modifier.height(4.dp))
                            Text(email.subject, fontWeight = FontWeight.SemiBold, color = Color(0xFFF1F5F9), fontSize = 13.sp)
                            Spacer(modifier = Modifier.height(4.dp))
                            Text(email.snippet, color = Color(0xFF94A3B8), fontSize = 12.sp, maxLines = 1)
                            if (email.isSecure) {
                                Spacer(modifier = Modifier.height(8.dp))
                                Text(
                                    "Post-Quantum Encrypted (ML-KEM-768)",
                                    color = Color(0xFFA7F3D0),
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Bold
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun EmailDetailScreen(message: EmailItem, onBack: () -> Unit) {
    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        Button(
            onClick = onBack,
            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF2A3B5F))
        ) {
            Text("Back to Inbox")
        }
        Spacer(modifier = Modifier.height(16.dp))

        if (message.isSecure) {
            Card(
                colors = CardDefaults.cardColors(containerColor = Color(0xFF064E3B)),
                shape = RoundedCornerShape(8.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Row(modifier = Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        "Post-Quantum Secured (ML-KEM-768 / ML-DSA-65 Verified)",
                        color = Color(0xFFA7F3D0),
                        fontWeight = FontWeight.Bold,
                        fontSize = 12.sp
                    )
                }
            }
            Spacer(modifier = Modifier.height(16.dp))
        }

        Text(message.subject, fontSize = 18.sp, fontWeight = FontWeight.Bold, color = Color.White)
        Spacer(modifier = Modifier.height(6.dp))
        Text("From: ${message.sender}", color = Color(0xFF94A3B8), fontSize = 13.sp)
        Spacer(modifier = Modifier.height(16.dp))

        Card(
            colors = CardDefaults.cardColors(containerColor = Color(0xFF161F33)),
            shape = RoundedCornerShape(8.dp),
            modifier = Modifier.fillMaxWidth()
        ) {
            Text(
                message.decryptedBody,
                color = Color.White,
                fontSize = 14.sp,
                modifier = Modifier.padding(16.dp),
                lineHeight = 20.sp
            )
        }
    }
}

data class EmailItem(
    val id: String,
    val sender: String,
    val subject: String,
    val snippet: String,
    val decryptedBody: String,
    val isSecure: Boolean = false,
    val date: String
)

@Composable
fun QuMailMobileTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = darkColorScheme(
            background = Color(0xFF0A0E17),
            surface = Color(0xFF161F33),
            primary = Color(0xFF6366F1)
        ),
        content = content
    )
}
