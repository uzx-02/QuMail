import { EmailMessage, HSMStatus, AccountSession, TranslationCompatibility, TranslationStatus, TranslationLogEntry } from '../types';
import { INITIAL_ACCOUNT, INITIAL_HSM } from '../initialState';

// Extend Window interface for pywebview
declare global {
  interface Window {
    pywebview?: {
      api: {
        ping: () => Promise<{ pong: boolean; version: string; timestamp: number; authenticated: boolean }>;
        getMessages: () => Promise<EmailMessage[]>;
        fetchInbox: (limit?: number) => Promise<EmailMessage[]>;
        sendMessage: (msg: Partial<EmailMessage> & { draftId?: string; outboxId?: string }) => Promise<{ success: boolean; id?: string; folder?: string; message?: string }>;
        saveDraft: (draft: Partial<EmailMessage>) => Promise<{ success: boolean; id?: string; draft?: EmailMessage }>;
        deleteMessage: (id: string) => Promise<boolean>;
        markRead: (id: string, seen: boolean) => Promise<boolean>;
        toggleStar: (id: string) => Promise<boolean>;
        getHSMStatus: () => Promise<any>;
        sampleEntropy: () => Promise<{ success: boolean; hex: string; rate: number }>;
        getAccount: () => Promise<any>;
        loginAccount: (email: string, displayName?: string, organization?: string) => Promise<any>;
        logoutAccount: () => Promise<boolean>;
        lockVault: () => Promise<boolean>;
        googleAuth: () => Promise<any>;
        connectGoogle: () => Promise<any>;
        getSessionStatus: () => Promise<{
          sessionState: string;
          vaultState: string;
          account: any;
          lastError: any;
          kemAlgorithm: string;
          dsaAlgorithm: string;
        }>;
        hasSecurityPin: () => Promise<boolean>;
        setSecurityPin: (newPin: string, currentPin?: string) => Promise<{ success: boolean; message?: string; error?: string }>;
        removeSecurityPin: (currentPin: string) => Promise<{ success: boolean; message?: string; error?: string }>;
        unlockVault: (passphrase?: string) => Promise<any>;
        logout: () => Promise<any>;
        getSettings: () => Promise<Record<string, any>>;
        saveSettings: (settings: Record<string, any>) => Promise<{ success: boolean; settings?: any; error?: string }>;
        checkGoogleConfigured: () => Promise<{
          configured: boolean;
          valid?: boolean;
          clientId?: string;
          source?: string;
          tokenExists: boolean;
          authRequired?: boolean;
        }>;
        selectGoogleClientSecret: () => Promise<{ success: boolean; message: string; clientId?: string }>;
        saveGoogleCredentials: (clientId: string, clientSecret: string) => Promise<{ success: boolean; message: string; clientId?: string }>;
        authenticateCustomMailbox: (config: {
          email: string;
          password?: string;
          displayName?: string;
          organization?: string;
          imapHost?: string;
          imapPort?: number;
          smtpHost?: string;
          smtpPort?: number;
        }) => Promise<{ success: boolean; message?: string; account?: any; messages?: EmailMessage[] }>;
        checkRecipient: (email: string) => Promise<{ registered: boolean; deviceCount?: number; securityMode: string; warning?: string; message: string }>;
        exportIdentityFile: (data: any) => Promise<{ success: boolean; path?: string; filename?: string; message?: string }>;
        saveAttachment: (data: { name: string; data?: string; mediaType?: string; [key: string]: any }) => Promise<{ success: boolean; path?: string; filename?: string; message?: string }>;
        getInitialSyncStatus?: () => Promise<{ isInitialSyncing: boolean; stagedCount: number }>;
        checkTranslationCompatibility: () => Promise<TranslationCompatibility>;
        getTranslationStatus: () => Promise<TranslationStatus>;
        downloadTranslationPack: () => Promise<{ status: string }>;
        cancelTranslationDownload: () => Promise<{ status: string }>;
        deleteTranslationPack: () => Promise<{ status: string }>;
        unloadTranslationModel: () => Promise<{ status: string; wasLoaded?: boolean; isModelLoadedInRam: boolean }>;
        cancelTranslation?: () => Promise<{ status: string }>;
        translateEmailContent: (messageId: string, text: string, targetLang: string, subject?: string) => Promise<{ status: string; translatedText?: string; translatedSubject?: string; sourceLang?: string; targetLang?: string; fromCache?: boolean; error?: string }>;
        getCachedTranslation?: (messageId: string, targetLang: string) => Promise<{ status: string; translatedText?: string; translatedSubject?: string; sourceLang?: string; targetLang?: string; fromCache?: boolean }>;
        getTranslationLogs: () => Promise<TranslationLogEntry[]>;
        deleteTranslationLog: (messageId?: string) => Promise<{ status: string; remaining: number }>;
        refreshAccountAvatar?: () => Promise<{ success: boolean; avatarUrl?: string }>;
        fetchStandardEmailBody?: (messageId: string) => Promise<{ success: boolean; body?: string; subject?: string }>;
        minimize_window?: () => Promise<{ success: boolean; message?: string }>;
        close_window?: () => Promise<{ success: boolean; message?: string }>;
        toggle_fullscreen?: () => Promise<{ success: boolean; message?: string }>;
      };
    };
  }
}

