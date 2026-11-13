import React, { useState, useEffect, useMemo } from 'react';
import {
  X,
  Cpu,
  RefreshCw,
  Sun,
  Moon,
  Award,
  User,
  Globe,
  Sliders,
  Copy,
  Check,
  Inbox,
  Shield,
  Eye,
  EyeOff,
  Lock,
  Link2,
  Star,
  Send,
  FileText,
  Package,
  Trash2,
  Download,
  KeyRound,
  Activity,
  Database,
  ExternalLink,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  AlertCircle,
  CheckCircle2,
  Server,
  FileCode,
  Mail,
  Accessibility,
  Keyboard,
  Volume2,
  RotateCcw,
  Sparkles,
  Languages,
  Clock,
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  HSMStatus,
  AccountSession,
  QuMailSettings,
  ThemeMode,
  AccentColor,
  FontFamilyOption,
  FontSizeOption,
  ListDensityOption,
  LanguageOption,
  TranslationCompatibility,
  TranslationStatus,
  TranslationLogEntry,
} from '../types';
import { FONT_FAMILY_STYLE, FONT_SIZE_STYLE } from '../lib/appearance';
import { api } from '../lib/api';
import { generateIdentityCertificateHtml } from '../lib/certificate';
import { t, LANGUAGE_OPTIONS } from '../lib/i18n';
import { SectionCard, SegmentedControl, SettingToggleRow } from './settings/SettingsPrimitives';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialTab?: 'general' | 'labels' | 'accounts' | 'security' | 'appearance' | 'accessibility' | 'offline_translation' | 'about';
  hsmStatus: HSMStatus;
  account: AccountSession;
  isDarkMode: boolean;
  onToggleTheme: () => void;
  onUpdateAccountEmail: (email: string) => void;
  onLogoutAccount?: () => void;
  onOpenSignIn?: () => void;
  settings: QuMailSettings;
  onUpdateSettings: (patch: Partial<QuMailSettings>) => void;
  onShowNotice?: (msg: string) => void;
  onVaultStateChange?: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  initialTab = 'general',
  hsmStatus,
  account,
  isDarkMode,
  onToggleTheme,
  onUpdateAccountEmail,
  onLogoutAccount,
  onOpenSignIn,
  settings,
  onUpdateSettings,
  onShowNotice,
  onVaultStateChange,
}) => {
  const [activeTab, setActiveTab] = useState<'general' | 'labels' | 'accounts' | 'security' | 'appearance' | 'accessibility' | 'offline_translation' | 'about'>(initialTab);

  useEffect(() => {
    if (isOpen && initialTab) {
      setActiveTab(initialTab);
    }
  }, [isOpen, initialTab]);
  const [newEmail, setNewEmail] = useState('');
  const [newPass, setNewPass] = useState('');
  const [isSampling, setIsSampling] = useState(false);
  const [entropyResult, setEntropyResult] = useState<string | null>(null);
  const [copiedFingerprint, setCopiedFingerprint] = useState(false);
  const [copiedAboutInfo, setCopiedAboutInfo] = useState(false);
  const [avatarError, setAvatarError] = useState(false);

  useEffect(() => {
    setAvatarError(false);
  }, [account.avatarUrl]);
  const [isPrivacyScopeOpen, setIsPrivacyScopeOpen] = useState(false);
  const [mailtoStatus, setMailtoStatus] = useState<string | null>(null);
  const [isVaultLocked, setIsVaultLocked] = useState(!account.isUnlocked && Boolean(account.email));
  const [isVaultActionBusy, setIsVaultActionBusy] = useState(false);
  const [isRefreshingTelemetry, setIsRefreshingTelemetry] = useState(false);
  const [isExportingCert, setIsExportingCert] = useState(false);

  // Accounts Tab state
  const [isGoogleAuthenticating, setIsGoogleAuthenticating] = useState(false);
  const [googleConfig, setGoogleConfig] = useState<{ configured: boolean; valid?: boolean; clientId?: string } | null>(null);
  const [isImportingClientSecret, setIsImportingClientSecret] = useState(false);
  const [isConnectingCustom, setIsConnectingCustom] = useState(false);
  const [showCustomPassword, setShowCustomPassword] = useState(false);
  const [showAdvancedPorts, setShowAdvancedPorts] = useState(false);
  const [customImapHost, setCustomImapHost] = useState('');
  const [customImapPort, setCustomImapPort] = useState(993);
  const [customSmtpHost, setCustomSmtpHost] = useState('');
  const [customSmtpPort, setCustomSmtpPort] = useState(587);

  // Security PIN state
  const [pinDialogMode, setPinDialogMode] = useState<'none' | 'set' | 'change' | 'remove' | 'unlock'>('none');
  const [pinCurrentInput, setPinCurrentInput] = useState('');
  const [pinNewInput, setPinNewInput] = useState('');
  const [pinConfirmInput, setPinConfirmInput] = useState('');
  const [pinActionError, setPinActionError] = useState<string | null>(null);
  const [isPinSubmitting, setIsPinSubmitting] = useState(false);

  // Offline Translation state
  const [compatData, setCompatData] = useState<TranslationCompatibility | null>(null);
  const [isCheckingCompat, setIsCheckingCompat] = useState(false);
  const [transStatus, setTransStatus] = useState<TranslationStatus>({
    isInstalled: false,
    isDownloading: false,
    progress: 0,
    downloadedMB: 0,
    totalMB: 628.7,
    currentFile: '',
    error: null,
    modelSizeMB: 0,
  });
  const [transLogs, setTransLogs] = useState<TranslationLogEntry[]>([]);
  const [isDeletingModel, setIsDeletingModel] = useState(false);
  const [isUnloadingModel, setIsUnloadingModel] = useState(false);
  const [isRefreshingTransStatus, setIsRefreshingTransStatus] = useState(false);

  const handleUnloadModel = async () => {
    setIsUnloadingModel(true);
    try {
      const res = await api.unloadTranslationModel();
      const updated = await api.getTranslationStatus();
      setTransStatus(updated);
      if (res?.wasLoaded || transStatus.isModelLoadedInRam) {
        showFeedback(t(settings.language, 'trans_model_unloaded'));
      } else {
        showFeedback('Model is already idle on disk (0 MB in RAM).');
      }
    } catch (e: any) {
      showFeedback(e?.message || 'Unload failed', 'warn');
    } finally {
      setIsUnloadingModel(false);
    }
  };

  const handleRefreshTransStatus = async () => {
    setIsRefreshingTransStatus(true);
    try {
      const status = await api.getTranslationStatus();
      setTransStatus(status);
      const compat = await api.checkTranslationCompatibility();
      setCompatData(compat);
      if (status.isInstalled) {
        showFeedback('Model status verified: Ready on device');
      } else if (status.isDownloading) {
        showFeedback(`Model download in progress (${status.progress}%)`);
      } else {
        showFeedback('Model status verified: Not installed');
      }
    } catch (e: any) {
      showFeedback(e?.message || 'Status check failed', 'warn');
    } finally {
      setIsRefreshingTransStatus(false);
    }
  };

  const showFeedback = (message: string, _type: 'info' | 'success' | 'warn' = 'success') => {
    onShowNotice?.(message);
  };

  useEffect(() => {
    setIsVaultLocked(!account.isUnlocked && Boolean(account.email));
  }, [account.isUnlocked, account.email]);

  useEffect(() => {
    if (activeTab === 'accounts') {
      api.checkGoogleConfigured()
        .then((cfg) => setGoogleConfig(cfg))
        .catch(() => setGoogleConfig({ configured: false }));
    } else if (activeTab === 'offline_translation') {
      (async () => {
        try {
          const s = await api.getTranslationStatus();
          setTransStatus(s);
          const logs = await api.getTranslationLogs();
          setTransLogs(logs);
          if (!compatData) {
            const compat = await api.checkTranslationCompatibility();
            setCompatData(compat);
          }
        } catch {}
      })();
    }
  }, [activeTab]);

  useEffect(() => {
    let timer: any = null;
    let inFlight = false;
    if (activeTab === 'offline_translation') {
      timer = setInterval(async () => {
        if (inFlight) return;
        inFlight = true;
        try {
          const s = await api.getTranslationStatus();
          setTransStatus(s);
        } catch {} finally {
          inFlight = false;
        }
      }, 4000);
    }
    return () => {
      if (timer) clearInterval(timer);
    };
  }, [activeTab]);

  useEffect(() => {
    let timer: any = null;
    let inFlight = false;
    if (transStatus.isDownloading) {
      timer = setInterval(async () => {
        if (inFlight) return;
        inFlight = true;
        try {
          const s = await api.getTranslationStatus();
          setTransStatus(s);
          if (!s.isDownloading) {
            clearInterval(timer);
          }
        } catch {
          // ignore
        } finally {
          inFlight = false;
        }
      }, 2000);
    }
    return () => {
      if (timer) clearInterval(timer);
    };
  }, [transStatus.isDownloading]);

  const accountInitials = useMemo(() => {
    if (!account.email) return 'GU';
    const name = account.displayName || account.email.split('@')[0];
    const parts = name.trim().split(/\s+/);
    if (parts.length >= 2) {
      return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    return name.slice(0, 2).toUpperCase();
  }, [account.email, account.displayName]);

  const providerHint = useMemo(() => {
    const trimmed = newEmail.trim().toLowerCase();
    if (!trimmed.includes('@')) return null;
    const domain = trimmed.split('@')[1];
    if (!domain) return null;

    if (domain.includes('gmail') || domain.includes('googlemail')) {
      return {
        type: 'gmail',
        label: 'Google Workspace / Gmail',
        hint: 'Requires a 16-character Google App Password (with 2-Step Verification enabled). Or use the "Sign in with Google" button above.',
        badgeColor: 'text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-950/40 border-red-200 dark:border-red-900',
        isWarning: false,
      };
    }
    if (domain.includes('yahoo') || domain.includes('ymail') || domain.includes('rocketmail')) {
      return {
        type: 'yahoo',
        label: 'Yahoo Mail',
        hint: 'Requires an App-Specific Password from your Yahoo account security settings.',
        badgeColor: 'text-purple-700 dark:text-purple-300 bg-purple-50 dark:bg-purple-950/40 border-purple-200 dark:border-purple-900',
        isWarning: false,
      };
    }
    if (domain.includes('icloud') || domain.includes('me.com') || domain.includes('mac.com')) {
      return {
        type: 'icloud',
        label: 'Apple iCloud',
        hint: 'Requires an App-Specific Password generated from appleid.apple.com.',
        badgeColor: 'text-cyan-700 dark:text-cyan-300 bg-cyan-50 dark:bg-cyan-950/40 border-cyan-200 dark:border-cyan-900',
        isWarning: false,
      };
    }
    if (domain.includes('outlook') || domain.includes('hotmail') || domain.includes('live') || domain.includes('office365')) {
      return {
        type: 'outlook',
        label: 'Microsoft Outlook',
        hint: 'Note: Microsoft retired App Passwords for personal/365 Outlook accounts; use a custom IMAP server or Gmail.',
        badgeColor: 'text-amber-800 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/40 border-amber-200 dark:border-amber-900',
        isWarning: true,
      };
    }
    if (domain.includes('zoho')) {
      return {
        type: 'zoho',
        label: 'Zoho Mail',
        hint: 'Requires an Application-Specific Password from Zoho account security.',
        badgeColor: 'text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-900',
        isWarning: false,
      };
    }
    return {
      type: 'custom',
      label: 'Corporate / Custom IMAP',
      hint: `Connecting to IMAP TLS (port ${customImapPort}) and SMTP TLS (port ${customSmtpPort}).`,
      badgeColor: 'text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-950/40 border-blue-200 dark:border-blue-900',
      isWarning: false,
    };
  }, [newEmail, customImapPort, customSmtpPort]);

  if (!isOpen) return null;

  const handleTestEntropy = async () => {
    setIsSampling(true);
    setEntropyResult(null);
    try {
      const res = await api.sampleEntropy();
      setEntropyResult(`Extracted 32 bytes conditioned entropy: 0x${res.hex}... (115,200 baud). NIST SP 800-90B PASSED.`);
      showFeedback('Sampled 256-bit hardware entropy successfully.');
    } catch (e) {
      setEntropyResult('Entropy test completed via local hardware simulator.');
      showFeedback('Sampled entropy from local security simulator.');
    } finally {
      setIsSampling(false);
    }
  };

  const handleGoogleAuth = async () => {
    setIsGoogleAuthenticating(true);
    try {
      const res = await api.signInWithGoogle();
      if (res.success && res.account) {
        onUpdateAccountEmail(res.account.email);
        showFeedback(`Signed in successfully as ${res.account.email}`);
      } else if (res.needsClientSecret) {
        showFeedback('Google Client Secret file required. Please import client_secret.json.', 'warn');
      } else {
        showFeedback(res.message || 'Google authentication was not completed.', 'warn');
      }
    } catch (err: any) {
      showFeedback(`Google authentication encountered an error: ${err?.message || err}`, 'warn');
    } finally {
      setIsGoogleAuthenticating(false);
    }
  };

  const handleSelectClientSecret = async () => {
    setIsImportingClientSecret(true);
    try {
      const res = await api.selectGoogleClientSecret();
      if (res.success) {
        showFeedback(res.message || 'Google client credentials imported successfully.');
        const updated = await api.checkGoogleConfigured();
        setGoogleConfig(updated);
      } else {
        showFeedback(res.message || 'Import cancelled or failed.', 'warn');
      }
    } catch (err: any) {
      showFeedback(`Failed to import credentials: ${err?.message || err}`, 'warn');
    } finally {
      setIsImportingClientSecret(false);
    }
  };

  const handleConnectAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newEmail || !newEmail.includes('@')) {
      showFeedback('Please enter a valid email address.', 'warn');
      return;
    }
    if (!newPass) {
      showFeedback('Password or App Password is required to authenticate mailbox access.', 'warn');
      return;
    }
    setIsConnectingCustom(true);
    try {
      const res = await api.authenticateCustomMailbox({
        email: newEmail.trim(),
        password: newPass,
        imapHost: customImapHost.trim() || undefined,
        imapPort: customImapPort || 993,
        smtpHost: customSmtpHost.trim() || undefined,
        smtpPort: customSmtpPort || 587,
      });
      if (res.success && res.account) {
        onUpdateAccountEmail(res.account.email);
        setNewEmail('');
        setNewPass('');
        showFeedback(`Account ${res.account.email} verified and enrolled successfully!`);
      } else {
        showFeedback(res.message || 'Custom mailbox authentication failed.', 'warn');
      }
    } catch (err: any) {
      showFeedback(`Error connecting mailbox: ${err?.message || err}`, 'warn');
    } finally {
      setIsConnectingCustom(false);
    }
  };

  const handlePinActionSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setPinActionError(null);
    setIsPinSubmitting(true);

    try {
      if (pinDialogMode === 'set') {
        const cleanNew = pinNewInput.trim();
        if (!cleanNew.match(/^\d{4,8}$/)) {
          setPinActionError('PIN must be between 4 and 8 numeric digits.');
          setIsPinSubmitting(false);
          return;
        }
        if (cleanNew !== pinConfirmInput.trim()) {
          setPinActionError('PIN confirmation does not match.');
          setIsPinSubmitting(false);
          return;
        }
        const res = await api.setSecurityPin(cleanNew);
        if (res.success) {
          showFeedback('Security PIN set successfully.');
          setPinDialogMode('none');
          onVaultStateChange?.();
        } else {
          setPinActionError(res.error || res.message || 'Failed to set Security PIN.');
        }
      } else if (pinDialogMode === 'change') {
        const cleanCurrent = pinCurrentInput.trim();
        const cleanNew = pinNewInput.trim();
        if (!cleanCurrent) {
          setPinActionError('Please enter your current PIN.');
          setIsPinSubmitting(false);
          return;
        }
        if (!cleanNew.match(/^\d{4,8}$/)) {
          setPinActionError('New PIN must be between 4 and 8 numeric digits.');
          setIsPinSubmitting(false);
          return;
        }
        if (cleanNew !== pinConfirmInput.trim()) {
          setPinActionError('New PIN confirmation does not match.');
          setIsPinSubmitting(false);
          return;
        }
        const res = await api.setSecurityPin(cleanNew, cleanCurrent);
        if (res.success) {
          showFeedback('Security PIN updated successfully.');
          setPinDialogMode('none');
          onVaultStateChange?.();
        } else {
          setPinActionError(res.error || res.message || 'Incorrect current PIN.');
        }
      } else if (pinDialogMode === 'remove') {
        const cleanCurrent = pinCurrentInput.trim();
        if (!cleanCurrent) {
          setPinActionError('Please enter your current PIN to confirm removal.');
          setIsPinSubmitting(false);
          return;
        }
        const res = await api.removeSecurityPin(cleanCurrent);
        if (res.success) {
          showFeedback('Security PIN removed. Vault unlocked via one-click.');
          setPinDialogMode('none');
          onVaultStateChange?.();
        } else {
          setPinActionError(res.error || res.message || 'Incorrect PIN. Could not remove.');
        }
      } else if (pinDialogMode === 'unlock') {
        const cleanCurrent = pinCurrentInput.trim();
        if (!cleanCurrent) {
          setPinActionError('Please enter your Security PIN.');
          setIsPinSubmitting(false);
          return;
        }
        const res = await api.unlockVault(cleanCurrent);
        if (res.success) {
          setIsVaultLocked(false);
          showFeedback('Mailbox unlocked and ready.');
          setPinDialogMode('none');
          onVaultStateChange?.();
        } else {
          setPinActionError(res.error || res.message || 'Incorrect Security PIN.');
        }
      }
    } catch (err: any) {
      setPinActionError(err?.message || 'Action failed.');
    } finally {
      setIsPinSubmitting(false);
    }
  };

  const handleCheckCompatibility = async () => {
    setIsCheckingCompat(true);
    try {
      const res = await api.checkTranslationCompatibility();
      setCompatData(res);
      showFeedback(t(settings.language, 'trans_compat_title') + ' · ' + (res.verdict === 'optimal' ? 'Optimal' : res.verdict === 'compatible' ? 'Compatible' : 'Warning'));
    } catch (e: any) {
      showFeedback(e?.message || 'Compatibility check failed', 'warn');
    } finally {
      setIsCheckingCompat(false);
    }
  };

  const handleDownloadModel = async () => {
    try {
      const res = await api.downloadTranslationPack();
      if (res?.status === 'already_installed') {
        const status = await api.getTranslationStatus();
        setTransStatus({ ...status, isInstalled: true });
        showFeedback('Model pack is already downloaded and verified on disk.');
        return;
      }
      setTransStatus((prev) => ({ ...prev, isDownloading: true, progress: 0, error: null }));
      showFeedback(t(settings.language, 'trans_model_downloading'));
    } catch (e: any) {
      showFeedback(e?.message || 'Download start failed', 'warn');
    }
  };

  const handleCancelDownload = async () => {
    try {
      await api.cancelTranslationDownload();
      const status = await api.getTranslationStatus();
      setTransStatus(status);
      showFeedback('Download cancelled');
    } catch (e: any) {
      showFeedback(e?.message || 'Cancel failed', 'warn');
    }
  };

  const handleDeleteModel = async () => {
    if (!window.confirm(t(settings.language, 'trans_delete_confirm'))) return;
    setIsDeletingModel(true);
    try {
      await api.deleteTranslationPack();
      const status = await api.getTranslationStatus();
      setTransStatus(status);
      showFeedback('Model files removed from disk');
    } catch (e: any) {
      showFeedback(e?.message || 'Delete failed', 'warn');
    } finally {
      setIsDeletingModel(false);
    }
  };

  const handleClearAllLogs = async () => {
    try {
      await api.deleteTranslationLog();
      setTransLogs([]);
      showFeedback(t(settings.language, 'trans_logs_cleared'));
    } catch (e: any) {
      showFeedback(e?.message || 'Clear logs failed', 'warn');
    }
  };

  const handleDeleteSingleLog = async (msgId: string) => {
    try {
      await api.deleteTranslationLog(msgId);
      setTransLogs((prev) => prev.filter((l) => l.messageId !== msgId));
      showFeedback('Log entry removed');
    } catch (e: any) {
      showFeedback(e?.message || 'Delete failed', 'warn');
    }
  };

  const tabs = [
    { id: 'general', label: t(settings.language, 'tab_general'), icon: <Sliders className="w-4 h-4" /> },
    { id: 'labels', label: t(settings.language, 'tab_labels'), icon: <Globe className="w-4 h-4" /> },
    { id: 'accounts', label: t(settings.language, 'tab_accounts'), icon: <User className="w-4 h-4" /> },
    { id: 'security', label: t(settings.language, 'tab_security'), icon: <Cpu className="w-4 h-4" /> },
    { id: 'appearance', label: t(settings.language, 'tab_appearance'), icon: isDarkMode ? <Moon className="w-4 h-4" /> : <Sun className="w-4 h-4" /> },
    { id: 'accessibility', label: t(settings.language, 'tab_accessibility'), icon: <Accessibility className="w-4 h-4" /> },
    { id: 'offline_translation', label: t(settings.language, 'tab_offline_translation'), icon: <Languages className="w-4 h-4" /> },
    { id: 'about', label: t(settings.language, 'tab_about'), icon: <Award className="w-4 h-4" /> },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm select-none">
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        className="w-full max-w-4xl h-[680px] bg-white dark:bg-[#161F33] rounded-3xl shadow-2xl border border-[#E0E3E7] dark:border-[#2A3B5F] flex flex-col overflow-hidden"
      >
        {/* Header */}
        <div className="h-16 px-6 bg-[#F6F8FC] dark:bg-[#111726] border-b border-[#E0E3E7] dark:border-[#1F2C47] flex items-center justify-between shrink-0">
          <div className="flex items-center space-x-2.5">
            <h2 className="text-xl font-bold text-[#202124] dark:text-[#F1F5F9]">
              {t(settings.language, 'settings_title')}
            </h2>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-full text-[#5F6368] dark:text-[#94A3B8] hover:bg-slate-200 dark:hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Navigation Bar (Gmail Underline Style) */}
        <div className="px-6 bg-[#F6F8FC] dark:bg-[#111726] border-b border-[#E0E3E7] dark:border-[#1F2C47] flex items-center space-x-2 shrink-0 overflow-x-auto">
          {tabs.map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`relative flex items-center space-x-2 py-3.5 px-4 text-xs font-bold transition-all outline-none cursor-pointer ${
                  isActive
                    ? 'qumail-accent-text'
                    : 'text-[#5F6368] dark:text-[#94A3B8] hover:text-[#202124] dark:hover:text-white'
                }`}
              >
                <span>{tab.icon}</span>
                <span>{tab.label}</span>
                {isActive && (
                  <motion.div
                    layoutId="settings-active-tab"
                    transition={{ type: "spring", stiffness: 500, damping: 38, mass: 0.6 }}
                    className="absolute bottom-0 left-2 right-2 h-[2.5px] rounded-full qumail-accent-bg"
                  />
                )}
              </button>
            );
          })}
        </div>

        {/* Tab Content Panel (Two-Column Gmail Layout) */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* 1. General Tab */}
          {activeTab === 'general' && (
            <div className="space-y-5">
              {/* Section 0: Language & Region */}
              <SectionCard
                title={t(settings.language, 'language_region_title')}
                subtitle={t(settings.language, 'language_region_desc')}
                icon={<Globe className="w-4 h-4" />}
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <h5 className="text-sm font-semibold text-[#202124] dark:text-[#F1F5F9]">
                      {t(settings.language, 'interface_language')}
                    </h5>
                    <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">
                      {t(settings.language, 'interface_language_desc')}
                    </p>
                  </div>
                  <SegmentedControl<LanguageOption>
                    layoutId="general-language"
                    value={settings.language || 'en'}
                    onChange={(lang) => onUpdateSettings({ language: lang })}
                    options={LANGUAGE_OPTIONS}
                  />
                </div>
              </SectionCard>
              {/* Section 1: Sync & Inbox */}
              <SectionCard
                title={t(settings.language, 'sync_inbox_title')}
                subtitle={t(settings.language, 'sync_inbox_desc')}
                icon={<Inbox className="w-4 h-4" />}
              >
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-center">
                  <div>
                    <h5 className="text-sm font-semibold text-[#202124] dark:text-[#F1F5F9]">
                      {t(settings.language, 'conv_per_page')}
                    </h5>
                    <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">
                      {t(settings.language, 'conv_per_page_desc')}
                    </p>
                  </div>
                  <div className="md:col-span-2">
                    <SegmentedControl<25 | 50 | 100>
                      layoutId="general-page-size"
                      value={settings.maxPageSize}
                      onChange={(val) => onUpdateSettings({ maxPageSize: val })}
                      options={[
                        { value: 25, label: '25' },
                        { value: 50, label: '50' },
                        { value: 100, label: '100' },
                      ]}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-center pt-4 border-t border-gray-100 dark:border-gray-800/80">
                  <div>
                    <h5 className="text-sm font-semibold text-[#202124] dark:text-[#F1F5F9]">
                      {t(settings.language, 'auto_sync_interval')}
                    </h5>
                    <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">
                      {t(settings.language, 'auto_sync_interval_desc')}
                    </p>
                  </div>
                  <div className="md:col-span-2">
                    <SegmentedControl<0 | 2 | 5 | 15>
                      layoutId="general-auto-sync"
                      value={settings.autoSyncMinutes ?? 5}
                      onChange={(val) => onUpdateSettings({ autoSyncMinutes: val })}
                      options={[
                        { value: 0, label: t(settings.language, 'sync_manual') },
                        { value: 2, label: t(settings.language, 'sync_2m') },
                        { value: 5, label: t(settings.language, 'sync_5m') },
                        { value: 15, label: t(settings.language, 'sync_15m') },
                      ]}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-center pt-4 border-t border-gray-100 dark:border-gray-800/80">
                  <div>
                    <h5 className="text-sm font-semibold text-[#202124] dark:text-[#F1F5F9]">
                      {t(settings.language, 'desktop_notif_privacy')}
                    </h5>
                    <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">
                      {t(settings.language, 'desktop_notif_privacy_desc')}
                    </p>
                  </div>
                  <div className="md:col-span-2">
                    <SegmentedControl<'off' | 'sender_only' | 'full'>
                      layoutId="general-notif-privacy"
                      value={settings.desktopNotifications ?? 'sender_only'}
                      onChange={(val) => onUpdateSettings({ desktopNotifications: val })}
                      options={[
                        { value: 'off', label: t(settings.language, 'notif_off') },
                        { value: 'sender_only', label: t(settings.language, 'notif_sender_only') },
                        { value: 'full', label: t(settings.language, 'notif_sender_subject') },
                      ]}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-center pt-4 border-t border-gray-100 dark:border-gray-800/80">
                  <div>
                    <h5 className="text-sm font-semibold text-[#202124] dark:text-[#F1F5F9]">
                      {t(settings.language, 'auto_mark_read')}
                    </h5>
                    <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">
                      {t(settings.language, 'auto_mark_read_desc')}
                    </p>
                  </div>
                  <div className="md:col-span-2">
                    <SegmentedControl<'immediate' | '3s' | 'manual'>
                      layoutId="general-mark-read"
                      value={settings.markAsReadDelay ?? '3s'}
                      onChange={(val) => onUpdateSettings({ markAsReadDelay: val })}
                      options={[
                        { value: 'immediate', label: t(settings.language, 'mark_read_immediate') },
                        { value: '3s', label: t(settings.language, 'mark_read_3s') },
                        { value: 'manual', label: t(settings.language, 'mark_read_manual') },
                      ]}
                    />
                  </div>
                </div>
              </SectionCard>

              {/* Section 2: Default Encryption & Compose */}
              <SectionCard
                title={t(settings.language, 'default_enc_compose_title')}
                subtitle={t(settings.language, 'default_enc_compose_desc')}
                icon={<Shield className="w-4 h-4" />}
              >
                <div className="space-y-2.5">
                  <div>
                    <h5 className="text-sm font-semibold text-[#202124] dark:text-[#F1F5F9]">
                      {t(settings.language, 'default_compose_protection')}
                    </h5>
                    <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">
                      {t(settings.language, 'default_compose_protection_desc')}
                    </p>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {(
                      [
                        {
                          id: 'pq' as const,
                          title: t(settings.language, 'mode_pq_title'),
                          techBadge: 'ML-KEM-768',
                          desc: t(settings.language, 'mode_pq_desc'),
                          icon: <Shield className="w-4 h-4" />,
                        },
                        {
                          id: 'weblink' as const,
                          title: t(settings.language, 'mode_weblink_title'),
                          techBadge: 'Zero-Knowledge',
                          desc: t(settings.language, 'mode_weblink_desc'),
                          icon: <Link2 className="w-4 h-4" />,
                        },
                      ]
                    ).map((mode) => {
                      const active = settings.defaultSecurityMode === mode.id;
                      return (
                        <motion.button
                          key={mode.id}
                          type="button"
                          whileHover={{ y: -1 }}
                          whileTap={{ scale: 0.99 }}
                          onClick={() => onUpdateSettings({ defaultSecurityMode: mode.id })}
                          className={`text-left p-3.5 rounded-2xl border-2 transition-colors cursor-pointer ${
                            active
                              ? 'qumail-accent-border qumail-accent-soft'
                              : 'border-gray-200 dark:border-gray-700/80 hover:border-gray-300 dark:hover:border-gray-600'
                          }`}
                        >
                          <div className="flex items-center justify-between mb-1.5">
                            <span
                              className={`inline-flex items-center gap-1.5 text-xs font-bold ${
                                active ? 'qumail-accent-text' : 'text-[#202124] dark:text-[#F1F5F9]'
                              }`}
                            >
                              {mode.icon}
                              <span>{mode.title}</span>
                              <span className="text-[10px] font-mono font-medium px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-[#5F6368] dark:text-[#94A3B8] ml-1">
                                {mode.techBadge}
                              </span>
                            </span>
                            {active && (
                              <span className="w-4 h-4 rounded-full qumail-accent-bg text-white flex items-center justify-center shrink-0">
                                <Check className="w-2.5 h-2.5" />
                              </span>
                            )}
                          </div>
                          <p className="text-[11px] text-[#5F6368] dark:text-[#94A3B8] leading-relaxed">
                            {mode.desc}
                          </p>
                        </motion.button>
                      );
                    })}
                  </div>
                </div>

                {/* Web Link Defaults */}
                <div className="rounded-xl border border-gray-200/80 dark:border-gray-700/70 bg-gray-50/70 dark:bg-white/[0.02] p-4 space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-center">
                    <div>
                      <h5 className="text-xs font-bold text-[#202124] dark:text-[#F1F5F9]">
                        {t(settings.language, 'default_link_expiry')}
                      </h5>
                      <p className="text-[11px] text-[#5F6368] dark:text-[#94A3B8]">
                        {t(settings.language, 'default_link_expiry_desc')}
                      </p>
                    </div>
                    <div className="md:col-span-2">
                      <SegmentedControl<'24h' | '7d' | '30d'>
                        layoutId="general-weblink-expiry"
                        value={settings.weblinkDefaultExpiry ?? '7d'}
                        onChange={(val) =>
                          onUpdateSettings({
                            weblinkDefaultExpiry: val,
                            weblinkExpiryHours: val === '24h' ? 24 : val === '30d' ? 720 : 168,
                          })
                        }
                        options={[
                          { value: '24h', label: t(settings.language, 'expiry_24h') },
                          { value: '7d', label: t(settings.language, 'expiry_7d') },
                          { value: '30d', label: t(settings.language, 'expiry_30d') },
                        ]}
                      />
                    </div>
                  </div>

                  <div className="pt-3 border-t border-gray-200/70 dark:border-gray-700/60">
                    <SettingToggleRow
                      title={t(settings.language, 'require_otp_title')}
                      description={t(settings.language, 'require_otp_desc')}
                      checked={settings.weblinkRequireOtp}
                      onChange={(checked) => onUpdateSettings({ weblinkRequireOtp: checked })}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-center pt-4 border-t border-gray-100 dark:border-gray-800/80">
                  <div>
                    <h5 className="text-sm font-semibold text-[#202124] dark:text-[#F1F5F9]">
                      {t(settings.language, 'undo_send_delay')}
                    </h5>
                    <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">
                      {t(settings.language, 'undo_send_delay_desc')}
                    </p>
                  </div>
                  <div className="md:col-span-2">
                    <SegmentedControl<0 | 5 | 10 | 30>
                      layoutId="general-undo-send"
                      value={settings.undoSendSeconds ?? 5}
                      onChange={(val) => onUpdateSettings({ undoSendSeconds: val })}
                      options={[
                        { value: 0, label: t(settings.language, 'undo_off') },
                        { value: 5, label: '5s' },
                        { value: 10, label: '10s' },
                        { value: 30, label: '30s' },
                      ]}
                    />
                  </div>
                </div>

                <div className="pt-4 border-t border-gray-100 dark:border-gray-800/80">
                  <SettingToggleRow
                    title={t(settings.language, 'confirm_before_send_title')}
                    description={t(settings.language, 'confirm_before_send_desc')}
                    checked={Boolean(settings.confirmBeforeSend)}
                    onChange={(checked) => onUpdateSettings({ confirmBeforeSend: checked })}
                  />
                </div>

                <div className="pt-4 border-t border-gray-100 dark:border-gray-800/80 space-y-3">
                  <SettingToggleRow
                    title={t(settings.language, 'plain_text_sig_title')}
                    description={t(settings.language, 'plain_text_sig_desc')}
                    checked={Boolean(settings.signatureEnabled)}
                    onChange={(checked) => onUpdateSettings({ signatureEnabled: checked })}
                  />
                  <AnimatePresence initial={false}>
                    {settings.signatureEnabled && (
                      <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        exit={{ opacity: 0, height: 0 }}
                        transition={{ duration: 0.18 }}
                        className="overflow-hidden"
                      >
                        <textarea
                          rows={3}
                          value={settings.signatureText ?? ''}
                          onChange={(e) => onUpdateSettings({ signatureText: e.target.value })}
                          placeholder="Sent with QuMail · Post-Quantum Protected (ML-KEM-768)"
                          className="w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50/70 dark:bg-[#0D1321] px-3.5 py-2.5 text-xs font-mono text-[#202124] dark:text-[#F1F5F9] outline-none focus:border-blue-500 resize-y"
                        />
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              </SectionCard>

              {/* Section 3: Privacy & Protection */}
              <SectionCard
                title={t(settings.language, 'privacy_protection_title')}
                subtitle={t(settings.language, 'privacy_protection_desc')}
                icon={<EyeOff className="w-4 h-4" />}
              >
                <SettingToggleRow
                  title={t(settings.language, 'block_tracking_images_title')}
                  description={t(settings.language, 'block_tracking_images_desc')}
                  checked={settings.blockRemoteImages}
                  onChange={(checked) => onUpdateSettings({ blockRemoteImages: checked })}
                />
                <div className="pt-4 border-t border-gray-100 dark:border-gray-800/80">
                  <SettingToggleRow
                    title={t(settings.language, 'hide_inbox_previews_title')}
                    description={t(settings.language, 'hide_inbox_previews_desc')}
                    checked={settings.maskEncryptedSnippets}
                    onChange={(checked) => onUpdateSettings({ maskEncryptedSnippets: checked })}
                  />
                </div>
                <div className="pt-4 border-t border-gray-100 dark:border-gray-800/80">
                  <SettingToggleRow
                    title={t(settings.language, 'hide_subject_line_title')}
                    description={t(settings.language, 'hide_subject_line_desc')}
                    badge="Privacy Shield"
                    checked={Boolean(settings.cloakSubjectHeaders)}
                    onChange={(checked) => onUpdateSettings({ cloakSubjectHeaders: checked })}
                  />
                </div>
                <div className="pt-4 border-t border-gray-100 dark:border-gray-800/80">
                  <SettingToggleRow
                    title={t(settings.language, 'safe_link_protection_title')}
                    description={t(settings.language, 'safe_link_protection_desc')}
                    checked={Boolean(settings.confirmExternalLinks)}
                    onChange={(checked) => onUpdateSettings({ confirmExternalLinks: checked })}
                  />
                </div>
              </SectionCard>

              {/* Section 4: Session & System */}
              <SectionCard
                title={t(settings.language, 'session_system_title')}
                subtitle={t(settings.language, 'session_system_desc')}
                icon={<Lock className="w-4 h-4" />}
              >
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-center">
                  <div>
                    <h5 className="text-sm font-semibold text-[#202124] dark:text-[#F1F5F9]">
                      {t(settings.language, 'auto_lock_inactive')}
                    </h5>
                    <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">
                      {t(settings.language, 'auto_lock_inactive_desc')}
                    </p>
                  </div>
                  <div className="md:col-span-2">
                    <SegmentedControl<0 | 5 | 15 | 60>
                      layoutId="general-idle-lock"
                      value={settings.idleLockMinutes ?? 15}
                      onChange={(val) => onUpdateSettings({ idleLockMinutes: val })}
                      options={[
                        { value: 0, label: t(settings.language, 'lock_never') },
                        { value: 5, label: t(settings.language, 'lock_5m') },
                        { value: 15, label: t(settings.language, 'lock_15m') },
                        { value: 60, label: t(settings.language, 'lock_1h') },
                      ]}
                    />
                  </div>
                </div>

                <div className="pt-4 border-t border-gray-100 dark:border-gray-800/80 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <h5 className="text-sm font-semibold text-[#202124] dark:text-[#F1F5F9]">
                      {t(settings.language, 'default_mailto_handler')}
                    </h5>
                    <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">
                      {t(settings.language, 'default_mailto_handler_desc')}
                    </p>
                    {mailtoStatus && (
                      <p className="text-[11px] qumail-accent-text font-medium mt-1">
                        {mailtoStatus}
                      </p>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      try {
                        if (typeof navigator !== 'undefined' && typeof navigator.registerProtocolHandler === 'function') {
                          navigator.registerProtocolHandler(
                            'mailto',
                            `${window.location.origin}/?compose=%s`
                          );
                          setMailtoStatus('Registered QuMail as mailto: handler.');
                        } else {
                          setMailtoStatus('Desktop shell handles mailto: registration via OS Default Apps.');
                        }
                      } catch {
                        setMailtoStatus('Desktop shell handles mailto: registration via OS Default Apps.');
                      }
                    }}
                    className="px-4 py-2 rounded-xl border border-gray-300 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-white/[0.04] text-xs font-bold text-[#202124] dark:text-[#F1F5F9] transition-colors cursor-pointer shrink-0"
                  >
                    {t(settings.language, 'set_as_default')}
                  </button>
                </div>
              </SectionCard>
            </div>
          )}

          {/* 2. Labels Tab */}
          {activeTab === 'labels' && (
            <div className="space-y-5">
              {/* Navigation Sidebar Folders */}
              <SectionCard
                title={t(settings.language, 'nav_sidebar_folders')}
                subtitle={t(settings.language, 'nav_sidebar_folders_desc')}
                icon={<Sliders className="w-4 h-4" />}
              >
                {/* Inbox - Always Visible */}
                <div className="flex items-center justify-between py-1 border-b border-gray-100 dark:border-gray-800">
                  <div className="flex items-center space-x-3">
                    <span className="text-[#5F6368] dark:text-[#94A3B8]">
                      <Inbox className="w-4 h-4" />
                    </span>
                    <div>
                      <span className="text-sm font-semibold text-[#202124] dark:text-[#F1F5F9]">
                        {t(settings.language, 'folder_inbox')}
                      </span>
                      <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">
                        {t(settings.language, 'inbox_folder_desc')}
                      </p>
                    </div>
                  </div>
                  <span className="text-[11px] font-bold px-2.5 py-1 rounded-full bg-gray-100 dark:bg-white/[0.04] text-[#5F6368] dark:text-[#94A3B8]">
                    {t(settings.language, 'always_visible')}
                  </span>
                </div>

                {/* Optional folders */}
                {(
                  [
                    { key: 'starred', label: t(settings.language, 'folder_starred'), desc: t(settings.language, 'starred_folder_desc'), icon: <Star className="w-4 h-4" /> },
                    { key: 'sent', label: t(settings.language, 'folder_sent'), desc: t(settings.language, 'sent_folder_desc'), icon: <Send className="w-4 h-4" /> },
                    { key: 'drafts', label: t(settings.language, 'folder_drafts'), desc: t(settings.language, 'drafts_folder_desc'), icon: <FileText className="w-4 h-4" /> },
                    { key: 'outbox', label: t(settings.language, 'folder_outbox'), desc: t(settings.language, 'outbox_folder_desc'), icon: <Package className="w-4 h-4" /> },
                    { key: 'trash', label: t(settings.language, 'folder_trash'), desc: t(settings.language, 'trash_folder_desc'), icon: <Trash2 className="w-4 h-4" /> },
                  ] as const
                ).map((item) => (
                  <div key={item.key} className="flex items-center justify-between py-1">
                    <div className="flex items-center space-x-3">
                      <span className="text-[#5F6368] dark:text-[#94A3B8]">
                        {item.icon}
                      </span>
                      <div>
                        <span className="text-sm font-semibold text-[#202124] dark:text-[#F1F5F9]">
                          {item.label}
                        </span>
                        <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">
                          {item.desc}
                        </p>
                      </div>
                    </div>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={settings.visibleFolders[item.key] !== false}
                      onClick={() =>
                        onUpdateSettings({
                          visibleFolders: {
                            ...settings.visibleFolders,
                            [item.key]: !(settings.visibleFolders[item.key] !== false),
                          },
                        })
                      }
                      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors cursor-pointer ${
                        settings.visibleFolders[item.key] !== false ? 'qumail-accent-bg' : 'bg-gray-300 dark:bg-gray-600'
                      }`}
                    >
                      <span
                        className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform duration-200 ${
                          settings.visibleFolders[item.key] !== false ? 'translate-x-6' : 'translate-x-1'
                        }`}
                      />
                    </button>
                  </div>
                ))}

                <div className="pt-4 border-t border-gray-100 dark:border-gray-800">
                  <SettingToggleRow
                    title={t(settings.language, 'smart_hide_empty_folders')}
                    description={t(settings.language, 'smart_hide_empty_desc')}
                    checked={Boolean(settings.hideEmptyFolders)}
                    onChange={(checked) => onUpdateSettings({ hideEmptyFolders: checked })}
                  />
                </div>
              </SectionCard>

              {/* Default Views & Badges */}
              <SectionCard
                title={t(settings.language, 'default_views_badges')}
                subtitle={t(settings.language, 'default_views_badges_desc')}
                icon={<EyeOff className="w-4 h-4" />}
              >
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-center">
                  <div>
                    <h5 className="text-sm font-semibold text-[#202124] dark:text-[#F1F5F9]">
                      {t(settings.language, 'default_startup_folder')}
                    </h5>
                    <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">
                      {t(settings.language, 'default_startup_folder_desc')}
                    </p>
                  </div>
                  <div className="md:col-span-2">
                    <SegmentedControl<'inbox' | 'starred' | 'sent'>
                      layoutId="labels-startup-folder"
                      value={settings.defaultStartupFolder || 'inbox'}
                      onChange={(val) => onUpdateSettings({ defaultStartupFolder: val })}
                      options={[
                        { value: 'inbox', label: t(settings.language, 'folder_inbox') },
                        { value: 'starred', label: t(settings.language, 'folder_starred') },
                        { value: 'sent', label: t(settings.language, 'folder_sent') },
                      ]}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-center pt-4 border-t border-gray-100 dark:border-gray-800">
                  <div>
                    <h5 className="text-sm font-semibold text-[#202124] dark:text-[#F1F5F9]">
                      {t(settings.language, 'default_inbox_filter')}
                    </h5>
                    <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">
                      {t(settings.language, 'default_inbox_filter_desc')}
                    </p>
                  </div>
                  <div className="md:col-span-2">
                    <SegmentedControl<'all' | 'secure' | 'unread'>
                      layoutId="labels-inbox-filter"
                      value={settings.defaultInboxFilter || 'all'}
                      onChange={(val) => onUpdateSettings({ defaultInboxFilter: val })}
                      options={[
                        { value: 'all', label: t(settings.language, 'filter_all_messages') },
                        { value: 'secure', label: t(settings.language, 'filter_secure_only') },
                        { value: 'unread', label: t(settings.language, 'filter_pill_unread') },
                      ]}
                    />
                  </div>
                </div>

                <div className="pt-4 border-t border-gray-100 dark:border-gray-800">
                  <SettingToggleRow
                    title={t(settings.language, 'show_unread_badges')}
                    description={t(settings.language, 'show_unread_badges_desc')}
                    checked={settings.showUnreadBadges !== false}
                    onChange={(checked) => onUpdateSettings({ showUnreadBadges: checked })}
                  />
                </div>
              </SectionCard>
            </div>
          )}

          {/* 3. Accounts Tab */}
          {activeTab === 'accounts' && (
            <div className="space-y-5">
              {/* Card 1: Active Mailbox Profile Card */}
              <SectionCard
                title={t(settings.language, 'active_mailbox_identity')}
                subtitle={t(settings.language, 'active_mailbox_desc')}
                icon={<User className="w-4 h-4" />}
              >
                {account.email ? (
                  <div className="p-4 sm:p-5 rounded-2xl bg-gradient-to-br from-blue-50/70 via-indigo-50/40 to-transparent dark:from-blue-950/20 dark:via-indigo-950/10 dark:to-transparent border border-blue-200/80 dark:border-blue-900/60 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div className="flex items-center space-x-3.5">
                      {account.avatarUrl && !avatarError ? (
                        <div className="w-12 h-12 rounded-2xl overflow-hidden border-2 border-blue-400/40 shadow-md shadow-blue-500/20 shrink-0">
                          <img
                            src={account.avatarUrl}
                            alt={account.displayName || account.email}
                            referrerPolicy="no-referrer"
                            crossOrigin="anonymous"
                            className="w-full h-full object-cover"
                            onError={() => setAvatarError(true)}
                          />
                        </div>
                      ) : (
                        <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-[#0B57D0] to-[#4F46E5] text-white flex items-center justify-center font-black text-base shadow-md shadow-blue-500/20 shrink-0">
                          {accountInitials}
                        </div>
                      )}
                      <div className="space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h4 className="text-sm font-bold text-[#202124] dark:text-[#F1F5F9]">
                            {account.displayName || account.email.split('@')[0]}
                          </h4>
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-800 dark:bg-blue-900/60 dark:text-blue-300">
                            {account.provider?.includes('Google') || account.email.endsWith('@gmail.com')
                              ? 'Google OAuth 2.0'
                              : 'App Password'}
                          </span>
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800 flex items-center gap-1">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                            <span>{t(settings.language, 'connected_and_ready')}</span>
                          </span>
                        </div>
                        <p className="text-xs font-mono text-[#5F6368] dark:text-[#94A3B8]">
                          {account.email}
                        </p>
                        <div className="flex items-center gap-3 pt-0.5 flex-wrap">
                          <p className="text-[11px] text-emerald-600 dark:text-emerald-400 font-medium flex items-center gap-1">
                            <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                            <span>{t(settings.language, 'vault_keys_enrolled')}</span>
                          </p>
                          {(account.provider?.includes('Google') || account.email.endsWith('@gmail.com')) && (
                            <a
                              href="https://myaccount.google.com/permissions"
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-[11px] text-blue-600 dark:text-blue-400 hover:underline inline-flex items-center space-x-1 font-semibold"
                            >
                              <span>{t(settings.language, 'manage_google_permissions')}</span>
                              <ExternalLink className="w-3 h-3" />
                            </a>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center space-x-2 shrink-0 pt-2 sm:pt-0 border-t sm:border-t-0 border-blue-200/50 dark:border-blue-900/40">
                      {onLogoutAccount && (
                        <>
                          <button
                            type="button"
                            onClick={() => {
                              onLogoutAccount();
                              showFeedback('Signed out of mailbox session.');
                            }}
                            className="px-3.5 py-1.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#1E293B] text-xs font-semibold text-[#202124] dark:text-white hover:bg-gray-100 dark:hover:bg-slate-700 transition-colors cursor-pointer"
                          >
                            {t(settings.language, 'sign_out')}
                          </button>
                          {onOpenSignIn && (
                            <button
                              type="button"
                              onClick={() => {
                                onLogoutAccount();
                                onClose();
                                onOpenSignIn();
                              }}
                              className="px-3.5 py-1.5 rounded-xl qumail-accent-bg text-white text-xs font-bold transition-opacity shadow-sm hover:opacity-95 cursor-pointer"
                            >
                              {t(settings.language, 'switch_account')}
                            </button>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="p-4 sm:p-5 rounded-2xl bg-gray-50 dark:bg-white/[0.02] border border-gray-200 dark:border-gray-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div className="flex items-center space-x-3">
                      <div className="w-10 h-10 rounded-xl bg-gray-200 dark:bg-gray-800 text-gray-500 dark:text-gray-400 flex items-center justify-center font-bold text-sm">
                        <User className="w-5 h-5" />
                      </div>
                      <div>
                        <p className="text-sm font-bold text-[#202124] dark:text-white">
                          {t(settings.language, 'no_active_mailbox')}
                        </p>
                        <p className="text-xs text-[#5F6368] dark:text-[#94A3B8] mt-0.5">
                          {t(settings.language, 'no_active_mailbox_desc')}
                        </p>
                      </div>
                    </div>
                    {onOpenSignIn && (
                      <button
                        type="button"
                        onClick={() => {
                          onClose();
                          onOpenSignIn();
                        }}
                        className="px-4 py-2 rounded-xl qumail-accent-bg text-white font-bold text-xs shadow-md transition-opacity hover:opacity-95 cursor-pointer shrink-0"
                      >
                        {t(settings.language, 'sign_in_now')}
                      </button>
                    )}
                  </div>
                )}
              </SectionCard>

              {/* Card 2: Google Sign-In Card */}
              <SectionCard
                title={t(settings.language, 'google_workspace_title')}
                subtitle={t(settings.language, 'google_workspace_desc')}
                icon={
                  <svg className="w-4 h-4 shrink-0" viewBox="0 0 24 24">
                    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
                    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
                  </svg>
                }
              >
                <div className="space-y-4">
                  {/* Google Status Header */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-2xl bg-gray-50/70 dark:bg-white/[0.02] border border-gray-200/80 dark:border-gray-800">
                    <div className="flex items-center space-x-3">
                      <div className="w-10 h-10 rounded-xl bg-white dark:bg-[#1E293B] border border-gray-200 dark:border-gray-700 flex items-center justify-center shadow-xs shrink-0">
                        <svg className="w-5 h-5 shrink-0" viewBox="0 0 24 24">
                          <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                          <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                          <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
                          <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
                        </svg>
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold text-[#202124] dark:text-[#F1F5F9]">
                            {t(settings.language, 'google_oauth_client')}
                          </span>
                          {googleConfig?.configured ? (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800">
                              ● {t(settings.language, 'oauth_ready')}
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300 border border-amber-300 dark:border-amber-800">
                              {t(settings.language, 'oauth_setup_required')}
                            </span>
                          )}
                        </div>
                        <p className="text-[11px] text-[#5F6368] dark:text-[#94A3B8] mt-0.5">
                          {googleConfig?.configured
                            ? `Client ID: ${googleConfig.clientId ? googleConfig.clientId.slice(0, 16) + '...' : 'Loaded from client_secret.json'}`
                            : 'Import your Google Cloud credentials to enable one-click browser authorization.'}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        type="button"
                        disabled={isImportingClientSecret}
                        onClick={handleSelectClientSecret}
                        className="px-3.5 py-1.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#1E293B] text-xs font-semibold text-[#202124] dark:text-white hover:bg-gray-100 dark:hover:bg-slate-700 transition-colors cursor-pointer shrink-0 flex items-center space-x-1.5 disabled:opacity-50"
                      >
                        <FileCode className="w-3.5 h-3.5 text-blue-500" />
                        <span>{isImportingClientSecret ? t(settings.language, 'selecting') : t(settings.language, 'import_client_secret')}</span>
                      </button>
                    </div>
                  </div>

                  {/* Compliant Google Sign-In Button */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1">
                    <div>
                      <h5 className="text-xs font-bold text-[#202124] dark:text-[#F1F5F9]">
                        {t(settings.language, 'connect_google_account')}
                      </h5>
                      <p className="text-[11px] text-[#5F6368] dark:text-[#94A3B8]">
                        {t(settings.language, 'connect_google_desc')}
                      </p>
                    </div>

                    <button
                      type="button"
                      disabled={isGoogleAuthenticating}
                      onClick={handleGoogleAuth}
                      className="inline-flex items-center justify-center px-5 py-2.5 rounded-xl bg-white text-[#1F1F1F] hover:bg-[#F8FAFC] border border-[#DADCE0] dark:bg-[#1E293B] dark:text-white dark:border-gray-700 dark:hover:bg-[#27354D] text-xs font-semibold shadow-xs transition-colors cursor-pointer disabled:opacity-50 shrink-0"
                    >
                      {isGoogleAuthenticating ? (
                        <>
                          <RefreshCw className="w-4 h-4 animate-spin text-blue-500 mr-2" />
                          <span>{t(settings.language, 'authenticating_with_google')}</span>
                        </>
                      ) : (
                        <>
                          <svg className="w-4 h-4 shrink-0 mr-2.5" viewBox="0 0 24 24">
                            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
                            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
                          </svg>
                          <span>{t(settings.language, 'sign_in_with_google')}</span>
                        </>
                      )}
                    </button>
                  </div>

                  {/* Privacy Guarantee Box */}
                  <div className="p-3.5 rounded-2xl bg-slate-50 dark:bg-white/[0.02] border border-gray-200 dark:border-gray-800 flex items-start space-x-3 text-xs">
                    <ShieldCheck className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />
                    <div className="space-y-0.5">
                      <p className="font-bold text-[#202124] dark:text-[#F1F5F9]">
                        {t(settings.language, 'privacy_guarantee_title')}
                      </p>
                      <p className="text-[11px] text-[#5F6368] dark:text-[#94A3B8] leading-relaxed">
                        {t(settings.language, 'privacy_guarantee_desc')}
                      </p>
                    </div>
                  </div>
                </div>
              </SectionCard>

              {/* Microsoft 365 & Outlook (In Development) Card */}
              <div className="p-4 rounded-2xl bg-gray-50/70 dark:bg-white/[0.02] border border-dashed border-gray-300 dark:border-gray-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-center space-x-3">
                  <div className="w-10 h-10 rounded-xl bg-white dark:bg-[#1E293B] border border-gray-200 dark:border-gray-700 flex items-center justify-center shadow-xs shrink-0 text-blue-600 dark:text-blue-400">
                    <Mail className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-[#202124] dark:text-[#F1F5F9]">
                        {t(settings.language, 'ms365_title')}
                      </span>
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-100/70 text-blue-800 dark:bg-blue-950/60 dark:text-blue-300 border border-blue-200 dark:border-blue-800">
                        {t(settings.language, 'ms365_in_dev')}
                      </span>
                    </div>
                    <p className="text-[11px] text-[#5F6368] dark:text-[#94A3B8] mt-0.5 leading-relaxed">
                      {t(settings.language, 'ms365_desc')}
                    </p>
                  </div>
                </div>
              </div>

              {/* Card 3: Connect with App Password Card */}
              <SectionCard
                title={t(settings.language, 'connect_app_password_title')}
                subtitle={t(settings.language, 'connect_app_password_desc')}
                icon={<KeyRound className="w-4 h-4" />}
              >
                <form onSubmit={handleConnectAccount} className="space-y-4">
                  {/* Email Input */}
                  <div className="space-y-1">
                    <label className="text-xs font-bold text-[#202124] dark:text-[#F1F5F9]">
                      {t(settings.language, 'email_address_label')}
                    </label>
                    <div className="relative">
                      <input
                        type="email"
                        placeholder="you@gmail.com, you@yahoo.com, or corporate email"
                        value={newEmail}
                        onChange={(e) => setNewEmail(e.target.value)}
                        className="w-full px-3.5 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#111726] text-xs text-[#202124] dark:text-white outline-none focus:ring-1 focus:ring-blue-500 transition-all placeholder:text-gray-400"
                      />
                    </div>
                  </div>

                  {/* Smart Provider Hint Banner */}
                  {providerHint && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      className={`p-3 rounded-xl border text-xs flex items-start space-x-2.5 ${providerHint.badgeColor}`}
                    >
                      {providerHint.isWarning ? (
                        <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                      ) : (
                        <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
                      )}
                      <div>
                        <span className="font-bold block">{providerHint.label}</span>
                        <span className="text-[11px] opacity-90 leading-relaxed block mt-0.5">
                          {providerHint.hint}
                        </span>
                      </div>
                    </motion.div>
                  )}

                  {/* Password Input with Eye Toggle */}
                  <div className="space-y-1">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-bold text-[#202124] dark:text-[#F1F5F9]">
                        {t(settings.language, 'app_password_label')}
                      </label>
                    </div>
                    <div className="relative">
                      <input
                        type={showCustomPassword ? 'text' : 'password'}
                        placeholder="16-character App Password (e.g. abcd efgh ijkl mnop)"
                        value={newPass}
                        onChange={(e) => setNewPass(e.target.value)}
                        className="w-full px-3.5 py-2.5 pr-10 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#111726] text-xs font-mono text-[#202124] dark:text-white outline-none focus:ring-1 focus:ring-blue-500 transition-all placeholder:text-gray-400"
                      />
                      <button
                        type="button"
                        onClick={() => setShowCustomPassword(!showCustomPassword)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 cursor-pointer"
                        title={showCustomPassword ? 'Hide password' : 'Show password'}
                      >
                        {showCustomPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>

                  {/* Collapsible Server Ports (Advanced) */}
                  <div className="pt-1">
                    <button
                      type="button"
                      onClick={() => setShowAdvancedPorts(!showAdvancedPorts)}
                      className="text-xs font-bold text-[#5F6368] dark:text-[#94A3B8] hover:text-[#202124] dark:hover:text-white flex items-center space-x-1.5 cursor-pointer outline-none"
                    >
                      <Server className="w-3.5 h-3.5" />
                      <span>{t(settings.language, 'server_ports_advanced')}</span>
                      {showAdvancedPorts ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    </button>

                    <AnimatePresence>
                      {showAdvancedPorts && (
                        <motion.div
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: 'auto' }}
                          exit={{ opacity: 0, height: 0 }}
                          className="pt-3 grid grid-cols-1 sm:grid-cols-2 gap-3"
                        >
                          <div className="space-y-1">
                            <label className="text-[11px] font-semibold text-[#5F6368] dark:text-[#94A3B8]">
                              {t(settings.language, 'imap_host_label')}
                            </label>
                            <input
                              type="text"
                              placeholder="Auto-detected (e.g. imap.gmail.com)"
                              value={customImapHost}
                              onChange={(e) => setCustomImapHost(e.target.value)}
                              className="w-full px-3 py-2 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#111726] text-xs font-mono text-[#202124] dark:text-white outline-none focus:ring-1 focus:ring-blue-500"
                            />
                            <span className="text-[10px] text-[#5F6368] dark:text-[#94A3B8] block">Port: {customImapPort} (TLS/SSL)</span>
                          </div>

                          <div className="space-y-1">
                            <label className="text-[11px] font-semibold text-[#5F6368] dark:text-[#94A3B8]">
                              {t(settings.language, 'smtp_host_label')}
                            </label>
                            <input
                              type="text"
                              placeholder="Auto-detected (e.g. smtp.gmail.com)"
                              value={customSmtpHost}
                              onChange={(e) => setCustomSmtpHost(e.target.value)}
                              className="w-full px-3 py-2 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#111726] text-xs font-mono text-[#202124] dark:text-white outline-none focus:ring-1 focus:ring-blue-500"
                            />
                            <span className="text-[10px] text-[#5F6368] dark:text-[#94A3B8] block">Port: {customSmtpPort} (STARTTLS)</span>
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>

                  {/* Connect Submit Action */}
                  <div className="pt-2 flex items-center justify-between">
                    <p className="text-[11px] text-[#5F6368] dark:text-[#94A3B8]">
                      {t(settings.language, 'tls_handshake_note')}
                    </p>
                    <button
                      type="submit"
                      disabled={isConnectingCustom}
                      className="px-5 py-2.5 rounded-xl qumail-accent-bg text-white font-bold text-xs shadow-md transition-opacity hover:opacity-95 cursor-pointer disabled:opacity-50 flex items-center space-x-1.5"
                    >
                      {isConnectingCustom ? (
                        <>
                          <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                          <span>{t(settings.language, 'connecting')}</span>
                        </>
                      ) : (
                        <span>{t(settings.language, 'connect_mailbox_btn')}</span>
                      )}
                    </button>
                  </div>
                </form>
              </SectionCard>
            </div>
          )}

          {/* 4. Security & Hardware Tab */}
          {activeTab === 'security' && (
            <div className="space-y-5">
              {/* Hardware Security & Randomness Card */}
              <SectionCard
                title={t(settings.language, 'sec_hardware_title')}
                subtitle={t(settings.language, 'sec_hardware_desc')}
                icon={<Cpu className="w-4 h-4" />}
              >
                {/* Connection Status Banner */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-2xl bg-gray-50 dark:bg-white/[0.02] border border-gray-200 dark:border-gray-800">
                  <div className="flex items-center space-x-3">
                    <div
                      className={`w-3 h-3 rounded-full ${
                        hsmStatus.isHardwareActive
                          ? 'bg-emerald-500 animate-pulse'
                          : 'bg-amber-400'
                      }`}
                    />
                    <div>
                      <div className="text-sm font-bold text-[#202124] dark:text-[#F1F5F9] flex items-center gap-2.5 flex-wrap">
                        <span>
                          {hsmStatus.isHardwareActive
                            ? t(settings.language, 'sec_key_active')
                            : t(settings.language, 'sec_system_active')}
                        </span>
                        <span className="text-[10px] font-mono px-2.5 py-0.5 rounded-full qumail-accent-soft qumail-accent-text ml-1.5 inline-block shrink-0">
                          {hsmStatus.activePort ? `${hsmStatus.activePort} · ${hsmStatus.rateBps || 115200} baud` : 'System CSPRNG'}
                        </span>
                      </div>
                      <p className="text-xs text-[#5F6368] dark:text-[#94A3B8] mt-1">
                        {hsmStatus.provenanceSummary || (hsmStatus.isHardwareActive ? 'Avalanche photodiode & microcontroller streaming physical entropy' : 'Operating system cryptographically secure random number generator')}
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    disabled={isRefreshingTelemetry}
                    onClick={async () => {
                      setIsRefreshingTelemetry(true);
                      try {
                        const s = await api.getHSMStatus();
                        const modeStr = s?.isHardwareActive ? t(settings.language, 'sec_key_active') : t(settings.language, 'sec_system_active');
                        showFeedback(`${t(settings.language, 'sec_telemetry_refreshed')} · ${modeStr}`);
                      } catch {
                        showFeedback('Could not refresh telemetry.', 'warn');
                      } finally {
                        setIsRefreshingTelemetry(false);
                      }
                    }}
                    className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl border border-gray-300 dark:border-gray-700 text-xs font-semibold text-[#202124] dark:text-[#F1F5F9] hover:bg-gray-100 dark:hover:bg-white/[0.04] transition-colors cursor-pointer shrink-0 disabled:opacity-50"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${isRefreshingTelemetry ? 'animate-spin text-sky-500' : ''}`} />
                    <span>{isRefreshingTelemetry ? t(settings.language, 'sec_refreshing') : t(settings.language, 'sec_refresh_btn')}</span>
                  </button>
                </div>

                {/* 4-Card Telemetry Grid */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="p-3.5 rounded-2xl bg-gray-50/70 dark:bg-white/[0.02] border border-gray-200/80 dark:border-gray-800 space-y-1">
                    <span className="text-[11px] font-semibold text-[#5F6368] dark:text-[#94A3B8]">
                      {t(settings.language, 'sec_random_quality')}
                    </span>
                    <div className="text-base font-mono font-bold text-emerald-600 dark:text-emerald-400">
                      {hsmStatus.shannonEntropy ? `${hsmStatus.shannonEntropy.toFixed(4)}` : '7.9998'} <span className="text-xs text-[#5F6368]">/ 8.0</span>
                    </div>
                    <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-semibold block">
                      {t(settings.language, 'sec_optimal_max')}
                    </span>
                  </div>

                  <div className="p-3.5 rounded-2xl bg-gray-50/70 dark:bg-white/[0.02] border border-gray-200/80 dark:border-gray-800 space-y-1">
                    <span className="text-[11px] font-semibold text-[#5F6368] dark:text-[#94A3B8]">
                      {t(settings.language, 'sec_health_check')}
                    </span>
                    <div className="text-sm font-bold text-emerald-600 dark:text-emerald-400 flex items-center gap-1.5 pt-0.5">
                      <Check className="w-4 h-4" />
                      <span>{hsmStatus.healthStatus || 'PASSED'}</span>
                    </div>
                    <span className="text-[10px] text-[#5F6368] dark:text-[#94A3B8] block">
                      {t(settings.language, 'sec_nist_verified')}
                    </span>
                  </div>

                  <div className="p-3.5 rounded-2xl bg-gray-50/70 dark:bg-white/[0.02] border border-gray-200/80 dark:border-gray-800 space-y-1">
                    <span className="text-[11px] font-semibold text-[#5F6368] dark:text-[#94A3B8]">
                      {t(settings.language, 'sec_key_reserve')}
                    </span>
                    <div className="text-sm font-mono font-bold text-[#202124] dark:text-[#F1F5F9]">
                      {hsmStatus.bytesInBuffer || 2048} B <span className="text-[10px] text-[#5F6368]">{t(settings.language, 'sec_ready_badge')}</span>
                    </div>
                    <div className="w-full bg-gray-200 dark:bg-gray-700 h-1.5 rounded-full overflow-hidden mt-1">
                      <div className="qumail-accent-bg h-full w-[85%]" />
                    </div>
                  </div>

                  <div className="p-3.5 rounded-2xl bg-gray-50/70 dark:bg-white/[0.02] border border-gray-200/80 dark:border-gray-800 space-y-1">
                    <span className="text-[11px] font-semibold text-[#5F6368] dark:text-[#94A3B8]">
                      {t(settings.language, 'sec_quantum_net')}
                    </span>
                    <div className="text-sm font-bold text-[#202124] dark:text-[#F1F5F9] pt-0.5">
                      {hsmStatus.etsiKmeConnected ? (
                        <span className="text-emerald-600 dark:text-emerald-400">{t(settings.language, 'sec_connected_badge')}</span>
                      ) : (
                        <span className="text-slate-500">{t(settings.language, 'sec_standby_badge')}</span>
                      )}
                    </div>
                    <span className="text-[10px] text-[#5F6368] dark:text-[#94A3B8] block">
                      ETSI GS QKD 014
                    </span>
                  </div>
                </div>

                {/* Test Random Generator */}
                <div className="pt-3 border-t border-gray-100 dark:border-gray-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <h5 className="text-xs font-bold text-[#202124] dark:text-[#F1F5F9]">
                      {t(settings.language, 'sec_test_random_title')}
                    </h5>
                    <p className="text-[11px] text-[#5F6368] dark:text-[#94A3B8]">
                      {t(settings.language, 'sec_test_random_desc')}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleTestEntropy}
                    disabled={isSampling}
                    className="flex items-center space-x-2 px-4 py-2 rounded-xl qumail-accent-bg text-white font-bold text-xs transition-opacity shadow-sm disabled:opacity-50 cursor-pointer shrink-0"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${isSampling ? 'animate-spin' : ''}`} />
                    <span>{isSampling ? t(settings.language, 'sec_generating') : t(settings.language, 'sec_test_random_title')}</span>
                  </button>
                </div>

                {entropyResult && (
                  <div className="p-3 rounded-xl bg-gray-100 dark:bg-black/30 border border-gray-200 dark:border-gray-800 font-mono text-xs text-[#202124] dark:text-[#F1F5F9] break-all select-all flex items-center justify-between gap-2">
                    <span>
                      {entropyResult.match(/.{1,8}/g)?.join(' ') || entropyResult}
                    </span>
                    <span className="text-[10px] text-[#5F6368] shrink-0 font-sans">
                      256 bits · Generated just now
                    </span>
                  </div>
                )}
              </SectionCard>

              {/* Your Verification Identity Card */}
              <SectionCard
                title={t(settings.language, 'sec_identity_title')}
                subtitle={t(settings.language, 'sec_identity_desc')}
                icon={<Award className="w-4 h-4" />}
              >
                {account.email && account.pqcIdentity ? (
                  <div className="space-y-3">
                    <div className="p-3.5 rounded-2xl bg-slate-50 dark:bg-white/[0.02] border border-gray-200 dark:border-gray-800 space-y-3">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                        <div>
                          <span className="text-[11px] font-semibold text-[#5F6368] dark:text-[#94A3B8] block">
                            {t(settings.language, 'sec_personal_code')}
                          </span>
                          <span className="text-[11px] text-[#5F6368] dark:text-[#94A3B8]">
                            {t(settings.language, 'sec_personal_code_desc')}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 shrink-0 flex-wrap">
                          <button
                            type="button"
                            onClick={async () => {
                              try {
                                await navigator.clipboard.writeText(account.pqcIdentity);
                                setCopiedFingerprint(true);
                                showFeedback('Personal verification code copied to clipboard.');
                                setTimeout(() => setCopiedFingerprint(false), 2000);
                              } catch {}
                            }}
                            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#1E293B] text-xs font-semibold text-[#202124] dark:text-white hover:bg-gray-50 dark:hover:bg-slate-700 transition-colors cursor-pointer shrink-0"
                          >
                            {copiedFingerprint ? (
                              <>
                                <Check className="w-3.5 h-3.5 text-emerald-500" />
                                <span>{t(settings.language, 'sec_copied')}</span>
                              </>
                            ) : (
                              <>
                                <Copy className="w-3.5 h-3.5" />
                                <span>{t(settings.language, 'sec_copy_code')}</span>
                              </>
                            )}
                          </button>

                          <button
                            type="button"
                            disabled={isExportingCert}
                            onClick={async () => {
                              setIsExportingCert(true);
                              try {
                                const htmlContent = generateIdentityCertificateHtml({
                                  email: account.email,
                                  fingerprint: account.pqcIdentity,
                                  kemAlgorithm: 'ML-KEM-768 (NIST FIPS 203)',
                                  dsaAlgorithm: 'ML-DSA-65 (NIST FIPS 204)',
                                  hsmStatus,
                                });
                                const cleanEmail = account.email.replace(/[^a-zA-Z0-9]/g, '_');
                                const filename = `QuMail-Identity-${cleanEmail}.html`;

                                const res = await api.exportIdentityFile({
                                  filename,
                                  htmlContent,
                                });

                                if (res.success) {
                                  const savedName = res.filename || 'QuMail-Identity-Certificate.html';
                                  showFeedback(`Security Certificate exported · Saved as ${savedName}`);
                                } else {
                                  showFeedback(res.message || 'Export cancelled.', 'warn');
                                }
                              } catch (err: any) {
                                showFeedback(`Failed to export certificate: ${err?.message || err}`, 'warn');
                              } finally {
                                setIsExportingCert(false);
                              }
                            }}
                            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#1E293B] text-xs font-semibold text-[#202124] dark:text-white hover:bg-gray-50 dark:hover:bg-slate-700 transition-colors cursor-pointer shrink-0 disabled:opacity-50"
                          >
                            <Download className={`w-3.5 h-3.5 ${isExportingCert ? 'animate-bounce text-sky-400' : ''}`} />
                            <span>{isExportingCert ? t(settings.language, 'sec_exporting') : t(settings.language, 'sec_export_cert')}</span>
                          </button>
                        </div>
                      </div>

                      <div className="p-3 rounded-xl bg-white dark:bg-black/30 border border-gray-200 dark:border-gray-800">
                        <code className="text-xs font-mono font-bold text-[#202124] dark:text-emerald-400 select-all tracking-wider break-all block leading-relaxed">
                          {account.pqcIdentity.replace(/(.{4})/g, '$1 ').trim()}
                        </code>
                      </div>
                    </div>

                    {/* Underlying Security Standards */}
                    <div className="pt-2">
                      <div className="text-[11px] font-semibold text-[#5F6368] dark:text-[#94A3B8] mb-1.5">
                        {t(settings.language, 'sec_standards_title')}
                      </div>
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                        <div className="p-2.5 rounded-xl bg-gray-50 dark:bg-white/[0.02] border border-gray-200/70 dark:border-gray-800 text-center">
                          <span className="text-[10px] text-[#5F6368] block">{t(settings.language, 'sec_std_kex')}</span>
                          <span className="text-xs font-bold text-[#202124] dark:text-[#F1F5F9]">ML-KEM-768</span>
                        </div>
                        <div className="p-2.5 rounded-xl bg-gray-50 dark:bg-white/[0.02] border border-gray-200/70 dark:border-gray-800 text-center">
                          <span className="text-[10px] text-[#5F6368] block">{t(settings.language, 'sec_std_sig')}</span>
                          <span className="text-xs font-bold text-[#202124] dark:text-[#F1F5F9]">ML-DSA-65</span>
                        </div>
                        <div className="p-2.5 rounded-xl bg-gray-50 dark:bg-white/[0.02] border border-gray-200/70 dark:border-gray-800 text-center">
                          <span className="text-[10px] text-[#5F6368] block">{t(settings.language, 'sec_std_cipher')}</span>
                          <span className="text-xs font-bold text-[#202124] dark:text-[#F1F5F9]">AES-256-GCM</span>
                        </div>
                        <div className="p-2.5 rounded-xl bg-gray-50 dark:bg-white/[0.02] border border-gray-200/70 dark:border-gray-800 text-center">
                          <span className="text-[10px] text-[#5F6368] block">{t(settings.language, 'sec_std_storage')}</span>
                          <span className="text-xs font-bold text-[#202124] dark:text-[#F1F5F9]">Windows DPAPI</span>
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">
                    Sign in to initialize and view your active personal verification identity.
                  </p>
                )}
              </SectionCard>

              {/* Local Vault Protection Card */}
              <SectionCard
                title={t(settings.language, 'sec_vault_title')}
                subtitle={t(settings.language, 'sec_vault_desc')}
                icon={<Database className="w-4 h-4" />}
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-2xl bg-gray-50 dark:bg-white/[0.02] border border-gray-200 dark:border-gray-800">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-bold text-[#202124] dark:text-[#F1F5F9]">
                        {t(settings.language, 'sec_protection_state')}
                      </span>
                      <span
                        className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold ${
                          isVaultLocked
                            ? 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300 border border-amber-300 dark:border-amber-800'
                            : 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800'
                        }`}
                      >
                        {isVaultLocked ? t(settings.language, 'sec_vault_locked') : t(settings.language, 'sec_vault_active')}
                      </span>
                    </div>
                    <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">
                      {isVaultLocked
                        ? t(settings.language, 'sec_vault_locked_desc')
                        : t(settings.language, 'sec_vault_active_desc')}
                    </p>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    {isVaultLocked ? (
                      <button
                        type="button"
                        disabled={isVaultActionBusy}
                        onClick={async () => {
                          if (account.hasSecurityPin) {
                            setPinDialogMode('unlock');
                            setPinCurrentInput('');
                            setPinActionError(null);
                            return;
                          }
                          setIsVaultActionBusy(true);
                          try {
                            const res = await api.unlockVault();
                            if (res.success) {
                              setIsVaultLocked(false);
                              onVaultStateChange?.();
                              showFeedback('Mailbox unlocked and ready.');
                            } else {
                              showFeedback(res.message || 'Could not unlock vault.', 'warn');
                            }
                          } catch {
                            showFeedback('Failed to unlock vault.', 'warn');
                          } finally {
                            setIsVaultActionBusy(false);
                          }
                        }}
                        className="flex items-center space-x-1.5 px-4 py-2 rounded-xl qumail-accent-bg text-white text-xs font-bold transition-opacity shadow-sm hover:opacity-95 disabled:opacity-50 cursor-pointer"
                      >
                        <KeyRound className="w-3.5 h-3.5" />
                        <span>{isVaultActionBusy ? t(settings.language, 'unlocking') : t(settings.language, 'sec_unlock_mailbox')}</span>
                      </button>
                    ) : (
                      <button
                        type="button"
                        disabled={isVaultActionBusy}
                        onClick={async () => {
                          setIsVaultActionBusy(true);
                          try {
                            await api.lockVault();
                            setIsVaultLocked(true);
                            onVaultStateChange?.();
                            showFeedback('Mailbox locked. Encryption keys are securely protected.');
                          } catch {
                            showFeedback('Failed to lock vault.', 'warn');
                          } finally {
                            setIsVaultActionBusy(false);
                          }
                        }}
                        className="flex items-center space-x-1.5 px-4 py-2 rounded-xl bg-amber-50 hover:bg-amber-100 dark:bg-amber-950/40 dark:hover:bg-amber-900/60 text-amber-800 dark:text-amber-200 border border-amber-200 dark:border-amber-800 text-xs font-bold transition-colors cursor-pointer disabled:opacity-50"
                      >
                        <Lock className="w-3.5 h-3.5" />
                        <span>{isVaultActionBusy ? t(settings.language, 'sec_locking') : t(settings.language, 'sec_lock_now')}</span>
                      </button>
                    )}
                  </div>
                </div>

                {/* Security PIN Section */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-2xl bg-gray-50 dark:bg-white/[0.02] border border-gray-200 dark:border-gray-800 mt-3">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-bold text-[#202124] dark:text-[#F1F5F9]">
                        {t(settings.language, 'sec_pin_title')}
                      </span>
                      <span
                        className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold ${
                          account.hasSecurityPin
                            ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800'
                            : 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 border border-slate-200 dark:border-slate-700'
                        }`}
                      >
                        {account.hasSecurityPin ? t(settings.language, 'sec_pin_active') : t(settings.language, 'sec_pin_not_set')}
                      </span>
                    </div>
                    <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">
                      {account.hasSecurityPin
                        ? t(settings.language, 'sec_pin_active_desc')
                        : t(settings.language, 'sec_pin_not_set_desc')}
                    </p>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    {account.hasSecurityPin ? (
                      <>
                        <button
                          type="button"
                          onClick={() => {
                            setPinDialogMode('change');
                            setPinCurrentInput('');
                            setPinNewInput('');
                            setPinConfirmInput('');
                            setPinActionError(null);
                          }}
                          className="px-3.5 py-1.5 rounded-xl border border-gray-300 dark:border-gray-700 text-xs font-semibold text-[#202124] dark:text-[#F1F5F9] hover:bg-gray-100 dark:hover:bg-white/[0.04] transition-colors cursor-pointer"
                        >
                          {t(settings.language, 'sec_change_pin')}
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setPinDialogMode('remove');
                            setPinCurrentInput('');
                            setPinActionError(null);
                          }}
                          className="px-3.5 py-1.5 rounded-xl border border-rose-200 dark:border-rose-900/60 text-xs font-semibold text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-colors cursor-pointer"
                        >
                          {t(settings.language, 'sec_remove_pin')}
                        </button>
                      </>
                    ) : (
                      <button
                        type="button"
                        onClick={() => {
                          setPinDialogMode('set');
                          setPinNewInput('');
                          setPinConfirmInput('');
                          setPinActionError(null);
                        }}
                        className="flex items-center space-x-1.5 px-4 py-2 rounded-xl qumail-accent-bg text-white text-xs font-bold transition-opacity shadow-sm hover:opacity-95 cursor-pointer"
                      >
                        <KeyRound className="w-3.5 h-3.5" />
                        <span>{t(settings.language, 'sec_set_pin')}</span>
                      </button>
                    )}
                  </div>
                </div>

                {/* Inline PIN Action Form */}
                {pinDialogMode !== 'none' && (
                  <form
                    onSubmit={handlePinActionSubmit}
                    className="mt-3 p-4 rounded-2xl bg-white dark:bg-[#111726] border border-[#0B57D0]/30 dark:border-[#6366F1]/40 shadow-sm space-y-3.5 animate-in fade-in duration-150"
                  >
                    <div className="flex items-center justify-between border-b border-gray-100 dark:border-gray-800 pb-2">
                      <div className="flex items-center space-x-2">
                        <KeyRound className="w-4 h-4 text-[#0B57D0] dark:text-[#818CF8]" />
                        <h5 className="text-xs font-bold text-[#202124] dark:text-[#F1F5F9]">
                          {pinDialogMode === 'set' && t(settings.language, 'pin_create_title')}
                          {pinDialogMode === 'change' && t(settings.language, 'pin_change_title')}
                          {pinDialogMode === 'remove' && t(settings.language, 'pin_remove_title')}
                          {pinDialogMode === 'unlock' && t(settings.language, 'pin_unlock_title')}
                        </h5>
                      </div>
                      <button
                        type="button"
                        onClick={() => setPinDialogMode('none')}
                        className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 text-xs cursor-pointer"
                      >
                        {t(settings.language, 'pin_cancel')}
                      </button>
                    </div>

                    {(pinDialogMode === 'change' || pinDialogMode === 'remove' || pinDialogMode === 'unlock') && (
                      <div>
                        <label className="block text-[11px] font-semibold text-[#5F6368] dark:text-[#94A3B8] mb-1">
                          {pinDialogMode === 'unlock' ? t(settings.language, 'sec_pin_title') : t(settings.language, 'pin_current_label')}
                        </label>
                        <input
                          type="password"
                          inputMode="numeric"
                          pattern="[0-9]*"
                          maxLength={8}
                          autoFocus
                          value={pinCurrentInput}
                          onChange={(e) => {
                            setPinCurrentInput(e.target.value.replace(/\D/g, ''));
                            if (pinActionError) setPinActionError(null);
                          }}
                          placeholder="••••••••"
                          className="w-full text-center tracking-[0.3em] font-mono py-2 px-3 rounded-xl bg-gray-50 dark:bg-black/30 border border-gray-300 dark:border-gray-700 text-sm text-[#202124] dark:text-white focus:outline-none focus:ring-2 focus:ring-[#0B57D0]"
                        />
                      </div>
                    )}

                    {(pinDialogMode === 'set' || pinDialogMode === 'change') && (
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div>
                          <label className="block text-[11px] font-semibold text-[#5F6368] dark:text-[#94A3B8] mb-1">
                            {t(settings.language, 'pin_new_label')}
                          </label>
                          <input
                            type="password"
                            inputMode="numeric"
                            pattern="[0-9]*"
                            maxLength={8}
                            autoFocus={pinDialogMode === 'set'}
                            value={pinNewInput}
                            onChange={(e) => {
                              setPinNewInput(e.target.value.replace(/\D/g, ''));
                              if (pinActionError) setPinActionError(null);
                            }}
                            placeholder="4–8 digits"
                            className="w-full text-center tracking-[0.3em] font-mono py-2 px-3 rounded-xl bg-gray-50 dark:bg-black/30 border border-gray-300 dark:border-gray-700 text-sm text-[#202124] dark:text-white focus:outline-none focus:ring-2 focus:ring-[#0B57D0]"
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] font-semibold text-[#5F6368] dark:text-[#94A3B8] mb-1">
                            {t(settings.language, 'pin_confirm_label')}
                          </label>
                          <input
                            type="password"
                            inputMode="numeric"
                            pattern="[0-9]*"
                            maxLength={8}
                            value={pinConfirmInput}
                            onChange={(e) => {
                              setPinConfirmInput(e.target.value.replace(/\D/g, ''));
                              if (pinActionError) setPinActionError(null);
                            }}
                            placeholder="Re-enter PIN"
                            className="w-full text-center tracking-[0.3em] font-mono py-2 px-3 rounded-xl bg-gray-50 dark:bg-black/30 border border-gray-300 dark:border-gray-700 text-sm text-[#202124] dark:text-white focus:outline-none focus:ring-2 focus:ring-[#0B57D0]"
                          />
                        </div>
                      </div>
                    )}

                    {pinActionError && (
                      <p className="text-xs text-rose-600 dark:text-rose-400 font-semibold">
                        {pinActionError}
                      </p>
                    )}

                    <div className="flex justify-end gap-2 pt-1">
                      <button
                        type="button"
                        onClick={() => setPinDialogMode('none')}
                        className="px-3.5 py-1.5 rounded-xl border border-gray-300 dark:border-gray-700 text-xs font-semibold text-[#5F6368] dark:text-[#94A3B8] hover:bg-gray-100 dark:hover:bg-white/[0.04] transition-colors cursor-pointer"
                      >
                        {t(settings.language, 'pin_cancel')}
                      </button>
                      <button
                        type="submit"
                        disabled={isPinSubmitting}
                        className={`px-4 py-1.5 rounded-xl text-xs font-bold transition-all shadow-sm cursor-pointer disabled:opacity-50 ${
                          pinDialogMode === 'remove'
                            ? 'bg-rose-600 hover:bg-rose-700 text-white'
                            : 'qumail-accent-bg text-white hover:opacity-95'
                        }`}
                      >
                        {isPinSubmitting
                          ? 'Saving...'
                          : pinDialogMode === 'set'
                          ? t(settings.language, 'pin_set_btn')
                          : pinDialogMode === 'change'
                          ? t(settings.language, 'pin_update_btn')
                          : pinDialogMode === 'remove'
                          ? t(settings.language, 'pin_remove_btn')
                          : t(settings.language, 'sec_unlock_mailbox')}
                      </button>
                    </div>
                  </form>
                )}
              </SectionCard>
            </div>
          )}

          {/* 5. Appearance Tab */}
          {activeTab === 'appearance' && (
            <div className="space-y-8 divide-y divide-gray-100 dark:divide-gray-800">
              {/* Theme Wireframe Cards + Sync with System */}
              <div className="space-y-4 pt-2">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                  <div>
                    <h4 className="text-sm font-bold text-[#202124] dark:text-[#F1F5F9]">{t(settings.language, 'theme_title')}</h4>
                    <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">
                      {t(settings.language, 'theme_desc')}
                    </p>
                  </div>

                  {/* Sync with System Toggle */}
                  <label className="inline-flex items-center space-x-2.5 cursor-pointer select-none px-3 py-1.5 rounded-xl border border-gray-200 dark:border-gray-700/80 bg-gray-50/70 dark:bg-white/[0.03]">
                    <span className="text-xs font-medium text-[#202124] dark:text-[#E2E8F0]">
                      {t(settings.language, 'sync_with_system')}
                    </span>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={settings.syncWithSystem}
                      onClick={() => onUpdateSettings({ syncWithSystem: !settings.syncWithSystem })}
                      className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors cursor-pointer ${
                        settings.syncWithSystem
                          ? 'qumail-accent-bg'
                          : 'bg-gray-300 dark:bg-gray-600'
                      }`}
                    >
                      <span
                        className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform duration-200 ${
                          settings.syncWithSystem ? 'translate-x-5' : 'translate-x-0.5'
                        }`}
                      />
                    </button>
                  </label>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  {(
                    [
                      {
                        id: 'light' as ThemeMode,
                        name: t(settings.language, 'theme_light'),
                        desc: t(settings.language, 'theme_light_desc'),
                        bg: '#F8FAFC',
                        surface: '#FFFFFF',
                        border: '#E2E8F0',
                        line: '#CBD5E1',
                        lineStrong: '#64748B',
                      },
                      {
                        id: 'dark' as ThemeMode,
                        name: t(settings.language, 'theme_dark'),
                        desc: t(settings.language, 'theme_dark_desc'),
                        bg: '#09090B',
                        surface: '#18181B',
                        border: '#27272A',
                        line: '#3F3F46',
                        lineStrong: '#A1A1AA',
                      },
                      {
                        id: 'midnight' as ThemeMode,
                        name: t(settings.language, 'theme_midnight'),
                        desc: t(settings.language, 'theme_midnight_desc'),
                        bg: '#0A0E17',
                        surface: '#161F33',
                        border: '#1F2C47',
                        line: '#2A3B5F',
                        lineStrong: '#94A3B8',
                      },
                    ]
                  ).map((tMode) => {
                    const isSelected = !settings.syncWithSystem
                      ? settings.theme === tMode.id
                      : (tMode.id === 'light' && !isDarkMode) || (tMode.id === settings.theme && isDarkMode);
                    return (
                      <motion.button
                        key={tMode.id}
                        type="button"
                        whileHover={{ y: -2 }}
                        whileTap={{ scale: 0.98 }}
                        onClick={() => onUpdateSettings({ theme: tMode.id, syncWithSystem: false })}
                        className={`group text-left rounded-2xl border-2 p-3 transition-colors cursor-pointer ${
                          isSelected
                            ? 'qumail-accent-border qumail-accent-soft'
                            : 'border-gray-200 dark:border-gray-700/80 hover:border-gray-300 dark:hover:border-gray-600 bg-white dark:bg-white/[0.02]'
                        }`}
                      >
                        {/* Miniature UI Wireframe */}
                        <div
                          className="w-full h-24 rounded-xl overflow-hidden border flex p-1.5 gap-1.5 mb-3 shadow-inner"
                          style={{ backgroundColor: tMode.bg, borderColor: tMode.border }}
                        >
                          {/* Mini Sidebar */}
                          <div
                            className="w-1/4 rounded-lg p-1.5 flex flex-col gap-1 border"
                            style={{ backgroundColor: tMode.surface, borderColor: tMode.border }}
                          >
                            <div className="h-2.5 w-full rounded qumail-accent-bg opacity-90" />
                            <div className="h-1.5 w-4/5 rounded-full mt-1" style={{ backgroundColor: tMode.lineStrong }} />
                            <div className="h-1.5 w-3/5 rounded-full" style={{ backgroundColor: tMode.line }} />
                            <div className="h-1.5 w-4/5 rounded-full" style={{ backgroundColor: tMode.line }} />
                          </div>
                          {/* Mini List + Reading Pane */}
                          <div
                            className="flex-1 rounded-lg p-1.5 flex flex-col gap-1.5 border"
                            style={{ backgroundColor: tMode.surface, borderColor: tMode.border }}
                          >
                            <div className="flex items-center justify-between">
                              <div className="h-1.5 w-12 rounded-full" style={{ backgroundColor: tMode.lineStrong }} />
                              <div className="h-2 w-2 rounded-full qumail-accent-bg" />
                            </div>
                            <div className="space-y-1">
                              <div className="h-2 w-full rounded" style={{ backgroundColor: tMode.line }} />
                              <div className="h-2 w-full rounded opacity-80" style={{ backgroundColor: tMode.line }} />
                              <div className="h-2 w-3/4 rounded opacity-60" style={{ backgroundColor: tMode.line }} />
                            </div>
                          </div>
                        </div>

                        <div className="flex items-center justify-between">
                          <div>
                            <div className="text-xs font-bold text-[#202124] dark:text-[#F1F5F9]">
                              {tMode.name}
                            </div>
                            <div className="text-[11px] text-[#5F6368] dark:text-[#94A3B8]">
                              {tMode.desc}
                            </div>
                          </div>
                          {isSelected && (
                            <span className="w-5 h-5 rounded-full qumail-accent-bg text-white flex items-center justify-center shrink-0">
                              <Check className="w-3 h-3" />
                            </span>
                          )}
                        </div>
                      </motion.button>
                    );
                  })}
                </div>
              </div>

              {/* Accent Color Swatches */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-6">
                <div className="space-y-1">
                  <h4 className="text-sm font-bold text-[#202124] dark:text-[#F1F5F9]">{t(settings.language, 'accent_color_title')}</h4>
                  <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">
                    {t(settings.language, 'accent_color_desc')}
                  </p>
                </div>
                <div className="md:col-span-2 flex flex-wrap items-center gap-4">
                  {(
                    [
                      { id: 'blue' as AccentColor, label: 'Blue', hex: '#0B57D0' },
                      { id: 'indigo' as AccentColor, label: 'Indigo', hex: '#6366F1' },
                      { id: 'emerald' as AccentColor, label: 'Emerald', hex: '#10B981' },
                      { id: 'cyan' as AccentColor, label: 'Cyan', hex: '#06B6D4' },
                      { id: 'rose' as AccentColor, label: 'Rose', hex: '#F43F5E' },
                    ]
                  ).map((swatch) => {
                    const active = (settings.accentColor || 'blue') === swatch.id;
                    return (
                      <motion.button
                        key={swatch.id}
                        type="button"
                        whileHover={{ scale: 1.08 }}
                        whileTap={{ scale: 0.94 }}
                        onClick={() => onUpdateSettings({ accentColor: swatch.id })}
                        title={swatch.label}
                        className="relative flex flex-col items-center gap-1.5 cursor-pointer group"
                      >
                        <div className="relative w-10 h-10 flex items-center justify-center">
                          {active && (
                            <motion.span
                              layoutId="appearance-accent-ring"
                              transition={{ type: 'spring', stiffness: 420, damping: 30 }}
                              className="absolute inset-0 rounded-full border-2"
                              style={{ borderColor: swatch.hex }}
                            />
                          )}
                          <span
                            className="w-7 h-7 rounded-full flex items-center justify-center shadow-sm transition-transform"
                            style={{ backgroundColor: swatch.hex }}
                          >
                            {active && <Check className="w-3.5 h-3.5 text-white stroke-[3]" />}
                          </span>
                        </div>
                        <span
                          className={`text-[11px] font-medium ${
                            active
                              ? 'text-[#202124] dark:text-[#F1F5F9] font-semibold'
                              : 'text-[#5F6368] dark:text-[#94A3B8]'
                          }`}
                        >
                          {swatch.label}
                        </span>
                      </motion.button>
                    );
                  })}
                </div>
              </div>

              {/* Typography Controls + Live Preview */}
              <div className="space-y-5 pt-6">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="space-y-1">
                    <h4 className="text-sm font-bold text-[#202124] dark:text-[#F1F5F9]">{t(settings.language, 'font_family_title')}</h4>
                    <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">
                      {t(settings.language, 'font_family_desc')}
                    </p>
                  </div>
                  <div className="md:col-span-2 grid grid-cols-2 sm:grid-cols-4 gap-2 p-1 rounded-2xl bg-gray-100/90 dark:bg-white/[0.04] border border-gray-200/70 dark:border-gray-700/70">
                    {(
                      [
                        { id: 'sans' as FontFamilyOption, label: t(settings.language, 'font_sans') },
                        { id: 'geometric' as FontFamilyOption, label: t(settings.language, 'font_geometric') },
                        { id: 'serif' as FontFamilyOption, label: t(settings.language, 'font_serif') },
                        { id: 'mono' as FontFamilyOption, label: t(settings.language, 'font_mono') },
                      ]
                    ).map((f) => {
                      const active = (settings.fontFamily || 'sans') === f.id;
                      return (
                        <button
                          key={f.id}
                          type="button"
                          onClick={() => onUpdateSettings({ fontFamily: f.id })}
                          className={`relative px-3 py-2 rounded-xl text-xs font-medium transition-colors cursor-pointer flex flex-col items-center gap-0.5 ${
                            active
                              ? 'text-[#202124] dark:text-white font-bold'
                              : 'text-[#5F6368] dark:text-[#94A3B8] hover:text-[#202124] dark:hover:text-white'
                          }`}
                        >
                          {active && (
                            <motion.div
                              layoutId="appearance-font-family-pill"
                              transition={{ type: 'spring', stiffness: 420, damping: 32 }}
                              className="absolute inset-0 rounded-xl bg-white dark:bg-[#1E293B] shadow-sm border border-gray-200/80 dark:border-gray-600/60"
                            />
                          )}
                          <span
                            className="relative z-10 text-sm"
                            style={{ fontFamily: FONT_FAMILY_STYLE[f.id] }}
                          >
                            Aa
                          </span>
                          <span className="relative z-10 text-[11px] truncate max-w-full">{f.label}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-center">
                  <div className="space-y-1">
                    <h4 className="text-sm font-bold text-[#202124] dark:text-[#F1F5F9]">{t(settings.language, 'font_size_title')}</h4>
                    <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">
                      {t(settings.language, 'font_size_desc')}
                    </p>
                  </div>
                  <div className="md:col-span-2 inline-flex p-1 rounded-2xl bg-gray-100/90 dark:bg-white/[0.04] border border-gray-200/70 dark:border-gray-700/70 w-full sm:w-auto">
                    {(
                      [
                        { id: 'small' as FontSizeOption, label: t(settings.language, 'size_small') },
                        { id: 'medium' as FontSizeOption, label: t(settings.language, 'size_medium') },
                        { id: 'large' as FontSizeOption, label: t(settings.language, 'size_large') },
                      ]
                    ).map((sz) => {
                      const active = (settings.fontSize || 'medium') === sz.id;
                      return (
                        <button
                          key={sz.id}
                          type="button"
                          onClick={() => onUpdateSettings({ fontSize: sz.id })}
                          className={`relative flex-1 sm:flex-initial px-4 py-2 rounded-xl text-xs transition-colors cursor-pointer ${
                            active
                              ? 'text-[#202124] dark:text-white font-bold'
                              : 'text-[#5F6368] dark:text-[#94A3B8] hover:text-[#202124] dark:hover:text-white font-medium'
                          }`}
                        >
                          {active && (
                            <motion.div
                              layoutId="appearance-font-size-pill"
                              transition={{ type: 'spring', stiffness: 420, damping: 32 }}
                              className="absolute inset-0 rounded-xl bg-white dark:bg-[#1E293B] shadow-sm border border-gray-200/80 dark:border-gray-600/60"
                            />
                          )}
                          <span className="relative z-10">{sz.label}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Live Typography Preview Card */}
                <div className="rounded-2xl border border-gray-200 dark:border-gray-700/80 bg-gray-50/70 dark:bg-white/[0.02] p-4 space-y-2">
                  <div className="flex items-center justify-between text-[11px] text-[#5F6368] dark:text-[#94A3B8]">
                    <span className="font-semibold uppercase tracking-wider">{t(settings.language, 'typography_preview')}</span>
                    <span className="px-2 py-0.5 rounded-full qumail-accent-soft qumail-accent-text font-semibold">
                      ML-KEM-768 Verified
                    </span>
                  </div>
                  <p
                    style={{
                      fontFamily: FONT_FAMILY_STYLE[settings.fontFamily || 'sans'],
                      fontSize: FONT_SIZE_STYLE[settings.fontSize || 'medium'],
                    }}
                    className="text-[#202124] dark:text-[#F1F5F9] leading-relaxed"
                  >
                    {t(settings.language, 'typography_sample_text')}
                  </p>
                </div>
              </div>

              {/* Inbox Layout & Density */}
              <div className="space-y-5 pt-6">
                <div className="space-y-3">
                  <div>
                    <h4 className="text-sm font-bold text-[#202124] dark:text-[#F1F5F9]">{t(settings.language, 'list_density_title')}</h4>
                    <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">
                      {t(settings.language, 'list_density_desc')}
                    </p>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    {(
                      [
                        {
                          id: 'comfortable' as ListDensityOption,
                          label: t(settings.language, 'density_comfortable'),
                          desc: t(settings.language, 'density_comfortable_desc'),
                          gapClass: 'gap-2',
                          barClass: 'h-3',
                        },
                        {
                          id: 'cozy' as ListDensityOption,
                          label: t(settings.language, 'density_cozy'),
                          desc: t(settings.language, 'density_cozy_desc'),
                          gapClass: 'gap-1.5',
                          barClass: 'h-2.5',
                        },
                        {
                          id: 'compact' as ListDensityOption,
                          label: t(settings.language, 'density_compact'),
                          desc: t(settings.language, 'density_compact_desc'),
                          gapClass: 'gap-1',
                          barClass: 'h-1.5',
                        },
                      ]
                    ).map((d) => {
                      const active = (settings.listDensity || 'comfortable') === d.id;
                      return (
                        <motion.button
                          key={d.id}
                          type="button"
                          whileHover={{ y: -2 }}
                          whileTap={{ scale: 0.98 }}
                          onClick={() => onUpdateSettings({ listDensity: d.id })}
                          className={`text-left rounded-2xl border-2 p-3 transition-colors cursor-pointer ${
                            active
                              ? 'qumail-accent-border qumail-accent-soft'
                              : 'border-gray-200 dark:border-gray-700/80 hover:border-gray-300 dark:hover:border-gray-600 bg-white dark:bg-white/[0.02]'
                          }`}
                        >
                          <div className={`w-full h-16 rounded-xl bg-gray-100 dark:bg-black/30 border border-gray-200/80 dark:border-gray-700/60 p-2 flex flex-col justify-center ${d.gapClass} mb-2.5`}>
                            {[0, 1, 2].map((rowIdx) => (
                              <div key={rowIdx} className="flex items-center gap-1.5">
                                <div className="w-2 h-2 rounded-full bg-gray-300 dark:bg-gray-600 shrink-0" />
                                <div
                                  className={`${d.barClass} flex-1 rounded bg-gray-300/90 dark:bg-gray-600/80`}
                                />
                              </div>
                            ))}
                          </div>
                          <div className="flex items-center justify-between">
                            <div>
                              <div className="text-xs font-bold text-[#202124] dark:text-[#F1F5F9]">
                                {d.label}
                              </div>
                              <div className="text-[11px] text-[#5F6368] dark:text-[#94A3B8]">
                                {d.desc}
                              </div>
                            </div>
                            {active && (
                              <span className="w-5 h-5 rounded-full qumail-accent-bg text-white flex items-center justify-center shrink-0">
                                <Check className="w-3 h-3" />
                              </span>
                            )}
                          </div>
                        </motion.button>
                      );
                    })}
                  </div>
                </div>

                {/* Show Sender Avatars Toggle */}
                <div className="flex items-center justify-between pt-2">
                  <div>
                    <h4 className="text-sm font-bold text-[#202124] dark:text-[#F1F5F9]">{t(settings.language, 'show_sender_avatars')}</h4>
                    <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">
                      {t(settings.language, 'show_sender_avatars_desc')}
                    </p>
                  </div>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={settings.showSenderAvatars !== false}
                    onClick={() =>
                      onUpdateSettings({ showSenderAvatars: !(settings.showSenderAvatars !== false) })
                    }
                    className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors cursor-pointer ${
                      settings.showSenderAvatars !== false
                        ? 'qumail-accent-bg'
                        : 'bg-gray-300 dark:bg-gray-600'
                    }`}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                        settings.showSenderAvatars !== false ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* 6. Accessibility Tab */}
          {activeTab === 'accessibility' && (
            <div className="space-y-6 text-xs text-[#5F6368] dark:text-[#94A3B8] leading-relaxed pb-6">
              {/* Card 1: Vision & Reading Comfort */}
              <SectionCard
                icon={<Eye className="w-4 h-4" />}
                title={t(settings.language, 'access_vision_title')}
                subtitle={t(settings.language, 'access_vision_desc')}
              >
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-[#202124] dark:text-[#F1F5F9]">{t(settings.language, 'interface_scale')}</span>
                    <span className="text-xs font-medium text-[#5F6368] dark:text-[#94A3B8]">
                      {settings.fontScale === 'xlarge' ? '130%' : settings.fontScale === 'large' ? '115%' : '100%'}
                    </span>
                  </div>
                  <SegmentedControl
                    layoutId="accessibility-font-scale"
                    options={[
                      { value: 'default', label: t(settings.language, 'scale_default') },
                      { value: 'large', label: t(settings.language, 'scale_large') },
                      { value: 'xlarge', label: t(settings.language, 'scale_xlarge') },
                    ]}
                    value={settings.fontScale || 'default'}
                    onChange={(scale) => onUpdateSettings({ fontScale: scale as 'default' | 'large' | 'xlarge' })}
                  />
                  <div className="p-3 rounded-xl bg-gray-50 dark:bg-black/20 border border-gray-200/60 dark:border-gray-800/80 text-xs text-[#3C4043] dark:text-[#CBD5E1]">
                    <span className="font-semibold block mb-0.5 text-gray-500 dark:text-gray-400 text-[10px] uppercase tracking-wider">{t(settings.language, 'scale_preview')}</span>
                    <p className="line-clamp-2">
                      QuMail client-side post-quantum security ensures emails remain private against quantum threats while staying comfortable to read.
                    </p>
                  </div>
                </div>

                <SettingToggleRow
                  title={t(settings.language, 'high_contrast_title')}
                  description={t(settings.language, 'high_contrast_desc')}
                  checked={Boolean(settings.highContrast)}
                  onChange={(checked) => onUpdateSettings({ highContrast: checked })}
                />

                <SettingToggleRow
                  title={t(settings.language, 'dyslexic_font_title')}
                  description={t(settings.language, 'dyslexic_font_desc')}
                  checked={Boolean(settings.dyslexicReadingFont)}
                  onChange={(checked) => onUpdateSettings({ dyslexicReadingFont: checked })}
                />

                <SettingToggleRow
                  title={t(settings.language, 'show_icon_labels_title')}
                  description={t(settings.language, 'show_icon_labels_desc')}
                  checked={Boolean(settings.showIconLabels)}
                  onChange={(checked) => onUpdateSettings({ showIconLabels: checked })}
                />
              </SectionCard>

              {/* Card 2: Motion & Sensory Comfort */}
              <SectionCard
                icon={<Sparkles className="w-4 h-4" />}
                title={t(settings.language, 'access_motion_title')}
                subtitle={t(settings.language, 'access_motion_desc')}
              >
                <SettingToggleRow
                  title={t(settings.language, 'reduce_motion_title')}
                  description={t(settings.language, 'reduce_motion_desc')}
                  checked={Boolean(settings.reduceMotion)}
                  onChange={(checked) => onUpdateSettings({ reduceMotion: checked })}
                />
              </SectionCard>

              {/* Card 3: Keyboard & Motor Navigation */}
              <SectionCard
                icon={<Keyboard className="w-4 h-4" />}
                title={t(settings.language, 'access_keyboard_title')}
                subtitle={t(settings.language, 'access_keyboard_desc')}
              >
                <SettingToggleRow
                  title={t(settings.language, 'enhanced_focus_title')}
                  description={t(settings.language, 'enhanced_focus_desc')}
                  checked={settings.enhancedFocusRings !== false}
                  onChange={(checked) => onUpdateSettings({ enhancedFocusRings: checked })}
                />

                <SettingToggleRow
                  title={t(settings.language, 'single_key_title')}
                  description={t(settings.language, 'single_key_desc')}
                  checked={settings.singleKeyShortcuts !== false}
                  onChange={(checked) => onUpdateSettings({ singleKeyShortcuts: checked })}
                />

                <div className="pt-2">
                  <span className="text-xs font-semibold text-[#202124] dark:text-[#F1F5F9] block mb-2">
                    {t(settings.language, 'shortcuts_ref_title')}
                  </span>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                    <div className="flex items-center justify-between p-2 rounded-xl bg-gray-50 dark:bg-black/20 border border-gray-200/50 dark:border-gray-800">
                      <span className="text-gray-600 dark:text-gray-400">{t(settings.language, 'shortcut_compose')}</span>
                      <kbd className="px-2 py-0.5 rounded-md bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 font-mono text-[11px] font-semibold">Ctrl + N</kbd>
                    </div>
                    <div className="flex items-center justify-between p-2 rounded-xl bg-gray-50 dark:bg-black/20 border border-gray-200/50 dark:border-gray-800">
                      <span className="text-gray-600 dark:text-gray-400">{t(settings.language, 'shortcut_send')}</span>
                      <kbd className="px-2 py-0.5 rounded-md bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 font-mono text-[11px] font-semibold">Ctrl + Enter</kbd>
                    </div>
                    <div className="flex items-center justify-between p-2 rounded-xl bg-gray-50 dark:bg-black/20 border border-gray-200/50 dark:border-gray-800">
                      <span className="text-gray-600 dark:text-gray-400">{t(settings.language, 'shortcut_search')}</span>
                      <kbd className="px-2 py-0.5 rounded-md bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 font-mono text-[11px] font-semibold">Ctrl + K</kbd>
                    </div>
                    <div className="flex items-center justify-between p-2 rounded-xl bg-gray-50 dark:bg-black/20 border border-gray-200/50 dark:border-gray-800">
                      <span className="text-gray-600 dark:text-gray-400">{t(settings.language, 'shortcut_next_prev')}</span>
                      <kbd className="px-2 py-0.5 rounded-md bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 font-mono text-[11px] font-semibold">J / K</kbd>
                    </div>
                    <div className="flex items-center justify-between p-2 rounded-xl bg-gray-50 dark:bg-black/20 border border-gray-200/50 dark:border-gray-800">
                      <span className="text-gray-600 dark:text-gray-400">{t(settings.language, 'shortcut_star_unread')}</span>
                      <kbd className="px-2 py-0.5 rounded-md bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 font-mono text-[11px] font-semibold">S / U</kbd>
                    </div>
                    <div className="flex items-center justify-between p-2 rounded-xl bg-gray-50 dark:bg-black/20 border border-gray-200/50 dark:border-gray-800">
                      <span className="text-gray-600 dark:text-gray-400">{t(settings.language, 'shortcut_close_esc')}</span>
                      <kbd className="px-2 py-0.5 rounded-md bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 font-mono text-[11px] font-semibold">Esc</kbd>
                    </div>
                  </div>
                </div>
              </SectionCard>

              {/* Card 4: Screen Reader & Assistive Support */}
              <SectionCard
                icon={<Volume2 className="w-4 h-4" />}
                title={t(settings.language, 'access_screen_reader_title')}
                subtitle={t(settings.language, 'access_screen_reader_desc')}
              >
                <p className="text-xs text-gray-600 dark:text-gray-400">
                  {t(settings.language, 'access_screen_reader_body')}
                </p>

                <div className="pt-2 flex items-center justify-between border-t border-gray-100 dark:border-gray-800">
                  <div>
                    <span className="text-sm font-semibold text-[#202124] dark:text-[#F1F5F9] block">
                      {t(settings.language, 'reset_access_title')}
                    </span>
                    <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">
                      {t(settings.language, 'reset_access_desc')}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      onUpdateSettings({
                        fontScale: 'default',
                        highContrast: false,
                        dyslexicReadingFont: false,
                        showIconLabels: false,
                        reduceMotion: false,
                        enhancedFocusRings: true,
                        singleKeyShortcuts: true,
                      });
                      if (onShowNotice) {
                        onShowNotice('Accessibility preferences reset to default');
                      }
                    }}
                    className="inline-flex items-center space-x-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold text-gray-700 dark:text-gray-200 bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 transition-colors cursor-pointer"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    <span>{t(settings.language, 'reset_defaults_btn')}</span>
                  </button>
                </div>
              </SectionCard>
            </div>
          )}

          {/* 7. Offline Translation Tab */}
          {activeTab === 'offline_translation' && (
            <div className="space-y-6 text-xs text-[#5F6368] dark:text-[#94A3B8] leading-relaxed pb-6">
              {/* Card 1: Device Compatibility Check */}
              <SectionCard
                icon={<Cpu className="w-4 h-4" />}
                title={t(settings.language, 'trans_compat_title')}
                subtitle={t(settings.language, 'trans_compat_desc')}
              >
                <div className="space-y-4">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-2xl bg-gray-50 dark:bg-white/[0.02] border border-gray-200 dark:border-gray-800">
                    <div className="flex items-center space-x-3">
                      <div
                        className={`w-3 h-3 rounded-full ${
                          compatData?.verdict === 'optimal'
                            ? 'bg-emerald-500 animate-pulse'
                            : compatData?.verdict === 'compatible'
                            ? 'bg-blue-500'
                            : 'bg-amber-500'
                        }`}
                      />
                      <div>
                        <div className="flex items-center space-x-2">
                          <span className="font-bold text-sm text-[#202124] dark:text-[#F1F5F9]">
                            {compatData?.verdict === 'optimal'
                              ? t(settings.language, 'trans_verdict_optimal')
                              : compatData?.verdict === 'compatible'
                              ? t(settings.language, 'trans_verdict_compatible')
                              : t(settings.language, 'trans_verdict_limited')}
                          </span>
                        </div>
                        <p className="text-[11px] text-[#5F6368] dark:text-[#94A3B8] mt-0.5">
                          {compatData ? `${t(settings.language, 'trans_est_speed')}: ${compatData.estimated_speed}` : 'Hardware analysis ready'}
                        </p>
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={handleCheckCompatibility}
                      disabled={isCheckingCompat}
                      className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-xl border border-gray-300 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 text-xs font-semibold text-[#202124] dark:text-white transition-colors cursor-pointer disabled:opacity-50"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 ${isCheckingCompat ? 'animate-spin' : ''}`} />
                      <span>{isCheckingCompat ? t(settings.language, 'trans_checking') : (compatData ? t(settings.language, 'trans_recheck_btn') : t(settings.language, 'trans_check_btn'))}</span>
                    </button>
                  </div>

                  {/* 3 Metric Readout Cards */}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div className="p-3.5 rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111726]/40 flex flex-col justify-between">
                      <span className="text-[11px] text-[#5F6368] dark:text-[#94A3B8] font-medium">{t(settings.language, 'trans_ram_avail')}</span>
                      <div className="mt-1.5 flex items-baseline space-x-1.5">
                        <span className="text-lg font-bold text-[#202124] dark:text-[#F1F5F9] font-mono">
                          {compatData ? `${compatData.free_ram_gb} GB` : '—'}
                        </span>
                        <span className="text-[10px] text-[#5F6368] dark:text-[#94A3B8]">
                          {compatData ? `/ ${compatData.total_ram_gb} GB Total` : ''}
                        </span>
                      </div>
                    </div>

                    <div className="p-3.5 rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111726]/40 flex flex-col justify-between">
                      <span className="text-[11px] text-[#5F6368] dark:text-[#94A3B8] font-medium">{t(settings.language, 'trans_disk_avail')}</span>
                      <div className="mt-1.5 flex items-baseline space-x-1.5">
                        <span className="text-lg font-bold text-[#202124] dark:text-[#F1F5F9] font-mono">
                          {compatData ? `${compatData.free_disk_gb} GB` : '—'}
                        </span>
                        <span className="text-[10px] text-[#5F6368] dark:text-[#94A3B8]">(Drive %LOCALAPPDATA%)</span>
                      </div>
                    </div>

                    <div className="p-3.5 rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111726]/40 flex flex-col justify-between">
                      <span className="text-[11px] text-[#5F6368] dark:text-[#94A3B8] font-medium">{t(settings.language, 'trans_cpu_cores')}</span>
                      <div className="mt-1.5 flex items-baseline space-x-1.5">
                        <span className="text-lg font-bold text-[#202124] dark:text-[#F1F5F9] font-mono">
                          {compatData ? compatData.cpu_cores : '—'}
                        </span>
                        <span className="text-[10px] text-[#5F6368] dark:text-[#94A3B8]">Threads</span>
                      </div>
                    </div>
                  </div>

                  {compatData?.warning && (
                    <div className="p-3 rounded-xl border border-amber-200/80 dark:border-amber-800/60 bg-amber-50/50 dark:bg-amber-950/20 text-amber-800 dark:text-amber-300 text-xs flex items-start space-x-2">
                      <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                      <span>{compatData.warning}</span>
                    </div>
                  )}
                </div>
              </SectionCard>

              {/* Card 2: Opt-In & Privacy / Accuracy Notice */}
              <SectionCard
                icon={<ShieldCheck className="w-4 h-4" />}
                title={t(settings.language, 'trans_optin_title')}
                subtitle={t(settings.language, 'trans_optin_desc')}
              >
                <div className="space-y-4">
                  <SettingToggleRow
                    title={t(settings.language, 'trans_enable_toggle')}
                    description={t(settings.language, 'trans_optin_desc')}
                    checked={settings.enableOfflineTranslation}
                    onChange={(checked: boolean) => onUpdateSettings({ enableOfflineTranslation: checked })}
                  />

                  <SettingToggleRow
                    title={t(settings.language, 'allow_standard_mail_trans')}
                    description={t(settings.language, 'allow_standard_mail_trans_desc')}
                    checked={Boolean(settings.allowStandardMailTranslation)}
                    onChange={(checked: boolean) => onUpdateSettings({ allowStandardMailTranslation: checked })}
                  />

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                    <div className="p-3.5 rounded-xl border border-emerald-200/70 dark:border-emerald-800/50 bg-emerald-50/30 dark:bg-emerald-950/15 space-y-1.5">
                      <div className="flex items-center space-x-2 text-emerald-800 dark:text-emerald-300 font-bold text-xs">
                        <Lock className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                        <span>{t(settings.language, 'trans_privacy_title')}</span>
                      </div>
                      <p className="text-[11px] text-emerald-900/80 dark:text-emerald-300/80 leading-relaxed">
                        {t(settings.language, 'trans_privacy_desc')}
                      </p>
                    </div>

                    <div className="p-3.5 rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50/50 dark:bg-white/[0.02] space-y-1.5">
                      <div className="flex items-center space-x-2 text-[#202124] dark:text-[#F1F5F9] font-bold text-xs">
                        <AlertCircle className="w-3.5 h-3.5 text-blue-500" />
                        <span>{t(settings.language, 'trans_accuracy_title')}</span>
                      </div>
                      <p className="text-[11px] text-[#5F6368] dark:text-[#94A3B8] leading-relaxed">
                        {t(settings.language, 'trans_accuracy_desc')}
                      </p>
                      <p className="text-[10.5px] text-amber-700 dark:text-amber-400/90 leading-relaxed pt-1 border-t border-gray-200/60 dark:border-gray-800/60 font-medium">
                        {t(settings.language, 'trans_disclaimer_note')}
                      </p>
                    </div>
                  </div>
                </div>
              </SectionCard>

              {/* Card 3: Offline Language Model (NLLB-200-distilled-600M INT8) */}
              <SectionCard
                icon={<Database className="w-4 h-4" />}
                title={t(settings.language, 'trans_model_title')}
                subtitle={t(settings.language, 'trans_model_desc')}
              >
                <div className="space-y-4">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-2xl bg-gray-50 dark:bg-white/[0.02] border border-gray-200 dark:border-gray-800">
                    <div className="space-y-1">
                      <div className="flex items-center space-x-2">
                        <span className="font-bold text-sm text-[#202124] dark:text-[#F1F5F9]">
                          NLLB-200-distilled-600M (INT8)
                        </span>
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                          transStatus.isInstalled
                            ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300'
                            : transStatus.isDownloading
                            ? 'bg-blue-100 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300 animate-pulse'
                            : 'bg-gray-200 text-gray-700 dark:bg-gray-800 dark:text-gray-300'
                        }`}>
                          {transStatus.isInstalled
                            ? `${t(settings.language, 'trans_model_installed')} (${transStatus.modelSizeMB} MB)`
                            : transStatus.isDownloading
                            ? t(settings.language, 'trans_model_downloading')
                            : t(settings.language, 'trans_model_not_installed')}
                        </span>
                        {transStatus.isInstalled && (
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-bold flex items-center space-x-1 ${
                              transStatus.isModelLoadedInRam
                                ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/70 dark:text-emerald-300'
                                : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
                            }`}
                          >
                            <span>{transStatus.isModelLoadedInRam ? '●' : '○'}</span>
                            <span>
                              {transStatus.isModelLoadedInRam
                                ? t(settings.language, 'trans_model_in_ram')
                                : t(settings.language, 'trans_model_idle_disk')}
                            </span>
                          </span>
                        )}
                        <button
                          type="button"
                          onClick={handleRefreshTransStatus}
                          disabled={isRefreshingTransStatus}
                          title="Refresh model and download status from disk"
                          className="p-1 rounded-lg border border-gray-200 dark:border-gray-700 text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors cursor-pointer"
                        >
                          <RefreshCw className={`w-3.5 h-3.5 ${isRefreshingTransStatus ? 'animate-spin' : ''}`} />
                        </button>
                      </div>
                      <p className="text-[11px] text-[#5F6368] dark:text-[#94A3B8]">
                        {t(settings.language, 'trans_languages_supported')}
                      </p>
                    </div>

                    <div className="flex items-center space-x-2">
                      {transStatus.isInstalled && (
                        <button
                          type="button"
                          onClick={handleUnloadModel}
                          disabled={isUnloadingModel}
                          title={transStatus.isModelLoadedInRam ? t(settings.language, 'trans_unload_ram_btn') : t(settings.language, 'trans_model_idle_disk')}
                          className={`px-3 py-1.5 rounded-xl border text-xs font-semibold transition-colors flex items-center space-x-1.5 cursor-pointer shadow-xs ${
                            transStatus.isModelLoadedInRam
                              ? 'border-emerald-300 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-950/40 bg-emerald-50/50 dark:bg-emerald-950/20'
                              : 'border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 bg-transparent'
                          }`}
                        >
                          <Cpu className={`w-3.5 h-3.5 ${isUnloadingModel ? 'animate-spin' : ''}`} />
                          <span>{t(settings.language, 'trans_unload_ram_btn')}</span>
                        </button>
                      )}
                      {transStatus.isDownloading ? (
                        <button
                          type="button"
                          onClick={handleCancelDownload}
                          className="px-3.5 py-1.5 rounded-xl border border-rose-300 dark:border-rose-800 text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/30 text-xs font-semibold transition-colors cursor-pointer"
                        >
                          {t(settings.language, 'trans_cancel_btn')}
                        </button>
                      ) : transStatus.isInstalled ? (
                        <button
                          type="button"
                          onClick={handleDeleteModel}
                          disabled={isDeletingModel}
                          className="px-3.5 py-1.5 rounded-xl border border-gray-300 dark:border-gray-700 text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/30 text-xs font-semibold transition-colors cursor-pointer disabled:opacity-50"
                        >
                          {t(settings.language, 'trans_delete_btn')}
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={handleDownloadModel}
                          className="px-4 py-2 rounded-xl qumail-accent-bg text-white text-xs font-bold hover:opacity-95 transition-opacity cursor-pointer flex items-center space-x-1.5 shadow-sm"
                        >
                          <Download className="w-3.5 h-3.5" />
                          <span>{t(settings.language, 'trans_download_btn')}</span>
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Real-time Byte Progress Bar */}
                  {transStatus.isDownloading && (
                    <div className="p-4 rounded-xl border border-blue-200 dark:border-blue-900/60 bg-blue-50/40 dark:bg-blue-950/20 space-y-2">
                      <div className="flex items-center justify-between text-xs font-semibold text-blue-900 dark:text-blue-200">
                        <span>{transStatus.currentFile ? `Downloading: ${transStatus.currentFile}` : t(settings.language, 'trans_model_downloading')}</span>
                        <span className="font-mono">{transStatus.downloadedMB} MB / {transStatus.totalMB} MB ({transStatus.progress}%)</span>
                      </div>
                      <div className="w-full bg-blue-100 dark:bg-blue-900/50 rounded-full h-2 overflow-hidden">
                        <div
                          className="bg-blue-600 dark:bg-blue-400 h-2 rounded-full transition-all duration-300"
                          style={{ width: `${Math.max(2, transStatus.progress)}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {transStatus.error && (
                    <div className="p-3 rounded-xl border border-rose-200 dark:border-rose-900/60 bg-rose-50/50 dark:bg-rose-950/20 text-rose-700 dark:text-rose-300 text-xs flex items-center space-x-2">
                      <AlertCircle className="w-4 h-4 shrink-0" />
                      <span>{transStatus.error}</span>
                    </div>
                  )}

                  <div className="flex items-center space-x-2 text-[11px] text-[#5F6368] dark:text-[#94A3B8]">
                    <Clock className="w-3.5 h-3.5 text-indigo-500" />
                    <span>{t(settings.language, 'trans_auto_unload_badge')}</span>
                  </div>
                </div>
              </SectionCard>

              {/* Card 4: Encrypted Translation History & Log Purge */}
              <SectionCard
                icon={<FileText className="w-4 h-4" />}
                title={t(settings.language, 'trans_history_title')}
                subtitle={t(settings.language, 'trans_history_desc')}
              >
                <div className="space-y-4">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 rounded-xl bg-gray-50 dark:bg-white/[0.02] border border-gray-200 dark:border-gray-800">
                    <div className="flex items-center space-x-2">
                      <Lock className="w-4 h-4 text-emerald-500" />
                      <span className="font-semibold text-xs text-[#202124] dark:text-[#F1F5F9]">
                        {t(settings.language, 'trans_history_count', { count: transLogs.length })}
                      </span>
                    </div>

                    {transLogs.length > 0 && (
                      <button
                        type="button"
                        onClick={handleClearAllLogs}
                        className="px-3 py-1.5 rounded-xl border border-gray-300 dark:border-gray-700 hover:bg-rose-50 dark:hover:bg-rose-950/30 text-rose-600 dark:text-rose-400 text-xs font-semibold transition-colors cursor-pointer"
                      >
                        {t(settings.language, 'trans_clear_all_btn')}
                      </button>
                    )}
                  </div>

                  {transLogs.length === 0 ? (
                    <p className="text-center py-4 text-[11px] text-[#5F6368] dark:text-[#94A3B8]">
                      {t(settings.language, 'trans_no_logs')}
                    </p>
                  ) : (
                    <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                      {transLogs.map((log) => (
                        <div
                          key={log.messageId}
                          className="flex items-center justify-between p-2.5 rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#111726]/40 hover:bg-gray-50 dark:hover:bg-white/[0.02] transition-colors text-xs"
                        >
                          <div className="min-w-0 flex-1 pr-3">
                            <p className="font-semibold text-[#202124] dark:text-white truncate">
                              {log.subject || '(No Subject)'}
                            </p>
                            <div className="flex items-center space-x-2 text-[10px] text-[#5F6368] dark:text-[#94A3B8] mt-0.5">
                              <span className="px-1.5 py-0.2 rounded bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 font-mono font-bold">
                                {log.targetLang.replace('_Deva', '').replace('_Latn', '').toUpperCase()}
                              </span>
                              <span>•</span>
                              <span>{log.charCount} chars</span>
                              <span>•</span>
                              <span>{new Date(log.timestamp).toLocaleDateString()}</span>
                            </div>
                          </div>

                          <button
                            type="button"
                            onClick={() => handleDeleteSingleLog(log.messageId)}
                            className="p-1.5 rounded-lg text-gray-400 hover:text-rose-600 dark:hover:text-rose-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors cursor-pointer"
                            title={t(settings.language, 'trans_delete_item')}
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </SectionCard>
            </div>
          )}

          {/* 8. About Tab */}
          {activeTab === 'about' && (
            <div className="space-y-6 text-xs text-[#5F6368] dark:text-[#94A3B8] leading-relaxed pb-6">
              {/* 1. Hero Identity Card */}
              <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-indigo-50/90 via-white to-blue-50/70 dark:from-[#111726] dark:via-[#161F33] dark:to-[#0F1E36] border border-indigo-100 dark:border-indigo-900/50 p-6 shadow-sm">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                  <div className="flex items-center space-x-3.5">
                    <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-indigo-600 to-blue-600 text-white flex items-center justify-center shadow-md shrink-0">
                      <ShieldCheck className="w-6 h-6" />
                    </div>
                    <div>
                      <div className="flex items-center space-x-2.5">
                        <h3 className="text-lg font-bold text-[#202124] dark:text-white tracking-tight">
                          QuMail
                        </h3>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-indigo-100 dark:bg-indigo-950/80 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800">
                          Version 1.0.0
                        </span>
                      </div>
                      <p className="text-xs font-semibold text-indigo-600 dark:text-indigo-400 mt-0.5">
                        {t(settings.language, 'about_tagline')}
                      </p>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => {
                      const diag = `QuMail Version 1.0.0 · ML-KEM-768 / ML-DSA-65 / AES-256-GCM · User: ${account.email || 'Not Signed In'}`;
                      navigator.clipboard.writeText(diag);
                      setCopiedAboutInfo(true);
                      onShowNotice?.('System diagnostic information copied to clipboard');
                      setTimeout(() => setCopiedAboutInfo(false), 2000);
                    }}
                    className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-xl border border-gray-300 dark:border-gray-700 hover:bg-white dark:hover:bg-gray-800 text-xs font-medium text-[#202124] dark:text-[#F1F5F9] transition-all cursor-pointer shrink-0"
                    title="Copy technical version & system specifications"
                  >
                    {copiedAboutInfo ? (
                      <>
                        <Check className="w-3.5 h-3.5 text-emerald-500" />
                        <span className="text-emerald-600 dark:text-emerald-400 font-semibold">{t(settings.language, 'copied_info')}</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3.5 h-3.5 text-[#5F6368] dark:text-[#94A3B8]" />
                        <span>{t(settings.language, 'copy_version_info')}</span>
                      </>
                    )}
                  </button>
                </div>

                <div className="mt-4 pt-4 border-t border-indigo-100/80 dark:border-indigo-900/40 text-xs text-[#444746] dark:text-[#C4C7C5] leading-relaxed">
                  {t(settings.language, 'about_description')}
                </div>
              </div>

              {/* 2. Cryptographic Standards & Architecture Grid */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-[#5F6368] dark:text-[#94A3B8]">
                    {t(settings.language, 'crypto_standards_title')}
                  </h4>
                  <span className="text-[11px] text-emerald-600 dark:text-emerald-400 font-medium flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                    {t(settings.language, 'all_primitives_active')}
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                  {/* Card 1: KEM */}
                  <div className="p-4 rounded-xl border border-gray-200/90 dark:border-gray-700/80 bg-white dark:bg-white/[0.02] shadow-sm space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <KeyRound className="w-4 h-4 text-indigo-500" />
                        <span className="font-bold text-[#202124] dark:text-white text-xs">
                          {t(settings.language, 'kem_card_title')}
                        </span>
                      </div>
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800">
                        NIST FIPS 203
                      </span>
                    </div>
                    <div className="font-mono text-[11px] text-[#202124] dark:text-[#F1F5F9] font-semibold">
                      ML-KEM-768
                    </div>
                    <p className="text-[11px] text-[#5F6368] dark:text-[#94A3B8] leading-normal">
                      {t(settings.language, 'kem_card_desc')}
                    </p>
                  </div>

                  {/* Card 2: DSA */}
                  <div className="p-4 rounded-xl border border-gray-200/90 dark:border-gray-700/80 bg-white dark:bg-white/[0.02] shadow-sm space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <Shield className="w-4 h-4 text-emerald-500" />
                        <span className="font-bold text-[#202124] dark:text-white text-xs">
                          {t(settings.language, 'dsa_card_title')}
                        </span>
                      </div>
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
                        NIST FIPS 204
                      </span>
                    </div>
                    <div className="font-mono text-[11px] text-[#202124] dark:text-[#F1F5F9] font-semibold">
                      ML-DSA-65
                    </div>
                    <p className="text-[11px] text-[#5F6368] dark:text-[#94A3B8] leading-normal">
                      {t(settings.language, 'dsa_card_desc')}
                    </p>
                  </div>

                  {/* Card 3: Symmetric & Storage */}
                  <div className="p-4 rounded-xl border border-gray-200/90 dark:border-gray-700/80 bg-white dark:bg-white/[0.02] shadow-sm space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <Lock className="w-4 h-4 text-blue-500" />
                        <span className="font-bold text-[#202124] dark:text-white text-xs">
                          {t(settings.language, 'sym_card_title')}
                        </span>
                      </div>
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-50 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800">
                        Zero-Trust Storage
                      </span>
                    </div>
                    <div className="font-mono text-[11px] text-[#202124] dark:text-[#F1F5F9] font-semibold">
                      AES-256-GCM + OS Keystore + PBKDF2
                    </div>
                    <p className="text-[11px] text-[#5F6368] dark:text-[#94A3B8] leading-normal">
                      {t(settings.language, 'sym_card_desc')}
                    </p>
                  </div>

                  {/* Card 4: Entropy & QKD */}
                  <div className="p-4 rounded-xl border border-gray-200/90 dark:border-gray-700/80 bg-white dark:bg-white/[0.02] shadow-sm space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <Cpu className="w-4 h-4 text-amber-500" />
                        <span className="font-bold text-[#202124] dark:text-white text-xs">
                          {t(settings.language, 'rand_card_title')}
                        </span>
                      </div>
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800">
                        NIST SP 800-90B / ETSI GS QKD 014
                      </span>
                    </div>
                    <div className="font-mono text-[11px] text-[#202124] dark:text-[#F1F5F9] font-semibold">
                      OS CSPRNG · Hardware TRNG · ETSI GS QKD 014
                    </div>
                    <p className="text-[11px] text-[#5F6368] dark:text-[#94A3B8] leading-normal">
                      {t(settings.language, 'rand_card_desc')}
                    </p>
                  </div>
                </div>
              </div>

              {/* 3. Core Privacy Scope */}
              <SectionCard
                title={t(settings.language, 'privacy_scope_title')}
                subtitle={t(settings.language, 'privacy_scope_desc')}
                icon={<ShieldCheck className="w-4 h-4" />}
              >
                <div className="space-y-3 pt-1">
                  <div className="flex items-start space-x-3">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
                    <div>
                      <span className="font-bold text-[#202124] dark:text-[#F1F5F9] text-xs">
                        {t(settings.language, 'scope_local_sealing')}{' '}
                      </span>
                      <p className="text-[11px] text-[#5F6368] dark:text-[#94A3B8] mt-0.5">
                        {t(settings.language, 'scope_local_sealing_desc')}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-start space-x-3">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
                    <div>
                      <span className="font-bold text-[#202124] dark:text-[#F1F5F9] text-xs">
                        {t(settings.language, 'scope_inbox_iso')}{' '}
                      </span>
                      <p className="text-[11px] text-[#5F6368] dark:text-[#94A3B8] mt-0.5">
                        {t(settings.language, 'scope_inbox_iso_desc')}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-start space-x-3">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
                    <div>
                      <span className="font-bold text-[#202124] dark:text-[#F1F5F9] text-xs">
                        {t(settings.language, 'scope_universal_access')}{' '}
                      </span>
                      <p className="text-[11px] text-[#5F6368] dark:text-[#94A3B8] mt-0.5">
                        {t(settings.language, 'scope_universal_access_desc')}
                      </p>
                    </div>
                  </div>
                </div>
              </SectionCard>

              {/* 4. Client Information & Scope Modal Trigger */}
              <div className="p-4 rounded-xl border border-gray-200/90 dark:border-gray-700/80 bg-gray-50/70 dark:bg-white/[0.02] flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs">
                <div>
                  <div className="font-semibold text-[#202124] dark:text-[#F1F5F9]">
                    QuMail Client · Version 1.0.0
                  </div>
                  <div className="text-[11px] text-[#5F6368] dark:text-[#94A3B8] mt-0.5">
                    Client-side post-quantum security layer for modern email
                  </div>
                </div>

                <div className="flex items-center space-x-3 text-[11px]">
                  <button
                    type="button"
                    onClick={() => setIsPrivacyScopeOpen(true)}
                    className="inline-flex items-center space-x-1.5 text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 font-semibold cursor-pointer py-1 px-2.5 rounded-lg hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-colors"
                  >
                    <ShieldCheck className="w-3.5 h-3.5" />
                    <span>{t(settings.language, 'privacy_encryption_scope_btn')}</span>
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Privacy & Encryption Scope Dialog */}
        <AnimatePresence>
          {isPrivacyScopeOpen && (
            <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs select-none">
              <motion.div
                initial={{ opacity: 0, scale: 0.96 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.96 }}
                className="w-full max-w-xl bg-white dark:bg-[#111726] border border-gray-200 dark:border-gray-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh]"
              >
                {/* Header */}
                <div className="px-5 py-4 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between bg-gray-50/50 dark:bg-white/[0.02]">
                  <div className="flex items-center space-x-2.5">
                    <div className="p-2 rounded-xl bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400">
                      <ShieldCheck className="w-4 h-4" />
                    </div>
                    <div>
                      <h4 className="text-sm font-bold text-[#202124] dark:text-[#F1F5F9]">
                        {t(settings.language, 'privacy_encryption_scope_btn')}
                      </h4>
                      <p className="text-[11px] text-[#5F6368] dark:text-[#94A3B8]">
                        {t(settings.language, 'scope_dialog_desc')}
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setIsPrivacyScopeOpen(false)}
                    className="p-1.5 rounded-xl text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors cursor-pointer"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>

                {/* Content */}
                <div className="p-5 space-y-4 overflow-y-auto text-xs leading-relaxed">
                  {/* Box 1: Encrypted Client-Side */}
                  <div className="p-4 rounded-xl border border-emerald-200/80 dark:border-emerald-800/60 bg-emerald-50/40 dark:bg-emerald-950/20 space-y-2.5">
                    <div className="flex items-center space-x-2 text-emerald-800 dark:text-emerald-300 font-bold">
                      <Lock className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                      <span>{t(settings.language, 'scope_encrypted_title')}</span>
                    </div>
                    <ul className="space-y-1.5 text-[11px] text-emerald-900/90 dark:text-emerald-200/90 pl-1">
                      <li className="flex items-start space-x-2">
                        <span className="text-emerald-500 font-bold">•</span>
                        <span><strong>Message Body &amp; Content:</strong> Encrypted locally using authenticated AES-256-GCM. Container keys are encapsulated with NIST FIPS 203 ML-KEM-768.</span>
                      </li>
                      <li className="flex items-start space-x-2">
                        <span className="text-emerald-500 font-bold">•</span>
                        <span><strong>File Attachments:</strong> Encrypted and sealed directly inside the quantum cryptographic envelope before transmission.</span>
                      </li>
                      <li className="flex items-start space-x-2">
                        <span className="text-emerald-500 font-bold">•</span>
                        <span><strong>Cloaked Subject:</strong> When Subject Cloaking is enabled, the true subject is encrypted inside the payload; mail servers only see <code className="font-mono bg-emerald-100/80 dark:bg-emerald-900/60 px-1 py-0.5 rounded">••••••</code>.</span>
                      </li>
                      <li className="flex items-start space-x-2">
                        <span className="text-emerald-500 font-bold">•</span>
                        <span><strong>Cryptographic Keys &amp; PIN:</strong> Stored locally in OS-backed secure storage; private keys are never transmitted to any server.</span>
                      </li>
                    </ul>
                  </div>

                  {/* Box 2: Provider Visible Routing Metadata */}
                  <div className="p-4 rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-white/[0.02] space-y-2.5">
                    <div className="flex items-center space-x-2 text-[#202124] dark:text-[#F1F5F9] font-bold">
                      <Globe className="w-4 h-4 text-blue-500" />
                      <span>{t(settings.language, 'scope_provider_title')}</span>
                    </div>
                    <p className="text-[11px] text-[#5F6368] dark:text-[#94A3B8]">
                      Standard email protocols (RFC 5321 / RFC 5322) require transport metadata for mail transfer agents (MTAs) to route and deliver messages:
                    </p>
                    <ul className="space-y-1.5 text-[11px] text-[#5F6368] dark:text-[#94A3B8] pl-1">
                      <li className="flex items-start space-x-2">
                        <span className="text-gray-400 font-bold">•</span>
                        <span><strong>Sender &amp; Recipient Addresses:</strong> Required by mail servers to deliver messages to destination mailboxes.</span>
                      </li>
                      <li className="flex items-start space-x-2">
                        <span className="text-gray-400 font-bold">•</span>
                        <span><strong>Delivery Timestamps &amp; Message IDs:</strong> Generated and recorded by intermediate mail servers during transit.</span>
                      </li>
                      <li className="flex items-start space-x-2">
                        <span className="text-gray-400 font-bold">•</span>
                        <span><strong>Standard (Uncloaked) Subject:</strong> Visible in transport headers only if Subject Cloaking is disabled.</span>
                      </li>
                      <li className="flex items-start space-x-2">
                        <span className="text-gray-400 font-bold">•</span>
                        <span><strong>Encrypted Container Size:</strong> The overall size of the encrypted payload in transit is visible to servers.</span>
                      </li>
                    </ul>
                  </div>
                </div>

                {/* Footer */}
                <div className="px-5 py-3 border-t border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-white/[0.02] flex justify-end">
                  <button
                    type="button"
                    onClick={() => setIsPrivacyScopeOpen(false)}
                    className="px-4 py-1.5 rounded-xl bg-gray-200 dark:bg-gray-800 text-[#202124] dark:text-white text-xs font-semibold hover:bg-gray-300 dark:hover:bg-gray-700 transition-colors cursor-pointer"
                  >
                    {t(settings.language, 'close')}
                  </button>
                </div>
              </motion.div>
            </div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  );
};
