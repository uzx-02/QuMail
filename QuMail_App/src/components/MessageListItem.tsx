import React from 'react';
import { View, Text, TouchableOpacity, Image } from 'react-native';
import { Star, Lock, Paperclip, Shield, Link2 } from 'lucide-react-native';
import { EmailMessage, ThemeMode, ListDensityOption } from '../types';
import { formatMailDate } from '../bridge/MailTransport';

export function getSenderAvatarUrl(
  sender: string,
  senderEmail: string,
  userEmail?: string,
  userAvatarUrl?: string
): string {
  if (
    userAvatarUrl &&
    userEmail &&
    senderEmail &&
    userEmail.trim().toLowerCase() === senderEmail.trim().toLowerCase()
  ) {
    return userAvatarUrl;
  }
  const str = senderEmail || sender || 'QuMail';
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  const colors = ['0D9488', '0284C7', '4F46E5', '7C3AED', 'C026D3', 'E11D48', 'D97706', '059669'];
  const bg = colors[Math.abs(hash) % colors.length];
  const name = encodeURIComponent(sender || senderEmail || 'U');
  return `https://ui-avatars.com/api/?name=${name}&background=${bg}&color=fff&size=128&bold=true`;
}

interface MessageListItemProps {
  message: EmailMessage;
  onPress: (msg: EmailMessage) => void;
  onToggleStar: (id: string) => void;
  selected?: boolean;
  showAvatars?: boolean;
  userEmail?: string;
  userAvatarUrl?: string;
  theme?: ThemeMode;
  density?: ListDensityOption;
  hidePreviews?: boolean;
}

export const MessageListItem: React.FC<MessageListItemProps> = React.memo(({
  message,
  onPress,
  onToggleStar,
  selected = false,
  showAvatars = true,
  userEmail,
  userAvatarUrl,
  theme = 'midnight',
  density = 'comfortable',
  hidePreviews = false,
}) => {
  const isPq = message.securityMode === 'pq' || (message.isQuMail && message.securityTier === 'pq_sealed');
  const isWebLink = message.securityMode === 'weblink' || message.securityTier === 'weblink';
  const initial = (message.sender || '?')
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() || '')
    .join('') || '?';

  const isUserSender = Boolean(
    userEmail &&
    message.senderEmail &&
    userEmail.trim().toLowerCase() === message.senderEmail.trim().toLowerCase()
  );

  const isLight = theme === 'light';
  const isMidnight = theme === 'midnight';

  // Dynamic Theme Colors
  const borderCol = isLight ? 'border-slate-200' : isMidnight ? 'border-slate-900' : 'border-slate-800';
  const bgCol = selected
    ? isLight
      ? 'bg-emerald-50'
      : 'bg-emerald-950/20'
    : message.seen
    ? isLight
      ? 'bg-white'
      : isMidnight
      ? 'bg-slate-950'
      : 'bg-slate-900'
    : isLight
    ? 'bg-slate-50'
    : isMidnight
    ? 'bg-slate-900/60'
    : 'bg-slate-800/60';

  const senderTextCol = message.seen
    ? isLight
      ? 'text-slate-600 font-normal'
      : 'text-slate-300 font-normal'
    : isLight
    ? 'text-slate-900 font-bold'
    : 'text-white font-bold';

  const subjectTextCol = message.seen
    ? isLight
      ? 'text-slate-500 font-normal'
      : 'text-slate-400 font-normal'
    : isLight
    ? 'text-slate-800 font-semibold'
    : 'text-slate-200 font-medium';

  const snippetTextCol = isLight ? 'text-slate-400' : 'text-slate-500';
  const paddingVertical = density === 'compact' ? 'py-2 px-3' : 'py-3.5 px-4';

  return (
    <TouchableOpacity
      onPress={() => onPress(message)}
      activeOpacity={0.7}
      className={`${paddingVertical} border-b ${borderCol} flex-row items-center ${bgCol}`}
    >
      {/* Sender Avatar */}
      {showAvatars && (
        <View
          className={`w-9 h-9 rounded-full items-center justify-center mr-3 overflow-hidden ${
            isPq
              ? 'border border-emerald-500/50'
              : isWebLink
              ? 'border border-sky-500/50'
              : isLight
              ? 'border border-slate-300'
              : 'border border-slate-700'
          }`}
        >
          <Image
            source={{
              uri: getSenderAvatarUrl(message.sender, message.senderEmail, userEmail, userAvatarUrl),
            }}
            style={{ width: 36, height: 36, borderRadius: 18 }}
          />
        </View>
      )}

      {/* Main message summary */}
      <View className="flex-1 pr-2">
        <View className="flex-row items-center justify-between mb-1">
          <View className="flex-row items-center flex-1 mr-2 overflow-hidden">
            {!message.seen && (
              <View className="w-2 h-2 rounded-full bg-emerald-500 mr-2 flex-shrink-0" />
            )}
            <Text className={`text-sm ${senderTextCol} flex-shrink`} numberOfLines={1}>
              {message.sender}
            </Text>

            {/* Compact Quantum-Safe Lock Badge (does not cut off sender name) */}
            {isPq && (
              <View className="flex-row items-center ml-1.5 px-1.5 py-0.5 rounded bg-emerald-500/15 border border-emerald-500/40 flex-shrink-0">
                <Lock size={10} color="#10b981" />
                <Text className="text-[9px] text-emerald-400 font-extrabold ml-1">PQ</Text>
              </View>
            )}

            {/* Compact Secure Link Badge */}
            {isWebLink && (
              <View className="flex-row items-center ml-1.5 px-1.5 py-0.5 rounded bg-sky-500/15 border border-sky-500/40 flex-shrink-0">
                <Link2 size={10} color="#38bdf8" />
                <Text className="text-[9px] text-sky-400 font-extrabold ml-1">LINK</Text>
              </View>
            )}

            {message.hasAttachments && (
              <View className="ml-1.5 flex-shrink-0">
                <Paperclip size={12} color={isLight ? '#64748b' : '#94a3b8'} />
              </View>
            )}
          </View>

          {/* Clean concise date without UTC/GMT bloat */}
          <Text className={`text-[11px] font-medium ${snippetTextCol} flex-shrink-0 ml-1`}>
            {formatMailDate(message.timestamp || message.date)}
          </Text>
        </View>

        {/* Subject line */}
        <Text className={`text-xs mb-0.5 ${subjectTextCol}`} numberOfLines={1}>
          {message.subject}
        </Text>

        {/* Snippet preview */}
        {!hidePreviews && (
          <Text className={`text-[11px] leading-tight ${snippetTextCol}`} numberOfLines={1}>
            {message.snippet}
          </Text>
        )}
      </View>

      {/* Star action */}
      <TouchableOpacity
        onPress={() => onToggleStar(message.id)}
        hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
        className="p-1.5"
      >
        <Star
          size={16}
          color={message.starred ? '#f59e0b' : isLight ? '#cbd5e1' : '#475569'}
          fill={message.starred ? '#f59e0b' : 'transparent'}
        />
      </TouchableOpacity>
    </TouchableOpacity>
  );
});
