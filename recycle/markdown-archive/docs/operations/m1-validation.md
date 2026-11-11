# M1 checkpoint and executed validation

Date: 2026-10-03, Asia/Calcutta. Repository root for every command below:
`C:\Users\<LOCAL_USER>\Desktop\Aavishkar-26\QuMail`.
Publication copies replace the local Windows account component with
`<LOCAL_USER>`; substitute the actual local path when reproducing commands.
Original records are preserved byte-for-byte in the ignored local directory
`tmp/m1-private-evidence/2026-10-03-publish-review`. Redaction and original-byte
hashes are recorded in `evidence/publication-redactions.json`. No test results,
warning counts, tracebacks apart from account paths, or provider inputs changed.
Historical baseline: `main` / `7079cf16cb2623172a329fd045045227f7eb65b4`.
Current review branch: `codex/m1-hosted-validation`, published to `uzx-02/QuMail`.
**M1 COMPLETE at research-baseline scope**, based on hosted commit
`023c941ec2ef284f6be28b5a9605f1dca9c28787` and run 37128055379. The final section
records exact results and supersedes earlier pending decisions retained below.
No main push, merge, mail, cloud deployment or user-data migration occurred.
Canonical engineering source: root Markdown specification.

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

## Hosted validation completed (2026-10-03)

Authentication succeeded through the normal OS keyring outside the network
sandbox. The sandbox's initial connection failure misleadingly reported an
invalid token; the permitted retry verified repository access and workflow scope.
No unrelated credential search or application secret was introduced.

Published branch: `codex/m1-hosted-validation`. Initial commit:
`529625de20ee11d556f0bae3e467b9c221c9d4be`. An explicit 67-file allowlist included
reviewed M1 work, canonical Markdown and redacted evidence. Staged common-secret,
private-key, personal-path and binary/NUL scans passed. The reference PDF, private
originals, environments, user keys/token caches and native binaries were excluded.
Canonical Markdown hard-break whitespace and archived traceback whitespace were
preserved; code diff checks passed with these records excluded. No merge/release.

### Runs and minimal corrections

