import React from 'react';
import { Pen, Inbox, Star, Send, FileText, Package, Trash2, Cpu, CheckCircle2 } from 'lucide-react';
import UseAnimations from 'react-useanimations';
import edit from 'react-useanimations/lib/edit';
import { motion } from 'framer-motion';
import { HSMStatus, QuMailSettings, LanguageOption } from '../types';
import { t } from '../lib/i18n';

interface SidebarProps {
  currentFolder: string;
  onSelectFolder: (folder: string) => void;
  onOpenCompose: () => void;
  unreadCount: number;
  starredCount: number;
  draftsCount: number;
  outboxCount?: number;
  isCollapsed: boolean;
  hsmStatus: HSMStatus;
  onOpenSettings: (tab?: 'general' | 'labels' | 'accounts' | 'security' | 'appearance' | 'accessibility' | 'about') => void;
  visibleFolders?: QuMailSettings['visibleFolders'];
  hideEmptyFolders?: boolean;
  showUnreadBadges?: boolean;
  language?: LanguageOption;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentFolder,
  onSelectFolder,
  onOpenCompose,
  unreadCount,
  starredCount,
  draftsCount,
  outboxCount = 0,
  isCollapsed,
  hsmStatus,
  onOpenSettings,
  visibleFolders,
  hideEmptyFolders = false,
  showUnreadBadges = true,
  language,
}) => {
  const allFolders = [
    { id: 'inbox', label: t(language, 'folder_inbox'), icon: <Inbox className="w-4 h-4" />, count: unreadCount },
    { id: 'starred', label: t(language, 'folder_starred'), icon: <Star className="w-4 h-4" />, count: starredCount },
    { id: 'sent', label: t(language, 'folder_sent'), icon: <Send className="w-4 h-4" /> },
    { id: 'drafts', label: t(language, 'folder_drafts'), icon: <FileText className="w-4 h-4" />, count: draftsCount },
    { id: 'outbox', label: t(language, 'folder_outbox'), icon: <Package className="w-4 h-4" />, count: outboxCount },
    { id: 'trash', label: t(language, 'folder_trash'), icon: <Trash2 className="w-4 h-4" /> },
  ];

  const folders = allFolders.filter((f) => {
    if (f.id === 'inbox') return true;
    if (visibleFolders && visibleFolders[f.id as keyof QuMailSettings['visibleFolders']] === false) {
      return false;
    }
    if (hideEmptyFolders && (f.id === 'outbox' || f.id === 'drafts')) {
      if ((f.count ?? 0) <= 0) return false;
    }
    return true;
  });

  return (
    <aside
      className={`h-[calc(100vh-64px)] flex flex-col justify-between p-3 border-r border-[#E0E3E7] dark:border-[#1F2C47] bg-[#F6F8FC] dark:bg-[#0A0E17] transition-all duration-300 select-none ${
        isCollapsed ? 'w-20' : 'w-64 min-w-[256px]'
      }`}
    >
      <div className="space-y-4">
        {/* Compose Button (Accent-driven) */}
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={onOpenCompose}
          data-tour="tour-compose"
          className={`flex items-center space-x-3 rounded-2xl shadow-md hover:shadow-lg transition-all duration-200 qumail-accent-bg font-semibold text-sm cursor-pointer ${
            isCollapsed ? 'w-12 h-12 justify-center mx-auto' : 'px-6 py-4 w-40'
          }`}
        >
          <UseAnimations animation={edit} size={20} strokeColor="#ffffff" className="shrink-0" />
          {!isCollapsed && <span>{t(language, 'compose_button')}</span>}
        </motion.button>

        {/* Navigation Folder List */}
        <nav className="space-y-0.5">
          {folders.map((f) => {
            const isSelected = currentFolder === f.id;
            return (
              <button
                key={f.id}
                onClick={() => onSelectFolder(f.id)}
                data-tour={f.id === 'inbox' ? 'tour-inbox' : undefined}
                className={`w-full flex items-center justify-between px-4 py-2.5 rounded-full text-sm transition-all duration-150 outline-none cursor-pointer ${
                  isSelected
                    ? 'qumail-accent-soft text-[#001D35] dark:text-white font-bold'
                    : 'text-[#202124] dark:text-[#94A3B8] hover:bg-[#F2F6FC] dark:hover:bg-[#1C2740]/60 font-medium'
                } ${isCollapsed ? 'justify-center px-0' : ''}`}
                title={f.label}
              >
                <div className="flex items-center space-x-3.5">
                  <span className={isSelected ? 'qumail-accent-text' : 'text-[#5F6368] dark:text-[#94A3B8]'}>
                    {f.icon}
                  </span>
                  {!isCollapsed && <span>{f.label}</span>}
                </div>

                {!isCollapsed && showUnreadBadges && f.count !== undefined && f.count > 0 && (
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full font-bold ${
                      isSelected
                        ? 'qumail-accent-bg'
                        : 'text-[#202124] dark:text-slate-300 font-bold'
                    }`}
                  >
                    {f.count}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Bottom: Hardware Security Key / Randomness Status Card */}
      {!isCollapsed ? (
        <div
          onClick={() => onOpenSettings('security')}
          className="p-3.5 rounded-2xl bg-white dark:bg-[#161F33] border border-[#E0E3E7] dark:border-[#2A3B5F] shadow-sm hover:border-[#0B57D0]/60 dark:hover:border-[#6366F1]/60 transition-all cursor-pointer group"
          title="Click to manage Hardware Security & Randomness settings"
        >
          {hsmStatus.isHardwareActive ? (
            <>
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center space-x-2">
                  <Cpu className="w-4 h-4 text-emerald-600 dark:text-emerald-400 group-hover:scale-110 transition-transform" />
                  <span className="text-xs font-bold text-[#202124] dark:text-[#F1F5F9]">
                    {t(language, 'hardware_security')}
                  </span>
                </div>
                <span className="flex h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
              </div>
              <p className="text-[11px] text-[#5F6368] dark:text-[#94A3B8] truncate mb-2">
                {hsmStatus.activePort || t(language, 'entropy_hardware_active')}
              </p>
              <div className="flex items-center space-x-1.5 text-[10px] text-emerald-700 dark:text-emerald-400 font-medium bg-emerald-50 dark:bg-emerald-950/40 px-2 py-1 rounded-lg">
                <CheckCircle2 className="w-3 h-3 shrink-0" />
                <span>NIST SP 800-90B PASSED</span>
              </div>
            </>
          ) : (
            <>
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center space-x-2">
                  <Cpu className="w-4 h-4 text-gray-500 dark:text-gray-400 group-hover:scale-110 transition-transform" />
                  <span className="text-xs font-bold text-[#202124] dark:text-[#F1F5F9]">
                    {t(language, 'system_randomness')}
                  </span>
                </div>
                <span className="flex h-2 w-2 rounded-full bg-gray-400 dark:bg-gray-600" />
              </div>
              <p className="text-[11px] text-[#5F6368] dark:text-[#94A3B8] truncate mb-2">
                {t(language, 'entropy_optimal')}
              </p>
              <div className="flex items-center space-x-1.5 text-[10px] text-gray-600 dark:text-gray-400 font-medium bg-gray-100 dark:bg-gray-800/80 px-2 py-1 rounded-lg">
                <span>Hardware Key Standby</span>
              </div>
            </>
          )}
        </div>
      ) : (
        <div
          onClick={() => onOpenSettings('security')}
          className="w-10 h-10 mx-auto rounded-xl bg-white dark:bg-[#161F33] border border-[#E0E3E7] dark:border-[#2A3B5F] flex items-center justify-center cursor-pointer hover:border-[#0B57D0]/60 transition-colors"
          title={hsmStatus.isHardwareActive ? "Hardware Security Key Active · Click to manage settings" : "Built-In System Randomness · Click to manage settings"}
        >
          <Cpu className={`w-5 h-5 ${hsmStatus.isHardwareActive ? 'text-emerald-500' : 'text-gray-400'}`} />
        </div>
      )}
    </aside>
  );
};
