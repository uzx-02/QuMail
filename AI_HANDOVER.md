# QuMail: successor starting point

Prepared 2026-11-01. **Read this first; then inspect Git before changing anything.**
This is a development prototype, not a production-approved secure mail client.
If you have no repository access, say so; do not invent code or execution results.

## Product and current reality

The owner wants usable secure email on **Windows and Android**: connect conventional
mail accounts, read ordinary mail, and prepare/send/retrieve/verify/decrypt protected
mail locally. Recipient-owned keys, explicit contact verification, encrypted storage,
recoverable keys and honest delivery states are essential. A judge-facing build must
use functioning services, not sample inboxes or fabricated success. Presentation-only
development has ended. Judge-facing usability does not imply production approval.

**Implemented:** Windows Python/PyQt6 development client, Google OAuth implementation,
Gmail IMAP/SMTP adapters, account-scoped vault/Settings, encrypted drafts/outbox,
protected attachments/reply/forward/archive and optional local ciphertext relay.
**Implemented but acceptance pending:** live Google end-to-end operation, human
usable-security/accessibility walkthrough and independent security/protocol review.
**Not implemented:** Android application, production packaging/release, real QKD or
ESP32 integration. Linux M1 baseline tests are not modern Linux desktop support.

The canonical engineering specification is
[QuMail-1.0-Research-Audit-Specification.md](QuMail-1.0-Research-Audit-Specification.md),
especially §§35–54. Its historical audit is not a description of every current path.
The PDF is reference material. Preserve both; do not reset to an historical anchor.

## Exact pause point

Source branch: `codex/m7-relay-google-acceptance`.
Source HEAD: `4e429a43a6d9ae7fe6bb45c4ae5a8dcb6200e6b0`.
The later documentation commit containing this file is a separate checkpoint;
obtain it with `git log -1`, not a self-referential SHA here.

No tracked engineering edits existed when this handover began. Three unrelated
untracked files remain: reference specification PDF, `Start-QuMailDemo.ps1`, and
`docs/operations/m2-reviewer-request.md`. Do not stage/delete them. Ignored `tmp/`
contains native builds, private test artifacts and launch configuration; environments
and outside-repository vault/client configuration also remain untouched.

**Known immediate defect:** the private Google launcher points at an acceptance
vault visible to tool subprocesses but absent in the owner's desktop File Explorer.
The earlier tool-only preflight was misleading. Do not repeat that as desktop proof
or silently create a replacement at the same path. A private GUI shortcut
`tmp/m7/QuMail-Desktop-DryRun.lnk` was prepared for a distinct new desktop path;
it was **not launched or validated**. No new vault was created. See the exact pause
record and next task in [STATUS_AND_ROADMAP](docs/handover/STATUS_AND_ROADMAP.md).

At stopping-time process inspection found no Python/pythonw, QuMail helper, Cargo
or rustc process. No known database commit, backup, SMTP submission or relay request
is in flight. No external send was performed or observed by this agent. Earlier A
enrollment only appeared successful to the owner; its durable outcome is unknown.
Recheck processes and owner-reported activity before resuming; do not inspect personal
credential caches. File Explorer was left open; no authentication was initiated.

## Architecture in one view

`main.py --dev-mailbox` → `ui/mailbox_window.py`, `ui/mail_actions.py`,
`ui/identity_settings.py` → `core/account_session.py`, `core/settings_operations.py`,
`mailbox_client/service.py`, `mailbox_client/workflows.py` → M3 vault/identity,
M5 MIME/helper, M4 durable outbox → fixed Gmail TLS transports.

Default `main.py` launches the **legacy** UI; it is not the modern application.
`--dev-identity` is isolated Settings; `--dev-simulator` explicitly starts the
unauthenticated CSPRNG lab service. Never mix these modes or route modern keys into
legacy TQR/portal. Modern application dependencies still live under
`experiments/m3`, `m4`, `m5`; these are not disposable fixtures. M2 is a frozen proof;
M5 demo/panel code is a separate historical fixture, not the mailbox application.

[CODEBASE_MAP](docs/handover/CODEBASE_MAP.md) gives actual symbols and contracts.
[BUILD_RUN_TEST](docs/handover/BUILD_RUN_TEST.md) gives commands and setup limits.

## Evidence and decisions to preserve

