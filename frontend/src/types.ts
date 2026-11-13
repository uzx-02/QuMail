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

export interface HSMStatus {
  isHardwareActive: boolean;
  activePort: string;
  mode: 'AUTO' | 'SERIAL' | 'ETSI_QKD' | 'SOFTWARE_ONLY';
  rateBps: number;
  continuousPassed: boolean;
  shannonEntropy?: number;
  bytesIngested?: number;
  bytesInBuffer?: number;
  healthStatus?: string;
  etsiKmeConnected?: boolean;
  provenanceSummary?: string;
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
  cooldownSeconds?: number;
  vaultState?: string;
  sessionState?: string;
  connectionStatus?: 'ONLINE' | 'OFFLINE' | 'OAUTH_EXPIRED';
  syncError?: string;
}

export type ThemeMode = 'light' | 'dark' | 'midnight';
export type AccentColor = 'blue' | 'indigo' | 'emerald' | 'cyan' | 'rose';
export type FontFamilyOption = 'sans' | 'geometric' | 'serif' | 'mono';
export type FontSizeOption = 'small' | 'medium' | 'large';
export type ListDensityOption = 'comfortable' | 'cozy' | 'compact';
export type LanguageOption = 'en' | 'hi' | 'mr';

export interface QuMailSettings {
  language?: LanguageOption;
  maxPageSize: 25 | 50 | 100;
  blockRemoteImages: boolean;
  maskEncryptedSnippets: boolean;
  defaultSecurityMode: 'pq' | 'weblink';
  visibleFolders: {
    starred: boolean;
    sent: boolean;
    drafts: boolean;
    outbox: boolean;
    trash: boolean;
  };
  defaultInboxFilter: 'all' | 'secure' | 'unread';
  hideEmptyFolders: boolean;
  defaultStartupFolder: 'inbox' | 'starred' | 'sent';
  showUnreadBadges: boolean;
  weblinkExpiryHours: 1 | 24 | 168 | 720;
  weblinkBurnAfterRead: boolean;
  weblinkRequireOtp: boolean;
  listDensity: ListDensityOption;
  theme: ThemeMode;
  syncWithSystem: boolean;
  accentColor: AccentColor;
  fontFamily: FontFamilyOption;
  fontSize: FontSizeOption;
  showSenderAvatars: boolean;

  // 1. Sync & Inbox Behavior
  autoSyncMinutes: 0 | 2 | 5 | 15;
  desktopNotifications: 'off' | 'sender_only' | 'full';
  markAsReadDelay: 'immediate' | '3s' | 'manual';

  // 2. Default Encryption & Compose Safeguards
  weblinkDefaultExpiry: '24h' | '7d' | '30d';
  undoSendSeconds: 0 | 5 | 10 | 30;
  confirmBeforeSend: boolean;
  signatureEnabled: boolean;
  signatureText: string;

  // 3. Privacy & Anti-Tracking
  cloakSubjectHeaders: boolean;
  confirmExternalLinks: boolean;

  // 4. Session & System
  idleLockMinutes: 0 | 5 | 15 | 60;

  // 5. Accessibility Settings
  fontScale: 'default' | 'large' | 'xlarge'; // 100% | 115% | 130%
  highContrast: boolean;                      // WCAG AAA border & text contrast boost
  dyslexicReadingFont: boolean;               // Wide-tracked, high-legibility reading & compose typography
  showIconLabels: boolean;                    // Displays explicit text labels beside toolbar icons
  reduceMotion: boolean;                      // Disables Framer Motion transitions & pulse animations
  enhancedFocusRings: boolean;                // Bold 2px high-visibility keyboard focus outlines
  singleKeyShortcuts: boolean;                // Enables/disables single-key shortcuts (J, K, S, U) for voice-dictation safety

  // 6. Offline Neural Translation (NLLB-200 INT8)
  enableOfflineTranslation: boolean;
  allowStandardMailTranslation: boolean;
}

export interface TranslationCompatibility {
  status: string;
  total_ram_gb: number;
  free_ram_gb: number;
  free_disk_gb: number;
  cpu_cores: number;
  verdict: 'optimal' | 'compatible' | 'limited';
  estimated_speed: string;
  warning?: string | null;
}

export interface TranslationStatus {
  isInstalled: boolean;
  isDownloading: boolean;
  progress: number;
  downloadedMB: number;
  totalMB: number;
  currentFile: string;
  error: string | null;
  modelSizeMB: number;
  isModelLoadedInRam?: boolean;
}

export interface TranslationLogEntry {
  messageId: string;
  subject: string;
  targetLang: string;
  sourceLang: string;
  timestamp: string;
  charCount: number;
}

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
