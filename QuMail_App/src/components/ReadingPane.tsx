import React, { useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, Alert, Linking, Image } from 'react-native';
import {
  ArrowLeft,
  Star,
  Trash2,
  Reply,
  Forward,
  Paperclip,
  Lock,
  Download,
  Languages,
  CheckCircle2,
  Shield,
  Sparkles,
  Link2,
  ExternalLink,
} from 'lucide-react-native';
import { EmailMessage, LanguageOption, ThemeMode } from '../types';
import { SecurityBadge } from './SecurityBadge';
import { t, LANGUAGE_OPTIONS } from '../lib/i18n';
import { getTheme, getAccent } from '../lib/theme';
import { translateTextOffline, detectLanguage } from '../lib/offlineTranslator';
import { formatMailDate } from '../bridge/MailTransport';
import { getSenderAvatarUrl } from './MessageListItem';

interface ReadingPaneProps {
  message: EmailMessage | null;
  onBack: () => void;
  onDelete: (id: string) => void;
  onToggleStar: (id: string) => void;
  onReply: (message: EmailMessage) => void;
  language?: LanguageOption;
  theme?: ThemeMode;
  userAvatarUrl?: string;
  userEmail?: string;
  highContrast?: boolean;
  dyslexicFont?: boolean;
  showIconLabels?: boolean;
}

