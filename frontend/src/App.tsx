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
import { INITIAL_ACCOUNT, INITIAL_HSM } from './mockData';

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

  // Initial load
  useEffect(() => {
    const initData = async () => {
      try {
        const [msgs, acc, hsm] = await Promise.all([
          api.getMessages(),
          api.getAccount(),
          api.getHSMStatus(),
        ]);
        setMessages(msgs);
        setAccount(acc);
        setHsmStatus(hsm);

        // If no email exists in session, prompt sign in
        if (!acc.email) {
          setIsSignInOpen(true);
        }
      } catch (e) {
        console.error('Failed to initialize QuMail state:', e);
      }
    };
    initData();
  }, []);

  const handleToggleTheme = useCallback(() => {
    setIsDarkMode((prev) => !prev);
  }, []);

  const handleToggleSidebar = useCallback(() => {
    setIsSidebarCollapsed((prev) => !prev);
  }, []);

  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const msgs = await api.fetchInbox();
      const hsm = await api.getHSMStatus();
      setMessages(msgs);
      setHsmStatus(hsm);
    } catch (e) {
      console.error('Failed to refresh data:', e);
    } finally {
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
    await api.sendMessage(draft);
    const updated = await api.getMessages();
    setMessages(updated);
  }, []);

  const handleSignIn = useCallback(async (email: string, displayName?: string, org?: string) => {
    const acc = await api.loginAccount(email, displayName, org);
    setAccount(acc);
    const msgs = await api.fetchInbox();
    setMessages(msgs);
  }, []);

  const handleLogout = useCallback(async () => {
    await api.logoutAccount();
    setAccount(INITIAL_ACCOUNT);
    setIsSignInOpen(true);
  }, []);

  const handleUpdateAccountEmail = useCallback(async (email: string) => {
    await api.updateAccountEmail(email);
    setAccount((prev) => ({ ...prev, email }));
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
