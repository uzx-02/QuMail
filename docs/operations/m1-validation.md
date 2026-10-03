# M1 checkpoint and executed validation

Date: 2026-10-03, Asia/Calcutta. Repository root for every command below:
`C:\Users\<LOCAL_USER>\Desktop\Aavishkar-26\QuMail`.
Publication copies replace the local Windows account component with
`<LOCAL_USER>`; substitute the actual local path when reproducing commands.
Original records are preserved byte-for-byte in the ignored local directory
`tmp/m1-private-evidence/2026-10-03-publish-review`. Redaction and original-byte
hashes are recorded in `evidence/publication-redactions.json`. No test results,
warning counts, tracebacks apart from account paths, or provider inputs changed.
Branch `main`; HEAD `7079cf16cb2623172a329fd045045227f7eb65b4`.
Changes are local and uncommitted. No push, mail, cloud deployment or user-data
migration occurred. Canonical engineering source: root Markdown specification.

## Specification comparison

Both supplied files were retained unmodified. PDF has 143 pages. Whole-document
text comparison after Unicode/Markdown presentation normalization, including
integers, found no substantive engineering requirement difference; M1 §54 agrees.
Presentation/extraction differences include link/navigation markup, code/Mermaid
markers, ligatures and merged/omitted citation labels: for example Markdown
`[S04][S05][S06][S08]` appears as `S04S06` in PDF extraction. This comparison does
not claim byte-identical rendering or validate PDF hyperlink targets. Use the
Markdown's explicit reference labels; do not silently infer missing PDF citations.
The extracted differences are retained in `evidence/specification-comparison.txt`.

SHA-256:

- Markdown: `ffa9300b7b9c496add91042e3fe1591818d2f84d3ac2fe8f26c55cc3d186ddc8`
- PDF: `e4e10463e535098263cdbb240c81c9628adc289ca65e3807f70289fe9877bea2`

## Pre-edit checkpoint

This checkpoint was presented before changes on the user's M1-only continuation.
It distinguishes existing work from the remaining work; the order defect found
later is recorded below rather than hidden by the initial normal-order result.

| M1 requirement or task | Status | Evidence | Files involved | Tests proving it | Remaining action at checkpoint |
|---|---|---|---|---|---|
| Actual baseline/prior edits | complete | main / 7079cf16; 22 modified tracked files, plus untracked prior M1/spec files | Git; inventory below | status, branch, rev-parse | Preserve prior work |
| Reproducible install | partial | Hash locks existed; fresh lock install untested | requirements.txt; packaging locks/inputs | Existing environment: 30 passed | Fresh installation/build input report |
| Original provider | blocked | 0.14.1 unavailable; separate research pair in ADR | legacy_provider.py; ADR 002 | Missing native: 2 failed, 4 passed | Explicit command/report and retain original pin |
| KME isolation | complete | Limiter/registry/keys reset, fixed clock | tests/conftest.py; test_kme.py | Both KME tests pass | Reverse/shuffle full suite |
| Windows permissions | complete | POSIX-only mode check; no Windows ACL claim | test_transport.py | Both permission tests pass | State Linux remains unvalidated |
| ML-KEM outcome | complete | No conditional skip; explicit native failures | test_crypto.py; test_tqr_roundtrip.py; test_legacy_provider.py | 30 passed/zero skips with research native | Fresh install and negative crypto checks |
| Simulator boundary | complete | No default KME thread; explicit flag and provenance | main.py; virtual_node.py; UI | Startup/status/UI tests | Correct stale comments |
| Characterization | complete | F03/04/05/07/10/11/15 unsafe behavior retained | test_legacy_characterization.py | Seven passing characterizations | Keep findings open |
| CI | not started | No workflow | .github/workflows absent | No hosted result | Add workflow; verify what is possible |
| Truthful/support/preservation docs | partial | Missing README-linked documents; stale historical claims | README; ARCHITECTURE; BUGS; DEFERRED; CHANGELOG; docs | Source inspection | Complete missing docs |
| Status/ADRs | partial | Status inaccurate about provider, tests and canonical source | IMPLEMENTATION_STATUS; ADRs | Source/result comparison | Update evidence and exit decision |

