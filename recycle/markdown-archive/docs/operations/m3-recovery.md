# M3 isolated enrollment, verification and recovery procedure

Updated 2026-10-10. Development-only Windows boundary; use the explicit
[development Settings path](m3-development-settings.md). See [ADR 004](../adrs/004-m3-development-exception.md)
and [validation](m3-validation.md). There is no production cryptographic enablement or SMTP integration.
Use disposable synthetic data until the live OAuth and independent review gates
are satisfied. Never point this experiment at existing QuMail data or credentials.

## Enrollment and contact trust

1. Establish a verified provider issuer/subject and authorized address through the
   provider adapter. The local tests mint synthetic authorization evidence; they
   do not authorize a real mailbox. Google browser/PKCE is implemented; real
   provider acceptance is pending. Yahoo is disabled. Do not feed unverified
   decoded tokens into the internal post-verification claims function.
2. Create a fresh vault at an explicit local path. The backend stores a random
   master key in Windows Credential Manager; SQLite contains authenticated
   ciphertext. Missing credentials or OS-store failure block access. Do not copy
   an adjacent plaintext key into place to recover access.
3. Enroll the account, retaining the returned AccountContext and opaque KeyHandle
   within trusted application code. One device per local account is allowed;
   duplicate issuer/subject enrollment in that vault is refused. Root certifies
   distinct signing/encryption subkeys; it is not used for ordinary message signing.
4. Import only the contact's public certificate. The provider checks profile,
   bindings, lifecycle and the claimed address. Independently compare the entire
   root fingerprint in person or through an independently authenticated channel.
   Then explicitly pin it, recording method/time. An email address, directory
   response, OAuth login or self-signature alone is not sufficient.
5. Importing a changed root blocks use pending new independent verification.
   Importing a root-signed rotation may retain the root pin, while old observed
   subkeys are blocked from rollback. Import a valid signed root revocation to
   mark a known contact revoked. No automated directory/revocation freshness
   service exists; offline stale trust remains a limitation.

## Rotation, archive and removal

`rotate` retains the root, adds new provider-generated device subkeys, and signs
old-subkey revocations. Old owned records become retired. Share the public update
manually; no network publishing is implemented. `revoke` prevents new local
signing and exports a public root revocation update without a private export.
Historical decryption remains available with retained encrypted snapshots.

Root replacement creates a new fingerprint and cannot preserve contacts' trust
automatically. Imported replacement roots must be independently reverified by
those contacts. Key expiry also blocks new signing/encryption; extending expiry
is not an automatic workaround.

Default archive policy retains retired/revoked private material indefinitely in
the encrypted vault and explicit backups, to preserve historical decryption.
`destroy_archive_key(..., accept_loss=True)` only removes one inactive snapshot
from active vault state. Rotated certificate bundles can still contain the same
historical subkey, and backups can retain copies. It is not cryptographic erasure
of all copies or media. No ciphertext is deleted and no legacy record is migrated.

## Ordinary encrypted backup

Choose **Encrypted backup** explicitly and select a NEW destination. The worker
prepares an authenticated package and random 32-byte recovery secret in memory.
The source remains unchanged; no file exists yet. Click **Complete backup**, save
the secret offline separately, re-enter all 64 hexadecimal characters, then choose
**I saved the secret separately; write package**. This explicitly acknowledges your
custody before the worker may write. It cannot prove that you really saved a copy.

Before acknowledgment, cancellation, locking, account switch or closing clears the
private stage and secret widgets without writing a package. A failed secret-display
attempt can be retried while that owner/stage remains current. After acknowledgment,
QuMail clears its stage/widgets and writes only encrypted bytes; the worker needs no
recovery secret. Thus a later cancellation, lock, stale result or display failure
cannot discard the only acknowledged copy. Losing your saved copy still loses
recovery: there is no reset shortcut or escrow.

