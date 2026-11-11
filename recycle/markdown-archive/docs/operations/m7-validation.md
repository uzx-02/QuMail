# Handover provenance clarification — 2026-11-01

The final hash-identified source below was committed as
`18174e1b8c0ce276aa294275e195b2e54c498075`, parent `8eebb5e…`.
Current source HEAD `4e429a43a6d9ae7fe6bb45c4ae5a8dcb6200e6b0` adds only launcher/docs;
all 17 source inputs and the M5 native hash were rechecked at handover with zero
mismatches. No runtime suite was rerun for this documentation-only task. Earlier
“uncommitted” wording describes when the logs were generated, not present Git state.

M7 remains locally qualified, cloud explicitly outside scope, independent review
pending before production/security release. Google live acceptance remains incomplete;
see [actual desktop/Google record](m6-google-acceptance.md). The
[handover](../../AI_HANDOVER.md) and [roadmap](../handover/STATUS_AND_ROADMAP.md)
identify the interrupted launcher task; no relay implementation changes were made.

## Preserved validation record

# M7 local relay validation — 2026-10-23

Starting checkpoint: `8eebb5eb7834caa230795c7ca9b446c631df6247`.
Local branch: `codex/m7-relay-google-acceptance`. Evidence below describes the
uncommitted working-tree inputs in [the hash manifest](evidence/m7/checkpoint-input-hashes.json),
not unchanged HEAD. No push, migration, deployment, provider/dependency upgrade
or QKD work. Earlier M1/M2/M6 evidence and the reviewer draft remain unchanged.

## Acceptance assessment

| Canonical requirement | Actual evidence | Disposition |
|---|---|---|
| §54 M7 approved optional scope; QM-PORTAL-001/002, I01 | Separate `services/relay`; actual frozen M5 ciphertext; no legacy portal/decrypt API, endpoint keys/Google tokens absent in backend snapshot | Local engineering satisfied; production authorization not implied |
| Authenticated upload, recipient/device authorization, own audience | Real loopback mTLS; exact public-cert allowlist; unknown cert/no cert/Google-style bearer denied; recipient principal/device checked transactionally | Local qualified; production enrollment/PKI review pending |
| I10/T10 one initial lease across instances | 128 competing requests, eight Windows processes and independent SQLite connections: one lease, 127 denied; exact winner retry succeeds | Satisfied for single-host SQLite; not cloud evidence |
| Expiry during contention/transaction, bounded retry, ACK | Fake-clock boundary tests after lock and before lease publication, <=300 seconds/object expiry; wrong device/key denied; concurrent download/ACK, repeated ACK, restart, no download after completion | Local satisfied; bytes already downloaded cannot be revoked |
| Quotas, durable readiness/outage, I12 | Active global/principal byte/object limits, tombstone cap; lost DB returns 503; no new empty store/fallback; actual Windows open-handle bug corrected | Local satisfied |
| Bounded API resources | Header/body/duplicate JSON/duplicate length checks, 16 admitted handlers, whole-connection five-second deadline; slow client closes in tested 4–7 second range | Local satisfied, not universal OS/DoS assurance |
| Ciphertext integrity remains endpoint responsibility | Real recipient decrypt/signature/trust/attachment and sender archive; altered encrypted data in syntactically valid MIME rejected locally without plaintext result or ACK | Satisfied with existing M5 provider; independent MIME peer gate unchanged |
| Account/cancellation boundaries | Original lease/context enforced; current trust/frozen bytes rechecked; late upload response suppressed after switching; actual committed object discoverable through same original owner/key | Local satisfied; cancellation does not undo remote commit |
| Retention/deletion transparency | Consumed/expired primary payload NULL; deny at expiry; one-second sweeper, opaque tombstones retained with caps | Local logical/primary-row deletion tested; WAL/backup forensic erasure not claimed |
| Backend API/IAM/deployment, real infrastructure access | Local API and explicit operator CLI implemented. No cloud backend/access supplied or configured; no public service deployed | Outside this workstream per explicit user scope; no cloud claims or fabricated IAM/deployment evidence |
| Independent backend/identity review | ADR 009 records assumptions and unanswered production questions | Pending; passing tests/self-inspection are not approval |
| QKD T11 and hardware evidence | QKD lane excluded; no custom combiner or simulator provenance changes | Not applicable to approved relay-only scope |