Prior tracked modifications were: `.gitignore`, `ARCHITECTURE.md`, `README.md`,
`certificates/{cert_generator,pdf_export}.py`, `crypto/level3_mlkem.py`,
`kme/virtual_node.py`, `main.py`, `mime/encapsulator.py`,
`portal/templates/portal.html`, `pytest.ini`, `requirements.txt`,
`tests/{test_certificates,test_crypto,test_kme,test_tqr_roundtrip,test_transport}.py`,
and `ui/{compose_window,inbox_view,key_status_widget,main_window,settings_window}.py`.
Untracked prior work included the status file, loader, two ADRs, dependency inputs/
locks, conftest and five new test modules. The supplied MD/PDF are user references.

## Clean installation and native evidence

Exact commands executed:

```powershell
uv venv .venv-m1-clean --python 'C:\Users\<LOCAL_USER>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
uv pip install --python .venv-m1-clean/Scripts/python.exe --require-hashes -r packaging/requirements-dev.lock --index-url https://pypi.org/simple
uv pip check --python .venv-m1-clean/Scripts/python.exe
```

Results: exit 0 for all three; CPython **3.12.14**; **47 packages resolved and
installed** (40.66 s preparation, 4.41 s installation); dependency check:
`Checked 47 packages in 5ms` / `All installed packages are compatible`.
The initial sandbox-only venv attempt failed accessing uv's external cache; the
authorized rerun succeeded. Test commands likewise required read access to uv's
cache-backed package files. No application dependency was changed to work around
the sandbox.

Runtime lock SHA-256: `0abf6d5b5410e14638983aba3ed0496a474c905cffafcfd983f8df514e3efa63`.
Development lock SHA-256: `36f382c6d828d0ff66627347236a1f808e8bf159b39af846e88034502a1317f2`.
Native immutable source/build flags and local DLL hash: `native-research.md` and
`packaging/native-research.json`. No exact-byte cross-platform rebuild claim.

```powershell
$env:OQS_INSTALL_PATH = (Resolve-Path 'tmp/oqs-install').Path
$env:PYTHONUTF8 = '1'
.venv-m1-clean\Scripts\python.exe -m crypto.legacy_provider --research
```

Exit 0; binding 0.16.0.1, native 0.16.0, original pin still blocked, production
approval false. Full output: `evidence/research-provider.txt`.

## Exact tests and results

The environment variables above apply to positive tests. Output was captured
using `2>&1 | Tee-Object -FilePath <evidence path>` and `$LASTEXITCODE` inspected.
All raw test outputs, including failed first order runs, are retained under
`evidence/`. Times below are pytest's own output, not shell/tool elapsed time.

Focused command:

```powershell
.venv-m1-clean\Scripts\python.exe -m pytest -q tests/test_kme.py tests/test_transport.py tests/test_startup.py tests/test_legacy_provider.py tests/test_native_compatibility.py tests/test_legacy_characterization.py tests/test_dependency_compatibility.py tests/test_ui_claims.py
```

Exit 0: **29 passed, 4 warnings in 3.95s** (`evidence/focused.txt`).

The first complete run passed, but subsequent ordering checks exposed a real
test-lifetime defect. The module-scoped QApplication was destroyed after the UI
tests and deleted the shared Session QObject used by later fixtures. The only
repair was changing the test application fixture to session scope. Production
`core/session.py` is untouched.

| Exact command after `.venv-m1-clean\Scripts\python.exe` | Output before fixture repair | Exit | Retained output |
|---|---|---|---|
| `-m pytest -q` | 37 passed, 5 warnings in 2.84s | 0 | evidence/before-qt-fix-normal.txt |
| `-m pytest -q --test-order reverse` | 2 passed, 35 errors in 0.72s | 1 | evidence/before-qt-fix-reverse.txt |
| `-m pytest -q --test-order 20261003` | 25 passed, 4 warnings, 12 errors in 1.08s | 1 | evidence/before-qt-fix-seeded.txt |

Focused fixture rerun:

```powershell
.venv-m1-clean\Scripts\python.exe -m pytest -q tests/test_ui_claims.py tests/test_transport.py tests/test_kme.py --test-order reverse
```

Exit 0: **7 passed, 1 warning in 0.55s** (`evidence/qt-fixture-focused.txt`).
The complete reverse run below exercises UI before non-UI modules.

Final complete regression commands, run sequentially in new Python processes:

```powershell
.venv-m1-clean\Scripts\python.exe -m pytest -q --test-order normal
.venv-m1-clean\Scripts\python.exe -m pytest -q --test-order reverse
.venv-m1-clean\Scripts\python.exe -m pytest -q --test-order 20261003
```

