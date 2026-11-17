import React, { useState } from 'react';
import { View, Text, TouchableOpacity, TextInput } from 'react-native';
import { Menu, Lock, Unlock, Settings, Search, Languages, SlidersHorizontal, RefreshCw } from 'lucide-react-native';
import { LanguageOption, ThemeMode, SearchFilters, DEFAULT_SEARCH_FILTERS, countActiveFilters } from '../types';
import { t } from '../lib/i18n';
import { getTheme } from '../lib/theme';
import { SearchFilterModal } from './SearchFilterModal';

interface HeaderProps {
  title: string;
  isUnlocked: boolean;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  searchFilters?: SearchFilters;
  onApplySearchFilters?: (filters: SearchFilters) => void;
  onClearSearchFilters?: () => void;
  onMenuPress: () => void;
  onVaultPress: () => void;
  onSettingsPress: () => void;
  onComposePress?: () => void;
  onRefresh?: () => void;
  refreshing?: boolean;
  language?: LanguageOption;
  onToggleLanguage?: () => void;
  theme?: ThemeMode;
}

export const Header: React.FC<HeaderProps> = ({
  title,
  isUnlocked,
  searchQuery,
  onSearchChange,
  searchFilters = DEFAULT_SEARCH_FILTERS,
  onApplySearchFilters,
  onClearSearchFilters,
  onMenuPress,
  onVaultPress,
  onSettingsPress,
  onRefresh,
  refreshing = false,
  language = 'en',
  onToggleLanguage,
  theme = 'midnight',
}) => {
  const pal = getTheme(theme);
  const isLight = theme === 'light';
  const [filterModalOpen, setFilterModalOpen] = useState(false);
  const [tempFilters, setTempFilters] = useState<SearchFilters>(searchFilters);

  const activeCount = countActiveFilters(searchFilters);

  return (
    <View
      style={{
        backgroundColor: pal.headerBg,
        borderBottomColor: pal.border,
        borderBottomWidth: 1,
        paddingHorizontal: 14,
        paddingTop: 6,
        paddingBottom: 10,
      }}
    >
      {/* Top action row */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 4 }}>
        {/* Left Side: Hamburger Menu & Title */}
        <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', marginRight: 8 }}>
          <TouchableOpacity
            onPress={onMenuPress}
            activeOpacity={0.7}
            style={{
              padding: 8,
              borderRadius: 12,
              borderWidth: 1,
              borderColor: pal.border,
              backgroundColor: pal.card,
            }}
          >
            <Menu size={18} color={pal.text} />
          </TouchableOpacity>

          <View style={{ flex: 1, marginLeft: 10, flexDirection: 'row', alignItems: 'center' }}>
            <Text
              numberOfLines={1}
              style={{
                fontSize: 17,
                fontWeight: '700',
                color: pal.text,
                textTransform: 'capitalize',
              }}
            >
              {title}
            </Text>
          </View>
        </View>

        {/* Right Side: Action Controls with fixed constraints to prevent clipping */}
        <View style={{ flexDirection: 'row', alignItems: 'center', flexShrink: 0 }}>
          {/* Inbox Refresh Button */}
          {onRefresh && (
            <TouchableOpacity
              onPress={onRefresh}
              disabled={refreshing}
              activeOpacity={0.7}
              style={{
                padding: 8,
                borderRadius: 12,
                borderWidth: 1,
                borderColor: pal.border,
                backgroundColor: pal.card,
                marginRight: 6,
              }}
            >
              <RefreshCw size={14} color="#10b981" />
            </TouchableOpacity>
          )}

          {/* Quick Language Toggle Pill */}
          {onToggleLanguage && (
            <TouchableOpacity
              onPress={onToggleLanguage}
              activeOpacity={0.7}
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                paddingHorizontal: 8,
                paddingVertical: 6,
                borderRadius: 12,
                borderWidth: 1,
                borderColor: pal.border,
                backgroundColor: pal.card,
                marginRight: 6,
              }}
            >
              <Languages size={13} color="#10b981" />
              <Text style={{ fontSize: 11, fontWeight: '700', marginLeft: 4, color: pal.subtext }}>
                {language.toUpperCase()}
              </Text>
            </TouchableOpacity>
          )}

          {/* Lock / Unlock App Action Button */}
          <TouchableOpacity
            onPress={onVaultPress}
            activeOpacity={0.7}
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              paddingHorizontal: 10,
              paddingVertical: 6,
              borderRadius: 12,
              borderWidth: 1,
              marginRight: 6,
              backgroundColor: isUnlocked
                ? isLight
                  ? 'rgba(16, 185, 129, 0.1)'
                  : 'rgba(16, 185, 129, 0.15)'
                : isLight
                ? 'rgba(244, 63, 94, 0.1)'
                : 'rgba(244, 63, 94, 0.15)',
              borderColor: isUnlocked ? 'rgba(16, 185, 129, 0.4)' : 'rgba(244, 63, 94, 0.4)',
            }}
          >
            {isUnlocked ? (
              <>
                <Lock size={13} color="#10b981" />
                <Text style={{ fontSize: 11, fontWeight: '700', color: '#10b981', marginLeft: 5 }}>
                  {t('action_lock_app', language)}
                </Text>
              </>
            ) : (
              <>
                <Unlock size={13} color="#f43f5e" />
                <Text style={{ fontSize: 11, fontWeight: '700', color: '#f43f5e', marginLeft: 5 }}>
                  {t('action_unlock_app', language)}
                </Text>
              </>
            )}
          </TouchableOpacity>

          {/* Settings Button */}
          <TouchableOpacity
            onPress={onSettingsPress}
            activeOpacity={0.7}
            style={{
              padding: 8,
              borderRadius: 12,
              borderWidth: 1,
              borderColor: pal.border,
              backgroundColor: pal.card,
            }}
          >
            <Settings size={18} color={pal.text} />
          </TouchableOpacity>
        </View>
      </View>

      {/* Search Bar */}
      <View
        style={{
          marginTop: 6,
          flexDirection: 'row',
          alignItems: 'center',
          borderRadius: 12,
          borderWidth: 1,
          borderColor: activeCount > 0 ? '#10b981' : pal.border,
          backgroundColor: pal.inputBg,
          paddingHorizontal: 12,
          paddingVertical: 6,
        }}
      >
        <Search size={15} color={pal.subtext} />
        <TextInput
          value={searchQuery}
          onChangeText={onSearchChange}
          placeholder={t('search_placeholder', language)}
          placeholderTextColor={pal.subtext}
          style={{
            flex: 1,
            marginLeft: 8,
            fontSize: 12,
            paddingVertical: 0,
            color: pal.text,
          }}
        />

        {/* Filter Trigger Button */}
        <TouchableOpacity
          onPress={() => {
            setTempFilters(searchFilters);
            setFilterModalOpen(true);
          }}
          activeOpacity={0.7}
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            paddingHorizontal: 8,
            paddingVertical: 4,
            borderRadius: 8,
            backgroundColor: activeCount > 0 ? 'rgba(16, 185, 129, 0.2)' : pal.card,
            borderWidth: 1,
            borderColor: activeCount > 0 ? '#10b981' : pal.border,
            marginLeft: 6,
          }}
        >
          <SlidersHorizontal size={13} color={activeCount > 0 ? '#10b981' : pal.subtext} />
          {activeCount > 0 && (
            <Text style={{ fontSize: 10, fontWeight: '700', color: '#10b981', marginLeft: 4 }}>
              {activeCount}
            </Text>
          )}
        </TouchableOpacity>
      </View>

      <SearchFilterModal
        visible={filterModalOpen}
        filters={tempFilters}
        onChange={(patch) => setTempFilters((prev) => ({ ...prev, ...patch }))}
        onApply={() => {
          onApplySearchFilters?.(tempFilters);
          setFilterModalOpen(false);
        }}
        onClear={() => {
          setTempFilters(DEFAULT_SEARCH_FILTERS);
          onClearSearchFilters?.();
          setFilterModalOpen(false);
        }}
        onClose={() => setFilterModalOpen(false)}
        language={language}
        theme={theme}
      />
    </View>
  );
};
