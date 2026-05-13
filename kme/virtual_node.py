# kme/virtual_node.py — Simulated ETSI GS QKD 014 KME (Key Management Entity).
# Runs as a local Flask server. Drop-in interface: replace with live KME in v2.
# Exposes only the endpoints QuMail needs. Not a full ETSI 014 implementation.
# Do not import from ui/, transport/, or crypto/ here.

import os
import uuid
import json
import time
import logging
from datetime import datetime

from flask import Flask, jsonify, request

from core.config import KME_HOST, KME_PORT, KME_KEY_SIZE
from kme.key_models import QuantumKey, SAERecord

app = Flask(__name__)
_LOGGER = logging.getLogger(__name__)

# --- SAE registry persistence ---
# Registry is written to disk on every new registration and loaded on startup.
# This ensures QuMail endpoint detection survives virtual node restarts.
_REGISTRY_PATH: str = os.path.join("secrets", "sae_registry.json")

# --- In-memory SAE registry ---
# Maps email address → SAERecord. Populated from disk at module load time.
_sae_registry: dict[str, SAERecord] = {}

# --- In-memory issued key log ---
# Maps key_id → QuantumKey. For audit trail and key retrieval by recipient.
_issued_keys: dict[str, QuantumKey] = {}

# --- Simple per-IP rate limiting (v1 local safety guard) ---
_RATE_WINDOW_SECONDS = 60
_MAX_REQUESTS_PER_IP = 120
_RATE_HISTORY: dict[str, list[float]] = {}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_registry() -> None:
    """
    Populate _sae_registry from the JSON file on disk.
    Called once at module load. Silent on missing file (first run).
    Logs a warning if the file exists but cannot be parsed.
    """
    if not os.path.exists(_REGISTRY_PATH):
        return
    try:
        with open(_REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for email, record_data in data.items():
            _sae_registry[email] = SAERecord(
                sae_id=record_data["sae_id"],
                email=record_data["email"],
                active=record_data.get("active", True),
            )
        _LOGGER.info("KME: loaded %d SAE record(s) from disk.", len(_sae_registry))
    except Exception as exc:
        _LOGGER.warning("KME: could not load SAE registry from '%s': %s", _REGISTRY_PATH, exc)


def _save_registry() -> None:
    """
    Write the current _sae_registry to disk as JSON.
    Called after every successful new registration.
    Logs a warning on failure — does not raise, so the endpoint still returns 201.
    """
    try:
        os.makedirs(os.path.dirname(_REGISTRY_PATH), exist_ok=True)
        data = {
            email: {"sae_id": r.sae_id, "email": r.email, "active": r.active}
            for email, r in _sae_registry.items()
        }
        with open(_REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as exc:
        _LOGGER.warning("KME: could not save SAE registry to '%s': %s", _REGISTRY_PATH, exc)


# Load persisted registry before the Flask server starts accepting requests.
_load_registry()


def _generate_key_bytes(size_bits: int) -> bytes:
    """Generate cryptographically random key bytes using os.urandom.
    os.urandom is the correct source for simulating QKD-grade entropy in v1."""
    return os.urandom(size_bits // 8)


def _get_sae_by_email(email: str) -> SAERecord | None:
    return _sae_registry.get(email.lower())


def _is_rate_limited() -> bool:
    """Return True when caller exceeds per-minute request allowance."""
    ip = request.remote_addr or "unknown"
    now = time.time()
    cutoff = now - _RATE_WINDOW_SECONDS
    history = _RATE_HISTORY.get(ip, [])
    history = [t for t in history if t >= cutoff]
    if len(history) >= _MAX_REQUESTS_PER_IP:
        _RATE_HISTORY[ip] = history
        _LOGGER.warning("KME rate limit exceeded from ip=%s", ip)
        return True
    history.append(now)
    _RATE_HISTORY[ip] = history
    return False


# ---------------------------------------------------------------------------
# ETSI GS QKD 014 — Key Request Endpoint
# POST /api/v1/keys
# ---------------------------------------------------------------------------

@app.route("/api/v1/keys", methods=["POST"])
def request_key():
    if _is_rate_limited():
        return jsonify({"error": "Too many requests. Slow down and retry."}), 429

    """
    Request a new quantum key for a given SAE ID.
    Body (JSON): { "sae_id": str, "key_size": int (bits, optional) }
    Returns:     { key_id, key_value (hex), sae_id, issued_at }
    """
    data = request.get_json(silent=True)
    if not data or "sae_id" not in data:
        return jsonify({"error": "Missing sae_id in request body"}), 400

    sae_id   = data["sae_id"]
    key_size = data.get("key_size", KME_KEY_SIZE)

    # Allow variable key sizes for Level 1 OTP (must match plaintext length).
    # Enforce a floor (128 bits) and ceiling (64 KB) for safety.
    if not isinstance(key_size, int) or key_size < 128 or key_size > 524288 or key_size % 8 != 0:
        return jsonify({"error": "key_size must be a multiple of 8 bits between 128 and 524288"}), 400

    key = QuantumKey(
        key_id=    str(uuid.uuid4()),
        key_value= _generate_key_bytes(key_size),
        sae_id=    sae_id,
        issued_at= datetime.utcnow().isoformat(),
    )

    _issued_keys[key.key_id] = key
    return jsonify(key.to_dict()), 200


# ---------------------------------------------------------------------------
# ETSI GS QKD 014 — Key Retrieval by ID (for recipient-side decryption)
# GET /api/v1/keys/<key_id>
# ---------------------------------------------------------------------------

@app.route("/api/v1/keys/<key_id>", methods=["GET"])
def retrieve_key(key_id: str):
    if _is_rate_limited():
        return jsonify({"error": "Too many requests. Slow down and retry."}), 429

    """
    Retrieve a previously issued key by its UUID.
    Used by the recipient's QuMail instance to obtain the key for decryption.
    """
    key = _issued_keys.get(key_id)
    if not key:
        return jsonify({"error": "Key not found"}), 404
    return jsonify(key.to_dict()), 200


# ---------------------------------------------------------------------------
# SAE Registry — Register a new SAE (QuMail user)
# POST /api/v1/sae/register
# ---------------------------------------------------------------------------

@app.route("/api/v1/sae/register", methods=["POST"])
def register_sae():
    if _is_rate_limited():
        return jsonify({"error": "Too many requests. Slow down and retry."}), 429

    """
    Register an email address as a QuMail SAE.
    Body (JSON): { "email": str }
    Returns:     { sae_id, email, active }
    """
    data = request.get_json(silent=True)
    if not data or "email" not in data:
        return jsonify({"error": "Missing email in request body"}), 400

    email = data["email"].lower()
    if email in _sae_registry:
        existing = _sae_registry[email]
        return jsonify({"sae_id": existing.sae_id, "email": existing.email, "active": existing.active}), 200

    record = SAERecord(sae_id=str(uuid.uuid4()), email=email)
    _sae_registry[email] = record
    _save_registry()
    return jsonify({"sae_id": record.sae_id, "email": record.email, "active": record.active}), 201


# ---------------------------------------------------------------------------
# SAE Registry — Check if an email is a registered QuMail SAE
# GET /api/v1/sae/lookup?email=<email>
# ---------------------------------------------------------------------------

@app.route("/api/v1/sae/lookup", methods=["GET"])
def lookup_sae():
    if _is_rate_limited():
        return jsonify({"error": "Too many requests. Slow down and retry."}), 429

    """
    Check whether a recipient email is registered as a QuMail SAE.
    Used by transport/recipient_check.py to trigger TQR downgrade if needed.
    Returns: { "registered": bool, "sae_id": str | null }
    """
    email = request.args.get("email", "").lower()
    if not email:
        return jsonify({"error": "Missing email query parameter"}), 400

    record = _get_sae_by_email(email)
    if record and record.active:
        return jsonify({"registered": True, "sae_id": record.sae_id}), 200
    return jsonify({"registered": False, "sae_id": None}), 200


# ---------------------------------------------------------------------------
# Health Check
# GET /api/v1/status
# ---------------------------------------------------------------------------

@app.route("/api/v1/status", methods=["GET"])
def status():
    if _is_rate_limited():
        return jsonify({"error": "Too many requests. Slow down and retry."}), 429

    """Simple liveness check used by kme_client to confirm KME is reachable."""
    return jsonify({
        "status":       "online",
        "node":         "QuMail ETSI QKD 014 Virtual Node",
        "version":      "1.0.0",
        "sae_count":    len(_sae_registry),
        "keys_issued":  len(_issued_keys),
    }), 200


# ---------------------------------------------------------------------------
# Entry point — run only when executed directly, not when imported
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(host=KME_HOST, port=KME_PORT, debug=False)
