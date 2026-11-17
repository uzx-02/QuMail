import React from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  TextInput,
  ScrollView,
  Modal,
} from 'react-native';
import {
  SlidersHorizontal,
  ShieldCheck,
  Lock,
  Mail,
  Star,
  Shield,
  X,
  RotateCcw,
  Check,
} from 'lucide-react-native';
import { SearchFilters, countActiveFilters, LanguageOption, ThemeMode } from '../types';
import { t } from '../lib/i18n';
import { getTheme } from '../lib/theme';

interface SearchFilterModalProps {
  visible: boolean;
  filters: SearchFilters;
  onChange: (patch: Partial<SearchFilters>) => void;
  onApply: () => void;
  onClear: () => void;
  onClose: () => void;
  language?: LanguageOption;
  theme?: ThemeMode;
}

export const SearchFilterModal: React.FC<SearchFilterModalProps> = ({
  visible,
  filters,
  onChange,
  onApply,
  onClear,
  onClose,
  language = 'en',
  theme = 'midnight',
}) => {
  const pal = getTheme(theme);
  const activeCount = countActiveFilters(filters);

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View
        style={{
          flex: 1,
          backgroundColor: 'rgba(0,0,0,0.65)',
          justifyContent: 'flex-end',
        }}
      >
        <View
          style={{
            backgroundColor: pal.bg,
            borderTopLeftRadius: 24,
            borderTopRightRadius: 24,
            borderWidth: 1,
            borderColor: pal.border,
            maxHeight: '85%',
            padding: 20,
          }}
        >
          {/* Header */}
          <View
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'space-between',
              paddingBottom: 14,
              borderBottomWidth: 1,
              borderBottomColor: pal.border,
            }}
          >
            <View style={{ flexDirection: 'row', alignItems: 'center' }}>
              <View
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: 10,
                  backgroundColor: 'rgba(16, 185, 129, 0.15)',
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginRight: 10,
                }}
              >
                <SlidersHorizontal size={16} color="#10b981" />
              </View>
              <View>
                <Text style={{ fontSize: 15, fontWeight: '700', color: pal.text }}>
                  Filter Messages
                </Text>
                <Text style={{ fontSize: 11, color: pal.subtext }}>
                  Refine mailbox search results
                </Text>
              </View>
            </View>

            <TouchableOpacity onPress={onClose} style={{ padding: 4 }}>
              <X size={20} color={pal.subtext} />
            </TouchableOpacity>
          </View>

          <ScrollView style={{ marginTop: 14 }}>
            {/* 1. Security / Encryption Tier */}
            <Text style={{ fontSize: 11, fontWeight: '700', textTransform: 'uppercase', color: pal.subtext, marginBottom: 8 }}>
              Security Mode
            </Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 16 }}>
              {[
                { id: 'all', label: 'All Modes' },
                { id: 'pq', label: 'Post-Quantum', icon: ShieldCheck },
                { id: 'weblink', label: 'Secure Link', icon: Lock },
                { id: 'standard', label: 'Standard Cleartext' },
              ].map((mode) => {
                const isSelected = filters.securityMode === mode.id;
                const Icon = mode.icon;
                return (
                  <TouchableOpacity
                    key={mode.id}
                    onPress={() => onChange({ securityMode: mode.id as any })}
                    style={{
                      flexDirection: 'row',
                      alignItems: 'center',
                      paddingHorizontal: 12,
                      paddingVertical: 7,
                      borderRadius: 10,
                      borderWidth: 1,
                      borderColor: isSelected ? '#10b981' : pal.border,
                      backgroundColor: isSelected ? 'rgba(16, 185, 129, 0.15)' : pal.card,
                    }}
                  >
                    {Icon && <Icon size={12} color={isSelected ? '#10b981' : pal.subtext} style={{ marginRight: 5 }} />}
                    <Text style={{ fontSize: 11, fontWeight: isSelected ? '700' : '500', color: isSelected ? '#10b981' : pal.text }}>
                      {mode.label}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>

            {/* 2. Sender / Recipient / Keyword Inputs */}
            <View style={{ gap: 10, marginBottom: 16 }}>
              <View>
                <Text style={{ fontSize: 11, fontWeight: '600', color: pal.subtext, marginBottom: 4 }}>From</Text>
                <TextInput
                  value={filters.from}
                  onChangeText={(v) => onChange({ from: v })}
                  placeholder="sender@example.com"
                  placeholderTextColor={pal.subtext}
                  style={{
                    backgroundColor: pal.inputBg,
                    borderWidth: 1,
                    borderColor: pal.border,
                    borderRadius: 10,
                    paddingHorizontal: 12,
                    paddingVertical: 8,
                    fontSize: 12,
                    color: pal.text,
                  }}
                />
              </View>

              <View>
                <Text style={{ fontSize: 11, fontWeight: '600', color: pal.subtext, marginBottom: 4 }}>To</Text>
                <TextInput
                  value={filters.to}
                  onChangeText={(v) => onChange({ to: v })}
                  placeholder="recipient@example.com"
                  placeholderTextColor={pal.subtext}
                  style={{
                    backgroundColor: pal.inputBg,
                    borderWidth: 1,
                    borderColor: pal.border,
                    borderRadius: 10,
                    paddingHorizontal: 12,
                    paddingVertical: 8,
                    fontSize: 12,
                    color: pal.text,
                  }}
                />
              </View>
            </View>

            {/* 3. Toggles */}
            <Text style={{ fontSize: 11, fontWeight: '700', textTransform: 'uppercase', color: pal.subtext, marginBottom: 8 }}>
              Attributes
            </Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 20 }}>
              {[
                { key: 'hasAttachment', label: 'Has Attachment' },
                { key: 'unreadOnly', label: 'Unread Only' },
                { key: 'starredOnly', label: 'Starred Only' },
                { key: 'cloakedOnly', label: 'Cloaked Subjects' },
              ].map((toggle) => {
                const isSelected = Boolean((filters as any)[toggle.key]);
                return (
                  <TouchableOpacity
                    key={toggle.key}
                    onPress={() => onChange({ [toggle.key]: !isSelected } as any)}
                    style={{
                      flexDirection: 'row',
                      alignItems: 'center',
                      paddingHorizontal: 12,
                      paddingVertical: 7,
                      borderRadius: 10,
                      borderWidth: 1,
                      borderColor: isSelected ? '#10b981' : pal.border,
                      backgroundColor: isSelected ? 'rgba(16, 185, 129, 0.15)' : pal.card,
                    }}
                  >
                    {isSelected && <Check size={12} color="#10b981" style={{ marginRight: 4 }} />}
                    <Text style={{ fontSize: 11, fontWeight: isSelected ? '700' : '500', color: isSelected ? '#10b981' : pal.text }}>
                      {toggle.label}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          </ScrollView>

          {/* Action Buttons */}
          <View style={{ flexDirection: 'row', gap: 10, paddingTop: 14, borderTopWidth: 1, borderTopColor: pal.border }}>
            <TouchableOpacity
              onPress={onClear}
              style={{
                flex: 1,
                paddingVertical: 12,
                borderRadius: 12,
                borderWidth: 1,
                borderColor: pal.border,
                backgroundColor: pal.card,
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Text style={{ fontSize: 12, fontWeight: '600', color: pal.text }}>Reset Filters</Text>
            </TouchableOpacity>

            <TouchableOpacity
              onPress={onApply}
              style={{
                flex: 1,
                paddingVertical: 12,
                borderRadius: 12,
                backgroundColor: '#059669',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Text style={{ fontSize: 12, fontWeight: '700', color: '#ffffff' }}>Apply Filters</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
};
