# QuMail 1.0 implementation status

Updated: 2026-10-03 (Asia/Calcutta). Target: first proper QuMail 1.0.

## Current milestone and exit decision

**M1: PARTIAL — local implementation and Windows validation complete; hosted CI
execution evidence outstanding. Do not mark M1 complete yet. Stop after M1.**
M2–M8 have not begun. No production release is approved.

Actual checkout: branch `main`, HEAD
`7079cf16cb2623172a329fd045045227f7eb65b4`. M1 changes remain local/uncommitted.
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
- Intentional missing-native run: 2 failed, 4 passed, zero skips; explicit native
  configuration failure. Intentional skip/xfail probe exited 1 as required.
- Original exact OQS pin resolver: exit 1, unsatisfiable. No silent substitution.
- `transport/imap_receiver.py` has no diagnostic print calls despite the historical
  audit narrative; this current-source difference is documented in architecture.

## M1 requirement checkpoint after work

| M1 requirement or task | Status | Evidence | Files involved | Tests proving it | Remaining action |
|---|---|---|---|---|---|
| Baseline and prior changes | complete | main/7079cf16, dirty-tree inventory retained | validation report; Git | branch/status/rev-parse/diff | None; no commit or push claimed |
| Clean development installation | complete | 47 hash-verified packages, consistent dependencies | requirements.txt; packaging inputs/locks | clean install and complete suite | Other platforms need execution |
| Research native reproducibility/report | complete | binding 0.16.0.1, native 0.16.0, immutable source/flags/binary hash recorded | legacy_provider.py; native manifest; ADR 002 | research report, round trips, five tamper/wrong-key cases, no-install guard | Research only; not original artifact reproduction |
| Original provider and historical compatibility | blocked | exact 0.14.1 resolver fails; historical fixtures unavailable | original-provider requirements; availability report | resolver exit 1; explicit offline blocker exit 1 | Obtain authentic original artifacts/fixtures; do not silently replace |
| Deterministic isolated tests | complete | fresh limiter/registry/stores/clock/temp cwd; session-scoped test QApplication | tests/conftest.py; test_ui_claims.py | three complete orders pass | None at local baseline scope |
| Platform-aware permissions | complete | POSIX mode checked only on POSIX; Windows chmod intent/access checked | test_transport.py | both Windows tests pass | Linux CI execution; no Windows ACL claim |
| Mandatory native tests/no false skips | complete | missing provider fails; skips/xfails fail | pytest.ini; conftest; native tests | missing-native and skip probes; full suite zero skips | Release vectors remain M2/M8 |
| Simulator opt-in/boundary | complete | default creates no server; custom simulator provenance/UI labels | main.py; kme/virtual_node.py; UI | startup/status/UI tests | Real QKD excluded |
| Baseline characterizations | complete | F03/F04/F05/F07/F10/F11/F15 retained as known defects | test_legacy_characterization.py | seven tests | Fix only in their future milestones |
| CI definition and execution | partial | pinned Windows/Ubuntu workflow; YAML checks pass; hosted run absent | .github/workflows/m1.yml | local Windows equivalent tests; static check | Publish through authorized repository workflow and verify both hosted jobs |
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
addressed; hosted CI evidence still missing. **F01–F19 remain tracked as open
findings; this milestone does not claim complete security remediation.**

No changes to TQR dispatch, XOR/AES algorithms, custom MIME schema/reader, identity
ownership, portal decryption/storage trust, OAuth storage or full storage design.
Legacy metadata, key IDs, readers and user data were preserved. Tests used temporary
fixture state; no real mail, credentials, cloud service or hardware QKD was used.

## Blockers and limits

1. No successful hosted CI run for these changes. GitHub CLI API requests require
   authentication; local workflow remains uncommitted/unpublished. Ubuntu/MSVC jobs
   are configured, not validated. This prevents unconditional M1 exit approval.
2. Original `liboqs-python==0.14.1` unavailable. ADR 002 explicitly permits a
   different research-only lane; it is not evidence of historical compatibility.
3. Project license/Qt distribution choice unresolved; no redistribution approval.
4. Legacy Docker recipe is obsolete and excluded, not advertised as runnable.
5. Five legacy datetime deprecation warnings remain. No release/interoperability,
   real provider OAuth/SMTP/IMAP, real Firestore or Windows ACL validation claimed.

## Publishing continuation (2026-10-03)

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

First obtain missing M1 CI evidence and reassess exit. **Do not begin M2 in this
work.** Subsequent M2 is a bounded production protocol/provider/interoperability
proof, separately authorized and gated; no implementation was started here.
