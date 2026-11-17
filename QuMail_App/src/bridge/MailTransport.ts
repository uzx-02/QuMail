import * as AuthSession from 'expo-auth-session';
import * as WebBrowser from 'expo-web-browser';
import * as SecureStore from 'expo-secure-store';
import * as Crypto from 'expo-crypto';
import {
  EmailMessage,
  AccountSession,
  RecipientInfo,
  OutboundMessage,
  DEFAULT_GOOGLE_CLIENT_ID,
} from '../types';
import {
  cryptoBridge,
  stringToUint8Array,
  uint8ArrayToString,
  uint8ArrayToBase64,
  base64ToUint8Array,
} from './CryptoBridge';
import { vaultManager } from './VaultManager';

WebBrowser.maybeCompleteAuthSession();

export interface MailTransport {
  signIn(): Promise<AccountSession>;
  signInWithGoogle(clientId?: string): Promise<{ email: string; displayName?: string; avatarUrl?: string }>;
  signInWithAppPassword(email: string, appPassword: string): Promise<AccountSession>;
  signOut(): Promise<void>;
  fetchMessages(folder: string, limit?: number): Promise<EmailMessage[]>;
  sendMessage(msg: OutboundMessage): Promise<{ id: string }>;
  saveDraft(msg: Partial<OutboundMessage>): Promise<{ id: string }>;
  deleteMessage(id: string): Promise<void>;
  markRead(id: string, seen: boolean): Promise<void>;
  toggleStar(id: string): Promise<void>;
  checkRecipient(email: string): Promise<RecipientInfo>;
  ensureDeviceEnrolled(email: string): Promise<string | null>;
  hasValidDirectorySession(): Promise<boolean>;
}

const GMAIL_TOKEN_KEY = 'qumail_gmail_access_token_v1';
const GMAIL_REFRESH_TOKEN_KEY = 'qumail_gmail_refresh_token_v1';
const GMAIL_APP_PASS_KEY = 'qumail_gmail_app_password_v1';
const GMAIL_ACCOUNT_EMAIL_KEY = 'qumail_gmail_account_email_v1';
const GOOGLE_ID_TOKEN_KEY = 'qumail_google_id_token_v1';
const DEVICE_ID_KEY = 'qumail_device_id_v1';
const DIRECTORY_SESSION_TOKEN_KEY = 'qumail_directory_session_token_v1';
const CLOUDFLARE_WORKER_URL = 'https://qumail-directory-dev.uzair-shaikh-sec-e24.workers.dev';

export function formatMailDate(timestamp: number | string | Date): string {
  const d = new Date(timestamp);
  if (isNaN(d.getTime())) return '';
  const now = new Date();
  const isToday = d.toDateString() === now.toDateString();
  if (isToday) {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  const isThisYear = d.getFullYear() === now.getFullYear();
  if (isThisYear) {
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  }
  return d.toLocaleDateString([], { month: 'numeric', day: 'numeric', year: '2-digit' });
}

function normalizeEmailForDirectory(raw: string): string {
  if (!raw || typeof raw !== 'string') return '';
  let clean = raw.trim().toLowerCase();
  clean = clean.replace(/^[<"']+|[>"']+$/g, '').trim();
  const parts = clean.split('@');
  if (parts.length !== 2) return clean;
  let [local, domain] = parts;
  if (domain === 'gmail.com' || domain === 'googlemail.com') {
    domain = 'gmail.com';
    local = local.replace(/\./g, '');
    const plusIdx = local.indexOf('+');
    if (plusIdx !== -1) local = local.substring(0, plusIdx);
  }
  return `${local}@${domain}`;
}

async function sha256Hex(str: string): Promise<string> {
  return (await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, str)).toLowerCase();
}

function safeStorageKey(email?: string | null): string {
  return (email || '').trim().toLowerCase().replace(/[^a-zA-Z0-9._-]/g, '_');
}

async function getFreshGoogleIdToken(email?: string): Promise<string | null> {
  const normEmail = email ? email.trim().toLowerCase() : '';
  const sKey = normEmail ? safeStorageKey(normEmail) : '';
  const idToken = (sKey && await SecureStore.getItemAsync(`${GOOGLE_ID_TOKEN_KEY}_${sKey}`)) ||
    await SecureStore.getItemAsync(GOOGLE_ID_TOKEN_KEY);
  if (idToken) {
    try {
      const parts = idToken.split('.');
      if (parts.length === 3) {
        const b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
        const pad = b64.length % 4;
        const padded = pad ? b64 + '='.repeat(4 - pad) : b64;
        const payloadStr = uint8ArrayToString(base64ToUint8Array(padded));
        const payload = JSON.parse(payloadStr);
        const exp = payload.exp;
        const now = Math.floor(Date.now() / 1000);
        if (normEmail && payload.email && payload.email.toLowerCase() !== normEmail) {
          // Token is for a different account
        } else if (exp && exp - now > 60) {
          return idToken;
        }
      }
    } catch {
      // ignore
    }
  }

  const refreshToken = (sKey && await SecureStore.getItemAsync(`${GMAIL_REFRESH_TOKEN_KEY}_${sKey}`)) ||
    await SecureStore.getItemAsync(GMAIL_REFRESH_TOKEN_KEY);
  const clientId =
    (await SecureStore.getItemAsync('qumail_google_client_id')) || DEFAULT_GOOGLE_CLIENT_ID;

  if (refreshToken) {
    try {
      const refreshRes = await fetch('https://oauth2.googleapis.com/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          client_id: clientId,
          grant_type: 'refresh_token',
          refresh_token: refreshToken,
        }).toString(),
      });

      if (refreshRes.ok) {
        const refreshData = await refreshRes.json();
        if (refreshData.access_token) {
          if (sKey) await SecureStore.setItemAsync(`${GMAIL_TOKEN_KEY}_${sKey}`, refreshData.access_token);
          await SecureStore.setItemAsync(GMAIL_TOKEN_KEY, refreshData.access_token);
        }
        if (refreshData.id_token) {
          if (sKey) await SecureStore.setItemAsync(`${GOOGLE_ID_TOKEN_KEY}_${sKey}`, refreshData.id_token);
          await SecureStore.setItemAsync(GOOGLE_ID_TOKEN_KEY, refreshData.id_token);
          return refreshData.id_token;
        }
      }
    } catch (err) {
      console.warn('Failed to refresh Google tokens:', err);
    }
  }

  return null;
}

function dearmorOpenPGP(armorText: string): Uint8Array {
  const lines = armorText.split(/\r?\n/);
  let inBody = false;
  const b64Lines: string[] = [];
  for (let rawLine of lines) {
    const line = rawLine.trim();
    if (!inBody) {
      if (line === '') {
        inBody = true;
      }
      continue;
    }
    if (line.startsWith('=') || line.startsWith('-----END PGP')) {
      break;
    }
    if (line.length > 0) {
      b64Lines.push(line);
    }
  }
  if (b64Lines.length > 0) {
    try {
      return base64ToUint8Array(b64Lines.join(''));
    } catch {
      // Fallback to raw text bytes
    }
  }
  return stringToUint8Array(armorText);
}

