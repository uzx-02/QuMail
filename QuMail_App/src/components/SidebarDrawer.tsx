import React from 'react';
import { View, Text, TouchableOpacity, ScrollView, Modal, Pressable, Image } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import {
  Inbox,
  Star,
  Send,
  FileText,
  Trash2,
  AlertOctagon,
  Shield,
  Key,
  X,
  User,
  LogOut,
  Languages,
  CheckCircle2,
} from 'lucide-react-native';
import { AccountSession, QuMailSettings, LanguageOption } from '../types';
import { t, LANGUAGE_OPTIONS } from '../lib/i18n';

interface SidebarProps {
  visible: boolean;
  onClose: () => void;
  currentFolder: string;
  onSelectFolder: (folder: string) => void;
  account: AccountSession;
  onSignOut: () => void;
  isTablet?: boolean;
  settings: QuMailSettings;
  onUpdateSettings?: (patch: Partial<QuMailSettings>) => void;
}

export const SidebarDrawer: React.FC<SidebarProps> = ({
  visible,
  onClose,
  currentFolder,
  onSelectFolder,
  account,
  onSignOut,
  isTablet = false,
  settings,
  onUpdateSettings,
}) => {
  const lang = settings.language || 'en';
  const insets = useSafeAreaInsets();
  const isLight = settings.theme === 'light';
  const isMidnight = settings.theme === 'midnight';

  // Dynamic Theme Colors
  const sidebarBg = isLight ? 'bg-white border-slate-200' : isMidnight ? 'bg-slate-950 border-slate-900' : 'bg-slate-900 border-slate-800';
  const cardBg = isLight ? 'bg-slate-100 border-slate-200' : isMidnight ? 'bg-slate-900 border-slate-800' : 'bg-slate-800/80 border-slate-700';
  const borderCol = isLight ? 'border-slate-200' : isMidnight ? 'border-slate-900' : 'border-slate-800';
  const textColor = isLight ? 'text-slate-900' : 'text-white';
  const subtextColor = isLight ? 'text-slate-500' : 'text-slate-400';

  const allFolders = [
    { id: 'inbox', labelKey: 'folder_inbox', icon: Inbox, defaultShow: true },
    { id: 'starred', labelKey: 'folder_starred', icon: Star, defaultShow: settings.visibleFolders.starred },
    { id: 'sent', labelKey: 'folder_sent', icon: Send, defaultShow: settings.visibleFolders.sent },
    { id: 'drafts', labelKey: 'folder_drafts', icon: FileText, defaultShow: settings.visibleFolders.drafts },
    { id: 'outbox', labelKey: 'folder_outbox', icon: Send, defaultShow: settings.visibleFolders.outbox },
    { id: 'trash', labelKey: 'folder_trash', icon: Trash2, defaultShow: settings.visibleFolders.trash },
    { id: 'spam', labelKey: 'folder_spam', icon: AlertOctagon, defaultShow: settings.visibleFolders.spam },
  ];

  const visibleFolders = allFolders.filter((f) => f.defaultShow);

  const content = (
    <View
      className={`flex-1 border-r w-72 p-4 ${sidebarBg}`}
      style={{ paddingTop: Math.max(insets.top, 16), paddingBottom: Math.max(insets.bottom, 16) }}
    >
      {/* Brand Header */}
      <View className={`flex-row items-center justify-between pb-4 border-b ${borderCol} mb-4`}>
        <View className="flex-row items-center">
          <View className="w-10 h-10 rounded-2xl bg-emerald-500/20 border border-emerald-500/40 items-center justify-center">
            <Shield size={22} color="#10b981" />
          </View>
          <View className="ml-3">
            <Text className={`text-lg font-bold tracking-wide ${textColor}`}>QuMail</Text>
            <Text className="text-[11px] text-emerald-500 font-semibold">
              {t('app_subtitle', lang)}
            </Text>
          </View>
        </View>

        {!isTablet && (
          <TouchableOpacity
            onPress={onClose}
            className={`w-8 h-8 rounded-full items-center justify-center ${isLight ? 'bg-slate-200' : 'bg-slate-800'}`}
          >
            <X size={16} color={isLight ? '#475569' : '#94a3b8'} />
          </TouchableOpacity>
        )}
      </View>

      {/* Account Info Pill */}
      <View className={`p-3 rounded-2xl border mb-5 ${cardBg}`}>
        <View className="flex-row items-center">
          {account.avatarUrl ? (
            <Image
              source={{ uri: account.avatarUrl }}
              className="w-8 h-8 rounded-full mr-2.5"
            />
          ) : (
            <View className="w-8 h-8 rounded-full bg-emerald-500/20 items-center justify-center mr-2.5">
              <User size={16} color="#10b981" />
            </View>
          )}
          <View className="flex-1">
            <Text className={`text-xs font-bold ${textColor}`} numberOfLines={1}>
              {account.displayName || 'QuMail User'}
            </Text>
            <Text className={`text-[10px] ${subtextColor}`} numberOfLines={1}>
              {account.email}
            </Text>
          </View>
        </View>

        <View className={`flex-row items-center mt-2 pt-2 border-t ${borderCol}`}>
          <CheckCircle2 size={12} color="#10b981" />
          <Text className="text-[10px] text-emerald-500 ml-1 font-semibold">
            {account.connectionStatus === 'ONLINE' ? 'Connected & Ready' : 'Standby / Enclave Ready'}
          </Text>
        </View>
      </View>

      {/* Folder Navigation */}
      <Text className={`text-[10px] font-bold uppercase tracking-wider mb-2 px-1 ${subtextColor}`}>
        {t('nav_folders', lang)}
      </Text>
      <ScrollView className="flex-1 space-y-1">
        {visibleFolders.map((folder) => {
          const Icon = folder.icon;
          const isActive = currentFolder === folder.id;
          return (
            <TouchableOpacity
              key={folder.id}
              onPress={() => {
                onSelectFolder(folder.id);
                if (!isTablet) onClose();
              }}
              className={`flex-row items-center justify-between px-3 py-2.5 rounded-xl mb-1 ${
                isActive
                  ? 'bg-emerald-500/20 border border-emerald-500/40'
                  : 'bg-transparent border border-transparent'
              }`}
            >
              <View className="flex-row items-center">
                <Icon size={18} color={isActive ? '#10b981' : isLight ? '#64748b' : '#94a3b8'} />
                <Text
                  className={`text-xs ml-3 font-semibold ${
                    isActive ? 'text-emerald-500 font-bold' : textColor
                  }`}
                >
                  {t(folder.labelKey, lang)}
                </Text>
              </View>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      {/* Language Quick Switcher */}
      <View className={`py-3 border-t ${borderCol}`}>
        <Text className={`text-[10px] font-bold uppercase tracking-wider mb-2 px-1 ${subtextColor}`}>
          {t('general_language', lang)}
        </Text>
        <View className="flex-row space-x-1">
          {LANGUAGE_OPTIONS.map((opt) => (
            <TouchableOpacity
              key={opt.value}
              onPress={() => onUpdateSettings?.({ language: opt.value })}
              className={`flex-1 py-1.5 rounded-lg border items-center mr-1 ${
                lang === opt.value
                  ? 'bg-emerald-500/20 border-emerald-500/60'
                  : isLight
                  ? 'bg-slate-100 border-slate-200'
                  : 'bg-slate-800/80 border-slate-700'
              }`}
            >
              <Text
                className={`text-[11px] font-bold ${
                  lang === opt.value ? 'text-emerald-500' : subtextColor
                }`}
              >
                {opt.label.substring(0, 3)}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* Sign Out Action */}
      <TouchableOpacity
        onPress={onSignOut}
        className={`flex-row items-center px-3 py-2.5 rounded-xl border border-rose-500/30 ${
          isLight ? 'bg-rose-50' : 'bg-rose-500/10'
        } mt-2`}
      >
        <LogOut size={16} color="#f43f5e" />
        <Text className="text-xs font-bold text-rose-500 ml-2.5">
          {t('accounts_sign_out', lang)}
        </Text>
      </TouchableOpacity>
    </View>
  );

  if (isTablet) {
    return content;
  }

  return (
    <Modal visible={visible} animationType="fade" transparent onRequestClose={onClose}>
      <Pressable className="flex-1 bg-black/60 flex-row" onPress={onClose}>
        <Pressable onPress={(e) => e.stopPropagation()} className="flex-1 max-w-[280px]">
          {content}
        </Pressable>
      </Pressable>
    </Modal>
  );
};
