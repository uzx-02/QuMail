QuMail – Privacy Policy
=======================

**Effective Date:** 14/11/2026**Last Updated:** 14/11/2026

1\. Introduction
----------------

The QuMail Project Team ("Project Team", "we", "us", or "our") respects the privacy of individuals using QuMail.

QuMail is a Windows desktop email client designed to provide additional cryptographic protection for electronic communications through post-quantum encrypted email and encrypted WebLinks.

QuMail is currently distributed as a private prototype for limited testing and evaluation.

This Privacy Policy explains how information is processed, stored, transmitted, and protected when you use the QuMail desktop application and its associated online infrastructure.

QuMail follows a local-first approach for important cryptographic operations. However, certain functionality requires communication with external email providers and cloud infrastructure.

This policy distinguishes between local processing, email-provider processing, and cloud-based processing.

2\. Who Operates QuMail?
------------------------

QuMail is developed and maintained by the **QuMail Project Team**.

The Project Team currently operates as a project team rather than representing itself through a registered company or incorporated organization in this Privacy Policy.

For privacy-related questions, requests, or concerns, you may contact:

**QuMail Project Team**

Email: [uzair.shaikh.sec@gmail.com](mailto:uzair.shaikh.sec@gmail.com)

Jurisdiction: India.

3\. Scope of This Policy
------------------------

This Privacy Policy applies to:

*   The QuMail Windows desktop application.
    
*   Local application storage and cryptographic vaults.
    
*   Google OAuth authentication.
    
*   Custom IMAP/SMTP mailbox connections.
    
*   QuMail Cloud Directory functionality.
    
*   Encrypted WebLink generation and storage.
    
*   Associated application settings and local processing.
    

This policy does not replace the independent privacy policies of Google, other email providers, Cloudflare, or other third-party services.

4\. Information Processed by QuMail
-----------------------------------

The information processed depends on the functionality you choose to use.

### 4.1 Account and Identity Information

When you configure an email account or enroll a QuMail identity, the application may process:

*   Email addresses.
    
*   Account identifiers.
    
*   Authentication tokens.
    
*   Mailbox configuration details.
    
*   Cryptographic public keys.
    
*   Public-key fingerprints.
    
*   Identity-related records.
    

The Cloud Directory uses HMAC-SHA256-derived email identifiers for account indexing rather than storing raw email addresses in the account index.

This does not mean that email addresses are never processed. They remain necessary for certain authentication, enrollment, and email-related operations.

### 4.2 Authentication Information

QuMail supports Google OAuth 2.0 and custom IMAP/SMTP authentication.

Depending on the authentication method, information processed may include:

*   OAuth access tokens.
    
*   OAuth refresh tokens.
    
*   Email addresses.
    
*   Mailbox authentication credentials.
    
*   IMAP and SMTP configuration details.
    

Certain credentials and tokens are maintained in local storage protected through Windows DPAPI-based mechanisms.

When using Google OAuth, authentication is performed through Google's supported authorization workflow rather than requiring you to provide your Google account password directly to QuMail.

### 4.3 Email Messages and Attachments

When you connect an email account, QuMail may process information necessary to retrieve, display, synchronize, and send messages.

This may include:

*   Sender and recipient addresses.
    
*   Email subjects.
    
*   Message bodies.
    
*   Message headers.
    
*   Attachments.
    
*   Timestamps.
    
*   Mailbox and folder information.
    
*   Message status information.
    

Messages retrieved through supported mailbox connections are processed by the local application.

Depending on the application workflow, mailbox information may also be retained in local application storage for synchronization and access.

Ordinary email messages remain subject to the processing and storage practices of your email provider.

### 4.4 Cryptographic Information

QuMail processes cryptographic information necessary to establish and maintain secure communication.

This includes:

*   ML-KEM-768 key material.
    
*   ML-DSA-65 key material.
    
*   Ed25519 signing information used by WebLink functionality.
    
*   Public-key fingerprints.
    
*   Key enrollment and verification information.
    

Private identity keys are generated and managed locally through the native Rust cryptographic providers.

The Cloud Directory receives public-key information and associated identity records required for public-key discovery.

Private cryptographic identity keys are not intended to be transmitted to the Cloud Directory.

### 4.5 Encrypted WebLink Information

When you generate an encrypted WebLink, QuMail processes:

*   Message content.
    
*   Attachments.
    
*   Recipient information required for delivery.
    
*   A randomly generated AES-256-GCM encryption key.
    
*   Encrypted message payloads.
    
*   WebLink identifiers.
    
*   Optional access-control settings.
    

The message and attachments are encrypted locally before the encrypted payload is uploaded to the Cloudflare-hosted infrastructure.

The decryption key is embedded in the URL fragment.

The key is designed not to be transmitted in ordinary HTTP requests to the storage server.