function callBridgeWithTimeout<T>(
  callFn: () => Promise<T>,
  timeoutMs: number,
  fallbackValue: T,
  label: string = 'bridge_call'
): Promise<T> {
  return new Promise<T>((resolve) => {
    let settled = false;
    const timer = setTimeout(() => {
      if (!settled) {
        settled = true;
        console.warn(`[QuMail Bridge] Call "${label}" timed out after ${timeoutMs}ms, using fallback.`);
        resolve(fallbackValue);
      }
    }, timeoutMs);

    try {
      callFn()
        .then((res) => {
          if (!settled) {
            settled = true;
            clearTimeout(timer);
            resolve(res);
          }
        })
        .catch((err) => {
          if (!settled) {
            settled = true;
            clearTimeout(timer);
            console.warn(`[QuMail Bridge] Call "${label}" rejected:`, err);
            resolve(fallbackValue);
          }
        });
    } catch (err) {
      if (!settled) {
        settled = true;
        clearTimeout(timer);
        console.warn(`[QuMail Bridge] Call "${label}" threw synchronously:`, err);
        resolve(fallbackValue);
      }
    }
  });
}

class ApiService {
  private messages: EmailMessage[] = [];
  private account: AccountSession = { ...INITIAL_ACCOUNT };
  private hsm: HSMStatus = { ...INITIAL_HSM };

  /**
   * Deterministic readiness probe ensuring Edge WebView2 Python bridge is active
   * before any cryptographic, account, or mailbox requests fire.
   */
  async waitForBackend(timeoutMs: number = 6000): Promise<boolean> {
    if (window.pywebview?.api?.ping) {
      try {
        const res = await window.pywebview.api.ping();
        return Boolean(res?.pong);
      } catch {
        // Fall through to poll/listener
      }
    }

    const start = Date.now();
    return new Promise((resolve) => {
      let resolved = false;

      const finish = (val: boolean) => {
        if (!resolved) {
          resolved = true;
          window.removeEventListener('pywebviewready', onReady);
          clearInterval(interval);
          resolve(val);
        }
      };

      const onReady = async () => {
        try {
          if (window.pywebview?.api?.ping) {
            const res = await window.pywebview.api.ping();
            finish(Boolean(res?.pong));
            return;
          }
        } catch {}
        finish(Boolean(window.pywebview?.api));
      };

      window.addEventListener('pywebviewready', onReady);

      const interval = setInterval(async () => {
        if (window.pywebview?.api?.ping) {
          try {
            const res = await window.pywebview.api.ping();
            if (res?.pong) {
              finish(true);
              return;
            }
          } catch {}
        }
        if (Date.now() - start >= timeoutMs) {
          finish(false);
        }
      }, 50);
    });
  }

  async getMessages(): Promise<EmailMessage[]> {
    if (window.pywebview?.api?.getMessages) {
      try {
        const res = await window.pywebview.api.getMessages();
        this.messages = res || [];
        return this.messages;
      } catch (e) {
        console.warn('Pywebview API getMessages failed:', e);
      }
    }
    return [...this.messages];
  }

