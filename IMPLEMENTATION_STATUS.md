# QuMail 1.0 implementation status

Updated: 2026-10-06 (Asia/Calcutta). Target: first proper QuMail 1.0.

## Current milestone and exit decision

**M1: COMPLETE at baseline scope. M2: PARTIAL. M3: PARTIAL.**
**M2 engineering proof complete; M2 exit pending external expert review.**
M3 development proceeds under the owner's explicit ordering exception in
[ADR 004](docs/adrs/004-m3-development-exception.md). Independent review remains
required before production cryptographic enablement or a security release; it
may require corrections to M2 and dependent M3 work. No AI assessment substitutes
for independent review. M4–M8 have not begun. No production release is approved.

Current local branch: `codex/m3-identity-vault`, created from preserved M2 checkpoint
`1fc4e55f09e173cec7634d0b2dc776097b552063`. The local M3 checkpoint records only the
isolated source/locks/tests/scripts, redacted evidence and documentation. Exact
input correspondence is in `docs/operations/evidence/m3/input-hashes.json`; results
belong to the tested working-tree bytes, not the unchanged M2 parent. M1/M2
branches, canonical specification and M2 reviewer draft are preserved. Nothing
was pushed, merged, deployed or released; no real mail or user-data migration.

## M3 bounded implementation and acceptance (2026-10-05–06)

[Full acceptance table and exact outputs](docs/operations/m3-validation.md),
[owner exception and design](docs/adrs/004-m3-development-exception.md),
[recovery instructions](docs/operations/m3-recovery.md) and
[source/reproduction](experiments/m3/README.md) describe this isolated boundary.

| Requirement / criterion | Implemented and executed evidence | Remaining gate |
|---|---|---|
| §54 M2 prerequisite | M2 engineering preserved; explicit owner-authorized ordering exception | M2 remains PARTIAL; independent crypto/protocol review before production enablement/security release |
| QM-ID-001/002, T06 | Distinct account/device/root/handle types; two same-provider accounts; maintained Google signature verifier with synthetic issuer; state/nonce/issuer/audience/subject/expiry/hosted-domain rejection | Live Gmail/Yahoo authorization, browser/PKCE, session/Settings integration pending; Yahoo fails closed |
| QM-ID-003/004/005, QM-PQC-002, T04 | Recipient-owned root plus separate signing/encryption keys; public-only import/export; explicit fingerprint pin; changed/retired-key blocking; root-signed rotation/revocation; expiry/unbound foreign subkey rejection | Human ceremony and enrollment/root-reset threat-model review; simultaneous devices explicitly deferred |
| QM-KEY-001/002/006, QM-SEC-004, T08 | Real Windows Credential Manager write/read/delete and cleanup; no file fallback; authenticated owned SQLite records; cross-account/tamper/hostile-ID rejection | Same-user malware/OS-store rollback/path races/installation ACLs not claimed addressed |
| QM-KEY-003/004/005, T08 | Additive rotation/history retention; explicit encrypted transfer backup; clean archive-only restore decrypts actual historical envelope; new-root re-verification; destruction acknowledgment | Offline copies/backups are not remotely erased; independent recovery review pending |
| §39 changed certificate interoperability | Sequoia/OpenSSL ↔ rPGP with separate signing subkey; rotated certificate sign/verify/decrypt checks | Common active-fingerprint selection is not independent policy selection; no multi-device/MUA/Linux claim |
| T08 atomicity | Parallel real writes, abrupt child exit, SQLite FULL and commit-denied restore leave consistent records | Whole-database rollback resistance and OS-store/database joint transaction not provided |
| QM-DOC-001/002, §54 | ADR 004, architecture, recovery, support limits and evidence updated | M3 stays PARTIAL pending provider-specific/live/integration and independent-review gates |

Final tests: **2 native passed** (1.14 s); **32 Python passed** normal (14.80 s)
and the **same 32 distinct tests passed** reverse (14.74 s), zero skips/warnings.
Legacy regression: **37 passed, 5 existing warnings**, 2.68 s, zero skips.
Real OS-store tests required the normal Windows logon session because the sandbox
denied access; mocked storage denial and synthetic OAuth are labeled separately.
All 15 M2 input hashes remain unchanged; M3 third-party Cargo inputs match M2.
OpenPGP still uses native OpenSSL 3.5.9; storage uses cryptography 50.0.2's separate
OpenSSL 4.0.3 backend. Neither is substituted silently for the other.