However, the complete WebLink may be included in an email delivered to the recipient. Anyone obtaining the complete link may potentially access the message, depending on the configured access controls.

Users should treat WebLinks as confidential access credentials.

### 4.6 Application Settings and Preferences

QuMail may store settings necessary for application functionality, including:

*   Interface language.
    
*   Theme preferences.
    
*   Account preferences.
    
*   Security settings.
    
*   Offline translation preferences.
    
*   Onboarding completion information.
    
*   Other application configuration.
    

These settings may be stored locally using the application's frontend and backend storage mechanisms.

### 4.7 Offline Translation Information

QuMail provides local translation functionality for supported languages, currently Hindi and Marathi.

The translation engine uses locally installed CTranslate2 models.

When translation is requested:

*   Selected text is processed locally.
    
*   Translation inference takes place on your device.
    
*   Downloaded translation models are used for local processing.
    
*   Translation does not require sending the selected message text to an external translation API.
    

An internet connection may be required to download the translation models initially.

5\. How Information Is Used
---------------------------

Information processed through QuMail is used to provide the application's functionality.

PurposeInformation involvedAccount authenticationEmail addresses and authentication tokensMailbox configurationServer settings and credentialsEmail operationsMessages, headers, recipients and attachmentsIdentity enrollmentEmail-derived identifiers and public keysKey discoveryPublic-key bundles and fingerprintsPost-quantum communicationCryptographic information and message payloadsWebLink creationEncrypted messages, attachments and access identifiersSecurity verificationKey fingerprints and signature-verification resultsOffline translationSelected text and local translation modelsApplication operationPreferences and local configuration

The Project Team does not describe QuMail as an advertising or data-broker service.

6\. Local Processing and Storage
--------------------------------

QuMail uses local storage for important application information.

Depending on the features used, this may include:

*   Encrypted account credentials.
    
*   OAuth tokens.
    
*   Cryptographic identity keys.
    
*   Mailbox information and caches.
    
*   Application settings.
    
*   Contact trust information.
    
*   Translation models and associated local data.
    

Windows DPAPI and associated local encryption mechanisms are used to protect documented credentials and vault information at rest.

These protections are associated with the local Windows security environment.

However, local encryption cannot guarantee protection against every threat, including compromised operating systems, malware, unauthorized access to an unlocked session, or attacks on the user's device.

7\. Cloud Infrastructure and External Services
----------------------------------------------

QuMail uses external infrastructure to provide selected features.

### 7.1 Cloudflare

QuMail uses Cloudflare Workers and D1 database infrastructure for Cloud Directory and encrypted WebLink functionality.

Depending on the workflow, information processed by this infrastructure may include:

*   HMAC-derived account identifiers.
    
*   Public cryptographic keys.
    
*   Public-key fingerprints.
    
*   Encrypted WebLink payloads.
    
*   Encrypted attachment payloads.
    
*   WebLink identifiers.
    
*   Associated access-control information.
    
*   Technical request information required for service operation.
    

The Cloud Directory is designed to store encrypted WebLink payloads rather than the corresponding plaintext message content.

The Cloudflare infrastructure remains an external service provider subject to its own privacy and operational practices.

### 7.2 Email Providers

QuMail connects to external email services through Google OAuth, IMAP, and SMTP.

Depending on your selected provider and communication method, those services may process:

*   Email addresses.
    
*   Message headers.
    
*   Message content.
    
*   Attachments.
    
*   Timestamps.
    
*   Authentication information.
    
*   WebLink URLs.
    

For ordinary email, the email provider may be able to access message contents.

For supported post-quantum encrypted messages, the email transport carries encrypted message payloads.

Your relationship with your email provider remains subject to its own privacy policy and terms.

### 7.3 Other Service Providers

Additional service providers may be involved in specific application operations, infrastructure hosting, or model distribution.

Any additional provider that processes personal information should be identified and reflected in this policy before the corresponding functionality is made available to users.

8\. What the Cloud Directory Can and Cannot Access
--------------------------------------------------

QuMail is designed to limit the information exposed to its Cloud Directory.

Based on the documented architecture:

**Information that may be available to the Cloud Directory:**

*   Public cryptographic keys.
    
*   Public-key fingerprints.
    
*   HMAC-derived account identifiers.
    
*   Encrypted WebLink payloads.
    
*   Encrypted attachment payloads.
    
*   WebLink identifiers and access-control information.
    
*   Technical information required for service operation.
    

**Information not intentionally uploaded through the documented cryptographic workflows:**

*   Private ML-KEM-768 identity keys.
    
*   Private ML-DSA-65 identity keys.
    
*   WebLink AES-256-GCM decryption keys through ordinary payload uploads.
    
*   Plaintext WebLink message content through encrypted payload storage.
    

These statements describe the intended application architecture and documented data flows. They do not constitute a guarantee against endpoint compromise, recipient-side disclosure, malicious browser extensions, or every possible information-security incident.

