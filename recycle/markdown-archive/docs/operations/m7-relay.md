# Local ciphertext relay operations

Development only. This service cannot bind a public address and is not started by
QuMail. It does not import the legacy portal or discover cloud/Google credentials.
Use the installed `.venv-m1-clean` environment; no new dependency is required.

## Reproduce qualification

```powershell
./.venv-m1-clean/Scripts/python.exe -m pytest experiments/m7 -q -rA
```

Tests create disposable M3 Windows-vault credentials, provider-generated M5
ciphertext and temporary relay-only TLS certificates. No fixture identities or
mail tokens are evidence of live Google acceptance. Private test keys/databases
must remain outside commits; pytest temporary directories are local test data.
Owned Windows Credential Manager entries are removed by the existing vault
fixture. Never bulk-delete credential entries or unrelated test directories.

## Explicit local service configuration

Use a NEW operator-selected local database path outside Git. Parent must exist:

```powershell
./.venv-m1-clean/Scripts/python.exe -m services.relay --database C:\chosen\relay.sqlite --create
./.venv-m1-clean/Scripts/python.exe -m services.relay --database C:\chosen\relay.sqlite --server-cert C:\chosen\server.pem --server-key C:\chosen\server.key --relay-client-ca C:\chosen\relay-client-ca.pem --registry C:\chosen\public-registry.json --port 8443
```

Files must be deliberately provisioned for this private service. Do not reuse a
Google token, general-purpose CA, desktop service-account credential or an
endpoint OpenPGP private key as transport authentication. Server certificate must
authenticate `127.0.0.1`. Client certificates require client-auth usage and exact
public-certificate SHA-256 allowlisting. Registry is a bounded JSON object:
each lowercase 64-hex certificate digest maps to exactly `principal` and `device`
(32 lowercase hex each, corresponding to the enrolled M3 context). Endpoint TLS
private keys stay with endpoints; server TLS key stays with the service.

Only loopback is supported. Registry changes require a controlled restart. On
shutdown, admitted requests may drain for their five-second connection budget
plus finite local storage handling; this is not a universal OS cancellation SLA.
Never put WAL on a network filesystem. Stop with Ctrl+C. A failed readiness check
must be fixed at the configured durable store, never by switching to memory.

## API and budgets

All operations require mTLS. JSON only; no `Authorization` header, redirects,
chunked request body or implicit user identity. Fixed error codes contain no
provider payloads. No access-log URLs, tokens or bodies are emitted.

| POST | Body | Meaning |
|---|---|---|
| `/v1/objects` | `key`, `recipient`, `ciphertext` (base64 frozen M5 wire), `ttl` | Upload for registered recipient; owner is authenticated certificate binding |
| `/v1/objects/{id}/leases` | `key` | One initial lease, device/request-bound |
| `/v1/objects/{id}/download` | `lease` | Same authorized lease retrieves frozen bytes |
| `/v1/objects/{id}/ack` | `lease` | Confirm completion; remove primary payload |

IDs/keys are random 128-bit lowercase-hex identifiers. Upload retries must retain
the exact owner, device, key, bytes, recipient and TTL. Conflict returns 409.
403 deliberately does not distinguish absent, expired and unauthorized objects.
429 denotes qualified limits; 503 means durable storage unavailable, with no
fallback. Connection loss or cancellation after dispatch may have committed;
investigate using the same idempotency key. Never infer rollback from lost reply.

Limits: 256 KiB frozen ciphertext, base64 request bound plus 4096 bytes metadata,
8192 bytes aggregate HTTP request line/headers, five-second whole connection,
16 admitted concurrent handlers, three-second SQLite writer wait. Active-object
quotas: 1024 global / 32 per principal, 16 MiB global / 2 MiB per principal.
Including tombstones: 10000 global / 256 per principal. These are conservative
development limits, not a benchmark or denial-of-service assurance claim.

Receiver uses `services.relay.client.Client` only with its original account lease,
then passes downloaded ciphertext to the existing M5 `OpenMessage` service with
the expected signer certificate and account key handle. Only a fully verified
result may be displayed/exported. ACK is explicit after successful verification;
failed verification must not be acknowledged as successful delivery. The relay
cannot prevent a malicious authorized recipient from saving/replaying ciphertext.
Ordinary Gmail compose/submission does not call the relay or depend on it.

Retention and trust limits, including WAL/backups and unavailable cloud evidence,
are normative for this development lane in [ADR 009](../adrs/009-m7-local-ciphertext-relay.md).
Current actual results: [M7 validation](m7-validation.md).
