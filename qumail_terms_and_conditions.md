QuMail – Terms & Conditions
===========================

**Effective Date:** 14/11/2026**Last Updated:** 14/11/2026

1\. Introduction
----------------

Welcome to QuMail.

QuMail is a Windows desktop email client developed and maintained by the QuMail Project Team ("Project Team", "we", "us", or "our").

These Terms & Conditions ("Terms") govern your access to and use of the QuMail software, its associated cryptographic functionality, encrypted WebLink services, and supporting online infrastructure.

QuMail is currently distributed as a private prototype for limited testing and evaluation. It is not represented as a fully established commercial email service or a production-grade enterprise communication platform.

By installing, accessing, or using QuMail, you acknowledge that you have read and understood these Terms.

If you do not agree with these Terms, you must discontinue using the software.

2\. Definitions
---------------

For the purposes of these Terms:

*   **QuMail:** The Windows desktop email application and its associated components.
    
*   **Project Team:** The group responsible for developing and maintaining the QuMail prototype.
    
*   **User:** An individual authorized to access or test QuMail.
    
*   **PQ Mail:** QuMail's post-quantum encrypted email functionality.
    
*   **WebLink:** An encrypted message access link generated for recipients who do not have QuMail installed.
    
*   **Cloud Directory:** The cloud infrastructure supporting public-key discovery, account enrollment, and encrypted WebLink storage.
    
*   **Third-Party Services:** External services used by QuMail, including email providers and cloud infrastructure providers.
    

3\. Nature and Status of the Software
-------------------------------------

QuMail is an experimental software project currently made available for private prototype testing and evaluation.

The software provides additional cryptographic functionality over existing email infrastructure.

Its principal communication mechanisms include:

### 3.1 Post-Quantum Encrypted Email

QuMail enables enrolled users to exchange supported encrypted messages using:

*   ML-KEM-768 for post-quantum key encapsulation.
    
*   ML-DSA-65 for post-quantum digital signatures.
    
*   OpenPGP-based MIME message formatting.
    
*   Locally managed cryptographic identities and private keys.
    

Both sender and recipient must have compatible enrolled QuMail identities to use this communication mode.

### 3.2 Encrypted WebLinks

QuMail provides encrypted WebLinks for communicating with recipients who do not have QuMail installed.

This functionality uses:

*   AES-256-GCM message and attachment encryption.
    
*   Ed25519 signature binding.
    
*   Cloud-hosted encrypted payload storage.
    
*   Browser-based client-side decryption.
    
*   URL fragment-based decryption key delivery.
    

Optional controls include OTP verification and burn-after-read restrictions.

### 3.3 Additional Functionality

Other functionality may include:

*   Google OAuth authentication.
    
*   Custom IMAP/SMTP mailbox connections.
    
*   Email synchronization.
    
*   Offline Hindi and Marathi translation.
    
*   Local encrypted credential storage.
    
*   Security PIN and automatic vault locking.
    
*   Contact trust evaluation and key-change detection.
    

Available functionality may change as the prototype develops.

4\. Prototype and Testing Conditions
------------------------------------

You acknowledge and agree that:

1.  QuMail is currently a prototype and may contain defects, incomplete functionality, compatibility issues, or unexpected behavior.
    
2.  Features may be modified, suspended, restricted, or removed without a guarantee of continued availability.
    
3.  External integrations may become unavailable due to changes in third-party services.
    
4.  The Project Team does not guarantee uninterrupted operation, message delivery, synchronization, or permanent storage.
    
5.  Updates may introduce changes to application behavior or data handling.
    

You should not rely on QuMail as your sole means of communication or as the only repository of important information.

During prototype testing, users are strongly advised to use test accounts and non-critical communications.

Do not use the prototype as the sole communication channel for emergencies, safety-critical operations, financial transactions, legal notices, or other communications requiring guaranteed delivery or independently assured confidentiality.

5\. Eligibility and Account Responsibility
------------------------------------------

QuMail is intended for a general audience.

You are responsible for ensuring that your use of QuMail is lawful and that you have the necessary authority to connect the email accounts you use.

You must:

*   Provide accurate account information.
    
*   Maintain the confidentiality of your email credentials.
    
*   Protect your Windows user account.
    
*   Protect your QuMail security PIN.
    
*   Safeguard your cryptographic recovery information, where applicable.
    
*   Protect complete WebLink URLs and associated access credentials.
    

If you are under 18, you should use QuMail with the knowledge and involvement of a parent or legal guardian.

6\. Acceptable Use
------------------

You agree not to use QuMail to:

*   Facilitate fraud, phishing, harassment, threats, or unlawful activities.
    
*   Distribute malware or malicious attachments.
    
*   Gain unauthorized access to another person's account, identity, or communications.
    
*   Attack, disrupt, or interfere with QuMail infrastructure.
    
*   Exploit vulnerabilities in the Cloud Directory or associated services.
    
*   Abuse account enrollment, public-key discovery, OTP verification, or WebLink storage.
    
*   Circumvent security controls for unauthorized purposes.
    
*   Violate applicable Indian laws or other laws applicable to your use.
    

You remain responsible for all content you create, transmit, or share through QuMail.

7\. Cryptographic Security and Limitations
------------------------------------------

QuMail incorporates cryptographic mechanisms intended to improve the confidentiality and integrity of electronic communications.

However, no cryptographic system or software application can guarantee absolute security.

### 7.1 Post-Quantum Cryptography

QuMail implements ML-KEM-768 and ML-DSA-65 in supported communication workflows.

The use of standardized algorithms does not guarantee that the complete application, implementation, operating environment, or communication process is free from vulnerabilities.

### 7.2 Local Key Protection

Private identity keys and certain credentials are maintained locally using Windows DPAPI-protected vault mechanisms.

