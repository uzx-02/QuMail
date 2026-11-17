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
  data?: string; // base64 or raw string
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
  folder: 'inbox' | 'starred' | 'sent' | 'drafts' | 'outbox' | 'trash' | 'spam';
  category: 'primary' | 'updates' | 'secure';
  hasAttachments: boolean;
  attachments?: Attachment[];
  securityMode?: 'pq' | 'weblink' | 'standard';
  isQuMail?: boolean;
  securityTier?: 'pq_sealed' | 'weblink' | 'standard_tls';
  requireEmailOtp?: boolean;
  burnAfterRead?: boolean;
  expiresInHours?: number;
  passcode?: string;
  outboxError?: string;
  indicator?: SecurityIndicator;
  cloakSubjectHeaders?: boolean;
  threadId?: string;
  messageId?: string;
  inReplyTo?: string;
  references?: string;
  rawStandardBody?: string;
  rawStandardSubject?: string;
}

export interface AccountSession {
  email: string;
  displayName?: string;
  avatarUrl?: string;
  provider: string;
  pqcAlgorithm: string;
  pqcIdentity: string;
  isUnlocked: boolean;
  hasSecurityPin?: boolean;
  vaultState?: 'ACTIVE' | 'LOCKED' | 'NOT_INITIALIZED';
  connectionStatus?: 'ONLINE' | 'OFFLINE' | 'OAUTH_EXPIRED';
  syncError?: string;
}

export type ThemeMode = 'light' | 'dark' | 'midnight';
export type AccentColor = 'blue' | 'indigo' | 'emerald' | 'cyan' | 'rose';
export type FontSizeOption = 'small' | 'medium' | 'large';
export type ListDensityOption = 'comfortable' | 'cozy' | 'compact';
export type LanguageOption = 'en' | 'hi' | 'mr';

export interface QuMailSettings {
  // General & Language
  language: LanguageOption;
  autoSyncMinutes: number;
  markAsReadDelay: 'immediate' | '3s' | 'manual';
  defaultSecurityMode: 'pq' | 'weblink' | 'standard';
  undoSendSeconds: number;
  signatureEnabled: boolean;
  signatureText: string;
  cloakSubjectHeaders: boolean;
  blockRemoteImages: boolean;
  hideInboxPreviews: boolean;
  confirmBeforeSend: boolean;
  safeLinkProtection: boolean;

  // Appearance
  theme: ThemeMode;
  syncWithSystem: boolean;
  accentColor: AccentColor;
  fontSize: FontSizeOption;
  listDensity: ListDensityOption;
  showSenderAvatars: boolean;

  // Labels & Folders
  visibleFolders: {
    starred: boolean;
    sent: boolean;
    drafts: boolean;
    outbox: boolean;
    trash: boolean;
    spam: boolean;
  };
  smartHideEmptyFolders: boolean;
  defaultStartupFolder: string;
  defaultInboxFilter: 'all' | 'secure' | 'unread';
  showUnreadBadges: boolean;

  // Security & Vault
  autoLockVaultMinutes: number;
  useBiometrics: boolean;
  googleClientId?: string;
  kemAlgorithm: string;
  dsaAlgorithm: string;

  // Accessibility
  highContrast: boolean;
  dyslexicReadingFont: boolean;
  showIconLabels: boolean;
  reduceMotion: boolean;

  // Offline Translation
  enableOfflineTranslation: boolean;
  translationTargetLang: LanguageOption;
  autoTranslateIncoming: boolean;
}

export interface RecipientInfo {
  registered: boolean;
  deviceCount?: number;
  securityMode: 'pq' | 'weblink' | 'standard';
  publicCertBase64?: string;
  publicCertsBase64?: string[];
  warning?: string;
  message: string;
}

export interface OutboundMessage {
  recipients: string[];
  subject: string;
  body: string;
  attachments?: Attachment[];
  securityMode: 'pq' | 'weblink' | 'standard';
  cloakSubjectHeaders?: boolean;
  passcode?: string;
  requireEmailOtp?: boolean;
  burnAfterRead?: boolean;
  expiresInHours?: number;
}

export const DEFAULT_GOOGLE_CLIENT_ID = '953431543574-8ci0e8ebrubaapsfvdhr0b2t5hvhojl1.apps.googleusercontent.com';

export const DEFAULT_SETTINGS: QuMailSettings = {
  // General & Language
  language: 'en',
  autoSyncMinutes: 5,
  markAsReadDelay: 'immediate',
  defaultSecurityMode: 'pq',
  undoSendSeconds: 5,
  signatureEnabled: false,
  signatureText: 'Sent securely with QuMail (Post-Quantum Encrypted)',
  cloakSubjectHeaders: false,
  blockRemoteImages: true,
  hideInboxPreviews: false,
  confirmBeforeSend: false,
  safeLinkProtection: true,

  // Appearance
  theme: 'midnight',
  syncWithSystem: false,
  accentColor: 'emerald',
  fontSize: 'medium',
  listDensity: 'comfortable',
  showSenderAvatars: true,

  // Labels & Folders
  visibleFolders: {
    starred: true,
    sent: true,
    drafts: true,
    outbox: true,
    trash: true,
    spam: true,
  },
  smartHideEmptyFolders: false,
  defaultStartupFolder: 'inbox',
  defaultInboxFilter: 'all',
  showUnreadBadges: true,

  // Security & Vault
  autoLockVaultMinutes: 15,
  useBiometrics: true,
  googleClientId: DEFAULT_GOOGLE_CLIENT_ID,
  kemAlgorithm: 'ML-KEM-768 (FIPS 203)',
  dsaAlgorithm: 'ML-DSA-65 (FIPS 204)',

  // Accessibility
  highContrast: false,
  dyslexicReadingFont: false,
  showIconLabels: true,
  reduceMotion: false,

  // Offline Translation
  enableOfflineTranslation: true,
  translationTargetLang: 'en',
  autoTranslateIncoming: false,
};

export interface SearchFilters {
  securityMode: 'all' | 'pq' | 'weblink' | 'standard';
  from: string;
  to: string;
  subjectKeywords: string;
  hasAttachment: boolean;
  unreadOnly: boolean;
  starredOnly: boolean;
  cloakedOnly: boolean;
  dateRange: 'all' | '24h' | '7d' | '30d';
}

export const DEFAULT_SEARCH_FILTERS: SearchFilters = {
  securityMode: 'all',
  from: '',
  to: '',
  subjectKeywords: '',
  hasAttachment: false,
  unreadOnly: false,
  starredOnly: false,
  cloakedOnly: false,
  dateRange: 'all',
};

export function countActiveFilters(f: SearchFilters): number {
  let count = 0;
  if (f.securityMode !== 'all') count++;
  if (f.from.trim()) count++;
  if (f.to.trim()) count++;
  if (f.subjectKeywords.trim()) count++;
  if (f.hasAttachment) count++;
  if (f.unreadOnly) count++;
  if (f.starredOnly) count++;
  if (f.cloakedOnly) count++;
  if (f.dateRange !== 'all') count++;
  return count;
}

export const INITIAL_ACCOUNT: AccountSession = {
  email: '',
  displayName: '',
  provider: 'Gmail (OAuth 2.0 PKCE)',
  pqcAlgorithm: 'ML-KEM-768 / ML-DSA-65 (OpenPGP v6)',
  pqcIdentity: '',
  isUnlocked: false,
  hasSecurityPin: false,
  vaultState: 'NOT_INITIALIZED',
  connectionStatus: 'OFFLINE',
};
