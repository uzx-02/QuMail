# M1 dependencies and support evidence

Scope: research development baseline, 2026-10-03. Canonical requirements are in
the root Markdown audit specification §54. No production platform is supported.

| Lane | Inputs and observed status |
|---|---|
| Original Level 3 | `liboqs-python==0.14.1` is unavailable from PyPI. Preserved in `packaging/requirements-original-provider.txt`. BLOCKED, not replaced as an exact-reproduction claim. |
| Windows local research | CPython 3.12.14 x64; hash-locked development dependencies; binding 0.16.0.1 / native 0.16.0. Local validation is recorded in `m1-validation.md`. |
| Windows hosted CI | Windows 2022 / Visual Studio 2022 configuration exists. No hosted execution verified. This differs from the locally validated MinGW compiler. |
| Linux hosted CI | Ubuntu 24.04 / Ninja configuration exists. No Linux execution verified. |
| Other platforms / historical ciphertext | Unvalidated; do not infer compatibility from same-provider round trips. No historical 0.14.1 ciphertext fixture or native binary was supplied. |
| Gmail / Yahoo / Firestore | Adapter/fixture tests only. No real mailbox, OAuth, cloud deployment or transaction integration was exercised. |
| Real QKD / ETSI | Not implemented. Custom unauthenticated CSPRNG simulator only. |

`requirements.txt` includes `packaging/requirements-runtime.lock`. Runtime excludes
OQS and Firestore. The development lock adds their explicitly research/legacy
test dependencies and native build tools. Install with `--require-hashes`; the
locks constrain transitive versions and accepted distribution hashes. They are
universal Python 3.12 inputs, not a claim that all wheel platforms were tested.

## Explicit availability reports

From the repository root (use your environment's Python):

```powershell
python -m crypto.legacy_provider
# Expected exit 1: original pin remains blocked; no network or provider import.
python -m crypto.legacy_provider --research
# Exit 0 only for the explicit validated local research pair; otherwise exit 1.
```

The report never installs a provider. The research report includes the native
binary hash. Configure `OQS_INSTALL_PATH` with an absolute path as described in
`native-research.md`. The source/digest/version guard prevents the pinned wrapper's
automatic installation path. Do not import `oqs` independently in the app.

## Advisory and license triage

This is triage of the supplied specification §17, not a fresh comprehensive
vulnerability scan or redistribution approval. `cryptography` 46.0.5 was changed
explicitly to 50.0.2 in ADR 002, beyond the listed 46.0.6, 46.0.7, 48.0.1, 49.0.0
and 50.0.0 fixes. AES-GCM, Fernet and X.509 generation compatibility tests cover
the used API families. The audit did not establish exploitation of its listed
X.509 verifier or PKCS#7 advisory paths in this app. Minimal native builds select
ML-KEM-768 only; unrelated OQS algorithm advisories are not proof of ML-KEM compromise.
Full transitive/native SBOM scanning and artifact provenance remain M8 gates.

| Direct component | License triage / disposition |
|---|---|
| QuMail | No project license grant found; owner decision required before redistribution. |
| PyQt6 / bundled Qt | GPL/commercial route and Qt obligations require owner review; no license choice inferred. |
| Flask | BSD-3-Clause; retained for development simulator. |
| cryptography | Apache-2.0 OR BSD-3-Clause; patched input, still requires binary inventory. |
| google-auth / google-auth-oauthlib / Firestore / requests | Apache-2.0; retain notices. OAuth successor maintenance supersedes historical archival assumptions. |
| fpdf2 | LGPL-3.0-or-later; optional local records, dependency/font inventory still needed. |
| OQS Python binding | MIT for the inspected research distribution; original unavailable artifact cannot be inspected. |
| liboqs | Main and algorithm-specific third-party licenses; preserve upstream license tree. |
| pytest / CMake / Ninja | Development tooling only; MIT / BSD-3-Clause / Apache-2.0 respectively; not a complete transitive inventory. |

The old `portal/Dockerfile` is retained as historical evidence, explicitly excluded
from supported recipes: it pins native 0.15.0, omits the new `packaging/` lock files,
and assumes the old dependency layout. It has not been built or deployed in M1.
Repairing a cloud deployment is outside this baseline; it must not be advertised
as working or production-safe.

## Lock regeneration (maintainer operation)

These commands were executed with uv 0.11.15; review resulting changes and repeat
clean-install validation before accepting new inputs:

```powershell
uv pip compile packaging/requirements.in --python-version 3.12 --universal --generate-hashes --output-file packaging/requirements-runtime.lock --index-url https://pypi.org/simple --quiet
uv pip compile packaging/requirements-dev.in --python-version 3.12 --universal --generate-hashes --output-file packaging/requirements-dev.lock --index-url https://pypi.org/simple --quiet
```