Next bounded work remains M3: complete and validate external-browser authorization
and session/Settings integration using explicitly provisioned test accounts;
obtain independent enrollment/recovery and M2 cryptographer/protocol review.
No production cryptographic enablement, M4, push, merge or release is approved.

## Preserved M2 handoff provenance

Preserved M2 branch: `codex/m2-provider-proof`. At test execution, HEAD was
`5880dd4d6bc15a2e111c49d929432e6ed2419f33` and M2 was working-tree content,
identified by the experiment source/input hashes in
`docs/operations/evidence/m2/20261005-input-audit.json`. The local review checkpoint
preserves those exact 15 input files; its SHA is recorded in the local reviewer
request prepared after committing (`docs/operations/m2-reviewer-request.md`).
Results belong to the hash-identified snapshot, not its earlier parent commit.
The M1 review branch below is preserved. No M2 publication,
merge, production integration, user-data migration or release occurred.

Review branch: `codex/m1-hosted-validation`, published to `uzx-02/QuMail`.
Audited source baseline: `7079cf16cb2623172a329fd045045227f7eb65b4` on `main`.
First fully successful hosted implementation/workflow commit:
`023c941ec2ef284f6be28b5a9605f1dca9c28787`. Results below belong to that exact SHA;
subsequent documentation commits must not inherit an unexecuted test claim.
The canonical engineering source is `QuMail-1.0-Research-Audit-Specification.md`.
The 143-page PDF is a presentation/reference copy. Comparison found formatting,
link/reference extraction differences (including merged/omitted citation labels),
not differing engineering requirements. Both supplied files remain untouched.

## M2 engineering continuation and acceptance (2026-10-05)

[Current acceptance table and exact validation](docs/operations/m2-validation.md),
[external review package](docs/operations/m2-external-review.md),
[provider evaluation](docs/operations/m2-provider-evaluation.md) and
[proposed ADR 003](docs/adrs/003-m2-provider-proof.md) are consistent with this
decision. The original nine-test evidence, hashes and dated 2026-10-04 decision
snapshots are retained; the broad provider survey was not repeated.

- Handoff unchanged: 023c941 → 5880dd4 is documentation/evidence only (15 files);
  application/dependency/CI paths unchanged. M1 review branch/evidence preserved.
- Candidate unchanged: Sequoia 2.4.1/OpenSSL 3.5.9; independent rPGP 0.21.0.
  The unmodified-provider lane retains all nine positive/negative/vector/header
  tests plus three typed contract tests. No provider version substitution.
- `CryptoPolicy`/`OpenPgpProvider` and explicit profile/failure/result types are
  implemented only inside the experiment. Unknown/weak/malformed/unsupported
  profiles, untrusted/changed recipients, forbidden portal/simulator routes,
  critical extensions and resource violations fail closed. Private staging
  cannot become VerifiedPlaintext on provider error or incomplete verification.
- Actual provider-generated OCB, SHA-256 signatures and unknown critical
  notations are rejected, with a valid-profile positive control. Mock provider
  status/staging/panic tests are labeled separately from native evidence.
- Sequoia's private OpenSSL context uses HMAC-DRBG/SHA-512. A diagnostic-only
  source copy exposes its context pointer without changing algorithms. Supported
  OpenSSL controls in fresh child processes demonstrate actual random-source
  initialization and provider failures, plus real post-health send/open panic
  containment. No ciphertext/plaintext success escapes. The native library is
  unchanged; the 651-file audit finds only a feature and accessor addition;
  transitive lock versions/checksums match the ordinary lane.
- Exact configuration has no default-provider self-test callback. Its return
  value 1 is not a FIPS/KAT guarantee. Direct OS entropy-outage and allocation
  failure are not claimed as executed; review questions state the limitations.
- Final normal: **12 passed** (3.03s) ordinary, **5 passed** (0.13s) diagnostic,
  zero failures/ignored. Reverse executes the **same 17 distinct tests**.
  New legacy regression: **37 passed, 5 existing warnings**, 2.40s, zero skips.
  No hosted/Linux M2 result or production IPC execution is claimed.
