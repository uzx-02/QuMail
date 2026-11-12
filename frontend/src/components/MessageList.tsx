import React, { useState } from 'react';
import { RefreshCw, Trash2, Mail, MailOpen, Star, Paperclip, ShieldCheck, AlertTriangle, ShieldAlert, Inbox, Bell, Shield } from 'lucide-react';
import { EmailMessage } from '../types';
import { AnimatedTabs, TabItem } from './reactbits/AnimatedTabs';
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
  categoryFilter: 'primary' | 'updates' | 'secure';
  onCategoryChange: (cat: 'primary' | 'updates' | 'secure') => void;
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
  categoryFilter,
  onCategoryChange,
}) => {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const categoryTabs: TabItem[] = [
    { id: 'primary', label: 'Primary', icon: <Inbox className="w-4 h-4" /> },
    { id: 'updates', label: 'Updates', icon: <Bell className="w-4 h-4" /> },
    { id: 'secure', label: 'Quantum Secured', icon: <Shield className="w-4 h-4" /> },
  ];

  const filteredMessages = messages.filter((m) => {
    if (categoryFilter === 'secure') {
      return m.indicator?.badgeLevel === 'SECURE';
    }
    return m.category === categoryFilter || (categoryFilter === 'primary' && !m.category);
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
    selectedIds.forEach((id) => onDeleteMessage(id));
    setSelectedIds(new Set());
  };

  const handleBatchMarkRead = (seen: boolean) => {
    selectedIds.forEach((id) => onMarkRead(id, seen));
    setSelectedIds(new Set());
  };

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
                title="Delete selected"
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

      {/* 2. Category Tabs */}
      <div className="border-b border-[#E0E3E7] dark:border-[#1F2C47] px-4 bg-white dark:bg-[#161F33] shrink-0">
        <AnimatedTabs
          tabs={categoryTabs}
          activeTab={categoryFilter}
          onChange={(id) => onCategoryChange(id as 'primary' | 'updates' | 'secure')}
        />
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
          <div className="h-64 flex flex-col items-center justify-center text-center p-8 space-y-3">
            <div className="w-12 h-12 rounded-full bg-blue-50 dark:bg-slate-800 flex items-center justify-center text-[#0B57D0]">
              <Inbox className="w-6 h-6" />
            </div>
            <p className="text-sm font-semibold text-[#202124] dark:text-[#F1F5F9]">
              Your inbox is clear in this category
            </p>
            <p className="text-xs text-[#5F6368] dark:text-[#94A3B8] max-w-xs">
              All messages have been processed or moved to other categories.
            </p>
          </div>
        ) : (
          filteredMessages.map((msg) => {
            const isSelected = selectedMessageId === msg.id;
            const isChecked = selectedIds.has(msg.id);
            return (
              <SpotlightCard
                key={msg.id}
                onClick={() => onSelectMessage(msg)}
                className={`group flex items-center px-4 py-3 cursor-pointer transition-all duration-150 select-none ${
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
                    {msg.snippet}
                  </span>
                </div>

                {/* Badges: Paperclip & PQC Security Pill */}
                <div className="flex items-center space-x-2 shrink-0 mr-4">
                  {msg.hasAttachments && (
                    <Paperclip className="w-4 h-4 text-[#5F6368] dark:text-[#94A3B8]" />
                  )}

                  {msg.indicator && (
                    <div
                      className={`flex items-center space-x-1 px-2 py-0.5 rounded-full text-[11px] font-bold ${
                        msg.indicator.badgeLevel === 'SECURE'
                          ? 'bg-emerald-100 dark:bg-emerald-950/70 text-emerald-800 dark:text-emerald-300'
                          : msg.indicator.badgeLevel === 'CAUTION'
                          ? 'bg-amber-100 dark:bg-amber-950/70 text-amber-800 dark:text-amber-300'
                          : msg.indicator.badgeLevel === 'NEUTRAL'
                          ? 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300'
                          : 'bg-red-100 dark:bg-red-950/70 text-red-800 dark:text-red-300'
                      }`}
                    >
                      {msg.indicator.badgeLevel === 'SECURE' ? (
                        <ShieldCheck className="w-3 h-3 text-emerald-600" />
                      ) : msg.indicator.badgeLevel === 'CAUTION' ? (
                        <AlertTriangle className="w-3 h-3 text-amber-600" />
                      ) : msg.indicator.badgeLevel === 'NEUTRAL' ? (
                        <Shield className="w-3 h-3 text-slate-500 dark:text-slate-400" />
                      ) : (
                        <ShieldAlert className="w-3 h-3 text-red-600" />
                      )}
                      <span>
                        {msg.indicator.badgeLevel === 'SECURE'
                          ? 'Verified PQC'
                          : msg.indicator.badgeLevel === 'CAUTION'
                          ? 'Encrypted'
                          : msg.indicator.badgeLevel === 'NEUTRAL'
                          ? 'Shielded'
                          : 'Alert'}
                      </span>
                    </div>
                  )}
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
    </div>
  );
};
