# Verified state and executable roadmap

Authoritative handover status, inspected **2026-11-01**. This records the source
checkpoint, not the SHA of the later documentation-only commit. Historical logs
remain in place; their old “next step” text is not a new instruction.

## Git, preservation and interrupted task

Branch: `codex/m7-relay-google-acceptance`.
HEAD: `4e429a43a6d9ae7fe6bb45c4ae5a8dcb6200e6b0`.
Parent: `18174e1b8c0ce276aa294275e195b2e54c498075`.
HEAD changed only `tools/start_google_acceptance.ps1`, manual launch instructions
and implementation status; modern application/test/dependency/native bytes did not
change after the M7 checkpoint. No tracked dirty code existed at handover start.

| Verified ancestor | Meaning / relationship |
|---|---|
| `023c941ec2ef284f6be28b5a9605f1dca9c28787` | M1 hosted validation; ancestor of all below, not current app qualification |
| `1fc4e55f09e173cec7634d0b2dc776097b552063` | Committed M2 proof; parent `5880dd4d6bc15a2e111c49d929432e6ed2419f33` is earlier, not the proof checkpoint |
| `219dc97bae4ab74f6a2d4d857be5dd54bcfeab6e` | M5 protected-MIME checkpoint; preserve as fallback provenance |
| `b96abc4` → `2c0eed635bb66740f8365ee89b81e04470a7f515` | Presentation UI followed by actual M6 Gmail mailbox path; useful frontend engineering retained without application fixture accounts |
| `6f4d5fcb62ae0fbae7be68739e0242a4468d750d` → `f39bc5429658ec3009b9ce10c3f1cd39c21db3ef` | Integrated mail workflows, then connection/usability fixes |
| `8eebb5eb7834caa230795c7ca9b446c631df6247` | M6 asynchronous Settings; direct parent of M7 checkpoint |
| `18174e1b8c0ce276aa294275e195b2e54c498075` | M7 local relay + bounded Google diagnostics/wait, retained final 163/27 evidence |

All four full owner-supplied anchors passed `git merge-base --is-ancestor <SHA> HEAD`
(exit 0). No resets, migrations or history rewriting were performed.

Untracked and deliberately excluded: `QuMail-1.0-Research-Audit-Specification.pdf`
(reference), `Start-QuMailDemo.ps1` (presentation artifact),
`docs/operations/m2-reviewer-request.md` (preserved local reviewer draft). Ignored
environments/native builds, `tmp/m7/Start-GoogleAcceptance.ps1`, diagnostic logs,
test stores and client/vault configuration stay private. Do not recursively clean tmp.

The user interrupted launcher troubleshooting to request this handover. The private
wrapper still targets `%LOCALAPPDATA%\QuMailAcceptance\2026-10-22-google-m7\acceptance.sqlite`.
The tool shell and even an escalated tool shell saw that file; **normal desktop
File Explorer explicitly could not find its parent folder**, reproducing the user's
PowerShell failure. This is observed execution-context/filesystem visibility
divergence; the underlying virtualization mapping has not been established.
Do not claim the old vault was deleted or recovered. Do not move/copy it or its master.

Prepared but **untested**: ignored `tmp/m7/QuMail-Desktop-DryRun.lnk`, a pythonw GUI
shortcut to current main.py with a distinct proposed desktop path
`%LOCALAPPDATA%\QuMailAcceptance\2026-11-01-desktop\acceptance.sqlite` and the
owner-supplied client-file reference. It was not launched. No replacement database,
credential-store entry or account was created. It bypasses the PowerShell preflight
and is not a qualified launcher. Keep private path contents out of committed docs.

Stopping-point process check used Win32_Process names/paths only and found **no**
python/pythonw, QuMail native helper, cargo or rustc process. The initial restricted
CIM query was denied; the authorized read-only query succeeded. No process was
killed. No known irreversible operation is pending. File Explorer remains open;
unrelated desktop applications were not closed. Past A enrollment's durable result
is unknown; inspect only the deliberately selected vault when access is established.
No agent-observed external send or Unknown SMTP outcome exists to retry.

## Evidence identity and milestone reconciliation

Handover-only check recomputed SHA-256 for all **17** `inputs` and **one** `native`
entry in [M7 final manifest](../operations/evidence/m7/checkpoint-input-hashes.json):
zero mismatches. Read retained normal/reverse outputs: 163 passed in 122.39 s and
27 passed in 29.42 s. No new runtime tests were run for this documentation task.
The manifest's `head=8eebb5e…` explicitly denotes the parent of tested dirty inputs;
`18174e1…` committed those inputs. Do not attribute new tests to unchanged parent HEAD.

