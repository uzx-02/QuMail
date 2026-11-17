import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  Modal,
  ScrollView,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import {
  X,
  Send,
  Lock,
  Shield,
  Link2,
  Globe,
  Paperclip,
  CheckCircle2,
  AlertTriangle,
  Flame,
  Clock,
  EyeOff,
  Key,
  ExternalLink,
} from 'lucide-react-native';
import { OutboundMessage, RecipientInfo, LanguageOption, ThemeMode } from '../types';
import { mailTransport } from '../bridge/MailTransport';
import { t } from '../lib/i18n';

interface ComposeModalProps {
  visible: boolean;
  onClose: () => void;
  onSend: (msg: OutboundMessage) => Promise<void>;
  replyTo?: { recipient: string; subject: string };
  language?: LanguageOption;
  theme?: ThemeMode;
}

export const ComposeModal: React.FC<ComposeModalProps> = ({
  visible,
  onClose,
  onSend,
  replyTo,
  language = 'en',
  theme = 'midnight',
}) => {
  const insets = useSafeAreaInsets();
  const [recipientsText, setRecipientsText] = useState(replyTo?.recipient || '');
  const [subject, setSubject] = useState(
    replyTo?.subject ? (replyTo.subject.startsWith('Re:') ? replyTo.subject : `Re: ${replyTo.subject}`) : ''
  );
  const [body, setBody] = useState('');
  const [securityMode, setSecurityMode] = useState<'pq' | 'weblink' | 'standard'>('pq');
  const [cloakSubject, setCloakSubject] = useState(false);
  const [burnAfterRead, setBurnAfterRead] = useState(false);
  const [expiresInHours, setExpiresInHours] = useState(24);
  const [passcode, setPasscode] = useState('');
  const [requireEmailOtp, setRequireEmailOtp] = useState(false);
  const [sending, setSending] = useState(false);
  const [recipientStatus, setRecipientStatus] = useState<RecipientInfo | null>(null);
  const [checkingRecipient, setCheckingRecipient] = useState(false);

  const isLight = theme === 'light';
  const containerBg = isLight ? 'bg-slate-50' : theme === 'dark' ? 'bg-slate-900' : 'bg-slate-950';
  const cardBg = isLight ? 'bg-white border-slate-200' : theme === 'dark' ? 'bg-slate-800 border-slate-700' : 'bg-slate-900 border-slate-800';
  const inputBg = isLight ? 'bg-slate-100 border-slate-200 text-slate-900' : theme === 'dark' ? 'bg-slate-800/80 border-slate-700 text-white' : 'bg-slate-900 border-slate-800 text-white';
  const textColor = isLight ? 'text-slate-900' : 'text-white';
  const subtextColor = isLight ? 'text-slate-500' : 'text-slate-400';

  const handleRecipientBlur = async () => {
    const trimmed = recipientsText.trim();
    if (!trimmed) {
      setRecipientStatus(null);
      return;
    }
    setCheckingRecipient(true);
    try {
      const info = await mailTransport.checkRecipient(trimmed);
      setRecipientStatus(info);
      // Auto-suggest weblink if recipient does not have PQC keys
      if (!info.registered && securityMode === 'pq') {
        // Do not force, but user will see recommendation banner
      }
    } catch {
      // ignore
    } finally {
      setCheckingRecipient(false);
    }
  };

  const handleSendPress = async () => {
    if (!recipientsText.trim()) {
      Alert.alert(t('compose_title', language), 'Please enter at least one recipient email.');
      return;
    }
    if (!subject.trim()) {
      Alert.alert(t('compose_title', language), 'Please provide an email subject.');
      return;
    }
    if (!body.trim()) {
      Alert.alert(t('compose_title', language), 'Message body cannot be empty.');
      return;
    }

    const recipients = recipientsText
      .split(',')
      .map((r) => r.trim())
      .filter((r) => r.length > 0);

    setSending(true);
    try {
      await onSend({
        recipients,
        subject,
        body,
        securityMode,
        cloakSubjectHeaders: cloakSubject,
        burnAfterRead,
        expiresInHours: securityMode === 'weblink' ? expiresInHours : undefined,
        passcode: passcode.trim() || undefined,
        requireEmailOtp,
      });

      // reset fields
      setRecipientsText('');
      setSubject('');
      setBody('');
      setRecipientStatus(null);
      setPasscode('');
      onClose();
    } catch (err: any) {
      Alert.alert('Send Error', err?.message || 'Failed to seal and send message.');
    } finally {
      setSending(false);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <View
        className={`flex-1 ${containerBg}`}
        style={{ paddingTop: insets.top, paddingBottom: insets.bottom }}
      >
        {/* Top Header */}
        <View className={`flex-row items-center justify-between px-4 py-3.5 border-b ${cardBg}`}>
          <View className="flex-row items-center">
            <View className="w-8 h-8 rounded-xl bg-emerald-500/15 border border-emerald-500/30 items-center justify-center mr-2.5">
              <Shield size={16} color="#10b981" />
            </View>
            <Text className={`text-base font-bold ${textColor}`}>
              {t('compose_title', language)}
            </Text>
          </View>
          <TouchableOpacity
            onPress={onClose}
            className={`w-8 h-8 rounded-full items-center justify-center ${isLight ? 'bg-slate-200' : 'bg-slate-800'}`}
          >
            <X size={16} color={isLight ? '#475569' : '#94a3b8'} />
          </TouchableOpacity>
        </View>

        <ScrollView className="flex-1 p-4" contentContainerStyle={{ paddingBottom: 60 }}>
          {/* Recipient Input */}
          <View className="mb-3.5">
            <Text className={`text-xs font-bold mb-1.5 ${subtextColor}`}>
              {t('compose_to', language)}
            </Text>
            <View className={`flex-row items-center rounded-xl border px-3.5 py-2.5 ${inputBg}`}>
              <TextInput
                placeholder={t('compose_to_placeholder', language)}
                placeholderTextColor={isLight ? '#94a3b8' : '#64748b'}
                value={recipientsText}
                onChangeText={setRecipientsText}
                onBlur={handleRecipientBlur}
                className={`flex-1 text-sm ${textColor}`}
                autoCapitalize="none"
                keyboardType="email-address"
              />
              {checkingRecipient && <ActivityIndicator size="small" color="#10b981" />}
            </View>

            {/* Recipient Verification Status Feedback */}
            {recipientStatus && (
              <View className="mt-2">
                {recipientStatus.registered ? (
                  <View className="flex-row items-center px-2 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30">
                    <CheckCircle2 size={13} color="#10b981" />
                    <Text className="text-[11px] text-emerald-400 ml-1.5 font-medium">
                      Quantum-Safe Recipient Verified (ML-KEM-768 key ready)
                    </Text>
                  </View>
                ) : (
                  <View className="p-3 rounded-xl bg-sky-500/10 border border-sky-500/30">
                    <View className="flex-row items-center justify-between">
                      <View className="flex-row items-center flex-1 mr-2">
                        <ExternalLink size={14} color="#38bdf8" />
                        <Text className="text-xs font-bold text-sky-400 ml-1.5">
                          External Recipient (Non-QuMail)
                        </Text>
                      </View>
                      {securityMode !== 'weblink' && (
                        <TouchableOpacity
                          onPress={() => setSecurityMode('weblink')}
                          className="px-2.5 py-1 rounded-lg bg-sky-600 active:bg-sky-700"
                        >
                          <Text className="text-[10px] font-bold text-white">Use Secure Link</Text>
                        </TouchableOpacity>
                      )}
                    </View>
                    <Text className="text-[11px] text-sky-300 mt-1 leading-normal">
                      This recipient does not have the QuMail app. Use <Text className="font-bold">Secure Private Link</Text> to send your message with zero-knowledge encryption that they can open in any browser!
                    </Text>
                  </View>
                )}
              </View>
            )}
          </View>

          {/* Subject Input */}
          <View className="mb-3.5">
            <Text className={`text-xs font-bold mb-1.5 ${subtextColor}`}>
              {t('compose_subject', language)}
            </Text>
            <TextInput
              placeholder={t('compose_subject_placeholder', language)}
              placeholderTextColor={isLight ? '#94a3b8' : '#64748b'}
              value={subject}
              onChangeText={setSubject}
              className={`rounded-xl border px-3.5 py-2.5 text-sm ${inputBg}`}
            />
          </View>

          {/* 3-Tier Security Mode Selector */}
          <View className={`mb-3.5 p-3.5 rounded-2xl border ${cardBg}`}>
            <Text className={`text-xs font-bold mb-2 ${textColor}`}>
              {t('compose_protection_tier', language)}
            </Text>
            <View className="space-y-2">
              {/* Option 1: Quantum-Safe (ML-KEM-768) */}
              <TouchableOpacity
                onPress={() => setSecurityMode('pq')}
                className={`p-3 rounded-xl border mb-2 flex-row items-start ${
                  securityMode === 'pq'
                    ? 'bg-emerald-500/15 border-emerald-500/60'
                    : isLight
                    ? 'bg-slate-100 border-slate-200'
                    : 'bg-slate-800/60 border-slate-700/60'
                }`}
              >
                <View className="w-7 h-7 rounded-lg bg-emerald-500/20 items-center justify-center mr-2.5 mt-0.5">
                  <Shield size={16} color="#10b981" />
                </View>
                <View className="flex-1">
                  <View className="flex-row items-center justify-between">
                    <Text className="text-xs font-bold text-emerald-400">
                      {t('compose_mode_pq', language)}
                    </Text>
                    {securityMode === 'pq' && <CheckCircle2 size={14} color="#10b981" />}
                  </View>
                  <Text className={`text-[11px] mt-0.5 leading-tight ${subtextColor}`}>
                    {t('compose_mode_pq_sub', language)}
                  </Text>
                </View>
              </TouchableOpacity>

              {/* Option 2: Secure Private Web Link (For Non-QuMail Users) */}
              <TouchableOpacity
                onPress={() => setSecurityMode('weblink')}
                className={`p-3 rounded-xl border mb-2 flex-row items-start ${
                  securityMode === 'weblink'
                    ? 'bg-sky-500/15 border-sky-500/60'
                    : isLight
                    ? 'bg-slate-100 border-slate-200'
                    : 'bg-slate-800/60 border-slate-700/60'
                }`}
              >
                <View className="w-7 h-7 rounded-lg bg-sky-500/20 items-center justify-center mr-2.5 mt-0.5">
                  <Link2 size={16} color="#38bdf8" />
                </View>
                <View className="flex-1">
                  <View className="flex-row items-center justify-between">
                    <Text className="text-xs font-bold text-sky-400">
                      {t('compose_mode_weblink', language)} (For Any Email / Browser)
                    </Text>
                    {securityMode === 'weblink' && <CheckCircle2 size={14} color="#38bdf8" />}
                  </View>
                  <Text className={`text-[11px] mt-0.5 leading-tight ${subtextColor}`}>
                    {t('compose_mode_weblink_sub', language)}
                  </Text>
                </View>
              </TouchableOpacity>

              {/* Option 3: Standard Email */}
              <TouchableOpacity
                onPress={() => setSecurityMode('standard')}
                className={`p-3 rounded-xl border flex-row items-start ${
                  securityMode === 'standard'
                    ? 'bg-slate-500/15 border-slate-400'
                    : isLight
                    ? 'bg-slate-100 border-slate-200'
                    : 'bg-slate-800/60 border-slate-700/60'
                }`}
              >
                <View className="w-7 h-7 rounded-lg bg-slate-500/20 items-center justify-center mr-2.5 mt-0.5">
                  <Globe size={16} color="#94a3b8" />
                </View>
                <View className="flex-1">
                  <View className="flex-row items-center justify-between">
                    <Text className={`text-xs font-bold ${textColor}`}>
                      {t('compose_mode_standard', language)}
                    </Text>
                    {securityMode === 'standard' && <CheckCircle2 size={14} color="#94a3b8" />}
                  </View>
                  <Text className={`text-[11px] mt-0.5 leading-tight ${subtextColor}`}>
                    {t('compose_mode_standard_sub', language)}
                  </Text>
                </View>
              </TouchableOpacity>
            </View>
          </View>

          {/* WebLink Extra Controls (Only visible when securityMode === 'weblink') */}
          {securityMode === 'weblink' && (
            <View className={`mb-3.5 p-3.5 rounded-2xl border ${cardBg}`}>
              <Text className="text-xs font-bold text-sky-400 mb-2.5 flex-row items-center">
                Secure Private Link Options
              </Text>

              {/* Expiry Selector */}
              <Text className={`text-[11px] font-semibold mb-1.5 ${subtextColor}`}>
                Link Lifespan / Expiry:
              </Text>
              <View className="flex-row mb-3">
                {[
                  { hours: 1, label: '1 Hour' },
                  { hours: 24, label: '24 Hours' },
                  { hours: 168, label: '7 Days' },
                  { hours: 720, label: '30 Days' },
                ].map((item) => (
                  <TouchableOpacity
                    key={item.hours}
                    onPress={() => setExpiresInHours(item.hours)}
                    className={`flex-1 py-1.5 rounded-lg border items-center mr-1.5 ${
                      expiresInHours === item.hours
                        ? 'bg-sky-500/20 border-sky-500/60'
                        : isLight
                        ? 'bg-slate-100 border-slate-200'
                        : 'bg-slate-800 border-slate-700'
                    }`}
                  >
                    <Text
                      className={`text-[11px] font-medium ${
                        expiresInHours === item.hours ? 'text-sky-400 font-bold' : subtextColor
                      }`}
                    >
                      {item.label}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              {/* Optional Passcode */}
              <Text className={`text-[11px] font-semibold mb-1.5 ${subtextColor}`}>
                Optional Extra Passcode (Zero-Knowledge):
              </Text>
              <TextInput
                placeholder="Leave blank or set a recipient password"
                placeholderTextColor={isLight ? '#94a3b8' : '#64748b'}
                value={passcode}
                onChangeText={setPasscode}
                secureTextEntry={true}
                className={`rounded-xl border px-3 py-2 text-xs mb-3 ${inputBg}`}
              />

              {/* Burn After Reading Toggle */}
              <TouchableOpacity
                onPress={() => setBurnAfterRead(!burnAfterRead)}
                className="flex-row items-center justify-between py-1"
              >
                <View className="flex-row items-center flex-1 mr-2">
                  <Flame size={15} color={burnAfterRead ? '#f59e0b' : '#64748b'} />
                  <Text className={`text-xs ml-2 font-medium ${textColor}`}>
                    {t('compose_burn_after_read', language)}
                  </Text>
                </View>
                <View
                  className={`w-10 h-5 rounded-full p-0.5 justify-center ${
                    burnAfterRead ? 'bg-amber-500' : isLight ? 'bg-slate-300' : 'bg-slate-700'
                  }`}
                >
                  <View
                    className={`w-4 h-4 rounded-full bg-white transition-all ${
                      burnAfterRead ? 'self-end' : 'self-start'
                    }`}
                  />
                </View>
              </TouchableOpacity>
            </View>
          )}

          {/* Privacy Controls (Subject cloaking) */}
          <View className={`mb-3.5 p-3 rounded-xl border flex-row items-center justify-between ${cardBg}`}>
            <View className="flex-row items-center flex-1 mr-2">
              <EyeOff size={15} color={cloakSubject ? '#10b981' : '#64748b'} />
              <View className="ml-2">
                <Text className={`text-xs font-medium ${textColor}`}>
                  {t('compose_hide_subject', language)}
                </Text>
                <Text className={`text-[10px] ${subtextColor}`}>
                  Hides subject from email servers and networks
                </Text>
              </View>
            </View>
            <TouchableOpacity
              onPress={() => setCloakSubject(!cloakSubject)}
              className={`w-10 h-5 rounded-full p-0.5 justify-center ${
                cloakSubject ? 'bg-emerald-500' : isLight ? 'bg-slate-300' : 'bg-slate-700'
              }`}
            >
              <View
                className={`w-4 h-4 rounded-full bg-white transition-all ${
                  cloakSubject ? 'self-end' : 'self-start'
                }`}
              />
            </TouchableOpacity>
          </View>

          {/* Message Body Input */}
          <View className="mb-4">
            <Text className={`text-xs font-bold mb-1.5 ${subtextColor}`}>
              {t('compose_body', language)}
            </Text>
            <TextInput
              placeholder={t('compose_body_placeholder', language)}
              placeholderTextColor={isLight ? '#94a3b8' : '#64748b'}
              value={body}
              onChangeText={setBody}
              multiline
              textAlignVertical="top"
              className={`rounded-2xl border p-4 text-sm min-h-[160px] ${inputBg}`}
            />
          </View>

          {/* Send Button */}
          <TouchableOpacity
            onPress={handleSendPress}
            disabled={sending}
            activeOpacity={0.85}
            className={`py-3.5 rounded-2xl flex-row items-center justify-center shadow-lg ${
              securityMode === 'weblink'
                ? 'bg-sky-600 active:bg-sky-700'
                : 'bg-emerald-600 active:bg-emerald-700'
            }`}
          >
            {sending ? (
              <ActivityIndicator color="#ffffff" size="small" />
            ) : (
              <>
                <Send size={18} color="#ffffff" />
                <Text className="text-white font-bold text-sm ml-2">
                  {securityMode === 'weblink'
                    ? 'Seal & Send Secure Link'
                    : t('compose_send', language)}
                </Text>
              </>
            )}
          </TouchableOpacity>
        </ScrollView>
      </View>
    </Modal>
  );
};