The security of this storage depends on the integrity of the operating system, Windows user account, device, and application environment.

Malware, compromised operating systems, unauthorized physical access, or other endpoint attacks may expose information accessible to the application.

### 7.3 Contact Trust and Verification

QuMail uses Trust-On-First-Use (TOFU) contact pinning and security indicators to identify certain changes in correspondent keys and signatures.

Users should carefully review unexpected key-change notifications and signature-verification failures.

### 7.4 Encrypted WebLinks

WebLink messages are encrypted using AES-256-GCM before their encrypted payloads are uploaded to cloud infrastructure.

The decryption key is embedded in the URL fragment and is designed not to be included in ordinary HTTP requests to the storage server.

However, anyone who obtains the complete WebLink may potentially gain access to its contents, depending on the applicable access controls.

Users must treat complete WebLinks as confidential credentials.

### 7.5 No Independent Security Certification

The existence of cryptographic algorithms, operating-system protections, automated tests, or implementation-level security checks does not constitute an independent security certification, penetration test, or guarantee against compromise.

8\. Email Providers and Third-Party Services
--------------------------------------------

QuMail connects to existing email infrastructure using supported authentication and communication mechanisms, including Google OAuth 2.0, IMAP, and SMTP.

Your use of these providers remains subject to their respective terms and privacy policies.

The Project Team does not own or control your underlying email account.

You authorize the application to perform the mailbox operations associated with the permissions and credentials you provide.

QuMail also depends on external cloud infrastructure for certain functions, including Cloud Directory operations and encrypted WebLink storage.

The availability and operation of those services are outside the Project Team's complete control.

9\. User Content and Data Responsibility
----------------------------------------

You retain whatever rights you hold in your messages, attachments, and other content.

You are responsible for:

*   Ensuring you have permission to transmit your content.
    
*   Maintaining appropriate backups.
    
*   Verifying recipients where necessary.
    
*   Protecting your cryptographic keys and access credentials.
    
*   Complying with applicable confidentiality and data-protection requirements.
    

QuMail does not guarantee recovery of lost messages, credentials, private keys, or encrypted content.

The processing of information through QuMail is described in the separate Privacy Policy.

10\. Intellectual Property and Third-Party Licenses
---------------------------------------------------

QuMail includes original project components and third-party libraries and technologies.

The ownership and licensing of individual components remain subject to their applicable intellectual property rights and licenses.

Nothing in these Terms grants you ownership of proprietary project components or rights beyond those expressly permitted by the applicable software licenses.

Third-party dependencies remain subject to their respective licenses.

11\. Updates and Discontinuation
--------------------------------

The Project Team may modify, update, suspend, or discontinue QuMail or its associated infrastructure as part of prototype development and maintenance.

The Project Team does not guarantee that:

*   A particular version will remain available.
    
*   Existing functionality will remain unchanged.
    
*   Future versions will preserve compatibility with previous versions.
    
*   Cloud-dependent functionality will remain continuously accessible.
    

Users are responsible for maintaining appropriate copies of important information.

12\. Disclaimer of Warranties
-----------------------------

To the maximum extent permitted by applicable law, QuMail is provided on an "AS IS" and "AS AVAILABLE" basis.

The Project Team makes no guarantee that the software will:

*   Operate without errors.
    
*   Remain continuously available.
    
*   Successfully deliver every message.
    
*   Prevent every unauthorized disclosure.
    
*   Remain compatible with all email providers.
    
*   Provide uninterrupted access to cloud-dependent functionality.
    
*   Be free from vulnerabilities or defects.
    

Nothing in these Terms excludes warranties or rights that cannot legally be excluded under applicable law.

13\. Limitation of Liability
----------------------------

To the maximum extent permitted by applicable law, the Project Team shall not be liable for indirect, incidental, special, or consequential losses arising from the use of, or inability to use, QuMail.

This may include losses associated with:

*   Failed or delayed email delivery.
    
*   Lost or inaccessible data.
    
*   Compromised devices or email accounts.
    
*   Exposure of WebLink access URLs.
    
*   Third-party service interruptions.
    
*   User configuration errors.
    
*   Loss of access to locally stored cryptographic material.
    

Nothing in this section excludes liability for fraud, wilful misconduct, or any liability that cannot legally be excluded or limited.

14\. Suspension and Termination
-------------------------------

You may stop using QuMail at any time.

The Project Team may restrict or suspend access to associated online services where reasonably necessary to protect infrastructure, prevent abuse, address security incidents, or comply with applicable legal requirements.

Discontinuing use or uninstalling QuMail does not automatically delete information held by your email provider or external infrastructure.

Local application data and cloud-stored records may require separate deletion procedures.

15\. Privacy
------------

Your use of QuMail is also governed by the QuMail Privacy Policy.

The Privacy Policy explains the categories of information processed, local and cloud storage arrangements, external service providers, retention practices, and privacy-related contact procedures.

16\. Governing Law and Jurisdiction
-----------------------------------

These Terms shall be governed by the laws of India.

Disputes arising in connection with these Terms shall be subject to the jurisdiction of competent courts in India, subject to applicable mandatory legal rights and consumer protections.

17\. Changes to These Terms
---------------------------

The Project Team may revise these Terms to reflect changes in the prototype, infrastructure, security architecture, or applicable legal requirements.

The latest version will be made available through the official QuMail distribution or documentation channel.

The effective date will be updated whenever material changes are made.

18\. Contact Information
------------------------

For questions, concerns, or requests concerning these Terms, contact:

**QuMail Project Team**

*   Email: [uzair.shaikh.sec@gmail.com](mailto:uzair.shaikh.sec@gmail.com)
    
*   Jurisdiction: India
    
*   Official Website: Not currently designated.
    

**End of Terms & Conditions**