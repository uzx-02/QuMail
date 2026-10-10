# ADR 004: owner-authorized M3 development before external M2 review

Date: 2026-10-05; development integration amendment 2026-10-10. Status: accepted **for bounded local development only**, at the
owner's explicit request. No independent reviewer, certification, production
cryptographic approval or security-release approval is represented by this ADR.

## Decision and affected requirements

Canonical specification §54 orders M3 after M2 and requires a cryptographer/
protocol reviewer to inspect M2 composition and secret boundaries. QM-CRYPTO-001
requires a reviewed provider; Appendix C3 retains the review/release gates.
The owner authorizes an exception to **development ordering**, because a human
cryptographer is not available. M2 engineering proof remains complete and its
independent review outstanding. M2 remains PARTIAL, not unconditionally complete.
M3 may use the provisional candidate. Independent review is still required before
production cryptographic enablement or a security release. Later review can
require changes to M2 and all dependent M3 work. The canonical specification is
unchanged, and the exception must not be mistaken for satisfying its review gate.

Preserve M2 checkpoint `1fc4e55f09e173cec7634d0b2dc776097b552063`, all its input
hashes and retained evidence, ADR 003 and unresolved findings. Preserve the
uncommitted reviewer-request draft separately. Work on local branch
`codex/m3-identity-vault` starts at that checkpoint. M1 remains unchanged.

## Bounded M3 product decisions

Requirements §§39–40, §54 M3, QM-ID-001–005, QM-KEY-001–006, QM-SEC-004,
QM-PQC-002, QM-PRIV-001, QM-DOC-001/002 and T04/T06/T08 govern this boundary.

- Windows first; multiple isolated accounts with **one active enrolled device
  per account**. Simultaneous multiple devices and their recipient-subkey
  selection/independent interoperability remain deferred.
- Manual public-certificate import, valid certified address binding and explicit
  independent full fingerprint comparison. Email/OAuth, directory responses and
  self-signatures cannot grant contact trust. Root replacements block new sends
  until a new independent confirmation. Known retired subkeys cannot be rolled
  back by importing an older certificate with the same root.
- Use direct Windows Credential Manager generic credentials to store one random
  256-bit vault master key, scoped to current Windows user/local machine.
  `CredWriteW`, `CredReadW`, `CredDeleteW`, `CredFree`; type GENERIC, persistence
  LOCAL_MACHINE. The 32-byte blob is below Microsoft's 2560-byte limit. No
  dynamically selected keyring or adjacent master-key file. Missing/unavailable
  secure storage fails access and enrollment; no cached master-key bypass.
- SQLite contains opaque account IDs, revisions and AES-256-GCM encrypted account
  aggregates. Ownership, keys, contacts, OAuth records and lifecycle metadata are
  inside authentication; associated data binds vault/account/revision/version.
  Random 96-bit nonces, maintained cryptography 50.0.2; BEGIN IMMEDIATE plus FULL
  synchronous transactions serialize concurrent changes and roll back failure.
- A certification-only v6 ML-DSA-65+Ed25519 root authorizes a separate v6 signing
  subkey of the same algorithm and a v6 ML-KEM-768+X25519 encryption subkey.
  This differs from M2's primary-signing fixture. Test this exact structure and
  additive rotation with rPGP before accepting it for provisional development.
  Root review/expiry three years; device subkeys one year. No independent
  cryptographic-lifetime assurance is implied by those product defaults.
- Keep the M2 AES-256/GCM SEIPDv2, v6 PKESK/signature, SHA-512 generated signatures
  and 4 KiB chunks. No new combiner, nonce rule or downgraded profile. Provider
  source/version/native flags remain unchanged. M3 copies/adapts the bounded
  M2 helper logic into its own isolated source; M2 bytes are never edited.
- Additive device rotation signs revocations for old subkeys and new bindings
  under the same root. Retain encrypted secret snapshots for historical decrypt.
  Revocation blocks new operations; explicit archive-key destruction requires
  acknowledgment of loss and does not erase ciphertext, offline backups or media.
- Recovery v1 encrypts one selected account locally with a fresh random 256-bit
  recovery secret. Ordinary backup does not suspend or revoke the source. Explicit
  device transfer first persists the package and only then commits local suspension.
  A failed persistence/commit leaves the account active; persisted orphan packages
  still restore archive-only. Restore is transactional into a clean vault with new
  local account/device IDs. Activation of an unchanged root requires explicit prior-
  device retirement acknowledgment. Replacement roots require contact re-verification.
  OAuth tokens are excluded from backup and require fresh authorization. No hosted
  recovery, directory or private-key escrow.

