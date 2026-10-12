# M4 durable outbox and controlled SMTP/TLS development proof

Opt-in development only. Default application startup does not import M4. This
qualification uses numeric loopback destinations, disposable accounts/vaults and
explicitly synthetic authorization. ADR 004/005 allow development while live
Google acceptance and independent review remain pending. No production MIME,
external mail, existing credential cache or user-data migration is involved.

## Run the development panel

Use the existing locked M1 Python environment and unchanged M3 helper built with
the exact M2 Sequoia/OpenSSL inputs. No dependency or native input is added. On the
validated Windows desktop logon session, from the repository root:

```powershell
./.venv-m1-clean/Scripts/python.exe -m experiments.m4.loopback_demo --loopback
./.venv-m1-clean/Scripts/python.exe -m experiments.m4.loopback_demo --loopback --scenario auth-reject
./.venv-m1-clean/Scripts/python.exe -m experiments.m4.loopback_demo --loopback --scenario final-loss
```

Each run creates two independent synthetic accounts, provider keys and prepared
operations in a disposable encrypted vault. Select/unlock an account, inspect its
prepared operation, then submit to the controlled server. The three scenarios
display Accepted, Failed and Unknown respectively. Switching accounts and locking
cancel the old lease and discard its late display result. Network work runs on
workers, outside the GUI thread and outside SQLite writer transactions.

Recover checks durable interrupted attempts without resending. Retry requires an
explicit duplicate-risk confirmation and returns the operation to Prepared; it
does not send automatically. Submit is a separate action. An unchanged rejecting
interactive server still rejects the retry. Receipt export writes a separate new
file and cannot change delivery status. Closing the harness joins cancelled
workers, removes its Windows credential entry and deletes its fixture storage.
This disposable harness is not a persistent user mailbox.

The headless workflow reopens the vault, checks recovery, explicitly authorizes a
retry for Failed/Unknown, switches the fixture to success, and verifies byte
identity and receipt-failure isolation:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
./.venv-m1-clean/Scripts/python.exe -m experiments.m4.loopback_demo --loopback --smoke
./.venv-m1-clean/Scripts/python.exe -m experiments.m4.loopback_demo --loopback --smoke --scenario auth-reject
./.venv-m1-clean/Scripts/python.exe -m experiments.m4.loopback_demo --loopback --smoke --scenario final-loss
```

The original deterministic simulation remains available with
`python -m experiments.m4.harness --simulate`. It is labeled simulation and does
not substitute for the actual socket/TLS cases in the expanded suite.

## Reproduce validation

```powershell
./.venv-m1-clean/Scripts/python.exe -m experiments.m4.run_tests
./.venv-m1-clean/Scripts/python.exe -m experiments.m4.run_tests --reverse
./.venv-m1-clean/Scripts/python.exe -m experiments.m3.run_tests
$env:OQS_INSTALL_PATH = Join-Path $PWD 'tmp/oqs-install'
./.venv-m1-clean/Scripts/python.exe -m pytest -q
uv --cache-dir tmp/m4-uv-cache pip check --python .venv-m1-clean/Scripts/python.exe
./.venv-m1-clean/Scripts/python.exe -m experiments.m4.audit_tls
```

Run normal and reverse sequentially. The runner verifies distinct test identities
and zero skips. Tests use disposable Windows secure-storage entries, actual local
TLS sockets, offscreen Qt, child processes and process termination. They never use
real provider credentials. Certificate private files stay in ignored temporary
paths; retained observations contain command names, state, counts and hashes,
never AUTH values, keys or bodies. Linux execution is not claimed.

`audit_tls` verifies current inputs/outputs and preserved historical manifests.
The original `audit_snapshot` describes b833e8b and is not a validator for the
changed working tree. Current evidence, versions and the acceptance table are in
[the SMTP/TLS report](../../docs/operations/m4-smtp-tls-validation.md).

## Interfaces and state contract

- `model.py`: immutable operation/binding/envelope/context handles, structured
  results and protocol interfaces; no Qt or network imports.
- `services.py`: preparation, durable claim/result ordering, recovery, explicit
  retry, reconciliation and separate receipt export.
- `vault_adapter.py`: short M3 account-authenticated transactions and frozen sender,
  recipients, payload/profile/key/archive references.
- `ownership.py`: nonblocking OS operation lock, released by process death;
  no expiry-based stealing and no account-wide lock during network I/O.
- `smtp_transport.py`: bounded SMTP, mandatory verified STARTTLS/fresh EHLO before
  resolving a credential handle, account/sender/mail-scope checks and XOAUTH2.
- `smtp_fixture.py`: disposable CA/server, synthetic resolver and explicitly
  experimental transport envelope builder.
- `outbox_panel.py`: coherent M3 account views/leases and generation-checked worker
  publication. `loopback_demo.py` owns fixture lifetime and deterministic teardown.
- `tests/crash_worker.py`: child-process boundaries for actual process kill,
  competition and socket/result-persistence tests.

Preparation persists the exact payload before any SMTP connection. The provider
fixture supports one encrypted recipient; unsupported counts fail closed. Separate
transport-level tests cover all-required-recipient handling and dot transparency.
The fixture builder puts existing provider ciphertext in a standard MIME base64
container. This is not M5's complete protected-header/PGP-MIME profile.

Submission accepts an existing operation ID, commits Submitting with an attempt
UUID, then performs network I/O under per-operation ownership. A short final
transaction checks that identity before recording the observed outcome. Final
successful DATA means Accepted, not delivery or decryptability. Rejection is
Failed; loss after possible acceptance is Unknown. Cleanup or receipt failure
cannot overwrite acceptance. Failed result persistence returns Unknown and leaves
the durable interrupted attempt for recovery. Three attempts is the maximum.
No implicit retry or exactly-once SMTP guarantee exists.

Selection/unlock creates a fresh lease; lock cancels it. Observed outcomes may be
persisted for their original authenticated account after a switch, while the UI
rejects stale publication. Archive references are not sender decryptability.
Earlier prepared fixtures lacking a frozen sender fail closed without migration.
Use new disposable vaults; M3 backup restore does not remap M4 operation IDs.

Cooperating workers must use the same canonical local vault path. Hostile same-user
file replacement/aliasing, network filesystems, machine power loss and rollback
resistance are unqualified. The POSIX locking branch is inspected, not executed.
Legacy F07 remains open at its unchanged entry point. Full M4 remains partial;
the requested controlled SMTP/TLS development scope is complete. Production MIME
integration, live-provider acceptance and production approval remain separate work.
