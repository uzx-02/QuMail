import React from 'react';
import { Pen, Inbox, Star, Send, FileText, Package, Trash2, Cpu, CheckCircle2 } from 'lucide-react';
import { motion } from 'framer-motion';
import { HSMStatus } from '../types';

interface SidebarProps {
  currentFolder: string;
  onSelectFolder: (folder: string) => void;
  onOpenCompose: () => void;
  unreadCount: number;
  starredCount: number;
  draftsCount: number;
  isCollapsed: boolean;
  hsmStatus: HSMStatus;
  onOpenSettings: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentFolder,
  onSelectFolder,
  onOpenCompose,
  unreadCount,
  starredCount,
  draftsCount,
  isCollapsed,
  hsmStatus,
  onOpenSettings,
}) => {
  const folders = [
    { id: 'inbox', label: 'Inbox', icon: <Inbox className="w-4 h-4" />, count: unreadCount },
    { id: 'starred', label: 'Starred', icon: <Star className="w-4 h-4" />, count: starredCount },
    { id: 'sent', label: 'Sent', icon: <Send className="w-4 h-4" /> },
    { id: 'drafts', label: 'Drafts', icon: <FileText className="w-4 h-4" />, count: draftsCount },
    { id: 'outbox', label: 'Outbox', icon: <Package className="w-4 h-4" /> },
    { id: 'trash', label: 'Trash', icon: <Trash2 className="w-4 h-4" /> },
  ];

  return (
    <aside
      className={`h-[calc(100vh-64px)] flex flex-col justify-between p-3 border-r border-[#E0E3E7] dark:border-[#1F2C47] bg-[#F6F8FC] dark:bg-[#0A0E17] transition-all duration-300 select-none ${
        isCollapsed ? 'w-20' : 'w-64 min-w-[256px]'
      }`}
    >
      <div className="space-y-4">
        {/* Gmail Compose Button */}
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={onOpenCompose}
          className={`flex items-center space-x-3 rounded-2xl shadow-md hover:shadow-lg transition-all duration-200 bg-[#C2E7FF] hover:bg-[#B3DCF5] text-[#001D35] font-semibold text-sm ${
            isCollapsed ? 'w-12 h-12 justify-center mx-auto' : 'px-6 py-4 w-40'
          }`}
        >
          <Pen className="w-5 h-5 shrink-0 text-[#001D35]" />
          {!isCollapsed && <span>Compose</span>}
        </motion.button>

        {/* Navigation Folder List */}
        <nav className="space-y-0.5">
          {folders.map((f) => {
            const isSelected = currentFolder === f.id;
            return (
              <button
                key={f.id}
                onClick={() => onSelectFolder(f.id)}
                className={`w-full flex items-center justify-between px-4 py-2.5 rounded-full text-sm transition-all duration-150 outline-none ${
                  isSelected
                    ? 'bg-[#D3E3FD] dark:bg-[#2C3D63] text-[#001D35] dark:text-white font-bold'
                    : 'text-[#202124] dark:text-[#94A3B8] hover:bg-[#F2F6FC] dark:hover:bg-[#1C2740]/60 font-medium'
                } ${isCollapsed ? 'justify-center px-0' : ''}`}
                title={f.label}
              >
                <div className="flex items-center space-x-3.5">
                  <span className={isSelected ? 'text-[#0B57D0] dark:text-[#818CF8]' : 'text-[#5F6368] dark:text-[#94A3B8]'}>
                    {f.icon}
                  </span>
                  {!isCollapsed && <span>{f.label}</span>}
                </div>

                {!isCollapsed && f.count !== undefined && f.count > 0 && (
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full font-bold ${
                      isSelected
                        ? 'bg-[#0B57D0] text-white'
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

      {/* Bottom: Hardware TRNG Health Card */}
      {!isCollapsed ? (
        <div
          onClick={onOpenSettings}
          className="p-3.5 rounded-2xl bg-white dark:bg-[#161F33] border border-[#E0E3E7] dark:border-[#2A3B5F] shadow-sm hover:border-[#0B57D0]/60 dark:hover:border-[#6366F1]/60 transition-all cursor-pointer group"
        >
          <div className="flex items-center justify-between mb-1.5">
            <div className="flex items-center space-x-2">
              <Cpu className="w-4 h-4 text-emerald-600 dark:text-emerald-400 group-hover:scale-110 transition-transform" />
              <span className="text-xs font-bold text-[#202124] dark:text-[#F1F5F9]">
                Hardware TRNG
              </span>
            </div>
            <span className="flex h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
          </div>
          <p className="text-[11px] text-[#5F6368] dark:text-[#94A3B8] truncate mb-2">
            {hsmStatus.activePort}
          </p>
          <div className="flex items-center space-x-1.5 text-[10px] text-emerald-700 dark:text-emerald-400 font-medium bg-emerald-50 dark:bg-emerald-950/40 px-2 py-1 rounded-lg">
            <CheckCircle2 className="w-3 h-3 shrink-0" />
            <span>NIST SP 800-90B PASSED</span>
          </div>
        </div>
      ) : (
        <div
          onClick={onOpenSettings}
          className="w-10 h-10 mx-auto rounded-xl bg-white dark:bg-[#161F33] border border-[#E0E3E7] dark:border-[#2A3B5F] flex items-center justify-center cursor-pointer"
          title="Hardware TRNG Active"
        >
          <Cpu className="w-5 h-5 text-emerald-500" />
        </div>
      )}
    </aside>
  );
};
