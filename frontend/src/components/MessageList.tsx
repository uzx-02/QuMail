import React, { useState, useEffect } from 'react';
import { RefreshCw, Trash2, Mail, MailOpen, Star, Paperclip, ShieldCheck, AlertTriangle, ShieldAlert, Inbox, Shield, Lock, CheckCircle2, RotateCw } from 'lucide-react';
import { EmailMessage } from '../types';
import { SpotlightCard } from './reactbits/SpotlightCard';

interface MessageListProps {
  messages: EmailMessage[];
  selectedMessageId: string | null;
  onSelectMessage: (msg: EmailMessage) => void;
  onToggleStar: (id: string, e: React.MouseEvent) => void;
  onRefresh: () => void;
  onDeleteMessage: (id: string, e?: React.MouseEvent) => void;
  onMarkRead: (id: string, seen: boolean, e?: React.MouseEvent) => void;
  isRefreshing: boolean;
  currentFolder?: string;
  onRetrySend?: (msg: EmailMessage, e: React.MouseEvent) => void;
  filterMode?: 'all' | 'secure' | 'unread';
  onFilterChange?: (filter: 'all' | 'secure' | 'unread') => void;
  onShowProtectionNotice?: (msg: string) => void;
  maskEncryptedSnippets?: boolean;
  listDensity?: 'comfortable' | 'compact';
}