export const ReadingPane: React.FC<ReadingPaneProps> = ({
  message,
  onBack,
  onDelete,
  onToggleStar,
  onReply,
  language = 'en',
  theme = 'midnight',
  userAvatarUrl,
  userEmail,
  highContrast = false,
  dyslexicFont = false,
  showIconLabels = false,
}) => {
  const [isDecrypted, setIsDecrypted] = useState(true);
  const [translatedBody, setTranslatedBody] = useState<string | null>(null);
  const [translatedSubject, setTranslatedSubject] = useState<string | null>(null);
  const [isTranslating, setIsTranslating] = useState(false);
  const [activeTransLang, setActiveTransLang] = useState<LanguageOption>(language === 'en' ? 'hi' : 'en');

  const pal = getTheme(theme, highContrast);
  const isLight = theme === 'light';

  if (!message) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24, backgroundColor: pal.bg }}>
        <Shield size={48} color={pal.border} />
        <Text style={{ fontSize: 14, marginTop: 12, fontWeight: '500', color: pal.subtext }}>
          Select a message to read
        </Text>
      </View>
    );
  }

  const isPq = message.securityMode === 'pq' || (message.isQuMail && message.securityTier === 'pq_sealed');
  const isWebLink = message.securityMode === 'weblink' || message.securityTier === 'weblink';
  const isQuMail = isPq || isWebLink || message.isQuMail || message.indicator?.badgeLevel === 'SECURE';

  const handleTranslate = async (target: LanguageOption) => {
    setActiveTransLang(target);
    setIsTranslating(true);
    try {
      const [bodyRes, subjRes] = await Promise.all([
        translateTextOffline(message.body, target),
        translateTextOffline(message.subject, target),
      ]);
      setTranslatedBody(bodyRes.translatedText);
      setTranslatedSubject(subjRes.translatedText);
    } catch {
      Alert.alert('Translation Error', 'Could not translate message on device.');
    } finally {
      setIsTranslating(false);
    }
  };

  const clearTranslation = () => {
    setTranslatedBody(null);
    setTranslatedSubject(null);
  };

  const bodyStyle = {
    fontSize: 13,
    color: pal.text,
    lineHeight: dyslexicFont ? 26 : 21,
    letterSpacing: dyslexicFont ? 0.8 : 0,
    fontWeight: dyslexicFont ? ('500' as const) : ('400' as const),
  };

  return (
    <View style={{ flex: 1, backgroundColor: pal.bg }}>
      {/* Top Header Navigation */}
      <View
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
          paddingHorizontal: 16,
          paddingVertical: 12,
          borderBottomWidth: 1,
          borderBottomColor: pal.border,
          backgroundColor: pal.headerBg,
        }}
      >
        <TouchableOpacity
          onPress={onBack}
          style={{
            padding: 8,
            borderRadius: 12,
            borderWidth: 1,
            borderColor: pal.border,
            backgroundColor: pal.innerCard,
          }}
        >
          <ArrowLeft size={18} color={pal.text} />
        </TouchableOpacity>

        <View style={{ flexDirection: 'row', alignItems: 'center' }}>
          {/* Quick Offline Translate Button */}
          <TouchableOpacity
            onPress={() => {
              if (translatedBody) {
                clearTranslation();
              } else {
                handleTranslate(activeTransLang);
              }
            }}
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              paddingHorizontal: 12,
              paddingVertical: 6,
              borderRadius: 12,
              borderWidth: 1,
              borderColor: translatedBody ? 'rgba(16, 185, 129, 0.4)' : pal.border,
              backgroundColor: translatedBody ? 'rgba(16, 185, 129, 0.15)' : pal.innerCard,
              marginRight: 8,
            }}
          >
            <Languages size={15} color={translatedBody ? '#10b981' : pal.text} />
            <Text
              style={{
                fontSize: 11,
                marginLeft: 6,
                fontWeight: '600',
                color: translatedBody ? '#10b981' : pal.text,
              }}
            >
              {translatedBody ? t('reading_original', language) : t('reading_translate', language)}
            </Text>
          </TouchableOpacity>

          {/* Star Button */}
          <TouchableOpacity
            onPress={() => onToggleStar(message.id)}
            style={{
              padding: 8,
              borderRadius: 12,
              borderWidth: 1,
              borderColor: pal.border,
              backgroundColor: pal.innerCard,
              marginRight: 8,
            }}
          >
            <Star
              size={18}
              color={message.starred ? '#f59e0b' : pal.subtext}
              fill={message.starred ? '#f59e0b' : 'transparent'}
            />
          </TouchableOpacity>

          {/* Delete Button */}
          <TouchableOpacity
            onPress={() => {
              if (!isQuMail || message.securityMode === 'standard') {
                Alert.alert(
                  'Action Restricted',
                  'Standard unsealed emails cannot be deleted or modified from the QuMail Sovereign Enclave to preserve provider mailbox audit integrity.'
                );
                return;
              }
              Alert.alert(t('reading_delete', language), 'Move this message to trash?', [
                { text: 'Cancel', style: 'cancel' },
                {
                  text: 'Delete',
                  style: 'destructive',
                  onPress: () => {
                    onDelete(message.id);
                    onBack();
                  },
                },
              ]);
            }}
            style={{
              padding: 8,
              borderRadius: 12,
              borderWidth: 1,
              borderColor: !isQuMail || message.securityMode === 'standard' ? pal.border : 'rgba(244, 63, 94, 0.3)',
              backgroundColor: !isQuMail || message.securityMode === 'standard' ? pal.innerCard : isLight ? '#fff1f2' : pal.innerCard,
              opacity: !isQuMail || message.securityMode === 'standard' ? 0.45 : 1,
            }}
          >
            <Trash2 size={18} color={!isQuMail || message.securityMode === 'standard' ? pal.subtext : '#f43f5e'} />
          </TouchableOpacity>
        </View>
      </View>

      <ScrollView style={{ flex: 1, padding: 16 }} contentContainerStyle={{ paddingBottom: 60 }}>
        {/* Interactive Offline Language Selector */}
        <View
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            padding: 8,
            borderRadius: 12,
            borderWidth: 1,
            borderColor: pal.border,
            backgroundColor: pal.innerCard,
            marginBottom: 12,
          }}
        >
          <Languages size={14} color="#10b981" />
          <Text style={{ fontSize: 11, fontWeight: '700', color: pal.text, marginLeft: 6, marginRight: 8 }}>
            {t('translate_to', language)}:
          </Text>
          {(['hi', 'mr', 'en'] as LanguageOption[]).map((tgt) => {
            const isSelected = activeTransLang === tgt && Boolean(translatedBody);
            return (
              <TouchableOpacity
                key={tgt}
                onPress={() => handleTranslate(tgt)}
                style={{
                  paddingHorizontal: 10,
                  paddingVertical: 5,
                  borderRadius: 8,
                  borderWidth: 1,
                  marginRight: 6,
                  borderColor: isSelected ? '#10b981' : pal.border,
                  backgroundColor: isSelected ? 'rgba(16, 185, 129, 0.2)' : pal.card,
                }}
              >
                <Text style={{ fontSize: 11, fontWeight: '700', color: isSelected ? '#10b981' : pal.text }}>
                  {tgt === 'hi' ? 'हिन्दी' : tgt === 'mr' ? 'मराठी' : 'English'}
                </Text>
              </TouchableOpacity>
            );
          })}
          {translatedBody && (
            <TouchableOpacity onPress={clearTranslation} style={{ marginLeft: 'auto', paddingHorizontal: 6, paddingVertical: 4 }}>
              <Text style={{ fontSize: 11, color: '#f43f5e', fontWeight: '700' }}>
                {t('reading_original', language)}
              </Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Subject Title */}
        <Text style={{ fontSize: 18, fontWeight: '700', color: pal.text, marginBottom: 12, lineHeight: 24 }}>
          {translatedSubject || message.subject}
        </Text>

        {/* Sender details card */}
        <View
          style={{
            padding: 14,
            borderRadius: 16,
            borderWidth: 1,
            borderColor: pal.border,
            backgroundColor: pal.card,
            marginBottom: 12,
          }}
        >
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', flex: 1, marginRight: 8 }}>
              <View
                style={{
                  width: 40,
                  height: 40,
                  borderRadius: 20,
                  overflow: 'hidden',
                  marginRight: 12,
                  borderWidth: 1,
                  borderColor: isPq ? '#10b981' : isWebLink ? '#0284c7' : pal.border,
                }}
              >
                <Image
                  source={{
                    uri: getSenderAvatarUrl(message.sender, message.senderEmail, userEmail, userAvatarUrl),
                  }}
                  style={{ width: 38, height: 38, borderRadius: 19 }}
                />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 13, fontWeight: '700', color: pal.text }}>{message.sender}</Text>
                <Text style={{ fontSize: 11, fontFamily: 'monospace', color: pal.subtext, marginTop: 2 }}>
                  {message.senderEmail}
                </Text>
              </View>
            </View>
            <Text style={{ fontSize: 11, color: pal.subtext }}>
              {formatMailDate(message.timestamp || message.date)}
            </Text>
          </View>

          <View style={{ marginTop: 8, paddingTop: 8, borderTopWidth: 1, borderTopColor: pal.border }}>
            <Text style={{ fontSize: 11, color: pal.subtext }}>
              {t('reading_to', language)}:{' '}
              <Text style={{ fontFamily: 'monospace', color: pal.text }}>{message.recipients.join(', ')}</Text>
            </Text>
          </View>
        </View>

        {/* Quantum-Safe Status Banner */}
        {isPq && (
          <View
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: 12,
              borderRadius: 12,
              backgroundColor: 'rgba(16, 185, 129, 0.1)',
              borderWidth: 1,
              borderColor: 'rgba(16, 185, 129, 0.3)',
              marginBottom: 12,
            }}
          >
            <View style={{ flexDirection: 'row', alignItems: 'center', flex: 1 }}>
              <Lock size={15} color="#10b981" />
              <View style={{ marginLeft: 8, flex: 1 }}>
                <Text style={{ fontSize: 12, fontWeight: '700', color: '#10b981' }}>
                  {t('sec_quantum_safe', language)}
                </Text>
                <Text style={{ fontSize: 10, color: pal.subtext, marginTop: 2 }}>
                  Decrypted on-device with ML-KEM-768 + ML-DSA-65.
                </Text>
              </View>
            </View>
          </View>
        )}

        {/* Secure Private Link Status Banner */}
        {isWebLink && (
          <View
            style={{
              padding: 12,
              borderRadius: 12,
              backgroundColor: 'rgba(56, 189, 248, 0.1)',
              borderWidth: 1,
              borderColor: 'rgba(56, 189, 248, 0.3)',
              marginBottom: 12,
            }}
          >
            <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 4 }}>
              <Link2 size={15} color="#38bdf8" />
              <Text style={{ fontSize: 12, fontWeight: '700', color: '#38bdf8', marginLeft: 6 }}>
                Secure Private Link (Zero-Knowledge)
              </Text>
            </View>
            <Text style={{ fontSize: 10, color: pal.subtext, lineHeight: 15 }}>
              This confidential message was delivered via an ephemeral secure web portal. The decryption key was embedded client-side in the URL fragment without touching server memory.
            </Text>
          </View>
        )}

        {/* Translated Notification Banner */}
        {translatedBody && (
          <View
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: 10,
              borderRadius: 12,
              backgroundColor: 'rgba(99, 102, 241, 0.1)',
              borderWidth: 1,
              borderColor: 'rgba(99, 102, 241, 0.3)',
              marginBottom: 12,
            }}
          >
            <View style={{ flexDirection: 'row', alignItems: 'center' }}>
              <Sparkles size={14} color="#6366f1" />
              <Text style={{ fontSize: 11, fontWeight: '600', color: '#818cf8', marginLeft: 6 }}>
                Translated on-device to {activeTransLang.toUpperCase()}
              </Text>
            </View>
            <TouchableOpacity onPress={clearTranslation}>
              <Text style={{ fontSize: 11, fontWeight: '700', color: '#818cf8', textDecorationLine: 'underline' }}>
                {t('reading_original', language)}
              </Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Message Body */}
        {isQuMail ? (
          <View
            style={{
              padding: 16,
              borderRadius: 16,
              borderWidth: 1,
              borderColor: pal.border,
              backgroundColor: pal.card,
              minHeight: 160,
            }}
          >
            <Text style={bodyStyle}>
              {translatedBody || message.body}
            </Text>
          </View>
        ) : (
          <View
            style={{
              padding: 20,
              borderRadius: 16,
              borderWidth: 1,
              borderColor: 'rgba(239, 68, 68, 0.25)',
              backgroundColor: isLight ? '#fef2f2' : 'rgba(239, 68, 68, 0.06)',
              alignItems: 'center',
            }}
          >
            <View
              style={{
                width: 48,
                height: 48,
                borderRadius: 24,
                backgroundColor: 'rgba(239, 68, 68, 0.15)',
                alignItems: 'center',
                justifyContent: 'center',
                marginBottom: 12,
              }}
            >
              <Shield size={24} color="#ef4444" />
            </View>
            <Text style={{ fontSize: 15, fontWeight: '700', color: pal.text, marginBottom: 6, textAlign: 'center' }}>
              Standard Provider Email (Unencrypted)
            </Text>
            <Text
              style={{
                fontSize: 12,
                color: pal.subtext,
                lineHeight: 18,
                textAlign: 'center',
                marginBottom: 16,
              }}
            >
              This message was delivered through your regular email provider without QuMail post-quantum sealing. To maintain quantum-safe enclave isolation, standard cleartext messages cannot be displayed inside the QuMail enclave viewer.
            </Text>
            <TouchableOpacity
              onPress={() => Linking.openURL('https://mail.google.com')}
              activeOpacity={0.8}
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                paddingHorizontal: 16,
                paddingVertical: 10,
                borderRadius: 12,
                backgroundColor: '#2563eb',
              }}
            >
              <Text style={{ fontSize: 12, fontWeight: '700', color: '#ffffff', marginRight: 6 }}>
                Open in Gmail
              </Text>
              <ExternalLink size={14} color="#ffffff" />
            </TouchableOpacity>
          </View>
        )}

        {/* Action Bottom Bar */}
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 16 }}>
          <TouchableOpacity
            onPress={() => onReply(message)}
            style={{
              flex: 1,
              paddingVertical: 12,
              borderRadius: 14,
              backgroundColor: '#059669',
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'center',
              elevation: 4,
            }}
          >
            <Reply size={16} color="#ffffff" />
            <Text style={{ color: '#ffffff', fontSize: 12, fontWeight: '700', marginLeft: 6 }}>
              {t('reading_reply', language)}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={() => onReply(message)}
            style={{
              flex: 1,
              paddingVertical: 12,
              borderRadius: 14,
              borderWidth: 1,
              borderColor: pal.border,
              backgroundColor: pal.card,
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Forward size={16} color={pal.text} />
            <Text style={{ fontSize: 12, fontWeight: '700', marginLeft: 6, color: pal.text }}>
              {t('reading_forward', language)}
            </Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </View>
  );
};
