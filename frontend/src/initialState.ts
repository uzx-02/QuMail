import { EmailMessage, HSMStatus, AccountSession, QuMailSettings } from './types';

export const INITIAL_ACCOUNT: AccountSession = {
  email: '',
  provider: 'QuMail Sovereign Post-Quantum Network',
  pqcAlgorithm: 'NIST FIPS 203 (ML-KEM-768) + NIST FIPS 204 (ML-DSA-65)',
  pqcIdentity: '',
  isUnlocked: false,
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
  maxPageSize: 50,
  blockRemoteImages: true,
  maskEncryptedSnippets: false,
  defaultSecurityMode: 'pq',
  visibleFolders: {
    starred: true,
    sent: true,
    drafts: true,
    outbox: true,
    trash: true,
  },
  defaultInboxFilter: 'all',
  weblinkExpiryHours: 24,
  weblinkBurnAfterRead: false,
  weblinkRequireOtp: true,
  listDensity: 'comfortable',
};
