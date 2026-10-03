# M1 preservation and rollback

M1 performs **no user-data migration**. Existing ciphertext, metadata, numeric
legacy modes, MIME protocol identifiers, key IDs, legacy readers and file paths
are retained. Documentation and human-readable labels/preambles change; previously
stored files are not rewritten. APP_VERSION is a legacy value, not release approval.

Before manually trying another build, close the client and retain a private backup
of the complete `secrets/` tree (including raw wrapping keys and `send_keys/`),
`certs/`, downloaded messages and any external mailbox/portal data. Do not upload
these files to CI, source control or issue reports. A token/key ciphertext without
its wrapping key may be unrecoverable. The process must not bulk-delete old keys.

Tests change to temporary directories before collection and reset simulator/portal
state per test. They do not migrate or inspect the user's secret directories. No
real account, mail transmission, remote database write or deployment is part of M1.

For rollback, use a separate checkout of the retained source baseline and a
separate environment, retaining the complete backup. Do not use destructive Git
cleanup on a checkout containing user data. The original OQS 0.14.1 artifact is
unavailable: rollback is not a promise that its Level 3 reader can be reconstructed.
Retain a known working historical environment if one exists; obtain real historical
fixtures before declaring compatibility. The research pair is not silent migration.

No encrypted recovery, account vault or full storage redesign is implemented here.
Those require later milestone design and migration tests. Nothing in rollback
instructions approves the historical prototype for confidential use.