- **M1 COMPLETE at research-baseline scope:** hosted Windows/Ubuntu at `023c941…`;
  original OQS 0.14.1 reproduction/historical ciphertext remain separate gates.
- **M2 PARTIAL:** engineering proof complete at `1fc4e55…`; external expert review
  pending. Independent Sequoia↔rPGP crypto exchange exists; independent MIME peer
  qualification does not follow from shared MIME fixtures.
- **M3–M6:** bounded Windows development engineering implemented; full milestone
  acceptance remains partial under recorded live/review/ship gates.
- **M7 locally qualified:** SQLite/mTLS relay only. Owner explicitly excluded cloud
  deployment; lack of cloud is not a blocker for this workstream. QKD lane excluded.
- **M8 not started.** No release, signing, license grant or independent approval.

Executed evidence at `18174e1…`: **163 passed** (13 M7 + 96 M6 + 54 M3), and
**27 passed** in reverse (relay/OAuth subset). On 2026-11-01 handover inspection,
all 17 source hashes and the M5 helper hash in that retained manifest matched.
HEAD adds launcher/docs only; no suites were rerun for this documentation task.
Exact provenance, anchor ancestry and historical results are in
[STATUS_AND_ROADMAP](docs/handover/STATUS_AND_ROADMAP.md).

ADRs 004/005/006 permit bounded development before unavailable independent reviews;
they do not waive production/security-release review. Do not repeatedly stop local
engineering for those unavailable reviewers. One active enrolled device per account
remains the explicit limit. No raw-key sharing or OAuth-as-key-recovery shortcut.

## Run and safety essentials

Use installed `.venv-m1-clean/Scripts/python.exe` and existing native helpers under
`tmp/m2/target/debug`. Do not upgrade dependencies to fix a path problem. Check the
actual desktop filesystem/logon context before accepting secure-store or vault results.
The parameterized launcher is `tools/start_google_acceptance.ps1`; it takes explicit
`-GoogleClient`, `-Vault`, `-CheckOnly`, and optional `-AllowNewVault`. Placeholder
paths are not files. Creation still requires the user's **Create vault** action.

Targeted offline checks: `python -m pytest experiments/m6/test_settings.py -q`
or the affected test module using the installed interpreter. Broad checkpoint:
`python -m pytest experiments/m7 experiments/m6 experiments/m3/tests -q -rA`.
Plain `pytest` selects only legacy `tests/`; see build instructions before using it.

Never release protected plaintext before complete integrity/signature verification.
Never auto-trust a certificate, downgrade a profile, fall back to legacy/portal, or
retry Unknown submission blindly. Commit frozen envelope before SMTP. Preserve
account/vault/generation ownership, recovery acknowledgment before package writing,
PEEK retrieval, safe plain-text display and attachment no-clobber export.
Full invariants and residual risks: [SECURITY_CONTRACTS](docs/handover/SECURITY_CONTRACTS.md).

## Copyable resumption prompt

> Read AI_HANDOVER.md, then only the launch/pause sections of BUILD_RUN_TEST.md and
> STATUS_AND_ROADMAP.md. Verify actual branch/HEAD/dirty files and running QuMail
> work. First task: finish the normal-desktop launcher dry run through Settings,
> correcting the tool/desktop vault-path mismatch without overwriting or migrating
> old data. Stop before Create vault, Google authorization or sending; the owner
> requested manual testing. State expected behavior and acceptance before coding.
> Use the installed environment/helpers and explicit private configuration; no
> credential searches, new dependencies, test weakening or security bypass. If a
> new disposable desktop vault is needed, explain its distinct path and that it
> cannot recover the old root; let the owner create/enroll it. Produce verified
> steps, not another tool-only success report. Work one bounded task at a time;
> preserve all account, verification, persistence and uncertainty contracts. Run
> focused checks only for changes, log verbose output, update status with exact
> source identity and create a scoped local checkpoint. Ask promptly for external
> inputs while completing independent work. No arbitrary sends, push, merge,
> deployment, release, Android port or hardware implementation in this first task.
> If repository access is unavailable, state that limitation rather than inventing
> implementation facts. Development exceptions are not independent approval.

After that task, follow the prioritized Windows/Android roadmap. The
[hardware addon](docs/handover/HARDWARE_ADDON.md) is deferred research after core delivery.