## Windows API evidence and limitations

Official API review on 2026-10-05:
[CredWriteW](https://learn.microsoft.com/en-us/windows/win32/api/wincred/nf-wincred-credwritew),
[CredReadW](https://learn.microsoft.com/en-us/windows/win32/api/wincred/nf-wincred-credreadw),
[CREDENTIALW](https://learn.microsoft.com/en-us/windows/win32/api/wincred/ns-wincred-credentialw),
[CredDeleteW](https://learn.microsoft.com/en-us/windows/win32/api/wincred/nf-wincred-creddeletew).
These documented desktop APIs use the current token's credential set. Network
logon sessions can lack a set. Local-machine persistence means this user's
subsequent logon sessions on this computer, not access granted to every local
user. It is not process isolation: malware acting as the logged-in user can
access that user's credentials. This implementation does not promise TPM binding,
Windows Hello confirmation, protection from an administrator or perfect erasure.

[cryptography AEAD API](https://cryptography.io/en/stable/hazmat/primitives/aead/)
supplies authenticated decryption before returning plaintext. The storage format
is a versioned application container, not a newly designed cryptographic primitive.
OS credential creation and SQLite cannot share a transaction: an interrupted
create may leave an orphan OS entry or incomplete database, which fails closed
and requires explicit cleanup. No secret is written unwrapped as a workaround.

## Assurance and integration boundary

The provisional vault/helper remain under `experiments/m3`. The explicit
`--dev-identity --dev-vault PATH` application branch now connects them to separate
account-session/service and Settings interfaces. It is disabled by default and
never constructs legacy inbox/compose, TQR, simulator or portal components. No
sending is available. Immutable context installation precedes notification; worker
generation tickets prevent stale persistence/display updates. Helpers use bounded anonymous pipes, generic failure codes,
30-second timeout and no forwarded native diagnostics. Keys necessarily cross
the private helper pipe into Python for encrypted storage; opaque IDs prevent
external path construction, not access by malicious code in this process.
Python copying, memory/crash-dump hygiene, subprocess resource isolation,
OS-store/SQLite rollback resistance and hostile same-user filesystem races need
further qualification. Full database rollback is not defeated by AEAD alone.

Google ID-token verification uses locked google-auth 2.49.1 with issuer/audience/
expiry and explicit state/nonce/subject/address checks. Following Google's
[official token guidance](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token),
email_verified alone is not authoritative for third-party mail. The prototype
accepts gmail.com or a matching verified hosted-domain claim; unproven aliases
fail closed pending provider API evidence. Local signed issuer
fixtures are synthetic, not Google approval. External-browser PKCE/loopback,
state/nonce validation, reauthorization and refresh are implemented. Refresh
authenticates identity at the fixed Google TLS userinfo endpoint; it does not
assume initial-token nonce semantics. Actual Google test-account authorization/
refresh acceptance remains pending; unproven aliases and Yahoo enrollment fail
closed. Only an explicit provisioned Desktop-client configuration is read. Existing legacy OAuth/session modules remain unchanged and unsafe
for the new boundary; none is claimed remediated by this isolated work.

Source suspension cannot revoke a copy of an offline old vault or a compromised
device. Repeated restores default to archive-only. Explicit unchanged-root
activation requires acknowledgment that previous devices are retired; no automatic
activation occurs. A changed root still requires contact re-verification. Do not claim remote device erasure or global enforcement.

The M2 native panic, allocation-context fallback, lack of default-provider FIPS
self-test, compiler warnings and constant-time limitations remain in ADR 003 and
the review package. This decision neither fixes nor approves them. Licensing,
historical-provider compatibility, distribution, platform and release gates
remain separate and unresolved. M4 is not authorized here.

## Bounded integration authorization (2026-10-10)

The owner explicitly authorized account/session, Settings, identity, vault and OAuth
integration without another routine review-order stop. The exception above remains
in force; independent review is deferred to before production enablement/security
release. UI/service implementation and tests are not independent approval. See
[m3-development-settings.md](../operations/m3-development-settings.md) for exact
setup and live acceptance, and the current integration section of M3 validation.
