import React, { useState, useRef, useEffect } from 'react';
import { Menu, Search, SlidersHorizontal, Sun, Moon, Settings, ShieldCheck, X, LogIn, Languages, Check, HelpCircle } from 'lucide-react';
import { ShinyText } from './reactbits/ShinyText';
import { HSMStatus, AccountSession, SearchFilters, countActiveFilters, DEFAULT_SEARCH_FILTERS, LanguageOption } from '../types';
import { SearchFilterPopover } from './SearchFilterPopover';
import { t } from '../lib/i18n';

interface HeaderProps {
  onToggleSidebar: () => void;
  onOpenSettings: (tab?: 'general' | 'labels' | 'accounts' | 'security' | 'appearance' | 'accessibility' | 'about') => void;
  onOpenSignIn: () => void;
  isDarkMode: boolean;
  onToggleTheme: () => void;
  hsmStatus?: HSMStatus;
  account: AccountSession;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  searchFilters: SearchFilters;
  onApplySearchFilters: (filters: SearchFilters) => void;
  onClearSearchFilters: () => void;
  showIconLabels?: boolean;
  language?: LanguageOption;
  onUpdateLanguage?: (lang: LanguageOption) => void;
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
  searchFilters,
  onApplySearchFilters,
  onClearSearchFilters,
  showIconLabels = false,
  language,
  onUpdateLanguage,
}) => {
  const [isSearchFocused, setIsSearchFocused] = useState(false);
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [isLanguageOpen, setIsLanguageOpen] = useState(false);
  const [avatarError, setAvatarError] = useState(false);
  const [tempFilters, setTempFilters] = useState<SearchFilters>(searchFilters);
  const searchContainerRef = useRef<HTMLDivElement>(null);
  const languageMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setAvatarError(false);
  }, [account.avatarUrl]);

  useEffect(() => {
    setTempFilters(searchFilters);
  }, [searchFilters]);

  // Click outside listener for language dropdown
  useEffect(() => {
    if (!isLanguageOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (languageMenuRef.current && !languageMenuRef.current.contains(e.target as Node)) {
        setIsLanguageOpen(false);
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIsLanguageOpen(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isLanguageOpen]);

  // Click outside listener for search filter popover
  useEffect(() => {
    if (!isFilterOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (searchContainerRef.current && !searchContainerRef.current.contains(e.target as Node)) {
        setIsFilterOpen(false);
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIsFilterOpen(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isFilterOpen]);

  const activeFilterCount = countActiveFilters(searchFilters);

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

        <div className="flex items-center space-x-2.5 cursor-pointer select-none" data-tour="tour-security">
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

      {/* Center: Large Gmail Search Pill with Advanced Filters */}
      <div className="flex-1 max-w-2xl mx-4 relative" ref={searchContainerRef} data-tour="tour-search">
        <div
          className={`relative flex items-center w-full h-11 px-4 rounded-full transition-all duration-200 ${
            isSearchFocused || isFilterOpen
              ? 'bg-white dark:bg-[#161F33] shadow-lg shadow-black/5 ring-1 ring-[#0B57D0] dark:ring-[#818CF8]'
              : 'bg-[#EAF1FB] dark:bg-[#111726] hover:bg-[#E2ECF8] dark:hover:bg-[#161F33]/80'
          }`}
        >
          <Search className="w-4 h-4 text-[#5F6368] dark:text-[#94A3B8] mr-3 shrink-0" />
          <input
            id="qumail-search-input"
            type="text"
            placeholder={t(language, 'search_placeholder')}
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            onFocus={() => setIsSearchFocused(true)}
            onBlur={() => setIsSearchFocused(false)}
            className="w-full bg-transparent border-none outline-none text-sm text-[#202124] dark:text-[#F1F5F9] placeholder-[#5F6368] dark:placeholder-[#64748B]"
          />
          {searchQuery && (
            <button
              onClick={() => onSearchChange('')}
              className="p-1 rounded-full text-[#5F6368] hover:text-[#202124] dark:hover:text-white mr-1 cursor-pointer"
              title="Clear text search"
            >
              <X className="w-4 h-4" />
            </button>
          )}

          <button
            type="button"
            onClick={() => setIsFilterOpen(!isFilterOpen)}
            title={t(language, 'filter_tooltip')}
            className={`p-1.5 rounded-full transition-all relative cursor-pointer outline-none ${
              isFilterOpen || activeFilterCount > 0
                ? 'qumail-accent-soft qumail-accent-text font-bold shadow-sm'
                : 'text-[#5F6368] dark:text-[#94A3B8] hover:bg-slate-200 dark:hover:bg-slate-700'
            }`}
          >
            <SlidersHorizontal className="w-4 h-4" />
            {activeFilterCount > 0 && (
              <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full qumail-accent-bg text-white text-[9px] font-extrabold flex items-center justify-center shadow-md">
                {activeFilterCount}
              </span>
            )}
          </button>
        </div>

        {/* Search Filter Popover */}
        {isFilterOpen && (
          <SearchFilterPopover
            filters={tempFilters}
            language={language}
            onChange={(patch) => {
              const updated = { ...tempFilters, ...patch };
              setTempFilters(updated);
              onApplySearchFilters(updated);
            }}
            onApply={() => {
              onApplySearchFilters(tempFilters);
              setIsFilterOpen(false);
            }}
            onClear={() => {
              setTempFilters(DEFAULT_SEARCH_FILTERS);
              onClearSearchFilters();
            }}
            onClose={() => {
              onApplySearchFilters(tempFilters);
              setIsFilterOpen(false);
            }}
          />
        )}
      </div>

      {/* Right: Theme, Language, Settings, Avatar / Sign In */}
      <div className="flex items-center space-x-2 shrink-0">
        {/* Quick Language Switcher */}
        <div className="relative" ref={languageMenuRef}>
          <button
            type="button"
            onClick={() => setIsLanguageOpen(!isLanguageOpen)}
            title={t(language, 'language_switcher')}
            className={`${
              showIconLabels ? 'px-3 py-1.5 rounded-full flex items-center space-x-1.5' : 'p-2.5 rounded-full'
            } text-[#5F6368] dark:text-[#94A3B8] hover:bg-[#EAEAEA] dark:hover:bg-[#1E2740] hover:text-[#202124] dark:hover:text-[#F1F5F9] transition-colors outline-none cursor-pointer flex items-center gap-1.5`}
          >
            <Languages className="w-5 h-5" />
            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-gray-200/80 dark:bg-gray-700/80 text-[#202124] dark:text-[#F1F5F9] font-mono leading-none">
              {language === 'hi' ? 'हि' : language === 'mr' ? 'मर' : 'EN'}
            </span>
            {showIconLabels && (
              <span className="text-xs font-semibold">{t(language, 'language_switcher')}</span>
            )}
          </button>

          {isLanguageOpen && (
            <div className="absolute right-0 top-full mt-2 w-48 rounded-2xl bg-white/95 dark:bg-[#161F33]/95 backdrop-blur-md border border-gray-200 dark:border-gray-700/80 shadow-2xl p-1.5 z-50 animate-in fade-in zoom-in-95 duration-100">
              <div className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-[#5F6368] dark:text-[#94A3B8] border-b border-gray-100 dark:border-gray-800">
                {t(language, 'language_switcher')}
              </div>
              <div className="py-1 space-y-0.5">
                {(
                  [
                    { code: 'en' as const, label: 'English', sub: 'English', tag: 'EN' },
                    { code: 'hi' as const, label: 'हिन्दी', sub: 'Hindi', tag: 'HI' },
                    { code: 'mr' as const, label: 'मराठी', sub: 'Marathi', tag: 'MR' },
                  ] as const
                ).map((item) => {
                  const isActive = (language || 'en') === item.code;
                  return (
                    <button
                      key={item.code}
                      type="button"
                      onClick={() => {
                        onUpdateLanguage?.(item.code);
                        setIsLanguageOpen(false);
                      }}
                      className={`w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs transition-colors cursor-pointer ${
                        isActive
                          ? 'qumail-accent-soft qumail-accent-text font-bold'
                          : 'text-[#202124] dark:text-[#F1F5F9] hover:bg-gray-100 dark:hover:bg-white/[0.05]'
                      }`}
                    >
                      <div className="flex items-center space-x-2 text-left">
                        <span className="font-semibold">{item.label}</span>
                        <span className="text-[10px] text-[#5F6368] dark:text-[#94A3B8]">({item.sub})</span>
                      </div>
                      <div className="flex items-center space-x-1.5">
                        <span className="text-[9px] font-mono px-1 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-[#5F6368] dark:text-[#94A3B8]">
                          {item.tag}
                        </span>
                        {isActive && <Check className="w-3.5 h-3.5 qumail-accent-text stroke-[3]" />}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Theme Toggle */}
        <button
          onClick={onToggleTheme}
          title={isDarkMode ? t(language, 'switch_to_light') : t(language, 'switch_to_dark')}
          className={`${
            showIconLabels ? 'px-3 py-1.5 rounded-full flex items-center space-x-1.5' : 'p-2.5 rounded-full'
          } text-[#5F6368] dark:text-[#94A3B8] hover:bg-[#EAEAEA] dark:hover:bg-[#1E2740] hover:text-[#202124] dark:hover:text-[#F1F5F9] transition-colors outline-none cursor-pointer`}
        >
          {isDarkMode ? <Sun className="w-5 h-5 text-amber-400" /> : <Moon className="w-5 h-5" />}
          {showIconLabels && (
            <span className="text-xs font-semibold">
              {isDarkMode ? t(language, 'switch_to_light') : t(language, 'switch_to_dark')}
            </span>
          )}
        </button>

        {/* Help Button */}
        <button
          onClick={() => onOpenSettings('about')}
          title="Help & FAQs"
          data-tour="tour-help"
          className={`${
            showIconLabels ? 'px-3 py-1.5 rounded-full flex items-center space-x-1.5' : 'p-2.5 rounded-full'
          } text-[#5F6368] dark:text-[#94A3B8] hover:bg-[#EAEAEA] dark:hover:bg-[#1E2740] hover:text-[#202124] dark:hover:text-[#F1F5F9] transition-colors outline-none cursor-pointer`}
        >
          <HelpCircle className="w-5 h-5" />
          {showIconLabels && <span className="text-xs font-semibold">Help</span>}
        </button>

        {/* Settings Button */}
        <button
          onClick={() => onOpenSettings('general')}
          title={t(language, 'settings_title')}
          data-tour="tour-settings"
          className={`${
            showIconLabels ? 'px-3 py-1.5 rounded-full flex items-center space-x-1.5' : 'p-2.5 rounded-full'
          } text-[#5F6368] dark:text-[#94A3B8] hover:bg-[#EAEAEA] dark:hover:bg-[#1E2740] hover:text-[#202124] dark:hover:text-[#F1F5F9] transition-colors outline-none cursor-pointer`}
        >
          <Settings className="w-5 h-5" />
          {showIconLabels && <span className="text-xs font-semibold">{t(language, 'settings_title')}</span>}
        </button>

        {/* Profile Avatar or Sign In button */}
        {account.email ? (
          <div
            onClick={() => onOpenSettings('accounts')}
            title={`${t(language, 'signed_in_as')}: ${account.displayName || account.email} (${account.email})`}
            className="w-9 h-9 rounded-full bg-gradient-to-tr from-[#0B57D0] to-[#1A73E8] text-white flex items-center justify-center font-bold text-xs shadow-md cursor-pointer hover:ring-2 hover:ring-offset-2 hover:ring-[#0B57D0] dark:hover:ring-offset-[#0A0E17] transition-all select-none overflow-hidden"
          >
            {account.avatarUrl && !avatarError ? (
              <img
                src={account.avatarUrl}
                alt={account.displayName || account.email}
                referrerPolicy="no-referrer"
                crossOrigin="anonymous"
                className="w-full h-full object-cover"
                onError={() => setAvatarError(true)}
              />
            ) : (
              getInitials(account.email)
            )}
          </div>
        ) : (
          <button
            onClick={onOpenSignIn}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-full bg-[#0B57D0] hover:bg-[#0842A0] text-white font-semibold text-xs shadow-sm hover:shadow transition-all"
          >
            <LogIn className="w-3.5 h-3.5" />
            <span>{t(language, 'sign_in')}</span>
          </button>
        )}
      </div>
    </header>
  );
};