function buildInnerMime(
  sender: string,
  recipients: string[],
  subject: string,
  body: string,
  date: string,
  messageId: string
): Uint8Array {
  // Base64 encode the body and chunk into 76-character lines (RFC 2045 / RFC 9788)
  const rawBodyBytes = stringToUint8Array(body);
  const b64Body = uint8ArrayToBase64(rawBodyBytes);
  const b64Lines: string[] = [];
  for (let i = 0; i < b64Body.length; i += 76) {
    b64Lines.push(b64Body.slice(i, i + 76));
  }
  const formattedB64Body = b64Lines.join('\r\n');

  const lines = [
    `From: ${sender}`,
    `To: ${recipients.join(', ')}`,
    `Subject: ${subject}`,
    `Date: ${date}`,
    `Message-ID: ${messageId}`,
    `X-QuMail-Profile: QM-OPENPGP-PQ-v1`,
    `X-QuMail-Archive: none`,
    `MIME-Version: 1.0`,
    `Content-Type: text/plain; charset="utf-8"; hp="cipher"`,
    `Content-Transfer-Encoding: base64`,
    `HP-Outer: From: ${sender}`,
    `HP-Outer: To: ${recipients.join(', ')}`,
    `HP-Outer: Subject: Encrypted message`,
    `HP-Outer: Date: ${date}`,
    `HP-Outer: Message-ID: ${messageId}`,
    ``,
    formattedB64Body,
    ``,
  ];

  return stringToUint8Array(lines.join('\r\n'));
}

async function refreshGoogleAccessToken(email?: string): Promise<string | null> {
  const normEmail = email ? email.trim().toLowerCase() : '';
  const sKey = normEmail ? safeStorageKey(normEmail) : '';
  const refreshToken = (sKey && await SecureStore.getItemAsync(`${GMAIL_REFRESH_TOKEN_KEY}_${sKey}`)) ||
    await SecureStore.getItemAsync(GMAIL_REFRESH_TOKEN_KEY);
  const clientId =
    (await SecureStore.getItemAsync('qumail_google_client_id')) || DEFAULT_GOOGLE_CLIENT_ID;

  if (!refreshToken) {
    return null;
  }

  try {
    const refreshRes = await fetch('https://oauth2.googleapis.com/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        client_id: clientId,
        grant_type: 'refresh_token',
        refresh_token: refreshToken,
      }).toString(),
    });

    if (refreshRes.ok) {
      const refreshData = await refreshRes.json();
      if (refreshData.access_token) {
        if (sKey) await SecureStore.setItemAsync(`${GMAIL_TOKEN_KEY}_${sKey}`, refreshData.access_token);
        await SecureStore.setItemAsync(GMAIL_TOKEN_KEY, refreshData.access_token);
        console.log('Successfully refreshed Google OAuth access token.');
      }
      if (refreshData.id_token) {
        if (sKey) await SecureStore.setItemAsync(`${GOOGLE_ID_TOKEN_KEY}_${sKey}`, refreshData.id_token);
        await SecureStore.setItemAsync(GOOGLE_ID_TOKEN_KEY, refreshData.id_token);
      }
      return refreshData.access_token || null;
    } else {
      console.warn('Google token refresh rejected:', refreshRes.status, await refreshRes.text());
    }
  } catch (err) {
    console.warn('Error refreshing Google access token:', err);
  }
  return null;
}

export class CombinedGmailTransport implements MailTransport {
  private messages: EmailMessage[] = [];
  private accessToken: string | null = null;
  private lookupCache: Map<string, { info: RecipientInfo; ts: number }> = new Map();

  async getAccessToken(forceRefresh: boolean = false): Promise<string | null> {
    if (this.accessToken && !forceRefresh) return this.accessToken;

    const storedEmail = (await SecureStore.getItemAsync(GMAIL_ACCOUNT_EMAIL_KEY)) || (await vaultManager.getAccount()).email;
    const sKey = storedEmail ? safeStorageKey(storedEmail) : '';

    let stored = (sKey && await SecureStore.getItemAsync(`${GMAIL_TOKEN_KEY}_${sKey}`)) ||
      await SecureStore.getItemAsync(GMAIL_TOKEN_KEY);

    if (!stored || forceRefresh) {
      stored = await refreshGoogleAccessToken(storedEmail || undefined);
    }

    this.accessToken = stored;
    return stored;
  }

  async hasValidDirectorySession(targetEmail?: string): Promise<boolean> {
    const email = targetEmail || (await SecureStore.getItemAsync(GMAIL_ACCOUNT_EMAIL_KEY)) || (await vaultManager.getAccount()).email;
    const norm = safeStorageKey(email);
    if (norm) {
      const perAccountToken = await SecureStore.getItemAsync(`${DIRECTORY_SESSION_TOKEN_KEY}_${norm}`);
      if (perAccountToken) return true;
    }
    const token = await SecureStore.getItemAsync(DIRECTORY_SESSION_TOKEN_KEY);
    return !!token;
  }

  async ensureDeviceEnrolled(email: string): Promise<string | null> {
    try {
      const normEmail = email.trim().toLowerCase();
      const sKey = safeStorageKey(normEmail);
      const accountDevKey = `${DEVICE_ID_KEY}_${sKey}`;
      let deviceId = await SecureStore.getItemAsync(accountDevKey);
      if (!deviceId) {
        // Generate a stable UUID for this account's device enrollment
        deviceId = Crypto.randomUUID();
        await SecureStore.setItemAsync(accountDevKey, deviceId);
      }
      await SecureStore.setItemAsync(DEVICE_ID_KEY, deviceId);

      const idToken = await getFreshGoogleIdToken(normEmail);
      const accessToken = await this.getAccessToken();
      if (!idToken && !accessToken) {
        console.warn(`Device enrollment skipped: Google authentication tokens are not available for ${normEmail}.`);
        return null;
      }

      // 1. Fetch challenge nonce from Cloudflare Worker
      const chalRes = await fetch(`${CLOUDFLARE_WORKER_URL}/api/v1/auth/challenge`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'User-Agent': 'QuMail-Mobile/1.0',
        },
      });
      if (!chalRes.ok) {
        console.warn('Failed to fetch auth challenge from Cloudflare:', await chalRes.text());
        return null;
      }
      const chalData = await chalRes.json();
      const nonceHex = chalData.nonce_hex;
      if (!nonceHex) {
        console.warn('Challenge response did not contain nonce_hex');
        return null;
      }

      // 2. Fetch secret certificate and public cert from vault for this specific account
      const secretCert = await vaultManager.getSecretCertBytes(normEmail);
      const pubCert = await vaultManager.getPublicCertBytes(normEmail);
      if (!secretCert || !pubCert) {
        console.warn(`Vault certificates not ready for device enrollment of ${normEmail}.`);
        return null;
      }

      // 3. Extract ML-DSA-65 verifying key via directoryProof probe
      const probe = await cryptoBridge.directoryProof(secretCert, stringToUint8Array('probe'));
      const dsaPubBase64 = uint8ArrayToBase64(probe.verifyingKey);
      const fingerprint = await sha256Hex(dsaPubBase64);
      const qumailIdentityId = (await sha256Hex(normEmail)).substring(0, 32);

      // 4. Create and sign Proof of Possession message
      const proofMessage = `QUMAIL-DIRECTORY-POP-v1\0${qumailIdentityId}\0${deviceId}\0${fingerprint}\0${nonceHex}`;
      const popRes = await cryptoBridge.directoryProof(secretCert, stringToUint8Array(proofMessage));
      const popSigBase64 = uint8ArrayToBase64(popRes.signature);

      const rawPubBase64 = uint8ArrayToBase64(pubCert);
      const rootFingerprint = (await sha256Hex(rawPubBase64)).toUpperCase();

