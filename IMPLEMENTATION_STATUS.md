# QuMail 1.0 implementation status

Updated: 2026-10-03 (Asia/Calcutta). Target: first proper QuMail 1.0.

## Current milestone and exit decision

**M1: COMPLETE at baseline scope — local and hosted Windows/Ubuntu evidence
passes. Stop after M1; this is not production or release approval.**
M2–M8 have not begun. No production release is approved.

Review branch: `codex/m1-hosted-validation`, published to `uzx-02/QuMail`.
Audited source baseline: `7079cf16cb2623172a329fd045045227f7eb65b4` on `main`.
First fully successful hosted implementation/workflow commit:
`023c941ec2ef284f6be28b5a9605f1dca9c28787`. Results below belong to that exact SHA;
subsequent documentation commits must not inherit an unexecuted test claim.
The canonical engineering source is `QuMail-1.0-Research-Audit-Specification.md`.
The 143-page PDF is a presentation/reference copy. Comparison found formatting,
link/reference extraction differences (including merged/omitted citation labels),
not differing engineering requirements. Both supplied files remain untouched.

## Evidence authority

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

## Next milestone

Review the M1 branch and its exact-commit evidence. **Do not begin M2 in this
work.** A later, separately authorized M2 task is the bounded production
protocol/provider/interoperability proof; no implementation was started here.

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
existing separate gates. F01–F19 are not declared fully fixed. M2 not started.