  async fetchInbox(limit: number = 50): Promise<EmailMessage[]> {
    if (window.pywebview?.api?.fetchInbox) {
      try {
        const res = await window.pywebview.api.fetchInbox(limit);
        this.messages = res || [];
        return this.messages;
      } catch (e) {
        console.warn('Pywebview API fetchInbox failed:', e);
      }
    }
    return [...this.messages];
  }

  async sendMessage(draft: Partial<EmailMessage> & { draftId?: string; outboxId?: string }): Promise<{ success: boolean; id?: string; folder?: string; queuedInOutbox?: boolean; message?: string }> {
    if (window.pywebview?.api?.sendMessage) {
      try {
        const res = await window.pywebview.api.sendMessage(draft);
        if (res.success) {
          await this.getMessages();
        }
        return res;
      } catch (e: any) {
        console.error('Pywebview API sendMessage exception:', e);
        return { success: false, message: e?.message || 'Failed to dispatch email.' };
      }
    }
    return { success: false, message: 'QuMail desktop bridge is not connected.' };
  }

  async markRead(id: string, seen: boolean): Promise<boolean> {
    if (window.pywebview?.api?.markRead) {
      try {
        return await window.pywebview.api.markRead(id, seen);
      } catch (e) {
        console.warn('Pywebview API markRead failed:', e);
      }
    }
    this.messages = this.messages.map((m) => (m.id === id ? { ...m, seen } : m));
    return true;
  }

  async toggleStar(id: string): Promise<boolean> {
    if (window.pywebview?.api?.toggleStar) {
      try {
        return await window.pywebview.api.toggleStar(id);
      } catch (e) {
        console.warn('Pywebview API toggleStar failed:', e);
      }
    }
    this.messages = this.messages.map((m) => (m.id === id ? { ...m, starred: !m.starred } : m));
    return true;
  }

  async deleteMessage(id: string): Promise<boolean> {
    if (window.pywebview?.api?.deleteMessage) {
      try {
        return await window.pywebview.api.deleteMessage(id);
      } catch (e) {
        console.warn('Pywebview API deleteMessage failed:', e);
      }
    }
    this.messages = this.messages.filter((m) => m.id !== id);
    return true;
  }

  async saveDraft(draft: Partial<EmailMessage>): Promise<{ success: boolean; id?: string; draft?: EmailMessage }> {
    if (window.pywebview?.api?.saveDraft) {
      try {
        return await window.pywebview.api.saveDraft(draft);
      } catch (e) {
        console.warn('Pywebview API saveDraft failed:', e);
      }
    }
    const id = draft.id || `draft-${Date.now()}`;
    return { success: true, id };
  }

  async getHSMStatus(): Promise<HSMStatus> {
    if (window.pywebview?.api?.getHSMStatus) {
      try {
        const raw = await window.pywebview.api.getHSMStatus();
        return {
          isHardwareActive: Boolean(raw.isHardwareActive),
          activePort: raw.activePort || '',
          mode: raw.mode || 'AUTO',
          rateBps: raw.baudRate || 0,
          continuousPassed: raw.healthStatus === 'PASSED',
        };
      } catch (e) {
        console.warn('Pywebview API getHSMStatus failed:', e);
      }
    }
    return { ...this.hsm };
  }

  async sampleEntropy(): Promise<{ success: boolean; hex: string; rate: number }> {
    if (window.pywebview?.api?.sampleEntropy) {
      try {
        return await window.pywebview.api.sampleEntropy();
      } catch (e) {
        console.warn('Pywebview API sampleEntropy failed:', e);
      }
    }
    return {
      success: false,
      hex: '',
      rate: 0,
    };
  }

  async getAccount(): Promise<AccountSession> {
    if (window.pywebview?.api?.getAccount) {
      try {
        const acc = await window.pywebview.api.getAccount();
        if (acc) {
          const hasPin = Boolean(acc.hasSecurityPin);
          const emailAddr = acc.email || '';
          const rawDn = acc.displayName || '';
          const effectiveDn = (rawDn && rawDn !== emailAddr.split('@')[0]) ? rawDn : (emailAddr || 'User');
          this.account = {
            email: emailAddr,
            displayName: effectiveDn,
            avatarUrl: acc.avatarUrl || '',
            provider: acc.organization || 'Google Workspace / Gmail',
            pqcAlgorithm: acc.kemAlgorithm || 'ML-KEM-768 (NIST FIPS 203)',
            pqcIdentity: acc.keyFingerprint || (acc.email ? `0x${acc.email.slice(0, 4)}...PQ` : ''),
            isUnlocked: acc.vaultState !== 'LOCKED' && acc.sessionState !== 'LOCKED',
            hasSecurityPin: hasPin,
            vaultState: acc.vaultState,
            sessionState: acc.sessionState,
            connectionStatus: acc.connectionStatus,
            syncError: acc.syncError,
          };
          return { ...this.account };
        }
      } catch (e) {
        console.warn('Pywebview API getAccount failed:', e);
      }
    }
    this.account = { ...INITIAL_ACCOUNT, isUnlocked: false };
    return { ...this.account };
  }

