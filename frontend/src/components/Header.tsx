import React, { useState } from 'react';
import { Menu, Search, SlidersHorizontal, Sun, Moon, Settings, ShieldCheck, Cpu, X, LogIn } from 'lucide-react';
import { ShinyText } from './reactbits/ShinyText';
import { HSMStatus, AccountSession } from '../types';

interface HeaderProps {
  onToggleSidebar: () => void;
  onOpenSettings: () => void;
  onOpenSignIn: () => void;
  isDarkMode: boolean;
  onToggleTheme: () => void;
  hsmStatus: HSMStatus;
  account: AccountSession;
  searchQuery: string;
  onSearchChange: (q: string) => void;
}

export const Header: React.FC<HeaderProps> = ({
  onToggleSidebar,
  onOpenSettings,
  onOpenSignIn,
  isDarkMode,
  onToggleTheme,
  hsmStatus,
  account,
  searchQuery,
  onSearchChange,
}) => {
  const [isSearchFocused, setIsSearchFocused] = useState(false);

  const getInitials = (email: string) => {
    if (!email) return 'GU';
    const name = email.split('@')[0];
    return name.slice(0, 2).toUpperCase();
  };

  return (
    <header className="h-16 px-4 flex items-center justify-between border-b border-[#E0E3E7] dark:border-[#1F2C47] bg-[#F6F8FC] dark:bg-[#0A0E17] z-20 transition-colors duration-200">
      {/* Left: Hamburger + Brand Logo */}
      <div className="flex items-center space-x-3 w-64 min-w-[240px]">
        <button
          onClick={onToggleSidebar}
          aria-label="Main menu"
          className="p-2.5 rounded-full text-[#5F6368] dark:text-[#94A3B8] hover:bg-[#EAEAEA] dark:hover:bg-[#1E2740] hover:text-[#202124] dark:hover:text-[#F1F5F9] transition-colors outline-none"
        >
          <Menu className="w-5 h-5" />
        </button>

        <div className="flex items-center space-x-2.5 cursor-pointer select-none">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-[#0B57D0] to-[#4F46E5] flex items-center justify-center shadow-md shadow-blue-500/20">
            <ShieldCheck className="w-5 h-5 text-white" />
          </div>
          <div className="flex flex-col">
            <span className="text-xl font-bold tracking-tight flex items-center space-x-1.5">
              <ShinyText text="QuMail" className="text-xl font-black" />
              <span className="text-[10px] font-extrabold uppercase tracking-wider px-1.5 py-0.5 rounded bg-blue-100 dark:bg-indigo-900/60 text-[#0B57D0] dark:text-indigo-300">
                PQC
              </span>
            </span>
          </div>
        </div>
      </div>

      {/* Center: Large Gmail Search Pill */}
      <div className="flex-1 max-w-2xl mx-4">
        <div
          className={`relative flex items-center w-full h-11 px-4 rounded-full transition-all duration-200 ${
            isSearchFocused
              ? 'bg-white dark:bg-[#161F33] shadow-lg shadow-black/5 ring-1 ring-[#0B57D0] dark:ring-[#818CF8]'
              : 'bg-[#EAF1FB] dark:bg-[#111726] hover:bg-[#E2ECF8] dark:hover:bg-[#161F33]/80'
          }`}
        >
          <Search className="w-4 h-4 text-[#5F6368] dark:text-[#94A3B8] mr-3 shrink-0" />
          <input
            type="text"
            placeholder="Search mail, recipients or quantum verification status..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            onFocus={() => setIsSearchFocused(true)}
            onBlur={() => setIsSearchFocused(false)}
            className="w-full bg-transparent border-none outline-none text-sm text-[#202124] dark:text-[#F1F5F9] placeholder-[#5F6368] dark:placeholder-[#64748B]"
          />
          {searchQuery && (
            <button
              onClick={() => onSearchChange('')}
              className="p-1 rounded-full text-[#5F6368] hover:text-[#202124] dark:hover:text-white"
            >
              <X className="w-4 h-4" />
            </button>
          )}
          <button
            title="Search options"
            className="p-1.5 rounded-full text-[#5F6368] dark:text-[#94A3B8] hover:bg-slate-200 dark:hover:bg-slate-700 ml-1"
          >
            <SlidersHorizontal className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Right: Hardware TRNG Status, Theme, Settings, Avatar / Sign In */}
      <div className="flex items-center space-x-2 shrink-0">
        {/* Hardware Status Pill */}
        {hsmStatus.isHardwareActive ? (
          <div
            title={`Physical TRNG Active: ${hsmStatus.activePort || 'COM3'} (${hsmStatus.rateBps || 115200} baud). NIST SP 800-90B PASSED.`}
            className="hidden md:flex items-center space-x-2 px-3 py-1.5 rounded-full bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800/60 text-emerald-800 dark:text-emerald-300 text-xs font-semibold select-none cursor-pointer"
            onClick={onOpenSettings}
          >
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            <Cpu className="w-3.5 h-3.5" />
            <span>TRNG: {hsmStatus.activePort || 'Active'}</span>
          </div>
        ) : (
          <div
            title="Entropy: OS Software CSPRNG (NIST SP 800-90A). No physical TRNG connected. Plug in a USB TRNG (ESP32/STM32) to stream hardware entropy."
            className="hidden md:flex items-center space-x-1.5 px-3 py-1.5 rounded-full bg-gray-100 dark:bg-[#161F33] border border-gray-300/80 dark:border-gray-700/80 text-gray-600 dark:text-gray-400 text-xs font-medium select-none cursor-pointer hover:border-blue-400 transition-colors"
            onClick={onOpenSettings}
          >
            <Cpu className="w-3.5 h-3.5 text-gray-500 dark:text-gray-400" />
            <span>Software CSPRNG</span>
          </div>
        )}

        {/* Theme Toggle */}
        <button
          onClick={onToggleTheme}
          title={isDarkMode ? 'Switch to Light Theme' : 'Switch to Dark Theme'}
          className="p-2.5 rounded-full text-[#5F6368] dark:text-[#94A3B8] hover:bg-[#EAEAEA] dark:hover:bg-[#1E2740] hover:text-[#202124] dark:hover:text-[#F1F5F9] transition-colors outline-none"
        >
          {isDarkMode ? <Sun className="w-5 h-5 text-amber-400" /> : <Moon className="w-5 h-5" />}
        </button>

        {/* Settings Button */}
        <button
          onClick={onOpenSettings}
          title="Settings"
          className="p-2.5 rounded-full text-[#5F6368] dark:text-[#94A3B8] hover:bg-[#EAEAEA] dark:hover:bg-[#1E2740] hover:text-[#202124] dark:hover:text-[#F1F5F9] transition-colors outline-none"
        >
          <Settings className="w-5 h-5" />
        </button>

        {/* Profile Avatar or Sign In button */}
        {account.email ? (
          <div
            onClick={onOpenSettings}
            title={`Signed in as: ${account.email}`}
            className="w-9 h-9 rounded-full bg-gradient-to-tr from-[#0B57D0] to-[#1A73E8] text-white flex items-center justify-center font-bold text-xs shadow-md cursor-pointer hover:ring-2 hover:ring-offset-2 hover:ring-[#0B57D0] dark:hover:ring-offset-[#0A0E17] transition-all select-none"
          >
            {getInitials(account.email)}
          </div>
        ) : (
          <button
            onClick={onOpenSignIn}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-full bg-[#0B57D0] hover:bg-[#0842A0] text-white font-semibold text-xs shadow-sm hover:shadow transition-all"
          >
            <LogIn className="w-3.5 h-3.5" />
            <span>Sign In</span>
          </button>
        )}
      </div>
    </header>
  );
};
