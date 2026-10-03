# Current claims and finding disposition

Read the canonical Markdown specification for full F01–F19 findings. Tests marked
`characterization` deliberately confirm unsafe behavior; green does not close it.

| Claim / requirement | Current evidence and boundary |
|---|---|
| Real QKD / ETSI / information-theoretic security | Not provided. QM-QKD-001 M1 scope: simulator opt-in, simulated provenance and UI labels; startup/status tests. Authentication and real adapters remain absent (F03). |
| Secure independent recipient messaging | Not established. F01/F05/F06 remain: sender owns Level 3 private key, dispatch metadata unbound, no identity signatures. |
| Portal endpoint-only E2EE or destruction | False. F02/F10/F11 remain: server key custody, cloud-memory fallback and retained consumed keys. HTML and README state these boundaries; tests record fallback/retention. |
| XOR integrity | Absent (F04). Characterization confirms accepted altered content. No M1 protocol change. |
| Message delivered / not sent | SMTP acceptance alone is observed. F07 remains: SMTP before record/portal/key persistence. UI avoids delivery and definite-not-sent claims; failure-order test confirms defect. |
| Secure credential/key storage | Not established (F08/F09/F18). POSIX chmod tests do not prove Windows ACLs; local wrapping key, account binding and path/persistence defects remain. |
| Private metadata / authentic certificate | Not established (F16). Header metadata is visible; recipient hashes are guessable; JSON/PDF is unsigned. Labels corrected, fields preserved. |
| Native crypto available | Only explicit research pair, native hash and passing tests substantiate availability. Original pin blocked (F17); no FIPS-validation claim. |
| Reproducible green suite | M1 tests isolate limiter/state, reject skips and run with multiple orders (F19). Hosted CI is configured, not yet verified. |

F12 capability logging, F13 resource limits, F14 endpoint/local TLS defects and
F15 MIME/rendering/worker issues remain open. The duplicate-control characterization
confirms parser permissiveness; M1 did not redesign parsing or Qt concurrency.
All F01–F19 remain tracked as unresolved findings; M1 addresses selected assurance,
dependency and labeling portions only. Known defects preclude production use.

QM-TEST-001 is implemented at baseline scope; release traceability remains M8.
QM-DOC-001/002 cover truthful docs and preservation. QM-DEPLOY-001 has locked inputs
and a CI definition; signed packages/SBOM/release gates are unfinished. QM-CRYPTO-006
independent vectors/interoperability are not fulfilled by legacy round trips.

Historical BUGS/DEFERRED/CHANGELOG entries are retained as historical reports,
superseded by IMPLEMENTATION_STATUS.md and the Markdown specification where they
make incompatible present-tense security or release claims.