**Policy clarification/change:** secret disclosure and explicit custody acknowledgment
now precede file persistence; the former UI disclosed it after persistence. The
secret is retained transiently in memory until acknowledgment/cancel/lock/close,
never saved by QuMail in the vault, logs, argv, clipboard or temporary files.
Python/Qt do not guarantee memory zeroization. OAuth tokens and local operation/
export receipts are excluded from new packages. Packet format and legacy recovery
readers are unchanged. Stale account revision requires preparing/acknowledging a
fresh package. Failed writes may leave incomplete encrypted files; use a new path.

## Explicit device transfer

**Transfer device** is a separate confirmed action with the same pre-write custody
ceremony. An encrypted owner-scoped intent is committed first, the new package is
written/flushed, then a guarded transaction records completion and source suspension.
A failed write or denied/cancelled final commit does not suspend the source. If
cancellation follows final commit authorization, that original-account commit can
finish; cancellation does not claim rollback or recall. Ordinary backup never
changes lifecycle.

Unlock/select the original owner and **Inspect outcomes** to discover the actual
result after cancellation/restart. It shows recent encrypted commit receipts,
export intent/completion, current source lifecycle and whether the file matches its
recorded digest. A matching file with only an intent can be a usable backup while
the source remains active; use your already saved secret. Missing/inaccessible/
changed files are not silently retried or overwritten. Filesystem and SQLite cannot
commit atomically together. Up to 16 export records are retained per account; the
next export fails explicitly rather than deleting those records. The most recent
16 ordinary operation receipts are retained. Paths/digests are encrypted metadata,
not secret escrow or proof of remote-device retirement.

Local suspension cannot disable an offline/cloned vault or erase a remote device.
Keep source data and backup until restore/historical decryption are validated.
There is no automatic deletion, migration or global one-device enforcement claim.

## Clean restore and explicit activation

1. Create a clean development vault under Windows secure storage. Select Restore
   backup, supply the package/secret and complete fresh matching Google authorization.
   Tests use controlled synthetic identity evidence. Wrong secret, tamper,
   subject/address mismatch or storage failure reject the entire restore.
2. Restore remaps protected account/device ownership into new opaque IDs in one
   transaction and validates provider public/secret correspondence. Historical
   private snapshots remain encrypted; recovered active keys become retired and
   the account becomes **archive-only**. The root fingerprint is unchanged.
3. Historical decryption works in this state, as tested with real provider keys.
   No second active device is created merely by restoring, including repeated
   restoration of an old backup. No existing nonempty vault is merged.
4. Activate unchanged root only after explicitly confirming prior devices are
   retired. The provider must still accept its certificate/lifecycle and the key
   must not be expired/revoked/destroyed. Its fingerprint remains the same, so root
   replacement verification is not falsely required. Prior-device retirement is
   an operator acknowledgment, not remote erasure or clone detection.
5. Replace root instead when replacement is intended (for example compromise).
   It creates new provider key material and a different fingerprint; contacts must
   independently reverify. Historical keys remain archived. Provider login alone
   never silently replaces another party's trust pin.

The one-active-device policy is enforced locally and through explicit ceremonies;
it cannot prevent every cloned backup or a malicious/compromised old endpoint.
Simultaneous multi-device operation is deferred. Losing both OS access and the
recovery secret can permanently lose historical readability. No service can bypass
that loss. No production mail pipeline is enabled by either activation action.

## Failure and rollback boundaries

SQLite serializes lifecycle changes with BEGIN IMMEDIATE and FULL synchronous
writes. Failed writes/commit roll back; an abruptly terminated write transaction
and actual SQLite FULL error were tested. OS credential creation is not in that
transaction: an interrupted create can leave an orphan disposable credential or
incomplete database, requiring explicit cleanup by exact vault ID. Never enumerate
or delete unrelated Windows credentials. Existing vault and user data stay intact.

AEAD detects record corruption and cross-account swaps, not rollback of a whole
valid database/backup. Same-user malware, admin compromise, racing reparse-point
replacement, memory dumps and backup media erasure are outside demonstrated
protection. Existing reparse points are rejected, but full filesystem-race and
installation ACL hardening remain pending. Current API callers are trusted local
code; opaque IDs are not authentication against malicious code in that process.
