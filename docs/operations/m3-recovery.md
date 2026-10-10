# M3 isolated enrollment, verification and recovery procedure

Development-only Windows boundary. See [ADR 004](../adrs/004-m3-development-exception.md)
and [validation](m3-validation.md). There is no production Settings/SMTP integration.
Use disposable synthetic data until the live OAuth and independent review gates
are satisfied. Never point this experiment at existing QuMail data or credentials.

## Enrollment and contact trust

1. Establish a verified provider issuer/subject and authorized address through the
   provider adapter. The local tests mint synthetic authorization evidence; they
   do not authorize a real mailbox. Google browser/PKCE and provider acceptance
   are pending; Yahoo is disabled in the new boundary. Do not feed unverified
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

## Explicit encrypted recovery / transfer

1. Invoke `export_recovery(context, explicit=True)` deliberately. It returns a
   versioned encrypted package and a fresh **32-byte random recovery secret**.
   Keep them separately on user-controlled offline media. No password/phrase KDF,
   mailbox password, provider reset or server escrow substitutes for this secret.
   The API does not write either plaintext key material or a recovery secret to disk.
2. This is an explicit transfer ceremony: the source account is transactionally
   suspended before package bytes are returned. If a commit fails no package is
   returned. Preserve the vault if writing the returned package fails; the source
   remains suspended and can export again. Do not reactivate recovered old keys.
   Any previously saved backup remains usable only for archive recovery.
3. Create a clean vault under supported Windows secure storage. Obtain fresh
   verified provider evidence for the same issuer/subject and authorized addresses.
   Restore with the package/secret and explicit consent. Wrong secret, tampering,
   ownership/profile mismatch or storage failure must reject the entire restore.
   Nonempty destination vaults are refused. No merger into existing user data occurs.
4. Restore allocates fresh account/device IDs, remaps protected ownership and
   validates provider public/secret correspondence in one database transaction.
   All recovered active keys become retired and the account is **archive-only**.
   Historical decryption is tested with actual restored provider-generated keys.
   OAuth tokens are excluded: a separate verified authorization is required.
5. To resume new messages in a future integrated application, explicitly replace
   the root. Contacts must independently verify that new fingerprint. The old
   source remains suspended. Restore alone never activates a second device.

Loss of both the device/master credential and recovery secret can permanently
lose historical readability. Copying an offline vault defeats local suspension;
this is not remote revocation or proof that a lost device was erased. A fresh root
and explicit contact verification limit transparent reuse. No simultaneous
multi-device model is claimed.

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
