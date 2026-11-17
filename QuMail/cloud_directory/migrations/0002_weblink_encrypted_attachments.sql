-- Development WebLink attachment transport.  All attachment content and
-- filenames are encrypted client-side before they reach D1.  Chunks stay
-- below D1's per-value limit and are addressed only by opaque random IDs.

CREATE TABLE IF NOT EXISTS weblink_attachments (
    link_id TEXT NOT NULL,
    attachment_id TEXT NOT NULL,
    encrypted_filename TEXT NOT NULL,
    filename_iv_b64 TEXT NOT NULL,
    plaintext_size INTEGER NOT NULL,
    chunk_count INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (link_id, attachment_id),
    FOREIGN KEY(link_id) REFERENCES weblinks(link_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS weblink_attachment_chunks (
    link_id TEXT NOT NULL,
    attachment_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    iv_b64 TEXT NOT NULL,
    ciphertext BLOB NOT NULL,
    PRIMARY KEY (link_id, attachment_id, chunk_index),
    FOREIGN KEY(link_id, attachment_id)
        REFERENCES weblink_attachments(link_id, attachment_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_weblink_attachment_chunks_link
    ON weblink_attachment_chunks(link_id, attachment_id, chunk_index);

-- A reveal or successful recipient OTP produces a short-lived opaque grant.
-- Only its SHA-256 hash is stored; the raw grant is returned to the viewer.
CREATE TABLE IF NOT EXISTS weblink_access_grants (
    grant_hash TEXT PRIMARY KEY,
    link_id TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    FOREIGN KEY(link_id) REFERENCES weblinks(link_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_weblink_access_grants_expiry
    ON weblink_access_grants(expires_at);