- Warnings remain visible: M1's 42 liboqs barrier emissions; the candidate native
  build's 871 MSVC diagnostics/231 Perl locale lines; diagnostic path dependency's
  22 upstream Rust deprecation warnings. Native mandatory-SHA256 panic and
  deprecated context constructor's allocation-failure fallback are reviewer
  questions. Successful tests/no-asm do not establish constant-time safety.

| M2 traceability | Current disposition |
|---|---|
| QM-CRYPTO-001/002; QM-INT-001 M2 portion; QM-PQC-001; §§41/54 exact provider/AEAD/header fixture | Engineering proof satisfied on measured Windows build; candidate frozen for review, not production-approved |
| QM-CRYPTO-006 / T01 | Published integration vectors and negative cases retained/passing; broad primitive/fuzz/platform qualification remains M8 |
| QM-CRYPTO-004 / T01/T09 | Real selected-backend RNG/provider failures prevent key generation/encryption; late native errors/panics contained. No nonexistent FIPS self-test guarantee claimed |
| QM-SEC-001/002/006, QM-QKD-004, QM-PORTAL-003 / T03, §54 typed interfaces | Isolated contract/matrix satisfied; no downgrade/substitution. Production UI/TQR/portal are unchanged and not declared fixed |
| §54 M2 Review | **Pending external human cryptographer/protocol review** of composition, secret boundaries and disclosed assurance limits |
| §54 Docs/Migration | Review package, proposed ADR, hash-identified validation ready; no production write migration |

**M2 engineering proof complete; M2 exit pending external expert review.**
Keep M2 PARTIAL until the specification's reviewer accepts it or requests bounded
corrections. Passing tests and this agent's inspection are not independent approval.
No new milestone requirement for enrollment, production UI, SMTP, installer or
Linux CI is invented. Linux/helper/package qualification, full independent MUA
interoperability, original-artifact/historical compatibility, owner licensing and
production release retain their existing gates. F01–F19 are not fully remediated.

## M1 evidence authority (preserved record)

[Checkpoint, exact commands and retained output](docs/operations/m1-validation.md)
records the pre-edit inventory, current tests, failed order runs and final results.
The prior status narrative was stale; source and executable evidence supersede it.

- Original available-dependency baseline in this session: 8 passed, 3 failed,
  2 skipped on Windows. Failures were KME limiter state and two POSIX-only
  permission assertions; ML-KEM skipped without its unavailable provider.
- Continuation checkpoint: 30 passed, 5 warnings, zero skips in existing research
  environment. Not evidence of order independence.
- Clean environment: CPython 3.12.14 x64, 47 packages installed from the development
  hash lock. Dependency consistency check passed.
- Focused M1 tests: 29 passed, 4 warnings. Added research-provider negative tests.
- First reversed/shuffled full runs exposed QApplication lifetime pollution:
  2 passed/35 errors and 25 passed/12 errors. Corrected the test fixture to session
  scope; production Session code was not changed.
- Final complete suite: **37 passed, 5 warnings, zero skips**, in each of normal,
  reverse and seeded order (20261003). Times: 1.50s / 1.55s / 1.41s.
