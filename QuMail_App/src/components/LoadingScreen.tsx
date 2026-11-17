import React, { useEffect, useState } from 'react';
import { View, Text, ActivityIndicator } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Shield, Lock, CheckCircle2, Cpu, KeyRound } from 'lucide-react-native';
import { LanguageOption } from '../types';
import { t } from '../lib/i18n';

interface LoadingScreenProps {
  language: LanguageOption;
  onReady: () => void;
}

export const LoadingScreen: React.FC<LoadingScreenProps> = ({ language, onReady }) => {
  const insets = useSafeAreaInsets();
  const [currentStep, setCurrentStep] = useState(0);

  const steps = [
    { key: 'loading_step_1', icon: Cpu },
    { key: 'loading_step_2', icon: Lock },
    { key: 'loading_step_3', icon: KeyRound },
    { key: 'loading_step_4', icon: Shield },
  ];

  useEffect(() => {
    const timer1 = setTimeout(() => setCurrentStep(1), 350);
    const timer2 = setTimeout(() => setCurrentStep(2), 700);
    const timer3 = setTimeout(() => setCurrentStep(3), 1050);
    const timer4 = setTimeout(() => {
      setCurrentStep(4);
      setTimeout(onReady, 300);
    }, 1400);

    return () => {
      clearTimeout(timer1);
      clearTimeout(timer2);
      clearTimeout(timer3);
      clearTimeout(timer4);
    };
  }, [onReady]);

  return (
    <View
      className="flex-1 bg-[#0A0E17] items-center justify-center px-6"
      style={{ paddingTop: insets.top, paddingBottom: insets.bottom }}
    >
      {/* Background glow effect matching desktop */}
      <View className="absolute w-72 h-72 rounded-full bg-cyan-500/10 blur-3xl pointer-events-none" />

      {/* Main Logo Container matching desktop emblem */}
      <View className="items-center mb-10">
        <View className="relative w-24 h-24 rounded-3xl bg-gradient-to-br from-cyan-500 to-blue-600 items-center justify-center shadow-2xl mb-5" style={{ backgroundColor: '#06B6D4' }}>
          <Shield size={48} color="#FFFFFF" />
          <View className="absolute bottom-2 right-2 w-7 h-7 rounded-full bg-slate-900 border border-cyan-400 items-center justify-center">
            <Lock size={14} color="#38BDF8" />
          </View>
        </View>

        <Text className="text-3xl font-extrabold text-white tracking-wider">
          {t('loading_title', language)}
        </Text>
        <Text className="text-sm font-medium text-cyan-400 mt-1.5 text-center">
          {t('loading_subtitle', language)}
        </Text>
        <Text className="text-xs text-slate-400 mt-1 text-center">
          {t('app_tagline', language)}
        </Text>
      </View>

      {/* Step Indicators */}
      <View className="w-full max-w-sm bg-slate-900/80 border border-slate-800 rounded-2xl p-5 mb-8">
        {steps.map((step, index) => {
          const Icon = step.icon;
          const isDone = currentStep > index;
          const isCurrent = currentStep === index;

          return (
            <View
              key={step.key}
              className={`flex-row items-center py-2 ${index !== steps.length - 1 ? 'border-b border-slate-800/60' : ''}`}
            >
              <View className="w-8 h-8 rounded-lg items-center justify-center mr-3 bg-slate-800/70">
                {isDone ? (
                  <CheckCircle2 size={18} color="#06B6D4" />
                ) : isCurrent ? (
                  <ActivityIndicator size="small" color="#06B6D4" />
                ) : (
                  <Icon size={16} color="#64748b" />
                )}
              </View>

              <Text
                className={`flex-1 text-xs font-medium ${
                  isDone
                    ? 'text-slate-300'
                    : isCurrent
                    ? 'text-cyan-400 font-semibold'
                    : 'text-slate-500'
                }`}
              >
                {t(step.key, language)}
              </Text>
            </View>
          );
        })}
      </View>

      {/* Progress Bar with Cyan/Blue gradient */}
      <View className="w-full max-w-sm h-1.5 bg-slate-800 rounded-full overflow-hidden">
        <View
          className="h-full bg-cyan-500 rounded-full transition-all"
          style={{ width: `${Math.min(100, (currentStep / 4) * 100)}%` }}
        />
      </View>

      {/* Cryptographic Standards Note */}
      <Text className="text-[11px] text-slate-500 mt-6 text-center">
        NIST FIPS 203 (ML-KEM-768) • FIPS 204 (ML-DSA-65) • Android Keystore
      </Text>
    </View>
  );
};
