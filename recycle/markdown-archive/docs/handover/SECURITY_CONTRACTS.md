# Security contracts and unresolved assurance

These invariants apply to the **modern opt-in development path**. They are not a
claim that legacy/default paths or production releases satisfy them. Requirements:
[canonical specification](../../QuMail-1.0-Research-Audit-Specification.md) §§35–50,
§51 tests, §54 milestones. Implementation locations are in
[CODEBASE_MAP](CODEBASE_MAP.md); exact profile is in
[M5 validation](../operations/m5-validation.md#exact-wire-profile-and-compatibility).

## Contracts a successor must not weaken

| Boundary / requirement | Rule and failure prevented |
|---|---|
| Policy, I01/QM-SEC-001/002/006 | Allowlisted experimental profile only. Unknown/weak/malformed/unsupported suites fail closed. No automatic provider replacement, plaintext, TQR, portal or simulator fallback; otherwise an attacker can turn a discovery/crypto failure into disclosure. M2 typed proof is isolated; do not claim a globally centralized production policy already exists. |
| Recipient ownership, QM-ID-001–005/KEY-002 | Distinct account/device/address/root/key IDs. Sender gets recipient public material, never recipient secret. OAuth proves authorized mailbox binding, not peer key trust. Valid self-signature/import is not independent verification. Changed roots block; current expiry/revocation/capability checks apply at preparation and before side effects. |
| Verify then publish, QM-SEC-003/CRYPTO-005 | Buffer native plaintext until final integrity and required composite signature verification; reject malformed profile/metadata/intended recipient. Identity trust remains a separate field; unverified identity cannot receive verified-confidential label. No streaming unverified text or salvage fallback on a modern parse failure. |
| Ownership, T04/T12 | Every worker/request carries original account/vault/generation; cancellation/lock/switch invalidates publication. All Qt widget access on GUI thread; worker-owned SQLite connections. Never install a stale worker's tokens/keys/display into the newly selected account. |
| Commit truth, T08/T09/T12 | Recheck authorization before reservation/commit. Short synchronized reservation cannot hold GUI mutex across disk/native/network work. After reservation or possible external side effect, cancellation may suppress display but cannot promise rollback; retain original-owner receipts/outcome inspection. |
| Vault, QM-KEY-001/004/006 | Secure-store failure blocks; no file-key/cache bypass. AEAD binds vault/account/revision/version; transactional restore and ownership checks. Keep secrets off argv/environment/logs/ordinary temp files/clipboard. Same-user malware can still access credentials/process memory; this is not a TPM/HSM enclave. |
| Recovery custody, T08 | Show fresh high-entropy secret and require explicit saved-offline acknowledgment **before** package writing. Before acknowledgment, switch/lock/cancel/display failure clears stage without exporting. Afterwards user already has custody; cancellation cannot silently lose the only secret for a written file. No new persistent recovery-secret copy. |
| Backup vs transfer | Backup leaves source active. Explicit transfer suspends only after successful package persistence and final transaction. Failed/cancelled transfer may leave a recoverable orphan package/intent but must not falsely deactivate source. Archive-only restore is default; activation/retirement explicit. Cannot erase remote/offline/cloned copies. |
| Durable SMTP, I09/QM-MAIL-004 | Complete encrypted envelope, stable ID, key/archive references persist before SMTP. Retry sends identical bytes; no fresh encryption or changing recipients under same operation. Accepted means final SMTP acceptance, not delivery/read/decrypt. Lost final response or crash after dispatch is Unknown. Explicit duplicate-risk acknowledgment/investigation, no blind retry. Receipt export failure never rewrites Accepted. |
| Network credentials, QM-MAIL-001/ID-002 | Fixed verified Gmail endpoints, TLS/hostname checks before XOAUTH2. Scope/issuer/subject/address bind credentials to account. No password fallback or identity-only tokens for mail. Loopback fixture policy remains restrictive; no verify=False or TLS bypass for tests. |
| Inbox, QM-MAIL-005/SEC-007 | Key is account/mailbox/UIDVALIDITY/UID, not row or message-id alone. Header and full reads use PEEK; no implicit Seen, CLOSE or EXPUNGE. Explicit read/unread may have completed even if cancellation hides result: re-fetch actual state. Replay identity/digest persist before returning modern message; duplicate/conflict remains visible. |
| UI/privacy, QM-MAIL-006/PRIV-001–003 | Plain text only, no HTML/remote resources/auto-execution. Untrusted filename/type cannot determine export path. Explicit no-clobber Save As only after verification; cleared plaintext must not reappear after stale result. Outer metadata is a transport claim, not authenticated identity. |
| Reply/forward | Protected reply uses authenticated inner author/references and verified-confidential source. Forward needs explicit recipients and states no original endorsement. Conventional reply requires confirmation/unverified label. Re-evaluate recipients/current keys for every new message; no Bcc or plaintext fallback. |
| Relay, I10/QM-PORTAL-001/002 | Only ciphertext body/attachments, no endpoint keys or Google tokens. Dedicated mTLS cert→principal/device mapping, recipient authorization, atomic one-initial-lease, bounded same-lease retry. Outage fails readiness, no memory fallback. Download is not human read; ACK cannot erase a recipient's copies. |
| Legacy/migration | Preserve old ciphertext, metadata, keys, readers and evidence. Never reinterpret TQR bytes as standard OpenPGP or automatically convert existing user stores. No default production route change during launcher fixes. |

## Cryptographic facts versus assurance

**Executed proof:** exact Sequoia 2.4.1/OpenSSL 3.5.9 and rPGP 0.21.0 exchange
ML-KEM-768+X25519 encryption and ML-DSA-65+Ed25519 signatures in both directions,
with v6 keys/PKESKs/signatures, SEIPDv2 AES-256/GCM, 4 KiB chunks and generated
SHA-512 signatures. Published vectors, multi-recipient, wrong key, tamper/truncation
and each composite-signature component negative tests are retained. Providers own
combiners, encodings and nonces; never implement a substitute from memory.
M3 root/subkey and M5 MIME adaptations have their own later proof records.

**Not equivalent evidence:** same-provider round trip, published vector, independent
crypto exchange, common MIME fixture, independent mail client, live Gmail and human
review. Do not substitute one for another. Neither current profile marker is an
approved production registry entry. M2 mock errors prove propagation only.

**Real diagnostic failure evidence:** selected Sequoia private OpenSSL context,
fresh child processes and supported TEST-RAND/provider-property injection produce
random-source/keygen/encrypt failure and mandatory-algorithm panic. Typed boundary
contains unwind with no plaintext success. This used an explicitly patched
diagnostic context accessor; unmodified-provider tests run separately. The 651-file
source/patch audit proves patch scope, **not broader cryptographic correctness**.

**Source-inspected/unresolved:** default-provider self_test returns success without
a self-test callback; no FIPS/KAT assurance. OS entropy outage and allocation failure
were not injected. Deprecated `OsslContext::new_lib_ctx` can fall back to NULL/default
context on allocation failure. Actual mandatory-SHA256 panic at Sequoia
`packet/key/v6.rs:282` needs expert disposition. Rust unwind containment does not
contain abort/OOM/segfault; current subprocess isolation helps reject exit but is
not a demonstrated OS memory-budget/constant-time/zeroization guarantee.

Review native diagnostics by category, not raw count: M1's 42 repeated liboqs
optimization-barrier warnings affect that legacy research build; the new selected
candidate does not link liboqs. New OpenSSL build separately emitted 871 MSVC
diagnostics: C4267 688, C4244 79 (conversions including ML-DSA/codecs), C4133 66
(pointer types/conditional interlocked paths), C4334 36 (shifts), C4319 two
(widening). 231 Perl locale lines and 22 diagnostic Rust deprecations are distinct.
Neither suppression, `no-asm`, functional tests nor warning counts establish safety
or insecurity. Detailed trace/questions/evidence:
[M2 external review](../operations/m2-external-review.md),
[provider evaluation](../operations/m2-provider-evaluation.md).

## Remaining risks and release gates

- **External review:** composition/secret boundaries, enrollment/root-reset/recovery,
  parser/protected-header policy, backend identity and usable-security. Existing
  ADR development exceptions allow work; independent approval is still absent.
- **Provider/build/platform:** native warning/side-channel review, allocation/abort/
  entropy assurance, exact release toolchain/build/signature provenance, Windows
  fresh desktop and Android-specific qualification. No FIPS, ITS, forward-secrecy,
  post-compromise-security or perfect deletion claim.
- **Trust/history:** manual contact updates lack online revocation freshness;
  historical decrypt with owned archive keys is not proof of historical signer
  validity after expiry/revocation. Whole-vault/backup rollback can roll back replay
  and trust state; AEAD does not add an external monotonic counter.
- **Endpoint:** same-user malware/admin/process inspection, Python copies/crash dumps,
  OS I/O drain latency and hostile filesystem races remain. Avoid implying opaque
  handles hide keys from arbitrary code already inside the process.
- **Operational limits:** smaller bounded development sizes, manual INBOX paging,
  page-local threads, capped outbox/receipts, no modern Yahoo, no Android support.
  These must remain explicit, not described as full specification performance.
- **Relay:** server sees routing identifiers, size/timing and ciphertext; compromised
  authorization registry/storage can deny/replay/corrupt, but endpoint verification
  still applies. SQLite single-host only. Primary-row payload removal leaves possible
  WAL/backup/remanence; bounded tombstones do not mean forensic erasure/exactly-once read.
- **Legacy:** original liboqs-python 0.14.1 artifact/historical fixture compatibility
  and independent legacy interoperability remain unresolved under ADR 002. Research
  0.16.0.1/0.16.0 tests do not satisfy them. F01–F19 remain open where legacy code ships.
- **Licensing/distribution:** no owner project license selected; Qt, LGPL/OpenSSL/
  transitive compliance and installers/bundled native binaries require decisions.
  Do not invent a license or produce a security release from local test success.

## Authorization at handoff

This documentation task sends nothing and changes no accounts. Earlier permission
covered only designated controlled A/B enrollment/refresh/retrieval, test-message
Seen changes and three non-sensitive protected sends: A→B with small attachment and
archive, B→A reply, B→A forward. User now asks to do manual testing. Preserve ordinary
application confirmations. Existing permission is not arbitrary send, deployment,
cloud provisioning, credential-cache access, data migration or deletion permission.
Local-only M7 is the agreed backend scope; QKD/hardware excluded. Human/AI inspection
and automated checks must never be described as independent expert approval.
