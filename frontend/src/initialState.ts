import { EmailMessage, HSMStatus, AccountSession, QuMailSettings } from './types';

export const INITIAL_ACCOUNT: AccountSession = {
  email: '',
  provider: 'QuMail Sovereign Post-Quantum Network',
  pqcAlgorithm: 'NIST FIPS 203 (ML-KEM-768) + NIST FIPS 204 (ML-DSA-65)',
  pqcIdentity: '',
  isUnlocked: false,
  hasSecurityPin: false,
};

export const INITIAL_HSM: HSMStatus = {
  isHardwareActive: false,
  activePort: '',
  mode: 'AUTO',
  rateBps: 0,
  continuousPassed: true,
};

// Pure live data — zero mock messages
export const INITIAL_MESSAGES: EmailMessage[] = [];

export const DEFAULT_SETTINGS: QuMailSettings = {
  language: 'en',
  maxPageSize: 50,
  blockRemoteImages: true,
  maskEncryptedSnippets: true,
  defaultSecurityMode: 'pq',
  visibleFolders: {
    starred: true,
    sent: true,
    drafts: true,
    outbox: true,
    trash: true,
  },
  defaultInboxFilter: 'all',
  hideEmptyFolders: false,
  defaultStartupFolder: 'inbox',
  showUnreadBadges: true,
  weblinkExpiryHours: 168,
  weblinkBurnAfterRead: false,
  weblinkRequireOtp: true,
  listDensity: 'comfortable',
  theme: 'light',
  syncWithSystem: false,
  accentColor: 'blue',
  fontFamily: 'sans',
  fontSize: 'medium',
  showSenderAvatars: true,
  autoSyncMinutes: 5,
  desktopNotifications: 'sender_only',
  markAsReadDelay: '3s',
  weblinkDefaultExpiry: '7d',
  undoSendSeconds: 5,
  confirmBeforeSend: false,
  signatureEnabled: true,
  signatureText: 'Sent with QuMail · Post-Quantum Protected (ML-KEM-768)',
  cloakSubjectHeaders: true,
  confirmExternalLinks: true,
  idleLockMinutes: 15,

  // Accessibility Defaults
  fontScale: 'default',
  highContrast: false,
  dyslexicReadingFont: false,
  showIconLabels: false,
  reduceMotion: typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches ? true : false,
  enhancedFocusRings: true,
  singleKeyShortcuts: true,

  // Offline Translation Default
  enableOfflineTranslation: false,
  allowStandardMailTranslation: false,
};
