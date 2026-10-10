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

Choose Encrypted backup explicitly. A random 32-byte recovery secret protects a
versioned authenticated package containing the selected account's keys/metadata.
The source remains in its existing lifecycle state; backup does not revoke or
suspend it. The UI writes ciphertext to a new file and displays the secret locally
once. Keep it offline separately; no password/provider-reset shortcut, plaintext
key export, automatic clipboard copy, hosted escrow or secret-file fallback exists.
OAuth tokens are excluded from backup and require fresh authorization at restore.
A failed write can leave an incomplete encrypted file; use a new destination on
retry. No account deactivation results from ordinary export or persistence failure.

## Explicit device transfer

Transfer device is a separate confirmed action. It holds a lifecycle transaction,
persists the encrypted package to a new file with flush/fsync, and only then commits
local suspension. A failed file write or vault commit leaves the source active.
If the file succeeds but database commit fails, an encrypted package can remain;
it still restores archive-only. OS filesystem and SQLite do not share an atomic
transaction, so this ordering prefers an extra inert backup over silent deactivation.
After a successful transfer commit, even a display refresh failure returns the
recovery secret and reports transfer completion; the UI may lock for safe refresh.

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