9\. Data Retention
------------------

Information is retained according to its purpose and the storage mechanism involved.

### 9.1 Local Information

Local credentials, encrypted vaults, mailbox information, application settings, and translation data may remain on your device until removed through the application, operating system, or relevant cleanup procedure.

Uninstalling QuMail should not be assumed to delete every locally stored application record.

### 9.2 Cloud Directory Information

Information maintained by the Cloud Directory is subject to the applicable record lifecycle, access-control, and deletion mechanisms implemented in the deployed infrastructure.

The Project Team does not make an unverified universal retention-period claim for all Cloud Directory records.

### 9.3 Email Provider Information

Messages transmitted through your email account remain subject to your email provider's storage, retention, backup, and deletion policies.

Deleting a message locally does not necessarily delete other copies maintained by an email provider or recipient.

10\. Information Sharing and Disclosure
---------------------------------------

Information may be shared with external service providers where necessary to provide the functionality requested by the user.

This includes:

*   Cloudflare for Cloud Directory and encrypted WebLink infrastructure.
    
*   Google and other email providers for authentication and email transport.
    
*   Other providers where required for a documented application function.
    

Information may also be disclosed where required by applicable law, valid legal process, or to protect the security and integrity of the application and its infrastructure.

The Project Team does not intentionally upload private cryptographic identity keys to the Cloud Directory.

11\. Security Measures
----------------------

QuMail incorporates multiple security mechanisms intended to protect user information.

These include:

*   ML-KEM-768 and ML-DSA-65 for supported post-quantum communication.
    
*   AES-256-GCM for encrypted WebLinks.
    
*   Ed25519 signatures for WebLink signature binding.
    
*   Windows DPAPI-protected local credential and vault storage.
    
*   Local cryptographic key generation.
    
*   SHA-256 integrity verification for native cryptographic providers.
    
*   Trust-On-First-Use contact pinning.
    
*   Key-change and signature-verification indicators.
    
*   Security PIN and automatic vault-lock functionality.
    
*   HTTPS communication with the Cloud Directory.
    

These mechanisms reduce certain security risks but cannot guarantee absolute protection.

The security of information also depends on device integrity, user practices, external infrastructure, and recipient systems.

12\. Your Privacy Choices and Requests
--------------------------------------

For questions or requests concerning information processed through QuMail, you may contact the Project Team using the email address provided in this policy.

You may request assistance concerning:

*   Information associated with your QuMail identity.
    
*   Correction of inaccurate information, where feasible.
    
*   Deletion of eligible information.
    
*   Questions about information sharing and processing.
    
*   Privacy-related concerns or complaints.
    

Requests may require verification to ensure that information is not disclosed or deleted on behalf of an unauthorized person.

Certain information may remain with external email providers or infrastructure providers under their independent retention obligations.

Deleting local application data does not automatically delete information held by external services.

Privacy requests will be handled in accordance with applicable Indian law and the provisions in force at the relevant time.

13\. International Data Processing
----------------------------------

QuMail integrates with external infrastructure providers that may process or store information in different geographical locations.

The location of processing depends on the relevant provider, service configuration, and deployment arrangements.

Where personal information is processed or transferred internationally, the applicable legal requirements will govern such processing.

The Project Team does not represent that all QuMail-related data is exclusively stored within India.

14\. Children's Privacy
-----------------------

QuMail is intended for a general audience and is not specifically designed to collect information from children.

Individuals under 18 should use the application with the knowledge and involvement of a parent or legal guardian.

The Project Team does not intentionally seek to collect children's personal information beyond what is necessary for an authorized and lawful use.

Applicable requirements concerning children's personal data will be observed as required by the laws in force.

15\. Third-Party Privacy Policies
---------------------------------

Your use of integrated third-party services may be subject to their respective privacy policies.

Relevant providers include:

*   Google: [https://policies.google.com/privacy](https://policies.google.com/privacy)
    
*   Cloudflare: [https://www.cloudflare.com/privacypolicy/](https://www.cloudflare.com/privacypolicy/)
    

Other provider policies will be identified where applicable.

16\. Changes to This Privacy Policy
-----------------------------------

The Project Team may update this Privacy Policy when:

*   QuMail functionality changes.
    
*   New integrations are introduced.
    
*   Data processing practices change.
    
*   The cloud architecture is modified.
    
*   Applicable legal requirements change.
    

The latest version will be made available through the official QuMail distribution or documentation channel.

The effective date will be updated whenever material changes are made.

17\. Contact Information
------------------------

For privacy-related questions, information requests, or complaints, contact:

**QuMail Project Team**

*   Email: [uzair.shaikh.sec@gmail.com](mailto:uzair.shaikh.sec@gmail.com)
    
*   Jurisdiction: India
    
*   Official Website: Not currently designated.
    

**End of Privacy Policy**