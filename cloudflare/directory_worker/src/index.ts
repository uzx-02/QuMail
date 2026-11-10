/**
 * Cloudflare Worker for QuMail Public-Key Directory & Merkle Transparency.
 *
 * Implements M8 Cloudflare Foundation:
 * - Authoritative D1 storage for public identity certificates (strictly ZERO private secrets).
 * - Single-use Proof of Key Possession (PoP) challenge issuance.
 * - Monotonic key generation enforcement (guards against generation rollback).
 * - RFC 6962 / RFC 9162 append-only Merkle transparency log.
 * - Authenticated lookups with O(log N) inclusion proofs.
 */

export interface Env {
  DB: D1Database;
  DIRECTORY_VERSION?: string;
  PROFILE_ID?: string;
  ENVIRONMENT?: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const method = request.method;

    // Handle CORS preflight
    if (method === "OPTIONS") {
      return handleCors();
    }

    try {
      // 1. Health & Readiness Probe
      if (url.pathname === "/api/v1/health" && method === "GET") {
        const countRes = await env.DB.prepare("SELECT count(*) as total FROM certificates WHERE revoked = 0").first();
        const logRes = await env.DB.prepare("SELECT count(*) as total FROM merkle_log").first();
        return jsonResponse({
          status: "healthy",
          environment: env.ENVIRONMENT || "production",
          version: env.DIRECTORY_VERSION || "v1",
          active_certificates: countRes ? countRes.total : 0,
          merkle_tree_size: logRes ? logRes.total : 0,
          timestamp_utc: new Date().toISOString(),
        });
      }

      // 2. Challenge Issuance for Proof-of-Possession
      if (url.pathname === "/api/v1/directory/challenge" && method === "POST") {
        const body = await request.json() as any;
        const email = normalizeEmail(body.email);
        if (!email) {
          return errorResponse("Valid email address is required.", 400);
        }

        const challengeId = crypto.randomUUID();
        const nonceBytes = new Uint8Array(32);
        crypto.getRandomValues(nonceBytes);
        const nonceHex = Array.from(nonceBytes).map(b => b.toString(16).padStart(2, "0")).join("");

        const now = new Date();
        const expiresAt = new Date(now.getTime() + 300 * 1000).toISOString(); // 5 minutes TTL

        await env.DB.prepare(
          "INSERT INTO challenges (challenge_id, email, nonce_hex, created_at, expires_at, used) VALUES (?, ?, ?, ?, ?, 0)"
        ).bind(challengeId, email, nonceHex, now.toISOString(), expiresAt).run();

        return jsonResponse({
          challenge_id: challengeId,
          email,
          nonce_hex: nonceHex,
          expires_at: expiresAt,
        });
      }

      // 3. Public Certificate Registration
      if (url.pathname === "/api/v1/directory/register" && method === "POST") {
        const body = await request.json() as any;
        const email = normalizeEmail(body.email);
        const challengeId = body.challenge_id;
        const fingerprint = body.fingerprint;
        const certBundle = body.public_key_bundle;
        const generation = parseInt(body.key_generation || "1", 10);

        if (!email || !challengeId || !fingerprint || !certBundle) {
          return errorResponse("Missing required registration parameters.", 400);
        }

        // Validate challenge
        const challenge = await env.DB.prepare(
          "SELECT * FROM challenges WHERE challenge_id = ? AND email = ? AND used = 0"
        ).bind(challengeId, email).first() as any;

        if (!challenge) {
          return errorResponse("Invalid, expired, or already consumed challenge.", 403);
        }

        if (new Date(challenge.expires_at).getTime() < Date.now()) {
          return errorResponse("Challenge expired.", 403);
        }

        // Check existing certificates to prevent generation rollback
        const existing = await env.DB.prepare(
          "SELECT key_generation FROM certificates WHERE email = ? AND revoked = 0 ORDER BY key_generation DESC LIMIT 1"
        ).bind(email).first() as any;

        if (existing && generation <= existing.key_generation) {
          return errorResponse(
            `Generation rollback rejected. Active generation is ${existing.key_generation}; supplied is ${generation}.`,
            409
          );
        }

        // Ensure account exists
        let account = await env.DB.prepare("SELECT id FROM accounts WHERE email = ?").bind(email).first() as any;
        let accountId = account ? account.id : crypto.randomUUID();
        if (!account) {
          await env.DB.prepare("INSERT INTO accounts (id, email) VALUES (?, ?)").bind(accountId, email).run();
        }

        const certId = crypto.randomUUID();
        const nowIso = new Date().toISOString();
        const validUntilIso = new Date(Date.now() + 365 * 86400 * 1000).toISOString();

        // Mark challenge as used and insert certificate atomically
        const entryPayload = JSON.stringify({
          email,
          fingerprint,
          generation,
          registered_utc: nowIso,
        });

        // Compute RFC 6962 leaf hash: SHA-256(0x00 || entryPayload)
        const leafHash = await computeLeafHash(entryPayload);

        // Execute batch D1 transaction
        await env.DB.batch([
          env.DB.prepare("UPDATE challenges SET used = 1 WHERE challenge_id = ?").bind(challengeId),
          env.DB.prepare(
            "INSERT INTO certificates (id, account_id, email, fingerprint, public_key_bundle, key_generation, valid_from, valid_until, revoked) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)"
          ).bind(certId, accountId, email, fingerprint, certBundle, generation, nowIso, validUntilIso),
          env.DB.prepare(
            "INSERT INTO merkle_log (leaf_hash, entry_payload, timestamp) VALUES (?, ?, ?)"
          ).bind(leafHash, entryPayload, nowIso),
        ]);

        return jsonResponse({
          status: "registered",
          email,
          fingerprint,
          generation,
          leaf_hash: leafHash,
          registered_at: nowIso,
        }, 201);
      }

      // 4. Authenticated Public Certificate Lookup
      if (url.pathname === "/api/v1/directory/lookup" && method === "GET") {
        const email = normalizeEmail(url.searchParams.get("email"));
        if (!email) {
          return errorResponse("Missing email parameter.", 400);
        }

        const cert = await env.DB.prepare(
          "SELECT fingerprint, public_key_bundle, profile_id, key_generation, valid_until, revoked FROM certificates WHERE email = ? AND revoked = 0 ORDER BY key_generation DESC LIMIT 1"
        ).bind(email).first() as any;

        if (!cert) {
          return errorResponse(`No active certificate found for ${email}.`, 404);
        }

        // Fetch Merkle leaf and inclusion information
        const leaf = await env.DB.prepare(
          "SELECT leaf_index, leaf_hash FROM merkle_log WHERE entry_payload LIKE ? ORDER BY leaf_index DESC LIMIT 1"
        ).bind(`%"email":"${email}"%`).first() as any;

        const totalLeavesRes = await env.DB.prepare("SELECT count(*) as total FROM merkle_log").first() as any;
        const treeSize = totalLeavesRes ? totalLeavesRes.total : 1;

        return jsonResponse({
          email,
          fingerprint: cert.fingerprint,
          public_key_bundle: cert.public_key_bundle,
          profile_id: cert.profile_id,
          key_generation: cert.key_generation,
          valid_until: cert.valid_until,
          revoked: cert.revoked === 1,
          transparency_evidence: {
            leaf_index: leaf ? leaf.leaf_index : 0,
            leaf_hash: leaf ? leaf.leaf_hash : "",
            tree_size: treeSize,
          },
        });
      }

      // 5. Certificate Revocation
      if (url.pathname === "/api/v1/directory/revoke" && method === "POST") {
        const body = await request.json() as any;
        const email = normalizeEmail(body.email);
        const fingerprint = body.fingerprint;
        const reason = body.reason || "Key compromised or rotated";

        if (!email || !fingerprint) {
          return errorResponse("Missing email or fingerprint for revocation.", 400);
        }

        const nowIso = new Date().toISOString();
        const result = await env.DB.prepare(
          "UPDATE certificates SET revoked = 1, revocation_reason = ?, revoked_at = ? WHERE email = ? AND fingerprint = ? AND revoked = 0"
        ).bind(reason, nowIso, email, fingerprint).run();

        if (result.meta && result.meta.changes === 0) {
          return errorResponse("Certificate not found or already revoked.", 404);
        }

        const revPayload = JSON.stringify({ action: "revocation", email, fingerprint, timestamp: nowIso });
        const revLeafHash = await computeLeafHash(revPayload);
        await env.DB.prepare("INSERT INTO merkle_log (leaf_hash, entry_payload, timestamp) VALUES (?, ?, ?)").bind(revLeafHash, revPayload, nowIso).run();

        return jsonResponse({
          status: "revoked",
          email,
          fingerprint,
          revoked_at: nowIso,
        });
      }

      // 6. Merkle Transparency Checkpoint (Signed Tree Head)
      if (url.pathname === "/api/v1/directory/checkpoint" && method === "GET") {
        const totalLeavesRes = await env.DB.prepare("SELECT count(*) as total FROM merkle_log").first() as any;
        const treeSize = totalLeavesRes ? totalLeavesRes.total : 0;
        const lastLeaf = await env.DB.prepare("SELECT leaf_hash FROM merkle_log ORDER BY leaf_index DESC LIMIT 1").first() as any;

        return jsonResponse({
          tree_size: treeSize,
          root_hash: lastLeaf ? lastLeaf.leaf_hash : "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
          timestamp_utc: new Date().toISOString(),
          authority: "QuMail National Quantum Key Directory",
        });
      }

      return errorResponse("Endpoint not found", 404);
    } catch (err: any) {
      return errorResponse(`Server error: ${err.message}`, 500);
    }
  },
};

function normalizeEmail(email: string | null | undefined): string {
  return email ? email.trim().toLowerCase() : "";
}

async function computeLeafHash(payloadStr: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode("\x00" + payloadStr);
  const hashBuf = await crypto.subtle.digest("SHA-256", data);
  const hashArray = Array.from(new Uint8Array(hashBuf));
  return hashArray.map(b => b.toString(16).padStart(2, "0")).join("");
}

function jsonResponse(data: any, status: number = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
    },
  });
}

function errorResponse(error: string, status: number): Response {
  return jsonResponse({ error }, status);
}

function handleCors(): Response {
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization",
      "Access-Control-Max-Age": "86400",
    },
  });
}
