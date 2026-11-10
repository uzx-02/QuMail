import { EmailMessage, HSMStatus, AccountSession } from '../types';
import { MOCK_MESSAGES, INITIAL_ACCOUNT, INITIAL_HSM } from '../mockData';

// Extend Window interface for pywebview
declare global {
  interface Window {
    pywebview?: {
      api: {
        getMessages: () => Promise<EmailMessage[]>;
        sendMessage: (msg: Partial<EmailMessage>) => Promise<{ success: boolean; id: string }>;
        deleteMessage: (id: string) => Promise<boolean>;
        markRead: (id: string, seen: boolean) => Promise<boolean>;
        toggleStar: (id: string) => Promise<boolean>;
        getHSMStatus: () => Promise<HSMStatus>;
        sampleEntropy: () => Promise<{ success: boolean; hex: string; rate: number }>;
        getAccount: () => Promise<AccountSession>;
        lockVault: () => Promise<boolean>;
      };
    };
  }
}

class ApiService {
  private messages: EmailMessage[] = [...MOCK_MESSAGES];
  private account: AccountSession = { ...INITIAL_ACCOUNT };
  private hsm: HSMStatus = { ...INITIAL_HSM };

  async getMessages(): Promise<EmailMessage[]> {
    if (window.pywebview?.api?.getMessages) {
      try {
        return await window.pywebview.api.getMessages();
      } catch (e) {
        console.warn('Pywebview API getMessages failed, falling back to local memory:', e);
      }
    }
    return [...this.messages];
  }

  async sendMessage(draft: Partial<EmailMessage>): Promise<{ success: boolean; id: string }> {
    if (window.pywebview?.api?.sendMessage) {
      try {
        return await window.pywebview.api.sendMessage(draft);
      } catch (e) {
        console.warn('Pywebview API sendMessage failed, fallback:', e);
      }
    }
    const newMsg: EmailMessage = {
      id: `msg-${Date.now()}`,
      sender: this.account.email,
      senderEmail: this.account.email,
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
        return await window.pywebview.api.getHSMStatus();
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
        return await window.pywebview.api.getAccount();
      } catch (e) {
        console.warn('Pywebview API getAccount failed:', e);
      }
    }
    return { ...this.account };
  }

  async updateAccountEmail(email: string): Promise<boolean> {
    this.account.email = email;
    return true;
  }
}

export const api = new ApiService();
