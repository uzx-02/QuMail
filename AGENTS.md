# Instructions for successor agents

- Read [AI_HANDOVER.md](AI_HANDOVER.md) first, then only relevant supporting sections.
  Inspect `git status --short`, branch, HEAD and pending processes before mutation.
  If repository access is absent, say so; never invent source/execution facts.
- Canonical requirements: `QuMail-1.0-Research-Audit-Specification.md`; PDF is reference.
  Apply owner decisions/ADRs, especially 004–009 and the Windows/Android roadmap
  amendment. Do not edit the canonical spec to manufacture milestone completion.
- Work one bounded task at a time. State intended behavior and acceptance evidence
  before coding. Reuse maintained dependencies and existing contracts; no broad
  rewrite, provider substitution, automatic downgrade or gratuitous audit restart.
- Modern entry: `main.py --dev-mailbox --dev-vault <explicit path>`; optional explicit
  Google client and Gmail-send flag. Default startup is legacy. Never route modern
  account/key records into TQR, simulator or server-decrypting portal.
- `experiments/m3`, `m4`, `m5` contain real application dependencies. Preserve frozen
  M1/M2 evidence, legacy readers/data, private vaults, recovery material and unrelated
  dirty/untracked files. Stage explicit intended files; no binaries, environments,
  client JSON, tokens, private evidence, reference PDF or reviewer draft by accident.
- Preserve immutable account/vault ownership, generations and synchronized commit
  guards; workers own SQLite connections, widgets stay on GUI thread. Cancellation
  after commit/possible remote side effect is not rollback. Keep owner receipts.
- Verification precedes plaintext release. Recipient trust is explicit. Prepared
  bytes persist before SMTP and remain identical on retry; Unknown needs inspection.
  Backup-secret acknowledgment precedes package persistence; backup is not transfer.
  Preserve PEEK/UID identity, explicit Seen changes and no-clobber attachment export.
- Use `.venv-m1-clean`/existing helpers where present. Run meaningful affected tests,
  then appropriate checkpoint regressions. Plain pytest selects legacy tests only.
  Never hide crypto failures/skips; do not rerun all historical suites for docs.
- Keep verbose output in local logs and user feedback concise. Record actual command,
  result, source/hash identity, platform and limits; update status each checkpoint.
  Distinguish synthetic, source-inspected, executed, live and independently reviewed.
- Ask for missing external configuration early and continue independent work.
  No passwords/tokens/recovery secrets in chat or logs; no personal cache discovery.
  Tool filesystem visibility may differ from the normal Windows desktop; verify in
  the execution context being claimed. Never silently replace an inaccessible vault.
- Independent review remains deferred for development, required before production/
  security release. Do not block routine local work merely because review is absent;
  never call AI inspection or passing tests independent approval.
- Local-only M7 is the approved scope; no cloud qualification claim. Android and
  ESP32 are future tracks, not implemented support. No deployment, paid resources,
  push, merge, release, migration or unrelated external messages without authorization.
