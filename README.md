# QuMail 1.0 — development prototype

QuMail is being evolved into its first proper 1.0 release. **This checkout is not
production-ready and must not be used for confidential communication.** The
existing desktop, SMTP/IMAP and custom encryption paths are retained for development
and migration testing. Passing legacy round trips does not establish secure email.

The primary engineering reference is the root-level
`QuMail-1.0-Research-Audit-Specification.md` supplied with this workspace. The PDF
is a presentation/reference copy; the Markdown is canonical.
[Implementation status](IMPLEMENTATION_STATUS.md) tracks requirements, findings,
validation and remaining gates. Historical “v2” plans are superseded by this 1.0 work.

## Current security boundary

- The key service is a **development CSPRNG simulator**, with a custom unauthenticated
  API. It is not real QKD or an ETSI-conformant KME. Keys vanish on restart.
- Legacy XOR has no integrity protection. AES-GCM protects body bytes but does not
  authenticate sender identity or the custom dispatch metadata.
- Legacy ML-KEM creates a private key at the sender. Independent recipient-owned
  keys, trusted discovery, signatures and standard OpenPGP mail are not implemented.
- The legacy portal stores the private key and decrypts on the server. Its operator
  can read content. Link consumption does not erase keys, backups or recipient copies.
- SMTP currently precedes key/portal/record persistence. A later failure can occur
  after acceptance. Check before retrying; delivery and decryption are not confirmed.
- Local token wrapping keys are files beside encrypted data. Windows ACL protection,
  account-scoped vaults and encrypted recovery are pending.
- From, To, Subject, routing, timing and size remain exposed. Local JSON/PDF records
  are unsigned and editable; recipient hashes are guessable, not anonymization.

The custom `application/qumail-pgp` format is **not OpenPGP/PGP-MIME**. There is no
blanket quantum-security, endpoint-only E2EE, FIPS validation, forward-secrecy,
post-compromise-security, self-destruction or production-support claim.

## Reproducible development setup

Initial validation target: **CPython 3.12 / Windows x64**. Exact local runtime:
3.12.14. Hosted Windows 2022 and Ubuntu 24.04 research validation passed for
commit `023c941ec2ef284f6be28b5a9605f1dca9c28787`, with 37 tests in each of
three orders on each platform. See [support and dependencies](docs/operations/dependencies.md)
and [exact hosted evidence](docs/operations/m1-validation.md#hosted-validation-completed-2026-10-03).

Create a fresh virtual environment with your CPython 3.12 interpreter, then install
with hash verification:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install --require-hashes -r packaging/requirements-dev.lock
```

On Linux use `.venv/bin/python`. `requirements.txt` points to the smaller runtime
lock; development requirements also include pytest, legacy portal characterization,
the explicitly different OQS research binding and native build tools. The original
`liboqs-python==0.14.1` remains an unavailable provider blocker (ADR 002); this
research environment does not reproduce that original pin. Runtime-only installation
does not validate Level 3. No provider is downloaded or compiled by the application.

The entire test suite is required:

```powershell
$env:OQS_INSTALL_PATH = (Resolve-Path tmp/oqs-install).Path
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m pytest -q --test-order reverse
.venv\Scripts\python -m pytest -q --test-order 20261003
```

Build the pinned native research library first using
[the build instructions](docs/operations/native-research.md). Missing native
configuration is a failure in the full suite. For an explicitly partial portable
check, `python -m pytest -q -m "not native_crypto"` deselects native tests and prints
the count. It is not a full validation result. Unexpected skips/xfails fail the run.
Tests use temporary state and injected network adapters; no real accounts are needed.

## Running the prototype

```powershell
.venv\Scripts\python main.py
# Explicit laboratory opt-in, loopback only:
.venv\Scripts\python main.py --dev-simulator
```

Default startup does not start the key simulator. Legacy Level 1/2 experiments
need the opt-in simulator; ordinary secure sending is not available yet. The UI
labels the prototype and legacy modes. Use nonsensitive fixtures.

Mail sign-in is initiated in Settings, not automatically on startup. Gmail's
prototype reads a locally supplied Desktop OAuth client file at
`secrets/gmail_client_secret.json`. Yahoo reads `QUMAIL_YAHOO_CLIENT_ID` and
`QUMAIL_YAHOO_CLIENT_SECRET`. Neither credentials nor successful production provider
authorization are supplied by this repository. Typed mailbox identity is not yet
verified against the OAuth subject. Do not commit the `secrets/` or `certs/` directories.

The legacy portal and its obsolete Docker recipe are excluded from validated
builds and production deployment. The Docker recipe does not consume the new lock
layout or approved research native version and is not currently runnable as documented.
Do not grant a desktop cloud database credentials or expose
this server as an E2EE service. Relay redesign is conditional M7 work.

## Engineering references

- [Actual architecture and flows](ARCHITECTURE.md)
- [Claims and evidence](docs/security/claims.md)
- [M1 validation](docs/operations/m1-validation.md)
- [Migration and rollback](docs/migration/m1-preservation.md)
- [Architecture decisions](docs/adrs/001-m1-baseline-boundaries.md)

M1 establishes a reproducible, honestly labeled baseline. M2 freezes a complete
standard provider/profile with independent interoperability. Identity/vault (M3),
durable outbox (M4), protocol integration (M5), workflows (M6), conditional relay/QKD
(M7), and release assurance (M8) follow their documented gates.

No project redistribution license is present. Qt and dependency licensing, signed
platform builds, independent security review and release provenance remain gates;
public source visibility is not a license grant.