| Order | Exact final summary | Exit | Full output |
|---|---|---|---|
| normal | 37 passed, 5 warnings in 1.50s | 0 | [normal](evidence/full-normal.txt) |
| reverse | 37 passed, 5 warnings in 1.55s | 0 | [reverse](evidence/full-reverse.txt) |
| seed 20261003 | 37 passed, 5 warnings in 1.41s | 0 | [seeded](evidence/full-seeded.txt) |

**Zero skips/xfails in all final full runs.** Five warnings are retained legacy
`datetime.utcnow()` deprecations in record generation, KME issuance and portal
test-certificate generation. No data/timestamp redesign was made to hide warnings.

## Intentional negative checks

```powershell
uv pip compile packaging/requirements-original-provider.txt --python-version 3.12 --index-url https://pypi.org/simple --output-file tmp/original-provider.lock
.venv-m1-clean\Scripts\python.exe -m crypto.legacy_provider
Remove-Item Env:OQS_INSTALL_PATH -ErrorAction SilentlyContinue
.venv-m1-clean\Scripts\python.exe -m pytest -q tests/test_crypto.py tests/test_tqr_roundtrip.py --tb=short
.venv-m1-clean\Scripts\python.exe -m pytest -q -p tests.conftest tmp/m1_gate_probe.py --tb=short
```

- Resolver: exit 1, `Because there is no version of liboqs-python==0.14.1 ... requirements are unsatisfiable.` Raw: `evidence/original-provider-resolver.txt`.
- Original report: exit 1, explicit blocked status; no provider import/network. Raw: `evidence/original-provider-report.txt`.
- Missing native: exit 1, **2 failed, 4 passed in 0.44s**; both ML-KEM tests name `OQS_INSTALL_PATH`, zero skips. Raw: `evidence/missing-native.txt`.
- Skip gate: exit 1, **1 skipped, 1 xfailed in 0.33s** plus `Unexpected skip/xfail: required validation is incomplete`. Raw: `evidence/skip-gate.txt`. This intentionally failing probe is not part of the normal suite.

The temporary gate probe is reproducible with these contents:

```python
import pytest
def test_unexpected_skip():
    pytest.skip("intentional M1 validation gate probe")
@pytest.mark.xfail(reason="intentional M1 validation gate probe")
def test_unexpected_xfail():
    assert False
```

## CI and review limits

`.github/workflows/m1.yml` defines push/PR/manual triggers, pinned action commits,
read-only contents permission, credential-free checkout, hash install, explicit
pinned native build, provider report and three full suite orders on Windows 2022
and Ubuntu 24.04. It accesses no mail/cloud secrets. YAML parsing, trigger/matrix
and immutable action reference checks passed using temporary PyYAML 6.0.3 in
`tmp/yaml-validation` (not an application or clean-environment dependency).
The first parser attempts found no YAML package; the installed parser required
authorized cache access. Final result: `evidence/ci-static-validation.txt`.

`gh api repos/uzx-02/QuMail/actions/workflows` and
`gh api 'repos/uzx-02/QuMail/actions/runs?per_page=3'` both exited 1: GitHub CLI
requires `gh auth login` or GH_TOKEN. The new local workflow has not been committed,
pushed or executed on GitHub. Static syntax and Windows local tests cannot prove
the Ubuntu/MSVC hosted build. **CI execution is an outstanding M1 evidence gate.**

Diff review confirms no changes to TQR dispatch, Level 1/2 algorithms, MIME reader,
session/storage/OAuth/transport implementations, portal trust/persistence code or
user data. Changes to Level 3 are the explicit research provider boundary and
truthful comments; cipher fields/algorithms remain legacy. `git diff --check`
passes (Git only emits local LF/CRLF normalization warnings).

M1 exit decision: **partial / awaiting hosted CI validation**, not complete and
not production-ready. Original provider/historical compatibility remains blocked;
the research lane supplies local baseline evidence only. Project/Qt licensing,
independent interoperability and release assurance remain later owner/milestone
gates. Stop after M1; M2 has not begun.

## Publishing continuation: 2026-10-03

Rechecked actual branch `main`, HEAD
`7079cf16cb2623172a329fd045045227f7eb65b4`, and the sole remote
`https://github.com/uzx-02/QuMail` for fetch/push. The starting pending diff had
26 modified tracked files plus the recorded untracked M1 work and supplied
specification copies. The index was empty. No review branch, commit or push was
attempted: the user explicitly required stopping publication if authentication
was unavailable.

Command `gh auth status` exited **1** with:

```text
You are not logged into any GitHub hosts. To log in, run: gh auth login
```

