import React from 'react';
import { View, Text } from 'react-native';
import { SecurityIndicator } from '../types';
import { ShieldCheck, ShieldAlert, AlertTriangle, Shield } from 'lucide-react-native';

interface SecurityBadgeProps {
  indicator?: SecurityIndicator;
  compact?: boolean;
}

export const SecurityBadge: React.FC<SecurityBadgeProps> = ({ indicator, compact = false }) => {
  if (!indicator) return null;

  const { badgeLevel, headline, description, actionAdvice } = indicator;

  const getStyle = () => {
    switch (badgeLevel) {
      case 'SECURE':
        return {
          bg: 'bg-emerald-950/40',
          border: 'border-emerald-500/40',
          text: 'text-emerald-400',
          subtext: 'text-emerald-300/80',
          Icon: ShieldCheck,
        };
      case 'CAUTION':
        return {
          bg: 'bg-amber-950/40',
          border: 'border-amber-500/40',
          text: 'text-amber-400',
          subtext: 'text-amber-300/80',
          Icon: AlertTriangle,
        };
      case 'ALERT':
        return {
          bg: 'bg-rose-950/40',
          border: 'border-rose-500/40',
          text: 'text-rose-400',
          subtext: 'text-rose-300/80',
          Icon: ShieldAlert,
        };
      case 'NEUTRAL':
      default:
        return {
          bg: 'bg-slate-900/60',
          border: 'border-slate-700/50',
          text: 'text-slate-300',
          subtext: 'text-slate-400',
          Icon: Shield,
        };
    }
  };

  const config = getStyle();
  const IconComponent = config.Icon;

  if (compact) {
    return (
      <View className={`flex-row items-center px-2 py-0.5 rounded-full border ${config.bg} ${config.border}`}>
        <IconComponent size={12} color={badgeLevel === 'SECURE' ? '#34d399' : '#94a3b8'} />
        <Text className={`text-xs ml-1 font-medium ${config.text}`}>{badgeLevel}</Text>
      </View>
    );
  }

  return (
    <View className={`p-3 rounded-xl border ${config.bg} ${config.border} my-2`}>
      <View className="flex-row items-center mb-1">
        <IconComponent size={18} color={badgeLevel === 'SECURE' ? '#34d399' : '#fbbf24'} />
        <Text className={`text-sm font-semibold ml-2 ${config.text}`}>{headline}</Text>
      </View>
      <Text className={`text-xs ${config.subtext} mb-1 leading-relaxed`}>{description}</Text>
      {actionAdvice ? (
        <Text className="text-[11px] text-slate-400 font-mono italic">{actionAdvice}</Text>
      ) : null}
    </View>
  );
};
