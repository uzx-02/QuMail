-- Baseline for a fresh QuMail directory database.
--
-- The original production database was initialized outside Wrangler's
-- migration ledger. Keep this baseline structurally compatible with that
-- legacy database, including the WebLink OTP columns already used by the
-- Worker. 0001_identity_bound_sessions.sql upgrades it to the current
-- identity-bound directory model.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,
    auth_provider TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS devices (
    device_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    device_label TEXT NOT NULL,
    fingerprint TEXT NOT NULL UNIQUE,
    public_key_bundle TEXT NOT NULL,
    key_generation INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(account_id) REFERENCES accounts(account_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_devices_account ON devices(account_id, revoked);

CREATE TABLE IF NOT EXISTS sessions (
    session_token_hash TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    FOREIGN KEY(account_id) REFERENCES accounts(account_id) ON DELETE CASCADE,
    FOREIGN KEY(device_id) REFERENCES devices(device_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS email_challenges (
    challenge_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    otp_hash TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    expires_at INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    challenge_salt TEXT,
    challenge_type TEXT NOT NULL DEFAULT 'custom_mailbox'
);
CREATE INDEX IF NOT EXISTS idx_challenges_expiry ON email_challenges(expires_at);

CREATE TABLE IF NOT EXISTS tombstones (
    fingerprint_hash TEXT PRIMARY KEY,
    revoked_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tombstones_expiry ON tombstones(expires_at);

CREATE TABLE IF NOT EXISTS weblinks (
    link_id TEXT PRIMARY KEY,
    sender_account_id TEXT,
    encrypted_payload TEXT NOT NULL,
    iv_hex TEXT NOT NULL,
    has_passcode INTEGER NOT NULL DEFAULT 0,
    passcode_hash TEXT,
    passcode_salt_hex TEXT,
    failed_passcode_attempts INTEGER NOT NULL DEFAULT 0,
    lockout_until INTEGER NOT NULL DEFAULT 0,
    max_views INTEGER NOT NULL DEFAULT 5,
    view_count INTEGER NOT NULL DEFAULT 0,
    burn_after_read INTEGER NOT NULL DEFAULT 0,
    expires_at INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    is_burned INTEGER NOT NULL DEFAULT 0,
    recipient_email_hash TEXT,
    recipient_email_salt TEXT,
    has_email_otp INTEGER NOT NULL DEFAULT 0,
    otp_verified INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_weblinks_expiry ON weblinks(expires_at);