Git's configured helper is `manager`; this setting alone does not prove an
authenticated account or permissions to write workflows. No credential-store
contents, unrelated files or tokens were inspected. No hosted job was triggered.
Workflow/run URL and tested hosted SHA: **none**. Existing local results above
are retained; tests were not repeated for documentation/path-redaction changes.

The M1 diff was reviewed against §54 and ADRs 001/002. Candidate-only pattern
scanning found no PEM private keys, common GitHub/Google/AWS credential values,
or populated long OAuth secret/token values. This is a bounded scan, not proof
that every possible secret encoding is absent. Candidate paths contained no
environments, caches, user-key directories or compiled native binaries. Ten
validation files contained local account paths; originals were preserved and
publication copies redacted. The supplied PDF remains an unstaged reference,
not an installer or generated native artifact. Publication must use an explicit
file list, recheck the final staged diff and exclude ignored local originals.

The workflow's unfiltered `push` trigger will run both matrix jobs on the review
branch's exact pushed SHA. Each hosted runner installs locked Python inputs and
builds native OQS from the pinned commit in that runner's checkout. Ubuntu selects
Ninja and `lib/`, with its own prefix; it does not use the local Windows DLL or
compiler path. Compiler/system libraries still require actual hosted verification.
Permissions remain `contents: read`; no artifact upload, installer publication,
service deployment or application secret is configured. A static review is not
hosted execution evidence.

### M1 acceptance assessment

| Criterion (specification §54 M1 unless noted) | Assessment | Justification / outstanding action |
|---|---|---|
| Clean install on declared initial platform | satisfied | Windows CPython 3.12.14; 47 hash-locked packages installed; consistency passed. |
| Exact dependency/native inputs and hashes | satisfied | Locks, immutable native source/flags, reviewed binding digest and local DLL hash retained. No cross-platform binary equivalence claim. |
| Deterministic existing tests, isolated state, no false green skips | satisfied locally | Normal/reverse/seeded: 37 passed, five warnings, zero skips each; negative gates verified. Hosted matrix remains a separate blocked criterion. |
| F07/F10 baseline characterization | satisfied | Tests record SMTP-before-persistence and cloud-memory fallback without changing either behavior. |
| Known findings and truthful claims/support | satisfied | F01–F19 remain open; simulator and research/provider limits are explicit; no production/QKD/ITS claims. |
| Simulator lab boundary | satisfied | Explicit opt-in; default no KME thread; simulated provenance and UI tests. |
| Advisory/license triage | satisfied for triage | ADR 002 and dependencies report identify updates and unresolved rights. No license or distribution approval inferred. |
| No secret leakage / unexpected native download in CI | satisfied by configuration review, execution pending | No application secrets or uploads; runtime no-install guard tested locally; publication copies redact account paths. Recheck staged files and hosted logs. |
| Preserve message bytes, keys, readers and user data | satisfied | No data migration or protocol/storage redesign; preservation instructions retained. |
| Hosted Windows and Ubuntu execution (explicit requested M1 gate) | blocked | Authentication absent; nothing pushed, no hosted SHA/run/results. Authenticate, publish review branch, inspect both jobs and fix M1 failures if any. |
| Original 0.14.1 artifact / authentic historical fixtures | deferred from M1 acceptance; compatibility gate blocked | §54 explicitly permits a reproducible research-only OQS pair **or** separately unavailable Level 3 state. ADR 002 adopts the different pair and explicitly leaves original compatibility unverified. M1 exit does not require claiming unavailable-artifact reproduction. |
| Independent interoperability / production-provider approval | deferred | M2 proof and subsequent release gates; research round trips do not satisfy them. |
| Project/Qt redistribution approval, installers, signed release/SBOM | deferred; distribution remains blocked | §§17, 54 M8 and ADR 002 retain owner/license and release gates. This source-review authorization does not supply a project license or permission to redistribute bundled binaries. |

M1 remains **PARTIAL** because the requested hosted execution evidence is absent.
The original artifact and historical-fixture blocker is tracked separately, not
used to silently redefine §54's research-baseline acceptance. No M2 work started.

### Required normal authentication setup

Run in a local terminal and complete GitHub's browser flow with an account that
can push branches and workflow files to `uzx-02/QuMail`:

```powershell
gh auth login --hostname github.com --git-protocol https --web --scopes workflow
gh auth setup-git --hostname github.com
gh auth status
```

The additional `workflow` scope is needed for committing the workflow definition;
it does not increase the workflow's own read-only runtime permissions. Keep tokens
out of chat and repository files. After authentication, resume the already
authorized review-branch publication and exact-commit hosted validation.
