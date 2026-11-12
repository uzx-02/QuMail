import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { MessageList } from './components/MessageList';
import { ReadingPane } from './components/ReadingPane';
import { ComposeModal } from './components/ComposeModal';
import { SettingsModal } from './components/SettingsModal';
import { SignInModal } from './components/SignInModal';
import { api } from './lib/api';
import { EmailMessage, HSMStatus, AccountSession } from './types';
import { INITIAL_ACCOUNT, INITIAL_HSM } from './initialState';

export const App: React.FC = () => {
  // Theme state
  const [isDarkMode, setIsDarkMode] = useState<boolean>(() => {
    const saved = localStorage.getItem('qumail-theme');
    if (saved) return saved === 'dark';
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  });

  // Navigation & layout state
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [currentFolder, setCurrentFolder] = useState('inbox');
  const [categoryFilter, setCategoryFilter] = useState<'primary' | 'updates' | 'secure'>('primary');
  const [searchQuery, setSearchQuery] = useState('');

  // Modals state
  const [isComposeOpen, setIsComposeOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isSignInOpen, setIsSignInOpen] = useState(false);
  const [composeDefaults, setComposeDefaults] = useState({ to: '', subject: '', body: '' });

  // Data state
  const [messages, setMessages] = useState<EmailMessage[]>([]);
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null);
  const [account, setAccount] = useState<AccountSession>(INITIAL_ACCOUNT);
  const [hsmStatus, setHsmStatus] = useState<HSMStatus>(INITIAL_HSM);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [syncStatus, setSyncStatus] = useState<string | null>(null);
  const [backendReady, setBackendReady] = useState<boolean | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);

  // Sync dark mode class on <html>
  useEffect(() => {
    if (isDarkMode) {
      document.documentElement.classList.add('dark');
      localStorage.setItem('qumail-theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('qumail-theme', 'light');
    }
  }, [isDarkMode]);

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

      // Sequential IPC initialization to avoid Edge WebView2 message interleaving
      const msgs = await api.getMessages();
      setMessages(msgs);
      const acc = await api.getAccount();
      setAccount(acc);
      const hsm = await api.getHSMStatus();
      setHsmStatus(hsm);

      // If no email exists in session, prompt sign in
      if (!acc.email) {
        setIsSignInOpen(true);
      } else {
        // Background live inbox synchronization with visual loading state
        setSyncStatus('Checking for new messages in background...');
        setIsRefreshing(true);
        api.fetchInbox()
          .then((liveMsgs) => {
            if (liveMsgs && liveMsgs.length > 0) {
              setMessages(liveMsgs);
            }
          })
          .catch((err) => console.debug('Initial live inbox sync note:', err))
          .finally(() => {
            setIsRefreshing(false);
            setSyncStatus(null);
          });
      }
    } catch (e: any) {
      console.error('Failed to initialize QuMail state:', e);
      setBackendReady(false);
      setBackendError(e?.message || 'Failed to initialize QuMail bridge');
    }
  }, []);

  // Initial load
  useEffect(() => {
    initData();
  }, [initData]);

  const handleToggleTheme = useCallback(() => {
    setIsDarkMode((prev) => !prev);
  }, []);

  const handleToggleSidebar = useCallback(() => {
    setIsSidebarCollapsed((prev) => !prev);
  }, []);

  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    setSyncStatus('Synchronizing inbox with mail server...');
    try {
      const msgs = await api.fetchInbox();
      const hsm = await api.getHSMStatus();
      setMessages(msgs);
      setHsmStatus(hsm);
    } catch (e) {
      console.error('Failed to refresh data:', e);
    } finally {
      setSyncStatus(null);
      setTimeout(() => setIsRefreshing(false), 400);
    }
  }, []);

  const handleSelectMessage = useCallback(async (msg: EmailMessage) => {
    setSelectedMessageId(msg.id);
    if (!msg.seen) {
      await api.markRead(msg.id, true);
      setMessages((prev) =>
        prev.map((m) => (m.id === msg.id ? { ...m, seen: true } : m))
      );
    }
  }, []);

  const handleToggleStar = useCallback(async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    await api.toggleStar(id);
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, starred: !m.starred } : m))
    );
  }, []);

  const handleDeleteMessage = useCallback(async (id: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    await api.deleteMessage(id);
    setMessages((prev) => prev.filter((m) => m.id !== id));
    if (selectedMessageId === id) {
      setSelectedMessageId(null);
    }
  }, [selectedMessageId]);

  const handleMarkRead = useCallback(async (id: string, seen: boolean, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    await api.markRead(id, seen);
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, seen } : m))
    );
  }, []);

  const handleOpenCompose = useCallback(() => {
    if (!account.email) {
      setIsSignInOpen(true);
      return;
    }
    setComposeDefaults({ to: '', subject: '', body: '' });
    setIsComposeOpen(true);
  }, [account.email]);

  const handleReply = useCallback((msg: EmailMessage) => {
    setComposeDefaults({
      to: msg.senderEmail,
      subject: msg.subject.startsWith('Re:') ? msg.subject : `Re: ${msg.subject}`,
      body: `\n\nOn ${msg.date}, ${msg.sender} <${msg.senderEmail}> wrote:\n> ${msg.body.split('\n').join('\n> ')}`,
    });
    setIsComposeOpen(true);
  }, []);

  const handleForward = useCallback((msg: EmailMessage) => {
    setComposeDefaults({
      to: '',
      subject: msg.subject.startsWith('Fwd:') ? msg.subject : `Fwd: ${msg.subject}`,
      body: `\n\n---------- Forwarded message ---------\nFrom: ${msg.sender} <${msg.senderEmail}>\nDate: ${msg.date}\nSubject: ${msg.subject}\nTo: ${msg.recipients.join(', ')}\n\n${msg.body}`,
    });
    setIsComposeOpen(true);
  }, []);

  const handleSend = useCallback(async (draft: Partial<EmailMessage>) => {
    const res = await api.sendMessage(draft);
    if (!res.success) {
      alert(res.message || 'Failed to dispatch email.');
      return false;
    }
    const updated = await api.getMessages();
    setMessages(updated);
    return true;
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
    await api.updateAccountEmail(email);
    try {
      const fullAcc = await api.getAccount();
      setAccount(fullAcc);
    } catch {
      setAccount((prev) => ({ ...prev, email }));
    }
    const msgs = await api.fetchInbox();
    setMessages(msgs);
  }, []);

  // Filter messages according to folder and search
  const displayedMessages = useMemo(() => {
    let result = messages;

    // Folder filtering
    if (currentFolder === 'starred') {
      result = result.filter((m) => m.starred && m.folder !== 'trash');
    } else if (currentFolder === 'trash') {
      result = result.filter((m) => m.folder === 'trash');
    } else {
      result = result.filter((m) => m.folder === currentFolder);
    }

    // Search query filtering
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

    return result;
  }, [messages, currentFolder, searchQuery]);

  // Selected message details
  const selectedMessage = useMemo(() => {
    if (!selectedMessageId) return null;
    return messages.find((m) => m.id === selectedMessageId) || null;
  }, [messages, selectedMessageId]);

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

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-[#F6F8FC] dark:bg-[#0A0E17] text-[#202124] dark:text-[#F1F5F9]">
      {/* 1. Gmail Header */}
      <Header
        onToggleSidebar={handleToggleSidebar}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onOpenSignIn={() => setIsSignInOpen(true)}
        isDarkMode={isDarkMode}
        onToggleTheme={handleToggleTheme}
        hsmStatus={hsmStatus}
        account={account}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
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
          isCollapsed={isSidebarCollapsed}
          hsmStatus={hsmStatus}
          onOpenSettings={() => setIsSettingsOpen(true)}
        />

        {/* Center / Right Content Pane */}
        <main className="flex-1 flex overflow-hidden">
          {selectedMessage ? (
            /* Reading View with back arrow & actions */
            <ReadingPane
              message={selectedMessage}
              onReply={handleReply}
              onForward={handleForward}
              onDelete={handleDeleteMessage}
              onClose={() => setSelectedMessageId(null)}
            />
          ) : (
            /* Gmail Message List */
            <MessageList
              messages={displayedMessages}
              selectedMessageId={selectedMessageId}
              onSelectMessage={handleSelectMessage}
              onToggleStar={handleToggleStar}
              onRefresh={handleRefresh}
              onDeleteMessage={handleDeleteMessage}
              onMarkRead={handleMarkRead}
              isRefreshing={isRefreshing}
              categoryFilter={categoryFilter}
              onCategoryChange={setCategoryFilter}
            />
          )}
        </main>
      </div>

      {/* Floating Gmail Compose Modal */}
      <ComposeModal
        isOpen={isComposeOpen}
        onClose={() => setIsComposeOpen(false)}
        onSend={handleSend}
        initialTo={composeDefaults.to}
        initialSubject={composeDefaults.subject}
        initialBody={composeDefaults.body}
      />

      {/* Two-Column Gmail Settings Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        hsmStatus={hsmStatus}
        account={account}
        isDarkMode={isDarkMode}
        onToggleTheme={handleToggleTheme}
        onUpdateAccountEmail={handleUpdateAccountEmail}
        onLogoutAccount={handleLogout}
        onOpenSignIn={() => setIsSignInOpen(true)}
      />

      {/* Welcome / Sign In Modal */}
      <SignInModal
        isOpen={isSignInOpen}
        onClose={() => setIsSignInOpen(false)}
        onSignIn={handleSignIn}
        allowClose={Boolean(account.email)}
      />
    </div>
  );
};

export default App;