  async refreshAccountAvatar(): Promise<{ success: boolean; avatarUrl?: string }> {
    if (window.pywebview?.api?.refreshAccountAvatar) {
      const res = await callBridgeWithTimeout(
        () => window.pywebview!.api.refreshAccountAvatar!(),
        6000,
        { success: false, avatarUrl: this.account?.avatarUrl || '' },
        'refreshAccountAvatar'
      );
      if (res?.success && res.avatarUrl) {
        if (this.account) {
          this.account.avatarUrl = res.avatarUrl;
        }
      }
      return res;
    }
    return { success: false, avatarUrl: this.account?.avatarUrl || '' };
  }

  async checkRecipient(email: string): Promise<{ registered: boolean; deviceCount?: number; securityMode: string; warning?: string; message: string }> {
    if (window.pywebview?.api?.checkRecipient) {
      try {
        return await (window.pywebview.api as any).checkRecipient(email);
      } catch (e: any) {
        console.warn('checkRecipient query note:', e);
      }
    }
    return {
      registered: false,
      securityMode: 'weblink',
      message: 'Cloud directory check pending.',
    };
  }

  async loginAccount(email: string, displayName?: string, organization?: string): Promise<AccountSession> {
    const trimmed = email.trim();
    if (window.pywebview?.api?.loginAccount) {
      try {
        const acc = await window.pywebview.api.loginAccount(trimmed, displayName, organization);
        if (acc && acc.email) {
          const rawDn = acc.displayName || '';
          const effectiveDn = (rawDn && rawDn !== trimmed.split('@')[0]) ? rawDn : trimmed;
          this.account = {
            email: acc.email,
            displayName: effectiveDn,
            provider: acc.organization || 'QuMail Secure Corporate',
            pqcAlgorithm: acc.kemAlgorithm || 'NIST FIPS 203 (ML-KEM-768) + NIST FIPS 204 (ML-DSA-65)',
            pqcIdentity: `0x${trimmed.slice(0, 4)}...PQ768`,
            isUnlocked: true,
          };
          return { ...this.account };
        }
      } catch (e) {
        console.warn('Pywebview loginAccount failed:', e);
      }
    }
    this.account = { ...INITIAL_ACCOUNT, isUnlocked: false };
    return { ...this.account };
  }

  async authenticateCustomMailbox(config: {
    email: string;
    password?: string;
    displayName?: string;
    organization?: string;
    imapHost?: string;
    imapPort?: number;
    smtpHost?: string;
    smtpPort?: number;
  }): Promise<{ success: boolean; account?: AccountSession; message?: string }> {
    if (window.pywebview?.api?.authenticateCustomMailbox) {
      try {
        const res = await window.pywebview.api.authenticateCustomMailbox(config);
        if (res.success && res.account) {
          const domain = config.email.split('@')[1] || 'Custom';
          const accEmail = res.account.email || config.email;
          const rawDn = res.account.displayName || config.displayName || '';
          const effectiveDn = (rawDn && rawDn !== accEmail.split('@')[0]) ? rawDn : accEmail;
          this.account = {
            email: accEmail,
            displayName: effectiveDn,
            provider: `${domain.charAt(0).toUpperCase() + domain.slice(1)} (IMAP/TLS)`,
            pqcAlgorithm: 'NIST FIPS 203 (ML-KEM-768) + NIST FIPS 204 (ML-DSA-65)',
            pqcIdentity: `0x${res.account.email.slice(0, 4)}...PQ768`,
            isUnlocked: true,
          };
          if (res.messages) {
            this.messages = res.messages;
          }
          return { success: true, account: this.account };
        }
        return { success: false, message: res.message || 'Custom mailbox authentication failed.' };
      } catch (e: any) {
        return { success: false, message: e?.message || 'Authentication check error.' };
      }
    }
    return { success: false, message: 'Custom mailbox verification requires the QuMail desktop environment.' };
  }

