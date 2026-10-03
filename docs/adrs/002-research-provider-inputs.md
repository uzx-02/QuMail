# ADR 002: reproducible legacy research provider

Date: 2026-10-03. Status: accepted for M1 characterization only.
Requirements: QM-TEST-001, QM-DOC-001, foundation for QM-DEPLOY-001.
Findings: F17/F19; F01/F02/F05/F06 remain unresolved.

## Evidence and decision

The declared `liboqs-python==0.14.1` cannot resolve. A browser-cached PyPI page
reported 0.15.0, but both actual installation and live PyPI JSON reject that
version. Live metadata lists 0.16.0 and 0.16.0.1. Use the installable **0.16.0.1**
wheel paired with **liboqs 0.16.0**, commit
`5a1a854b0dc9f2141bdc771c555ee60c37950183`, for legacy research tests only.
This changes provider inputs; it does not approve this custom protocol.
The original pin remains explicitly blocked in
`packaging/requirements-original-provider.txt`. `python -m crypto.legacy_provider`
reports that blocker and exits 1; only `--research` checks the different lane.
No automatic version substitution occurs. The exact-pin resolver was rerun and
its failure is retained in `docs/operations/evidence/original-provider-resolver.txt`.

Build only ML-KEM-768, shared library, distribution CPU dispatch, no OpenSSL
integration, using explicit CMake/Ninja commands. Record compiler and resulting
binary hash in local build evidence. No arbitrary native binary distribution.
Upstream binding is MIT; liboqs has algorithm-specific third-party notices in
addition to its main license. Preserve the upstream license tree in any eventual
research package; there is no redistribution approval for QuMail yet.

`cryptography` changes from 46.0.5 to **50.0.2** because the original pin predates
the advisory fixes documented in specification §17. Validate existing AES-GCM,
Fernet and X.509 operations. Other original direct pins stay fixed for M1; freeze
transitives separately. A package upgrade is not evidence of a full system audit.

## Native loading boundary

The inspected 0.16.0.1 wheel automatically clones/builds native code if loading
fails. It has no documented disable-install flag. QuMail therefore checks its
exact version and `oqs.py` SHA-256 before import, requires an absolute explicit
native installation, checks native version, and passes a deliberately invalid
`PYOQS_VERSION` sentinel during import. The pinned upstream version parser raises
before temporary-directory creation or subprocesses for that sentinel. An
executable test extracts that exact upstream function and verifies rejection
before side effects. After import, verify the actual loaded path and ML-KEM
capability. Loading failure never selects another crypto mode.

This unusual integration is contained in `crypto/legacy_provider.py`; it is
research-only technical debt, not the proposed production OpenPGP adapter. Source
changes, pre-imported OQS or unexpected versions fail closed. Native DLL loading
assumes a trusted local build directory and trusted process/environment; this is
not a defense against same-user malicious code. No perfect Python zeroization
claim. A future binding update requires reviewing the guard and regenerating
locks, not editing the expected version alone.

## Validation, migration and rollback

Full legacy round trips, wrong-key/tamper tests, missing-provider and no-install
tests are required. Wire fields and old keys are preserved. Original unavailable
0.14.1 artifacts cannot be compared: historical Level 3 compatibility remains
unverified until real fixtures are supplied. Revert provider integration and use
an isolated historical reader if required; never delete historical key material.

## Primary sources

- [Live PyPI OQS metadata](https://pypi.org/pypi/liboqs-python/json)
- [OQS source and limitations](https://github.com/open-quantum-safe/liboqs)
- [Binding source](https://github.com/open-quantum-safe/liboqs-python)
- [Cryptography release history](https://cryptography.io/en/latest/changelog/)

Installed wheel contents and executed resolver results take precedence over
cached web snippets. Exact platform/build evidence is in the M1 validation report.
