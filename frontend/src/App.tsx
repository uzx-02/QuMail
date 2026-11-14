import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { ShieldAlert, Lock, Undo2, X, KeyRound } from 'lucide-react';
import { MotionConfig } from 'framer-motion';
import { expiryStringToHours, resolveDisplaySubject } from './lib/privacy';
import { t } from './lib/i18n';
import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { MessageList } from './components/MessageList';
import { ReadingPane } from './components/ReadingPane';
import { ComposeModal } from './components/ComposeModal';
import { SettingsModal } from './components/SettingsModal';
import { SignInModal } from './components/SignInModal';
import { api } from './lib/api';
import { EmailMessage, HSMStatus, AccountSession, QuMailSettings, SearchFilters, DEFAULT_SEARCH_FILTERS, countActiveFilters } from './types';
import { INITIAL_ACCOUNT, INITIAL_HSM, DEFAULT_SETTINGS } from './initialState';

export const App: React.FC = () => {
  // Persisted user settings
  const [settings, setSettings] = useState<QuMailSettings>(() => {
    try {
      const saved = localStorage.getItem('qumail-settings');
      const legacyTheme = localStorage.getItem('qumail-theme');
      if (saved) {
        const parsed = JSON.parse(saved);
        return {
          ...DEFAULT_SETTINGS,
          ...(parsed.theme === undefined && legacyTheme === 'dark' ? { theme: 'midnight' as const } : {}),
          ...parsed,
          visibleFolders: {
            ...DEFAULT_SETTINGS.visibleFolders,
            ...(parsed.visibleFolders || {}),
          },
        };
      }
      if (legacyTheme === 'dark') {
        return { ...DEFAULT_SETTINGS, theme: 'midnight' };
      }
    } catch {}
    return DEFAULT_SETTINGS;
  });

  // Theme state
  const [preferredDarkTheme, setPreferredDarkTheme] = useState<'dark' | 'midnight'>(() => {
    if (settings.theme === 'dark' || settings.theme === 'midnight') {
      return settings.theme;
    }
    try {
      const savedDark = localStorage.getItem('qumail-preferred-dark-theme');
      if (savedDark === 'dark' || savedDark === 'midnight') return savedDark;
    } catch {}
    return 'midnight';
  });

  const [systemPrefersDark, setSystemPrefersDark] = useState<boolean>(() =>
    window.matchMedia('(prefers-color-scheme: dark)').matches
  );

  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = (e: MediaQueryListEvent) => setSystemPrefersDark(e.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  const effectiveTheme = settings.syncWithSystem
    ? systemPrefersDark
      ? preferredDarkTheme
      : 'light'
    : settings.theme || 'light';

  const isDarkMode = effectiveTheme !== 'light';

  // Navigation & layout state
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [currentFolder, setCurrentFolder] = useState<string>(() => settings.defaultStartupFolder || 'inbox');
  const [searchQuery, setSearchQuery] = useState('');

  // Modals state
  const [isComposeOpen, setIsComposeOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [settingsInitialTab, setSettingsInitialTab] = useState<'general' | 'labels' | 'accounts' | 'security' | 'appearance' | 'accessibility' | 'offline_translation' | 'about'>('general');
  const [isSignInOpen, setIsSignInOpen] = useState(false);
  const [unlockPin, setUnlockPin] = useState('');
  const [unlockError, setUnlockError] = useState<string | null>(null);
  const [unlockBusy, setUnlockBusy] = useState(false);
  const [unlockCooldown, setUnlockCooldown] = useState(0);

  const handleOpenSettings = useCallback(
    (tab: 'general' | 'labels' | 'accounts' | 'security' | 'appearance' | 'accessibility' | 'offline_translation' | 'about' = 'general') => {
      setSettingsInitialTab(tab);
      setIsSettingsOpen(true);
    },
    []
  );
  const [composeDefaults, setComposeDefaults] = useState<{
    draftId?: string;
    to: string;
    subject: string;
    body: string;
    securityMode?: 'pq' | 'weblink' | 'standard';
    threadId?: string;
    inReplyTo?: string;
    references?: string;
  }>({ to: '', subject: '', body: '' });

  // Network and OAuth status banners
  const [isBrowserOnline, setIsBrowserOnline] = useState<boolean>(() => navigator.onLine);
  const [dismissedOfflineBanner, setDismissedOfflineBanner] = useState<boolean>(false);
  const [dismissedOAuthBanner, setDismissedOAuthBanner] = useState<boolean>(false);

  // Data state
  const [messages, setMessages] = useState<EmailMessage[]>([]);
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null);
  const [account, setAccount] = useState<AccountSession>(INITIAL_ACCOUNT);
  const [hsmStatus, setHsmStatus] = useState<HSMStatus>(INITIAL_HSM);

  const handleUpdateSettings = useCallback((patch: Partial<QuMailSettings>) => {
    if (patch.theme === 'dark' || patch.theme === 'midnight') {
      setPreferredDarkTheme(patch.theme);
      try {
        localStorage.setItem('qumail-preferred-dark-theme', patch.theme);
      } catch {}
    }
    setSettings((prev) => {
      const next = { ...prev, ...patch };
      try {
        localStorage.setItem('qumail-settings', JSON.stringify(next));
      } catch {}
      // Mirror to Python backend disk storage
      api.saveSettings(next).catch((err) => console.warn('Failed to mirror settings to backend:', err));
      return next;
    });
    if (patch.maxPageSize && account.email) {
      api.fetchInbox(patch.maxPageSize)
        .then((msgs) => {
          if (msgs && msgs.length > 0) setMessages(msgs);
        })
        .catch((err) => console.debug('Page size sync note:', err));
    }
  }, [account.email]);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isInitialSyncing, setIsInitialSyncing] = useState(false);
  const [syncStatus, setSyncStatus] = useState<string | null>(null);
  const [backendReady, setBackendReady] = useState<boolean | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [toastNotice, setToastNotice] = useState<string | null>(null);
  const [isSessionLocked, setIsSessionLocked] = useState(false);
  const [lockAvatarError, setLockAvatarError] = useState(false);

  useEffect(() => {
    setLockAvatarError(false);
  }, [account.avatarUrl]);
  const [searchFilters, setSearchFilters] = useState<SearchFilters>(DEFAULT_SEARCH_FILTERS);
  const [pendingSend, setPendingSend] = useState<{
    payload: Partial<EmailMessage> & { draftId?: string; outboxId?: string };
    secondsLeft: number;
  } | null>(null);
  const knownMsgIdsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    knownMsgIdsRef.current = new Set(messages.map((m) => m.id));
  }, [messages]);

  // Auto-dismiss protective toast notice after 4.5 seconds
  useEffect(() => {
    if (toastNotice) {
      const timer = setTimeout(() => setToastNotice(null), 4500);
      return () => clearTimeout(timer);
    }
  }, [toastNotice]);

  // Sync theme, data-theme, data-accent, data-font, data-font-size, and accessibility attributes on <html>
  useEffect(() => {
    const root = document.documentElement;
    if (effectiveTheme === 'light') {
      root.classList.remove('dark');
      root.removeAttribute('data-theme');
      localStorage.setItem('qumail-theme', 'light');
    } else {
      root.classList.add('dark');
      root.setAttribute('data-theme', effectiveTheme);
      localStorage.setItem('qumail-theme', 'dark');
    }
    root.setAttribute('data-accent', settings.accentColor || 'blue');
    root.setAttribute('data-font', settings.fontFamily || 'sans');
    root.setAttribute('data-font-size', settings.fontSize || 'medium');
    root.setAttribute('data-font-scale', settings.fontScale || 'default');
    root.setAttribute('data-high-contrast', String(Boolean(settings.highContrast)));
    root.setAttribute('data-dyslexic-font', String(Boolean(settings.dyslexicReadingFont)));
    root.setAttribute('data-reduce-motion', String(Boolean(settings.reduceMotion)));
    root.setAttribute('data-enhanced-focus', String(Boolean(settings.enhancedFocusRings !== false)));
    root.setAttribute('data-language', settings.language || 'en');
    document.documentElement.lang = settings.language || 'en';
  }, [
    effectiveTheme,
    settings.accentColor,
    settings.fontFamily,
    settings.fontSize,
    settings.fontScale,
    settings.highContrast,
    settings.dyslexicReadingFont,
    settings.reduceMotion,
    settings.enhancedFocusRings,
    settings.language,
  ]);

  const initData = useCallback(async () => {
    setBackendReady(null);
    setBackendError(null);
    try {
      const ready = await api.waitForBackend(6000);
      if (!ready) {
        setBackendReady(false);
        setBackendError('QuMail desktop bridge did not attach within 6 seconds. Please ensure QuMail is launched via Launch-QuMail-Modern.bat.');
        return;
      }
      setBackendReady(true);

      // 1. Hydrate settings from Python backend disk backup
      try {
        const diskSettings = await api.getSettings();
        if (diskSettings && Object.keys(diskSettings).length > 0) {
          setSettings((prev) => {
            const merged = {
              ...prev,
              ...diskSettings,
              visibleFolders: {
                ...prev.visibleFolders,
                ...(diskSettings.visibleFolders || {}),
              },
            };
            try {
              localStorage.setItem('qumail-settings', JSON.stringify(merged));
            } catch {}
            return merged;
          });
        } else {
          // If backend has no settings yet, mirror initial localStorage settings to backend disk
          const currentLocal = localStorage.getItem('qumail-settings');
          if (currentLocal) {
            try {
              api.saveSettings(JSON.parse(currentLocal));
            } catch {}
          }
        }
      } catch (err) {
        console.debug('Disk settings hydration note:', err);
      }

      // 2. Fetch session status, account info, and PIN status
      const [status, acc, hsm, hasPin] = await Promise.all([
        api.getSessionStatus(),
        api.getAccount(),
        api.getHSMStatus(),
        api.hasSecurityPin(),
      ]);
      const pinActive = Boolean(hasPin || acc?.hasSecurityPin);
      const mergedAcc: AccountSession = {
        ...acc,
        hasSecurityPin: pinActive,
      };
      setAccount(mergedAcc);
      setHsmStatus(hsm);
      if (acc?.cooldownSeconds && acc.cooldownSeconds > 0) {
        setUnlockCooldown(acc.cooldownSeconds);
      }

      // Auto-fetch provider avatar in background if not yet cached
      if (acc?.email && !acc?.avatarUrl) {
        api.refreshAccountAvatar().then((res) => {
          if (res?.success && res.avatarUrl) {
            setAccount((prev) => ({ ...prev, avatarUrl: res.avatarUrl }));
          }
        }).catch(() => {});
      }

      // 3. Check if mailbox is locked or Security PIN is active on cold startup
      const isLocked =
        status?.vaultState === 'LOCKED' ||
        status?.sessionState === 'LOCKED' ||
        acc?.vaultState === 'LOCKED' ||
        acc?.sessionState === 'LOCKED' ||
        !acc?.isUnlocked ||
        pinActive;

      if (isLocked) {
        setIsSessionLocked(true);
        setIsInitialSyncing(false);
        setSelectedMessageId(null);
        setMessages([]);
        setIsComposeOpen(false);
        return;
      }

      // 4. Normal unlocked startup
      setIsSessionLocked(false);
      const msgs = await api.getMessages();
      setMessages(msgs);

      // If no email exists in session, prompt sign in
      if (!acc.email) {
        setIsSignInOpen(true);
      } else {
        // Background live inbox synchronization with visual loading state
        setSyncStatus('Checking for new messages in background...');
        setIsRefreshing(true);
        if (msgs.length === 0) {
          setIsInitialSyncing(true);
        }
        api.fetchInbox(settings.maxPageSize)
          .then((liveMsgs) => {
            if (liveMsgs && liveMsgs.length > 0) {
              setMessages(liveMsgs);
            }
          })
          .catch((err) => console.debug('Initial live inbox sync note:', err))
          .finally(() => {
            setIsRefreshing(false);
            setIsInitialSyncing(false);
            setSyncStatus(null);
          });
      }
    } catch (e: any) {
      console.error('Failed to initialize QuMail state:', e);
      setBackendReady(false);
      setBackendError(e?.message || 'Failed to initialize QuMail bridge');
    }
  }, [settings.maxPageSize]);

  // Initial load
  useEffect(() => {
    initData();
  }, [initData]);

  const handleToggleTheme = useCallback(() => {
    handleUpdateSettings({
      theme: isDarkMode ? 'light' : preferredDarkTheme,
      syncWithSystem: false,
    });
  }, [handleUpdateSettings, isDarkMode, preferredDarkTheme]);

  const handleToggleSidebar = useCallback(() => {
    setIsSidebarCollapsed((prev) => !prev);
  }, []);

  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    setSyncStatus('Synchronizing inbox with mail server...');
    try {
      const msgs = await api.fetchInbox(settings.maxPageSize);
      const [hsm, acc, avatarRes] = await Promise.all([
        api.getHSMStatus(),
        api.getAccount(),
        api.refreshAccountAvatar().catch(() => null),
      ]);
      setMessages(msgs);
      setHsmStatus(hsm);
      if (avatarRes?.success !== undefined) {
        setAccount({ ...acc, avatarUrl: avatarRes.avatarUrl || '' });
      } else {
        setAccount(acc);
      }
    } catch (e) {
      console.error('Failed to refresh data:', e);
    } finally {
      setSyncStatus(null);
      setTimeout(() => setIsRefreshing(false), 400);
    }
  }, [settings.maxPageSize]);

  // Window online/offline listeners
  useEffect(() => {
    const handleOnline = () => {
      setIsBrowserOnline(true);
      setDismissedOfflineBanner(false);
      handleRefresh();
    };
    const handleOffline = () => {
      setIsBrowserOnline(false);
      setDismissedOfflineBanner(false);
    };
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, [handleRefresh]);

  const handleSelectMessage = useCallback(async (msg: EmailMessage) => {
    if (msg.folder === 'drafts') {
      setComposeDefaults({
        draftId: msg.id,
        to: msg.recipients.join(', '),
        subject: msg.subject === '(No Subject)' ? '' : msg.subject,
        body: msg.body || '',
        securityMode: msg.securityMode || 'pq',
      });
      setIsComposeOpen(true);
      return;
    }

    setSelectedMessageId(msg.id);
    if (!msg.seen && settings.markAsReadDelay === 'immediate') {
      setMessages((prev) =>
        prev.map((m) => (m.id === msg.id ? { ...m, seen: true } : m))
      );
      api.markRead(msg.id, true).catch((err) => console.debug('Background markRead sync error:', err));
    }
  }, [settings.markAsReadDelay]);

  // Delayed auto-mark-as-read (when markAsReadDelay === '3s')
  useEffect(() => {
    if (!selectedMessageId || settings.markAsReadDelay !== '3s') return;
    const target = messages.find((m) => m.id === selectedMessageId);
    if (!target || target.seen) return;

    const timer = setTimeout(() => {
      setMessages((prev) =>
        prev.map((m) => (m.id === selectedMessageId ? { ...m, seen: true } : m))
      );
      api.markRead(selectedMessageId, true).catch((err) => console.debug('Delayed markRead sync error:', err));
    }, 3000);

    return () => clearTimeout(timer);
  }, [selectedMessageId, settings.markAsReadDelay, messages]);

  // Background auto-sync & desktop notification privacy
  useEffect(() => {
    const mins = settings.autoSyncMinutes ?? 0;
    if (mins <= 0 || !account.email || isSessionLocked || !isBrowserOnline || account.connectionStatus === 'OAUTH_EXPIRED') return;

    const intervalMs = mins * 60 * 1000;
    const timer = setInterval(async () => {
      try {
        const liveMsgs = await api.fetchInbox(settings.maxPageSize);
        if (!liveMsgs || liveMsgs.length === 0) return;

        const newArrivals = liveMsgs.filter(
          (m) => m.folder === 'inbox' && !knownMsgIdsRef.current.has(m.id)
        );
        setMessages(liveMsgs);

        if (newArrivals.length > 0 && settings.desktopNotifications !== 'off') {
          const newest = newArrivals[0];
          const senderLabel = newest.sender || newest.senderEmail || 'QuMail';
          const title =
            settings.desktopNotifications === 'full'
              ? `New message from ${senderLabel}`
              : 'New QuMail Message';
          const body =
            settings.desktopNotifications === 'full'
              ? resolveDisplaySubject(newest).displaySubject
              : `From ${senderLabel}`;

          if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
            new Notification(title, { body });
          } else {
            setToastNotice(`${title}: ${body}`);
          }
        }
      } catch (err) {
        console.debug('Background auto-sync note:', err);
      }
    }, intervalMs);

    return () => clearInterval(timer);
  }, [settings.autoSyncMinutes, settings.maxPageSize, settings.desktopNotifications, account.email, isSessionLocked]);

  const handleLockVault = useCallback(async () => {
    setIsSessionLocked(true);
    setSelectedMessageId(null);
    setMessages([]);
    setIsComposeOpen(false);
    setIsSettingsOpen(false);
    try {
      await api.lockVault();
      const hasPin = await api.hasSecurityPin();
      setAccount((prev) => ({ ...prev, isUnlocked: false, hasSecurityPin: hasPin }));
    } catch {}
  }, []);

  // Idle session auto-lock with wall-clock sleep/hibernate wake detection
  useEffect(() => {
    const mins = settings.idleLockMinutes ?? 0;
    if (mins <= 0 || !account.email || isSessionLocked) return;

    const timeoutMs = mins * 60 * 1000;
    let lastActivityTime = Date.now();
    let idleTimer: ReturnType<typeof setTimeout>;

    const lockNow = () => {
      handleLockVault();
    };

    const checkElapsed = () => {
      const elapsed = Date.now() - lastActivityTime;
      if (elapsed >= timeoutMs) {
        lockNow();
      }
    };

    const recordActivity = () => {
      lastActivityTime = Date.now();
      clearTimeout(idleTimer);
      idleTimer = setTimeout(() => {
        checkElapsed();
      }, timeoutMs);
    };

    const onWakeOrFocus = () => {
      // Check elapsed wall-clock time immediately on frame 1 of wake/focus
      checkElapsed();
    };

    const activityEvents = ['mousemove', 'keydown', 'pointerdown', 'scroll'] as const;
    activityEvents.forEach((ev) => window.addEventListener(ev, recordActivity, { passive: true }));

    // Listen to OS wake / tab visibility / window focus events
    window.addEventListener('focus', onWakeOrFocus);
    document.addEventListener('visibilitychange', onWakeOrFocus);
    window.addEventListener('pageshow', onWakeOrFocus);

    // Periodic heartbeat to catch sleep/hibernate wake even if mouse hasn't moved yet
    const heartbeat = setInterval(checkElapsed, 10_000);

    recordActivity();

    return () => {
      clearTimeout(idleTimer);
      clearInterval(heartbeat);
      activityEvents.forEach((ev) => window.removeEventListener(ev, recordActivity));
      window.removeEventListener('focus', onWakeOrFocus);
      document.removeEventListener('visibilitychange', onWakeOrFocus);
      window.removeEventListener('pageshow', onWakeOrFocus);
    };
  }, [settings.idleLockMinutes, account.email, isSessionLocked, handleLockVault]);

  // Security PIN cooldown countdown timer
  useEffect(() => {
    if (unlockCooldown <= 0) return;
    const t = setInterval(() => {
      setUnlockCooldown((prev) => (prev <= 1 ? 0 : prev - 1));
    }, 1000);
    return () => clearInterval(t);
  }, [unlockCooldown]);

  const handleUnlockSession = useCallback(async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (unlockCooldown > 0) return;
    setUnlockBusy(true);
    setUnlockError(null);
    try {
      const res = await api.unlockVault(unlockPin);
      if (res.success) {
        setUnlockPin('');
        setUnlockError(null);
        setIsSessionLocked(false);
        const [acc, hasPin] = await Promise.all([api.getAccount(), api.hasSecurityPin()]);
        setAccount({ ...acc, hasSecurityPin: Boolean(hasPin || acc.hasSecurityPin) });

        // Check if messages were already decapsulated and returned by unlockVault() or in local cache
        const initialMsgs = (res as any).messages || (await api.getMessages());
        if (initialMsgs && initialMsgs.length > 0) {
          setMessages(initialMsgs);
          setIsInitialSyncing(false);
          setIsRefreshing(false);
        } else {
          // No cached messages yet; show initial sync shimmer while network fetch runs
          setIsInitialSyncing(true);
          setIsRefreshing(true);
        }

        // Fast IMAP background sync for latest changes
        api.fetchInbox(settings.maxPageSize)
          .then((fresh) => {
            if (fresh && fresh.length > 0) {
              setMessages(fresh);
            }
          })
          .catch((err) => console.debug('Unlock inbox sync note:', err))
          .finally(() => {
            setIsInitialSyncing(false);
            setIsRefreshing(false);
          });
        setToastNotice('Mailbox unlocked and ready.');
      } else {
        const errMsg = res.error || res.message || 'Incorrect Security PIN';
        setUnlockError(errMsg);
        const cd = (res as any).cooldownSeconds || (res as any).cooldown || 0;
        if (cd > 0) {
          setUnlockCooldown(cd);
        }
        if (errMsg.toLowerCase().includes('pin')) {
          setAccount((prev) => ({ ...prev, hasSecurityPin: true }));
        }
      }
    } catch (err: any) {
      setUnlockError(err?.message || 'Failed to unlock mailbox');
    } finally {
      setUnlockBusy(false);
    }
  }, [unlockCooldown, unlockPin, settings.maxPageSize]);

  const handleToggleStar = useCallback((id: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, starred: !m.starred } : m))
    );
    api.toggleStar(id).catch((err) => console.debug('Background star sync error:', err));
  }, []);

  const handleDeleteMessage = useCallback(async (id: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    const target = messages.find((m) => m.id === id);
    const isQuMail = target
      ? Boolean(
          target.isQuMail !== undefined
            ? target.isQuMail
            : target.securityTier === 'pq_sealed' ||
              target.securityTier === 'weblink' ||
              target.securityMode === 'pq' ||
              target.securityMode === 'weblink' ||
              target.indicator?.badgeLevel === 'SECURE' ||
              target.subject?.startsWith('[QuMail Secure Link]')
        )
      : false;

    if (target && !isQuMail) {
      setToastNotice('Safe Deletion Guard: Standard legacy emails cannot be deleted by QuMail.');
      return;
    }

    const ok = await api.deleteMessage(id);
    if (!ok) {
      setToastNotice('Safe Deletion Guard: Deletion of this message was rejected.');
      return;
    }

    setMessages((prev) => prev.filter((m) => m.id !== id));
    if (selectedMessageId === id) {
      setSelectedMessageId(null);
    }
  }, [messages, selectedMessageId]);

  const handleMarkRead = useCallback((id: string, seen: boolean, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, seen } : m))
    );
    api.markRead(id, seen).catch((err) => console.debug('Background read sync error:', err));
  }, []);

  const handleOpenCompose = useCallback(() => {
    if (!account.email) {
      setIsSignInOpen(true);
      return;
    }
    const sigBody =
      settings.signatureEnabled && settings.signatureText?.trim()
        ? `\n\n--\n${settings.signatureText.trim()}`
        : '';
    setComposeDefaults({
      to: '',
      subject: '',
      body: sigBody,
      securityMode: settings.defaultSecurityMode,
    });
    setIsComposeOpen(true);
  }, [account.email, settings.defaultSecurityMode, settings.signatureEnabled, settings.signatureText]);

  const handleReply = useCallback((msg: EmailMessage, replyAll: boolean = false) => {
    const cleanSubject = (msg.subject || '')
      .replace(/^((re|fwd):\s*)+/gi, '')
      .replace(/\s*\[(Shield|Shielded|Quantum-Safe|QuMail Secure Link|Encrypted)\]\s*/gi, ' ')
      .trim();
    const replySubject = `Re: ${cleanSubject || '(No Subject)'}`;

    // Preserve encryption mode
    let inheritedMode: 'pq' | 'weblink' | 'standard' = settings.defaultSecurityMode || 'pq';
    if (msg.securityMode === 'pq' || msg.securityTier === 'pq_sealed') {
      inheritedMode = 'pq';
    } else if (msg.securityMode === 'weblink' || msg.securityTier === 'weblink' || msg.subject?.startsWith('[QuMail Secure Link]')) {
      inheritedMode = 'weblink';
    }

    // Determine recipients
    let recipientsList: string[] = [];
    if (replyAll) {
      const allRecipients = [msg.senderEmail, ...(msg.recipients || [])];
      const selfEmail = account.email?.toLowerCase();
      const unique = Array.from(new Set(allRecipients.map((r) => r?.trim()).filter(Boolean)));
      recipientsList = unique.filter((r) => r.toLowerCase() !== selfEmail);
      if (recipientsList.length === 0 && msg.senderEmail) {
        recipientsList = [msg.senderEmail];
      }
    } else {
      recipientsList = [msg.senderEmail || ''];
    }

    const threadId = msg.threadId || msg.messageId || msg.id;
    const inReplyTo = msg.messageId || msg.id;
    const references = msg.references ? `${msg.references} ${msg.messageId || msg.id}` : (msg.messageId || msg.id);

    const sigBody =
      settings.signatureEnabled && settings.signatureText?.trim()
        ? `\n\n--\n${settings.signatureText.trim()}`
        : '';

    setComposeDefaults({
      to: recipientsList.join(', '),
      subject: replySubject,
      body: `${sigBody}\n\nOn ${msg.date}, ${msg.sender} <${msg.senderEmail}> wrote:\n> ${(msg.body || '').split('\n').join('\n> ')}`,
      securityMode: inheritedMode,
      threadId,
      inReplyTo,
      references,
    });
    setIsComposeOpen(true);
  }, [account.email, settings.defaultSecurityMode, settings.signatureEnabled, settings.signatureText]);

  const handleForward = useCallback((msg: EmailMessage) => {
    const cleanSubject = (msg.subject || '')
      .replace(/^((re|fwd):\s*)+/gi, '')
      .replace(/\s*\[(Shield|Shielded|Quantum-Safe|QuMail Secure Link|Encrypted)\]\s*/gi, ' ')
      .trim();
    const fwdSubject = `Fwd: ${cleanSubject || '(No Subject)'}`;

    let inheritedMode: 'pq' | 'weblink' | 'standard' = settings.defaultSecurityMode || 'pq';
    if (msg.securityMode === 'pq' || msg.securityTier === 'pq_sealed') {
      inheritedMode = 'pq';
    } else if (msg.securityMode === 'weblink' || msg.securityTier === 'weblink' || msg.subject?.startsWith('[QuMail Secure Link]')) {
      inheritedMode = 'weblink';
    }

    const threadId = msg.threadId || msg.id;
    const inReplyTo = msg.messageId || msg.id;
    const references = msg.references ? `${msg.references} ${msg.messageId || msg.id}` : (msg.messageId || msg.id);

    const sigBody =
      settings.signatureEnabled && settings.signatureText?.trim()
        ? `\n\n--\n${settings.signatureText.trim()}`
        : '';

    setComposeDefaults({
      to: '',
      subject: fwdSubject,
      body: `${sigBody}\n\n---------- Forwarded message ---------\nFrom: ${msg.sender} <${msg.senderEmail}>\nDate: ${msg.date}\nSubject: ${msg.subject}\nTo: ${(msg.recipients || []).join(', ')}\n\n${msg.body || ''}`,
      securityMode: inheritedMode,
      threadId,
      inReplyTo,
      references,
    });
    setIsComposeOpen(true);
  }, [settings.defaultSecurityMode, settings.signatureEnabled, settings.signatureText]);

  const executeSendNow = useCallback(
    async (draft: Partial<EmailMessage> & { draftId?: string; outboxId?: string }) => {
      const res: any = await api.sendMessage(draft);
      if (!res.success) {
        if (res.queuedInOutbox) {
          const updated = await api.getMessages();
          setMessages(updated);
          setToastNotice(res.message || 'SMTP dispatch failed. Message queued in Outbox for retry.');
          return true;
        }
        if (res.code === 'UNREGISTERED_RECIPIENTS') {
          return res;
        }
        alert(res.message || 'Failed to dispatch email.');
        return false;
      }
      const updated = await api.getMessages();
      setMessages(updated);
      // Show a contextual success toast once the operation has genuinely succeeded.
      const secMode = (draft as any).securityMode || 'standard';
      if (res.dispatched === false) {
        // Sealed and recorded locally but no SMTP transport — sitting in outbox
        setToastNotice(res.message || 'Message sealed and queued in Outbox (no SMTP transport configured).');
      } else if (secMode === 'pq') {
        setToastNotice('Quantum Private Mail dispatched and sealed successfully.');
      } else if (secMode === 'weblink') {
        setToastNotice('Secure Web Link sent successfully.');
      } else {
        setToastNotice('Message sent successfully.');
      }
      return true;
    },
    [setToastNotice]
  );

  // Undo Send countdown effect
  useEffect(() => {
    if (!pendingSend) return;
    if (pendingSend.secondsLeft <= 0) {
      const payload = pendingSend.payload;
      setPendingSend(null);
      executeSendNow(payload);
      return;
    }
    const timer = setTimeout(() => {
      setPendingSend((prev) =>
        prev ? { ...prev, secondsLeft: prev.secondsLeft - 1 } : null
      );
    }, 1000);
    return () => clearTimeout(timer);
  }, [pendingSend, executeSendNow]);

  const handleUndoSend = useCallback(() => {
    if (!pendingSend) return;
    const payload = pendingSend.payload;
    setPendingSend(null);
    const resolved = resolveDisplaySubject({
      subject: payload.subject,
      body: payload.body,
    });
    setComposeDefaults({
      draftId: payload.draftId,
      to: (payload.recipients || []).join(', '),
      subject: resolved.displaySubject === '(No Subject)' ? '' : resolved.displaySubject,
      body: resolved.cleanBody,
      securityMode: payload.securityMode || settings.defaultSecurityMode,
    });
    setIsComposeOpen(true);
  }, [pendingSend, settings.defaultSecurityMode]);

  const handleSend = useCallback(
    async (draft: Partial<EmailMessage> & { draftId?: string; outboxId?: string }) => {
      const delay = settings.undoSendSeconds ?? 0;
      if (delay > 0) {
        setPendingSend({ payload: draft, secondsLeft: delay });
        return true;
      }
      return executeSendNow(draft);
    },
    [settings.undoSendSeconds, executeSendNow]
  );

  const handleSaveDraft = useCallback(async (draft: Partial<EmailMessage>) => {
    const res = await api.saveDraft(draft);
    if (res.success) {
      const updated = await api.getMessages();
      setMessages(updated);
      return res.id;
    }
  }, []);

  const handleDiscardDraft = useCallback(async (draftId: string) => {
    await api.deleteMessage(draftId);
    setMessages((prev) => prev.filter((m) => m.id !== draftId));
  }, []);

  const handleRetrySend = useCallback(async (msg: EmailMessage, e: React.MouseEvent) => {
    e.stopPropagation();
    setToastNotice('Retrying SMTP dispatch from Outbox...');
    const res: any = await api.sendMessage({
      outboxId: msg.id,
      recipients: msg.recipients,
      subject: msg.subject,
      body: msg.body,
      attachments: msg.attachments,
      securityMode: msg.securityMode || 'pq',
      requireEmailOtp: msg.requireEmailOtp ?? true,
    });
    const updated = await api.getMessages();
    setMessages(updated);
    if (res.success) {
      setToastNotice('Outbox message dispatched successfully.');
    } else {
      setToastNotice(res.message || 'Retry failed. Message remains in Outbox.');
    }
  }, []);

  const handleSignIn = useCallback(async (email: string, displayName?: string, org?: string) => {
    setIsRefreshing(true);
    setSyncStatus(`Connected as ${email}. Initializing post-quantum mailbox...`);
    try {
      const acc = await api.loginAccount(email, displayName, org);
      setAccount(acc);
      setSyncStatus('Fetching real messages from mail server...');
      const msgs = await api.fetchInbox();
      setMessages(msgs);
    } catch (err: any) {
      console.warn('Sign in inbox sync note:', err);
    } finally {
      setIsRefreshing(false);
      setSyncStatus(null);
    }
  }, []);

  const handleLogout = useCallback(async () => {
    // Close compose modal and clear draft before switching accounts
    setIsComposeOpen(false);
    setComposeDefaults({ to: '', subject: '', body: '' });
    setMessages([]);
    setSelectedMessageId(null);
    await api.logoutAccount();
    setAccount(INITIAL_ACCOUNT);
    setIsSignInOpen(true);
  }, []);

  const handleUpdateAccountEmail = useCallback(async (email: string) => {
    setSelectedMessageId(null);
    setCurrentFolder('inbox');
    setMessages([]);
    await api.updateAccountEmail(email);
    try {
      const fullAcc = await api.getAccount();
      setAccount(fullAcc);
      if (fullAcc.email && !fullAcc.avatarUrl) {
        api.refreshAccountAvatar().then((res) => {
          if (res?.success && res.avatarUrl) {
            setAccount((prev) => ({ ...prev, avatarUrl: res.avatarUrl }));
          }
        }).catch(() => {});
      }
    } catch {
      setAccount((prev) => ({ ...prev, email }));
    }
    const msgs = await api.fetchInbox();
    setMessages(msgs);
  }, []);

  // Helper to distinguish QuMail-protected emails from standard TLS
  const isQuMailMessage = useCallback((m: EmailMessage): boolean => {
    if (m.isQuMail !== undefined) return Boolean(m.isQuMail);
    return Boolean(
      m.securityTier === 'pq_sealed' ||
      m.securityTier === 'weblink' ||
      m.securityMode === 'pq' ||
      m.securityMode === 'weblink' ||
      m.indicator?.badgeLevel === 'SECURE' ||
      m.subject?.startsWith('[QuMail Secure Link]')
    );
  }, []);

  // Filter messages according to folder, text search and advanced filters
  const displayedMessages = useMemo(() => {
    let result = messages;
    const currentMyEmail = (account.email || '').trim().toLowerCase();

    // Folder filtering with strict account isolation for Sent and Outbox
    if (currentFolder === 'starred') {
      result = result.filter((m) => m.starred && m.folder !== 'trash');
    } else if (currentFolder === 'trash') {
      result = result.filter((m) => m.folder === 'trash');
    } else if (currentFolder === 'sent') {
      result = result.filter(
        (m) =>
          m.folder === 'sent' &&
          (!currentMyEmail || !m.senderEmail || m.senderEmail.trim().toLowerCase() === currentMyEmail)
      );
    } else if (currentFolder === 'outbox') {
      result = result.filter(
        (m) =>
          m.folder === 'outbox' &&
          (!currentMyEmail || !m.senderEmail || m.senderEmail.trim().toLowerCase() === currentMyEmail)
      );
    } else {
      result = result.filter((m) => m.folder === currentFolder);
    }

    // Text query filtering
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      result = result.filter(
        (m) =>
          m.subject.toLowerCase().includes(q) ||
          m.body.toLowerCase().includes(q) ||
          m.sender.toLowerCase().includes(q) ||
          m.senderEmail.toLowerCase().includes(q) ||
          m.recipients.some((r) => r.toLowerCase().includes(q))
      );
    }

    // Advanced Search Filters
    if (searchFilters.securityMode !== 'all') {
      if (searchFilters.securityMode === 'pq') {
        result = result.filter(
          (m) =>
            m.securityMode === 'pq' ||
            m.securityTier === 'pq_sealed' ||
            (isQuMailMessage(m) &&
              m.securityTier !== 'weblink' &&
              m.securityMode !== 'weblink' &&
              !m.subject?.startsWith('[QuMail Secure Link]'))
        );
      } else if (searchFilters.securityMode === 'weblink') {
        result = result.filter(
          (m) =>
            m.securityTier === 'weblink' ||
            m.securityMode === 'weblink' ||
            Boolean(m.subject?.startsWith('[QuMail Secure Link]'))
        );
      } else if (searchFilters.securityMode === 'standard') {
        result = result.filter(
          (m) =>
            !isQuMailMessage(m) &&
            m.securityMode !== 'pq' &&
            m.securityMode !== 'weblink' &&
            m.securityTier !== 'pq_sealed' &&
            m.securityTier !== 'weblink' &&
            !m.subject?.startsWith('[QuMail Secure Link]')
        );
      }
    }

    if (searchFilters.from.trim()) {
      const f = searchFilters.from.toLowerCase().trim();
      result = result.filter(
        (m) =>
          (m.sender && m.sender.toLowerCase().includes(f)) ||
          (m.senderEmail && m.senderEmail.toLowerCase().includes(f))
      );
    }

    if (searchFilters.to.trim()) {
      const t = searchFilters.to.toLowerCase().trim();
      result = result.filter(
        (m) =>
          Array.isArray(m.recipients) &&
          m.recipients.some((r) => typeof r === 'string' && r.toLowerCase().includes(t))
      );
    }

    if (searchFilters.subjectKeywords.trim()) {
      const k = searchFilters.subjectKeywords.toLowerCase().trim();
      result = result.filter(
        (m) =>
          (m.subject && m.subject.toLowerCase().includes(k)) ||
          (m.body && m.body.toLowerCase().includes(k)) ||
          (m.snippet && m.snippet.toLowerCase().includes(k))
      );
    }

    if (searchFilters.hasAttachment) {
      result = result.filter(
        (m) => Boolean(m.hasAttachments) || Boolean(m.attachments && m.attachments.length > 0)
      );
    }

    if (searchFilters.unreadOnly) {
      result = result.filter((m) => !m.seen);
    }

    if (searchFilters.starredOnly) {
      result = result.filter((m) => Boolean(m.starred));
    }

    if (searchFilters.cloakedOnly) {
      result = result.filter((m) => {
        const { isCloaked } = resolveDisplaySubject(m);
        return isCloaked;
      });
    }

    if (searchFilters.dateRange !== 'all') {
      const now = Date.now();
      const cutoff =
        searchFilters.dateRange === '24h'
          ? 24 * 3600 * 1000
          : searchFilters.dateRange === '7d'
          ? 7 * 24 * 3600 * 1000
          : 30 * 24 * 3600 * 1000;
      result = result.filter((m) => {
        const t = m.timestamp || (m.date ? Date.parse(m.date) : 0);
        return t > 0 ? now - t <= cutoff : false;
      });
    }

    return result;
  }, [messages, currentFolder, searchQuery, searchFilters, isQuMailMessage, account.email]);

  // Selected message details
  const selectedMessage = useMemo(() => {
    if (!selectedMessageId) return null;
    return messages.find((m) => m.id === selectedMessageId) || null;
  }, [messages, selectedMessageId]);

  // Keyboard Shortcuts & Lock-Screen / DevTools Hardening
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      // 1. Strict Lock-Screen Isolation: block all global shortcuts when session is locked
      if (isSessionLocked) {
        return;
      }

      // 2. Escape: Close active modals, popovers, or deselect message
      if (e.key === 'Escape') {
        if (isComposeOpen) {
          setIsComposeOpen(false);
          return;
        }
        if (isSettingsOpen) {
          setIsSettingsOpen(false);
          return;
        }
        if (isSignInOpen && account.email) {
          setIsSignInOpen(false);
          return;
        }
        if (selectedMessageId) {
          setSelectedMessageId(null);
          return;
        }
      }

      // 3. Ctrl+L: Immediately Lock Mailbox
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'l') {
        e.preventDefault();
        handleLockVault();
        return;
      }

      // 4. Ctrl+R / F5: Trigger Inbox Sync
      if (((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'r') || e.key === 'F5') {
        e.preventDefault();
        handleRefresh();
        return;
      }

      // Target check: do not trigger single-key shortcuts when typing in inputs/textareas
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName?.toLowerCase();
      const isInputActive =
        tag === 'input' || tag === 'textarea' || tag === 'select' || target?.isContentEditable;

      // 5. Ctrl+F or /: Focus Search bar
      if (
        ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') ||
        (!isInputActive && e.key === '/')
      ) {
        e.preventDefault();
        const searchInput = document.getElementById('qumail-search-input') as HTMLInputElement | null;
        if (searchInput) {
          searchInput.focus();
          searchInput.select();
        }
        return;
      }

      // 6. Ctrl+N: Open Compose window
      if (
        (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'n'
      ) {
        if (!isComposeOpen && !isSettingsOpen && !isSignInOpen) {
          e.preventDefault();
          handleOpenCompose();
          return;
        }
      }

      // If typing inside an input or modal is open, suppress single-key navigation
      if (isInputActive || isComposeOpen || isSettingsOpen || isSignInOpen) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;

      // Gate single-key navigation behind user accessibility setting
      if (settings.singleKeyShortcuts === false) return;

      const key = e.key.toLowerCase();
      if (key === 'j' || key === 'k') {
        if (displayedMessages.length === 0) return;
        e.preventDefault();
        const idx = selectedMessageId
          ? displayedMessages.findIndex((m) => m.id === selectedMessageId)
          : -1;
        const nextIdx =
          key === 'j'
            ? Math.min(idx + 1, displayedMessages.length - 1)
            : Math.max(idx <= 0 ? 0 : idx - 1, 0);
        const nextMsg = displayedMessages[nextIdx];
        if (nextMsg) handleSelectMessage(nextMsg);
      } else if (key === 's' && selectedMessage) {
        e.preventDefault();
        handleToggleStar(selectedMessage.id);
      } else if (key === 'u' && selectedMessage) {
        e.preventDefault();
        handleMarkRead(selectedMessage.id, !selectedMessage.seen);
      } else if ((e.key === 'Delete' || e.key === 'Backspace') && selectedMessage) {
        e.preventDefault();
        handleDeleteMessage(selectedMessage.id);
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [
    isSessionLocked,
    isComposeOpen,
    isSettingsOpen,
    isSignInOpen,
    account.email,
    displayedMessages,
    selectedMessageId,
    selectedMessage,
    handleOpenCompose,
    handleRefresh,
    handleLockVault,
    handleSelectMessage,
    handleToggleStar,
    handleMarkRead,
    handleDeleteMessage,
    settings.singleKeyShortcuts,
  ]);

  // Badge counts
  const unreadCount = useMemo(
    () => messages.filter((m) => m.folder === 'inbox' && !m.seen).length,
    [messages]
  );
  const starredCount = useMemo(
    () => messages.filter((m) => m.starred && m.folder !== 'trash').length,
    [messages]
  );
  const draftsCount = useMemo(
    () => messages.filter((m) => m.folder === 'drafts').length,
    [messages]
  );
  const outboxCount = useMemo(
    () =>
      messages.filter(
        (m) =>
          m.folder === 'outbox' &&
          (!account.email || !m.senderEmail || m.senderEmail.toLowerCase() === account.email.toLowerCase())
      ).length,
    [messages, account.email]
  );

  // Recipient autocomplete suggestions derived from user's active contacts & messages
  const knownContacts = useMemo(() => {
    const map = new Map<string, string>();
    for (const m of messages) {
      if (m.senderEmail && m.senderEmail.includes('@') && m.senderEmail.toLowerCase() !== account.email.toLowerCase()) {
        const emailLower = m.senderEmail.trim().toLowerCase();
        if (!map.has(emailLower)) {
          map.set(emailLower, m.sender && m.sender !== m.senderEmail ? m.sender : '');
        }
      }
      if (Array.isArray(m.recipients)) {
        for (const r of m.recipients) {
          if (r && r.includes('@') && r.toLowerCase() !== account.email.toLowerCase()) {
            const emailLower = r.trim().toLowerCase();
            if (!map.has(emailLower)) {
              map.set(emailLower, '');
            }
          }
        }
      }
    }
    return Array.from(map.entries()).map(([email, name]) => ({ email, name }));
  }, [messages, account.email]);

  return (
    <MotionConfig reducedMotion={settings.reduceMotion ? 'always' : 'user'}>
      <div className="flex flex-col h-screen w-screen overflow-hidden bg-[#F6F8FC] dark:bg-[#0A0E17] text-[#202124] dark:text-[#F1F5F9]">
        {/* Background Application Workspace - inert when mailbox session is locked */}
        <div
          className="flex flex-col flex-1 overflow-hidden"
          inert={isSessionLocked ? true : undefined}
        >
          {/* 1. Gmail Header */}
          <Header
          onToggleSidebar={handleToggleSidebar}
          onOpenSettings={handleOpenSettings}
          onOpenSignIn={() => setIsSignInOpen(true)}
          isDarkMode={isDarkMode}
          onToggleTheme={handleToggleTheme}
          hsmStatus={hsmStatus}
          account={account}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          searchFilters={searchFilters}
          onApplySearchFilters={setSearchFilters}
          onClearSearchFilters={() => setSearchFilters(DEFAULT_SEARCH_FILTERS)}
          showIconLabels={settings.showIconLabels}
          language={settings.language}
          onUpdateLanguage={(lang) => {
            handleUpdateSettings({ language: lang });
            const toastKey = `lang_changed_${lang}` as const;
            setToastNotice(t(lang, toastKey));
          }}
        />

      {/* Bridge Readiness Alert Banners */}
      {backendReady === null && (
        <div className="h-9 bg-blue-500/10 dark:bg-blue-900/30 border-b border-blue-500/20 px-4 flex items-center justify-between text-xs text-blue-600 dark:text-blue-300 select-none">
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 rounded-full bg-blue-500 animate-ping" />
            <span className="font-medium">Connecting to QuMail Desktop Service (Edge WebView2 IPC Handshake)...</span>
          </div>
        </div>
      )}
      {backendReady === false && (
        <div className="h-10 bg-rose-500/15 border-b border-rose-500/30 px-4 flex items-center justify-between text-xs text-rose-700 dark:text-rose-300">
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 rounded-full bg-rose-500" />
            <span className="font-semibold">{backendError || 'Desktop bridge connection unavailable.'}</span>
          </div>
          <button
            onClick={initData}
            className="px-3 py-1 bg-rose-600 text-white rounded-md text-[11px] font-bold hover:bg-rose-700 transition-colors cursor-pointer"
          >
            Retry Connection
          </button>
        </div>
      )}

      {/* Offline Mode Banner */}
      {(!isBrowserOnline || account.connectionStatus === 'OFFLINE') && !dismissedOfflineBanner && (
        <div className="h-10 bg-amber-500/15 border-b border-amber-500/30 px-4 flex items-center justify-between text-xs text-amber-800 dark:text-amber-200 select-none animate-in fade-in duration-200">
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
            <span className="font-semibold">
              {t(settings.language, 'offline_banner')}
            </span>
          </div>
          <div className="flex items-center space-x-2">
            <button
              onClick={handleRefresh}
              className="px-3 py-1 bg-amber-600 hover:bg-amber-700 text-white rounded-md text-[11px] font-bold transition-colors cursor-pointer"
            >
              Retry Connection
            </button>
            <button
              onClick={() => setDismissedOfflineBanner(true)}
              className="p-1 text-amber-700 dark:text-amber-300 hover:bg-amber-500/20 rounded cursor-pointer"
              title="Dismiss banner"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

      {/* Expired Google OAuth Banner */}
      {account.connectionStatus === 'OAUTH_EXPIRED' && !dismissedOAuthBanner && (
        <div className="h-10 bg-rose-500/15 border-b border-rose-500/30 px-4 flex items-center justify-between text-xs text-rose-700 dark:text-rose-200 select-none animate-in fade-in duration-200">
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse" />
            <span className="font-semibold">
              Google session expired — reconnect your account to sync and send.
            </span>
          </div>
          <div className="flex items-center space-x-2">
            <button
              onClick={async () => {
                const res = await api.signInWithGoogle();
                if (res.success) {
                  const updatedAcc = await api.getAccount();
                  setAccount(updatedAcc);
                  setDismissedOAuthBanner(false);
                  handleRefresh();
                } else if (res.message) {
                  setToastNotice(res.message);
                }
              }}
              className="px-3 py-1 bg-rose-600 hover:bg-rose-700 text-white rounded-md text-[11px] font-bold transition-colors cursor-pointer"
            >
              Reconnect Google
            </button>
            <button
              onClick={() => setDismissedOAuthBanner(true)}
              className="p-1 text-rose-700 dark:text-rose-300 hover:bg-rose-500/20 rounded cursor-pointer"
              title="Dismiss banner"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

      {/* Background Inbox Synchronization Banner */}
      {syncStatus && (
        <div className="h-8 bg-emerald-500/10 dark:bg-emerald-950/40 border-b border-emerald-500/20 px-4 flex items-center justify-between text-xs text-emerald-700 dark:text-emerald-300 select-none animate-in fade-in duration-200">
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping" />
            <span className="font-medium">{syncStatus}</span>
          </div>
        </div>
      )}

      {/* 2. Main Workspace Layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Collapsible Sidebar */}
        <Sidebar
          currentFolder={currentFolder}
          onSelectFolder={(folder) => {
            setCurrentFolder(folder);
            setSelectedMessageId(null);
          }}
          onOpenCompose={handleOpenCompose}
          unreadCount={unreadCount}
          starredCount={starredCount}
          draftsCount={draftsCount}
          outboxCount={outboxCount}
          isCollapsed={isSidebarCollapsed}
          hsmStatus={hsmStatus}
          onOpenSettings={handleOpenSettings}
          visibleFolders={settings.visibleFolders}
          hideEmptyFolders={settings.hideEmptyFolders}
          showUnreadBadges={settings.showUnreadBadges}
          language={settings.language}
        />

        {/* Center / Right Content Pane */}
        <main className="flex-1 flex overflow-hidden">
          {selectedMessage ? (
            /* Reading View with back arrow & actions */
            <ReadingPane
              message={selectedMessage}
              userEmail={account.email}
              userAvatarUrl={account.avatarUrl}
              onReply={handleReply}
              onForward={handleForward}
              onDelete={handleDeleteMessage}
              onToggleStar={handleToggleStar}
              onClose={() => setSelectedMessageId(null)}
              onShowProtectionNotice={setToastNotice}
              blockRemoteImages={settings.blockRemoteImages}
              confirmExternalLinks={settings.confirmExternalLinks}
              fontFamily={settings.fontFamily}
              fontSize={settings.fontSize}
              showIconLabels={settings.showIconLabels}
              language={settings.language}
              enableOfflineTranslation={settings.enableOfflineTranslation}
              allowStandardMailTranslation={settings.allowStandardMailTranslation}
              onOpenSettings={handleOpenSettings}
            />
          ) : (
            /* Gmail Message List */
            <MessageList
              messages={displayedMessages}
              selectedMessageId={selectedMessageId}
              userEmail={account.email}
              userAvatarUrl={account.avatarUrl}
              onSelectMessage={handleSelectMessage}
              onToggleStar={handleToggleStar}
              onRefresh={handleRefresh}
              onDeleteMessage={handleDeleteMessage}
              onMarkRead={handleMarkRead}
              isRefreshing={isRefreshing}
              isInitialSyncing={isInitialSyncing}
              currentFolder={currentFolder}
              onRetrySend={handleRetrySend}
              filterMode={settings.defaultInboxFilter}
              maskEncryptedSnippets={settings.maskEncryptedSnippets}
              listDensity={settings.listDensity}
              showSenderAvatars={settings.showSenderAvatars}
              pageSize={settings.maxPageSize}
              onShowProtectionNotice={setToastNotice}
              hasActiveFilters={countActiveFilters(searchFilters) > 0}
              onClearFilters={() => setSearchFilters(DEFAULT_SEARCH_FILTERS)}
              showIconLabels={settings.showIconLabels}
              language={settings.language}
            />
          )}
        </main>
      </div>

      {/* Undo Send Countdown Toast (Centered at bottom, cleanly above System Randomness) */}
      {pendingSend && (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 z-50 px-5 py-3 rounded-2xl bg-[#0F172A]/95 text-white text-xs font-semibold shadow-2xl flex items-center space-x-3 border border-slate-700/80 shadow-sky-950/50 backdrop-blur-xl animate-in fade-in slide-in-from-bottom-3 duration-200 select-none">
          <div className="w-2 h-2 rounded-full bg-amber-400 animate-ping" />
          <span>{t(settings.language, 'undo_countdown', { seconds: pendingSend.secondsLeft })}</span>
          <button
            type="button"
            onClick={handleUndoSend}
            className="inline-flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl qumail-accent-bg text-white font-bold cursor-pointer hover:opacity-95 shadow-md active:scale-95 transition-all"
          >
            <Undo2 className="w-3.5 h-3.5" />
            <span>{t(settings.language, 'undo')}</span>
          </button>
        </div>
      )}
      </div>

      {/* Mailbox / Session Lock Screen */}
      {isSessionLocked && (
        <div className="fixed inset-0 z-[100] bg-slate-950/85 backdrop-blur-md flex flex-col items-center justify-center p-6 text-center select-none animate-in fade-in duration-200">
          <div className="w-full max-w-sm rounded-3xl bg-white/10 dark:bg-[#161F33]/90 border border-white/20 dark:border-[#2A3B5F] p-8 shadow-2xl backdrop-blur-xl flex flex-col items-center">
            <div className="relative mb-3">
              {account.avatarUrl && !lockAvatarError ? (
                <div className="relative">
                  <img
                    src={account.avatarUrl}
                    alt={account.displayName || account.email}
                    referrerPolicy="no-referrer"
                    crossOrigin="anonymous"
                    className="w-16 h-16 rounded-2xl object-cover border-2 border-sky-400/40 shadow-xl"
                    onError={() => setLockAvatarError(true)}
                  />
                  <div className="absolute -bottom-1 -right-1 w-6 h-6 rounded-lg bg-slate-900 border border-sky-400/40 flex items-center justify-center text-sky-400 shadow-md">
                    <Lock className="w-3.5 h-3.5" />
                  </div>
                </div>
              ) : (
                <div className="w-14 h-14 rounded-2xl qumail-accent-soft qumail-accent-text flex items-center justify-center border border-white/10 shadow-inner">
                  <Lock className="w-7 h-7" />
                </div>
              )}
            </div>
            <h2 className="text-xl font-bold text-white mb-1">{t(settings.language, 'mailbox_locked')}</h2>
            {account.email && (
              <div className="mb-4">
                <div className="text-sm font-semibold text-slate-100">
                  {account.displayName && account.displayName !== account.email.split('@')[0]
                    ? account.displayName
                    : account.email}
                </div>
                {account.displayName && account.displayName !== account.email && account.displayName !== account.email.split('@')[0] && (
                  <div className="text-xs text-slate-400 font-mono mt-0.5">
                    {account.email}
                  </div>
                )}
              </div>
            )}
            <p className="text-xs text-slate-300 dark:text-slate-400 mb-6 leading-relaxed">
              {account.hasSecurityPin
                ? t(settings.language, 'enter_pin_prompt')
                : 'QuMail has cleared decrypted message views and locked your keys to protect your privacy.'}
            </p>

            <form onSubmit={handleUnlockSession} className="w-full space-y-4">
              {account.hasSecurityPin ? (
                <div className="space-y-2 text-left">
                  <label className="text-xs font-semibold text-slate-300 block">
                    {t(settings.language, 'security_pin')} (4–8 digits)
                  </label>
                  <div className="relative">
                    <input
                      type="password"
                      inputMode="numeric"
                      pattern="[0-9]*"
                      maxLength={8}
                      autoFocus
                      disabled={unlockBusy || unlockCooldown > 0}
                      value={unlockPin}
                      onChange={(e) => {
                        const val = e.target.value.replace(/\D/g, '');
                        setUnlockPin(val);
                        if (unlockError) setUnlockError(null);
                      }}
                      placeholder="••••••••"
                      className="w-full text-center text-2xl tracking-[0.4em] py-3 px-4 rounded-xl bg-black/40 border border-white/20 text-white placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-[#0B57D0] focus:border-transparent transition-all disabled:opacity-50"
                    />
                  </div>
                </div>
              ) : null}

              {/* Status and Error Alerts always rendered if active */}
              {unlockError && (
                <div className="p-2.5 rounded-xl bg-rose-500/20 border border-rose-500/40 text-xs text-rose-300 font-semibold animate-in fade-in">
                  {unlockError}
                </div>
              )}
              {unlockCooldown > 0 && (
                <div className="p-2.5 rounded-xl bg-amber-500/20 border border-amber-500/40 text-xs text-amber-300 font-semibold animate-in fade-in">
                  Too many failed attempts. Cooldown active: {unlockCooldown}s
                </div>
              )}

              <button
                type="submit"
                disabled={unlockBusy || unlockCooldown > 0 || (Boolean(account.hasSecurityPin) && unlockPin.length < 4)}
                className="w-full py-3 rounded-xl qumail-accent-bg text-white text-sm font-bold shadow-lg hover:opacity-95 transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center space-x-2"
              >
                <KeyRound className="w-4 h-4" />
                <span>
                  {unlockBusy
                    ? t(settings.language, 'unlocking')
                    : unlockCooldown > 0
                    ? `Cooldown (${unlockCooldown}s)`
                    : t(settings.language, 'unlock_button')}
                </span>
              </button>
            </form>

            {!account.hasSecurityPin && (
              <button
                type="button"
                onClick={() => {
                  handleOpenSettings('security');
                }}
                className="text-xs text-blue-400 hover:text-blue-300 hover:underline mt-5 transition-colors cursor-pointer"
              >
                Set up a Security PIN in Settings → Security & Hardware
              </button>
            )}
          </div>
        </div>
      )}

      {/* Floating Gmail Compose Modal - unmounted when mailbox locked */}
      {!isSessionLocked && (
        <ComposeModal
          isOpen={isComposeOpen}
          onClose={() => setIsComposeOpen(false)}
          onSend={handleSend}
          onSaveDraft={handleSaveDraft}
          onDiscardDraft={handleDiscardDraft}
          initialDraftId={composeDefaults.draftId}
          initialThreadId={composeDefaults.threadId}
          initialInReplyTo={composeDefaults.inReplyTo}
          initialReferences={composeDefaults.references}
          initialTo={composeDefaults.to}
          initialSubject={composeDefaults.subject}
          initialBody={composeDefaults.body}
          initialSecurityMode={composeDefaults.securityMode || settings.defaultSecurityMode}
          defaultRequireEmailOtp={settings.weblinkRequireOtp}
          defaultBurnAfterRead={settings.weblinkBurnAfterRead}
          defaultExpiryHours={
            settings.weblinkDefaultExpiry
              ? expiryStringToHours(settings.weblinkDefaultExpiry)
              : settings.weblinkExpiryHours
          }
          fontFamily={settings.fontFamily}
          fontSize={settings.fontSize}
          confirmBeforeSend={settings.confirmBeforeSend}
          cloakSubjectHeaders={settings.cloakSubjectHeaders}
          knownContacts={knownContacts}
          language={settings.language}
        />
      )}

      {/* Two-Column Gmail Settings Modal - unmounted when mailbox locked */}
      {!isSessionLocked && (
        <SettingsModal
          isOpen={isSettingsOpen}
          onClose={() => setIsSettingsOpen(false)}
          initialTab={settingsInitialTab}
          hsmStatus={hsmStatus}
          account={account}
          isDarkMode={isDarkMode}
          onToggleTheme={handleToggleTheme}
          onUpdateAccountEmail={handleUpdateAccountEmail}
          onLogoutAccount={handleLogout}
          onOpenSignIn={() => setIsSignInOpen(true)}
          settings={settings}
          onUpdateSettings={handleUpdateSettings}
          onShowNotice={setToastNotice}
          onVaultStateChange={async () => {
            try {
              const acc = await api.getAccount();
              setAccount(acc);
              if (!acc.isUnlocked) {
                setIsSessionLocked(true);
                setSelectedMessageId(null);
                setMessages([]);
                setIsComposeOpen(false);
              } else {
                setIsSessionLocked(false);
                const msgs = await api.fetchInbox(settings.maxPageSize);
                setMessages(msgs);
              }
            } catch {}
          }}
        />
      )}

      {/* Welcome / Sign In Modal */}
      <SignInModal
        isOpen={isSignInOpen}
        onClose={() => setIsSignInOpen(false)}
        onSignIn={handleSignIn}
        allowClose={Boolean(account.email)}
      />

      {/* Viewport-Centered Floating Toast Outside the Settings Card */}
      {toastNotice && (
        <div className="fixed bottom-5 left-1/2 -translate-x-1/2 z-[100] px-5 py-2.5 rounded-full bg-[#0F172A]/95 text-white text-xs font-semibold shadow-2xl border border-sky-500/40 shadow-sky-950/50 backdrop-blur-xl flex items-center space-x-3 w-auto max-w-[90vw] whitespace-nowrap pointer-events-auto animate-in fade-in slide-in-from-bottom-3 duration-200 select-none">
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse shrink-0" />
          <span className="truncate leading-normal tracking-wide">{toastNotice}</span>
          <button
            type="button"
            onClick={() => setToastNotice(null)}
            className="ml-2 p-1 text-slate-400 hover:text-white rounded-full hover:bg-white/10 transition-colors shrink-0 cursor-pointer"
            title="Dismiss"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Visually hidden ARIA live region for screen readers */}
      <div aria-live="polite" aria-atomic="true" className="sr-only">
        {toastNotice || syncStatus || (isSessionLocked ? 'QuMail mailbox is locked' : '')}
      </div>
    </div>
  </MotionConfig>
  );
};

export default App;