M7 is **locally qualified** at this bounded development scope. The user explicitly
selected local-only qualification on 2026-10-23; cloud deployment is outside scope,
not an implementation blocker. Independent backend/identity approval remains
pending before production enablement/security release; none is claimed. Ordinary mail remains independent. Development exceptions do not remove
release, licensing, native assurance or historical compatibility gates.

## Final checkpoint validation — 2026-11-01

Final working-tree source/input hashes are in
[checkpoint-input-hashes.json](evidence/m7/checkpoint-input-hashes.json).
The same combined command below now reports **163 passed in 122.39 seconds**:
13 M7, 96 M6 and 54 M3 tests; zero skips/warnings. The exact reverse run of all
13 M7 + 14 OAuth diagnostic cases reports **27 passed in 29.42 seconds**;
its 27 distinct IDs exactly match the targeted subset of the normal run.
[Full normal output](evidence/m7/checkpoint-normal.txt),
[reverse output](evidence/m7/checkpoint-reverse.txt),
[exact commands](evidence/m7/checkpoint-commands.json),
[node IDs](evidence/m7/checkpoint-nodeids.txt).

Final review added a meaningful upload check: the bridge compares the envelope
with its exact persisted outbox bytes and rechecks current account/key/contact
policy before network dispatch. A changed contact and altered frozen bytes are
rejected without creating a relay object. Three affected relay cases passed
before the complete run. Google live findings led to fixed verifier reason codes
and a <=20-second cancellable not-yet-valid-token wait; full maintained-library
signature/audience/time verification repeats unchanged, with no clock-skew
allowance. Expiry/signature failures are not retried. Fourteen synthetic diagnostic
cases test these behaviors; they are not live Google evidence.

The owner requested manual Google testing on 2026-11-01. Use
[manual acceptance](google-manual-acceptance.md); the reported possible A
success still requires explicit confirmation in the app. No real send was
performed by the agent. Earlier milestone evidence remains intact.

## Earlier executed results (preserved, superseded for final source hashes)

Windows 11 build 26200 x64, Python 3.12.14 (MSVC 1944), pytest 8.4.2, PyQt 6.10.2,
cryptography 50.0.2, google-auth 2.49.1, google-auth-oauthlib 1.3.0, SQLite 3.53.1,
Python TLS OpenSSL 3.5.8. Existing native M5 Sequoia 2.4.1/OpenSSL 3.5.9 helper
was reused unchanged; its SHA-256 is retained in the manifest. No build/upgrade.

Commands from repository root, with disposable Windows Credential Manager
access and loopback sockets (no Google traffic in these tests):

```powershell
./.venv-m1-clean/Scripts/python.exe -m pytest experiments/m7 experiments/m6 experiments/m3/tests -q -rA
```

**153 passed in 95.92 seconds**, zero skips/warnings: 11 then-current M7 cases,
88 M6 cases (including six new sanitized OAuth diagnostics), 54 M3 regressions.
This preceded addition of the one ciphertext-tamper case; no application source
changed afterwards. That additional focused case passed in 2.81 seconds.

Earlier collection and order runs:

```powershell
./.venv-m1-clean/Scripts/python.exe -m pytest experiments/m7 experiments/m6/test_google_diagnostics.py --collect-only -q
# Historical argv description: python -m pytest -q -rA followed by final-nodeids.txt in listed order
# Historical argv description: the same node IDs in reverse order (not literal angle-bracket arguments)
```

Earlier normal: **18 passed in 25.85 seconds**. Exact reverse: **18 passed in
24.16 seconds**. Same 18 distinct IDs, zero skips/warnings. Included all 12 then-current
M7 cases, real tamper rejection and six OAuth diagnostic tests. Retained full
commands/IDs and outputs: [evidence directory](evidence/m7).

Initial failures are retained, not hidden: wrong result-field name in new test
(`trust` vs existing `identity_trust`), Windows file rename racing the cleanup
worker, and SQLite initialization not explicitly closing its connection.
Stopped the cleanup worker before the intentional outage injection and fixed
the actual connection lifecycle; no assertion weakening or skip.

## Live Google distinction

See [the actual Google acceptance record](m6-google-acceptance.md). Local tests
use synthetic identity/authorization fixtures, not Google accounts. Live browser
completion initially reached the callback but identity verification failed;
fixed enum-only stage reporting now identifies this without logging provider
payloads. No verification checks were removed. The owner confirmed Windows clock
synchronization before the resumed real authorization attempt. These events do
not constitute successful enrollment/refresh/SMTP evidence by themselves.
