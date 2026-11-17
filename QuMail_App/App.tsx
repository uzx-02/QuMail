import './global.css';
import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  ActivityIndicator,
  useWindowDimensions,
  Alert,
  BackHandler,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider, useSafeAreaInsets } from 'react-native-safe-area-context';
import { FlashList } from '@shopify/flash-list';
import { Edit3, RefreshCw, Inbox, ShieldCheck } from 'lucide-react-native';
import * as SecureStore from 'expo-secure-store';

import {
  EmailMessage,
  AccountSession,
  QuMailSettings,
  DEFAULT_SETTINGS,
  INITIAL_ACCOUNT,
  OutboundMessage,
  LanguageOption,
  SearchFilters,
  DEFAULT_SEARCH_FILTERS,
} from './src/types';
import { mailTransport } from './src/bridge/MailTransport';
import { vaultManager } from './src/bridge/VaultManager';
import { t } from './src/lib/i18n';
import { getTheme, getAccent } from './src/lib/theme';

import { Header } from './src/components/Header';
import { SidebarDrawer } from './src/components/SidebarDrawer';
import { MessageListItem } from './src/components/MessageListItem';
import { ReadingPane } from './src/components/ReadingPane';
import { ComposeModal } from './src/components/ComposeModal';
import { SettingsModal } from './src/components/SettingsModal';
import { SignInModal } from './src/components/SignInModal';
import { LoadingScreen } from './src/components/LoadingScreen';

const SETTINGS_STORAGE_KEY = 'qumail_user_settings_v1';

