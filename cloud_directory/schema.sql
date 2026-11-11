-- ============================================================================
-- QuMail Cloud Directory & WebLink Gateway — D1 SQL Schema (v1.0)
-- Strict zero-plaintext-email architecture with foreign keys & cascades.
-- ============================================================================

PRAGMA foreign_keys = ON;

-- 1. Accounts Table (Strictly zero plaintext emails)
CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,               -- HMAC-SHA256(normalized_email, PEPPER)
    auth_provider TEXT NOT NULL,               -- 'google' or 'custom'
    created_at INTEGER NOT NULL,               -- Unix epoch timestamp (seconds)
    updated_at INTEGER NOT NULL
);

-- 2. Device Certificates Table
CREATE TABLE IF NOT EXISTS devices (
    device_id TEXT PRIMARY KEY,                -- Client-generated UUIDv4
    account_id TEXT NOT NULL,                  -- Foreign key to accounts
    device_label TEXT NOT NULL,                -- e.g. "Work Laptop (Windows 11)"
    fingerprint TEXT NOT NULL UNIQUE,          -- SHA-256 of ML-DSA-65 public key (hex)
    public_key_bundle TEXT NOT NULL,           -- JSON: { kem_public_base64, dsa_public_base64 }
    key_generation INTEGER NOT NULL DEFAULT 1, -- Monotonically increasing counter
    created_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(account_id) REFERENCES accounts(account_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_devices_account ON devices(account_id, revoked);

-- 3. Opaque Session Tokens
CREATE TABLE IF NOT EXISTS sessions (
    session_token_hash TEXT PRIMARY KEY,       -- SHA-256 of raw opaque bearer token
    account_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    FOREIGN KEY(account_id) REFERENCES accounts(account_id) ON DELETE CASCADE,
    FOREIGN KEY(device_id) REFERENCES devices(device_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);

-- 4. Email OTP Challenges (Custom Mailbox Verification)
CREATE TABLE IF NOT EXISTS email_challenges (
    challenge_id TEXT PRIMARY KEY,             -- Cryptographically random UUIDv4
    account_id TEXT NOT NULL,                  -- HMAC-SHA256(normalized_email, PEPPER)
    otp_hash TEXT NOT NULL,                    -- HMAC-SHA256(otp_code, PEPPER)
    attempts INTEGER NOT NULL DEFAULT 0,       -- Maximum 3 attempts
    expires_at INTEGER NOT NULL,               -- 5-minute TTL
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_challenges_expiry ON email_challenges(expires_at);

-- 5. Tombstones Table (90-day retention of revoked fingerprints to block replay)
CREATE TABLE IF NOT EXISTS tombstones (
    fingerprint_hash TEXT PRIMARY KEY,         -- SHA-256(fingerprint)
    revoked_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL                -- Retained for 90 days
);
CREATE INDEX IF NOT EXISTS idx_tombstones_expiry ON tombstones(expires_at);

-- 6. Ephemeral WebLinks Table (Pillar 2)
CREATE TABLE IF NOT EXISTS weblinks (
    link_id TEXT PRIMARY KEY,                  -- Random URL-safe identifier
    sender_account_id TEXT,                    -- Optional HMAC of sender
    encrypted_payload TEXT NOT NULL,           -- AES-256-GCM ciphertext (Base64, max 256 KB)
    iv_hex TEXT NOT NULL,                      -- 96-bit AES-GCM nonce (hex)
    has_passcode INTEGER NOT NULL DEFAULT 0,   -- 1 if passcode required, 0 if raw fragment
    passcode_hash TEXT,                        -- HMAC-SHA256(passcode_tag, PEPPER) or NULL
    passcode_salt_hex TEXT,                    -- Salt for client-side / server passcode verification
    failed_passcode_attempts INTEGER NOT NULL DEFAULT 0, -- Max 5 attempts
    lockout_until INTEGER NOT NULL DEFAULT 0,  -- Temporary cooldown timestamp (anti-griefing)
    max_views INTEGER NOT NULL DEFAULT 5,      -- View quota
    view_count INTEGER NOT NULL DEFAULT 0,     -- Increments only on explicit user Reveal click
    burn_after_read INTEGER NOT NULL DEFAULT 0,-- 1 if destroyed immediately on first reveal
    expires_at INTEGER NOT NULL,               -- Default: created_at + 7 days
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_weblinks_expiry ON weblinks(expires_at);
