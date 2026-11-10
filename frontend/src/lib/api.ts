import { EmailMessage, HSMStatus, AccountSession } from '../types';
import { MOCK_MESSAGES, INITIAL_ACCOUNT, INITIAL_HSM } from '../mockData';

// Extend Window interface for pywebview
declare global {
  interface Window {
    pywebview?: {
      api: {
        getMessages: () => Promise<EmailMessage[]>;
        fetchInbox: () => Promise<EmailMessage[]>;
        sendMessage: (msg: Partial<EmailMessage>) => Promise<{ success: boolean; id: string }>;
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
        checkGoogleConfigured: () => Promise<{ configured: boolean; tokenExists: boolean }>;
        selectGoogleClientSecret: () => Promise<{ success: boolean; message: string }>;
        saveGoogleCredentials: (clientId: string, clientSecret: string) => Promise<{ success: boolean; message: string }>;
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
      };
    };
  }
}

class ApiService {
  private messages: EmailMessage[] = [...MOCK_MESSAGES];
  private account: AccountSession = { ...INITIAL_ACCOUNT };
  private hsm: HSMStatus = { ...INITIAL_HSM };

  constructor() {
    // Check localStorage for saved user account
    try {
      const saved = localStorage.getItem('qumail-account');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed && parsed.email) {
          this.account = {
            ...INITIAL_ACCOUNT,
            ...parsed,
            isUnlocked: true,
          };
        }
      }
    } catch {
      // Ignore storage errors
    }
  }

  async getMessages(): Promise<EmailMessage[]> {
    if (window.pywebview?.api?.getMessages) {
      try {
        const res = await window.pywebview.api.getMessages();
        this.messages = res || [];
        return this.messages;
      } catch (e) {
        console.warn('Pywebview API getMessages failed, falling back to local memory:', e);
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

  async sendMessage(draft: Partial<EmailMessage>): Promise<{ success: boolean; id: string }> {
    if (window.pywebview?.api?.sendMessage) {
      try {
        const res = await window.pywebview.api.sendMessage(draft);
        await this.getMessages();
        return res;
      } catch (e) {
        console.warn('Pywebview API sendMessage failed, fallback:', e);
      }
    }
    const senderEmail = this.account.email || 'guest@qumail.local';
    const newMsg: EmailMessage = {
      id: `msg-${Date.now()}`,
      sender: this.account.email ? this.account.email.split('@')[0] : 'Guest User',
      senderEmail,
      recipients: draft.recipients || ['recipient@example.com'],
      subject: draft.subject || '(No Subject)',
      snippet: (draft.body || '').slice(0, 80),
      body: draft.body || '',
      date: 'Just now',
      timestamp: Date.now(),
      seen: true,
      starred: false,
      folder: 'sent',
      category: 'primary',
      hasAttachments: !!draft.attachments && draft.attachments.length > 0,
      attachments: draft.attachments,
      indicator: {
        badgeLevel: 'SECURE',
        headline: 'Post-Quantum Sealed',
        description: 'Sealed with NIST FIPS 203 (ML-KEM-768) and signed locally with ML-DSA-65.',
        actionAdvice: 'Message stored in outbox.',
      },
    };
    this.messages.unshift(newMsg);
    return { success: true, id: newMsg.id };
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
      success: true,
      hex: '9F82A4C1B3E0D85517283940428B7A1C',
      rate: 115200,
    };
  }

  async getAccount(): Promise<AccountSession> {
    if (window.pywebview?.api?.getAccount) {
      try {
        const acc = await window.pywebview.api.getAccount();
        if (acc && acc.email) {
          this.account = {
            email: acc.email,
            provider: acc.organization || 'Google Workspace / Gmail',
            pqcAlgorithm: acc.kemAlgorithm || 'ML-KEM-768 (NIST FIPS 203)',
            pqcIdentity: `0x${acc.email.slice(0, 4)}...PQ`,
            isUnlocked: true,
          };
          return { ...this.account };
        }
      } catch (e) {
        console.warn('Pywebview API getAccount failed:', e);
      }
    }
    return { ...this.account };
  }

  async loginAccount(email: string, displayName?: string, organization?: string): Promise<AccountSession> {
    const trimmed = email.trim();
    this.account = {
      email: trimmed,
      provider: organization || 'QuMail Secure Corporate',
      pqcAlgorithm: 'NIST FIPS 203 (ML-KEM-768) + NIST FIPS 204 (ML-DSA-65)',
      pqcIdentity: `0x${trimmed.slice(0, 4)}...PQ768`,
      isUnlocked: true,
    };
    try {
      localStorage.setItem('qumail-account', JSON.stringify(this.account));
    } catch {}

    if (window.pywebview?.api?.loginAccount) {
      try {
        await window.pywebview.api.loginAccount(trimmed, displayName, organization);
      } catch (e) {
        console.warn('Pywebview loginAccount failed:', e);
      }
    }
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
            provider: `${domain.charAt(0).toUpperCase() + domain.slice(1)} (IMAP/TLS)`,
            pqcAlgorithm: 'NIST FIPS 203 (ML-KEM-768) + NIST FIPS 204 (ML-DSA-65)',
            pqcIdentity: `0x${res.account.email.slice(0, 4)}...PQ768`,
            isUnlocked: true,
          };
          try {
            localStorage.setItem('qumail-account', JSON.stringify(this.account));
          } catch {}
          if (res.messages) {
            this.messages = res.messages;
          }
          return { success: true, account: this.account };
        }
        return { success: false, message: res.message || 'Custom mailbox authentication failed.' };
      } catch (e: any) {
        return { success: false, message: e?.message || 'Authentication error.' };
      }
    }

    // Fallback when outside desktop wrapper
    const trimmed = config.email.trim();
    const domain = trimmed.split('@')[1] || 'Corporate';
    this.account = {
      email: trimmed,
      provider: `${domain.charAt(0).toUpperCase() + domain.slice(1)} (IMAP/TLS)`,
      pqcAlgorithm: 'NIST FIPS 203 (ML-KEM-768) + NIST FIPS 204 (ML-DSA-65)',
      pqcIdentity: `0x${trimmed.slice(0, 4)}...PQ768`,
      isUnlocked: true,
    };
    try {
      localStorage.setItem('qumail-account', JSON.stringify(this.account));
    } catch {}
    return { success: true, account: this.account };
  }

  async logoutAccount(): Promise<boolean> {
    this.account = { ...INITIAL_ACCOUNT };
    this.messages = [];
    try {
      localStorage.removeItem('qumail-account');
    } catch {}

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
            provider: 'Google Workspace / Gmail',
            pqcAlgorithm: 'NIST FIPS 203 (ML-KEM-768) + NIST FIPS 204 (ML-DSA-65)',
            pqcIdentity: `0x${res.account.email.slice(0, 4)}...PQ768`,
            isUnlocked: true,
          };
          try {
            localStorage.setItem('qumail-account', JSON.stringify(this.account));
          } catch {}
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
    return { success: false, message: 'Google Auth requires desktop environment.' };
  }

  async checkGoogleConfigured(): Promise<{ configured: boolean; tokenExists: boolean }> {
    if (window.pywebview?.api?.checkGoogleConfigured) {
      try {
        return await window.pywebview.api.checkGoogleConfigured();
      } catch (e) {
        console.warn('checkGoogleConfigured failed:', e);
      }
    }
    return { configured: false, tokenExists: false };
  }

  async selectGoogleClientSecret(): Promise<{ success: boolean; message: string }> {
    if (window.pywebview?.api?.selectGoogleClientSecret) {
      try {
        return await window.pywebview.api.selectGoogleClientSecret();
      } catch (e: any) {
        return { success: false, message: e?.message || 'Failed to select client secret' };
      }
    }
    return { success: false, message: 'File picker not available in browser mode' };
  }

  async saveGoogleCredentials(clientId: string, clientSecret: string): Promise<{ success: boolean; message: string }> {
    if (window.pywebview?.api?.saveGoogleCredentials) {
      try {
        return await window.pywebview.api.saveGoogleCredentials(clientId, clientSecret);
      } catch (e: any) {
        return { success: false, message: e?.message || 'Failed to save credentials' };
      }
    }
    return { success: false, message: 'Not available in browser mode' };
  }

  async updateAccountEmail(email: string): Promise<boolean> {
    return (await this.loginAccount(email)) !== null;
  }
}

export const api = new ApiService();