  async logoutAccount(): Promise<boolean> {
    this.account = { ...INITIAL_ACCOUNT, isUnlocked: false };
    this.messages = [];

    if (window.pywebview?.api?.logoutAccount) {
      try {
        await window.pywebview.api.logoutAccount();
      } catch (e) {
        console.warn('Pywebview logoutAccount failed:', e);
      }
    }
    return true;
  }

  async signInWithGoogle(): Promise<{ success: boolean; account?: AccountSession; needsClientSecret?: boolean; message?: string }> {
    if (window.pywebview?.api?.googleAuth) {
      try {
        const res = await window.pywebview.api.googleAuth();
        if (res.success && res.account) {
          const accEmail = res.account.email || '';
          const rawDn = res.account.displayName || '';
          const effectiveDn = (rawDn && rawDn !== accEmail.split('@')[0]) ? rawDn : accEmail;
          this.account = {
            email: accEmail,
            displayName: effectiveDn,
            provider: 'Google Workspace / Gmail',
            pqcAlgorithm: 'NIST FIPS 203 (ML-KEM-768) + NIST FIPS 204 (ML-DSA-65)',
            pqcIdentity: `0x${res.account.email.slice(0, 4)}...PQ768`,
            isUnlocked: true,
          };
          if (res.messages) {
            this.messages = res.messages;
          }
          return { success: true, account: this.account };
        }
        return res;
      } catch (e: any) {
        return { success: false, message: e?.message || 'Google OAuth failed' };
      }
    }
    return { success: false, message: 'Google Auth requires the QuMail desktop environment.' };
  }

  async checkGoogleConfigured(): Promise<{
    configured: boolean;
    valid?: boolean;
    clientId?: string;
    source?: string;
    tokenExists: boolean;
    authRequired?: boolean;
  }> {
    if (window.pywebview?.api?.checkGoogleConfigured) {
      try {
        return await window.pywebview.api.checkGoogleConfigured();
      } catch (e) {
        console.warn('checkGoogleConfigured failed:', e);
      }
    }
    return { configured: false, tokenExists: false };
  }

  async selectGoogleClientSecret(): Promise<{ success: boolean; message: string; clientId?: string }> {
    if (window.pywebview?.api?.selectGoogleClientSecret) {
      try {
        return await window.pywebview.api.selectGoogleClientSecret();
      } catch (e: any) {
        return { success: false, message: e?.message || 'Failed to select client secret' };
      }
    }
    return { success: false, message: 'File picker is not available outside desktop environment.' };
  }

  async saveGoogleCredentials(clientId: string, clientSecret: string): Promise<{ success: boolean; message: string; clientId?: string }> {
    if (window.pywebview?.api?.saveGoogleCredentials) {
      try {
        return await window.pywebview.api.saveGoogleCredentials(clientId, clientSecret);
      } catch (e: any) {
        return { success: false, message: e?.message || 'Failed to save credentials' };
      }
    }
    return { success: false, message: 'Not available outside desktop environment.' };
  }

  async getSessionStatus(): Promise<any> {
    if (window.pywebview?.api?.getSessionStatus) {
      try {
        return await window.pywebview.api.getSessionStatus();
      } catch (e) {
        console.warn('Pywebview getSessionStatus failed:', e);
      }
    }
    return {
      sessionState: this.account.isUnlocked ? 'MAILBOX_READY' : 'SIGNED_OUT',
      vaultState: this.account.isUnlocked ? 'UNLOCKED' : 'LOCKED',
      account: this.account.email ? this.account : null,
      lastError: null,
      kemAlgorithm: 'ML-KEM-768 (NIST FIPS 203)',
      dsaAlgorithm: 'ML-DSA-65 (NIST FIPS 204)',
    };
  }

  async connectGoogle(): Promise<{ success: boolean; account?: AccountSession; message?: string }> {
    return this.signInWithGoogle();
  }

