import React from 'react';
import { motion } from 'framer-motion';

interface SectionCardProps {
  title: string;
  subtitle?: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}

export const SectionCard: React.FC<SectionCardProps> = ({
  title,
  subtitle,
  icon,
  children,
}) => (
  <div className="rounded-2xl border border-gray-200/90 dark:border-gray-700/80 bg-white dark:bg-white/[0.02] p-5 space-y-5 shadow-sm">
    <div className="flex items-start space-x-3 pb-3 border-b border-gray-100 dark:border-gray-800">
      {icon && (
        <div className="w-8 h-8 rounded-xl qumail-accent-soft qumail-accent-text flex items-center justify-center shrink-0 mt-0.5">
          {icon}
        </div>
      )}
      <div>
        <h4 className="text-sm font-bold text-[#202124] dark:text-[#F1F5F9]">{title}</h4>
        {subtitle && (
          <p className="text-xs text-[#5F6368] dark:text-[#94A3B8] mt-0.5">{subtitle}</p>
        )}
      </div>
    </div>
    <div className="space-y-5">{children}</div>
  </div>
);

export interface SegmentedOption<T extends string | number> {
  value: T;
  label: string;
}

interface SegmentedControlProps<T extends string | number> {
  options: SegmentedOption<T>[];
  value: T;
  onChange: (val: T) => void;
  layoutId: string;
}

export function SegmentedControl<T extends string | number>({
  options,
  value,
  onChange,
  layoutId,
}: SegmentedControlProps<T>) {
  return (
    <div className="inline-flex flex-wrap p-1 rounded-2xl bg-gray-100/90 dark:bg-white/[0.04] border border-gray-200/70 dark:border-gray-700/70 w-full sm:w-auto">
      {options.map((opt) => {
        const active = value === opt.value;
        return (
          <button
            key={String(opt.value)}
            type="button"
            onClick={() => onChange(opt.value)}
            className={`relative flex-1 sm:flex-initial px-3.5 py-2 rounded-xl text-xs transition-colors cursor-pointer whitespace-nowrap ${
              active
                ? 'text-[#202124] dark:text-white font-bold'
                : 'text-[#5F6368] dark:text-[#94A3B8] hover:text-[#202124] dark:hover:text-white font-medium'
            }`}
          >
            {active && (
              <motion.div
                layoutId={layoutId}
                transition={{ type: 'spring', stiffness: 420, damping: 32 }}
                className="absolute inset-0 rounded-xl bg-white dark:bg-[#1E293B] shadow-sm border border-gray-200/80 dark:border-gray-600/60"
              />
            )}
            <span className="relative z-10">{opt.label}</span>
          </button>
        );
      })}
    </div>
  );
}

interface SettingToggleRowProps {
  title: string;
  description: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  badge?: string;
}

export const SettingToggleRow: React.FC<SettingToggleRowProps> = ({
  title,
  description,
  checked,
  onChange,
  badge,
}) => (
  <div className="flex items-center justify-between gap-4">
    <div className="space-y-0.5">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-[#202124] dark:text-[#F1F5F9]">{title}</span>
        {badge && (
          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold qumail-accent-soft qumail-accent-text">
            {badge}
          </span>
        )}
      </div>
      <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">{description}</p>
    </div>
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors cursor-pointer ${
        checked ? 'qumail-accent-bg' : 'bg-gray-300 dark:bg-gray-600'
      }`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform duration-200 ${
          checked ? 'translate-x-6' : 'translate-x-1'
        }`}
      />
    </button>
  </div>
);

