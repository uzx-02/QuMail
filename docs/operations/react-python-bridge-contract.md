# React-Python Bridge Contract & API Specification

## 1. Overview

The QuMail 1.0 desktop architecture uses Microsoft Edge WebView2 (`pywebview`) to host a React 19 single-page application communicating with an underlying Python 3.12 backend engine.

The Python class `QuMailJsApi` (in `launch_react_desktop.py`) is exposed to the frontend window environment at `window.pywebview.api`.

The frontend interacts with the bridge through `ApiService` (`frontend/src/lib/api.ts`).

---

## 2. Readiness Probe & Lifecycle Handshake

To prevent race conditions where React components fire data requests before WebView2 binds the bridge:
1. `api.waitForBackend(timeoutMs = 6000)` executes immediately upon application mount.
2. It probes `window.pywebview.api.ping()` and listens for the `pywebviewready` DOM event.
3. Only after `ping()` returns `pong: true` does the UI dispatch account, mailbox, or hardware queries.

```typescript
interface PingResponse {
  pong: boolean;
  version: string;
  timestamp: number;
  authenticated: boolean;
  sessionState: 'SIGNED_OUT' | 'AUTHENTICATING' | 'VAULT_READY' | 'MAILBOX_READY' | 'ERROR';
  vaultState: 'UNINITIALIZED' | 'LOCKED' | 'UNLOCKED';
}
```

---

## 3. Bridge Method Specifications

### 3.1 Session & Account Management

#### `getSessionStatus()`
Returns the authoritative session state machine snapshot.
- **Arguments:** None.
- **Returns:**
  ```typescript
  interface SessionStatus {
    sessionState: 'SIGNED_OUT' | 'AUTHENTICATING' | 'VAULT_READY' | 'MAILBOX_READY' | 'ERROR';
    vaultState: 'UNINITIALIZED' | 'LOCKED' | 'UNLOCKED';
    account: {
      email: string;
      displayName: string;
      organization: string;
      isEnrolled: boolean;
      kemAlgorithm: string;
      dsaAlgorithm: string;
      keyFingerprint: string;
      hsmBound: boolean;
    } | null;
    lastError: {
      code: string;
      message: string;
      timestamp: number;
    } | null;
    kemAlgorithm: string;
    dsaAlgorithm: string;
  }
  ```

#### `getAccount()`
Returns the active account profile.
- **Arguments:** None.
- **Returns:**
  ```typescript
  interface AccountProfile {
    email: string;
    displayName: string;
    organization: string;
    isEnrolled: boolean;
    kemAlgorithm: string;
    dsaAlgorithm: string;
    keyFingerprint: string;
    sessionState: string;
    vaultState: string;
    hsmBound: boolean;
  }
  ```

#### `connectGoogle()` (alias: `googleAuth()`)
Triggers the browser-based Google OAuth PKCE flow.
- **Arguments:** None.
- **Returns:**
  ```typescript
  interface AuthResponse {
    success: boolean;
    email?: string;
    displayName?: string;
    account?: AccountProfile;
    sessionStatus?: SessionStatus;
    messages?: EmailMessage[];
    message?: string;
  }
  ```

#### `lockVault()`
Locks the M3 cryptographic vault and clears active keys from memory.
- **Arguments:** None.
- **Returns:** `boolean` (`true` on successful lock).

#### `unlockVault(passphrase?: string)`
Unlocks an existing M3 vault.
- **Arguments:** `passphrase?: string` (optional).
- **Returns:** `{ success: boolean; sessionStatus?: SessionStatus; message?: string }`.

#### `logout()` (alias: `logoutAccount()`)
Revokes OAuth credentials, purges active session, and locks the vault.
- **Arguments:** None.
- **Returns:** `{ success: boolean; sessionStatus: SessionStatus }`.

---

### 3.2 Google Client Secret Management

#### `checkGoogleConfigured()`
Checks whether a valid Desktop Client ID exists on the host.
- **Returns:**
  ```typescript
  {
    configured: boolean;
    valid: boolean;
    clientId: string;
    source: string;
    tokenExists: boolean;
    authRequired: boolean;
  }
  ```

#### `selectGoogleClientSecret()`
Opens the native Windows file dialog to select a Google `client_secret_*.json`.
- **Validation:** Enforces `"installed"` client type and loopback redirect URIs. Rejects Service Accounts and Web client configurations.
- **Returns:** `{ success: boolean; message: string; clientId?: string }`.

#### `saveGoogleCredentials(clientId: string, clientSecret: string)`
Manually saves Google OAuth credentials for Desktop application flow.
- **Returns:** `{ success: boolean; message: string; clientId?: string }`.

---

### 3.3 Mailbox & Message Operations

#### `fetchInbox()` / `getMessages()`
Retrieves live messages from the authenticated IMAP mailbox.
- **Preserves `BODY.PEEK[]`:** Reading headers and metadata never alters server-side `\Seen` flags.
- **Returns:** `EmailMessage[]`
  ```typescript
  interface EmailMessage {
    id: string;
    sender: string;
    senderEmail: string;
    recipients: string[];
    subject: string;
    snippet: string;
    body: string;
    date: string;
    timestamp: number;
    seen: boolean;
    starred: boolean;
    folder: 'inbox' | 'sent' | 'trash';
    hasAttachments: boolean;
    attachments: Array<{
      id: string;
      filename: string;
      size: number;
      contentType: string;
      verified: boolean;
    }>;
    indicator: {
      badgeLevel: 'SECURE' | 'NEUTRAL' | 'ALERT' | 'CAUTION';
      headline: string;
      description: string;
      actionAdvice: string;
    };
  }
  ```

#### `sendMessage(draft)`
Encapsulates and dispatches an email message.
- **Arguments:**
  ```typescript
  {
    recipients: string[];
    subject: string;
    body: string;
    attachments: any[];
    securityMode: 'pq' | 'standard' | 'weblink';
  }
  ```
- **Returns:** `{ success: boolean; id?: string; message?: string }`.

---

## 4. Hardware Security & Entropy

#### `getHSMStatus()`
Reports the real-time status of physical TRNG hardware or ETSI QKD nodes.
- **Returns:**
  ```typescript
  {
    mode: 'software' | 'usb_serial' | 'etsi_qkd';
    isHardwareActive: boolean;
    activeDeviceName: string;
    activePort: string;
    baudRate: number;
    healthStatus: string;
    shannonEntropy: number;
    bytesIngested: number;
  }
  ```

#### `sampleEntropy()`
Samples 32 bytes of high-entropy randomness from the physical entropy pool.
- **Returns:** `{ success: boolean; hex: string; rate: number }`.

---

## 5. Security Boundary Guarantees

1. **Zero Secret Exposure:** Private keys, seed phrases, raw refresh tokens, and vault master keys are never serialized to JSON or returned across the bridge.
2. **Type Safety:** TypeScript definitions in `frontend/src/types/` mirror Python backend dataclasses strictly.
3. **Fail-Closed Principle:** Any bridge exception returns `{ success: false, message: ... }` and transitions the UI to a safe state without exposing crash callstacks.