      // 5. Post to /api/v1/auth/google
      console.log(`Dispatching device enrollment handshake to Cloudflare Directory for ${normEmail}...`);
      const authRes = await fetch(`${CLOUDFLARE_WORKER_URL}/api/v1/auth/google`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'User-Agent': 'QuMail-Mobile/1.0',
        },
        body: JSON.stringify({
          id_token: idToken || undefined,
          access_token: accessToken || undefined,
          device_id: deviceId,
          device_label: 'QuMail Android',
          public_key_bundle: {
            kem_public_base64: rawPubBase64,
            dsa_public_base64: dsaPubBase64,
            raw_public_base64: rawPubBase64,
          },
          pop_signature: popSigBase64,
          server_nonce: nonceHex,
          qumail_identity_id: qumailIdentityId,
          key_metadata: {
            root_fingerprint: rootFingerprint,
            suite: 'QUMAIL-OPENPGP-PQ-v1/ML-KEM-768+ML-DSA-65',
            key_version: 1,
            lifecycle: 'active',
          },
        }),
      });

      if (authRes.ok) {
        const authData = await authRes.json();
        if (authData.session_token) {
          await SecureStore.setItemAsync(`${DIRECTORY_SESSION_TOKEN_KEY}_${sKey}`, authData.session_token);
          await SecureStore.setItemAsync(DIRECTORY_SESSION_TOKEN_KEY, authData.session_token);
          console.log(`Cloudflare Directory enrollment SUCCESS for ${normEmail}! Session token stored.`);
          return authData.session_token;
        }
      } else {
        const errText = await authRes.text();
        console.warn(`Cloudflare Directory enrollment rejected for ${normEmail}:`, authRes.status, errText);
      }
    } catch (err) {
      console.warn('Error during device enrollment handshake:', err);
    }
    return null;
  }

  async fetchWithDirectoryAuth(path: string, options: RequestInit = {}): Promise<Response> {
    const url = path.startsWith('http') ? path : `${CLOUDFLARE_WORKER_URL}${path}`;
    const storedEmail = await SecureStore.getItemAsync(GMAIL_ACCOUNT_EMAIL_KEY);
    const activeAcc = await vaultManager.getAccount();
    const email = (storedEmail || activeAcc.email || '').trim().toLowerCase();
    const sKey = safeStorageKey(email);

    let token: string | null = null;
    if (sKey) {
      token = await SecureStore.getItemAsync(`${DIRECTORY_SESSION_TOKEN_KEY}_${sKey}`);
    }
    if (!token) {
      token = await SecureStore.getItemAsync(DIRECTORY_SESSION_TOKEN_KEY);
    }

    // If no token exists, attempt enrollment first
    if (!token && email) {
      token = await this.ensureDeviceEnrolled(email);
    }

    const makeReq = (t: string | null) => {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        'User-Agent': 'QuMail-Mobile/1.0',
        ...(options.headers as any),
      };
      if (t) {
        headers['Authorization'] = `Bearer ${t}`;
      }
      return fetch(url, { ...options, headers });
    };

    let res = await makeReq(token);

    if (res.status === 401 && email) {
      // Stored token was rejected by Cloudflare; re-enroll
      if (sKey) await SecureStore.deleteItemAsync(`${DIRECTORY_SESSION_TOKEN_KEY}_${sKey}`);
      await SecureStore.deleteItemAsync(DIRECTORY_SESSION_TOKEN_KEY);
      const freshToken = await this.ensureDeviceEnrolled(email);
      if (freshToken) {
        res = await makeReq(freshToken);
      }
    }

    return res;
  }

  async signIn(): Promise<AccountSession> {
    try {
      const discovery = {
        authorizationEndpoint: 'https://accounts.google.com/o/oauth2/v2/auth',
        tokenEndpoint: 'https://oauth2.googleapis.com/token',
        revocationEndpoint: 'https://oauth2.googleapis.com/revoke',
      };

      const clientId =
        (await SecureStore.getItemAsync('qumail_google_client_id')) ||
        DEFAULT_GOOGLE_CLIENT_ID;

      const prefix = clientId.split('.apps.googleusercontent.com')[0];
      const reverseScheme = `com.googleusercontent.apps.${prefix}`;
      const redirectUri = `${reverseScheme}:/oauth2redirect`;

      const request = new AuthSession.AuthRequest({
        clientId,
        scopes: [
          'openid',
          'profile',
          'email',
          'https://www.googleapis.com/auth/gmail.modify',
          'https://www.googleapis.com/auth/gmail.send',
        ],
        redirectUri,
        responseType: AuthSession.ResponseType.Code,
        usePKCE: true,
        extraParams: {
          access_type: 'offline',
          prompt: 'consent',
          audience: '953431543574-btts945dj9dqv5si2gplcapif8gitm8v.apps.googleusercontent.com',
        },
      });

      const result = await request.promptAsync(discovery);

      if (result.type === 'success' && result.params.code) {
        const tokenResult = await AuthSession.exchangeCodeAsync(
          {
            clientId,
            code: result.params.code,
            extraParams: { code_verifier: request.codeVerifier || '' },
            redirectUri,
          },
          discovery
        );

        if (tokenResult.accessToken) {
          this.accessToken = tokenResult.accessToken;

          const userInfoRes = await fetch('https://www.googleapis.com/oauth2/v3/userinfo', {
            headers: { Authorization: `Bearer ${tokenResult.accessToken}` },
          });
          const userInfo = await userInfoRes.json();
          const email = (userInfo.email || 'user@gmail.com').trim().toLowerCase();
          const sKey = safeStorageKey(email);
          await SecureStore.setItemAsync(GMAIL_ACCOUNT_EMAIL_KEY, email);
          await SecureStore.setItemAsync(`${GMAIL_ACCOUNT_EMAIL_KEY}_${sKey}`, email);

          await SecureStore.setItemAsync(GMAIL_TOKEN_KEY, tokenResult.accessToken);
          await SecureStore.setItemAsync(`${GMAIL_TOKEN_KEY}_${sKey}`, tokenResult.accessToken);
          if (tokenResult.refreshToken) {
            await SecureStore.setItemAsync(GMAIL_REFRESH_TOKEN_KEY, tokenResult.refreshToken);
            await SecureStore.setItemAsync(`${GMAIL_REFRESH_TOKEN_KEY}_${sKey}`, tokenResult.refreshToken);
          }
          if (tokenResult.idToken) {
            await SecureStore.setItemAsync(GOOGLE_ID_TOKEN_KEY, tokenResult.idToken);
            await SecureStore.setItemAsync(`${GOOGLE_ID_TOKEN_KEY}_${sKey}`, tokenResult.idToken);
            console.log('Google ID token saved successfully.');
          }

          if (userInfo.picture) {
            await SecureStore.setItemAsync('qumail_user_avatar_url_v1', userInfo.picture);
          }
          if (userInfo.name) {
            await SecureStore.setItemAsync('qumail_user_display_name_v1', userInfo.name);
          }

          await vaultManager.initializeIdentity(email);

          // Complete Cloudflare Directory enrollment with real session token
          try {
            await this.ensureDeviceEnrolled(email);
          } catch (enrollErr) {
            console.warn('Initial device enrollment warning:', enrollErr);
          }

          return {
            email,
            displayName: userInfo.name || email.split('@')[0],
            avatarUrl: userInfo.picture,
            provider: 'Gmail (OAuth 2.0 PKCE)',
            pqcAlgorithm: 'ML-KEM-768 / ML-DSA-65 (OpenPGP v6)',
            pqcIdentity: email,
            isUnlocked: true,
            vaultState: 'ACTIVE',
            connectionStatus: 'ONLINE',
          };
        }
      }

      throw new Error('Google OAuth authorization was not completed.');
    } catch (e: any) {
      console.warn('OAuth prompt failed:', e);
      throw e;
    }
  }

  async signInWithGoogle(customClientId?: string): Promise<{ email: string; displayName?: string; avatarUrl?: string }> {
    if (customClientId) {
      await SecureStore.setItemAsync('qumail_google_client_id', customClientId);
    }
    const acc = await this.signIn();
    if (acc.avatarUrl) {
      await SecureStore.setItemAsync('qumail_user_avatar_url_v1', acc.avatarUrl);
    }
    if (acc.displayName) {
      await SecureStore.setItemAsync('qumail_user_display_name_v1', acc.displayName);
    }
    return { email: acc.email, displayName: acc.displayName, avatarUrl: acc.avatarUrl };
  }

  async signInWithAppPassword(email: string, appPassword: string): Promise<AccountSession> {
    const cleanEmail = email.trim();
    const cleanPass = appPassword.replace(/\s+/g, '');

    await SecureStore.setItemAsync(GMAIL_ACCOUNT_EMAIL_KEY, cleanEmail);
    await SecureStore.setItemAsync(GMAIL_APP_PASS_KEY, cleanPass);

    await vaultManager.initializeIdentity(cleanEmail);

    return {
      email: cleanEmail,
      displayName: cleanEmail.split('@')[0],
      provider: 'QuMail Mailbox (App Password / TLS)',
      pqcAlgorithm: 'NIST FIPS 203 (ML-KEM-768) + NIST FIPS 204 (ML-DSA-65)',
      pqcIdentity: cleanEmail,
      isUnlocked: true,
      vaultState: 'ACTIVE',
      connectionStatus: 'ONLINE',
    };
  }

  async signOut(): Promise<void> {
    this.accessToken = null;
    this.messages = [];
    this.lookupCache.clear();
    await SecureStore.deleteItemAsync(GMAIL_TOKEN_KEY);
    await SecureStore.deleteItemAsync(GMAIL_REFRESH_TOKEN_KEY);
    await SecureStore.deleteItemAsync(GMAIL_APP_PASS_KEY);
    await SecureStore.deleteItemAsync(GMAIL_ACCOUNT_EMAIL_KEY);
    await SecureStore.deleteItemAsync(GOOGLE_ID_TOKEN_KEY);
    await SecureStore.deleteItemAsync(DIRECTORY_SESSION_TOKEN_KEY);
    await SecureStore.deleteItemAsync('qumail_user_avatar_url_v1');
    await SecureStore.deleteItemAsync('qumail_user_display_name_v1');
    await vaultManager.lockVault();
  }

  async fetchMessages(folder: string, limit: number = 50): Promise<EmailMessage[]> {
    const token = await this.getAccessToken();

    // Ensure user avatar and display name are cached if missing
    try {
      const storedAvatar = await SecureStore.getItemAsync('qumail_user_avatar_url_v1');
      if (!storedAvatar && token) {
        const userInfoRes = await fetch('https://www.googleapis.com/oauth2/v3/userinfo', {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (userInfoRes.ok) {
          const userInfo = await userInfoRes.json();
          if (userInfo.picture) {
            await SecureStore.setItemAsync('qumail_user_avatar_url_v1', userInfo.picture);
          }
          if (userInfo.name) {
            await SecureStore.setItemAsync('qumail_user_display_name_v1', userInfo.name);
          }
        }
      }
    } catch {
      // ignore
    }

    if (!token) {
      return this.messages.filter((m) => {
        if (folder === 'starred') return m.starred;
        return m.folder === folder;
      });
    }

    try {
      const query =
        folder === 'inbox' ? 'in:inbox' :
        folder === 'starred' ? 'is:starred' :
        folder === 'sent' ? 'in:sent' :
        folder === 'drafts' ? 'in:drafts' :
        folder === 'trash' ? 'in:trash' :
        folder === 'spam' ? 'in:spam' : '';

      let listRes = await fetch(
        `https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults=${limit}&q=${encodeURIComponent(query)}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );

      // If token expired (401), trigger silent auto-refresh and retry once
      if (listRes.status === 401) {
        console.log('Gmail returned 401 Unauthorized; attempting silent token refresh...');
        const freshToken = await this.getAccessToken(true);
        if (freshToken) {
          listRes = await fetch(
            `https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults=${limit}&q=${encodeURIComponent(query)}`,
            { headers: { Authorization: `Bearer ${freshToken}` } }
          );
        }
      }

      if (listRes.ok) {
        const data = await listRes.json();
        if (data.messages && data.messages.length > 0) {
          const activeToken = this.accessToken || token;
          const fetched = await Promise.all(
            data.messages.slice(0, 25).map(async (item: { id: string }) => {
              const msgRes = await fetch(
                `https://gmail.googleapis.com/gmail/v1/users/me/messages/${item.id}?format=full`,
                { headers: { Authorization: `Bearer ${activeToken}` } }
              );
              const msgData = await msgRes.json();
              return await this.parseGmailMessage(msgData, folder);
            })
          );
          this.messages = fetched;
          return fetched;
        }
      }
    } catch (err) {
      console.warn('Error fetching messages from Gmail API:', err);
    }

    return [];
  }

  private async parseGmailMessage(raw: any, folder: string): Promise<EmailMessage> {
    const headers = raw.payload?.headers || [];
    const getHeader = (name: string) =>
      headers.find((h: any) => h.name.toLowerCase() === name.toLowerCase())?.value || '';

    let subject = getHeader('Subject') || '(No Subject)';
    const from = getHeader('From') || 'Unknown Sender';
    const to = getHeader('To') || '';
    const rawDate = getHeader('Date') || new Date().toLocaleString();
    const contentType = getHeader('Content-Type') || '';
    const pqPayloadHeader = getHeader('X-QuMail-PQ-Payload');

    let senderName = from;
    let senderEmail = from;
    const match = from.match(/^(.*?)\s*<([^>]+)>/);
    if (match) {
      senderName = match[1].trim().replace(/^["']|["']$/g, '') || match[2].trim();
      senderEmail = match[2].trim();
    } else {
      senderEmail = from.trim();
      const localPart = from.split('@')[0].trim();
      senderName = localPart
        .replace(/[._]/g, ' ')
        .replace(/\b\w/g, (c: string) => c.toUpperCase());
    }

    const timestamp = parseInt(raw.internalDate || Date.now().toString(), 10);
    const formattedDate = formatMailDate(timestamp);

    const isMimeEncrypted =
      contentType.toLowerCase().includes('multipart/encrypted') ||
      contentType.toLowerCase().includes('application/pgp-encrypted');
    const hasPqHeader = Boolean(pqPayloadHeader);
    const hasSubjectPq =
      subject.includes('[QuMail-PQ]') ||
      subject.toLowerCase().includes('encrypted message') ||
      subject.startsWith('Encrypted message');
    const snippetHasArmor = (raw.snippet || '').includes('-----BEGIN PGP MESSAGE-----');

    const isPq = isMimeEncrypted || hasPqHeader || hasSubjectPq || snippetHasArmor;
    const isWebLink =
      subject.startsWith('[QuMail Secure Link]') || Boolean(getHeader('X-QuMail-Secure-Link'));

    let decryptedBody = raw.snippet || '';
    let isDecryptedSuccessfully = false;
    let decryptionErrorReason = '';

    if (isPq) {
      try {
        let armorText = '';

        const extractArmorFromStr = (s: string): string => {
          if (!s || typeof s !== 'string') return '';
          const start = s.indexOf('-----BEGIN PGP MESSAGE-----');
          if (start === -1) return '';
          const end = s.indexOf('-----END PGP MESSAGE-----', start);
          if (end === -1) return '';
          return s.substring(start, end + '-----END PGP MESSAGE-----'.length);
        };

        const safeDecodeBase64 = (dataStr: string): string => {
          if (!dataStr) return '';
          try {
            const b64 = dataStr.replace(/-/g, '+').replace(/_/g, '/');
            const pad = b64.length % 4;
            const padded = pad ? b64 + '='.repeat(4 - pad) : b64;
            return uint8ArrayToString(base64ToUint8Array(padded));
          } catch {
            try {
              const b64 = dataStr.replace(/-/g, '+').replace(/_/g, '/');
              return atob(b64);
            } catch {
              return '';
            }
          }
        };

        // Gmail REST API truncates body.data to ~5KB for large parts.
        // If body.data is absent but body.attachmentId is set, we must
        // fetch the actual content from the attachments endpoint.
        const fetchAttachmentData = async (msgId: string, attachmentId: string, accessToken: string): Promise<string> => {
          try {
            const url = `https://gmail.googleapis.com/gmail/v1/users/me/messages/${msgId}/attachments/${attachmentId}`;
            const res = await fetch(url, { headers: { Authorization: `Bearer ${accessToken}` } });
            if (!res.ok) return '';
            const json = await res.json();
            return json.data || ''; // base64url encoded
          } catch {
            return '';
          }
        };

        // Recursively inspect all payload parts; fetch via attachmentId when body.data is absent
        const searchPartsAsync = async (partList: any[], msgId: string, accessToken: string): Promise<void> => {
          if (!partList || !Array.isArray(partList)) return;
          for (const p of partList) {
            // Case 1: body.data is present inline
            if (p.body?.data) {
              const decoded = safeDecodeBase64(p.body.data);
              const found = extractArmorFromStr(decoded);
              if (found) {
                armorText = found;
                return;
              }
            }

            // Case 2: body.data is absent but attachmentId is set (Gmail 5KB truncation)
            if (!p.body?.data && p.body?.attachmentId) {
              const rawData = await fetchAttachmentData(msgId, p.body.attachmentId, accessToken);
              if (rawData) {
                const decoded = safeDecodeBase64(rawData);
                const found = extractArmorFromStr(decoded);
                if (found) {
                  armorText = found;
                  return;
                }
              }
            }

            // Case 3: recurse into sub-parts
            if (p.parts && Array.isArray(p.parts)) {
              await searchPartsAsync(p.parts, msgId, accessToken);
              if (armorText) return;
            }
          }
        };

        // Retrieve the access token once for attachment fetching
        const accessTokenForAttachments = await this.getAccessToken() || '';
        const messageId = raw.id || '';

        // 1. Search recursive parts (async, handles attachmentId)
        if (raw.payload?.parts) {
          await searchPartsAsync(raw.payload.parts, messageId, accessTokenForAttachments);
        }

        // 2. Try top-level payload body data
        if (!armorText && raw.payload?.body?.data) {
          const decoded = safeDecodeBase64(raw.payload.body.data);
          const found = extractArmorFromStr(decoded);
          if (found) armorText = found;
        }

        // 3. Top-level body is also potentially an attachment (e.g. single-part encrypted message)
        if (!armorText && !raw.payload?.body?.data && raw.payload?.body?.attachmentId) {
          const rawData = await fetchAttachmentData(messageId, raw.payload.body.attachmentId, accessTokenForAttachments);
          if (rawData) {
            const decoded = safeDecodeBase64(rawData);
            const found = extractArmorFromStr(decoded);
            if (found) armorText = found;
          }
        }

        // 4. Try raw.snippet if payload was stripped or nested as snippet
        if (!armorText && raw.snippet) {
          const found = extractArmorFromStr(raw.snippet);
          if (found) armorText = found;
        }

        // 5. Try raw.raw if full RFC 822 format was retrieved
        if (!armorText && (raw as any).raw) {
          const decoded = safeDecodeBase64((raw as any).raw);
          const found = extractArmorFromStr(decoded);
          if (found) armorText = found;
        }

        if (armorText) {
          const mySecretCertBytes = await vaultManager.getSecretCertBytes();
          if (mySecretCertBytes) {
            const candidateSenderCerts: Uint8Array[] = [];

            // 1. If self-send, include local device public cert
            const storedEmail = await SecureStore.getItemAsync(GMAIL_ACCOUNT_EMAIL_KEY);
            const activeAcc = await vaultManager.getAccount();
            const myEmail = (storedEmail || activeAcc.email || '').trim().toLowerCase();
            const isSelf = Boolean(myEmail && (senderEmail.toLowerCase() === myEmail || folder === 'sent'));
            if (isSelf) {
              const myPub = await vaultManager.getPublicCertBytes();
              if (myPub) candidateSenderCerts.push(myPub);
            }

            // 2. Fetch all registered public keys for sender from Cloudflare Directory
            try {
              const senderInfo = await this.checkRecipient(senderEmail);
              const remoteCerts = senderInfo.publicCertsBase64 || (senderInfo.publicCertBase64 ? [senderInfo.publicCertBase64] : []);
              for (const b64 of remoteCerts) {
                const certBytes = base64ToUint8Array(b64);
                if (!candidateSenderCerts.some(c => c.length === certBytes.length && c.every((v, i) => v === certBytes[i]))) {
                  candidateSenderCerts.push(certBytes);
                }
              }
            } catch (lookupErr) {
              console.warn('Sender key lookup error:', lookupErr);
            }

            // 3. Try decrypting and verifying signature with each candidate sender key
            let lastErr: any = null;
            const dearmoredBytes = dearmorOpenPGP(armorText);
            const rawArmorBytes = stringToUint8Array(armorText);
            const candidateEnvelopes: Uint8Array[] = [dearmoredBytes];
            if (rawArmorBytes.length !== dearmoredBytes.length) {
              candidateEnvelopes.push(rawArmorBytes);
            }

            sender_loop:
            for (const senderCertBytes of candidateSenderCerts) {
              for (const envBytes of candidateEnvelopes) {
                try {
                  const openResult = await cryptoBridge.openMessage({
                    recipientSecret: mySecretCertBytes,
                    senderPublic: senderCertBytes,
                    envelope: envBytes,
                  });

                  const innerText = uint8ArrayToString(openResult);

                  // Extract inner Subject if present
                  const innerSubjMatch = innerText.match(/(?:^|\r?\n)Subject:\s*([^\r\n]+)/i);
                  if (innerSubjMatch && innerSubjMatch[1]) {
                    subject = innerSubjMatch[1].trim();
                  }

                  // Extract inner body after header boundary
                  const splitMatch = innerText.match(/\r?\n\r?\n([\s\S]*)$/);
                  let rawBodyPart = splitMatch ? splitMatch[1].trim() : innerText.trim();

                  // Base64 decode body if MIME Content-Transfer-Encoding is base64
                  const isBase64 = /Content-Transfer-Encoding:\s*base64/i.test(innerText);
                  if (isBase64) {
                    try {
                      const cleanB64 = rawBodyPart.replace(/\s+/g, '');
                      rawBodyPart = decodeURIComponent(escape(atob(cleanB64)));
                    } catch {
                      try {
                        rawBodyPart = atob(rawBodyPart.replace(/\s+/g, ''));
                      } catch {
                        // keep rawBodyPart
                      }
                    }
                  }

                  decryptedBody = rawBodyPart;
                  isDecryptedSuccessfully = true;
                  break sender_loop;
                } catch (openErr) {
                  lastErr = openErr;
                }
              }
            }

            if (!isDecryptedSuccessfully) {
              decryptionErrorReason = !mySecretCertBytes 
                ? 'vault_secret_missing' 
                : candidateSenderCerts.length === 0 
                ? `sender_key_not_found(${senderEmail})` 
                : `open_failed(${lastErr?.message || String(lastErr) || 'unknown'})`;
            }
          } else {
            decryptionErrorReason = 'vault_secret_not_found';
          }
        } else {
          decryptionErrorReason = 'armor_text_not_found';
        }
      } catch (decryptErr: any) {
        console.warn('On-device PQC decryption failed:', decryptErr);
        decryptionErrorReason = `exception: ${decryptErr?.message || String(decryptErr)}`;
      }
    }

    const displayBody = isDecryptedSuccessfully
      ? decryptedBody
      : isPq
      ? `[Decryption Error: ${decryptionErrorReason || 'invalid_message'}]`
      : raw.snippet || '';

    const displaySnippet = isDecryptedSuccessfully
      ? decryptedBody.substring(0, 100)
      : isPq
      ? `[Decryption Error: ${decryptionErrorReason || 'invalid_message'}]`
      : raw.snippet || '';

    return {
      id: raw.id,
      sender: senderName,
      senderEmail,
      recipients: [to],
      subject: subject.replace(/^\[QuMail-PQ\]\s*/i, ''),
      snippet: displaySnippet,
      body: displayBody,
      date: formattedDate,
      timestamp,
      seen: !(raw.labelIds || []).includes('UNREAD'),
      starred: (raw.labelIds || []).includes('STARRED'),
      folder: (folder as any) || 'inbox',
      category: isPq || isWebLink ? 'secure' : 'primary',
      hasAttachments: false,
      securityMode: isPq ? 'pq' : isWebLink ? 'weblink' : 'standard',
      isQuMail: isPq || isWebLink,
      securityTier: isPq ? 'pq_sealed' : isWebLink ? 'weblink' : 'standard_tls',
      indicator: isPq
        ? isDecryptedSuccessfully
          ? {
              badgeLevel: 'SECURE',
              headline: 'Post-Quantum Sealed Envelope (ML-KEM-768 + ML-DSA-65)',
              description: 'Decrypted on-device using NIST post-quantum standard ML-KEM-768 key encapsulation and verified with ML-DSA-65 signature.',
              actionAdvice: 'Safe to read. Sovereign enclave cryptography active.',
            }
          : {
              badgeLevel: 'ALERT',
              headline: 'Decryption Failed',
              description: `Failed to decrypt post-quantum envelope (${decryptionErrorReason || 'invalid_message'}).`,
              actionAdvice: 'Verify sender identity and device enrollment in Cloudflare Directory.',
            }
        : isWebLink
        ? {
            badgeLevel: 'SECURE',
            headline: 'QuMail Secure Private Link',
            description: 'Zero-knowledge browser delivery link with client-side key fragmentation.',
            actionAdvice: 'Safe to open in secure browser.',
          }
        : {
            badgeLevel: 'NEUTRAL',
            headline: 'Standard Email',
            description: 'Delivered via TLS transport without QuMail post-quantum sealing.',
            actionAdvice: 'Standard email security.',
          },
    };
  }

  async sendMessage(msg: OutboundMessage): Promise<{ id: string }> {
    const token = await this.getAccessToken();
    const isPq = msg.securityMode === 'pq';
    const isWebLink = msg.securityMode === 'weblink';
    let finalBody = msg.body;
    let finalSubject = msg.subject;
    let accessUrl = '';

    const myAccount = await vaultManager.getAccount();
    const storedEmail = await SecureStore.getItemAsync(GMAIL_ACCOUNT_EMAIL_KEY);
    const myEmail = storedEmail || myAccount.email || 'user@qumail.app';
    const d = new Date();
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const rfcDate = `${days[d.getUTCDay()]}, ${String(d.getUTCDate()).padStart(2, '0')} ${months[d.getUTCMonth()]} ${d.getUTCFullYear()} ${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}:${String(d.getUTCSeconds()).padStart(2, '0')} +0000`;
    const messageId = `<${Date.now()}.${Math.random().toString(36).substring(2, 9)}@qumail.app>`;
    const nowTs = Date.now();
    const pqBoundary = `===============QuMail_${nowTs}_Boundary==`;
    const altBoundary = `===============QuMail_Alt_${nowTs}==`;

    if (isWebLink) {
      let linkId = '';
      let rawKeyHex = '';

      const keyBytes = new Uint8Array(32);
      for (let i = 0; i < 32; i++) keyBytes[i] = Math.floor(Math.random() * 256);
      rawKeyHex = Array.from(keyBytes).map((b) => b.toString(16).padStart(2, '0')).join('');

      const ptBytes = stringToUint8Array(msg.body);
      const encRes = await cryptoBridge.encryptAttachment(keyBytes, ptBytes);
      const encryptedPayloadB64 = uint8ArrayToBase64(encRes.ciphertext);

      // Synchronize exact 12-byte AES-GCM IV returned by native Rust provider
      const ivHex = Array.from(encRes.nonce).map((b) => b.toString(16).padStart(2, '0')).join('');

      // Enable Email OTP gating with anti-enumeration salt and normalized hash
      const recipientEmail = (msg.recipients[0] || '').trim();
      const normRecipient = normalizeEmailForDirectory(recipientEmail);
      const saltBytes16 = new Uint8Array(16);
      for (let i = 0; i < 16; i++) saltBytes16[i] = Math.floor(Math.random() * 256);
      const recipientEmailSalt = Array.from(saltBytes16).map((b) => b.toString(16).padStart(2, '0')).join('');
      const recipientEmailHash = await sha256Hex(normRecipient + recipientEmailSalt);

      const ttlDays = Math.max(1, Math.min(14, Math.ceil((msg.expiresInHours || 24) / 24)));
      const wlPostRes = await this.fetchWithDirectoryAuth('/api/v1/weblinks/create', {
        method: 'POST',
        body: JSON.stringify({
          encrypted_payload: encryptedPayloadB64,
          iv_hex: ivHex,
          has_passcode: false,
          max_views: 5,
          burn_after_read: Boolean(msg.burnAfterRead),
          ttl_days: ttlDays,
          recipient_email_hash: recipientEmailHash,
          recipient_email_salt: recipientEmailSalt,
          attachments: [],
        }),
      });

      if (!wlPostRes.ok) {
        const errText = await wlPostRes.text();
        console.warn('WebLink creation error response:', wlPostRes.status, errText);
        if (wlPostRes.status === 401) {
          throw new Error('Device enrollment required. Please connect with Google to register this device with Cloudflare Directory.');
        }
        throw new Error(`Failed to create secure WebLink on Cloudflare Directory (${wlPostRes.status}): ${errText}`);
      }

      const wlData = await wlPostRes.json();
      linkId = wlData.link_id;
      if (!linkId) {
        throw new Error('Cloudflare Directory did not return a valid WebLink ID.');
      }

      accessUrl = `${CLOUDFLARE_WORKER_URL}/v/${linkId}#key=${rawKeyHex}`;

      finalSubject = msg.cloakSubjectHeaders
        ? '[QuMail Secure Link] Confidential message'
        : `[QuMail Secure Link] ${msg.subject}`;

      const shortUrl = accessUrl.length > 70 ? accessUrl.substring(0, 68) + '…' : accessUrl;
      finalBody = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>QuMail Secure Link</title>
</head>
<body style="margin:0;padding:0;background:#0a0e1a;font-family:'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#0a0e1a;padding:40px 0;">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">
      <tr>
        <td style="background:linear-gradient(135deg,#0d1b35 0%,#0a2040 100%);border-radius:16px 16px 0 0;padding:36px 40px 28px;text-align:center;border-bottom:1px solid #1a3a6b;">
          <table cellpadding="0" cellspacing="0" style="margin:0 auto;">
            <tr>
              <td style="background:#00c8e0;border-radius:12px;padding:10px 18px;display:inline-block;">
                <span style="font-size:22px;font-weight:800;color:#050d1a;letter-spacing:2px;font-family:monospace;">Q</span>
                <span style="font-size:18px;font-weight:700;color:#050d1a;letter-spacing:1px;">uMail</span>
              </td>
            </tr>
          </table>
          <p style="color:#8ba8cc;font-size:13px;margin:14px 0 0;letter-spacing:0.5px;">SECURE MESSAGE DELIVERY</p>
        </td>
      </tr>
      <tr>
        <td style="background:#0d1b35;padding:40px 40px 32px;">
          <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
            <tr>
              <td style="background:#0d2a4a;border-left:3px solid #00c8e0;border-radius:0 8px 8px 0;padding:14px 18px;">
                <span style="color:#00c8e0;font-size:12px;font-weight:700;letter-spacing:1px;text-transform:uppercase;">🔒 Encrypted Message</span>
              </td>
            </tr>
          </table>
          <p style="color:#c5d8f0;font-size:16px;line-height:1.6;margin:0 0 8px;">
            You have received a <strong style="color:#e8f4ff;">confidential communication</strong> secured with Post-Quantum encryption.
          </p>
          <table cellpadding="0" cellspacing="0" style="margin:24px 0;">
            <tr>
              <td style="background:#0a2040;border:1px solid #1e4080;border-radius:8px;padding:12px 20px;">
                <span style="color:#8ba8cc;font-size:12px;font-weight:600;letter-spacing:0.8px;text-transform:uppercase;display:block;margin-bottom:4px;">Message</span>
                <span style="color:#e8f4ff;font-size:15px;font-weight:600;">Confidential communication</span>
              </td>
            </tr>
          </table>
          <p style="color:#8ba8cc;font-size:14px;line-height:1.6;margin:0 0 28px;">
            Click the button below to open the secure viewer in your browser. The message is decrypted entirely on your device — no data is exposed to any server.
          </p>
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td align="center" style="padding:4px 0 32px;">
                <a href="${accessUrl}" style="display:inline-block;background:linear-gradient(135deg,#00c8e0 0%,#0098b8 100%);color:#050d1a;font-size:16px;font-weight:800;text-decoration:none;padding:16px 42px;border-radius:50px;letter-spacing:0.5px;">
                  🔓 &nbsp;Open Secure Message
                </a>
              </td>
            </tr>
          </table>
          <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:32px;">
            <tr>
              <td style="background:#070f20;border:1px solid #1a3a6b;border-radius:8px;padding:14px 16px;">
                <p style="color:#8ba8cc;font-size:11px;margin:0 0 6px;letter-spacing:0.5px;">Or paste this link in your browser:</p>
                <p style="color:#4fb8d0;font-size:12px;word-break:break-all;margin:0;font-family:monospace;">${shortUrl}</p>
              </td>
            </tr>
          </table>

          <!-- Security Badges -->
          <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:12px;">
            <tr>
              <td width="33%" align="center" style="padding:0 4px;">
                <div style="background:#070f20;border:1px solid #1a3a6b;border-radius:8px;padding:12px 8px;text-align:center;">
                  <div style="color:#00c8e0;font-size:18px;margin-bottom:4px;">⚡</div>
                  <div style="color:#8ba8cc;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">ML-KEM-768</div>
                  <div style="color:#566880;font-size:9px;">NIST FIPS 203</div>
                </div>
              </td>
              <td width="33%" align="center" style="padding:0 4px;">
                <div style="background:#070f20;border:1px solid #1a3a6b;border-radius:8px;padding:12px 8px;text-align:center;">
                  <div style="color:#00c8e0;font-size:18px;margin-bottom:4px;">🛡️</div>
                  <div style="color:#8ba8cc;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">ML-DSA-65</div>
                  <div style="color:#566880;font-size:9px;">NIST FIPS 204</div>
                </div>
              </td>
              <td width="33%" align="center" style="padding:0 4px;">
                <div style="background:#070f20;border:1px solid #1a3a6b;border-radius:8px;padding:12px 8px;text-align:center;">
                  <div style="color:#00c8e0;font-size:18px;margin-bottom:4px;">🔑</div>
                  <div style="color:#8ba8cc;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">AES-256-GCM</div>
                  <div style="color:#566880;font-size:9px;">Zero-Knowledge</div>
                </div>
              </td>
            </tr>
          </table>
        </td>
      </tr>
      <tr>
        <td style="background:#070f20;border-radius:0 0 16px 16px;padding:24px 40px;border-top:1px solid #1a3a6b;text-align:center;">
          <p style="color:#566880;font-size:12px;margin:0 0 6px;">
            🔒 The decryption key is embedded in the URL <code style="color:#4fb8d0;">#fragment</code> and is <strong>never</strong> transmitted to any server.
          </p>
          <p style="color:#3d5270;font-size:11px;margin:0;">
            Sent via QuMail &nbsp;·&nbsp; Post-Quantum Secure Email
          </p>
        </td>
      </tr>
    </table>
  </td></tr>
</table>
</body>
</html>`;
    } else if (isPq) {
      const targetEmail = msg.recipients[0];
      const recInfo = await this.checkRecipient(targetEmail);
      if (!recInfo.registered || !recInfo.publicCertBase64) {
        throw new Error(
          `Recipient "${targetEmail}" is not a registered QuMail user. Please use Secure Private Link instead.`
        );
      }

      const senderSecret = await vaultManager.getSecretCertBytes();
      if (!senderSecret) {
        throw new Error('On-device Security Vault is locked or uninitialized.');
      }

      // Collect all candidate recipient device public keys
      const certList: string[] = recInfo.publicCertsBase64 && recInfo.publicCertsBase64.length > 0
        ? [...recInfo.publicCertsBase64]
        : [recInfo.publicCertBase64];

      // Always include sender's local device key so sender can decrypt their own Sent email
      const localPub = await vaultManager.getPublicCert();
      if (localPub && !certList.includes(localPub)) {
        if (certList.length >= 4) {
          certList.splice(3);
        }
        certList.push(localPub);
      }

      const recipientPublicBytesList: Uint8Array[] = certList.map((c) => base64ToUint8Array(c));

      // Build RFC 9788 / MIME inner message with full header protection
      const innerMimeBytes = buildInnerMime(
        myEmail,
        msg.recipients,
        msg.subject,
        msg.body,
        rfcDate,
        messageId
      );

      // Seal inner message using Sequoia OpenPGP v6 ML-KEM-768 + ML-DSA-65 to all active recipient devices
      const sealedArmorBytes = await cryptoBridge.sealMessage({
        senderSecret,
        recipientPublics: recipientPublicBytesList,
        plaintext: innerMimeBytes,
      });

      const armorStr = uint8ArrayToString(sealedArmorBytes);

      // Format outer RFC 3156 multipart/encrypted message
      // Strictly conforms to Desktop mime.py profile (STRUCTURAL headers only, zero child parameters)
      finalSubject = msg.cloakSubjectHeaders ? 'Encrypted message' : msg.subject;

      finalBody = [
        `--${pqBoundary}`,
        `Content-Type: application/pgp-encrypted`,
        `Content-Transfer-Encoding: 7bit`,
        ``,
        `Version: 1`,
        ``,
        `--${pqBoundary}`,
        `Content-Type: application/octet-stream`,
        `Content-Transfer-Encoding: 7bit`,
        ``,
        armorStr.trim().replace(/\r?\n/g, '\r\n'),
        ``,
        `--${pqBoundary}--`,
        ``,
      ].join('\r\n');
    }

    if (!token) {
      throw new Error('Not signed in to email account.');
    }

    let payloadMimeBody = finalBody;
    if (isWebLink) {
      const plainTextAlternative = [
        `You have received a confidential communication via QuMail Secure Link.`,
        ``,
        `Open the secure link below to decrypt and read the message:`,
        `${accessUrl}`,
        ``,
        `The decryption key is embedded in the URL fragment (#) and is never sent to any server.`,
        `Powered by QuMail · Post-Quantum Encryption (ML-KEM-768 / ML-DSA-65)`,
      ].join('\r\n');

      payloadMimeBody = [
        `--${altBoundary}`,
        `Content-Type: text/plain; charset=UTF-8`,
        `Content-Transfer-Encoding: 7bit`,
        ``,
        plainTextAlternative,
        ``,
        `--${altBoundary}`,
        `Content-Type: text/html; charset=UTF-8`,
        `Content-Transfer-Encoding: 7bit`,
        ``,
        finalBody,
        ``,
        `--${altBoundary}--`,
        ``,
      ].join('\r\n');
    }

    const rawMimeLines = [
      `From: ${myEmail}`,
      `To: ${msg.recipients.join(', ')}`,
      `Subject: ${finalSubject}`,
      `Date: ${rfcDate}`,
      `Message-ID: ${messageId}`,
      `MIME-Version: 1.0`,
      ...(isPq
        ? [
            `Content-Type: multipart/encrypted; protocol="application/pgp-encrypted"; boundary="${pqBoundary}"`,
            `X-QuMail-PQ-Payload: hybrid-v1`,
          ]
        : isWebLink
        ? [
            `Content-Type: multipart/alternative; boundary="${altBoundary}"`,
            `X-QuMail-Secure-Link: weblink-v1`,
          ]
        : [`Content-Type: text/plain; charset=UTF-8`]),
      '',
      payloadMimeBody,
    ];

    const rawMime = rawMimeLines.join('\r\n');
    const rawMimeBytes = stringToUint8Array(rawMime);
    const encodedMime = uint8ArrayToBase64(rawMimeBytes)
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '');

    const sendRes = await fetch('https://gmail.googleapis.com/gmail/v1/users/me/messages/send', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ raw: encodedMime }),
    });

    if (!sendRes.ok) {
      const errText = await sendRes.text();
      throw new Error(`Gmail API dispatch failed: ${errText}`);
    }

    const sendData = await sendRes.json();
    return { id: sendData.id };
  }

  async saveDraft(msg: Partial<OutboundMessage>): Promise<{ id: string }> {
    const draftId = `draft-${Date.now()}`;
    return { id: draftId };
  }

  async deleteMessage(id: string): Promise<void> {
    const msg = this.messages.find((m) => m.id === id);
    if (msg && !msg.isQuMail && msg.securityMode !== 'pq' && msg.securityMode !== 'weblink') {
      throw new Error('Security Policy: QuMail cannot delete standard emails. Only post-quantum and secure emails can be managed.');
    }

    const token = await this.getAccessToken();
    if (token) {
      try {
        await fetch(`https://gmail.googleapis.com/gmail/v1/users/me/messages/${id}/trash`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
        });
      } catch (e) {
        console.warn('Delete on Gmail failed:', e);
      }
    }
    const idx = this.messages.findIndex((m) => m.id === id);
    if (idx !== -1) {
      this.messages.splice(idx, 1);
    }
  }

  async markRead(id: string, seen: boolean): Promise<void> {
    const token = await this.getAccessToken();
    if (token) {
      try {
        await fetch(`https://gmail.googleapis.com/gmail/v1/users/me/messages/${id}/modify`, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(seen ? { removeLabelIds: ['UNREAD'] } : { addLabelIds: ['UNREAD'] }),
        });
      } catch (e) {
        console.warn('Mark read on Gmail failed:', e);
      }
    }
    const msg = this.messages.find((m) => m.id === id);
    if (msg) msg.seen = seen;
  }

  async toggleStar(id: string): Promise<void> {
    const msg = this.messages.find((m) => m.id === id);
    if (msg) {
      msg.starred = !msg.starred;
      const token = await this.getAccessToken();
      if (token) {
        try {
          await fetch(`https://gmail.googleapis.com/gmail/v1/users/me/messages/${id}/modify`, {
            method: 'POST',
            headers: {
              Authorization: `Bearer ${token}`,
              'Content-Type': 'application/json',
            },
            body: JSON.stringify(
              msg.starred ? { addLabelIds: ['STARRED'] } : { removeLabelIds: ['STARRED'] }
            ),
          });
        } catch (e) {
          console.warn('Toggle star on Gmail failed:', e);
        }
      }
    }
  }

  async checkRecipient(email: string): Promise<RecipientInfo> {
    const norm = email
      .trim()
      .toLowerCase()
      .replace(/^<|>$/g, '')
      .replace(/^["']|["']$/g, '');

    if (!norm || !norm.includes('@')) {
      return {
        registered: false,
        securityMode: 'weblink',
        message: 'Invalid email address.',
      };
    }

    // 1. Check in-memory cache to prevent 429 rate limits
    const cached = this.lookupCache.get(norm);
    if (cached) {
      const ttl = cached.info.registered ? 10 * 60 * 1000 : 15 * 1000;
      if (Date.now() - cached.ts < ttl) {
        return cached.info;
      }
    }

    // 2. Check if recipient is the current active account (self-send)
    const storedEmail = await SecureStore.getItemAsync(GMAIL_ACCOUNT_EMAIL_KEY);
    const activeAcc = await vaultManager.getAccount();
    const myEmail = (storedEmail || activeAcc.email || '').trim().toLowerCase();
    const isSelf = Boolean(myEmail && norm === myEmail);

    let directoryPubCerts: string[] = [];

    // 3. Query Cloudflare Directory Service with authenticated session
    try {
      const res = await this.fetchWithDirectoryAuth('/api/v1/directory/lookup', {
        method: 'POST',
        body: JSON.stringify({ email: norm }),
      });

      if (res.ok) {
        const data = await res.json();
        if (data.found && data.devices && data.devices.length > 0) {
          directoryPubCerts = data.devices
            .map((dev: any) => {
              let bundle = dev.public_key_bundle;
              if (typeof bundle === 'string') {
                try { bundle = JSON.parse(bundle); } catch {}
              }
              return bundle?.raw_public_base64 || bundle?.kem_public_base64;
            })
            .filter((k: any) => typeof k === 'string' && k.length > 0);
        }
      } else if (res.status === 401) {
        console.warn('Directory lookup 401: device enrollment or session refresh required.');
      }
    } catch (err) {
      console.warn('Directory lookup error:', err);
    }

    // 4. If self-send, guarantee that local vault public key is always included
    if (isSelf) {
      const localPub = await vaultManager.getPublicCert();
      if (localPub && !directoryPubCerts.includes(localPub)) {
        directoryPubCerts.push(localPub);
      }
    }

    if (directoryPubCerts.length > 0) {
      const primaryCert = directoryPubCerts[0];
      const info: RecipientInfo = {
        registered: true,
        deviceCount: directoryPubCerts.length,
        securityMode: 'pq',
        publicCertBase64: primaryCert,
        publicCertsBase64: directoryPubCerts,
        message: isSelf
          ? `Verified QuMail recipient (${directoryPubCerts.length} registered device(s) - Current Identity). Post-quantum ML-KEM-768 active.`
          : `Verified QuMail recipient (${directoryPubCerts.length} registered device(s)). Post-quantum ML-KEM-768 active.`,
      };
      this.lookupCache.set(norm, { info, ts: Date.now() });
      return info;
    }

    const fallbackInfo: RecipientInfo = {
      registered: false,
      securityMode: 'weblink',
      message:
        'Recipient is not registered with QuMail. Use Secure Private Link to deliver end-to-end encrypted to their browser.',
    };
    return fallbackInfo;
  }
}

export const mailTransport: MailTransport = new CombinedGmailTransport();
