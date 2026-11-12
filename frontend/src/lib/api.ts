import { EmailMessage, HSMStatus, AccountSession } from '../types';
import { INITIAL_ACCOUNT, INITIAL_HSM } from '../initialState';

// Extend Window interface for pywebview
declare global {
  interface Window {
    pywebview?: {
      api: {
        ping: () => Promise<{ pong: boolean; version: string; timestamp: number; authenticated: boolean }>;
        getMessages: () => Promise<EmailMessage[]>;
        fetchInbox: () => Promise<EmailMessage[]>;
        sendMessage: (msg: Partial<EmailMessage>) => Promise<{ success: boolean; id?: string; message?: string }>;
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
        unlockVault: (passphrase?: string) => Promise<any>;
        logout: () => Promise<any>;
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
      };
    };
  }
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

  async fetchInbox(): Promise<EmailMessage[]> {
    if (window.pywebview?.api?.fetchInbox) {
      try {
        const res = await window.pywebview.api.fetchInbox();
        this.messages = res || [];
        return this.messages;
      } catch (e) {
        console.warn('Pywebview API fetchInbox failed:', e);
      }
    }
    return [...this.messages];
  }

  async sendMessage(draft: Partial<EmailMessage>): Promise<{ success: boolean; id?: string; message?: string }> {
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
        if (acc && acc.email) {
          this.account = {
            email: acc.email,
            displayName: acc.displayName || acc.email.split('@')[0],
            provider: acc.organization || 'Google Workspace / Gmail',
            pqcAlgorithm: acc.kemAlgorithm || 'ML-KEM-768 (NIST FIPS 203)',
            pqcIdentity: `0x${acc.email.slice(0, 4)}...PQ`,
            isUnlocked: true,
          };
          return { ...this.account };
        } else {
          this.account = { ...INITIAL_ACCOUNT, isUnlocked: false };
          return { ...this.account };
        }
      } catch (e) {
        console.warn('Pywebview API getAccount failed:', e);
      }
    }
    this.account = { ...INITIAL_ACCOUNT, isUnlocked: false };
    return { ...this.account };
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
          this.account = {
            email: acc.email,
            displayName: acc.displayName || trimmed.split('@')[0],
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
          this.account = {
            email: res.account.email,
            displayName: res.account.displayName || config.displayName || res.account.email.split('@')[0],
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
          this.account = {
            email: res.account.email,
            displayName: res.account.displayName || res.account.email.split('@')[0],
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

  async unlockVault(passphrase: string = ''): Promise<{ success: boolean; sessionStatus?: any; message?: string }> {
    if (window.pywebview?.api?.unlockVault) {
      try {
        const res = await window.pywebview.api.unlockVault(passphrase);
        if (res.success) {
          this.account = { ...this.account, isUnlocked: true };
          return res;
        }
        return res;
      } catch (e: any) {
        return { success: false, message: e?.message || 'Failed to unlock vault' };
      }
    }
    return { success: false, message: 'QuMail desktop bridge is not connected.' };
  }

  async logout(): Promise<boolean> {
    return this.logoutAccount();
  }

  async updateAccountEmail(email: string): Promise<boolean> {
    return (await this.loginAccount(email)) !== null;
  }
}

export const api = new ApiService();
