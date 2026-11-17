-- Apply once to existing D1 databases before deploying the identity-bound
-- directory Worker. Existing rows remain unbound until a verified
-- re-enrollment binds their pre-existing device history in place.

ALTER TABLE accounts ADD COLUMN google_binding_id TEXT;
ALTER TABLE accounts ADD COLUMN qumail_identity_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_google_binding
    ON accounts(google_binding_id) WHERE google_binding_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_qumail_identity
    ON accounts(qumail_identity_id) WHERE qumail_identity_id IS NOT NULL;

ALTER TABLE sessions ADD COLUMN scope TEXT;

CREATE TABLE IF NOT EXISTS directory_nonces (
    nonce_hash TEXT PRIMARY KEY,
    expires_at INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_directory_nonces_expiry ON directory_nonces(expires_at);

CREATE TABLE IF NOT EXISTS directory_lookup_limits (
    requester_id TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_directory_lookup_limits_requester
    ON directory_lookup_limits(requester_id, created_at);
