# QuMail Cloudflare Public-Key Directory & Merkle Transparency Foundation

This directory contains the production-ready **Cloudflare Worker** and **Cloudflare D1** implementation for QuMail's globally distributed, highly available Public-Key Directory.

---

## 1. Architectural Blueprint

```
+-------------------------------------------------------------------------------+
|                      CLOUDFLARE PUBLIC-KEY DIRECTORY                          |
+-------------------------------------------------------------------------------+
|                                                                               |
|   [ Desktop / Android QuMail Clients ]                                        |
|                     |                                                         |
|                     | HTTPS (TLS 1.3 / Strict Hostname Verification)          |
|                     v                                                         |
|   [ Cloudflare Global Edge Network (Anycast) ]                                |
|   - DDOS Protection & Global CDN Edge Caching                                 |
|   - Automated TLS Certificate Lifecycle                                       |
|                     |                                                         |
|                     v                                                         |
|   [ Cloudflare Worker Runtime (src/index.ts) ]                                |
|   - Proof of Key Possession (PoP) Verification                                |
|   - Monotonic Key Generation Guard (Anti-Rollback)                            |
|   - Single-use 256-bit Challenge Issuance ($N_{chal}$)                       |
|   - RFC 6962 / RFC 9162 Merkle Tree Hash Computation                         |
|                     |                                                         |
|                     v                                                         |
|   [ Cloudflare D1 Relational Database (schema.sql) ]                          |
|   - Authoritative SQLite-compatible globally distributed relational store     |
|   - Tables: accounts, certificates, challenges, merkle_log                    |
|   - Zero Private Keys · Zero Vault Passwords · Zero Plaintext Storage         |
|                                                                               |
+-------------------------------------------------------------------------------+
```

---

## 2. D1 Relational Schema

The directory schema (`schema.sql`) enforces strict transactional integrity:
- `accounts`: Maps normalized email addresses to unique account IDs.
- `certificates`: Stores public key bundles, fingerprints, profile versions (`QM-OPENPGP-PQ-v1`), monotonically increasing key generations, and revocation timestamps.
- `challenges`: Ephemeral single-use 256-bit challenge nonces expiring after 300 seconds (5 minutes).
- `merkle_log`: Append-only audit trail calculating RFC 6962 leaf hashes:
  $$\text{LeafHash} = \text{SHA-256}(0\text{x}00 \parallel \text{EntryPayload})$$

---

## 3. Deployment Instructions

### Prerequisites
- Node.js (v18+) and npm.
- Cloudflare Account with Workers and D1 enabled.

### Steps to Deploy
```bash
# 1. Install dependencies
cd cloudflare/directory_worker
npm install

# 2. Authenticate with Cloudflare
npx wrangler login

# 3. Create the D1 Database (Staging or Production)
npx wrangler d1 create qumail-directory-db

# 4. Copy the generated database_id into wrangler.toml:
# [[d1_databases]]
# binding = "DB"
# database_name = "qumail-directory-db"
# database_id = "<YOUR_DATABASE_ID>"

# 5. Apply the initial schema migration
npx wrangler d1 execute qumail-directory-db --file=./schema.sql

# 6. Deploy the Worker to Cloudflare Global Edge
npx wrangler deploy
```

---

## 4. Operational Maintenance, Backup & Cost Model

### Backup & Disaster Recovery
To create an immutable offline snapshot of the directory database:
```bash
npx wrangler d1 export qumail-directory-db --output=qumail_directory_backup_$(date +%Y%m%d).sql
```

### Cost Assumptions
- **Cloudflare Free Tier:** Covers **100,000 requests/day**, 5GB D1 storage, and unlimited edge bandwidth at **$0.00 / month**. Ideal for the Aavishkar demonstration and university deployment.
- **Cloudflare Workers Paid ($5.00 / month):** Unlocks 10 million requests/month, 25GB D1 storage, and sub-millisecond cold starts for commercial enterprise rollout.

### Data Visibility & Threat Boundary
- **Public Key Material Only:** The directory never receives or stores private keys, session tokens, master passwords, or unencrypted emails.
- **Provider Metadata Visibility:** In accordance with standard HTTPS routing, Cloudflare's edge infrastructure observes the client IP and queried email address. For high-security environments requiring zero directory query visibility, the QuMail desktop client supports local cached offline directory bundles and TOFU key pinning.
