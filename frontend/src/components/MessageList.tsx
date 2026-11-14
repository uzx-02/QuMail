import React, { useState, useEffect, useMemo } from 'react';
import { RefreshCw, Trash2, Mail, MailOpen, Star, Paperclip, ShieldCheck, AlertTriangle, ShieldAlert, Inbox, Shield, Lock, CheckCircle2, RotateCw, ChevronLeft, ChevronRight, Check, X, SlidersHorizontal } from 'lucide-react';
import UseAnimations from 'react-useanimations';
import checkBox from 'react-useanimations/lib/checkBox';
import star from 'react-useanimations/lib/star';
import { EmailMessage, ListDensityOption, LanguageOption } from '../types';
import { SpotlightCard } from './reactbits/SpotlightCard';
import { resolveDisplaySubject } from '../lib/privacy';
import { t } from '../lib/i18n';

const CustomCheckbox: React.FC<{
  checked: boolean;
  indeterminate?: boolean;
  onClick: (e: React.MouseEvent) => void;
  title?: string;
  className?: string;
  size?: number;
}> = ({ checked, indeterminate, onClick, title, className = '', size = 22 }) => {
  const isChecked = checked || Boolean(indeterminate);
  return (
    <div
      role="checkbox"
      aria-checked={indeterminate ? 'mixed' : checked}
      onClick={(e) => {
        e.stopPropagation();
        onClick(e);
      }}
      title={title}
      className={`inline-flex items-center justify-center cursor-pointer select-none transition-transform active:scale-95 shrink-0 ${
        isChecked
          ? 'text-[#0B57D0] dark:text-sky-400'
          : 'text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300'
      } ${className}`}
    >
      <UseAnimations
        animation={checkBox}
        size={size}
        active={isChecked}
        strokeColor={isChecked ? 'var(--qumail-accent, #0B57D0)' : 'currentColor'}
      />
    </div>
  );
};

interface MessageListProps {
  messages: EmailMessage[];
  selectedMessageId: string | null;
  userEmail?: string;
  userAvatarUrl?: string;
  onSelectMessage: (msg: EmailMessage) => void;
  onToggleStar: (id: string, e: React.MouseEvent) => void;
  onRefresh: () => void;
  onDeleteMessage: (id: string, e?: React.MouseEvent) => void;
  onMarkRead: (id: string, seen: boolean, e?: React.MouseEvent) => void;
  isRefreshing: boolean;
  isInitialSyncing?: boolean;
  currentFolder?: string;
  onRetrySend?: (msg: EmailMessage, e: React.MouseEvent) => void;
  filterMode?: 'all' | 'secure' | 'unread';
  onFilterChange?: (filter: 'all' | 'secure' | 'unread') => void;
  onShowProtectionNotice?: (msg: string) => void;
  maskEncryptedSnippets?: boolean;
  listDensity?: ListDensityOption;
  showSenderAvatars?: boolean;
  pageSize?: number;
  hasActiveFilters?: boolean;
  onClearFilters?: () => void;
  showIconLabels?: boolean;
  language?: LanguageOption;
}

