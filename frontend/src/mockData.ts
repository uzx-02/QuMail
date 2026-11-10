import { EmailMessage, HSMStatus, AccountSession } from './types';

export const INITIAL_ACCOUNT: AccountSession = {
  email: '',
  provider: 'QuMail Sovereign Post-Quantum Network',
  pqcAlgorithm: 'NIST FIPS 203 (ML-KEM-768) + NIST FIPS 204 (ML-DSA-65)',
  pqcIdentity: '',
  isUnlocked: false,
};

export const INITIAL_HSM: HSMStatus = {
  isHardwareActive: false,
  activePort: '',
  mode: 'AUTO',
  rateBps: 0,
  continuousPassed: true,
};

export const MOCK_MESSAGES: EmailMessage[] = [
  {
    id: 'msg-001',
    sender: 'Aavishkar Convention Directorate',
    senderEmail: 'directorate@aavishkar-convention.res.in',
    recipients: ['uzair@aavishkar.res.in'],
    subject: 'Official Invitation: Aavishkar Research Convention 2026 Live Defense',
    snippet: 'Congratulations! Your post-quantum secure messaging research (QuMail 1.0) has been selected for the final live defense and demonstration...',
    body: `Dear Researcher,

Congratulations! Your research initiative — QuMail 1.0: Post-Quantum Cryptographic Corporate Mail Client with Physical True Random Number Generation — has been officially selected for the final live round of the Aavishkar Research Convention 2026.

Session Details:
• Stage: Main Engineering & National Security Auditorium
• Format: 3-Minute Poster Presentation + 2-Minute Live Engineering Q&A
• Strategic Theme: Viksit Bharat 2047 — Quantum Cybersecurity & Sovereign Cryptographic Infrastructure

Our technical evaluation panel noted the significant real-world readiness of your implementation:
1. Native NIST FIPS 203 (ML-KEM-768) key exchange coupled with ML-DSA-65 composite signatures.
2. Direct USB microcontroller Hardware TRNG entropy integration bypassing software RNG predictability.
3. Durable zero-plaintext release architecture ensuring cryptographic isolation even during network disruption.

Please have your hardware circuit and live demonstration environment prepared on your workstation for the judges' panel.

Sincerely,
Dr. V. Ramanathan
Chief Convenor, Aavishkar Research Convention 2026`,
    date: '10:45 AM',
    timestamp: Date.now() - 3600000 * 2,
    seen: false,
    starred: true,
    folder: 'inbox',
    category: 'primary',
    hasAttachments: true,
    attachments: [
      { name: 'Aavishkar_Presentation_Schedule.pdf', size: 1024 * 420, mediaType: 'application/pdf' },
      { name: 'Defense_Evaluation_Rubric.pdf', size: 1024 * 180, mediaType: 'application/pdf' }
    ],
    indicator: {
      badgeLevel: 'SECURE',
      headline: 'Post-Quantum Verified & Sealed',
      description: 'Sealed with NIST FIPS 203 (ML-KEM-768) and signed with ML-DSA-65. Verified against Aavishkar Central Public Key Transparency Directory.',
      actionAdvice: 'Message authentic. Corporate identity certified.',
    },
  },
  {
    id: 'msg-002',
    sender: 'National Quantum Mission (NQM)',
    senderEmail: 'initiatives@nqm.gov.in',
    recipients: ['uzair@aavishkar.res.in'],
    subject: 'Strategic Alignment: Viksit Bharat 2047 & Quantum Security Framework',
    snippet: 'Review of QuMail indigenous architecture in addressing the Harvest Now, Decrypt Later (HNDL) threat vector across strategic communications...',
    body: `To the Lead Architect, QuMail Project,

The National Quantum Mission (NQM) technical division has reviewed your technical specification and audit report regarding indigenous post-quantum email defense.

Key Points of Alignment:
• Threat Mitigation: Immediate countermeasure against 'Harvest Now, Decrypt Later' adversaries intercepting corporate and defense communications prior to CRQC (Cryptanalytically Relevant Quantum Computers).
• Hardware Root of Trust: Commendation on integrating USB serial hardware entropy collectors (Avalanche photodiode & STM32/ESP32 physical thermal noise), eliminating dependence on closed-source OS pseudorandom generators.
• Self-Healing Outbox: Implementation of transactional SQLite durable queuing guarantees that transient network dropouts never release unencrypted plaintext onto the wire.

Your work stands as a strong example of indigenous deep-tech innovation aligned with India's Viksit Bharat 2047 quantum readiness mandate.

Best regards,
Secretariat, National Quantum Mission
Department of Science & Technology, Government of India`,
    date: 'Yesterday',
    timestamp: Date.now() - 86400000,
    seen: true,
    starred: true,
    folder: 'inbox',
    category: 'primary',
    hasAttachments: false,
    indicator: {
      badgeLevel: 'SECURE',
      headline: 'Post-Quantum Verified & Sealed',
      description: 'End-to-end encrypted with hybrid ML-KEM/X25519. Key inclusion confirmed in public Merkle transparency log.',
      actionAdvice: 'Corporate identity certified.',
    },
  },
  {
    id: 'msg-003',
    sender: 'QuMail Automated Diagnostics',
    senderEmail: 'daemon@qumail-local.internal',
    recipients: ['uzair@aavishkar.res.in'],
    subject: 'Hardware TRNG Connected: COM3 Health Verification Passed (NIST SP 800-90B)',
    snippet: 'Automatic hardware detection identified physical USB entropy source at 115,200 baud. Repetition Count & Adaptive Proportion tests passed with zero drops...',
    body: `QuMail Hardware Entropy Subsystem Report
Timestamp: 2026-11-10T20:15:00+05:30
Device: Physical Microcontroller TRNG (Hardware Source)
Port: COM3 (Baud 115200)

Continuous Health Test Results:
• Repetition Count Test: PASSED (cutoff threshold 32, max observed 4)
• Adaptive Proportion Test: PASSED (cutoff threshold 312/1024, max observed 168)
• Min-Entropy Assessment: 7.84 bits per byte conditioned
• Fallback Condition: Inactive (Hardware TRNG primary)

The local post-quantum key generation and ephemeral session seed pools are now operating with physical quantum-grade randomness.`,
    date: 'Nov 09',
    timestamp: Date.now() - 86400000 * 2,
    seen: true,
    starred: false,
    folder: 'inbox',
    category: 'updates',
    hasAttachments: false,
    indicator: {
      badgeLevel: 'SECURE',
      headline: 'Internal Diagnostic Sealed',
      description: 'Authenticated local subsystem telemetry. Zero remote leaks.',
      actionAdvice: 'Informational system record.',
    },
  },
  {
    id: 'msg-004',
    sender: 'External Legal Counsel',
    senderEmail: 'notices@global-legal-partners.com',
    recipients: ['uzair@aavishkar.res.in'],
    subject: 'External Contractual Review — Non-Disclosure & Intellectual Property',
    snippet: 'Please find attached the standard mutual NDA for research collaboration. Note that sender public certificate is self-asserted...',
    body: `Greetings,

Attached is our mutual non-disclosure agreement for the upcoming research commercialization round.

Please note that our firm operates on a conventional corporate mail server without post-quantum identity enrollment. When replying with sensitive research artifacts, please consider issuing an ephemeral Zero-Knowledge Web Link or requesting directory key enrollment.

Cordially,
S. Mehta, Attorney at Law`,
    date: 'Nov 08',
    timestamp: Date.now() - 86400000 * 3,
    seen: true,
    starred: false,
    folder: 'inbox',
    category: 'primary',
    hasAttachments: true,
    attachments: [
      { name: 'Mutual_NDA_Draft_2026.pdf', size: 1024 * 310, mediaType: 'application/pdf' }
    ],
    indicator: {
      badgeLevel: 'CAUTION',
      headline: 'Identity Unverified / Standard TLS',
      description: 'This message was delivered over standard mail transport. Sender does not possess a verified Post-Quantum directory certificate.',
      actionAdvice: 'Verify identity out-of-band before sharing classified research.',
    },
  },
  {
    id: 'msg-005',
    sender: 'Uzair Shaikh',
    senderEmail: 'uzair@aavishkar.res.in',
    recipients: ['evaluator@aavishkar.res.in'],
    subject: 'QuMail 1.0 Engineering Executive Summary & Technical Architecture',
    snippet: 'Prepared executive summary detailing WP1 through WP5 deliverables, native cryptographic engine benchmarks, and live demonstration checklist...',
    body: `Respected Evaluator,

Please find the executive summary of the QuMail 1.0 post-quantum secure messaging suite, covering our five core engineering work packages:
1. Gmail-Grade Desktop UI/UX with zero cryptographic friction.
2. Physical USB Microcontroller TRNG and ETSI GS QKD 014 integration.
3. Turnkey Windows installer and single-file portable packages.
4. Zero-Knowledge ephemeral web link delivery for non-PQC external correspondents.
5. Cross-platform native Rust cryptographic engine bridges.

We look forward to demonstrating the live hardware link during our defense.

Warm regards,
Uzair Shaikh`,
    date: 'Nov 07',
    timestamp: Date.now() - 86400000 * 4,
    seen: true,
    starred: false,
    folder: 'sent',
    category: 'primary',
    hasAttachments: true,
    attachments: [
      { name: 'QuMail_Architecture_Brief.pdf', size: 1024 * 512, mediaType: 'application/pdf' }
    ],
    indicator: {
      badgeLevel: 'SECURE',
      headline: 'Signed with ML-DSA-65',
      description: 'Your local post-quantum key was used to sign this outbound transmission.',
      actionAdvice: 'Archived in Sent Mail.',
    },
  }
];
