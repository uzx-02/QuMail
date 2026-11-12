import React, { useState } from 'react';
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
} from 'lucide-react';
import { EmailMessage } from '../types';

interface ReadingPaneProps {
  message: EmailMessage | null;
  onReply: (msg: EmailMessage) => void;
  onForward: (msg: EmailMessage) => void;
  onDelete: (id: string) => void;
  onToggleStar?: (id: string, e: React.MouseEvent) => void;
  onClose: () => void;
  onShowProtectionNotice?: (msg: string) => void;
}

export const ReadingPane: React.FC<ReadingPaneProps> = ({
  message,
  onReply,
  onForward,
  onDelete,
  onToggleStar,
  onClose,
  onShowProtectionNotice,
}) => {
  const [isReceiptOpen, setIsReceiptOpen] = useState(false);

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

  const isQuMail = Boolean(
    message.isQuMail !== undefined
      ? message.isQuMail
      : message.securityTier === 'pq_sealed' ||
        message.securityTier === 'weblink' ||
        message.securityMode === 'pq' ||
        message.securityMode === 'weblink' ||
        message.indicator?.badgeLevel === 'SECURE' ||
        message.subject?.startsWith('[QuMail Secure Link]')
  );

  const isSecure = message.indicator?.badgeLevel === 'SECURE';
  const isWebLink = message.securityTier === 'weblink' || message.securityMode === 'weblink' || message.subject?.startsWith('[QuMail Secure Link]');

  return (
    <div className="flex-1 flex flex-col h-full bg-white dark:bg-[#161F33] overflow-y-auto">
      {/* Top Action Toolbar */}
      <div className="h-14 px-6 flex items-center justify-between border-b border-[#E0E3E7] dark:border-[#1F2C47] shrink-0 bg-white dark:bg-[#161F33]">
        <div className="flex items-center space-x-2">
          <button
            onClick={onClose}
            title="Back to message list"
            className="p-2 rounded-full text-[#5F6368] dark:text-[#94A3B8] hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors mr-1"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <button
            onClick={() => onReply(message)}
            className="flex items-center space-x-2 px-3.5 py-1.5 rounded-full border border-gray-300 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 text-xs font-semibold text-[#202124] dark:text-[#F1F5F9] transition-colors"
          >
            <Reply className="w-3.5 h-3.5" />
            <span>Reply</span>
          </button>
          <button
            onClick={() => onForward(message)}
            className="flex items-center space-x-2 px-3.5 py-1.5 rounded-full border border-gray-300 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 text-xs font-semibold text-[#202124] dark:text-[#F1F5F9] transition-colors"
          >
            <Forward className="w-3.5 h-3.5" />
            <span>Forward</span>
          </button>
        </div>

        <div className="flex items-center space-x-2">
          {onToggleStar && (
            <button
              onClick={(e) => onToggleStar(message.id, e)}
              title={message.starred ? 'Remove star (S)' : 'Star message (S)'}
              className="p-2 rounded-full text-[#5F6368] dark:text-[#94A3B8] hover:bg-amber-50 dark:hover:bg-amber-950/30 hover:text-amber-500 transition-colors cursor-pointer"
            >
              <Star
                className={`w-4 h-4 ${
                  message.starred ? 'fill-amber-400 text-amber-400' : ''
                }`}
              />
            </button>
          )}
          <button
            onClick={() => window.print()}
            title="Print message"
            className="p-2 rounded-full text-[#5F6368] dark:text-[#94A3B8] hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            <Printer className="w-4 h-4" />
          </button>

          {/* Safe Trash Action with Tooltip & Block */}
          <button
            onClick={() => {
              if (!isQuMail) {
                onShowProtectionNotice?.('Safe Deletion Guard: Standard legacy emails cannot be deleted by QuMail.');
                return;
              }
              onDelete(message.id);
            }}
            disabled={!isQuMail}
            title={isQuMail ? 'Delete QuMail message' : 'Deletion Protected: Standard email cannot be deleted by QuMail'}
            className={`p-2 rounded-full transition-colors ${
              isQuMail
                ? 'text-[#5F6368] dark:text-[#94A3B8] hover:bg-red-50 dark:hover:bg-red-950/40 hover:text-red-600'
                : 'text-gray-300 dark:text-gray-600 opacity-25 cursor-not-allowed hover:bg-transparent'
            }`}
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Main Content Scroll Area */}
      <div className="p-8 space-y-6 max-w-4xl mx-auto w-full">
        {/* Subject Heading */}
        <h1 className="text-2xl font-bold text-[#202124] dark:text-[#F1F5F9] leading-snug">
          {message.subject || '(No Subject)'}
        </h1>

        {/* Collapsible Cryptographic Receipt & Verification Banner */}
        {message.indicator && (
          <div
            className={`p-4 rounded-2xl border transition-all ${
              isSecure
                ? 'bg-emerald-50/70 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-800/60'
                : message.indicator.badgeLevel === 'CAUTION'
                ? 'bg-amber-50/70 dark:bg-amber-950/30 border-amber-200 dark:border-amber-800/60'
                : message.indicator.badgeLevel === 'NEUTRAL'
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
                    : message.indicator.badgeLevel === 'NEUTRAL'
                    ? 'bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300'
                    : 'bg-red-100 dark:bg-red-900/60 text-red-700 dark:text-red-300'
                }`}
              >
                {isSecure ? (
                  isWebLink ? <Lock className="w-5 h-5 text-cyan-600" /> : <ShieldCheck className="w-5 h-5 text-emerald-600" />
                ) : message.indicator.badgeLevel === 'CAUTION' ? (
                  <AlertTriangle className="w-5 h-5" />
                ) : message.indicator.badgeLevel === 'NEUTRAL' ? (
                  <Shield className="w-5 h-5 text-slate-600 dark:text-slate-400" />
                ) : (
                  <ShieldAlert className="w-5 h-5" />
                )}
              </div>
              <div className="flex-1 space-y-1">
                <div className="flex items-center space-x-2">
                  <span className="font-bold text-sm text-[#202124] dark:text-[#F1F5F9]">
                    {message.indicator.headline}
                  </span>
                  <span
                    className={`text-[10px] font-extrabold px-2 py-0.5 rounded-full uppercase tracking-wider ${
                      isSecure
                        ? isWebLink
                          ? 'bg-cyan-200 dark:bg-cyan-900 text-cyan-900 dark:text-cyan-100'
                          : 'bg-emerald-200 dark:bg-emerald-900 text-emerald-900 dark:text-emerald-100'
                        : message.indicator.badgeLevel === 'CAUTION'
                        ? 'bg-amber-200 dark:bg-amber-900 text-amber-900 dark:text-amber-100'
                        : message.indicator.badgeLevel === 'NEUTRAL'
                        ? 'bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300'
                        : 'bg-red-200 dark:bg-red-900 text-red-900 dark:text-red-100'
                    }`}
                  >
                    {isWebLink ? 'WEBLINK' : message.indicator.badgeLevel === 'NEUTRAL' ? 'SHIELDED' : message.indicator.badgeLevel}
                  </span>
                </div>
                <p className="text-xs text-[#5F6368] dark:text-[#94A3B8] leading-relaxed">
                  {message.indicator.description}
                </p>

                {/* Collapsible Toggle */}
                <button
                  type="button"
                  onClick={() => setIsReceiptOpen(!isReceiptOpen)}
                  className="pt-1.5 flex items-center space-x-1 text-xs font-semibold text-[#0B57D0] dark:text-[#818CF8] hover:underline cursor-pointer select-none"
                >
                  <span>{isReceiptOpen ? 'Hide Cryptographic Receipt' : 'View Cryptographic Receipt'}</span>
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
                          <span className="text-gray-500 dark:text-gray-400 block font-sans font-bold">Privacy Enclave:</span>
                          <span className="text-gray-700 dark:text-gray-300">Content Isolated Locally</span>
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
        <div className="flex items-start justify-between p-4 rounded-2xl bg-[#F6F8FC] dark:bg-[#111726] border border-[#E0E3E7] dark:border-[#1F2C47]">
          <div className="flex items-center space-x-3.5">
            <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-indigo-500 to-blue-600 text-white flex items-center justify-center font-bold text-sm shadow">
              {getInitials(message.sender)}
            </div>
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

        {/* Plain Text Message Body */}
        <div className="text-sm text-[#202124] dark:text-[#F1F5F9] whitespace-pre-wrap leading-relaxed font-sans font-normal py-2 select-text">
          {message.body}
        </div>

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
                    onClick={() => {
                      if (att.data) {
                        const link = document.createElement('a');
                        link.href = `data:${att.mediaType || 'application/octet-stream'};base64,${att.data}`;
                        link.download = att.name;
                        link.click();
                      }
                    }}
                    title="Download attachment"
                    className="p-1.5 rounded-lg text-[#5F6368] dark:text-[#94A3B8] hover:bg-white dark:hover:bg-gray-700 transition-colors shrink-0"
                  >
                    <Download className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