export const MessageList: React.FC<MessageListProps> = ({
  messages,
  selectedMessageId,
  userEmail,
  userAvatarUrl,
  onSelectMessage,
  onToggleStar,
  onRefresh,
  onDeleteMessage,
  onMarkRead,
  isRefreshing,
  isInitialSyncing = false,
  currentFolder,
  onRetrySend,
  filterMode = 'all',
  onFilterChange,
  onShowProtectionNotice,
  maskEncryptedSnippets = false,
  listDensity = 'comfortable',
  showSenderAvatars = true,
  pageSize = 50,
  hasActiveFilters = false,
  onClearFilters,
  showIconLabels = false,
  language,
}) => {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [activeFilter, setActiveFilter] = useState<'all' | 'secure' | 'unread'>(filterMode);
  const [currentPage, setCurrentPage] = useState(1);
  const [contextMenu, setContextMenu] = useState<{ msg: EmailMessage; x: number; y: number } | null>(null);

  useEffect(() => {
    setActiveFilter(filterMode);
  }, [filterMode]);

  useEffect(() => {
    setCurrentPage(1);
  }, [currentFolder, activeFilter, pageSize]);

  useEffect(() => {
    if (!contextMenu) return;
    const closeMenu = () => setContextMenu(null);
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeMenu();
    };
    window.addEventListener('click', closeMenu);
    window.addEventListener('scroll', closeMenu, true);
    window.addEventListener('keydown', onKeyDown);
    return () => {
      window.removeEventListener('click', closeMenu);
      window.removeEventListener('scroll', closeMenu, true);
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [contextMenu]);

  const handleContextMenu = (e: React.MouseEvent, msg: EmailMessage) => {
    e.preventDefault();
    e.stopPropagation();
    const menuWidth = 210;
    const menuHeight = 165;
    const x = Math.max(8, Math.min(e.clientX, window.innerWidth - menuWidth - 8));
    const y = Math.max(8, Math.min(e.clientY, window.innerHeight - menuHeight - 8));
    setContextMenu({ msg, x, y });
  };

  const handleFilterSelect = (mode: 'all' | 'secure' | 'unread') => {
    setActiveFilter(mode);
    onFilterChange?.(mode);
  };

  const isMessageQuMail = (m: EmailMessage): boolean => {
    if (m.isQuMail !== undefined) return Boolean(m.isQuMail);
    return Boolean(
      m.securityTier === 'pq_sealed' ||
      m.securityTier === 'weblink' ||
      m.securityMode === 'pq' ||
      m.securityMode === 'weblink' ||
      m.indicator?.badgeLevel === 'SECURE' ||
      m.subject?.startsWith('[QuMail Secure Link]')
    );
  };

  // Thread message counts for grouping indication
  const threadCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const m of messages) {
      const normSubj = (m.subject || '')
        .replace(/^((re|fwd):\s*)+/gi, '')
        .replace(/\s*\[(Shield|Shielded|Quantum-Safe|QuMail Secure Link|Encrypted)\]\s*/gi, ' ')
        .trim()
        .toLowerCase();
      const key = m.threadId || (normSubj ? `${m.folder || 'inbox'}:${normSubj}` : '');
      if (key) {
        counts.set(key, (counts.get(key) || 0) + 1);
      }
    }
    return counts;
  }, [messages]);

  const filteredMessages = messages.filter((m) => {
    if (activeFilter === 'secure') {
      return isMessageQuMail(m);
    }
    if (activeFilter === 'unread') {
      return !m.seen;
    }
    return true;
  });

  const handleToggleSelectAll = (e?: React.MouseEvent) => {
    e?.stopPropagation();
    if (selectedIds.size === filteredMessages.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filteredMessages.map((m) => m.id)));
    }
  };

  const handleToggleRowSelect = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelectedIds(next);
  };

  const handleBatchDelete = () => {
    let blockedCount = 0;
    selectedIds.forEach((id) => {
      const msg = messages.find((m) => m.id === id);
      if (msg && !isMessageQuMail(msg)) {
        blockedCount++;
      } else {
        onDeleteMessage(id);
      }
    });
    if (blockedCount > 0 && onShowProtectionNotice) {
      onShowProtectionNotice(`Safe Deletion Guard: Protected ${blockedCount} standard email(s). Only QuMail messages can be deleted.`);
    }
    setSelectedIds(new Set());
  };

  const handleBatchMarkRead = (seen: boolean) => {
    selectedIds.forEach((id) => onMarkRead(id, seen));
    setSelectedIds(new Set());
  };

  const filterPills: { id: 'all' | 'secure' | 'unread'; label: string; icon: React.ReactNode; count: number }[] = [
    { id: 'all', label: t(language, 'filter_pill_all'), icon: <Inbox className="w-3.5 h-3.5" />, count: messages.length },
    {
      id: 'secure',
      label: t(language, 'filter_pill_secure'),
      icon: <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />,
      count: messages.filter(isMessageQuMail).length,
    },
    {
      id: 'unread',
      label: t(language, 'filter_pill_unread'),
      icon: <Mail className="w-3.5 h-3.5 text-blue-500" />,
      count: messages.filter((m) => !m.seen).length,
    },
  ];

  return (
    <div className="flex-1 flex flex-col h-full bg-white dark:bg-[#161F33] overflow-hidden border-r border-[#E0E3E7] dark:border-[#1F2C47]">
      {/* 1. Top Mailbox Toolbar */}
      <div className="h-12 px-4 flex items-center justify-between border-b border-[#E0E3E7] dark:border-[#1F2C47] shrink-0 select-none bg-white dark:bg-[#161F33]">
        <div className="flex items-center space-x-2">
          {selectedIds.size === 0 ? (
            <button
              onClick={onRefresh}
              title={t(language, 'refresh')}
              className={`${
                showIconLabels ? 'px-3 py-1.5 rounded-full flex items-center space-x-1.5' : 'p-2 rounded-full'
              } text-[#5F6368] dark:text-[#94A3B8] hover:bg-[#F2F6FC] dark:hover:bg-[#1E2740] hover:text-[#202124] dark:hover:text-white transition-colors outline-none cursor-pointer`}
            >
              <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin text-[#0B57D0]' : ''}`} />
              {showIconLabels && <span className="text-xs font-semibold">{t(language, 'refresh')}</span>}
            </button>
          ) : (
            <div className="flex items-center space-x-2.5">
              <CustomCheckbox
                checked={filteredMessages.length > 0 && selectedIds.size === filteredMessages.length}
                indeterminate={selectedIds.size > 0 && selectedIds.size < filteredMessages.length}
                onClick={handleToggleSelectAll}
                title={selectedIds.size === filteredMessages.length ? t(language, 'deselect_all') : t(language, 'select_all')}
              />

              <span className="text-xs font-bold text-[#202124] dark:text-[#F1F5F9]">
                {t(language, 'selected_count', { count: selectedIds.size })}
              </span>

              {selectedIds.size < filteredMessages.length && (
                <button
                  type="button"
                  onClick={() => setSelectedIds(new Set(filteredMessages.map((m) => m.id)))}
                  className="text-[11px] font-semibold qumail-accent-text hover:underline cursor-pointer"
                >
                  {t(language, 'select_all')} ({filteredMessages.length})
                </button>
              )}

              <div className="flex items-center space-x-1 pl-2 border-l border-gray-200 dark:border-gray-700">
                <button
                  onClick={() => handleBatchMarkRead(true)}
                  title={t(language, 'mark_as_read')}
                  className={`${
                    showIconLabels ? 'px-2.5 py-1 rounded-full flex items-center space-x-1' : 'p-2 rounded-full'
                  } text-[#5F6368] dark:text-[#94A3B8] hover:bg-[#F2F6FC] dark:hover:bg-[#1E2740] transition-colors cursor-pointer`}
                >
                  <MailOpen className="w-4 h-4" />
                  {showIconLabels && <span className="text-xs font-medium">{t(language, 'mark_as_read')}</span>}
                </button>
                <button
                  onClick={() => handleBatchMarkRead(false)}
                  title={t(language, 'mark_as_unread')}
                  className={`${
                    showIconLabels ? 'px-2.5 py-1 rounded-full flex items-center space-x-1' : 'p-2 rounded-full'
                  } text-[#5F6368] dark:text-[#94A3B8] hover:bg-[#F2F6FC] dark:hover:bg-[#1E2740] transition-colors cursor-pointer`}
                >
                  <Mail className="w-4 h-4" />
                  {showIconLabels && <span className="text-xs font-medium">{t(language, 'mark_as_unread')}</span>}
                </button>
                <button
                  onClick={handleBatchDelete}
                  title={t(language, 'delete_selected')}
                  className={`${
                    showIconLabels ? 'px-2.5 py-1 rounded-full flex items-center space-x-1' : 'p-2 rounded-full'
                  } text-[#5F6368] dark:text-[#94A3B8] hover:bg-red-50 dark:hover:bg-red-950/40 hover:text-red-600 transition-colors cursor-pointer`}
                >
                  <Trash2 className="w-4 h-4" />
                  {showIconLabels && <span className="text-xs font-medium">{t(language, 'delete_selected')}</span>}
                </button>
                <button
                  onClick={() => setSelectedIds(new Set())}
                  title={t(language, 'deselect_all')}
                  className="p-1.5 rounded-full text-[#5F6368] dark:text-[#94A3B8] hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors cursor-pointer ml-1"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </div>

        {(() => {
          const total = filteredMessages.length;
          const totalPages = Math.max(1, Math.ceil(total / pageSize));
          const safePage = Math.min(currentPage, totalPages);
          const startIdx = (safePage - 1) * pageSize;
          const endIdx = Math.min(startIdx + pageSize, total);

          return (
            <div className="flex items-center space-x-2 text-xs text-[#5F6368] dark:text-[#94A3B8] font-medium">
              <span>
                {total > 0 ? `${startIdx + 1}–${endIdx} of ${total}` : '0 messages'}
              </span>
              {totalPages > 1 && (
                <div className="flex items-center space-x-0.5">
                  <button
                    type="button"
                    disabled={safePage <= 1}
                    onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                    title="Previous page"
                    className="p-1 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer transition-colors"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <button
                    type="button"
                    disabled={safePage >= totalPages}
                    onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                    title="Next page"
                    className="p-1 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer transition-colors"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              )}
            </div>
          );
        })()}
      </div>

      {/* 2. Modern Filter Pills (All | QuMail Secure | Unread) */}
      <div className="border-b border-[#E0E3E7] dark:border-[#1F2C47] px-4 py-2.5 bg-white dark:bg-[#161F33] shrink-0 flex items-center space-x-2">
        {filterPills.map((pill) => {
          const isActive = activeFilter === pill.id;
          return (
            <button
              key={pill.id}
              onClick={() => handleFilterSelect(pill.id)}
              className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-full text-xs font-semibold transition-all duration-150 outline-none cursor-pointer ${
                isActive
                  ? 'qumail-accent-bg shadow-sm'
                  : 'bg-[#F0F4F9] dark:bg-[#1E2740] text-[#444746] dark:text-[#C4C7C5] hover:bg-[#E2E8F0] dark:hover:bg-[#2A3755]'
              }`}
            >
              <span>{pill.icon}</span>
              <span>{pill.label}</span>
              <span
                className={`text-[10px] px-1.5 py-0.2 rounded-full font-bold ${
                  isActive ? 'bg-white/20 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
                }`}
              >
                {pill.count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Active Search Filter Status Bar */}
      {hasActiveFilters && (
        <div className="bg-sky-50/80 dark:bg-sky-950/30 border-b border-sky-200/60 dark:border-sky-800/60 px-4 py-2 flex items-center justify-between text-xs transition-colors">
          <div className="flex items-center space-x-2 text-sky-800 dark:text-sky-300">
            <SlidersHorizontal className="w-3.5 h-3.5 text-sky-600 dark:text-sky-400 shrink-0" />
            <span className="font-semibold">
              {t(language, 'filter_active_status', { count: filteredMessages.length, plural: filteredMessages.length !== 1 ? 's' : '' })}
            </span>
          </div>
          {onClearFilters && (
            <button
              type="button"
              onClick={onClearFilters}
              className="text-[11px] font-bold text-sky-700 dark:text-sky-400 hover:text-sky-900 dark:hover:text-sky-200 hover:underline cursor-pointer flex items-center space-x-1"
            >
              <span>{t(language, 'reset_filters')}</span>
            </button>
          )}
        </div>
      )}

      {/* Synchronization Progress Line */}
      {isRefreshing && (
        <div className="h-0.5 w-full bg-blue-100 dark:bg-blue-950 overflow-hidden shrink-0">
          <div className="h-full bg-blue-600 dark:bg-blue-400 animate-pulse w-full" />
        </div>
      )}

      {/* 3. Messages List */}
      <div className="flex-1 overflow-y-auto divide-y divide-[#F2F2F2] dark:divide-[#1F2C47]/60">
        {filteredMessages.length === 0 ? (
          (isInitialSyncing || (isRefreshing && messages.length === 0)) ? (
            <div>
              {/* Subtle status header */}
              <div className="flex items-center justify-between px-5 py-3 bg-blue-50/70 dark:bg-blue-950/30 border-b border-blue-100 dark:border-blue-900/40 text-xs text-blue-700 dark:text-blue-300 select-none">
                <div className="flex items-center space-x-2.5">
                  <RotateCw className="w-3.5 h-3.5 animate-spin text-blue-500 shrink-0" />
                  <span className="font-semibold">{t(language, 'syncing_mailbox')}</span>
                </div>
                <span className="text-[11px] text-blue-600/80 dark:text-blue-400/80 font-medium">{t(language, 'syncing_checking_imap')}</span>
              </div>

              {/* Skeleton Shimmer Rows */}
              <div className="divide-y divide-[#F2F2F2] dark:divide-[#1F2C47]/60">
                {[1, 2, 3, 4, 5, 6, 7].map((n) => (
                  <div
                    key={n}
                    className="flex items-center px-4 py-3.5 gap-3.5 border-b border-gray-100 dark:border-gray-800/40 animate-pulse select-none"
                  >
                    <div className="flex items-center space-x-2 shrink-0">
                      <div className="w-4 h-4 rounded-[4px] bg-gray-200 dark:bg-gray-800" />
                      <div className="w-4 h-4 rounded bg-gray-200 dark:bg-gray-800" />
                    </div>
                    {showSenderAvatars && (
                      <div className="w-8 h-8 rounded-full bg-gray-200 dark:bg-gray-800 shrink-0" />
                    )}
                    <div className="flex-1 min-w-0 space-y-2">
                      <div className="flex items-center justify-between gap-4">
                        <div className={`h-3.5 bg-gray-200 dark:bg-gray-800 rounded ${n % 2 === 0 ? 'w-36' : 'w-28'}`} />
                        <div className="h-3 bg-gray-200 dark:bg-gray-800 rounded w-14 shrink-0" />
                      </div>
                      <div className={`h-3 bg-gray-200 dark:bg-gray-800 rounded ${n % 3 === 0 ? 'w-4/5' : 'w-3/5'}`} />
                      <div className={`h-2.5 bg-gray-100 dark:bg-gray-800/60 rounded ${n % 2 === 0 ? 'w-1/2' : 'w-2/3'}`} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : currentFolder === 'outbox' ? (
            <div className="h-64 flex flex-col items-center justify-center text-center p-8 space-y-3">
              <div className="w-12 h-12 rounded-full bg-emerald-50 dark:bg-emerald-950/50 flex items-center justify-center text-emerald-600 dark:text-emerald-400">
                <CheckCircle2 className="w-6 h-6" />
              </div>
              <p className="text-sm font-semibold text-[#202124] dark:text-white">
                {t(language, 'outbox_clear_title')}
              </p>
              <p className="text-xs text-[#5F6368] dark:text-[#94A3B8] max-w-sm">
                {t(language, 'outbox_clear_desc')}
              </p>
            </div>
          ) : hasActiveFilters ? (
            <div className="h-64 flex flex-col items-center justify-center text-center p-8 space-y-3">
              <div className="w-12 h-12 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center qumail-accent-text">
                <SlidersHorizontal className="w-6 h-6" />
              </div>
              <p className="text-sm font-semibold text-[#202124] dark:text-white">
                {t(language, 'no_matching_filters')}
              </p>
              <p className="text-xs text-[#5F6368] dark:text-[#94A3B8] max-w-xs">
                {t(language, 'no_matching_filters_desc')}
              </p>
              {onClearFilters && (
                <button
                  type="button"
                  onClick={onClearFilters}
                  className="px-4 py-2 rounded-xl qumail-accent-bg text-white text-xs font-bold shadow-md cursor-pointer hover:opacity-95 transition-opacity"
                >
                  {t(language, 'reset_filters')}
                </button>
              )}
            </div>
          ) : (
            <div className="h-64 flex flex-col items-center justify-center text-center p-8 space-y-3">
              <div className="w-12 h-12 rounded-full bg-blue-50 dark:bg-slate-800 flex items-center justify-center text-[#0B57D0]">
                <Inbox className="w-6 h-6" />
              </div>
              <p className="text-sm font-semibold text-[#202124] dark:text-white">
                {t(language, 'no_messages_in_folder')}
              </p>
            </div>
          )
        ) : (
          filteredMessages
            .slice(
              (Math.min(currentPage, Math.max(1, Math.ceil(filteredMessages.length / pageSize))) - 1) * pageSize,
              Math.min(currentPage, Math.max(1, Math.ceil(filteredMessages.length / pageSize))) * pageSize
            )
            .map((msg) => {
            const isSelected = selectedMessageId === msg.id;
            const isChecked = selectedIds.has(msg.id);
            const isQuMail = isMessageQuMail(msg);
            const isPQC = msg.securityTier === 'pq_sealed' || (isQuMail && msg.securityTier !== 'weblink' && !msg.subject?.startsWith('[QuMail Secure Link]'));
            const isWebLink = msg.securityTier === 'weblink' || msg.securityMode === 'weblink' || Boolean(msg.subject?.startsWith('[QuMail Secure Link]'));

            // Clean sender display name
            const senderDisplayName = (msg.sender || msg.senderEmail?.split('@')[0] || 'Unknown').trim();

            // Clean display subject (strip bracketed tags like [Shield], [Shielded], [Quantum-Safe], etc. while preserving masking dots ••••••••)
            const { displaySubject, isCloaked } = resolveDisplaySubject(msg);
            const cleanSubject = (displaySubject || '(No Subject)')
              .replace(/\s*\[(Shield|Shielded|Quantum-Safe|QuMail Secure Link|Encrypted)\]\s*/gi, ' ')
              .trim() || '(No Subject)';

            // Single optional compact status pill
            let statusPill: React.ReactNode = null;
            if (msg.folder === 'outbox' && msg.outboxError) {
              statusPill = (
                <span
                  title={msg.outboxError}
                  className="shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded bg-rose-50 dark:bg-rose-950/60 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800"
                >
                  Send Failed
                </span>
              );
            } else if (msg.indicator?.badgeLevel === 'ALERT' || msg.snippet?.toLowerCase().includes('decryption error')) {
              statusPill = (
                <span
                  title="Message could not be decrypted with active keys"
                  className="shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded bg-rose-50 dark:bg-rose-950/60 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800"
                >
                  Decryption Failed
                </span>
              );
            } else if (isCloaked) {
              statusPill = (
                <span
                  title="Subject line was hidden from mail servers for privacy"
                  className="shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800"
                >
                  Hidden Subject
                </span>
              );
            }

            // Preview snippet text
            let previewText = '';
            if (maskEncryptedSnippets && isQuMail) {
              previewText = 'Encrypted message';
            } else if (!isQuMail) {
              const isGmail =
                msg.senderEmail?.toLowerCase().includes('gmail') ||
                msg.recipients?.some((r) => r.toLowerCase().includes('gmail')) ||
                true;
              previewText = isGmail ? 'Standard email · View in Gmail' : 'Standard email · View in webmail';
            } else if (msg.snippet) {
              previewText = msg.snippet.trim();
            }

            return (
              <SpotlightCard
                key={msg.id}
                onClick={() => onSelectMessage(msg)}
                onContextMenu={(e: React.MouseEvent) => handleContextMenu(e, msg)}
                className={`group flex items-center px-4 overflow-hidden w-full ${
                  listDensity === 'compact'
                    ? 'py-1.5'
                    : listDensity === 'cozy'
                    ? 'py-2.5'
                    : 'py-3'
                } cursor-pointer transition-all duration-150 select-none ${
                  isSelected
                    ? 'qumail-accent-soft font-semibold border-l-4 qumail-accent-border'
                    : !msg.seen
                    ? 'bg-white dark:bg-[#161F33] text-[#202124] dark:text-white'
                    : 'bg-[#F9FAFC] dark:bg-[#111726]/60 text-[#5F6368] dark:text-[#94A3B8] hover:bg-[#F2F6FC] dark:hover:bg-[#1E2740]/70'
                }`}
              >
                {/* 1. Left Cluster (Fixed Width — Never Wraps or Shrinks) */}
                <div className="flex items-center space-x-1.5 mr-2 shrink-0" onClick={(e) => e.stopPropagation()}>
                  <div
                    className={`transition-opacity duration-150 ${
                      selectedIds.size > 0 || isChecked
                        ? 'opacity-100'
                        : 'opacity-0 group-hover:opacity-100'
                    }`}
                  >
                    <CustomCheckbox
                      checked={isChecked}
                      onClick={(e) => handleToggleRowSelect(msg.id, e)}
                      title={isChecked ? 'Deselect message' : 'Select message'}
                    />
                  </div>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onToggleStar(msg.id, e);
                    }}
                    className="p-0.5 text-gray-400 hover:text-amber-400 transition-colors cursor-pointer rounded flex items-center justify-center shrink-0"
                    title={msg.starred ? 'Starred' : 'Not starred'}
                  >
                    <UseAnimations
                      animation={star}
                      size={22}
                      active={msg.starred}
                      strokeColor={msg.starred ? '#f59e0b' : 'currentColor'}
                      fillColor={msg.starred ? '#f59e0b' : 'transparent'}
                    />
                  </button>
                </div>

                {/* Compact Security Icon Only */}
                {isPQC ? (
                  <span
                    title="Quantum-Safe Private (ML-KEM-768 sealed)"
                    className="shrink-0 text-emerald-600 dark:text-emerald-400 mr-2 flex items-center justify-center"
                  >
                    <ShieldCheck className="w-4 h-4" />
                  </span>
                ) : isWebLink ? (
                  <span
                    title="Secure Private Link (Zero-Knowledge)"
                    className="shrink-0 text-sky-500 dark:text-sky-400 mr-2 flex items-center justify-center"
                  >
                    <Lock className="w-3.5 h-3.5" />
                  </span>
                ) : null}

                {/* Sender Name (w-44 / 176px fixed, truncate) */}
                <div className="w-44 shrink-0 flex items-center space-x-1.5 truncate pr-2">
                  {showSenderAvatars && (
                    (userEmail && msg.senderEmail && userEmail.toLowerCase() === msg.senderEmail.toLowerCase() && userAvatarUrl) ? (
                      <img
                        src={userAvatarUrl}
                        alt={senderDisplayName}
                        referrerPolicy="no-referrer"
                        crossOrigin="anonymous"
                        className={`shrink-0 rounded-full object-cover shadow-xs border border-indigo-200 dark:border-indigo-800 ${
                          listDensity === 'compact' ? 'w-5 h-5' : 'w-6 h-6'
                        }`}
                      />
                    ) : (
                      <div
                        className={`shrink-0 rounded-full flex items-center justify-center font-bold text-[10px] qumail-accent-soft qumail-accent-text ${
                          listDensity === 'compact' ? 'w-5 h-5' : 'w-6 h-6'
                        }`}
                      >
                        {senderDisplayName
                          .split(' ')
                          .filter(Boolean)
                          .slice(0, 2)
                          .map((p) => p[0]?.toUpperCase() || '')
                          .join('') || '?'}
                      </div>
                    )
                  )}
                  <span
                    className={`text-sm truncate ${
                      !msg.seen ? 'text-[#202124] dark:text-white font-bold' : 'text-[#444746] dark:text-[#C4C7C5]'
                    }`}
                    title={msg.senderEmail ? `${senderDisplayName} <${msg.senderEmail}>` : senderDisplayName}
                  >
                    {senderDisplayName}
                  </span>
                  {(() => {
                    const normSubj = (cleanSubject || '')
                      .replace(/^((re|fwd):\s*)+/gi, '')
                      .trim()
                      .toLowerCase();
                    const threadKey = msg.threadId || (normSubj ? `${msg.folder || 'inbox'}:${normSubj}` : '');
                    const threadCount = threadKey ? (threadCounts.get(threadKey) || 1) : 1;
                    return threadCount > 1 ? (
                      <span
                        title={`${threadCount} messages in conversation`}
                        className="shrink-0 text-[10px] font-bold text-slate-500 dark:text-slate-400 bg-black/5 dark:bg-white/10 px-1.5 py-0.2 rounded-full select-none"
                      >
                        {threadCount}
                      </span>
                    ) : null;
                  })()}
                </div>

                {/* 2. Center Cluster (flex-1 min-w-0 flex items-center gap-2 — Single Clean Line) */}
                <div className="flex-1 min-w-0 flex items-center gap-2 overflow-hidden pr-3">
                  <span
                    className={`text-sm truncate shrink-0 max-w-[65%] ${
                      !msg.seen
                        ? 'text-[#202124] dark:text-white font-medium'
                        : 'text-[#3C4043] dark:text-[#CBD5E1] font-normal'
                    }`}
                  >
                    {cleanSubject}
                  </span>
                  {statusPill}
                  {previewText && (
                    <span className="text-xs text-slate-400 dark:text-slate-500 truncate font-normal">
                      {previewText}
                    </span>
                  )}
                </div>

                {/* 3. Right Cluster (Fixed Width — Clean Date / Hover Actions) */}
                <div
                  className="shrink-0 flex items-center justify-end w-28 text-right"
                  onClick={(e) => e.stopPropagation()}
                >
                  {/* Default View: Paperclip + Timestamp */}
                  {msg.hasAttachments && (
                    <Paperclip className="w-3.5 h-3.5 text-[#5F6368] dark:text-[#94A3B8] mr-2 shrink-0 group-hover:hidden" />
                  )}
                  <span
                    className={`text-xs whitespace-nowrap group-hover:hidden ${
                      !msg.seen
                        ? 'text-[#0B57D0] dark:text-[#818CF8] font-bold'
                        : 'text-[#5F6368] dark:text-[#94A3B8]'
                    }`}
                  >
                    {msg.date}
                  </span>

                  {/* Hover View: Smoothly swapped quick action buttons */}
                  <div className="hidden group-hover:flex items-center space-x-1">
                    {msg.folder === 'outbox' && onRetrySend && (
                      <button
                        type="button"
                        onClick={(e) => onRetrySend(msg, e)}
                        title="Retry Send"
                        className="p-1 rounded-md text-blue-600 hover:bg-blue-100 dark:hover:bg-blue-900/40 cursor-pointer"
                      >
                        <RotateCw className="w-3.5 h-3.5" />
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={(e) => onMarkRead(msg.id, !msg.seen, e)}
                      title={msg.seen ? 'Mark as unread (U)' : 'Mark as read (U)'}
                      className="p-1.5 rounded-full text-gray-500 dark:text-gray-400 hover:text-[#0B57D0] dark:hover:text-[#818CF8] hover:bg-blue-50 dark:hover:bg-blue-950/40 transition-colors cursor-pointer"
                    >
                      {msg.seen ? <Mail className="w-3.5 h-3.5" /> : <MailOpen className="w-3.5 h-3.5" />}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        if (!isQuMail) {
                          onShowProtectionNotice?.('Safe Deletion Guard: Standard legacy emails cannot be deleted by QuMail.');
                          return;
                        }
                        onDeleteMessage(msg.id);
                      }}
                      disabled={!isQuMail}
                      title={isQuMail ? 'Delete QuMail message' : 'Protected: Standard emails cannot be deleted'}
                      className={`p-1.5 rounded-full transition-colors ${
                        isQuMail
                          ? 'text-gray-500 dark:text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/40 cursor-pointer'
                          : 'text-gray-300 dark:text-gray-600 opacity-20 cursor-not-allowed hover:bg-transparent'
                      }`}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </SpotlightCard>
            );
          })
        )}
      </div>

      {/* Right-Click Context Menu */}
      {contextMenu && (() => {
        const ctxMsg = contextMenu.msg;
        const ctxIsQuMail = isMessageQuMail(ctxMsg);
        return (
          <div
            style={{ top: contextMenu.y, left: contextMenu.x }}
            onClick={(e) => e.stopPropagation()}
            className="fixed z-50 w-52 py-1.5 rounded-xl bg-white dark:bg-[#1E293B] border border-[#E0E3E7] dark:border-[#334155] shadow-2xl text-xs font-medium text-[#202124] dark:text-[#F1F5F9] select-none animate-in fade-in zoom-in-95 duration-100"
          >
            <button
              onClick={(e) => {
                onToggleStar(ctxMsg.id, e);
                setContextMenu(null);
              }}
              className="w-full px-3.5 py-2 flex items-center space-x-2.5 hover:bg-gray-100 dark:hover:bg-slate-700/60 transition-colors cursor-pointer text-left"
            >
              <Star className={`w-4 h-4 ${ctxMsg.starred ? 'fill-amber-400 text-amber-400' : 'text-gray-500 dark:text-gray-400'}`} />
              <span>{ctxMsg.starred ? 'Remove star' : 'Add star'}</span>
            </button>
            <button
              onClick={(e) => {
                onMarkRead(ctxMsg.id, !ctxMsg.seen, e);
                setContextMenu(null);
              }}
              className="w-full px-3.5 py-2 flex items-center space-x-2.5 hover:bg-gray-100 dark:hover:bg-slate-700/60 transition-colors cursor-pointer text-left"
            >
              {ctxMsg.seen ? (
                <>
                  <Mail className="w-4 h-4 text-gray-500 dark:text-gray-400" />
                  <span>Mark as unread</span>
                </>
              ) : (
                <>
                  <MailOpen className="w-4 h-4 text-gray-500 dark:text-gray-400" />
                  <span>Mark as read</span>
                </>
              )}
            </button>
            <div className="my-1 border-t border-gray-200 dark:border-slate-700" />
            <button
              onClick={() => {
                if (!ctxIsQuMail) {
                  onShowProtectionNotice?.("Safe Deletion Guard: Standard legacy emails cannot be deleted by QuMail.");
                  setContextMenu(null);
                  return;
                }
                onDeleteMessage(ctxMsg.id);
                setContextMenu(null);
              }}
              title={ctxIsQuMail ? "Move QuMail message to Trash" : "Deletion Protected: Standard email cannot be deleted by QuMail"}
              className={`w-full px-3.5 py-2 flex items-center space-x-2.5 transition-colors text-left ${
                ctxIsQuMail
                  ? 'text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/40 cursor-pointer'
                  : 'text-gray-400 dark:text-gray-500 opacity-50 cursor-not-allowed'
              }`}
            >
              <Trash2 className="w-4 h-4" />
              <span>{ctxIsQuMail ? 'Move to Trash' : 'Move to Trash (Protected)'}</span>
            </button>
          </div>
        );
      })()}
    </div>
  );
};