| Run / exact tested commit | Actual result | Correction |
|---|---|---|
| [37127749711](https://github.com/uzx-02/QuMail/actions/runs/37127749711), `529625de20ee11d556f0bae3e467b9c221c9d4be` | Windows setup-python could not obtain 3.12.14; no tests ran. Ubuntu dependencies/native build passed, then collection failed with missing libEGL.so.1: one error, no tests executed. Later order steps were skipped by Actions. | Fresh managed-Python setup and explicit Linux Qt libraries. |
| [37127932449](https://github.com/uzx-02/QuMail/actions/runs/37127932449), `8f9525c0691109ea53ee3854a9060c39866b32c3` | Both setups failed because uv 0.11.15's embedded catalog lacks Python 3.12.14. Dependency/native/test steps did not run. | Explicit CI-only uv 0.12.22 pin, after verifying its Python download catalog. |
| [37128055379](https://github.com/uzx-02/QuMail/actions/runs/37128055379), **`023c941ec2ef284f6be28b5a9605f1dca9c28787`** | **Both jobs passed clean setup, hash install, consistency check, independent native builds, provider report and all three test orders.** | No application/test changes needed. |

Workflow: [.github/workflows/m1.yml at tested SHA](https://github.com/uzx-02/QuMail/blob/023c941ec2ef284f6be28b5a9605f1dca9c28787/.github/workflows/m1.yml).
Jobs: [Windows](https://github.com/uzx-02/QuMail/actions/runs/37128055379/job/111217345728),
[Ubuntu](https://github.com/uzx-02/QuMail/actions/runs/37128055379/job/111217345547).
Run JSON snapshots, failure excerpts and successful job command/output excerpts
are retained in `evidence/hosted-*`. Full downloaded logs remain under ignored
`tmp/hosted-*-run.log`. Published excerpts remove ANSI colors only, retaining
native warnings and complete pytest results. No binary artifact was uploaded.

### Exact environments and provider inputs

| Input | Windows | Ubuntu |
|---|---|---|
| Runner/image | windows-2022; image 20260927.320.1; runner 2.337.0 | ubuntu-24.04; image 20260927.320.1; runner 2.337.0 |
| Python | Managed CPython 3.12.14 x64, Sep 29 2026 build, MSC v.1944 | Managed CPython 3.12.14 x64, Sep 29 2026 build, Clang 22.1.3 |
| Provisioning | uv 0.12.22, setup-uv commit 94527f2e458b27549849d47d273a16bec83a01e9; fresh venv/caches disabled | Same pinned inputs; independently provisioned |
| Consistency | Checked 47 packages in 2ms; all installed packages compatible | Checked 46 packages in 1ms; all installed packages compatible |
| Locked packages | cryptography 50.0.2, PyQt6 6.10.2, pytest 8.4.2; unchanged development lock | Same lock; Windows colorama marker explains count difference |
| Native tools | CMake 3.31.6, Ninja 1.11.1.3 installed; Visual Studio 17 2022 x64 generator; MSVC 19.44.35229.0; SDK 10.0.26100.0 | CMake 3.31.6 / Ninja 1.11.1.3; GNU 13.3.0 |
| Qt system prerequisites | Not applicable | libegl1 and libopengl0, each 1.7.0-1build1 |
| OQS research pair | binding 0.16.0.1 / native 0.16.0 | binding 0.16.0.1 / native 0.16.0 |
| Native SHA-256 | `f797a7483d13e134f0a8c76cb2c0afc93ba1ba43e556f31fea70597ff27192e3` | `43abe526be5a7a067c8e0e4d460bc354b7c0570be3bc2d685727f97c6dd0a2e6` |

Each runner verified native source commit
`5a1a854b0dc9f2141bdc771c555ee60c37950183` against the unchanged build manifest:
shared/build-only library, ML-KEM-768 only, OpenSSL OFF, distribution build ON,
Windows export-all-symbols TRUE; Linux also sets install libdir `lib`.
Linux does not depend on any Windows binary or local filesystem path. Distinct
hashes are expected for different compilers/platforms, not bit-reproducibility.

### Commands and exact results at 023c941

The pinned setup action creates and activates a fresh managed-Python venv.
Commands below ran in both hosted checkouts except the Linux-only apt/dpkg step.
Expanded prefix/generator values and native output are in the job excerpts.

```powershell
# Linux only:
sudo apt-get update
sudo apt-get install --no-install-recommends -y libegl1 libopengl0
dpkg-query -W libegl1 libopengl0
# Both:
uv --version
python -c "import platform, sys; print(platform.platform()); print(sys.version); assert sys.version_info[:3] == (3, 12, 14)"
uv pip install --require-hashes -r packaging/requirements-dev.lock
uv pip check
git -C tmp/liboqs-src rev-parse HEAD
# Verify source SHA; set the platform generator and runner-local prefix:
cmake -S tmp/liboqs-src -B tmp/liboqs-build @generator "-DCMAKE_INSTALL_PREFIX=$prefix" @($manifest.cmake_flags)
cmake --build tmp/liboqs-build --config Release --parallel 2
cmake --install tmp/liboqs-build --config Release
# OQS_INSTALL_PATH points to this runner's native install:
python -m crypto.legacy_provider --research
python -m pytest -q
python -m pytest -q --test-order reverse
python -m pytest -q --test-order 20261003
```

| Platform | Normal | Reverse | Seed 20261003 |
|---|---|---|---|
| Windows | 37 passed, 5 warnings in 3.25s | 37 passed, 5 warnings in 1.11s | 37 passed, 5 warnings in 1.14s |
| Ubuntu | 37 passed, 5 warnings in 2.38s | 37 passed, 5 warnings in 0.66s | 37 passed, 5 warnings in 0.70s |

Every invocation exited 0: **zero failed tests, errors, skips, xfails or xpasses**.
That is 37 distinct tests repeated three times on each platform. Windows' Linux-
only setup step is conditionally skipped by design; no required test is skipped.
Five pytest warnings per invocation are the recorded legacy utcnow deprecations.

Additional warnings: Windows liboqs emitted **42 repeated compiler warnings**
that MSVC lacks the reviewed optimization barrier and may introduce non-constant-
time behavior. Passing functional tests does not establish constant-time safety;
assembly/side-channel review and production compiler/provider approval remain
gated. Ubuntu emitted no corresponding native warning. Each job also emitted one
notice that the pinned checkout action targets deprecated Node 20 and the runner
forced Node 24. Both jobs succeeded; these notices are retained, not suppressed.

Local focused check after the setup edit (configured local OQS):

```powershell
.venv-m1-clean\Scripts\python.exe -m pytest -q tests/test_ui_claims.py tests/test_legacy_provider.py tests/test_native_compatibility.py
```

**12 passed in 1.12s**, exit 0. YAML, matrix, immutable action references and
read-only permissions also passed local static checks. Temporary uv 0.12.22
confirmed both Python download targets before updating its CI pin. These local
results are separate from hosted evidence. Application locks and tests unchanged.

### Final M1 acceptance assessment

| Criterion | Assessment | Evidence and limits |
|---|---|---|
| Clean installation on declared initial platform | satisfied | Local Windows and clean hosted Windows/Ubuntu hash installs. |
| Exact dependency/native inputs and hashes | satisfied | Unchanged locks/source/flags; binding digest, toolchain/image/package versions and independent native hashes recorded. Bit-identical release builds not claimed. |
| Deterministic existing tests and isolated state | satisfied | All 37 tests pass in all three orders on both platforms; Windows/POSIX permission branches exercised. |
| Mandatory crypto/no false green skips | satisfied | Native tests executed, zero pytest skips; local missing-native/skip-gate negative evidence preserved. |
| F07/F10 characterization | satisfied | Unsafe send ordering and memory fallback recorded without redesign. |
| Hosted Windows/Ubuntu evidence | satisfied | Successful run 37128055379 at exact commit 023c941; independent native builds. |
| Truthful claims/support and simulator boundary | satisfied | Docs now reflect tested platforms; no production/QKD/ITS claim; startup and UI tests pass. |
| Advisory/license triage | satisfied at M1 scope | Decisions and residual MSVC warning recorded; no license or cryptographic production qualification inferred. |
| No secret leakage/unexpected native install | satisfied within baseline evidence | Reviewed staged list and bounded scans; no app secrets/uploads; explicit build and tested runtime no-install guard. Not universal security certification. |
| Preserve legacy data/migration boundaries | satisfied | No wire/key/storage migration; original evidence/user data retained; PDF and binaries excluded. |
| Original 0.14.1 artifact/historical fixtures | deferred from M1; compatibility gate blocked | §54 explicitly allows the research pair or unavailable legacy lane; ADR 002 leaves original reproduction/historical compatibility unverified. |
| Independent interoperability, licensing/distribution, release | deferred; existing gates retained | §§17, 54 and 58; ADR 002. No M2 proof, license choice, installer/binary distribution or production approval. |

**M1 COMPLETE at research-baseline scope**, for the validated implementation above.
F01–F19 remain tracked open; test success does not close them. No M2 work, merge,
release or deployment occurred. A later documentation commit does not inherit
this run's results: any later reported run must name its own SHA. The next bounded
task is reviewing the M1 branch and evidence before separately authorizing M2.
