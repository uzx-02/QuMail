import React, { useState } from 'react';
import { X, Minus, Maximize2, Minimize2, Paperclip, Shield, Lock, Link, Send, Trash2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { EmailMessage, Attachment } from '../types';

interface ComposeModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSend: (msg: Partial<EmailMessage>) => Promise<void>;
  initialTo?: string;
  initialSubject?: string;
  initialBody?: string;
}

export const ComposeModal: React.FC<ComposeModalProps> = ({
  isOpen,
  onClose,
  onSend,
  initialTo = '',
  initialSubject = '',
  initialBody = '',
}) => {
  const [to, setTo] = useState(initialTo);
  const [subject, setSubject] = useState(initialSubject);
  const [body, setBody] = useState(initialBody);
  const [securityMode, setSecurityMode] = useState<'pq' | 'weblink' | 'standard'>('pq');
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [isMinimized, setIsMinimized] = useState(false);
  const [isMaximized, setIsMaximized] = useState(false);
  const [isSending, setIsSending] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!to.trim()) {
      alert('Please enter at least one recipient.');
      return;
    }
    setIsSending(true);
    try {
      await onSend({
        recipients: to.split(',').map((s) => s.trim()),
        subject: subject.trim() || '(No Subject)',
        body: body.trim(),
        attachments,
      });
      setTo('');
      setSubject('');
      setBody('');
      setAttachments([]);
      onClose();
    } finally {
      setIsSending(false);
    }
  };

  const handleSimulateAttach = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.onchange = (e: any) => {
      const file = e.target.files?.[0];
      if (file) {
        setAttachments((prev) => [
          ...prev,
          { name: file.name, size: file.size, mediaType: file.type },
        ]);
      }
    };
    input.click();
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 50, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 50, scale: 0.95 }}
        transition={{ type: 'spring', damping: 25, stiffness: 350 }}
        className={`fixed z-50 bg-white dark:bg-[#161F33] rounded-2xl shadow-2xl border border-[#E0E3E7] dark:border-[#2A3B5F] flex flex-col overflow-hidden ${
          isMaximized
            ? 'inset-8 w-auto h-auto'
            : isMinimized
            ? 'bottom-0 right-12 w-80 h-12'
            : 'bottom-0 right-12 w-[600px] h-[580px]'
        }`}
      >
        {/* Modal Header */}
        <div className="h-12 px-4 bg-[#F2F6FC] dark:bg-[#111726] flex items-center justify-between border-b border-[#E0E3E7] dark:border-[#1F2C47] shrink-0 select-none">
          <span className="font-bold text-sm text-[#202124] dark:text-[#F1F5F9] flex items-center space-x-2">
            <span>New Message</span>
            <span className="text-[10px] uppercase font-extrabold px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/60 text-[#0B57D0] dark:text-blue-300">
              {securityMode === 'pq' ? 'ML-KEM-768' : securityMode === 'weblink' ? 'Zero-Knowledge Link' : 'Standard'}
            </span>
          </span>

          <div className="flex items-center space-x-1 text-[#5F6368] dark:text-[#94A3B8]">
            <button
              onClick={() => setIsMinimized(!isMinimized)}
              className="p-1.5 hover:bg-slate-200 dark:hover:bg-slate-800 rounded"
              title="Minimize"
            >
              <Minus className="w-4 h-4" />
            </button>
            <button
              onClick={() => setIsMaximized(!isMaximized)}
              className="p-1.5 hover:bg-slate-200 dark:hover:bg-slate-800 rounded"
              title={isMaximized ? 'Restore' : 'Maximize'}
            >
              {isMaximized ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
            </button>
            <button
              onClick={onClose}
              className="p-1.5 hover:bg-slate-200 dark:hover:bg-slate-800 rounded"
              title="Close"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Modal Body */}
        {!isMinimized && (
          <form onSubmit={handleSubmit} className="flex-1 flex flex-col overflow-hidden">
            {/* Security Mode Selector Bar */}
            <div className="px-4 py-2.5 bg-blue-50/60 dark:bg-[#0A0E17]/60 border-b border-[#E0E3E7] dark:border-[#1F2C47] flex items-center justify-between shrink-0">
              <div className="flex items-center space-x-2">
                <span className="text-xs font-semibold text-[#5F6368] dark:text-[#94A3B8]">
                  Protection:
                </span>
                <select
                  value={securityMode}
                  onChange={(e: any) => setSecurityMode(e.target.value)}
                  className="text-xs font-bold rounded-lg border-gray-300 dark:border-gray-700 bg-white dark:bg-[#161F33] text-[#0B57D0] dark:text-[#818CF8] px-2.5 py-1 outline-none focus:ring-1 focus:ring-[#0B57D0] cursor-pointer"
                >
                  <option value="pq">Maximum Security (Post-Quantum ML-KEM-768)</option>
                  <option value="weblink">Secure Web Link (For Non-PQC Recipient)</option>
                  <option value="standard">Standard Email (Unencrypted)</option>
                </select>
              </div>

              <div className="flex items-center space-x-1 text-[11px] text-emerald-700 dark:text-emerald-400 font-semibold">
                <Shield className="w-3.5 h-3.5" />
                <span>Zero Plaintext Leak</span>
              </div>
            </div>

            {/* Recipients Field */}
            <div className="flex items-center px-4 py-2 border-b border-[#F2F2F2] dark:border-[#1F2C47]/60">
              <span className="w-12 text-xs font-semibold text-[#5F6368] dark:text-[#94A3B8]">To</span>
              <input
                type="text"
                placeholder="Recipients (comma separated)"
                value={to}
                onChange={(e) => setTo(e.target.value)}
                className="flex-1 bg-transparent border-none outline-none text-sm text-[#202124] dark:text-white"
                required
              />
            </div>

            {/* Subject Field */}
            <div className="flex items-center px-4 py-2 border-b border-[#F2F2F2] dark:border-[#1F2C47]/60">
              <span className="w-12 text-xs font-semibold text-[#5F6368] dark:text-[#94A3B8]">Subject</span>
              <input
                type="text"
                placeholder="Subject"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                className="flex-1 bg-transparent border-none outline-none text-sm text-[#202124] dark:text-white"
              />
            </div>

            {/* Message Body Editor */}
            <div className="flex-1 p-4 overflow-y-auto">
              <textarea
                placeholder="Write your secure message here…"
                value={body}
                onChange={(e) => setBody(e.target.value)}
                className="w-full h-full bg-transparent border-none outline-none resize-none text-sm text-[#202124] dark:text-[#F1F5F9] leading-relaxed font-sans placeholder-[#5F6368]"
              />
            </div>

            {/* Attachment Chips */}
            {attachments.length > 0 && (
              <div className="px-4 py-2 flex flex-wrap gap-2 border-t border-gray-100 dark:border-gray-800">
                {attachments.map((att, i) => (
                  <span
                    key={i}
                    className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-lg bg-gray-100 dark:bg-gray-800 text-xs font-medium text-gray-700 dark:text-gray-300"
                  >
                    <Paperclip className="w-3 h-3 text-gray-500" />
                    <span>{att.name}</span>
                    <button
                      type="button"
                      onClick={() => setAttachments((p) => p.filter((_, idx) => idx !== i))}
                      className="hover:text-red-500"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}

            {/* Bottom Actions Bar */}
            <div className="h-16 px-4 bg-white dark:bg-[#161F33] border-t border-[#E0E3E7] dark:border-[#1F2C47] flex items-center justify-between shrink-0">
              <div className="flex items-center space-x-3">
                <button
                  type="submit"
                  disabled={isSending}
                  className="flex items-center space-x-2 px-6 py-2.5 rounded-full bg-[#0B57D0] hover:bg-[#0842A0] text-white font-bold text-sm shadow-md hover:shadow-lg transition-all outline-none disabled:opacity-50"
                >
                  <Send className="w-4 h-4" />
                  <span>{isSending ? 'Sealing...' : 'Send'}</span>
                </button>

                <button
                  type="button"
                  onClick={handleSimulateAttach}
                  title="Attach file"
                  className="p-2 text-[#5F6368] dark:text-[#94A3B8] hover:bg-[#F2F6FC] dark:hover:bg-[#1E2740] rounded-full transition-colors"
                >
                  <Paperclip className="w-5 h-5" />
                </button>
              </div>

              <button
                type="button"
                onClick={() => {
                  setTo('');
                  setSubject('');
                  setBody('');
                  setAttachments([]);
                  onClose();
                }}
                title="Discard draft"
                className="p-2 text-[#5F6368] dark:text-[#94A3B8] hover:bg-red-50 dark:hover:bg-red-950/40 hover:text-red-600 rounded-full transition-colors"
              >
                <Trash2 className="w-5 h-5" />
              </button>
            </div>
          </form>
        )}
      </motion.div>
    </AnimatePresence>
  );
};
