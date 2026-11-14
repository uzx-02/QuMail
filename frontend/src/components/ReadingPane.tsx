import React, { useState, useEffect, useMemo } from 'react';
import UseAnimations from 'react-useanimations';
import star from 'react-useanimations/lib/star';
import {
  ArrowLeft,
  Reply,
  Forward,
  Trash2,
  Printer,
  ShieldCheck,
  AlertTriangle,
  ShieldAlert,
  Shield,
  Download,
  FileText,
  CheckCircle2,
  Lock,
  Key,
  ChevronDown,
  ChevronUp,
  Star,
  ImageOff,
  ExternalLink,
  MoreHorizontal,
  ReplyAll,
  Languages,
  RefreshCw,
  X,
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { api } from '../lib/api';
import { EmailMessage, FontFamilyOption, FontSizeOption, LanguageOption } from '../types';
import { FONT_FAMILY_STYLE, FONT_SIZE_STYLE } from '../lib/appearance';
import { resolveDisplaySubject, sanitizeExternalUrl } from '../lib/privacy';
import { t } from '../lib/i18n';

interface ReadingPaneProps {
  message: EmailMessage | null;
  userEmail?: string;
  userAvatarUrl?: string;
  onReply: (msg: EmailMessage, replyAll?: boolean) => void;
  onForward: (msg: EmailMessage) => void;
  onDelete: (id: string) => void;
  onToggleStar?: (id: string, e: React.MouseEvent) => void;
  onClose: () => void;
  onShowProtectionNotice?: (msg: string) => void;
  blockRemoteImages?: boolean;
  confirmExternalLinks?: boolean;
  fontFamily?: FontFamilyOption;
  fontSize?: FontSizeOption;
  showIconLabels?: boolean;
  language?: LanguageOption;
  enableOfflineTranslation?: boolean;
  allowStandardMailTranslation?: boolean;
  onOpenSettings?: (tab?: 'general' | 'labels' | 'accounts' | 'security' | 'appearance' | 'accessibility' | 'offline_translation' | 'about') => void;
}

export const ReadingPane: React.FC<ReadingPaneProps> = ({
  message,
  userEmail,
  userAvatarUrl,
  onReply,
  onForward,
  onDelete,
  onToggleStar,
  onClose,
  onShowProtectionNotice,
  blockRemoteImages = true,
  confirmExternalLinks = true,
  fontFamily = 'sans',
  fontSize = 'medium',
  showIconLabels = false,
  language,
  enableOfflineTranslation = false,
  allowStandardMailTranslation = false,
  onOpenSettings,
}) => {
  const [isReceiptOpen, setIsReceiptOpen] = useState(false);
  const [allowRemoteImages, setAllowRemoteImages] = useState(false);
  const [showQuotedText, setShowQuotedText] = useState(false);
  const [savingAttachmentName, setSavingAttachmentName] = useState<string | null>(null);
  const [pendingLink, setPendingLink] = useState<{
    originalUrl: string;
    cleanUrl: string;
    strippedParams: string[];
  } | null>(null);

  // On-Demand Offline Translation state
  const [translatedText, setTranslatedText] = useState<string | null>(null);
  const [translatedSubject, setTranslatedSubject] = useState<string | null>(null);
  const [isTranslating, setIsTranslating] = useState(false);
  const [showTranslated, setShowTranslated] = useState(false);
  const [modelPromptOpen, setModelPromptOpen] = useState(false);
  const [targetLang, setTargetLang] = useState<'hi' | 'mr' | 'en'>(() => {
    if (language === 'hi' || language === 'mr') return language;
    return 'hi';
  });

  // Standard Email on-demand fetch state
  const [loadedStandardBody, setLoadedStandardBody] = useState<string | null>(null);
  const [loadedStandardSubject, setLoadedStandardSubject] = useState<string | null>(null);
  const [isFetchingStandard, setIsFetchingStandard] = useState(false);

  const { displaySubject, isCloaked, cleanBody } = useMemo(() => {
    if (!message) return { displaySubject: '', isCloaked: false, cleanBody: '' };
    return resolveDisplaySubject(message);
  }, [message]);

  const isQuMail = Boolean(
    message?.isQuMail !== undefined
      ? message.isQuMail
      : message?.securityTier === 'pq_sealed' ||
        message?.securityTier === 'weblink' ||
        message?.securityMode === 'pq' ||
        message?.securityMode === 'weblink' ||
        message?.indicator?.badgeLevel === 'SECURE' ||
        message?.subject?.startsWith('[QuMail Secure Link]')
  );

  const isSecure = message?.indicator?.badgeLevel === 'SECURE';
  const isWebLink = message?.securityTier === 'weblink' || message?.securityMode === 'weblink' || message?.subject?.startsWith('[QuMail Secure Link]');
  const isStandardEmail = !isQuMail || message?.indicator?.badgeLevel === 'NEUTRAL';

  const cleanDisplaySubject = useMemo(() => {
    let subj = displaySubject || '(No Subject)';
    if (allowStandardMailTranslation && !isQuMail) {
      subj = loadedStandardSubject || message?.rawStandardSubject || displaySubject || '(No Subject)';
    }
    return (subj || '(No Subject)')
      .replace(/\s*\[(Shield|Shielded|Quantum-Safe|QuMail Secure Link|Encrypted)\]\s*/gi, ' ')
      .replace(/\s*•+\s*\[Shielded\]/gi, '')
      .replace(/\s*•+\s*/g, '')
      .trim() || '(No Subject)';
  }, [displaySubject, allowStandardMailTranslation, isQuMail, loadedStandardSubject, message?.rawStandardSubject]);

  const effectiveSubject = useMemo(() => {
    if (showTranslated && translatedSubject) {
      return translatedSubject;
    }
    return cleanDisplaySubject;
  }, [showTranslated, translatedSubject, cleanDisplaySubject]);

  const displayedBodyText = useMemo(() => {
    let body = cleanBody;
    const realStandardBody = (loadedStandardBody || message?.rawStandardBody || '').trim();
    if (allowStandardMailTranslation && !isQuMail && realStandardBody) {
      body = loadedStandardBody || message?.rawStandardBody || cleanBody;
    } else if (isStandardEmail) {
      body = body.replace(/\s*\[Shielded\]/g, '');
    }
    if (blockRemoteImages && !allowRemoteImages) {
      body = body.replace(/<img[^>]+src=["'](https?:\/\/[^"']+)["'][^>]*>/gi, '[Blocked Remote Image]');
    }
    return body;
  }, [cleanBody, isStandardEmail, isQuMail, allowStandardMailTranslation, loadedStandardBody, message?.rawStandardBody, blockRemoteImages, allowRemoteImages]);

  const effectiveBodyText = useMemo(() => {
    if (showTranslated && translatedText) {
      return translatedText;
    }
    return displayedBodyText;
  }, [showTranslated, translatedText, displayedBodyText]);

  // Split message body into new content and quoted reply chain
  const { mainText, quotedText } = useMemo(() => {
    const text = effectiveBodyText;
    if (!text) return { mainText: '', quotedText: '' };

    const quoteRegex = /(?:^|\r?\n)(?:On\s+[^\n]+wrote:[\r\n]+(?:>.*(?:\r?\n|$))+|---------- Forwarded message ---------[\r\n]+[\s\S]+|-----Original Message-----[\r\n]+[\s\S]+|(?:>.*(?:\r?\n|$)){2,})/i;

    const match = quoteRegex.exec(text);
    if (match && match.index !== undefined) {
      const splitIdx = match.index;
      const main = text.slice(0, splitIdx).trimEnd();
      const quoted = text.slice(splitIdx).trim();
      return { mainText: main, quotedText: quoted };
    }
    return { mainText: text, quotedText: '' };
  }, [effectiveBodyText]);

  // Reset per-message state whenever the user opens a different email
  useEffect(() => {
    setAllowRemoteImages(false);
    setPendingLink(null);
    setShowQuotedText(false);
    setSavingAttachmentName(null);
    setTranslatedText(null);
    setTranslatedSubject(null);
    setShowTranslated(false);
    setModelPromptOpen(false);
    setLoadedStandardBody(message?.rawStandardBody || null);
    setLoadedStandardSubject(message?.rawStandardSubject || null);

    if (allowStandardMailTranslation && !isQuMail && message?.id) {
      if (!message.rawStandardBody || (message.body && message.body.includes('QUMAIL ZERO-TRUST PRIVACY SHIELD'))) {
        setIsFetchingStandard(true);
        api.fetchStandardEmailBody(message.id)
          .then((res) => {
            if (res.success && res.body) {
              setLoadedStandardBody(res.body);
              if (res.subject) {
                setLoadedStandardSubject(res.subject);
              }
            }
          })
          .catch(() => {})
          .finally(() => setIsFetchingStandard(false));
      }
    }
  }, [message?.id]); // STRICTLY key on message?.id only

  // Load cached translation on message selection if already translated in vault
  useEffect(() => {
    if (!enableOfflineTranslation || !message?.id) return;
    api.getCachedTranslation(message.id, targetLang)
      .then((res) => {
        if (res.status === 'ok' && res.fromCache && res.translatedText) {
          setTranslatedText(res.translatedText);
          if (res.translatedSubject) {
            setTranslatedSubject(res.translatedSubject);
          }
        }
      })
      .catch(() => {});
  }, [message?.id, targetLang, enableOfflineTranslation]);

  const handleCancelTranslate = async () => {
    try {
      await api.cancelTranslation();
      setIsTranslating(false);
      onShowProtectionNotice?.('Translation cancelled');
    } catch {
      setIsTranslating(false);
    }
  };

  const handleTriggerTranslate = async (langChoice?: 'hi' | 'mr' | 'en') => {
    if (!message) return;
    const tgt = langChoice || targetLang;
    setTargetLang(tgt);

    try {
      const status = await api.getTranslationStatus();
      if (!status?.isInstalled) {
        setModelPromptOpen(true);
        onShowProtectionNotice?.(t(language, 'trans_model_not_installed') || 'Offline translation model is not installed. Please download it in Settings.');
        return;
      }
    } catch {
      // If status check fails, proceed cautiously
    }

    let bodyToTranslate = (!isQuMail && (loadedStandardBody || message.rawStandardBody))
      ? (loadedStandardBody || message.rawStandardBody)
      : (message.body || '');
    let subjToTranslate = (!isQuMail && (loadedStandardSubject || message.rawStandardSubject))
      ? (loadedStandardSubject || message.rawStandardSubject)
      : cleanDisplaySubject;

    setIsTranslating(true);
    try {
      if (!isQuMail && allowStandardMailTranslation && (!bodyToTranslate || bodyToTranslate.includes('QUMAIL ZERO-TRUST PRIVACY SHIELD'))) {
        const stdRes = await api.fetchStandardEmailBody(message.id);
        if (stdRes.success && stdRes.body) {
          bodyToTranslate = stdRes.body;
          setLoadedStandardBody(stdRes.body);
          if (stdRes.subject) {
            subjToTranslate = stdRes.subject;
            setLoadedStandardSubject(stdRes.subject);
          }
        }
      }

      if (!bodyToTranslate || bodyToTranslate.includes('QUMAIL ZERO-TRUST PRIVACY SHIELD')) {
        onShowProtectionNotice?.('Could not load email body for translation. Please verify connection.');
        return;
      }

      const res = await api.translateEmailContent(message.id, bodyToTranslate || '', tgt, subjToTranslate);
      if (res.status === 'cancelled') {
        onShowProtectionNotice?.('Translation cancelled');
        return;
      }
      if (res.status === 'ok' && res.translatedText) {
        setTranslatedText(res.translatedText);
        setTranslatedSubject(res.translatedSubject || null);
        setShowTranslated(true);
        onShowProtectionNotice?.(`Translated to ${tgt === 'hi' ? 'हिन्दी' : tgt === 'mr' ? 'मराठी' : 'English'} on device`);
      } else {
        onShowProtectionNotice?.(res.error || 'Translation failed');
      }
    } catch (err: any) {
      onShowProtectionNotice?.(err?.message || 'Translation failed');
    } finally {
      setIsTranslating(false);
    }
  };

  const handleDeleteTranslation = async () => {
    if (!message) return;
    try {
      await api.deleteTranslationLog(message.id);
      setTranslatedText(null);
      setTranslatedSubject(null);
      setShowTranslated(false);
      onShowProtectionNotice?.('Cached translation deleted');
    } catch {
      // ignore
    }
  };

  const remoteImageUrls = useMemo(() => {
    const body = message?.body || '';
    const urls = new Set<string>();
    const imgTagRegex = /<img[^>]+src=["'](https?:\/\/[^"']+)["'][^>]*>/gi;
    let match: RegExpExecArray | null;
    while ((match = imgTagRegex.exec(body)) !== null) {
      urls.add(match[1]);
    }
    const directImgUrlRegex = /https?:\/\/[^\s<>"{}|\\^`[\]]+\.(?:png|jpe?g|gif|webp|svg)(?:\?[^\s<>"{}|\\^`[\]]*)?/gi;
    while ((match = directImgUrlRegex.exec(body)) !== null) {
      urls.add(match[0]);
    }
    return Array.from(urls);
  }, [message?.body]);

  if (!message) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-[#F6F8FC] dark:bg-[#0A0E17] select-none">
        <div className="w-16 h-16 rounded-full bg-blue-100 dark:bg-slate-800 flex items-center justify-center text-[#0B57D0] dark:text-[#818CF8] mb-4">
          <FileText className="w-8 h-8" />
        </div>
        <h3 className="text-base font-bold text-[#202124] dark:text-[#F1F5F9] mb-1">
          No message selected
        </h3>
        <p className="text-xs text-[#5F6368] dark:text-[#94A3B8] max-w-sm">
          Select an email from the list to read its contents and inspect cryptographic verification receipts.
        </p>
      </div>
    );
  }

  const getInitials = (name: string) => {
    const parts = name.split(' ');
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
    return name.slice(0, 2).toUpperCase();
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const handleDownloadAttachment = async (att: any) => {
    if (!att || savingAttachmentName) return;
    setSavingAttachmentName(att.name);
    try {
      const res = await api.saveAttachment({
        name: att.name,
        data: att.data,
        mediaType: att.mediaType,
      });
      if (res.success) {
        onShowProtectionNotice?.(res.message || `Attachment saved · ${att.name}`);
      } else {
        onShowProtectionNotice?.(res.message || `Failed to save ${att.name}`);
      }
    } catch (err: any) {
      onShowProtectionNotice?.(`Error saving attachment: ${err?.message || err}`);
    } finally {
      setSavingAttachmentName(null);
    }
  };

  const handleLinkClick = (url: string, e: React.MouseEvent) => {
    e.preventDefault();
    const { cleanUrl, strippedParams } = sanitizeExternalUrl(url);
    if (confirmExternalLinks) {
      setPendingLink({ originalUrl: url, cleanUrl, strippedParams });
    } else {
      window.open(cleanUrl, '_blank', 'noopener,noreferrer');
    }
  };

  const renderBodyWithLinks = (text: string) => {
    const urlRegex = /(https?:\/\/[^\s<>"{}|\\^`[\]]+)/gi;
    const parts = text.split(urlRegex);
    return parts.map((part, idx) => {
      if (/^https?:\/\//i.test(part)) {
        return (
          <a
            key={idx}
            href={part}
            onClick={(e) => handleLinkClick(part, e)}
            className="qumail-accent-text underline decoration-dotted underline-offset-2 hover:opacity-80 break-all cursor-pointer"
          >
            {part}
          </a>
        );
      }
      return <React.Fragment key={idx}>{part}</React.Fragment>;
    });
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-white dark:bg-[#161F33] overflow-y-auto">
      {/* Top Action Toolbar */}
      <div className="h-14 px-6 flex items-center justify-between border-b border-[#E0E3E7] dark:border-[#1F2C47] shrink-0 bg-white dark:bg-[#161F33] print:hidden">
        <div className="flex items-center space-x-2">
          <button
            onClick={onClose}
            title={t(language, 'back')}
            className={`${
              showIconLabels ? 'px-3 py-1.5 rounded-full flex items-center space-x-1.5' : 'p-2 rounded-full'
            } text-[#5F6368] dark:text-[#94A3B8] hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors mr-1`}
          >
            <ArrowLeft className="w-4 h-4" />
            {showIconLabels && <span className="text-xs font-semibold">{t(language, 'back')}</span>}
          </button>
          <button
            onClick={() => onReply(message)}
            className="flex items-center space-x-2 px-3.5 py-1.5 rounded-full border border-gray-300 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 text-xs font-semibold text-[#202124] dark:text-[#F1F5F9] transition-colors"
          >
            <Reply className="w-3.5 h-3.5" />
            <span>{t(language, 'reply')}</span>
          </button>
          {message.recipients && message.recipients.length > 1 && (
            <button
              onClick={() => onReply(message, true)}
              className="flex items-center space-x-2 px-3.5 py-1.5 rounded-full border border-gray-300 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 text-xs font-semibold text-[#202124] dark:text-[#F1F5F9] transition-colors"
              title={t(language, 'reply_all')}
            >
              <ReplyAll className="w-3.5 h-3.5" />
              <span>{t(language, 'reply_all')}</span>
            </button>
          )}
          <button
            onClick={() => onForward(message)}
            className="flex items-center space-x-2 px-3.5 py-1.5 rounded-full border border-gray-300 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 text-xs font-semibold text-[#202124] dark:text-[#F1F5F9] transition-colors"
          >
            <Forward className="w-3.5 h-3.5" />
            <span>{t(language, 'forward')}</span>
          </button>

          {/* On-Demand Offline Translation Action */}
          {enableOfflineTranslation && (isQuMail || allowStandardMailTranslation) && (
            <div className="flex items-center space-x-1.5 pl-1">
              {isTranslating ? (
                <div className="flex items-center space-x-1.5">
                  <div className="flex items-center space-x-1.5 px-3 py-1.5 rounded-full border border-indigo-200 dark:border-indigo-800/80 bg-indigo-50/70 dark:bg-indigo-950/40 text-xs font-semibold text-indigo-700 dark:text-indigo-300 shadow-xs">
                    <RefreshCw className="w-3.5 h-3.5 animate-spin text-indigo-600 dark:text-indigo-400" />
                    <span>{t(language, 'trans_translating_spin')}</span>
                  </div>
                  <button
                    type="button"
                    onClick={handleCancelTranslate}
                    className="flex items-center space-x-1 px-2.5 py-1.5 rounded-full border border-rose-300 dark:border-rose-800/80 bg-rose-50/80 dark:bg-rose-950/40 hover:bg-rose-100 dark:hover:bg-rose-900/60 text-xs font-semibold text-rose-700 dark:text-rose-300 transition-colors cursor-pointer shadow-xs"
                    title="Cancel translation in progress"
                  >
                    <X className="w-3.5 h-3.5" />
                    <span>{t(language, 'cancel') || 'Cancel'}</span>
                  </button>
                </div>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => handleTriggerTranslate()}
                    className="flex items-center space-x-1.5 px-3 py-1.5 rounded-full border border-indigo-200 dark:border-indigo-800/80 bg-indigo-50/70 dark:bg-indigo-950/40 hover:bg-indigo-100 dark:hover:bg-indigo-900/60 text-xs font-semibold text-indigo-700 dark:text-indigo-300 transition-colors cursor-pointer shadow-xs"
                    title={`${t(language, 'trans_reading_btn')} (NLLB-200 INT8)`}
                  >
                    <Languages className="w-3.5 h-3.5" />
                    <span>
                      {`${t(language, 'trans_reading_btn')} (${targetLang === 'hi' ? 'हिन्दी' : targetLang === 'mr' ? 'मराठी' : 'English'})`}
                    </span>
                  </button>

                  <div className="flex items-center bg-gray-100 dark:bg-gray-800 rounded-full p-0.5 border border-gray-200 dark:border-gray-700">
                    {(['hi', 'mr', 'en'] as const).map((l) => (
                      <button
                        key={l}
                        type="button"
                        onClick={() => handleTriggerTranslate(l)}
                        className={`px-1.5 py-0.5 rounded-full text-[10px] font-bold transition-all cursor-pointer ${
                          targetLang === l
                            ? 'qumail-accent-bg text-white shadow-xs'
                            : 'text-gray-500 hover:text-gray-900 dark:hover:text-white'
                        }`}
                      >
                        {l === 'hi' ? 'हि' : l === 'mr' ? 'मर' : 'EN'}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center space-x-2">
          {onToggleStar && (
            <button
              onClick={(e) => onToggleStar(message.id, e)}
              title={message.starred ? `${t(language, 'star')} (S)` : `${t(language, 'star')} (S)`}
              className={`${
                showIconLabels ? 'px-3 py-1.5 rounded-full flex items-center space-x-1.5' : 'p-1.5 rounded-full'
              } text-[#5F6368] dark:text-[#94A3B8] hover:bg-amber-50 dark:hover:bg-amber-950/30 hover:text-amber-500 transition-colors cursor-pointer`}
            >
              <UseAnimations
                animation={star}
                size={22}
                active={message.starred}
                strokeColor={message.starred ? '#f59e0b' : 'currentColor'}
                fillColor={message.starred ? '#f59e0b' : 'transparent'}
              />
              {showIconLabels && (
                <span className="text-xs font-semibold">
                  {message.starred ? t(language, 'starred') : t(language, 'star')}
                </span>
              )}
            </button>
          )}
          <button
            onClick={() => window.print()}
            title={t(language, 'print')}
            className={`${
              showIconLabels ? 'px-3 py-1.5 rounded-full flex items-center space-x-1.5' : 'p-2 rounded-full'
            } text-[#5F6368] dark:text-[#94A3B8] hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors`}
          >
            <Printer className="w-4 h-4" />
            {showIconLabels && <span className="text-xs font-semibold">{t(language, 'print')}</span>}
          </button>

          {/* Safe Trash Action with Tooltip & Block */}
          <button
            onClick={() => {
              if (!isQuMail) {
                onShowProtectionNotice?.(t(language, 'safe_deletion_guard'));
                return;
              }
              onDelete(message.id);
            }}
            disabled={!isQuMail}
            title={isQuMail ? t(language, 'delete') : t(language, 'safe_deletion_guard')}
            className={`${
              showIconLabels ? 'px-3 py-1.5 rounded-full flex items-center space-x-1.5' : 'p-2 rounded-full'
            } transition-colors ${
              isQuMail
                ? 'text-[#5F6368] dark:text-[#94A3B8] hover:bg-red-50 dark:hover:bg-red-950/40 hover:text-red-600'
                : 'text-gray-300 dark:text-gray-600 opacity-25 cursor-not-allowed hover:bg-transparent'
            }`}
          >
            <Trash2 className="w-4 h-4" />
            {showIconLabels && <span className="text-xs font-semibold">{t(language, 'delete')}</span>}
          </button>
        </div>
      </div>

      {/* Main Content Scroll Area */}
      <div id="qumail-printable-email" className="p-8 space-y-6 max-w-4xl mx-auto w-full">
        {/* Dedicated Clean Isolated Print Header */}
        <div className="hidden print:block border-b-2 border-gray-900 pb-4 mb-6 text-black print-border">
          <div className="flex items-center justify-between mb-2">
            <h1 className="text-xl font-bold font-sans text-black">{effectiveSubject}</h1>
            <span className="text-xs uppercase tracking-wider font-semibold border border-gray-800 px-2 py-0.5 rounded text-black">
              {isSecure ? (isWebLink ? 'AES-256-GCM Secure Link' : 'Quantum-Safe Sealed · ML-KEM-768 / ML-DSA-65') : 'Standard Mail (TLS)'}
            </span>
          </div>
          <div className="text-xs space-y-1 font-sans text-gray-800">
            <div><strong>From:</strong> {message.sender} &lt;{message.senderEmail}&gt;</div>
            <div><strong>To:</strong> {message.recipients.join(', ')}</div>
            <div><strong>Date:</strong> {message.date}</div>
            {showTranslated && translatedText && (
              <div className="mt-2 pt-1 border-t border-gray-400 text-[11px] italic text-gray-700">
                * Translated locally via QuMail Offline Neural Engine ({targetLang.toUpperCase()})
              </div>
            )}
          </div>
        </div>

        {/* Subject Heading */}
        <div className="flex flex-wrap items-center gap-2.5 print:hidden">
          <h1 className="text-2xl font-bold text-[#202124] dark:text-[#F1F5F9] leading-snug">
            {effectiveSubject}
          </h1>
          {isCloaked && (
            <span
              title="Subject line was hidden from mail servers for privacy; real subject was decrypted inside the secure message."
              className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold qumail-accent-soft qumail-accent-text"
            >
              <Shield className="w-3 h-3" />
              <span>Hidden Subject</span>
            </span>
          )}
        </div>

        {/* Collapsible Cryptographic Receipt & Verification Banner */}
        {message.indicator && (
          <div
            className={`p-4 rounded-2xl border transition-all print:hidden ${
              isSecure
                ? 'bg-emerald-50/70 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-800/60'
                : message.indicator.badgeLevel === 'CAUTION'
                ? 'bg-amber-50/70 dark:bg-amber-950/30 border-amber-200 dark:border-amber-800/60'
                : isStandardEmail
                ? 'bg-slate-50/80 dark:bg-slate-900/40 border-slate-200 dark:border-slate-800'
                : 'bg-red-50/70 dark:bg-red-950/30 border-red-200 dark:border-red-800/60'
            }`}
          >
            <div className="flex items-start space-x-3">
              <div
                className={`p-2 rounded-xl shrink-0 ${
                  isSecure
                    ? 'bg-emerald-100 dark:bg-emerald-900/60 text-emerald-700 dark:text-emerald-300'
                    : message.indicator.badgeLevel === 'CAUTION'
                    ? 'bg-amber-100 dark:bg-amber-900/60 text-amber-700 dark:text-amber-300'
                    : isStandardEmail
                    ? 'bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300'
                    : 'bg-red-100 dark:bg-red-900/60 text-red-700 dark:text-red-300'
                }`}
              >
                {isSecure ? (
                  isWebLink ? <Lock className="w-5 h-5 text-cyan-600" /> : <ShieldCheck className="w-5 h-5 text-emerald-600" />
                ) : message.indicator.badgeLevel === 'CAUTION' ? (
                  <AlertTriangle className="w-5 h-5" />
                ) : isStandardEmail ? (
                  <Shield className="w-5 h-5 text-slate-600 dark:text-slate-400" />
                ) : (
                  <ShieldAlert className="w-5 h-5" />
                )}
              </div>
              <div className="flex-1 space-y-1">
                <div className="flex items-center space-x-2">
                  <span className="font-bold text-sm text-[#202124] dark:text-[#F1F5F9]">
                    {isStandardEmail
                      ? allowStandardMailTranslation
                        ? 'Standard Email (Offline Translation Active)'
                        : 'Standard Provider Email'
                      : message.indicator.headline}
                  </span>
                  <span
                    className={`text-[10px] font-extrabold px-2 py-0.5 rounded-full uppercase tracking-wider ${
                      isSecure
                        ? isWebLink
                          ? 'bg-cyan-200 dark:bg-cyan-900 text-cyan-900 dark:text-cyan-100'
                          : 'bg-emerald-200 dark:bg-emerald-900 text-emerald-900 dark:text-emerald-100'
                        : message.indicator.badgeLevel === 'CAUTION'
                        ? 'bg-amber-200 dark:bg-amber-900 text-amber-900 dark:text-amber-100'
                        : isStandardEmail
                        ? allowStandardMailTranslation
                          ? 'bg-indigo-100 dark:bg-indigo-950/80 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800'
                          : 'bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300'
                        : 'bg-red-200 dark:bg-red-900 text-red-900 dark:text-red-100'
                    }`}
                  >
                    {isWebLink ? 'PRIVATE LINK' : isStandardEmail ? (allowStandardMailTranslation ? 'LOCAL TRANSLATE' : 'STANDARD') : message.indicator.badgeLevel}
                  </span>
                </div>
                <p className="text-xs text-[#5F6368] dark:text-[#94A3B8] leading-relaxed">
                  {isStandardEmail
                    ? allowStandardMailTranslation
                      ? 'Standard unencrypted inbound message. Offline translation and content viewing are enabled locally on your device.'
                      : 'This message was delivered through your regular email provider without QuMail end-to-end sealing. To keep your inbox isolated, QuMail only opens quantum-safe messages.'
                    : message.indicator.description}
                </p>

                {isFetchingStandard && (
                  <div className="flex items-center space-x-2 pt-1.5 text-xs text-indigo-600 dark:text-indigo-400 font-medium">
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Loading original email content...</span>
                  </div>
                )}

                {isStandardEmail && !allowStandardMailTranslation && (
                  <div className="pt-2">
                    <a
                      href="https://mail.google.com"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs shadow-sm transition-colors cursor-pointer"
                    >
                      <span>Open in Gmail ↗</span>
                    </a>
                  </div>
                )}

                {/* Collapsible Toggle */}
                <button
                  type="button"
                  onClick={() => setIsReceiptOpen(!isReceiptOpen)}
                  className="pt-1.5 flex items-center space-x-1 text-xs font-semibold text-[#0B57D0] dark:text-[#818CF8] hover:underline cursor-pointer select-none"
                >
                  <span>{isReceiptOpen ? 'Hide Security Details' : 'View Security Details'}</span>
                  {isReceiptOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                </button>

                {/* Detailed Cryptographic Receipts Panel */}
                {isReceiptOpen && (
                  <div className="mt-3 pt-3 border-t border-black/10 dark:border-white/10 grid grid-cols-1 md:grid-cols-2 gap-2.5 text-[11px] font-mono select-text">
                    {isWebLink ? (
                      <>
                        <div className="p-2 rounded-lg bg-black/5 dark:bg-black/30">
                          <span className="text-gray-500 dark:text-gray-400 block font-sans font-bold">Cipher Protocol:</span>
                          <span className="text-cyan-600 dark:text-cyan-300 font-bold">AES-256-GCM (Zero-Knowledge)</span>
                        </div>
                        <div className="p-2 rounded-lg bg-black/5 dark:bg-black/30">
                          <span className="text-gray-500 dark:text-gray-400 block font-sans font-bold">Recipient Verification:</span>
                          <span className="text-gray-800 dark:text-gray-200">Ephemeral 6-Digit Email OTP</span>
                        </div>
                        <div className="p-2 rounded-lg bg-black/5 dark:bg-black/30">
                          <span className="text-gray-500 dark:text-gray-400 block font-sans font-bold">Key Confidentiality:</span>
                          <span className="text-gray-800 dark:text-gray-200">Client-Side URL #fragment</span>
                        </div>
                        <div className="p-2 rounded-lg bg-black/5 dark:bg-black/30">
                          <span className="text-gray-500 dark:text-gray-400 block font-sans font-bold">Burn Policy:</span>
                          <span className="text-gray-800 dark:text-gray-200">Atomic Single-Use Purge</span>
                        </div>
                      </>
                    ) : isSecure ? (
                      <>
                        <div className="p-2 rounded-lg bg-black/5 dark:bg-black/30">
                          <span className="text-gray-500 dark:text-gray-400 block font-sans font-bold">Key Encapsulation (KEM):</span>
                          <span className="text-emerald-600 dark:text-emerald-300 font-bold">NIST FIPS 203 (ML-KEM-768)</span>
                        </div>
                        <div className="p-2 rounded-lg bg-black/5 dark:bg-black/30">
                          <span className="text-gray-500 dark:text-gray-400 block font-sans font-bold">Digital Signature (DSA):</span>
                          <span className="text-emerald-600 dark:text-emerald-300 font-bold">NIST FIPS 204 (ML-DSA-65)</span>
                        </div>
                        <div className="p-2 rounded-lg bg-black/5 dark:bg-black/30">
                          <span className="text-gray-500 dark:text-gray-400 block font-sans font-bold">Payload Encryption:</span>
                          <span className="text-gray-800 dark:text-gray-200">AES-256-GCM Authenticated Envelope</span>
                        </div>
                        <div className="p-2 rounded-lg bg-black/5 dark:bg-black/30">
                          <span className="text-gray-500 dark:text-gray-400 block font-sans font-bold">Vault Authority:</span>
                          <span className="text-gray-800 dark:text-gray-200">Windows DPAPI Protected SQLite</span>
                        </div>
                      </>
                    ) : (
                      <>
                        <div className="p-2 rounded-lg bg-black/5 dark:bg-black/30">
                          <span className="text-gray-500 dark:text-gray-400 block font-sans font-bold">Transport Layer:</span>
                          <span className="text-gray-700 dark:text-gray-300">Standard IMAP/TLS</span>
                        </div>
                        <div className="p-2 rounded-lg bg-black/5 dark:bg-black/30">
                          <span className="text-gray-500 dark:text-gray-400 block font-sans font-bold">Mailbox Isolation:</span>
                          <span className="text-gray-700 dark:text-gray-300">QuMail Enclave Active</span>
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Sender & Recipient Metadata Card */}
        <div className="flex items-start justify-between p-4 rounded-2xl bg-[#F6F8FC] dark:bg-[#111726] border border-[#E0E3E7] dark:border-[#1F2C47] print:hidden">
          <div className="flex items-center space-x-3.5">
            {userEmail && message.senderEmail && userEmail.toLowerCase() === message.senderEmail.toLowerCase() && userAvatarUrl ? (
              <img
                src={userAvatarUrl}
                alt={message.sender}
                referrerPolicy="no-referrer"
                crossOrigin="anonymous"
                className="w-10 h-10 rounded-full object-cover shadow border border-indigo-200 dark:border-indigo-800"
              />
            ) : (
              <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-indigo-500 to-blue-600 text-white flex items-center justify-center font-bold text-sm shadow">
                {getInitials(message.sender)}
              </div>
            )}
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-bold text-sm text-[#202124] dark:text-[#F1F5F9]">
                  {message.sender}
                </span>
                <span className="text-xs text-[#5F6368] dark:text-[#94A3B8]">
                  &lt;{message.senderEmail}&gt;
                </span>
              </div>
              <div className="text-xs text-[#5F6368] dark:text-[#94A3B8] mt-0.5">
                to {message.recipients.join(', ')}
              </div>
            </div>
          </div>

          <span className="text-xs text-[#5F6368] dark:text-[#94A3B8] font-medium">
            {message.date}
          </span>
        </div>

        {/* Remote Image / Tracking Beacon Protection Banner */}
        {remoteImageUrls.length > 0 && blockRemoteImages && !allowRemoteImages && (
          <div className="px-4 py-2.5 rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 flex items-center justify-between text-xs print:hidden">
            <div className="flex items-center space-x-2 text-amber-800 dark:text-amber-300">
              <ImageOff className="w-4 h-4 shrink-0" />
              <span>
                {t(language, 'remote_images_blocked')}
              </span>
            </div>
            <button
              type="button"
              onClick={() => setAllowRemoteImages(true)}
              className="px-3 py-1 rounded-lg bg-amber-600 hover:bg-amber-700 text-white font-semibold transition-colors cursor-pointer shrink-0 ml-3"
            >
              {t(language, 'load_remote_images')}
            </button>
          </div>
        )}

        {/* On-Device Local Translation Banner */}
        {enableOfflineTranslation && translatedText && (
          <div className="mb-4 p-3.5 rounded-2xl border border-indigo-200 dark:border-indigo-800/60 bg-gradient-to-r from-indigo-50/80 via-white to-blue-50/60 dark:from-indigo-950/30 dark:via-[#111726] dark:to-blue-950/20 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-xs print:hidden">
            <div className="flex items-center space-x-2.5">
              <div className="p-1.5 rounded-xl bg-indigo-100 dark:bg-indigo-900/60 text-indigo-600 dark:text-indigo-400">
                <Languages className="w-4 h-4" />
              </div>
              <div>
                <span className="font-bold text-xs text-indigo-900 dark:text-indigo-200 block">
                  {t(language, 'trans_banner_badge')}
                </span>
                <span className="text-[10px] text-indigo-700/80 dark:text-indigo-300/70 font-mono">
                  {showTranslated ? 'Showing Translation · ' : 'Showing Original · '}
                  Target: {targetLang === 'hi' ? 'हिन्दी (hin_Deva)' : targetLang === 'mr' ? 'मराठी (mar_Deva)' : 'English (eng_Latn)'}
                </span>
              </div>
            </div>

            <div className="flex items-center space-x-2">
              <button
                type="button"
                onClick={() => setShowTranslated(!showTranslated)}
                className="px-3 py-1.5 rounded-xl bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 transition-colors cursor-pointer shadow-xs"
              >
                {showTranslated ? t(language, 'trans_show_original') : t(language, 'trans_show_translated')}
              </button>
              <button
                type="button"
                onClick={handleDeleteTranslation}
                className="p-1.5 rounded-xl border border-gray-300 dark:border-gray-700 hover:bg-rose-50 dark:hover:bg-rose-950/30 text-rose-600 dark:text-rose-400 text-xs font-medium transition-colors cursor-pointer"
                title={t(language, 'trans_purge_this')}
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}

        {/* Plain Text Message Body with Collapsible Quoted Reply Chain */}
        <div
          style={{
            fontFamily: FONT_FAMILY_STYLE[fontFamily],
            fontSize: FONT_SIZE_STYLE[fontSize],
          }}
          className="text-[#202124] dark:text-[#F1F5F9] whitespace-pre-wrap leading-relaxed font-normal py-2 select-text"
        >
          {renderBodyWithLinks(mainText || effectiveBodyText)}

          {quotedText && (
            <div className="mt-4 pt-2">
              <div className="print:hidden">
                <button
                  type="button"
                  onClick={() => setShowQuotedText(!showQuotedText)}
                  className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-md bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-xs text-[#5F6368] dark:text-[#94A3B8] transition-colors cursor-pointer select-none"
                  title={showQuotedText ? 'Hide quoted text' : 'Show quoted text'}
                >
                  <MoreHorizontal className="w-4 h-4" />
                  <span>{showQuotedText ? 'Hide quoted text' : 'Show quoted text'}</span>
                </button>

                {showQuotedText && (
                  <div className="mt-3 pl-3 border-l-2 border-indigo-400 dark:border-indigo-600 text-[#5F6368] dark:text-[#94A3B8] text-xs font-mono">
                    {renderBodyWithLinks(quotedText)}
                  </div>
                )}
              </div>

              {/* In print, print quoted text cleanly if toggled open */}
              {showQuotedText && (
                <div className="hidden print:block mt-4 pl-3 border-l-2 border-gray-600 text-gray-800 text-xs font-mono">
                  {quotedText}
                </div>
              )}
            </div>
          )}
        </div>

        {/* External Link Guard Modal */}
        {pendingLink && (
          <div
            className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4"
            onClick={() => setPendingLink(null)}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              className="w-full max-w-md rounded-2xl bg-white dark:bg-[#161F33] border border-[#E0E3E7] dark:border-[#1F2C47] shadow-2xl p-5 space-y-4"
            >
              <div className="flex items-center space-x-2.5 text-amber-600 dark:text-amber-400">
                <ExternalLink className="w-5 h-5 shrink-0" />
                <h3 className="text-sm font-bold text-[#202124] dark:text-[#F1F5F9]">
                  External Link Guard
                </h3>
              </div>
              <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">
                Verify the destination URL before opening it in your browser.
              </p>
              <div className="p-3 rounded-xl bg-gray-50 dark:bg-black/30 border border-gray-200 dark:border-gray-700 font-mono text-xs text-[#202124] dark:text-[#F1F5F9] break-all select-all">
                {pendingLink.cleanUrl}
              </div>
              {pendingLink.strippedParams.length > 0 && (
                <div className="text-[11px] text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 rounded-xl px-3 py-2">
                  Stripped {pendingLink.strippedParams.length} tracking{' '}
                  {pendingLink.strippedParams.length === 1 ? 'parameter' : 'parameters'}:{' '}
                  <span className="font-mono font-semibold">
                    {pendingLink.strippedParams.join(', ')}
                  </span>
                </div>
              )}
              <div className="flex items-center justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setPendingLink(null)}
                  className="px-4 py-2 rounded-xl border border-gray-300 dark:border-gray-700 text-xs font-semibold text-[#202124] dark:text-[#F1F5F9] hover:bg-gray-100 dark:hover:bg-white/[0.04] cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => {
                    const target = pendingLink.cleanUrl;
                    setPendingLink(null);
                    window.open(target, '_blank', 'noopener,noreferrer');
                  }}
                  className="px-4 py-2 rounded-xl qumail-accent-bg text-white text-xs font-bold shadow-sm cursor-pointer"
                >
                  Open Link
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Loaded External Images (only when allowed by user or Settings) */}
        {remoteImageUrls.length > 0 && (!blockRemoteImages || allowRemoteImages) && (
          <div className="pt-2 space-y-2">
            {remoteImageUrls.map((url, idx) => (
              <img
                key={idx}
                src={url}
                alt={`External attachment ${idx + 1}`}
                className="max-w-full max-h-96 rounded-xl border border-[#E0E3E7] dark:border-[#1F2C47]"
              />
            ))}
          </div>
        )}

        {/* Attachments Section */}
        {message.attachments && message.attachments.length > 0 && (
          <div className="pt-4 border-t border-[#E0E3E7] dark:border-[#1F2C47] space-y-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-[#5F6368] dark:text-[#94A3B8]">
              Attachments ({message.attachments.length})
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {message.attachments.map((att, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between p-3 rounded-xl border border-[#E0E3E7] dark:border-[#1F2C47] bg-[#F6F8FC] dark:bg-[#111726] hover:bg-gray-100 dark:hover:bg-gray-800/80 transition-colors"
                >
                  <div className="flex items-center space-x-3 truncate">
                    <FileText className="w-5 h-5 text-[#0B57D0] shrink-0" />
                    <div className="truncate">
                      <p className="text-xs font-semibold text-[#202124] dark:text-[#F1F5F9] truncate">
                        {att.name}
                      </p>
                      <p className="text-[10px] text-[#5F6368] dark:text-[#94A3B8]">
                        {formatSize(att.size)}
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => handleDownloadAttachment(att)}
                    disabled={savingAttachmentName === att.name}
                    title="Save attachment to disk"
                    className="p-1.5 rounded-lg text-[#5F6368] dark:text-[#94A3B8] hover:bg-white dark:hover:bg-gray-700 transition-colors shrink-0 disabled:opacity-50 cursor-pointer"
                  >
                    {savingAttachmentName === att.name ? (
                      <div className="w-4 h-4 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
                    ) : (
                      <Download className="w-4 h-4" />
                    )}
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Bottom Quick Reply Action Bar */}
        <div className="pt-6 border-t border-[#E0E3E7] dark:border-[#1F2C47] flex items-center space-x-3">
          <button
            onClick={() => onReply(message)}
            className="flex items-center space-x-2 px-4 py-2 rounded-xl border border-gray-300 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 text-xs font-semibold text-[#202124] dark:text-[#F1F5F9] transition-colors cursor-pointer"
          >
            <Reply className="w-3.5 h-3.5" />
            <span>{t(language, 'reply')}</span>
          </button>
          {message.recipients && message.recipients.length > 1 && (
            <button
              onClick={() => onReply(message, true)}
              className="flex items-center space-x-2 px-4 py-2 rounded-xl border border-gray-300 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 text-xs font-semibold text-[#202124] dark:text-[#F1F5F9] transition-colors cursor-pointer"
            >
              <ReplyAll className="w-3.5 h-3.5" />
              <span>{t(language, 'reply_all')}</span>
            </button>
          )}
          <button
            onClick={() => onForward(message)}
            className="flex items-center space-x-2 px-4 py-2 rounded-xl border border-gray-300 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 text-xs font-semibold text-[#202124] dark:text-[#F1F5F9] transition-colors cursor-pointer"
          >
            <Forward className="w-3.5 h-3.5" />
            <span>{t(language, 'forward')}</span>
          </button>
        </div>

        {/* Missing Model Prompt Dialog */}
        <AnimatePresence>
          {modelPromptOpen && (
            <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs select-none">
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="w-full max-w-md bg-white dark:bg-[#111726] border border-gray-200 dark:border-gray-800 rounded-2xl shadow-2xl p-6 space-y-4"
              >
                <div className="flex items-center space-x-3 text-indigo-600 dark:text-indigo-400">
                  <div className="p-2 rounded-xl bg-indigo-50 dark:bg-indigo-950/60">
                    <Languages className="w-5 h-5" />
                  </div>
                  <div>
                    <h4 className="font-bold text-sm text-[#202124] dark:text-[#F1F5F9]">
                      {t(language, 'trans_setup_prompt_title')}
                    </h4>
                    <p className="text-[11px] text-[#5F6368] dark:text-[#94A3B8]">
                      NLLB-200-distilled-600M INT8 (~610 MB)
                    </p>
                  </div>
                </div>

                <p className="text-xs text-[#5F6368] dark:text-[#94A3B8] leading-relaxed">
                  {t(language, 'trans_setup_prompt_desc')}
                </p>

                <div className="flex items-center justify-end space-x-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setModelPromptOpen(false)}
                    className="px-3.5 py-1.5 rounded-xl border border-gray-300 dark:border-gray-700 text-xs font-semibold text-[#202124] dark:text-white hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors cursor-pointer"
                  >
                    {t(language, 'close')}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setModelPromptOpen(false);
                      onOpenSettings?.('offline_translation');
                    }}
                    className="px-4 py-1.5 rounded-xl qumail-accent-bg text-white text-xs font-bold hover:opacity-95 transition-opacity cursor-pointer shadow-sm"
                  >
                    {t(language, 'trans_goto_settings_btn')}
                  </button>
                </div>
              </motion.div>
            </div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
};