- Hosted run [37128055379](https://github.com/uzx-02/QuMail/actions/runs/37128055379)
  passed both Windows 2022 and Ubuntu 24.04 at `023c941`: **37 passed, 5 warnings,
  zero failures/errors/skips/xfails**, each in normal/reverse/seeded order.
  Dependency consistency: Windows 47 packages, Ubuntu 46; both passed.
- Intentional missing-native run: 2 failed, 4 passed, zero skips; explicit native
  configuration failure. Intentional skip/xfail probe exited 1 as required.
- Original exact OQS pin resolver: exit 1, unsatisfiable. No silent substitution.
- `transport/imap_receiver.py` has no diagnostic print calls despite the historical
  audit narrative; this current-source difference is documented in architecture.

## M1 requirement checkpoint after work

| M1 requirement or task | Status | Evidence | Files involved | Tests proving it | Remaining action |
|---|---|---|---|---|---|
| Baseline and prior changes | complete | main/7079cf16 baseline, inventory retained; review branch published | validation report; Git | branch/status/rev-parse/staged scan | Review branch remains unmerged |
| Clean development installation | complete | Local and hosted Windows: 47 packages; hosted Ubuntu: 46; all consistent | requirements.txt; packaging inputs/locks | clean installs and complete suites | Other platforms remain unvalidated |
| Research native reproducibility/report | complete | binding 0.16.0.1, native 0.16.0, immutable source/flags/binary hash recorded | legacy_provider.py; native manifest; ADR 002 | research report, round trips, five tamper/wrong-key cases, no-install guard | Research only; not original artifact reproduction |
| Original provider and historical compatibility | blocked | exact 0.14.1 resolver fails; historical fixtures unavailable | original-provider requirements; availability report | resolver exit 1; explicit offline blocker exit 1 | Obtain authentic original artifacts/fixtures; do not silently replace |
| Deterministic isolated tests | complete | fresh limiter/registry/stores/clock/temp cwd; session-scoped test QApplication | tests/conftest.py; test_ui_claims.py | three complete orders pass | None at local baseline scope |
| Platform-aware permissions | complete | POSIX mode checked only on POSIX; Windows chmod intent/access checked | test_transport.py | Windows and Ubuntu hosted tests pass | No Windows ACL claim |
| Mandatory native tests/no false skips | complete | missing provider fails; skips/xfails fail | pytest.ini; conftest; native tests | missing-native and skip probes; full suite zero skips | Release vectors remain M2/M8 |
| Simulator opt-in/boundary | complete | default creates no server; custom simulator provenance/UI labels | main.py; kme/virtual_node.py; UI | startup/status/UI tests | Real QKD excluded |
| Baseline characterizations | complete | F03/F04/F05/F07/F10/F11/F15 retained as known defects | test_legacy_characterization.py | seven tests | Fix only in their future milestones |
| CI definition and execution | complete | pinned workflow; independent native builds; run 37128055379 at 023c941 | .github/workflows/m1.yml; hosted evidence | Both platforms pass three complete orders and consistency checks | Preserve exact-SHA attribution for later changes |
| Truthful architecture/claims/support | complete | canonical source corrected; actual flows, provider and historical-doc limits | README; ARCHITECTURE; historical docs; docs/security; docs/operations | source/diff inspection; UI tests | Update support only as new evidence arrives |
| Preservation/status/ADRs | complete | no data migration; backups/rollback and decisions recorded | docs/migration; status; ADR 001/002 | legacy round trips/MIME characterization; diff review | Retain user data and original reader evidence |

## Requirements and security disposition

QM-QKD-001, QM-TEST-001, QM-DOC-001 and QM-DOC-002 are addressed at M1 scope.
QM-DEPLOY-001 receives hash locks and CI groundwork, not signed release/SBOM
completion. QM-CRYPTO-006 independent-provider vectors/interoperability remain
M2/M8 work; same-provider ML-KEM tests do not fulfill them.

F03: simulator exposure/provenance labeling and opt-in addressed; no authorization
redesign. F16: unsigned records/privacy claims corrected. F17: lock/research
availability/reporting and cryptography input update addressed, original pin still
blocked. F19: limiter/Qt isolation, explicit skips and local order evidence
addressed, including hosted CI evidence. **F01–F19 remain tracked as open
findings; this milestone does not claim complete security remediation.**

No changes to TQR dispatch, XOR/AES algorithms, custom MIME schema/reader, identity
ownership, portal decryption/storage trust, OAuth storage or full storage design.
Legacy metadata, key IDs, readers and user data were preserved. Tests used temporary
fixture state; no real mail, credentials, cloud service or hardware QKD was used.

## Blockers and limits

1. No outstanding M1 baseline validation blocker. Hosted run 37128055379 validates
   exact commit 023c941 on both declared platforms; later commits need their own
   evidence. Branch remains unmerged; there is no release approval.
2. Original `liboqs-python==0.14.1` unavailable. ADR 002 explicitly permits a
   different research-only lane; it is not evidence of historical compatibility.
3. Project license/Qt distribution choice unresolved; no redistribution approval.
4. Legacy Docker recipe is obsolete and excluded, not advertised as runnable.
5. Five legacy datetime deprecation warnings remain. No release/interoperability,
   real provider OAuth/SMTP/IMAP, real Firestore or Windows ACL validation claimed.
6. Hosted MSVC emitted 42 optimization-barrier/possible non-constant-time warnings.
   Functional research success does not qualify constant-time safety; production
   compiler/provider review remains gated. Both jobs also reported the checkout
   action's Node 20-to-24 runtime deprecation notice.

## Publishing continuation (2026-10-03)

Historical record before authentication became available; superseded by the
completed hosted continuation below. Preserved for audit continuity.

Remote confirmed as `https://github.com/uzx-02/QuMail`; branch/HEAD unchanged.
`gh auth status` exits 1: no GitHub host is authenticated. Per the user's explicit
stop condition, no review branch was created, no files were staged, and no commit,
push or hosted run was attempted. Git's `manager` helper does not establish CLI
authentication or workflow-write permission. No credentials were sought elsewhere.

Publication scan found local account paths in ten validation files. Byte-identical
originals are retained under ignored `tmp/m1-private-evidence/2026-10-03-publish-review`;
publication copies replace the account component with `<LOCAL_USER>`. Redaction
hashes are recorded in `docs/operations/evidence/publication-redactions.json`.
No common credential-pattern hits, key/cache directories or generated native
binaries were found among pending candidate files; final staged review is still
required before publishing. The PDF remains an unstaged user reference.

The validation report now assesses each M1 acceptance criterion as satisfied,
blocked or deferred. **Original 0.14.1 reproduction and historical compatibility
are separately blocked compatibility/release gates, not additional M1 exit
requirements:** §54 permits a reproducible research-only pair or explicitly
unavailable Level 3; ADR 002 records that choice and its limits. Project/Qt rights
remain owner/distribution gates; triage is complete, approval is not supplied.
The actual remaining M1 exit gate is successful hosted Windows/Ubuntu evidence.

Required user action: complete `gh auth login --hostname github.com --git-protocol
https --web --scopes workflow`, then `gh auth setup-git --hostname github.com` and
`gh auth status` in a local terminal. Do not paste tokens into chat. The review
branch publication remains authorized once normal authentication is available.

## Historical M2 handoff next step (superseded only for development ordering)

Obtain the §54 external human cryptographer/protocol review of the local M2
package and exact input hashes. Address any requested corrections within M2.
That handoff did not authorize M3, production sending, push, merge or release. ADR
004 now authorizes bounded M3 development while retaining the review gate. The package
has not been sent or published; this task does not claim independent approval.

## Hosted continuation completed (2026-10-03)

Authentication verified outside the network sandbox as account `uzx-02`, with
repository access and workflow scope; no unrelated credential search occurred.
Created/pushed the review branch only. The explicit 67-file initial staging list
excluded the reference PDF, private originals, environments, keys and binaries;
staged credential-pattern and personal-path checks passed. Canonical Markdown
and archived output retain presentation/trailing whitespace; code diff checks
pass with those preserved records excluded. No main push, merge or deployment.

Actual failures fixed only in CI setup: actions/setup-python lacked Windows
3.12.14; Ubuntu lacked libEGL; uv 0.11.15 lacked the requested Python download in
its embedded catalog. Pinned uv 0.12.22 now creates fresh managed Python 3.12.14
environments; Linux Qt libraries are explicitly installed. Application locks,
OQS binding 0.16.0.1/native 0.16.0 and all tests/assertions are unchanged. Local
focused checks after the setup edit: 12 passed. No algorithm/provider substitution.

First all-green run: [Windows job](https://github.com/uzx-02/QuMail/actions/runs/37128055379/job/111217345728),
[Ubuntu job](https://github.com/uzx-02/QuMail/actions/runs/37128055379/job/111217345547).
The final acceptance assessment, commands, toolchain versions, native hashes,
warnings and preserved failed runs are in `docs/operations/m1-validation.md`.
All M1 criteria are satisfied; historical compatibility, project/Qt distribution
rights, independent interoperability and production approval retain their
existing separate gates. F01–F19 are not declared fully fixed. At the end of that
M1 continuation M2 had not started; the subsequent M2 state is recorded above.