| §54 milestone | Verified disposition | Evidence and exact remaining acceptance |
|---|---|---|
| M1 reproducible baseline | **COMPLETE at research-baseline scope** | Retained [hosted success JSON](../operations/evidence/hosted-success-run.json) names 023c941, completed/success; [run 37128055379](https://github.com/uzx-02/QuMail/actions/runs/37128055379), [Windows](https://github.com/uzx-02/QuMail/actions/runs/37128055379/job/111217345728), [Ubuntu](https://github.com/uzx-02/QuMail/actions/runs/37128055379/job/111217345547). 37 distinct tests/platform in normal/reverse/seed orders; five legacy warnings each, zero skips/failures. Historical records inspected, not a new hosted execution. [M1 validation](../operations/m1-validation.md) |
| M2 protocol/provider/policy | **PARTIAL: engineering proof complete; external review pending** | 12 ordinary + five diagnostic tests, same 17 in normal/reverse; Sequoia↔rPGP, vectors, composite negatives and header fixtures. [Validation](../operations/m2-validation.md), [review package](../operations/m2-external-review.md), [ADR 003](../adrs/003-m2-provider-proof.md). External composition/secret-boundary review remains actual exit requirement; ADR 004 authorizes further development, not M2 sign-off. |
| M3 identity/vault | **Implemented bounded engineering; full acceptance PARTIAL** | Real disposable Windows secure-store/recovery + synthetic OAuth; original 54 integrated cases in both orders, three native tests; 54 rerun within M7 combined suite. [M3 validation](../operations/m3-validation.md). Live Google/clean user-session evidence and independent enrollment/recovery review remain; one-device limit explicitly satisfies the allowed limited mode. Yahoo unavailable. |
| M4 durable sending | **Implemented/integrated; full acceptance PARTIAL** | 85 normal/reverse controlled SMTP/TLS cases at b00693c; later M6 uses Gmail adapter. [TLS validation](../operations/m4-smtp-tls-validation.md), [M6 workflow regression](../operations/m6-validation.md). Frozen bytes, crash/uncertainty/ownership proved locally; actual Gmail submission/receipt evidence and review pending. Older “no real adapter” record is superseded, not current engineering gap. |
| M5 standard MIME | **Implemented bounded profile; full acceptance PARTIAL** | 55 Python cases each order + two native tests; independent crypto exchange each way, shared MIME wrapper. [M5 validation](../operations/m5-validation.md). Independent MIME-peer acceptance unexecuted, historical signer expiry/revocation policy unqualified, protocol/parser review and production profile approval pending. |
| M6 useful workflows/UI | **Local Windows engineering complete at bounded scope; full acceptance PARTIAL** | 8eebb5e: 82 M6 + 54 M3, 17 Settings reverse. M7 later: 96 M6 + 54 M3 + 13 relay =163 normal, 27 reverse subset, zero skips/warnings. [Settings validation](../operations/m6-settings-validation.md), [M7 validation](../operations/m7-validation.md). Desktop launch handoff is now a concrete operational gap; live Google and human usable-security/accessibility walkthrough remain. Automated Qt tests are not independent approval. |
| M7 optional extension | **Locally qualified relay-only development** | 13 relay cases, real mTLS/provider ciphertext and eight-process/128-request lease race; [M7 validation](../operations/m7-validation.md), [ADR 009](../adrs/009-m7-local-ciphertext-relay.md). Independent backend/identity review pending before production. Owner explicitly excluded cloud deployment and QKD; neither is an implementation blocker for approved scope. No full cloud/production M7 sign-off. |
| M8 release assurance | **Not implemented as release milestone** | M1 CI/locks are useful foundations, not a signed/reproducible modern client distribution. Mandatory release/review/platform/license/migration/performance gates remain. |

Google actual outcomes have **one authoritative record**:
[m6-google-acceptance.md](../operations/m6-google-acceptance.md). Desktop client/test
users configured; real browser callback/token exchange reached strict verification;
token-time rejection diagnosed; bounded full-reverification wait implemented/tested.
Owner's possible A enrollment is not verified. B, refresh, retrieval/flags, the three
test sends and recipient/archive/attachment/reply/forward outcomes remain unverified.
No sample data substitutes for these steps.

## Documentation checkpoint verification

No runtime/source/lock/native/CI edits and no new engineering-suite execution.
`git diff --check` passed; `main.py --help` exited 0 without launching Qt or OAuth.
A local checker resolved all relative Markdown links in the 14 touched documents
and checked referenced inline source/artifact paths. PowerShell examples were parsed
with `System.Management.Automation.Language.Parser.ParseInput`, not executed;
two historical illustrative angle-bracket commands were changed to comments.
Retained test outputs/JSON evidence and canonical specification remain byte-for-byte
unchanged. Existing status/architecture/ADR history is retained below new annotations.
The only paused engineering artifact is the private untested GUI shortcut; it is
excluded from the documentation commit along with all unrelated/private files.

## Owner decisions and platform-goal amendment

This explicit roadmap amendment records the 2026-11-01 owner instruction: **Windows
and Android are product delivery goals**, while current implementation is Windows.
It does not change canonical M1–M8 numbering or claim Android support. No Android
manifest, Gradle project, Kotlin/Java/Dart source was found in tracked files or the
ordinary source inventory. Installed dependencies/build caches are not an Android app.

ADRs [004](../adrs/004-m3-development-exception.md),
[005](../adrs/005-m4-development-ordering-and-outbox.md),
[006](../adrs/006-m5-development-message-boundary.md),
[007](../adrs/007-m6-gmail-mailbox-slice.md),
[008](../adrs/008-m6-mail-workflows.md),
[009](../adrs/009-m7-local-ciphertext-relay.md) preserve bounded development exceptions.
Independent reviews are deferred to before production enablement/security release;
do not require routine reconfirmation to continue local engineering. No exception
creates independent approval. Cloud relay is outside current scope. Presentation-only
features have ended; preserve harnesses/evidence and functioning frontend boundaries.

## Ordered work items and stopping boundaries

Priority is an execution order, not new milestone requirements. Live inputs can
block an acceptance step without blocking independent local work. Do not expand
core scope to enterprise features or hardware before delivery.

| Priority / dependency | Requirement and components | Bounded behavior / evidence / external input / stop |
|---|---|---|
| **P0 next: desktop launch handoff**; current source | QM-DOC-001; launcher/main/Settings, docs | Resolve actual desktop vs tool path, choose explicitly distinct new vault if needed, reach Settings in normal desktop without creating/enrolling/sending. Verify visible controls and no silent data replacement; owner performs creation/manual tests. Input: explicit private client path and owner selection of vault. Stop with one tested command and accurate click steps/local checkpoint. |
| P1 after launch: live Google | QM-ID-002, MAIL-001/004/005, T06/T07/T12; Google, mailbox, SMTP, outbox | Execute existing manual checklist with owner A/B, actual refresh, Seen checks, public-cert verification, A→B attachment/archive, B→A reply/forward only. Fix concrete findings. Input: owner browser actions, consent, controlled accounts; no arbitrary send permission. Stop with sanitized per-step results and exact source SHA, not a preparation-only completion claim. |
| P1 independent local/human walkthrough | §54 M6 T12/T15; UI/Settings/session | Owner keyboard/focus, labels, cancellation and account switch walkthrough; fix concrete defects with focused tests. Input: human operator/assistive technology where claimed. Stop at bounded Windows acceptance record, not automated “human approval.” |
| P2 interoperability/profile/history | QM-INT-001, ID-005; M5 MIME/OpenMessage | Qualify exact protected-header policy with an independent MIME peer; explicitly decide historical expired/revoked signer verification with authenticated time/context. Keep original bytes/history. Inputs: capable independent implementation, reviewer. Stop at corpus + ADR/profile decision; no silent downgrade. This is distinct from already-complete raw crypto exchange. |
| P2 declared product limits | QM-PERF-001/002, §§42/54; vault/MIME/UI | Measure current limits and justify a release limit or implement a bounded increase with hostile-input, storage, crash and responsiveness evidence. Current 256 KiB wire/16 KiB attachments are not the spec's proposed 25/15 MiB experience. Stop at one documented limit/qualification checkpoint; no unchecked constant bump. |
| P2 shared boundary consolidation | QM-SEC-001, §53; M3/M4/M5 imports | After interface freeze, move shared modules mechanically in small checkpoints; retain compatibility shims, bytes and contracts. See CODEBASE_MAP. No live inputs needed. Stop per module with import/affected regression proof; no concurrent protocol redesign. |
| P2 Android feasibility, then delivery | Platform amendment; M2/M3/M5/M6 contracts | Follow Android table below; first prove selected provider/ABI and Keystore custody, then UI/mail. Input: devices, toolchain/client configuration; stop feasibility ADR before claiming runnable client. |
| P3 release assurance | §54 M8, T13/T14; CI/packaging/licenses/runbooks | Resolve project/Qt/transitive licenses, native warning/side-channel/provider and enrollment/recovery/parser review, shipped-path High findings, signed builds/updates/SBOM, performance/recovery drills and migration rollback. Input: owner license decision, qualified independent reviewers, signing identities. Stop at reproducible review artifacts; release needs separate authorization. |
| P3 compatibility gate | ADR 002, §55; legacy readers | Obtain original unavailable 0.14.1 artifact and authentic historical fixtures legally/safely; test unchanged readers or document incompatibility. No fabricated fixture equivalence. Stop at explicit compatibility matrix; no mass migration. |
| Optional later providers | §43/provider-specific authorization; modern adapters | Yahoo remains explicitly unavailable; add only with bounded owner scope, maintained provider flow and controlled live evidence. Do not reuse Google token semantics or passwords. Stop per provider acceptance. |
| Optional excluded cloud/QKD | §54 M7 conditional requirements | Keep excluded unless owner reopens scope; cloud requires real infrastructure/IAM/retention review, real QKD requires paired authenticated hardware evidence. No work now. |
| Last: hardware addon | §44/provider boundaries | Research only after core Windows/Android; [HARDWARE_ADDON](HARDWARE_ADDON.md). Stop at characterization/decision, never auto-enable entropy use. |

## Android delivery track — proposal, not existing support

Smallest justified approach: retain Windows UI, evaluate a **native Kotlin/Jetpack
Compose** Android shell and a narrow Rust/JNI cryptographic boundary using the exact
profile. Reuse protocol fixtures/contracts rather than assuming Python/PyQt, Win32
Credential Manager, Windows process locks or `.exe` helpers run on Android. Do not
start by rewriting the entire Windows core. Compose is an official Android UI option;
choice is a proposal, not a measured port result. [Official Compose documentation](https://developer.android.com/develop/ui/compose/documentation).

| Order / dependency | Decision / work | Required acceptance and checkpoint |
|---|---|---|
| A1 before UI | Pin Android SDK/NDK/minimum API and Rust/OpenSSL versions; build exact candidate for arm64-v8a, then emulator ABI if needed. License and upstream capability check. | Independent Windows↔Android primitive/packet vectors and composite negative cases on real device; reproducible ABI artifacts/hashes. Windows no-asm/MSVC evidence cannot transfer. Stop feasibility ADR if unsupported; no substitution. [NDK ABI documentation](https://developer.android.com/ndk/guides/abis) |
| A2 after A1 | Narrow JNI boundary with structured errors, bounded buffers, complete verification before Java-visible plaintext; choose process isolation vs in-process crash implications. | Oversize/malformed/panic/process-death cases, no partial success. Shared M2 diagnostic accessor must not ship. Stop at provider adapter test library. |
| A3 custody/identity | Keystore-backed wrapping key for encrypted account records; determine device algorithms/security level/auth policy and invalidation behavior. PQ private keys may require software use after unwrap. | Fail closed on lost/unavailable key; lock/reboot/biometric-change/process-death and clean restore tests. No claim hardware-backed ML-KEM/ML-DSA without measured support. [Android Keystore](https://developer.android.com/privacy-and-security/keystore) |
| A4 identity and app lifecycle | Provision Android-specific OAuth client/package/signing identity and supported provider flow; no Desktop JSON/loopback assumption. Immutable account context and durable work ownership. | Actual browser/account/refresh/cancel mismatch checks with supplied accounts; process recreation cannot install wrong tokens or replay submit automatically. [Google native-app guidance](https://developers.google.com/identity/protocols/oauth2/native-app) points to Android-specific authorization. |
| A5 usable client | Native plain-text inbox/compose with encrypted draft/outbox, PEEK/explicit Seen, verified contact ceremony, reply/forward. Lifecycle-aware background scheduling. | Real retrieval and Windows↔Android protected send both ways, archive/attachment, offline/restart/Unknown tests. WorkManager scheduling is not exactly-once SMTP. [Android persistent work](https://developer.android.com/develop/background-work/background-tasks/persistent) |
| A6 storage/privacy | Scoped storage and explicit document-provider export; decide screenshot/clipboard/notification redaction and backup exclusions. | Malicious names/provider failures/no overwrite/lock cleanup; no plaintext cache/notification preview by default. Device/API tests required; not implemented here. |
| A7 device enrollment | Maintain one-active-device rule: explicit supported transfer/archive restore; no simultaneous private-key clones as enrollment. | Windows↔Android recovery-format and prior-device retirement/root-replacement trust tests. OAuth login never recovers root. Any multi-device feature needs separate design/authorization. |
| A8 platform delivery/release | Controlled signed APK for device testing, signing-key custody/update policy; distinguish installable judge build from publishable release. | Actual supported devices/ABIs, accessibility/performance/security acceptance, dependencies/license/provenance, upgrade/rollback. No APK exists or was qualified in this task. |

Judge-facing exit: real controlled accounts/services, honest trust/delivery states,
stable launch, recoverable operations and no presentation substitute. Production exit:
all applicable M8 and upstream review/license/platform gates, not merely a successful
walkthrough. Delivery goal does not authorize cloud publishing, raw-key sharing or
automatic multi-device enrollment.
