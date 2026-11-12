import React, { useState, useEffect, useRef } from 'react';
import { X, Minus, Maximize2, Minimize2, Paperclip, Shield, Send, Trash2, GripHorizontal } from 'lucide-react';
import { motion, AnimatePresence, useDragControls } from 'framer-motion';
import { EmailMessage, Attachment } from '../types';

interface ComposeModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSend: (msg: Partial<EmailMessage> & { draftId?: string }) => Promise<boolean | void>;
  onSaveDraft?: (draft: Partial<EmailMessage>) => Promise<string | void>;
  onDiscardDraft?: (draftId: string) => void;
  initialDraftId?: string;
  initialTo?: string;
  initialSubject?: string;
  initialBody?: string;
  initialSecurityMode?: 'pq' | 'weblink' | 'standard';
  defaultRequireEmailOtp?: boolean;
  defaultBurnAfterRead?: boolean;
  defaultExpiryHours?: 1 | 24 | 168;
}

export const ComposeModal: React.FC<ComposeModalProps> = ({
  isOpen,
  onClose,
  onSend,
  onSaveDraft,
  onDiscardDraft,
  initialDraftId,
  initialTo = '',
  initialSubject = '',
  initialBody = '',
  initialSecurityMode = 'pq',
  defaultRequireEmailOtp = true,
  defaultBurnAfterRead = false,
  defaultExpiryHours = 24,
}) => {
  const [draftId, setDraftId] = useState<string | undefined>(initialDraftId);
  const [to, setTo] = useState(initialTo);
  const [subject, setSubject] = useState(initialSubject);
  const [body, setBody] = useState(initialBody);
  const [securityMode, setSecurityMode] = useState<'pq' | 'weblink' | 'standard'>(initialSecurityMode);
  const [requireEmailOtp, setRequireEmailOtp] = useState(defaultRequireEmailOtp);
  const [burnAfterRead, setBurnAfterRead] = useState(defaultBurnAfterRead);
  const [expiresInHours, setExpiresInHours] = useState<1 | 24 | 168>(defaultExpiryHours);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [isMinimized, setIsMinimized] = useState(false);
  const [isMaximized, setIsMaximized] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [draftStatus, setDraftStatus] = useState<'idle' | 'saving' | 'saved'>('idle');

  const dragControls = useDragControls();
  const autoSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hasSentRef = useRef(false);

  // Sync fields whenever modal opens or a different draft/reply is loaded
  useEffect(() => {
    if (isOpen) {
      hasSentRef.current = false;
      setDraftId(initialDraftId);
      setTo(initialTo);
      setSubject(initialSubject);
      setBody(initialBody);
      setSecurityMode(initialSecurityMode);
      setRequireEmailOtp(defaultRequireEmailOtp);
      setBurnAfterRead(defaultBurnAfterRead);
      setExpiresInHours(defaultExpiryHours);
      setAttachments([]);
      setIsMinimized(false);
      setDraftStatus('idle');
    } else if (autoSaveTimerRef.current) {
      clearTimeout(autoSaveTimerRef.current);
      autoSaveTimerRef.current = null;
    }
  }, [isOpen, initialDraftId, initialTo, initialSubject, initialBody, initialSecurityMode, defaultRequireEmailOtp, defaultBurnAfterRead, defaultExpiryHours]);

  // Silent 1.5s debounced auto-save (skips completely blank drafts and cancelled if Send clicked)
  useEffect(() => {
    if (!isOpen || !onSaveDraft || hasSentRef.current) return;

    const hasContent =
      to.trim().length > 0 || subject.trim().length > 0 || body.trim().length > 0;
    if (!hasContent) return;

    if (autoSaveTimerRef.current) {
      clearTimeout(autoSaveTimerRef.current);
    }

    autoSaveTimerRef.current = setTimeout(async () => {
      if (hasSentRef.current) return;
      setDraftStatus('saving');
      try {
        const cleanRecipients = to.split(',').map((s) => s.trim()).filter(Boolean);
        const savedId = await onSaveDraft({
          id: draftId,
          recipients: cleanRecipients,
          subject: subject.trim(),
          body,
          attachments,
          securityMode,
          requireEmailOtp,
        });
        if (savedId && !draftId) {
          setDraftId(savedId);
        }
        setDraftStatus('saved');
      } catch {
        setDraftStatus('idle');
      }
    }, 1500);

    return () => {
      if (autoSaveTimerRef.current) {
        clearTimeout(autoSaveTimerRef.current);
      }
    };
  }, [isOpen, to, subject, body, securityMode, requireEmailOtp, attachments, draftId, onSaveDraft]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanRecipients = to.split(',').map((s) => s.trim()).filter(Boolean);
    if (cleanRecipients.length === 0) {
      alert('Please enter at least one recipient email address.');
      return;
    }
    // Cancel any pending auto-save immediately so it cannot recreate a draft after Send
    if (autoSaveTimerRef.current) {
      clearTimeout(autoSaveTimerRef.current);
      autoSaveTimerRef.current = null;
    }
    hasSentRef.current = true;
    setIsSending(true);
    try {
      const ok = await onSend({
        draftId,
        recipients: cleanRecipients,
        subject: subject.trim() || '(No Subject)',
        body: body.trim(),
        attachments,
        securityMode,
        requireEmailOtp,
        burnAfterRead,
        expiresInHours,
      });
      if (ok !== false) {
        setDraftId(undefined);
        setTo('');
        setSubject('');
        setBody('');
        setAttachments([]);
        onClose();
      } else {
        hasSentRef.current = false;
      }
    } catch {
      hasSentRef.current = false;
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
        drag={!isMaximized}
        dragListener={false}
        dragControls={dragControls}
        dragMomentum={false}
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
        {/* Modal Header (Drag Handle) */}
        <div
          onPointerDown={(e) => {
            if (!isMaximized) dragControls.start(e);
          }}
          className={`h-12 px-4 bg-[#F2F6FC] dark:bg-[#111726] flex items-center justify-between border-b border-[#E0E3E7] dark:border-[#1F2C47] shrink-0 select-none ${
            !isMaximized ? 'cursor-grab active:cursor-grabbing' : ''
          }`}
        >
          <span className="font-bold text-sm text-[#202124] dark:text-[#F1F5F9] flex items-center space-x-2">
            {!isMaximized && <GripHorizontal className="w-3.5 h-3.5 text-gray-400" />}
            <span>New Message</span>
            <span className="text-[10px] uppercase font-extrabold px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/60 text-[#0B57D0] dark:text-blue-300">
              {securityMode === 'pq' ? 'ML-KEM-768' : securityMode === 'weblink' ? 'Zero-Knowledge Link' : 'Standard'}
            </span>
            {draftStatus === 'saving' && (
              <span className="text-[10px] font-medium text-gray-400">Saving…</span>
            )}
            {draftStatus === 'saved' && (
              <span className="text-[10px] font-medium text-emerald-600 dark:text-emerald-400">Saved</span>
            )}
          </span>

          <div
            className="flex items-center space-x-1 text-[#5F6368] dark:text-[#94A3B8]"
            onPointerDown={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              onClick={() => setIsMinimized(!isMinimized)}
              className="p-1.5 hover:bg-slate-200 dark:hover:bg-slate-800 rounded cursor-pointer"
              title={isMinimized ? 'Expand' : 'Minimize to dock'}
            >
              <Minus className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={() => {
                setIsMinimized(false);
                setIsMaximized(!isMaximized);
              }}
              className="p-1.5 hover:bg-slate-200 dark:hover:bg-slate-800 rounded cursor-pointer"
              title={isMaximized ? 'Restore' : 'Maximize'}
            >
              {isMaximized ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 hover:bg-slate-200 dark:hover:bg-slate-800 rounded cursor-pointer"
              title="Close (auto-saved to Drafts)"
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

            {/* WebLink Security Controls */}
            {securityMode === 'weblink' && (
              <div className="px-4 py-2 bg-emerald-50/70 dark:bg-emerald-950/30 border-b border-[#E0E3E7] dark:border-[#1F2C47] flex flex-wrap items-center justify-between gap-2 text-xs">
                <span className="text-emerald-800 dark:text-emerald-300 font-medium flex items-center space-x-1.5">
                  <Shield className="w-3.5 h-3.5" />
                  <span>WebLink Policy:</span>
                </span>
                <div className="flex items-center space-x-3">
                  <select
                    value={expiresInHours}
                    onChange={(e) => setExpiresInHours(Number(e.target.value) as 1 | 24 | 168)}
                    className="text-[11px] font-semibold rounded border border-emerald-300 dark:border-emerald-800 bg-white dark:bg-[#161F33] text-emerald-900 dark:text-emerald-200 px-2 py-0.5 outline-none cursor-pointer"
                    title="Link expiry"
                  >
                    <option value={1}>Expires: 1h</option>
                    <option value={24}>Expires: 24h</option>
                    <option value={168}>Expires: 7d</option>
                  </select>
                  <label className="flex items-center space-x-1 cursor-pointer text-gray-700 dark:text-gray-300 font-semibold select-none">
                    <input
                      type="checkbox"
                      checked={burnAfterRead}
                      onChange={(e) => setBurnAfterRead(e.target.checked)}
                      className="rounded text-[#0B57D0] focus:ring-[#0B57D0]"
                    />
                    <span>Burn</span>
                  </label>
                  <label className="flex items-center space-x-1 cursor-pointer text-gray-700 dark:text-gray-300 font-semibold select-none">
                    <input
                      type="checkbox"
                      checked={requireEmailOtp}
                      onChange={(e) => setRequireEmailOtp(e.target.checked)}
                      className="rounded text-[#0B57D0] focus:ring-[#0B57D0]"
                    />
                    <span>OTP</span>
                  </label>
                </div>
              </div>
            )}

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
                  if (autoSaveTimerRef.current) {
                    clearTimeout(autoSaveTimerRef.current);
                    autoSaveTimerRef.current = null;
                  }
                  hasSentRef.current = true;
                  if (draftId && onDiscardDraft) {
                    onDiscardDraft(draftId);
                  }
                  setDraftId(undefined);
                  setTo('');
                  setSubject('');
                  setBody('');
                  setAttachments([]);
                  onClose();
                }}
                title="Discard draft"
                className="p-2 text-[#5F6368] dark:text-[#94A3B8] hover:bg-red-50 dark:hover:bg-red-950/40 hover:text-red-600 rounded-full transition-colors cursor-pointer"
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
