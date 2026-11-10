-- =====================================================================
-- Cloudflare D1 Relational Schema for QuMail Public-Key Directory
-- Authoritative, Transactional Storage for Public Key Bundles & Transparency
-- =====================================================================

-- 1. Accounts Table (Normalized Email Identifiers)
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_accounts_email ON accounts(email);

-- 2. Certificates Table (Public Key Bundles, strictly ZERO private material)
CREATE TABLE IF NOT EXISTS certificates (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    fingerprint TEXT UNIQUE NOT NULL,
    public_key_bundle TEXT NOT NULL,
    profile_id TEXT NOT NULL DEFAULT 'QM-OPENPGP-PQ-v1',
    key_generation INTEGER NOT NULL DEFAULT 1,
    valid_from TEXT NOT NULL,
    valid_until TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0,
    revocation_reason TEXT,
    revoked_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_certs_email ON certificates(email);
CREATE INDEX IF NOT EXISTS idx_certs_fingerprint ON certificates(fingerprint);
CREATE INDEX IF NOT EXISTS idx_certs_active ON certificates(email, revoked);

-- 3. Ephemeral Single-Use Challenges (Proof-of-Possession Binding)
CREATE TABLE IF NOT EXISTS challenges (
    challenge_id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    nonce_hex TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL,
    used INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_challenges_lookup ON challenges(challenge_id, used);

-- 4. Merkle Transparency Log (RFC 6962 / RFC 9162 Append-Only Audit Trail)
CREATE TABLE IF NOT EXISTS merkle_log (
    leaf_index INTEGER PRIMARY KEY AUTOINCREMENT,
    leaf_hash TEXT NOT NULL,
    entry_payload TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_merkle_leaf_index ON merkle_log(leaf_index);