export const MessageList: React.FC<MessageListProps> = ({
  messages,
  selectedMessageId,
  onSelectMessage,
  onToggleStar,
  onRefresh,
  onDeleteMessage,
  onMarkRead,
  isRefreshing,
  currentFolder,
  onRetrySend,
  filterMode = 'all',
  onFilterChange,
  onShowProtectionNotice,
  maskEncryptedSnippets = false,
  listDensity = 'comfortable',
}) => {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [activeFilter, setActiveFilter] = useState<'all' | 'secure' | 'unread'>(filterMode);
  const [contextMenu, setContextMenu] = useState<{ msg: EmailMessage; x: number; y: number } | null>(null);

  useEffect(() => {
    setActiveFilter(filterMode);
  }, [filterMode]);

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

  const filteredMessages = messages.filter((m) => {
    if (activeFilter === 'secure') {
      return isMessageQuMail(m);
    }
    if (activeFilter === 'unread') {
      return !m.seen;
    }
    return true;
  });

  const handleSelectAll = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.checked) {
      setSelectedIds(new Set(filteredMessages.map((m) => m.id)));
    } else {
      setSelectedIds(new Set());
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

  const renderSecurityBadge = (msg: EmailMessage) => {
    const isPQC = msg.securityTier === 'pq_sealed' || (isMessageQuMail(msg) && msg.securityTier !== 'weblink' && !msg.subject?.startsWith('[QuMail Secure Link]'));
    const isWebLink = msg.securityTier === 'weblink' || msg.securityMode === 'weblink' || msg.subject?.startsWith('[QuMail Secure Link]');

    if (isPQC) {
      return (
        <div className="flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 dark:bg-emerald-950/70 text-emerald-800 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800 shrink-0">
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
          <span>Verified PQC</span>
        </div>
      );
    }

    if (isWebLink) {
      return (
        <div className="flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-cyan-100 dark:bg-cyan-950/70 text-cyan-800 dark:text-cyan-300 border border-cyan-300 dark:border-cyan-800 shrink-0">
          <Lock className="w-3.5 h-3.5 text-cyan-600 dark:text-cyan-400" />
          <span>Secure WebLink</span>
        </div>
      );
    }

    return (
      <div className="flex items-center space-x-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-slate-100 dark:bg-slate-800/80 text-slate-500 dark:text-slate-400 border border-slate-200 dark:border-slate-700/80 shrink-0">
        <Shield className="w-3 h-3 text-slate-400" />
        <span>Standard TLS</span>
      </div>
    );
  };

  const filterPills: { id: 'all' | 'secure' | 'unread'; label: string; icon: React.ReactNode; count: number }[] = [
    { id: 'all', label: 'All', icon: <Inbox className="w-3.5 h-3.5" />, count: messages.length },
    {
      id: 'secure',
      label: 'QuMail Secure',
      icon: <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />,
      count: messages.filter(isMessageQuMail).length,
    },
    {
      id: 'unread',
      label: 'Unread',
      icon: <Mail className="w-3.5 h-3.5 text-blue-500" />,
      count: messages.filter((m) => !m.seen).length,
    },
  ];

  return (
    <div className="flex-1 flex flex-col h-full bg-white dark:bg-[#161F33] overflow-hidden border-r border-[#E0E3E7] dark:border-[#1F2C47]">
      {/* 1. Top Mailbox Toolbar */}
      <div className="h-12 px-4 flex items-center justify-between border-b border-[#E0E3E7] dark:border-[#1F2C47] shrink-0 select-none bg-white dark:bg-[#161F33]">
        <div className="flex items-center space-x-2">
          <input
            type="checkbox"
            checked={filteredMessages.length > 0 && selectedIds.size === filteredMessages.length}
            onChange={handleSelectAll}
            className="w-4 h-4 rounded border-gray-300 dark:border-gray-600 text-[#0B57D0] focus:ring-[#0B57D0] cursor-pointer"
          />

          <button
            onClick={onRefresh}
            title="Refresh mail"
            className="p-2 rounded-full text-[#5F6368] dark:text-[#94A3B8] hover:bg-[#F2F6FC] dark:hover:bg-[#1E2740] hover:text-[#202124] transition-colors outline-none"
          >
            <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin text-[#0B57D0]' : ''}`} />
          </button>

          {selectedIds.size > 0 && (
            <div className="flex items-center space-x-1 pl-2 border-l border-gray-200 dark:border-gray-700">
              <button
                onClick={() => handleBatchMarkRead(true)}
                title="Mark as read"
                className="p-2 rounded-full text-[#5F6368] dark:text-[#94A3B8] hover:bg-[#F2F6FC] dark:hover:bg-[#1E2740] transition-colors"
              >
                <MailOpen className="w-4 h-4" />
              </button>
              <button
                onClick={() => handleBatchMarkRead(false)}
                title="Mark as unread"
                className="p-2 rounded-full text-[#5F6368] dark:text-[#94A3B8] hover:bg-[#F2F6FC] dark:hover:bg-[#1E2740] transition-colors"
              >
                <Mail className="w-4 h-4" />
              </button>
              <button
                onClick={handleBatchDelete}
                title="Delete selected (QuMail only)"
                className="p-2 rounded-full text-[#5F6368] dark:text-[#94A3B8] hover:bg-red-50 dark:hover:bg-red-950/40 hover:text-red-600 transition-colors"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>

        <div className="text-xs text-[#5F6368] dark:text-[#94A3B8] font-medium">
          {filteredMessages.length > 0 ? `1–${filteredMessages.length} of ${filteredMessages.length}` : '0 messages'}
        </div>
      </div>

      {/* 2. Modern Filter Pills (All | QuMail Secure | Unread) */}
      <div className="border-b border-[#E0E3E7] dark:border-[#1F2C47] px-4 py-2.5 bg-white dark:bg-[#161F33] shrink-0 flex items-center space-x-2">
        {filterPills.map((pill) => {
          const isActive = activeFilter === pill.id;
          return (
            <button
              key={pill.id}
              onClick={() => handleFilterSelect(pill.id)}
              className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-full text-xs font-semibold transition-all duration-150 outline-none ${
                isActive
                  ? 'bg-[#0B57D0] text-white shadow-sm'
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

      {/* Synchronization Progress Line */}
      {isRefreshing && (
        <div className="h-0.5 w-full bg-blue-100 dark:bg-blue-950 overflow-hidden shrink-0">
          <div className="h-full bg-blue-600 dark:bg-blue-400 animate-pulse w-full" />
        </div>
      )}

      {/* 3. Messages List */}
      <div className="flex-1 overflow-y-auto divide-y divide-[#F2F2F2] dark:divide-[#1F2C47]/60">
        {filteredMessages.length === 0 ? (
          currentFolder === 'outbox' ? (
            <div className="h-64 flex flex-col items-center justify-center text-center p-8 space-y-3">
              <div className="w-12 h-12 rounded-full bg-emerald-50 dark:bg-emerald-950/50 flex items-center justify-center text-emerald-600 dark:text-emerald-400">
                <CheckCircle2 className="w-6 h-6" />
              </div>
              <p className="text-sm font-semibold text-[#202124] dark:text-white">
                Outbox is clear
              </p>
              <p className="text-xs text-[#5F6368] dark:text-[#94A3B8] max-w-sm">
                All Post-Quantum & WebLink messages have been dispatched cleanly. Failed or offline sends will appear here with a Retry Send option.
              </p>
            </div>
          ) : (
            <div className="h-64 flex flex-col items-center justify-center text-center p-8 space-y-3">
              <div className="w-12 h-12 rounded-full bg-blue-50 dark:bg-slate-800 flex items-center justify-center text-[#0B57D0]">
                <Inbox className="w-6 h-6" />
              </div>
              <p className="text-sm font-semibold text-[#202124] dark:text-white">
                No messages found
              </p>
              <p className="text-xs text-[#5F6368] dark:text-[#94A3B8] max-w-xs">
                All messages have been processed or moved to other categories.
              </p>
            </div>
          )
        ) : (
          filteredMessages.map((msg) => {
            const isSelected = selectedMessageId === msg.id;
            const isChecked = selectedIds.has(msg.id);
            const isQuMail = isMessageQuMail(msg);

            return (
              <SpotlightCard
                key={msg.id}
                onClick={() => onSelectMessage(msg)}
                onContextMenu={(e: React.MouseEvent) => handleContextMenu(e, msg)}
                className={`group flex items-center px-4 ${
                  listDensity === 'compact' ? 'py-1.5' : 'py-3'
                } cursor-pointer transition-all duration-150 select-none ${
                  isSelected
                    ? 'bg-[#D3E3FD]/60 dark:bg-[#2C3D63]/70 font-semibold border-l-4 border-l-[#0B57D0]'
                    : !msg.seen
                    ? 'bg-white dark:bg-[#161F33] font-semibold text-[#202124] dark:text-white'
                    : 'bg-[#F9FAFC] dark:bg-[#111726]/60 text-[#5F6368] dark:text-[#94A3B8] font-normal hover:bg-[#F2F6FC] dark:hover:bg-[#1E2740]/70'
                }`}
              >
                {/* Row Checkbox & Star */}
                <div className="flex items-center space-x-2 mr-3 shrink-0" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={(e) => handleToggleRowSelect(msg.id, e as any)}
                    className="w-4 h-4 rounded border-gray-300 dark:border-gray-600 text-[#0B57D0] focus:ring-[#0B57D0] cursor-pointer"
                  />
                  <button
                    onClick={(e) => onToggleStar(msg.id, e)}
                    className="p-1 text-gray-400 hover:text-amber-400 transition-colors"
                  >
                    <Star
                      className={`w-4 h-4 ${
                        msg.starred ? 'fill-amber-400 text-amber-400' : 'text-gray-300 dark:text-gray-600'
                      }`}
                    />
                  </button>
                </div>

                {/* Sender Column */}
                <div className="w-44 truncate shrink-0 pr-2">
                  <span
                    className={`text-sm ${
                      !msg.seen ? 'text-[#202124] dark:text-white font-bold' : 'text-[#444746] dark:text-[#C4C7C5]'
                    }`}
                  >
                    {msg.sender}
                  </span>
                </div>

                {/* Inline Subject + Snippet */}
                <div className="flex-1 flex items-center truncate min-w-0 pr-4">
                  <span
                    className={`text-sm truncate ${
                      !msg.seen ? 'text-[#202124] dark:text-white font-bold' : 'text-[#202124] dark:text-[#E2E8F0]'
                    }`}
                  >
                    {msg.subject || '(No Subject)'}
                  </span>
                  <span className="mx-2 text-gray-400 shrink-0">—</span>
                  <span className="text-sm text-[#5F6368] dark:text-[#94A3B8] truncate font-normal">
                    {maskEncryptedSnippets && isQuMail
                      ? '•••••••• (Encrypted snippet hidden)'
                      : msg.snippet}
                  </span>
                </div>

                {/* Badges: Paperclip, Outbox Retry & Distinct Security Badge */}
                <div className="flex items-center space-x-2 shrink-0 mr-3">
                  {msg.folder === 'outbox' && (
                    <div className="flex items-center space-x-2" onClick={(e) => e.stopPropagation()}>
                      {msg.outboxError && (
                        <span
                          title={msg.outboxError}
                          className="max-w-[180px] truncate px-2 py-0.5 rounded-full text-[10px] font-semibold bg-rose-50 dark:bg-rose-950/60 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800"
                        >
                          {msg.outboxError}
                        </span>
                      )}
                      {onRetrySend && (
                        <button
                          onClick={(e) => onRetrySend(msg, e)}
                          className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full text-[11px] font-bold bg-[#0B57D0] hover:bg-[#0842A0] text-white shadow-sm transition-colors cursor-pointer"
                          title="Retry SMTP dispatch"
                        >
                          <RotateCw className="w-3 h-3" />
                          <span>Retry Send</span>
                        </button>
                      )}
                    </div>
                  )}
                  {msg.hasAttachments && (
                    <Paperclip className="w-4 h-4 text-[#5F6368] dark:text-[#94A3B8]" />
                  )}
                  {renderSecurityBadge(msg)}
                </div>

                {/* Hover Quick Actions + Safe Trash */}
                <div
                  className="flex items-center space-x-1 shrink-0 mr-2 opacity-0 group-hover:opacity-100 transition-opacity duration-150"
                  onClick={(e) => e.stopPropagation()}
                >
                  <button
                    onClick={(e) => onToggleStar(msg.id, e)}
                    title={msg.starred ? "Remove star (S)" : "Star message (S)"}
                    className="p-1.5 rounded-full text-gray-400 hover:text-amber-500 hover:bg-amber-50 dark:hover:bg-amber-950/30 transition-colors cursor-pointer"
                  >
                    <Star
                      className={`w-3.5 h-3.5 ${
                        msg.starred ? "fill-amber-400 text-amber-400" : ""
                      }`}
                    />
                  </button>
                  <button
                    onClick={(e) => onMarkRead(msg.id, !msg.seen, e)}
                    title={msg.seen ? "Mark as unread (U)" : "Mark as read (U)"}
                    className="p-1.5 rounded-full text-gray-400 hover:text-[#0B57D0] dark:hover:text-[#818CF8] hover:bg-blue-50 dark:hover:bg-blue-950/30 transition-colors cursor-pointer"
                  >
                    {msg.seen ? <Mail className="w-3.5 h-3.5" /> : <MailOpen className="w-3.5 h-3.5" />}
                  </button>
                  <button
                    onClick={() => {
                      if (!isQuMail) {
                        onShowProtectionNotice?.("Deletion Protected: Standard legacy emails cannot be deleted by QuMail.");
                        return;
                      }
                      onDeleteMessage(msg.id);
                    }}
                    disabled={!isQuMail}
                    title={isQuMail ? "Delete QuMail message" : "Deletion Protected: Standard email cannot be deleted by QuMail"}
                    className={`p-1.5 rounded-full transition-colors ${
                      isQuMail
                        ? "text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/40 cursor-pointer"
                        : "text-gray-300 dark:text-gray-600 opacity-30 cursor-not-allowed hover:bg-transparent"
                    }`}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>

                {/* Date */}
                <div className="w-20 text-right shrink-0">
                  <span
                    className={`text-xs ${
                      !msg.seen
                        ? 'text-[#0B57D0] dark:text-[#818CF8] font-bold'
                        : 'text-[#5F6368] dark:text-[#94A3B8]'
                    }`}
                  >
                    {msg.date}
                  </span>
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
