import React from 'react';
import { ArrowLeft, Reply, Forward, Trash2, Printer, ShieldCheck, AlertTriangle, ShieldAlert, Download, FileText, CheckCircle2 } from 'lucide-react';
import { EmailMessage } from '../types';

interface ReadingPaneProps {
  message: EmailMessage | null;
  onReply: (msg: EmailMessage) => void;
  onForward: (msg: EmailMessage) => void;
  onDelete: (id: string) => void;
  onClose: () => void;
}

export const ReadingPane: React.FC<ReadingPaneProps> = ({
  message,
  onReply,
  onForward,
  onDelete,
  onClose,
}) => {
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

  const isSecure = message.indicator?.badgeLevel === 'SECURE';

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
          <button
            onClick={() => window.print()}
            title="Print message"
            className="p-2 rounded-full text-[#5F6368] dark:text-[#94A3B8] hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            <Printer className="w-4 h-4" />
          </button>
          <button
            onClick={() => onDelete(message.id)}
            title="Delete message"
            className="p-2 rounded-full text-[#5F6368] dark:text-[#94A3B8] hover:bg-red-50 dark:hover:bg-red-950/40 hover:text-red-600 transition-colors"
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

        {/* Post-Quantum Reassurance Trust Ribbon */}
        {message.indicator && (
          <div
            className={`p-4 rounded-2xl border transition-all ${
              isSecure
                ? 'bg-emerald-50/70 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-800/60'
                : message.indicator.badgeLevel === 'CAUTION'
                ? 'bg-amber-50/70 dark:bg-amber-950/30 border-amber-200 dark:border-amber-800/60'
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
                    : 'bg-red-100 dark:bg-red-900/60 text-red-700 dark:text-red-300'
                }`}
              >
                {isSecure ? (
                  <ShieldCheck className="w-5 h-5" />
                ) : message.indicator.badgeLevel === 'CAUTION' ? (
                  <AlertTriangle className="w-5 h-5" />
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
                        ? 'bg-emerald-200 dark:bg-emerald-900 text-emerald-900 dark:text-emerald-100'
                        : 'bg-amber-200 dark:bg-amber-900 text-amber-900 dark:text-amber-100'
                    }`}
                  >
                    {message.indicator.badgeLevel}
                  </span>
                </div>
                <p className="text-xs text-[#5F6368] dark:text-[#94A3B8] leading-relaxed">
                  {message.indicator.description}
                </p>
                <div className="flex items-center space-x-1.5 text-[11px] text-[#0B57D0] dark:text-[#818CF8] font-medium pt-1">
                  <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                  <span>Advice: {message.indicator.actionAdvice}</span>
                </div>
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
          <div className="pt-6 border-t border-[#E0E3E7] dark:border-[#1F2C47] space-y-3">
            <h4 className="text-xs font-bold text-[#5F6368] dark:text-[#94A3B8] uppercase tracking-wider">
              Attachments ({message.attachments.length})
            </h4>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {message.attachments.map((att, idx) => (
                <div
                  key={idx}
                  className="flex items-center justify-between p-3.5 rounded-xl border border-[#E0E3E7] dark:border-[#1F2C47] bg-[#F6F8FC] dark:bg-[#111726] hover:border-[#0B57D0]/60 transition-colors group"
                >
                  <div className="flex items-center space-x-3 truncate mr-2">
                    <div className="w-8 h-8 rounded-lg bg-blue-100 dark:bg-blue-900/40 text-[#0B57D0] flex items-center justify-center shrink-0">
                      <FileText className="w-4 h-4" />
                    </div>
                    <div className="truncate">
                      <p className="text-xs font-bold text-[#202124] dark:text-[#F1F5F9] truncate">
                        {att.name}
                      </p>
                      <p className="text-[11px] text-[#5F6368] dark:text-[#94A3B8]">
                        {formatSize(att.size)}
                      </p>
                    </div>
                  </div>

                  <button
                    onClick={() => alert(`Saving ${att.name}... In native desktop mode, files export to your Downloads folder.`)}
                    title="Download attachment"
                    className="p-2 rounded-lg text-[#5F6368] dark:text-[#94A3B8] hover:bg-white dark:hover:bg-slate-800 hover:text-[#0B57D0] dark:hover:text-blue-400 transition-colors shrink-0"
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
