import React from 'react';
import { motion } from 'framer-motion';

export interface TabItem {
  id: string;
  label: string;
  icon?: React.ReactNode;
  badge?: number | string;
}

interface AnimatedTabsProps {
  tabs: TabItem[];
  activeTab: string;
  onChange: (id: string) => void;
  className?: string;
}

export const AnimatedTabs: React.FC<AnimatedTabsProps> = ({
  tabs,
  activeTab,
  onChange,
  className = '',
}) => {
  return (
    <div className={`flex items-center space-x-1 ${className}`}>
      {tabs.map((tab) => {
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => onChange(tab.id)}
            className={`relative flex items-center space-x-2.5 px-6 py-3 text-sm font-medium transition-colors duration-200 outline-none select-none ${
              isActive
                ? 'text-[#0B57D0] dark:text-[#818CF8] font-semibold'
                : 'text-[#5F6368] dark:text-[#94A3B8] hover:text-[#202124] dark:hover:text-[#F1F5F9] hover:bg-[#F2F6FC]/60 dark:hover:bg-[#1E2740]/40 rounded-t-lg'
            }`}
          >
            {tab.icon && (
              <span className={`transition-colors duration-200 ${isActive ? 'text-[#0B57D0] dark:text-[#818CF8]' : 'text-[#5F6368] dark:text-[#94A3B8]'}`}>
                {tab.icon}
              </span>
            )}
            <span>{tab.label}</span>
            {tab.badge !== undefined && (
              <span className="text-xs px-1.5 py-0.5 rounded-full bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300 font-bold">
                {tab.badge}
              </span>
            )}

            {isActive && (
              <motion.div
                layoutId="activeTabUnderline"
                className="absolute bottom-0 left-0 right-0 h-[3px] bg-[#0B57D0] dark:bg-[#818CF8] rounded-t-full"
                transition={{ type: 'spring', stiffness: 450, damping: 35 }}
              />
            )}
          </button>
        );
      })}
    </div>
  );
};
