# QuMail Cryptographic Key Lifecycle & Rotation Operations
## Subkey Expiration, Authorized Rotation, Historical Verification & Memory Hygiene

**Milestone:** M7 — Module 1.6  
**Document:** Operations & Key Management Guide  
**Author:** Antigravity (Implementation Engineer)  
**Reviewer:** ChatGPT (Technical Lead & Security Architect)  
**Project Owner:** Mohammed Uzair Shaikh  
**Date:** 2026-11-09  

---

## 1. Overview and Operational Philosophy

Cryptographic security in QuMail depends on maintaining active, authorized subkeys while managing lifecycle transitions cleanly. 

WS-02 introduces automated lifecycle management that:
1. Monitors subkey validity periods and provides proactive renewal warnings before keys expire.
2. Supports authorized key rotation without breaking historical message readability.
3. Defends against unauthorized root key substitution.
4. Preserves historical signature verification under RFC 4880 and RFC 9580 time-aware rules.

---

## 2. Key Validity Periods & Proactive Expiration Alerts

### 2.1 Subkey Validity Rules
* Subkeys are generated with an initial validity period of **365 days (1 year)** from creation.
* Primary certification root keys do not expire by default, but can be explicitly retired or revoked.

### 2.2 Expiration Monitoring (`core/key_lifecycle.py`)
`evaluate_key_expiration` monitors subkeys and categorizes validity:

| State | Condition | UI Behavior | Action Required |
|---|---|---|---|
| `ACTIVE` | More than 30 days until expiration | Normal operation | None |
| `EXPIRING_SOON` | 30 days or fewer until expiration | Amber notification banner | Prompt one-click subkey rotation |
| `EXPIRED` | Expiration timestamp has passed | Red security warning | Subkey rotation required; sending blocked |
| `REVOKED` | Explicit revocation signature issued | Red security alert | Immediate retirement of key material |

---

## 3. Subkey Rotation vs. Key Replacement

A critical security distinction enforced by QuMail is distinguishing **authorized subkey rotation** from **unauthorized key replacement**:

```
AUTHORIZED SUBKEY ROTATION                      UNAUTHORIZED ROOT REPLACEMENT
Root Key: AAAA (Unchanged)                      Root Key: AAAA -> BBBB (Changed!)
Old Signing: S1                                 Old Signing: S1
New Signing: S2 (Signed by Root AAAA)           New Signing: S2
Old Encryption: E1                              Old Encryption: E1
New Encryption: E2 (Signed by Root AAAA)        New Encryption: E2
RESULT: APPROVED (Historical records kept)      RESULT: BLOCKED (CHANGED_BLOCKED alert)
```

### 3.1 Authorized Rotation
When an employee initiates subkey rotation:
1. The local primary root key issues a subkey revocation signature (`0x28`) for the outgoing subkeys with reason `KeyRetired`.
2. The primary root key generates and certifies fresh post-quantum signing and encryption subkeys.
3. The outgoing subkey fingerprints are appended to the contact's `retired_subkeys` list in the vault.
4. **Anti-Rollback Invariant:** If a remote correspondent or server attempts to present a subkey that was previously retired, `experiments/m3/vault.py:import_contact` rejects the transaction with `BoundaryError(Code.TRUST)`.

### 3.2 Unauthorized Replacement
If an incoming message or directory lookup presents a **different primary root fingerprint** for an already established contact:
* QuMail classifies the transition as `UNAUTHORIZED_ROOT_REPLACEMENT`.
* The contact's state is set to `CHANGED_BLOCKED`.
* Outbound encryption to that recipient is blocked, and inbound messages display a prominent red `Security Alert — Key Changed Unexpectedly` warning.
* Communication remains blocked until the change is verified through an approved out-of-band channel or enterprise administrator intervention.

---

## 4. RFC 4880 / RFC 9580 Time-Aware Historical Verification

In standard OpenPGP implementations, when an annual subkey expires, previously received emails signed by that subkey are often erroneously flagged as having "invalid" or "untrusted" signatures.

QuMail implements **time-aware historical signature verification**:

$$\text{Valid}(\text{Signature}) \iff t_{\text{signed}} \ge t_{\text{created}} \land t_{\text{signed}} \le t_{\text{expires}} \land t_{\text{signed}} < t_{\text{revoked}}$$

* If an email was signed on `2026-03-01` by a subkey that was active on that date, and the subkey subsequently expires on `2027-01-01`, opening the message in `2027` evaluates the signature against key status on `2026-03-01`.
* The signature remains historically authentic.
* If, however, a message timestamp postdates key expiration or revocation, verification fails immediately.

---

## 5. Runtime Memory Hygiene & Limitations

### 5.1 Native Provider Memory (Rust)
Inside `qumail-m3-provider.exe` and `qumail-m5-provider.exe`:
* Secret keys and intermediate cryptographic buffers are managed using Rust's memory-safe semantics.
* Sensitive key pairs in Sequoia and OpenSSL are cleared from heap memory upon process drop.
* Subprocess IPC operates over anonymous unidirectional pipes, terminating immediately after each operation.

### 5.2 Python Runtime Memory Limitations (Honest Assessment)
In accordance with Module 1.6 integrity requirements, we explicitly document the limitations of Python runtime memory management:
* In CPython 3.12, strings (`str`) and byte objects (`bytes`) are immutable heap objects.
* While Python variables can be deleted (`del data`) and garbage collection invoked (`gc.collect()`), CPython’s small object allocator does not guarantee immediate zeroization of physical RAM pages.
* Complete in-memory zeroization of sensitive plaintext buffers requires mutable `bytearray` structures and native memory wiping (`memset_s` / `SecureZeroMemory`), which is scheduled for formal hardening under **WS-07 (Forensic Hardening & Replay Armor)**.
