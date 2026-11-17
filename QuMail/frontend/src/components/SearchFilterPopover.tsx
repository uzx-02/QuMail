import React from 'react';
import { motion } from 'framer-motion';
import { SlidersHorizontal, ShieldCheck, Lock, Paperclip, Mail, Star, Shield, X, RotateCcw } from 'lucide-react';
import { SearchFilters, countActiveFilters, LanguageOption } from '../types';
import { t } from '../lib/i18n';

interface SearchFilterPopoverProps {
  filters: SearchFilters;
  onChange: (patch: Partial<SearchFilters>) => void;
  onApply: () => void;
  onClear: () => void;
  onClose: () => void;
  language?: LanguageOption;
}

export const SearchFilterPopover: React.FC<SearchFilterPopoverProps> = ({
  filters,
  onChange,
  onApply,
  onClear,
  onClose,
  language,
}) => {
  const activeCount = countActiveFilters(filters);

  return (
    <motion.div
      initial={{ opacity: 0, y: -6, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -6, scale: 0.98 }}
      transition={{ duration: 0.15 }}
      onClick={(e) => e.stopPropagation()}
      className="absolute top-13 left-0 right-0 z-50 mt-1 bg-white/95 dark:bg-[#111827]/95 backdrop-blur-2xl border border-gray-200 dark:border-gray-800 rounded-3xl shadow-2xl p-5 select-none space-y-4 text-xs"
    >
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-gray-100 dark:border-gray-800">
        <div className="flex items-center space-x-2">
          <div className="w-7 h-7 rounded-lg qumail-accent-soft qumail-accent-text flex items-center justify-center">
            <SlidersHorizontal className="w-4 h-4" />
          </div>
          <div>
            <h3 className="font-bold text-sm text-[#202124] dark:text-[#F1F5F9]">
              {t(language, 'filter_heading')}
            </h3>
            <p className="text-[11px] text-[#5F6368] dark:text-[#94A3B8]">
              {t(language, 'filter_tooltip')}
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={onClose}
          className="p-1 rounded-full text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors cursor-pointer"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* 1. Security / Encryption Tier */}
      <div className="space-y-1.5">
        <label className="text-[11px] font-bold text-[#5F6368] dark:text-[#94A3B8] uppercase tracking-wider">
          {t(language, 'filter_encryption_mode')}
        </label>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {[
            { id: 'all', label: t(language, 'filter_mode_all') },
            { id: 'pq', label: t(language, 'filter_mode_pq'), icon: <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" /> },
            { id: 'weblink', label: t(language, 'filter_mode_weblink'), icon: <Lock className="w-3.5 h-3.5 text-cyan-500" /> },
            { id: 'standard', label: t(language, 'filter_mode_standard') },
          ].map((mode) => {
            const isSelected = filters.securityMode === mode.id;
            return (
              <button
                key={mode.id}
                type="button"
                onClick={() => onChange({ securityMode: mode.id as any })}
                className={`flex items-center justify-center space-x-1.5 px-3 py-2 rounded-xl text-xs font-semibold transition-all border cursor-pointer ${
                  isSelected
                    ? 'qumail-accent-soft qumail-accent-text border-transparent font-bold ring-1 qumail-accent-border'
                    : 'bg-gray-50 dark:bg-white/[0.02] border-gray-200 dark:border-gray-800 text-[#5F6368] dark:text-[#94A3B8] hover:bg-gray-100 dark:hover:bg-white/[0.05]'
                }`}
              >
                {mode.icon && <span>{mode.icon}</span>}
                <span>{mode.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 2. Sender (From) & Recipient (To) Inputs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-1">
          <label className="text-[11px] font-bold text-[#5F6368] dark:text-[#94A3B8] uppercase tracking-wider">
            {t(language, 'filter_from')}
          </label>
          <input
            type="text"
            placeholder="alex@company.com or name"
            value={filters.from}
            onChange={(e) => onChange({ from: e.target.value })}
            className="w-full px-3.5 py-2 rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-white/[0.02] text-xs text-[#202124] dark:text-white outline-none focus:ring-1 focus:ring-sky-500 transition-all placeholder:text-gray-400"
          />
        </div>

        <div className="space-y-1">
          <label className="text-[11px] font-bold text-[#5F6368] dark:text-[#94A3B8] uppercase tracking-wider">
            {t(language, 'filter_to')}
          </label>
          <input
            type="text"
            placeholder="sarah@partner.org or email"
            value={filters.to}
            onChange={(e) => onChange({ to: e.target.value })}
            className="w-full px-3.5 py-2 rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-white/[0.02] text-xs text-[#202124] dark:text-white outline-none focus:ring-1 focus:ring-sky-500 transition-all placeholder:text-gray-400"
          />
        </div>
      </div>

      {/* 3. Subject Keywords Input */}
      <div className="space-y-1">
        <label className="text-[11px] font-bold text-[#5F6368] dark:text-[#94A3B8] uppercase tracking-wider">
          {t(language, 'filter_subject_keywords')}
        </label>
        <input
          type="text"
          placeholder="e.g. quarterly report, project budget, NDA..."
          value={filters.subjectKeywords}
          onChange={(e) => onChange({ subjectKeywords: e.target.value })}
          className="w-full px-3.5 py-2 rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-white/[0.02] text-xs text-[#202124] dark:text-white outline-none focus:ring-1 focus:ring-sky-500 transition-all placeholder:text-gray-400"
        />
      </div>

      {/* 4. Quick Attribute Toggles */}
      <div className="space-y-1.5">
        <label className="text-[11px] font-bold text-[#5F6368] dark:text-[#94A3B8] uppercase tracking-wider">
          {t(language, 'filter_has_attachment')} / Flags
        </label>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {[
            {
              id: 'hasAttachment',
              label: t(language, 'filter_has_attachment'),
              icon: <Paperclip className="w-3.5 h-3.5" />,
              active: filters.hasAttachment,
              toggle: () => onChange({ hasAttachment: !filters.hasAttachment }),
            },
            {
              id: 'unreadOnly',
              label: t(language, 'filter_unread_only'),
              icon: <Mail className="w-3.5 h-3.5" />,
              active: filters.unreadOnly,
              toggle: () => onChange({ unreadOnly: !filters.unreadOnly }),
            },
            {
              id: 'starredOnly',
              label: t(language, 'filter_starred_only'),
              icon: <Star className="w-3.5 h-3.5" />,
              active: filters.starredOnly,
              toggle: () => onChange({ starredOnly: !filters.starredOnly }),
            },
            {
              id: 'cloakedOnly',
              label: t(language, 'filter_cloaked_only'),
              icon: <Shield className="w-3.5 h-3.5" />,
              active: filters.cloakedOnly,
              toggle: () => onChange({ cloakedOnly: !filters.cloakedOnly }),
            },
          ].map((attr) => (
            <button
              key={attr.id}
              type="button"
              onClick={attr.toggle}
              className={`flex items-center justify-center space-x-1.5 px-3 py-2 rounded-xl text-xs font-semibold transition-all border cursor-pointer ${
                attr.active
                  ? 'qumail-accent-soft qumail-accent-text font-bold border-transparent ring-1 qumail-accent-border'
                  : 'bg-gray-50 dark:bg-white/[0.02] border-gray-200 dark:border-gray-800 text-[#5F6368] dark:text-[#94A3B8] hover:bg-gray-100 dark:hover:bg-white/[0.05]'
              }`}
            >
              <span>{attr.icon}</span>
              <span>{attr.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* 5. Date Range Selector */}
      <div className="space-y-1.5">
        <label className="text-[11px] font-bold text-[#5F6368] dark:text-[#94A3B8] uppercase tracking-wider">
          {t(language, 'filter_date_range')}
        </label>
        <div className="grid grid-cols-4 gap-2">
          {[
            { id: 'all', label: t(language, 'filter_date_all') },
            { id: '24h', label: t(language, 'filter_date_24h') },
            { id: '7d', label: t(language, 'filter_date_7d') },
            { id: '30d', label: t(language, 'filter_date_30d') },
          ].map((d) => {
            const isSelected = filters.dateRange === d.id;
            return (
              <button
                key={d.id}
                type="button"
                onClick={() => onChange({ dateRange: d.id as any })}
                className={`py-1.5 px-3 rounded-xl text-center text-xs font-semibold border transition-all cursor-pointer ${
                  isSelected
                    ? 'qumail-accent-soft qumail-accent-text font-bold border-transparent ring-1 qumail-accent-border'
                    : 'bg-gray-50 dark:bg-white/[0.02] border-gray-200 dark:border-gray-800 text-[#5F6368] dark:text-[#94A3B8] hover:bg-gray-100 dark:hover:bg-white/[0.05]'
                }`}
              >
                {d.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* 6. Footer Actions */}
      <div className="flex items-center justify-between pt-3 border-t border-gray-100 dark:border-gray-800">
        <div>
          {activeCount > 0 ? (
            <span className="text-[11px] font-semibold text-emerald-600 dark:text-emerald-400 flex items-center space-x-1">
              <span>● {activeCount} {t(language, 'selected_count', { count: activeCount })}</span>
            </span>
          ) : (
            <span className="text-[11px] text-[#5F6368] dark:text-[#94A3B8]">
              {t(language, 'filter_date_all')}
            </span>
          )}
        </div>

        <div className="flex items-center space-x-2">
          {activeCount > 0 && (
            <button
              type="button"
              onClick={onClear}
              className="flex items-center space-x-1 px-3 py-1.5 rounded-xl text-xs font-semibold text-[#5F6368] dark:text-[#94A3B8] hover:text-[#202124] dark:hover:text-white transition-colors cursor-pointer"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>{t(language, 'filter_reset')}</span>
            </button>
          )}

          <button
            type="button"
            onClick={onApply}
            className="px-5 py-2 rounded-xl qumail-accent-bg text-white text-xs font-bold shadow-md cursor-pointer hover:opacity-95 transition-opacity"
          >
            {t(language, 'filter_apply')}
          </button>
        </div>
      </div>
    </motion.div>
  );
};

