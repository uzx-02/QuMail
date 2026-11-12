export type BadgeLevel = 'SECURE' | 'CAUTION' | 'ALERT' | 'NEUTRAL';

export interface SecurityIndicator {
  badgeLevel: BadgeLevel;
  headline: string;
  description: string;
  actionAdvice: string;
}

export interface Attachment {
  name: string;
  size: number;
  mediaType?: string;
  data?: string; // base64
}

export interface EmailMessage {
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
  folder: 'inbox' | 'starred' | 'sent' | 'drafts' | 'outbox' | 'trash';
  category: 'primary' | 'updates' | 'secure';
  hasAttachments: boolean;
  attachments?: Attachment[];
  securityMode?: 'pq' | 'weblink' | 'standard';
  requireEmailOtp?: boolean;
  passcode?: string;
  indicator?: SecurityIndicator;
}

export interface HSMStatus {
  isHardwareActive: boolean;
  activePort: string;
  mode: 'AUTO' | 'SERIAL' | 'ETSI_QKD' | 'SOFTWARE_ONLY';
  rateBps: number;
  continuousPassed: boolean;
}

export interface AccountSession {
  email: string;
  displayName?: string;
  provider: string;
  pqcAlgorithm: string;
  pqcIdentity: string;
  isUnlocked: boolean;
}