  async hasSecurityPin(): Promise<boolean> {
    if (window.pywebview?.api?.hasSecurityPin) {
      try {
        const hasPin = await window.pywebview.api.hasSecurityPin();
        this.account = { ...this.account, hasSecurityPin: Boolean(hasPin) };
        return Boolean(hasPin);
      } catch (e) {
        console.warn('hasSecurityPin error:', e);
      }
    }
    return Boolean(this.account?.hasSecurityPin);
  }

  async setSecurityPin(newPin: string, currentPin: string = ''): Promise<{ success: boolean; message?: string; error?: string }> {
    if (window.pywebview?.api?.setSecurityPin) {
      try {
        const res = await window.pywebview.api.setSecurityPin(newPin, currentPin);
        if (res.success) {
          this.account = { ...this.account, hasSecurityPin: true };
        }
        return res;
      } catch (e: any) {
        return { success: false, error: e?.message || 'Failed to set Security PIN' };
      }
    }
    return { success: false, error: 'QuMail desktop bridge is not connected.' };
  }

  async removeSecurityPin(currentPin: string): Promise<{ success: boolean; message?: string; error?: string }> {
    if (window.pywebview?.api?.removeSecurityPin) {
      try {
        const res = await window.pywebview.api.removeSecurityPin(currentPin);
        if (res.success) {
          this.account = { ...this.account, hasSecurityPin: false };
        }
        return res;
      } catch (e: any) {
        return { success: false, error: e?.message || 'Failed to remove Security PIN' };
      }
    }
    return { success: false, error: 'QuMail desktop bridge is not connected.' };
  }

  async lockVault(): Promise<boolean> {
    if (window.pywebview?.api?.lockVault) {
      try {
        await window.pywebview.api.lockVault();
      } catch (e) {
        console.warn('Pywebview lockVault failed:', e);
      }
    }
    this.account = { ...this.account, isUnlocked: false };
    return true;
  }

  async unlockVault(passphrase: string = ''): Promise<{ success: boolean; sessionStatus?: any; messages?: any[]; message?: string; error?: string; cooldownSeconds?: number }> {
    if (window.pywebview?.api?.unlockVault) {
      try {
        const res = await window.pywebview.api.unlockVault(passphrase);
        if (res.success) {
          this.account = { ...this.account, isUnlocked: true };
          return res;
        }
        return res;
      } catch (e: any) {
        return { success: false, error: e?.message || 'Failed to unlock vault', message: e?.message };
      }
    }
    return { success: false, error: 'QuMail desktop bridge is not connected.' };
  }

  async getInitialSyncStatus(): Promise<{ isInitialSyncing: boolean; stagedCount: number }> {
    if (window.pywebview?.api?.getInitialSyncStatus) {
      try {
        return await window.pywebview.api.getInitialSyncStatus();
      } catch {
        return { isInitialSyncing: false, stagedCount: 0 };
      }
    }
    return { isInitialSyncing: false, stagedCount: 0 };
  }

  async logout(): Promise<boolean> {
    return this.logoutAccount();
  }

  async getSettings(): Promise<Record<string, any>> {
    if (window.pywebview?.api?.getSettings) {
      try {
        const res = await window.pywebview.api.getSettings();
        if (res && typeof res === 'object') {
          return res;
        }
      } catch (e) {
        console.warn('Pywebview API getSettings failed:', e);
      }
    }
    return {};
  }

  async saveSettings(settings: Record<string, any>): Promise<boolean> {
    if (window.pywebview?.api?.saveSettings) {
      try {
        const res = await window.pywebview.api.saveSettings(settings);
        return Boolean(res?.success);
      } catch (e) {
        console.warn('Pywebview API saveSettings failed:', e);
        return false;
      }
    }
    return true;
  }

