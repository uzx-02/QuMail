import React from 'react';
import { View, Text, TouchableOpacity, Modal, ScrollView } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { X, ShieldCheck, FileText } from 'lucide-react-native';
import { ThemeMode } from '../types';
import { getTheme } from '../lib/theme';
import { PRIVACY_POLICY_MD, TERMS_AND_CONDITIONS_MD } from '../lib/legalDocs';

interface LegalDocModalProps {
  visible: boolean;
  onClose: () => void;
  docType: 'privacy' | 'terms';
  theme?: ThemeMode;
  highContrast?: boolean;
}

export const LegalDocModal: React.FC<LegalDocModalProps> = ({
  visible,
  onClose,
  docType,
  theme = 'midnight',
  highContrast = false,
}) => {
  const insets = useSafeAreaInsets();
  const pal = getTheme(theme, highContrast);
  const isPrivacy = docType === 'privacy';
  const title = isPrivacy ? 'QuMail Privacy Policy' : 'QuMail Terms & Conditions';
  const rawText = isPrivacy ? PRIVACY_POLICY_MD : TERMS_AND_CONDITIONS_MD;

  // Split into paragraphs / lines for clean React Native rendering
  const paragraphs = rawText.split('\n\n');

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: pal.bg, paddingTop: insets.top, paddingBottom: insets.bottom }}>
        {/* Header */}
        <View
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'space-between',
            paddingHorizontal: 16,
            paddingVertical: 14,
            borderBottomWidth: 1,
            borderBottomColor: pal.border,
            backgroundColor: pal.headerBg,
          }}
        >
          <View style={{ flexDirection: 'row', alignItems: 'center', flex: 1, marginRight: 10 }}>
            {isPrivacy ? (
              <ShieldCheck size={20} color="#10b981" />
            ) : (
              <FileText size={20} color="#3b82f6" />
            )}
            <Text
              numberOfLines={1}
              style={{
                fontSize: 15,
                fontWeight: '700',
                color: pal.text,
                marginLeft: 10,
              }}
            >
              {title}
            </Text>
          </View>
          <TouchableOpacity
            onPress={onClose}
            style={{
              width: 32,
              height: 32,
              borderRadius: 16,
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: pal.innerCard,
            }}
          >
            <X size={16} color={pal.subtext} />
          </TouchableOpacity>
        </View>

        {/* Legal Text Body */}
        <ScrollView style={{ flex: 1, padding: 16 }} contentContainerStyle={{ paddingBottom: 60 }}>
          {paragraphs.map((para, idx) => {
            const trimmed = para.trim();
            if (!trimmed) return null;

            // Heading 1 / Title
            if (trimmed.startsWith('# ') || trimmed.includes('===')) {
              return (
                <Text
                  key={idx}
                  style={{
                    fontSize: 20,
                    fontWeight: '800',
                    color: pal.text,
                    marginBottom: 12,
                    marginTop: 6,
                  }}
                >
                  {trimmed.replace(/#+\s*/g, '').replace(/===/g, '').trim()}
                </Text>
              );
            }

            // Heading 2 / Section numbers (e.g. "1. Introduction" or "## 2. Who Operates")
            if (
              trimmed.startsWith('## ') ||
              /^\d+\\\.\s+/.test(trimmed) ||
              /^\d+\.\s+/.test(trimmed) ||
              trimmed.includes('---')
            ) {
              return (
                <Text
                  key={idx}
                  style={{
                    fontSize: 15,
                    fontWeight: '700',
                    color: isPrivacy ? '#10b981' : '#3b82f6',
                    marginTop: 16,
                    marginBottom: 8,
                  }}
                >
                  {trimmed.replace(/#+\s*/g, '').replace(/---/g, '').replace(/\\/g, '').trim()}
                </Text>
              );
            }

            // Heading 3 (e.g. "### 4.1 Account and Identity")
            if (trimmed.startsWith('### ')) {
              return (
                <Text
                  key={idx}
                  style={{
                    fontSize: 13,
                    fontWeight: '700',
                    color: pal.text,
                    marginTop: 10,
                    marginBottom: 4,
                  }}
                >
                  {trimmed.replace(/#+\s*/g, '').trim()}
                </Text>
              );
            }

            // Normal paragraph or bullet points
            return (
              <Text
                key={idx}
                style={{
                  fontSize: 12,
                  color: pal.subtext,
                  lineHeight: 19,
                  marginBottom: 10,
                }}
              >
                {trimmed.replace(/\\/g, '').replace(/\*\*/g, '')}
              </Text>
            );
          })}
        </ScrollView>
      </View>
    </Modal>
  );
};