function MainApp() {
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const isTablet = width >= 600;
  const isDesktop = width >= 960;

  // Startup & Loading Screen
  const [isAppLoading, setIsAppLoading] = useState(true);

  // State
  const [account, setAccount] = useState<AccountSession>(INITIAL_ACCOUNT);
  const [settings, setSettings] = useState<QuMailSettings>(DEFAULT_SETTINGS);
  const [currentFolder, setCurrentFolder] = useState<string>('inbox');
  const [messages, setMessages] = useState<EmailMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedMessage, setSelectedMessage] = useState<EmailMessage | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchFilters, setSearchFilters] = useState<SearchFilters>(DEFAULT_SEARCH_FILTERS);

  // Modals & Drawers
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [composeOpen, setComposeOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [forceFreshSignIn, setForceFreshSignIn] = useState(false);
  const [replyTo, setReplyTo] = useState<{ recipient: string; subject: string } | undefined>();

  const lang = settings.language || 'en';
  const theme = getTheme(settings.theme, settings.highContrast);
  const accent = getAccent(settings.accentColor);

  // Android Gesture & Hardware Back Button Handling
  useEffect(() => {
    const onBackPress = () => {
      // 1. If Settings modal is open, close it
      if (settingsOpen) {
        setSettingsOpen(false);
        return true;
      }
      // 2. If Compose modal is open, close it
      if (composeOpen) {
        setComposeOpen(false);
        return true;
      }
      // 3. If Sidebar drawer is open, close it
      if (sidebarOpen) {
        setSidebarOpen(false);
        return true;
      }
      // 4. If reading a specific email, return to the message list
      if (selectedMessage) {
        setSelectedMessage(null);
        return true;
      }
      // 5. If in a different folder other than inbox, return to inbox
      if (currentFolder !== 'inbox') {
        setCurrentFolder('inbox');
        return true;
      }
      // 6. Otherwise let OS perform default behavior (exit/minimize)
      return false;
    };

    const backHandlerSubscription = BackHandler.addEventListener(
      'hardwareBackPress',
      onBackPress
    );

    return () => backHandlerSubscription.remove();
  }, [settingsOpen, composeOpen, sidebarOpen, selectedMessage, currentFolder]);

  // Check vault, load persisted settings, and initial setup on mount
  useEffect(() => {
    bootstrapVault();
  }, []);

  const handleUpdateSettings = useCallback(async (newSettings: QuMailSettings) => {
    setSettings(newSettings);
    try {
      await SecureStore.setItemAsync(SETTINGS_STORAGE_KEY, JSON.stringify(newSettings));
    } catch (e) {
      console.warn('Failed to persist settings:', e);
    }
  }, []);

  const selectedMessageRef = useRef(selectedMessage);
  selectedMessageRef.current = selectedMessage;

  const loadFolder = useCallback(async (folder: string) => {
    setLoading(true);
    try {
      const msgs = await mailTransport.fetchMessages(folder);
      setMessages(msgs);
      if (msgs.length > 0 && isDesktop && !selectedMessageRef.current) {
        setSelectedMessage(msgs[0]);
      }
    } finally {
      setLoading(false);
    }
  }, [isDesktop]);

  const bootstrapVault = async () => {
    try {
      // Load saved settings from hardware storage
      try {
        const stored = await SecureStore.getItemAsync(SETTINGS_STORAGE_KEY);
        if (stored) {
          const parsed = JSON.parse(stored);
          setSettings((prev) => ({ ...prev, ...parsed }));
        }
      } catch (e) {
        console.warn('Settings load exception:', e);
      }

      const isInit = await vaultManager.isVaultInitialized();
      if (isInit) {
        const acc = await vaultManager.getAccount();
        const savedAvatar = await SecureStore.getItemAsync('qumail_user_avatar_url_v1');
        const savedDisplayName = await SecureStore.getItemAsync('qumail_user_display_name_v1');
        const mergedAcc = {
          ...acc,
          ...(savedAvatar ? { avatarUrl: savedAvatar } : {}),
          ...(savedDisplayName ? { displayName: savedDisplayName } : {}),
        };
        setAccount(mergedAcc);
        if (!acc.isUnlocked) {
          // Attempt biometric auto-unlock
          const unlocked = await vaultManager.unlockWithBiometrics();
          if (unlocked) {
            const fresh = await vaultManager.getAccount();
            setAccount({
              ...fresh,
              ...(savedAvatar ? { avatarUrl: savedAvatar } : {}),
              ...(savedDisplayName ? { displayName: savedDisplayName } : {}),
            });
            await loadFolder(currentFolder);
            checkDirectoryEnrollment(fresh.email);
          }
        } else {
          await loadFolder(currentFolder);
          checkDirectoryEnrollment(acc.email);
        }
      }
    } finally {
      setIsAppLoading(false);
    }
  };

  useEffect(() => {
    if (account.isUnlocked) {
      loadFolder(currentFolder);
      if (account.email) {
        checkDirectoryEnrollment(account.email);
      }
    }
  }, [currentFolder, account.isUnlocked, account.email]);

  // Search and Advanced Filter processing
  const filteredMessages = useMemo(() => {
    return messages.filter((m) => {
      // 1. Text Search Query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesQuery =
          m.subject.toLowerCase().includes(q) ||
          m.snippet.toLowerCase().includes(q) ||
          m.sender.toLowerCase().includes(q) ||
          m.senderEmail.toLowerCase().includes(q);
        if (!matchesQuery) return false;
      }

      // 2. Security Mode Filter
      if (searchFilters.securityMode !== 'all') {
        if (m.securityMode !== searchFilters.securityMode) return false;
      }

      // 3. From Filter
      if (searchFilters.from.trim()) {
        const fromQ = searchFilters.from.trim().toLowerCase();
        if (
          !m.sender.toLowerCase().includes(fromQ) &&
          !m.senderEmail.toLowerCase().includes(fromQ)
        ) {
          return false;
        }
      }

      // 4. To Filter
      if (searchFilters.to.trim()) {
        const toQ = searchFilters.to.trim().toLowerCase();
        const matchesTo = m.recipients.some((r) => r.toLowerCase().includes(toQ));
        if (!matchesTo) return false;
      }

      // 5. Has Attachment
      if (searchFilters.hasAttachment && !m.hasAttachments) {
        return false;
      }

      // 6. Unread Only
      if (searchFilters.unreadOnly && m.seen) {
        return false;
      }

      // 7. Starred Only
      if (searchFilters.starredOnly && !m.starred) {
        return false;
      }

      // 8. Cloaked Only
      if (searchFilters.cloakedOnly && !m.cloakSubjectHeaders) {
        return false;
      }

      return true;
    });
  }, [messages, searchQuery, searchFilters]);

  const handleToggleStar = async (id: string) => {
    await mailTransport.toggleStar(id);
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, starred: !m.starred } : m))
    );
    if (selectedMessage?.id === id) {
      setSelectedMessage((prev) => (prev ? { ...prev, starred: !prev.starred } : null));
    }
  };

  const handleDeleteMessage = async (id: string) => {
    const targetMsg = messages.find((m) => m.id === id);
    if (targetMsg && (targetMsg.securityMode === 'standard' || !targetMsg.isQuMail)) {
      Alert.alert(
        'Action Restricted',
        'Standard unsealed emails cannot be deleted or modified from the QuMail Sovereign Enclave to preserve provider mailbox audit integrity.'
      );
      return;
    }
    setMessages((prev) => prev.filter((m) => m.id !== id));
    if (selectedMessage?.id === id) {
      setSelectedMessage(null);
    }
    try {
      await mailTransport.deleteMessage(id);
    } catch (e) {
      console.warn('Failed to delete message on transport:', e);
    }
  };

  const checkDirectoryEnrollment = async (email: string) => {
    if (!email) return;
    try {
      const normEmail = email.trim().toLowerCase();
      const myPub = await vaultManager.getPublicCert(normEmail);
      let isRegisteredInDirectory = false;

      if (myPub) {
        try {
          const recInfo = await mailTransport.checkRecipient(normEmail);
          const certs = recInfo.publicCertsBase64 || (recInfo.publicCertBase64 ? [recInfo.publicCertBase64] : []);
          if (certs.includes(myPub)) {
            isRegisteredInDirectory = true;
          }
        } catch {
          // ignore network lookup failures
        }
      }

      if (!isRegisteredInDirectory) {
        console.log(`Device public key not enrolled in Cloudflare Directory for ${normEmail}. Enrolling device now...`);
        const enrolledToken = await mailTransport.ensureDeviceEnrolled(normEmail);
        if (enrolledToken) {
          console.log(`Successfully enrolled ${normEmail} into Cloudflare Directory!`);
          await loadFolder(currentFolder);
        }
      }
    } catch (e) {
      console.warn('Directory enrollment check warning:', e);
    }
  };

  const handleSendOutbound = async (outbound: OutboundMessage) => {
    try {
      await mailTransport.sendMessage(outbound);
      await loadFolder(currentFolder);
    } catch (err: any) {
      const msg = err?.message || String(err);
      if (
        msg.includes('Device enrollment required') ||
        msg.includes('401') ||
        msg.includes('unauthorized') ||
        msg.includes('session token')
      ) {
        Alert.alert(
          'Cloudflare Directory Enrollment Required',
          'A valid Cloudflare Directory session is required to perform quantum-safe key exchange or create secure WebLinks. Tap "Connect Now" to verify your device.',
          [
            { text: 'Cancel', style: 'cancel' },
            { text: 'Connect Now', onPress: handleGoogleSignIn },
          ]
        );
      } else {
        throw err;
      }
    }
  };

  const handleReply = (msg: EmailMessage) => {
    setReplyTo({ recipient: msg.senderEmail, subject: msg.subject });
    setComposeOpen(true);
  };

  const handleLockVault = useCallback(async () => {
    await vaultManager.lockVault();
    setMessages([]);
    setSelectedMessage(null);
    const acc = await vaultManager.getAccount();
    setAccount({ ...acc, isUnlocked: false });
  }, []);

  const handleSignOut = useCallback(async () => {
    await vaultManager.lockVault();
    setMessages([]);
    setSelectedMessage(null);
    setAccount(INITIAL_ACCOUNT);
    setSettingsOpen(false);
  }, []);

  const handleSwitchAccount = useCallback(async () => {
    await vaultManager.lockVault();
    setMessages([]);
    setSelectedMessage(null);
    setAccount(INITIAL_ACCOUNT);
    setForceFreshSignIn(true);
    setSettingsOpen(false);
  }, []);

  const handleGoogleSignIn = async () => {
    try {
      const user = await mailTransport.signInWithGoogle(settings.googleClientId);
      const isInit = await vaultManager.isVaultInitialized();
      if (!isInit) {
        await vaultManager.initializeVault(user.email);
      }
      const fresh = await vaultManager.getAccount();
      setAccount({
        ...fresh,
        email: user.email,
        displayName: user.displayName || user.email.split('@')[0],
        avatarUrl: user.avatarUrl,
        connectionStatus: 'ONLINE',
        isUnlocked: true,
      });
      await loadFolder('inbox');
    } catch (err: any) {
      Alert.alert('Google Sign-In', err?.message || 'Could not complete sign-in. Please verify your Google account.');
    }
  };

  const handleAppPasswordSignIn = async (email: string, appPassword: string) => {
    try {
      const acc = await mailTransport.signInWithAppPassword(email, appPassword);
      setAccount(acc);
      await loadFolder('inbox');
    } catch (err: any) {
      Alert.alert('Sign-In Error', err?.message || 'Could not authenticate mailbox.');
    }
  };

  const cycleLanguage = () => {
    const order: LanguageOption[] = ['en', 'hi', 'mr'];
    const nextIdx = (order.indexOf(settings.language) + 1) % order.length;
    handleUpdateSettings({ ...settings, language: order[nextIdx] });
  };

  // 1. Render Loading / Splash Screen on first launch
  if (isAppLoading) {
    return (
      <View style={{ flex: 1, backgroundColor: '#020617' }}>
        <StatusBar style="light" />
        <LoadingScreen language={lang} onReady={() => setIsAppLoading(false)} />
      </View>
    );
  }

  // 2. Unbypassable Security Barrier: If the mailbox is locked, render ONLY the lock gate!
  // No email messages are loaded, and the inbox UI is completely unmounted.
  if (!account.isUnlocked) {
    return (
      <View
        style={{
          flex: 1,
          backgroundColor: theme.bg,
          paddingTop: insets.top,
          paddingBottom: insets.bottom,
        }}
      >
        <StatusBar style={theme.statusBarStyle} />
        <SignInModal
          visible={true}
          isInitialized={account.vaultState === 'ACTIVE' || account.vaultState === 'LOCKED'}
          forceFreshSignIn={forceFreshSignIn}
          onToggleFreshSignIn={setForceFreshSignIn}
          onGoogleSignIn={handleGoogleSignIn}
          onBiometricUnlock={async () => {
            const ok = await vaultManager.unlockWithBiometrics();
            if (ok) {
              const fresh = await vaultManager.getAccount();
              const savedAvatar = await SecureStore.getItemAsync('qumail_user_avatar_url_v1');
              const savedDisplayName = await SecureStore.getItemAsync('qumail_user_display_name_v1');
              setAccount({
                ...fresh,
                isUnlocked: true,
                ...(savedAvatar ? { avatarUrl: savedAvatar } : {}),
                ...(savedDisplayName ? { displayName: savedDisplayName } : {}),
              });
              await loadFolder('inbox');
              checkDirectoryEnrollment(fresh.email);
              return true;
            }
            return false;
          }}
          onPinUnlock={async (pin: string) => {
            const ok = await vaultManager.unlockWithPin(pin);
            if (ok) {
              const fresh = await vaultManager.getAccount();
              const savedAvatar = await SecureStore.getItemAsync('qumail_user_avatar_url_v1');
              const savedDisplayName = await SecureStore.getItemAsync('qumail_user_display_name_v1');
              setAccount({
                ...fresh,
                isUnlocked: true,
                ...(savedAvatar ? { avatarUrl: savedAvatar } : {}),
                ...(savedDisplayName ? { displayName: savedDisplayName } : {}),
              });
              await loadFolder('inbox');
              checkDirectoryEnrollment(fresh.email);
              return true;
            }
            return false;
          }}
          onAppPasswordSignIn={handleAppPasswordSignIn}
          language={lang}
        />
      </View>
    );
  }

  // 3. Authenticated Mailbox View
  return (
    <View
      style={{
        flex: 1,
        backgroundColor: theme.bg,
        paddingTop: insets.top,
        paddingBottom: insets.bottom,
      }}
    >
      <StatusBar style={theme.statusBarStyle} />

      {/* Main Layout Container (Multi-pane responsive) */}
      <View style={{ flex: 1, flexDirection: 'row' }}>
        {/* Tablet Persistent Sidebar */}
        {isTablet && (
          <SidebarDrawer
            visible={true}
            onClose={() => {}}
            currentFolder={currentFolder}
            onSelectFolder={(f) => {
              setCurrentFolder(f);
              setSelectedMessage(null);
            }}
            account={account}
            onSignOut={handleSignOut}
            isTablet={true}
            settings={settings}
            onUpdateSettings={(patch) => handleUpdateSettings({ ...settings, ...patch })}
          />
        )}

        {/* Message List Pane */}
        <View
          style={{
            flex: 1,
            maxWidth: isDesktop ? 420 : undefined,
            borderRightWidth: isDesktop ? 1 : 0,
            borderRightColor: theme.border,
            display: selectedMessage && !isDesktop ? 'none' : 'flex',
          }}
        >
          <Header
            title={t(`folder_${currentFolder}`, lang) || currentFolder}
            isUnlocked={account.isUnlocked}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            searchFilters={searchFilters}
            onApplySearchFilters={setSearchFilters}
            onClearSearchFilters={() => setSearchFilters(DEFAULT_SEARCH_FILTERS)}
            onMenuPress={() => setSidebarOpen(true)}
            onVaultPress={() => {
              if (account.isUnlocked) {
                handleLockVault();
              }
            }}
            onSettingsPress={() => setSettingsOpen(true)}
            onRefresh={() => loadFolder(currentFolder)}
            refreshing={loading}
            language={lang}
            onToggleLanguage={cycleLanguage}
            theme={settings.theme}
          />

          {loading ? (
            <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32 }}>
              <ActivityIndicator size="large" color={accent.primary} />
              <Text style={{ fontSize: 12, marginTop: 12, fontWeight: '500', color: theme.subtext }}>
                {t('syncing', lang)}
              </Text>
            </View>
          ) : filteredMessages.length === 0 ? (
            <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32 }}>
              <Inbox size={48} color={theme.border} />
              <Text style={{ fontSize: 14, fontWeight: '600', marginTop: 12, color: theme.subtext }}>
                {t('no_messages_in_folder', lang) || 'No messages in this folder'}
              </Text>
              <Text style={{ fontSize: 12, marginTop: 4, textAlign: 'center', color: theme.subtext }}>
                {t('inbox_clean_note', lang) || 'Your quantum-encrypted mailbox is up to date.'}
              </Text>
            </View>
          ) : (
            <FlashList
              data={filteredMessages}
              refreshing={loading}
              onRefresh={() => loadFolder(currentFolder)}
              renderItem={({ item }) => (
                <MessageListItem
                  message={item}
                  selected={selectedMessage?.id === item.id}
                  theme={settings.theme}
                  density={settings.listDensity}
                  hidePreviews={settings.hideInboxPreviews}
                  showAvatars={settings.showSenderAvatars}
                  userEmail={account.email}
                  userAvatarUrl={account.avatarUrl}
                  onPress={(msg) => {
                    setSelectedMessage(msg);
                    if (!msg.seen) {
                      mailTransport.markRead(msg.id, true);
                      setMessages((prev) =>
                        prev.map((m) => (m.id === msg.id ? { ...m, seen: true } : m))
                      );
                    }
                  }}
                  onToggleStar={handleToggleStar}
                />
              )}
              keyExtractor={(item) => item.id}
            />
          )}

          {/* Floating Action Button for Mobile */}
          {!isDesktop && (
            <TouchableOpacity
              onPress={() => {
                setReplyTo(undefined);
                setComposeOpen(true);
              }}
              activeOpacity={0.85}
              style={{
                position: 'absolute',
                bottom: 24,
                right: 24,
                width: 56,
                height: 56,
                borderRadius: 16,
                backgroundColor: accent.primary,
                alignItems: 'center',
                justifyContent: 'center',
                elevation: 8,
              }}
            >
              <Edit3 size={24} color="#ffffff" />
            </TouchableOpacity>
          )}
        </View>

        {/* Reading Pane (Split on Tablet/Desktop, Fullscreen on Phone) */}
        {(selectedMessage || isDesktop) && (
          <View
            style={{
              flex: 1,
              display: selectedMessage ? 'flex' : isDesktop ? 'flex' : 'none',
            }}
          >
            <ReadingPane
              message={selectedMessage}
              onBack={() => setSelectedMessage(null)}
              onDelete={handleDeleteMessage}
              onToggleStar={handleToggleStar}
              onReply={handleReply}
              language={lang}
              theme={settings.theme}
              userAvatarUrl={account.avatarUrl}
              userEmail={account.email}
              highContrast={settings.highContrast}
              dyslexicFont={settings.dyslexicReadingFont}
              showIconLabels={settings.showIconLabels}
            />
          </View>
        )}
      </View>

      {/* Slide-out Sidebar Drawer (Phone) */}
      {!isTablet && (
        <SidebarDrawer
          visible={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          currentFolder={currentFolder}
          onSelectFolder={(f) => {
            setCurrentFolder(f);
            setSelectedMessage(null);
          }}
          account={account}
          onSignOut={handleSignOut}
          isTablet={false}
          settings={settings}
          onUpdateSettings={(patch) => handleUpdateSettings({ ...settings, ...patch })}
        />
      )}

      {/* Compose Email Modal */}
      <ComposeModal
        visible={composeOpen}
        onClose={() => setComposeOpen(false)}
        onSend={handleSendOutbound}
        replyTo={replyTo}
        language={lang}
        theme={settings.theme}
      />

      {/* Settings Modal (8 comprehensive tabs with full desktop parity) */}
      <SettingsModal
        visible={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        settings={settings}
        onUpdateSettings={handleUpdateSettings}
        account={account}
        onLockVault={handleLockVault}
        onOpenSignIn={() => {
          setSettingsOpen(false);
          handleLockVault();
        }}
        onSignOut={handleSignOut}
        onSwitchAccount={handleSwitchAccount}
      />
    </View>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <MainApp />
    </SafeAreaProvider>
  );
}