  async exportIdentityFile(data: {
    filename?: string;
    htmlContent?: string;
    [key: string]: any;
  }): Promise<{ success: boolean; path?: string; filename?: string; message?: string }> {
    if (window.pywebview?.api?.exportIdentityFile) {
      try {
        return await window.pywebview.api.exportIdentityFile(data);
      } catch (e: any) {
        console.warn('Pywebview API exportIdentityFile failed:', e);
        return { success: false, message: e?.message || 'Export failed' };
      }
    }
    // Browser fallback
    try {
      const content = data.htmlContent || JSON.stringify(data, null, 2);
      const blob = new Blob([content], { type: 'text/html;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = data.filename || 'qumail-identity-certificate.html';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      return { success: true, filename: data.filename || 'qumail-identity-certificate.html' };
    } catch (err: any) {
      return { success: false, message: err?.message || 'Download failed' };
    }
  }

  async saveAttachment(data: {
    name: string;
    data?: string;
    mediaType?: string;
    [key: string]: any;
  }): Promise<{ success: boolean; path?: string; filename?: string; message?: string }> {
    if (window.pywebview?.api?.saveAttachment) {
      try {
        return await window.pywebview.api.saveAttachment(data);
      } catch (e: any) {
        console.warn('Pywebview API saveAttachment failed, falling back to browser download:', e);
      }
    }
    // Browser fallback
    try {
      if (data.data) {
        const link = document.createElement('a');
        link.href = `data:${data.mediaType || 'application/octet-stream'};base64,${data.data}`;
        link.download = data.name || 'attachment.bin';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        return { success: true, filename: data.name, message: `Attachment saved · ${data.name}` };
      }
      return { success: false, message: 'Attachment payload is empty' };
    } catch (err: any) {
      return { success: false, message: err?.message || 'Download failed' };
    }
  }

  async updateAccountEmail(email: string): Promise<boolean> {
    return (await this.loginAccount(email)) !== null;
  }

  // ------------------------------------------------------------------------
  // Offline Neural Translation API
  // ------------------------------------------------------------------------

  async checkTranslationCompatibility(): Promise<TranslationCompatibility> {
    const fallback: TranslationCompatibility = {
      status: 'ok',
      total_ram_gb: 8.0,
      free_ram_gb: 3.5,
      free_disk_gb: 25.0,
      cpu_cores: 8,
      verdict: 'optimal',
      estimated_speed: 'Fast (~1–2 sec per email)',
      warning: null,
    };
    if (window.pywebview?.api?.checkTranslationCompatibility) {
      return callBridgeWithTimeout(
        () => window.pywebview!.api.checkTranslationCompatibility(),
        5000,
        fallback,
        'checkTranslationCompatibility'
      );
    }
    return fallback;
  }

  async getTranslationStatus(): Promise<TranslationStatus> {
    const fallback: TranslationStatus = {
      isInstalled: false,
      isDownloading: false,
      progress: 0,
      downloadedMB: 0,
      totalMB: 628.7,
      currentFile: '',
      error: null,
      modelSizeMB: 0,
    };
    if (window.pywebview?.api?.getTranslationStatus) {
      return callBridgeWithTimeout(
        () => window.pywebview!.api.getTranslationStatus(),
        8000,
        fallback,
        'getTranslationStatus'
      );
    }
    return fallback;
  }

  async downloadTranslationPack(): Promise<{ status: string }> {
    if (window.pywebview?.api?.downloadTranslationPack) {
      return callBridgeWithTimeout(
        () => window.pywebview!.api.downloadTranslationPack(),
        6000,
        { status: 'started' },
        'downloadTranslationPack'
      );
    }
    return { status: 'started' };
  }

  async cancelTranslationDownload(): Promise<{ status: string }> {
    if (window.pywebview?.api?.cancelTranslationDownload) {
      return callBridgeWithTimeout(
        () => window.pywebview!.api.cancelTranslationDownload(),
        4000,
        { status: 'cancelled' },
        'cancelTranslationDownload'
      );
    }
    return { status: 'cancelled' };
  }

  async deleteTranslationPack(): Promise<{ status: string }> {
    if (window.pywebview?.api?.deleteTranslationPack) {
      return callBridgeWithTimeout(
        () => window.pywebview!.api.deleteTranslationPack(),
        6000,
        { status: 'deleted' },
        'deleteTranslationPack'
      );
    }
    return { status: 'deleted' };
  }

  async unloadTranslationModel(): Promise<{ status: string; wasLoaded?: boolean; isModelLoadedInRam: boolean }> {
    const fallback = { status: 'ok', wasLoaded: false, isModelLoadedInRam: false };
    if (window.pywebview?.api?.unloadTranslationModel) {
      return callBridgeWithTimeout(
        () => window.pywebview!.api.unloadTranslationModel(),
        6000,
        fallback,
        'unloadTranslationModel'
      );
    }
    return fallback;
  }

  async cancelTranslation(): Promise<{ status: string }> {
    if (window.pywebview?.api?.cancelTranslation) {
      return callBridgeWithTimeout(
        () => window.pywebview!.api.cancelTranslation!(),
        4000,
        { status: 'cancelled' },
        'cancelTranslation'
      );
    }
    return { status: 'cancelled' };
  }

  async fetchStandardEmailBody(messageId: string): Promise<{ success: boolean; body?: string; subject?: string }> {
    const fallback = { success: false, body: '', subject: '' };
    if (window.pywebview?.api?.fetchStandardEmailBody) {
      return callBridgeWithTimeout(
        () => window.pywebview!.api.fetchStandardEmailBody!(messageId),
        10000,
        fallback,
        'fetchStandardEmailBody'
      );
    }
    return fallback;
  }

  async translateEmailContent(
    messageId: string,
    text: string,
    targetLang: string,
    subject?: string
  ): Promise<{
    status: string;
    translatedText?: string;
    translatedSubject?: string;
    sourceLang?: string;
    targetLang?: string;
    fromCache?: boolean;
    error?: string;
  }> {
    const fallback = {
      status: 'error',
      error: 'Translation timed out or service unavailable',
    };
    if (window.pywebview?.api?.translateEmailContent) {
      return callBridgeWithTimeout(
        () => window.pywebview!.api.translateEmailContent(messageId, text, targetLang, subject || ''),
        25000,
        fallback,
        'translateEmailContent'
      );
    }
    return {
      status: 'ok',
      translatedText: text ? `[Translated to ${targetLang}]: ${text}` : '',
      translatedSubject: subject ? `[Translated to ${targetLang}]: ${subject}` : undefined,
      sourceLang: 'eng_Latn',
      targetLang,
      fromCache: false,
    };
  }

  async getCachedTranslation(
    messageId: string,
    targetLang: string
  ): Promise<{
    status: string;
    translatedText?: string;
    translatedSubject?: string;
    sourceLang?: string;
    targetLang?: string;
    fromCache?: boolean;
  }> {
    const fallback = { status: 'not_cached', fromCache: false };
    if (window.pywebview?.api?.getCachedTranslation) {
      return callBridgeWithTimeout(
        () => window.pywebview!.api.getCachedTranslation!(messageId, targetLang),
        4000,
        fallback,
        'getCachedTranslation'
      );
    }
    return fallback;
  }

  async getTranslationLogs(): Promise<TranslationLogEntry[]> {
    if (window.pywebview?.api?.getTranslationLogs) {
      return callBridgeWithTimeout(
        () => window.pywebview!.api.getTranslationLogs(),
        5000,
        [],
        'getTranslationLogs'
      );
    }
    return [];
  }

  async deleteTranslationLog(messageId?: string): Promise<{ status: string; remaining: number }> {
    if (window.pywebview?.api?.deleteTranslationLog) {
      return callBridgeWithTimeout(
        () => window.pywebview!.api.deleteTranslationLog(messageId || ''),
        5000,
        { status: 'ok', remaining: 0 },
        'deleteTranslationLog'
      );
    }
    return { status: 'ok', remaining: 0 };
  }

  async minimizeWindow(): Promise<{ success: boolean }> {
    if (window.pywebview?.api?.minimize_window) {
      return callBridgeWithTimeout(
        () => window.pywebview!.api.minimize_window!(),
        3000,
        { success: false },
        'minimizeWindow'
      );
    }
    return { success: false };
  }

  async closeWindow(): Promise<{ success: boolean }> {
    if (window.pywebview?.api?.close_window) {
      return callBridgeWithTimeout(
        () => window.pywebview!.api.close_window!(),
        3000,
        { success: false },
        'closeWindow'
      );
    }
    return { success: false };
  }

  async toggleFullscreen(): Promise<{ success: boolean }> {
    if (window.pywebview?.api?.toggle_fullscreen) {
      return callBridgeWithTimeout(
        () => window.pywebview!.api.toggle_fullscreen!(),
        3000,
        { success: false },
        'toggleFullscreen'
      );
    }
    return { success: false };
  }
}

export const api = new ApiService();
