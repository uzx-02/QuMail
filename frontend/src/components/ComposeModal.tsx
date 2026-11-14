import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  X,
  Minus,
  Maximize2,
  Minimize2,
  Paperclip,
  Shield,
  ShieldCheck,
  Send,
  Trash2,
  GripHorizontal,
  ExternalLink,
  ChevronDown,
  Check,
  Globe,
  Link2,
  User,
  Clock,
  Flame,
  KeyRound,
} from 'lucide-react';
import UseAnimations from 'react-useanimations';
import send from 'react-useanimations/lib/send';
import trash2 from 'react-useanimations/lib/trash2';
import lock from 'react-useanimations/lib/lock';
import { motion, AnimatePresence } from 'framer-motion';
import { EmailMessage, Attachment, FontFamilyOption, FontSizeOption, LanguageOption } from '../types';
import { FONT_FAMILY_STYLE, FONT_SIZE_STYLE } from '../lib/appearance';
import { CLOAKED_TRANSPORT_SUBJECT, embedCloakedSubject } from '../lib/privacy';
import { t } from '../lib/i18n';

interface ComposeModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSend: (msg: Partial<EmailMessage> & { draftId?: string }) => Promise<boolean | void>;
  onSaveDraft?: (draft: Partial<EmailMessage>) => Promise<string | void>;
  onDiscardDraft?: (draftId: string) => void;
  initialDraftId?: string;
  initialThreadId?: string;
  initialInReplyTo?: string;
  initialReferences?: string;
  initialTo?: string;
  initialSubject?: string;
  initialBody?: string;
  initialSecurityMode?: 'pq' | 'weblink' | 'standard';
  defaultRequireEmailOtp?: boolean;
  defaultBurnAfterRead?: boolean;
  defaultExpiryHours?: 1 | 24 | 168 | 720;
  fontFamily?: FontFamilyOption;
  fontSize?: FontSizeOption;
  confirmBeforeSend?: boolean;
  cloakSubjectHeaders?: boolean;
  knownContacts?: Array<{ email: string; name?: string }>;
  language?: LanguageOption;
}

export const ComposeModal: React.FC<ComposeModalProps> = ({
  isOpen,
  onClose,
  onSend,
  onSaveDraft,
  onDiscardDraft,
  initialDraftId,
  initialThreadId,
  initialInReplyTo,
  initialReferences,
  initialTo = '',
  initialSubject = '',
  initialBody = '',
  initialSecurityMode = 'pq',
  defaultRequireEmailOtp = true,
  defaultBurnAfterRead = false,
  defaultExpiryHours = 168,
  fontFamily = 'sans',
  fontSize = 'medium',
  confirmBeforeSend = false,
  cloakSubjectHeaders = false,
  knownContacts = [],
  language,
}) => {
  const [draftId, setDraftId] = useState<string | undefined>(initialDraftId);
  const [recipientsList, setRecipientsList] = useState<string[]>(() =>
    initialTo ? initialTo.split(/[,;]+/).map((s) => s.trim()).filter(Boolean) : []
  );
  const [recipientInput, setRecipientInput] = useState('');
  const toInputRef = useRef<HTMLInputElement>(null);

  const cleanRecipients = useMemo(() => {
    const list = [...recipientsList];
    const pending = recipientInput.trim().replace(/^[,;\s]+|[,;\s]+$/g, '');
    if (pending && !list.includes(pending)) {
      list.push(pending);
    }
    return list;
  }, [recipientsList, recipientInput]);

  const to = useMemo(() => cleanRecipients.join(', '), [cleanRecipients]);

  useEffect(() => {
    if (initialTo !== undefined) {
      const parsed = initialTo ? initialTo.split(/[,;]+/).map((s) => s.trim()).filter(Boolean) : [];
      setRecipientsList(parsed);
      setRecipientInput('');
    }
  }, [initialTo, isOpen]);

  const [subject, setSubject] = useState(initialSubject);
  const [body, setBody] = useState(initialBody);
  const [securityMode, setSecurityMode] = useState<'pq' | 'weblink' | 'standard'>(initialSecurityMode);
  const [requireEmailOtp, setRequireEmailOtp] = useState(defaultRequireEmailOtp);
  const [burnAfterRead, setBurnAfterRead] = useState(defaultBurnAfterRead);
  const [expiresInHours, setExpiresInHours] = useState<1 | 24 | 168 | 720>(defaultExpiryHours);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [isMinimized, setIsMinimized] = useState(false);
  const [isMaximized, setIsMaximized] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [showSendConfirm, setShowSendConfirm] = useState(false);
  const [unregisteredWarning, setUnregisteredWarning] = useState<string[] | null>(null);
  const [isAttaching, setIsAttaching] = useState(false);
  const [attachWarning, setAttachWarning] = useState<string | null>(null);
  const [draftStatus, setDraftStatus] = useState<'idle' | 'saving' | 'saved'>('idle');

  // Custom themed Security Mode selector
  const [isSecurityDropdownOpen, setIsSecurityDropdownOpen] = useState(false);
  const securityDropdownRef = useRef<HTMLDivElement>(null);

  // Recipient email autocomplete state
  const [toAutocompleteOpen, setToAutocompleteOpen] = useState(false);
  const [selectedSuggestionIdx, setSelectedSuggestionIdx] = useState(0);
  const toContainerRef = useRef<HTMLDivElement>(null);

  const currentRecipientSegment = useMemo(() => {
    return recipientInput.trim().toLowerCase();
  }, [recipientInput]);

  const recipientSuggestions = useMemo(() => {
    if (!currentRecipientSegment || currentRecipientSegment.length < 1) return [];
    const existingRecipients = new Set(
      recipientsList.map((p) => p.trim().toLowerCase()).filter(Boolean)
    );
    return (knownContacts || [])
      .filter((c) => {
        const em = c.email.toLowerCase();
        const nm = (c.name || '').toLowerCase();
        return (
          (em.includes(currentRecipientSegment) || nm.includes(currentRecipientSegment)) &&
          !existingRecipients.has(em)
        );
      })
      .slice(0, 5);
  }, [currentRecipientSegment, knownContacts, recipientsList]);

  const commitRecipientInput = (text: string) => {
    const candidates = text.split(/[,;\s]+/).map((s) => s.trim()).filter(Boolean);
    if (candidates.length === 0) return;
    setRecipientsList((prev) => {
      const next = [...prev];
      for (const c of candidates) {
        if (!next.includes(c)) next.push(c);
      }
      return next;
    });
    setRecipientInput('');
    setToAutocompleteOpen(false);
    setSelectedSuggestionIdx(0);
  };

  const removeRecipient = (index: number) => {
    setRecipientsList((prev) => prev.filter((_, i) => i !== index));
  };

  const applyRecipientSuggestion = (email: string) => {
    const trimmed = email.trim();
    if (trimmed) {
      setRecipientsList((prev) => (prev.includes(trimmed) ? prev : [...prev, trimmed]));
    }
    setRecipientInput('');
    setToAutocompleteOpen(false);
    setSelectedSuggestionIdx(0);
    toInputRef.current?.focus();
  };

  // Close dropdowns on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        securityDropdownRef.current &&
        !securityDropdownRef.current.contains(e.target as Node)
      ) {
        setIsSecurityDropdownOpen(false);
      }
      if (
        toContainerRef.current &&
        !toContainerRef.current.contains(e.target as Node)
      ) {
        setToAutocompleteOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const MIN_WIDTH = 380;
  const MIN_HEIGHT = 360;

  const getDefaultRect = () => {
    const w = Math.min(600, window.innerWidth - 32);
    const h = Math.min(580, window.innerHeight - 32);
    return {
      left: Math.max(16, window.innerWidth - w - 48),
      top: Math.max(16, window.innerHeight - h),
      width: w,
      height: h,
    };
  };

  const [windowRect, setWindowRect] = useState(getDefaultRect);
  const interactionRef = useRef<{
    type: 'drag' | 'resize';
    dir?: string;
    startX: number;
    startY: number;
    startRect: { left: number; top: number; width: number; height: number };
  } | null>(null);
  const autoSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hasSentRef = useRef(false);

  // Clamp floating window inside viewport if the browser/app window is resized
  useEffect(() => {
    const handleResize = () => {
      setWindowRect((prev) => {
        const w = Math.min(prev.width, window.innerWidth - 16);
        const h = Math.min(prev.height, window.innerHeight - 16);
        return {
          width: Math.max(MIN_WIDTH, w),
          height: Math.max(MIN_HEIGHT, h),
          left: Math.max(8, Math.min(prev.left, window.innerWidth - w - 8)),
          top: Math.max(8, Math.min(prev.top, window.innerHeight - h - 8)),
        };
      });
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const startHeaderDrag = (e: React.PointerEvent<HTMLDivElement>) => {
    if (isMaximized || isMinimized || e.button !== 0) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    interactionRef.current = {
      type: 'drag',
      startX: e.clientX,
      startY: e.clientY,
      startRect: { ...windowRect },
    };
  };

  const startResize = (dir: string) => (e: React.PointerEvent<HTMLDivElement>) => {
    if (isMaximized || isMinimized || e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.setPointerCapture(e.pointerId);
    interactionRef.current = {
      type: 'resize',
      dir,
      startX: e.clientX,
      startY: e.clientY,
      startRect: { ...windowRect },
    };
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const active = interactionRef.current;
    if (!active) return;

    const dx = e.clientX - active.startX;
    const dy = e.clientY - active.startY;
    const s = active.startRect;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    if (active.type === 'drag') {
      const nextLeft = Math.max(8, Math.min(s.left + dx, vw - s.width - 8));
      const nextTop = Math.max(8, Math.min(s.top + dy, vh - (isMinimized ? 48 : s.height) - 8));
      setWindowRect((prev) => ({ ...prev, left: nextLeft, top: nextTop }));
      return;
    }

    const dir = active.dir || '';
    let { left, top, width, height } = s;

    if (dir.includes('e')) {
      width = Math.max(MIN_WIDTH, Math.min(s.width + dx, vw - s.left - 8));
    }
    if (dir.includes('s')) {
      height = Math.max(MIN_HEIGHT, Math.min(s.height + dy, vh - s.top - 8));
    }
    if (dir.includes('w')) {
      const maxLeft = s.left + s.width - MIN_WIDTH;
      const clampedLeft = Math.max(8, Math.min(s.left + dx, maxLeft));
      width = s.width + (s.left - clampedLeft);
      left = clampedLeft;
    }
    if (dir.includes('n')) {
      const maxTop = s.top + s.height - MIN_HEIGHT;
      const clampedTop = Math.max(8, Math.min(s.top + dy, maxTop));
      height = s.height + (s.top - clampedTop);
      top = clampedTop;
    }

    setWindowRect({ left, top, width, height });
  };

  const endPointerInteraction = (e: React.PointerEvent<HTMLDivElement>) => {
    if (interactionRef.current) {
      interactionRef.current = null;
      try {
        if (e.currentTarget.hasPointerCapture(e.pointerId)) {
          e.currentTarget.releasePointerCapture(e.pointerId);
        }
      } catch {}
    }
  };

  // Sync fields whenever modal opens or a different draft/reply is loaded
  useEffect(() => {
    if (isOpen) {
      hasSentRef.current = false;
      setDraftId(initialDraftId);
      const parsedTo = initialTo ? initialTo.split(/[,;]+/).map((s) => s.trim()).filter(Boolean) : [];
      setRecipientsList(parsedTo);
      setRecipientInput('');
      setSubject(initialSubject);
      setBody(initialBody);
      setSecurityMode(initialSecurityMode);
      setRequireEmailOtp(defaultRequireEmailOtp);
      setBurnAfterRead(defaultBurnAfterRead);
      setExpiresInHours(defaultExpiryHours);
      setAttachments([]);
      setIsMinimized(false);
      setShowSendConfirm(false);
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
          threadId: initialThreadId,
          inReplyTo: initialInReplyTo,
          references: initialReferences,
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

  const dispatchSend = async (overrideMode?: 'pq' | 'weblink' | 'standard') => {
    const cleanRecipients = to.split(',').map((s) => s.trim()).filter(Boolean);
    if (cleanRecipients.length === 0) {
      alert('Please enter at least one recipient email address.');
      return;
    }
    const modeToUse = overrideMode || securityMode;

    // Cancel any pending auto-save immediately so it cannot recreate a draft after Send
    if (autoSaveTimerRef.current) {
      clearTimeout(autoSaveTimerRef.current);
      autoSaveTimerRef.current = null;
    }
    hasSentRef.current = true;
    setIsSending(true);
    setShowSendConfirm(false);
    setUnregisteredWarning(null);

    const realSubject = subject.trim() || '(No Subject)';
    const shouldCloak = Boolean(cloakSubjectHeaders && modeToUse !== 'standard');
    // For WebLink mode: embed subject into plaintext body so the recipient portal can display it.
    // For ML-KEM mode: pass realSubject as subject + cloakSubjectHeaders: true; backend MIME layer
    // stores realSubject in the encrypted inner container and sets outer Subject: Encrypted message.
    const finalSubject = modeToUse === 'weblink' && shouldCloak ? CLOAKED_TRANSPORT_SUBJECT : realSubject;
    const finalBody = modeToUse === 'weblink' && shouldCloak
      ? embedCloakedSubject(realSubject, body.trim())
      : body.trim();

    try {
      const res: any = await onSend({
        draftId,
        recipients: cleanRecipients,
        subject: finalSubject,
        body: finalBody,
        attachments,
        securityMode: modeToUse,
        requireEmailOtp,
        burnAfterRead,
        expiresInHours,
        cloakSubjectHeaders: shouldCloak,
        threadId: initialThreadId,
        inReplyTo: initialInReplyTo,
        references: initialReferences,
      });

      if (res && typeof res === 'object' && res.code === 'UNREGISTERED_RECIPIENTS') {
        hasSentRef.current = false;
        setUnregisteredWarning(res.unregistered || cleanRecipients);
        return;
      }

      if (res !== false) {
        setDraftId(undefined);
        setRecipientsList([]);
        setRecipientInput('');
        setSubject('');
        setBody('');
        setAttachments([]);
        setUnregisteredWarning(null);
        setAttachWarning(null);
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanRecipients = to.split(',').map((s) => s.trim()).filter(Boolean);
    if (cleanRecipients.length === 0) {
      alert('Please enter at least one recipient email address.');
      return;
    }
    if (confirmBeforeSend && !showSendConfirm) {
      setShowSendConfirm(true);
      return;
    }
    await dispatchSend();
  };

  const handleSimulateAttach = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.multiple = true;
    input.onchange = async (e: any) => {
      const files: File[] = Array.from(e.target.files || []);
      if (files.length === 0) return;

      setIsAttaching(true);
      setAttachWarning(null);

      try {
        const newAttachments: Attachment[] = [];
        let totalSize = attachments.reduce((sum, a) => sum + (a.size || 0), 0);

        for (const file of files) {
          if (file.size > 30 * 1024 * 1024) {
            alert(`"${file.name}" exceeds the 30 MB maximum attachment limit.`);
            continue;
          }
          totalSize += file.size;

          const base64Data = await new Promise<string>((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result as string);
            reader.onerror = reject;
            reader.readAsDataURL(file);
          });

          newAttachments.push({
            name: file.name,
            size: file.size,
            mediaType: file.type || 'application/octet-stream',
            data: base64Data,
          });
        }

        if (totalSize > 20 * 1024 * 1024) {
          setAttachWarning(
            `Total attachment size is ${Math.round(totalSize / (1024 * 1024))} MB. With MIME base64 overhead (~33%), this approaches standard provider limits (~25 MB).`
          );
        }

        setAttachments((prev) => [...prev, ...newAttachments]);
      } catch (err: any) {
        alert(`Failed to attach file: ${err?.message || err}`);
      } finally {
        setIsAttaching(false);
      }
    };
    input.click();
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 24, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 24, scale: 0.97 }}
        transition={{ duration: 0.16 }}
        style={
          isMinimized
            ? { bottom: 0, right: 48, width: 320, height: 48 }
            : isMaximized
            ? { top: 24, left: 24, right: 24, bottom: 24, width: 'auto', height: 'auto' }
            : {
                top: windowRect.top,
                left: windowRect.left,
                width: windowRect.width,
                height: windowRect.height,
              }
        }
        className={`fixed z-50 bg-white dark:bg-[#161F33] shadow-2xl border border-[#E0E3E7] dark:border-[#2A3B5F] flex flex-col overflow-hidden ${
          isMinimized ? 'rounded-t-xl rounded-b-none' : 'rounded-2xl'
        }`}
      >
        {/* 8-Way Edge & Corner Resize Handles (when floating & expanded) */}
        {!isMaximized && !isMinimized && (
          <>
            <div
              onPointerDown={startResize('n')}
              onPointerMove={handlePointerMove}
              onPointerUp={endPointerInteraction}
              onPointerCancel={endPointerInteraction}
              className="absolute top-0 left-3 right-3 h-1.5 cursor-ns-resize z-20"
            />
            <div
              onPointerDown={startResize('s')}
              onPointerMove={handlePointerMove}
              onPointerUp={endPointerInteraction}
              onPointerCancel={endPointerInteraction}
              className="absolute bottom-0 left-3 right-3 h-1.5 cursor-ns-resize z-20"
            />
            <div
              onPointerDown={startResize('w')}
              onPointerMove={handlePointerMove}
              onPointerUp={endPointerInteraction}
              onPointerCancel={endPointerInteraction}
              className="absolute top-3 bottom-3 left-0 w-1.5 cursor-ew-resize z-20"
            />
            <div
              onPointerDown={startResize('e')}
              onPointerMove={handlePointerMove}
              onPointerUp={endPointerInteraction}
              onPointerCancel={endPointerInteraction}
              className="absolute top-3 bottom-3 right-0 w-1.5 cursor-ew-resize z-20"
            />
            <div
              onPointerDown={startResize('nw')}
              onPointerMove={handlePointerMove}
              onPointerUp={endPointerInteraction}
              onPointerCancel={endPointerInteraction}
              className="absolute top-0 left-0 w-3 h-3 cursor-nwse-resize z-30"
            />
            <div
              onPointerDown={startResize('ne')}
              onPointerMove={handlePointerMove}
              onPointerUp={endPointerInteraction}
              onPointerCancel={endPointerInteraction}
              className="absolute top-0 right-0 w-3 h-3 cursor-nesw-resize z-30"
            />
            <div
              onPointerDown={startResize('sw')}
              onPointerMove={handlePointerMove}
              onPointerUp={endPointerInteraction}
              onPointerCancel={endPointerInteraction}
              className="absolute bottom-0 left-0 w-3 h-3 cursor-nesw-resize z-30"
            />
            <div
              onPointerDown={startResize('se')}
              onPointerMove={handlePointerMove}
              onPointerUp={endPointerInteraction}
              onPointerCancel={endPointerInteraction}
              className="absolute bottom-0 right-0 w-3.5 h-3.5 cursor-nwse-resize z-30"
            />
          </>
        )}

        {/* Modal Header (Drag Handle + Double-Click Maximize/Restore) */}
        <div
          onPointerDown={startHeaderDrag}
          onPointerMove={handlePointerMove}
          onPointerUp={endPointerInteraction}
          onPointerCancel={endPointerInteraction}
          onDoubleClick={() => {
            setIsMinimized(false);
            setIsMaximized((prev) => !prev);
          }}
          className={`h-12 px-4 bg-[#F2F6FC] dark:bg-[#111726] flex items-center justify-between border-b border-[#E0E3E7] dark:border-[#1F2C47] shrink-0 select-none ${
            !isMaximized ? 'cursor-grab active:cursor-grabbing' : 'cursor-pointer'
          }`}
        >
          <span className="font-bold text-sm text-[#202124] dark:text-[#F1F5F9] flex items-center space-x-2 min-w-0">
            {!isMaximized && <GripHorizontal className="w-3.5 h-3.5 text-gray-400 shrink-0" />}
            <span className="truncate">{t(language, 'new_message')}</span>
            {!isMinimized && (
              <span className="text-[10px] uppercase font-extrabold px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/60 text-[#0B57D0] dark:text-blue-300 shrink-0">
                {securityMode === 'pq' ? 'Quantum-Safe' : securityMode === 'weblink' ? 'Secure Link' : 'Standard'}
              </span>
            )}
            {draftStatus === 'saving' && (
              <span className="text-[10px] font-medium text-gray-400 shrink-0">Saving…</span>
            )}
            {draftStatus === 'saved' && (
              <span className="text-[10px] font-medium text-emerald-600 dark:text-emerald-400 shrink-0">Saved</span>
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
                <div className="relative" ref={securityDropdownRef}>
                  <button
                    type="button"
                    onClick={() => setIsSecurityDropdownOpen(!isSecurityDropdownOpen)}
                    className="inline-flex items-center space-x-2 px-3 py-1.5 rounded-xl border border-blue-200/80 dark:border-slate-700 bg-white dark:bg-[#161F33] text-xs font-bold text-[#0B57D0] dark:text-sky-300 shadow-xs hover:border-blue-400 dark:hover:border-slate-600 transition-all cursor-pointer"
                  >
                    {securityMode === 'pq' && <ShieldCheck className="w-3.5 h-3.5 text-emerald-500 shrink-0" />}
                    {securityMode === 'weblink' && <Link2 className="w-3.5 h-3.5 text-cyan-500 shrink-0" />}
                    {securityMode === 'standard' && <Globe className="w-3.5 h-3.5 text-slate-400 shrink-0" />}
                    <span>
                      {securityMode === 'pq' && t(language, 'mode_pq')}
                      {securityMode === 'weblink' && t(language, 'mode_weblink')}
                      {securityMode === 'standard' && t(language, 'mode_standard')}
                    </span>
                    <ChevronDown
                      className={`w-3.5 h-3.5 text-slate-400 transition-transform duration-200 ${
                        isSecurityDropdownOpen ? 'rotate-180' : ''
                      }`}
                    />
                  </button>

                  {isSecurityDropdownOpen && (
                    <div className="absolute top-full left-0 mt-1.5 w-84 rounded-2xl bg-white/98 dark:bg-[#161F33]/98 border border-slate-200 dark:border-slate-700 shadow-2xl backdrop-blur-xl p-1.5 z-[100] animate-in fade-in zoom-in-95 duration-150">
                      <button
                        type="button"
                        onClick={() => {
                          setSecurityMode('pq');
                          setIsSecurityDropdownOpen(false);
                        }}
                        className={`w-full text-left p-2.5 rounded-xl flex items-start space-x-2.5 transition-all cursor-pointer ${
                          securityMode === 'pq'
                            ? 'bg-blue-50/90 dark:bg-blue-950/50 text-[#0B57D0] dark:text-sky-300'
                            : 'hover:bg-slate-50 dark:hover:bg-slate-800/60 text-slate-800 dark:text-slate-200'
                        }`}
                      >
                        <ShieldCheck className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
                        <div className="flex-1">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold">{t(language, 'mode_pq')}</span>
                            <span className="text-[9px] font-extrabold uppercase px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-400">
                              ML-KEM-768
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5 leading-tight">
                            Direct post-quantum key encapsulation with ML-DSA digital signatures.
                          </p>
                        </div>
                        {securityMode === 'pq' && (
                          <Check className="w-3.5 h-3.5 text-blue-600 dark:text-sky-400 shrink-0 mt-0.5" />
                        )}
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          setSecurityMode('weblink');
                          setIsSecurityDropdownOpen(false);
                        }}
                        className={`w-full text-left p-2.5 rounded-xl flex items-start space-x-2.5 transition-all cursor-pointer ${
                          securityMode === 'weblink'
                            ? 'bg-blue-50/90 dark:bg-blue-950/50 text-[#0B57D0] dark:text-sky-300'
                            : 'hover:bg-slate-50 dark:hover:bg-slate-800/60 text-slate-800 dark:text-slate-200'
                        }`}
                      >
                        <Link2 className="w-4 h-4 text-cyan-500 shrink-0 mt-0.5" />
                        <div className="flex-1">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold">{t(language, 'mode_weblink')}</span>
                            <span className="text-[9px] font-extrabold uppercase px-1.5 py-0.5 rounded bg-cyan-100 text-cyan-800 dark:bg-cyan-950 dark:text-cyan-400">
                              Zero-Knowledge
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5 leading-tight">
                            Client-side AES-256-GCM encrypted portal with Email OTP &amp; Burn.
                          </p>
                        </div>
                        {securityMode === 'weblink' && (
                          <Check className="w-3.5 h-3.5 text-blue-600 dark:text-sky-400 shrink-0 mt-0.5" />
                        )}
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          setSecurityMode('standard');
                          setIsSecurityDropdownOpen(false);
                        }}
                        className={`w-full text-left p-2.5 rounded-xl flex items-start space-x-2.5 transition-all cursor-pointer ${
                          securityMode === 'standard'
                            ? 'bg-blue-50/90 dark:bg-blue-950/50 text-[#0B57D0] dark:text-sky-300'
                            : 'hover:bg-slate-50 dark:hover:bg-slate-800/60 text-slate-800 dark:text-slate-200'
                        }`}
                      >
                        <Globe className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
                        <div className="flex-1">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold">{t(language, 'mode_standard')}</span>
                            <span className="text-[9px] font-extrabold uppercase px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300">
                              Regular TLS
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5 leading-tight">
                            Standard unsealed email for non-sensitive, external communication.
                          </p>
                        </div>
                        {securityMode === 'standard' && (
                          <Check className="w-3.5 h-3.5 text-blue-600 dark:text-sky-400 shrink-0 mt-0.5" />
                        )}
                      </button>
                    </div>
                  )}
                </div>
              </div>

              <div className="flex items-center space-x-1 text-[11px] text-emerald-700 dark:text-emerald-400 font-semibold">
                <Shield className="w-3.5 h-3.5" />
                <span>
                  {securityMode === 'pq'
                    ? 'End-to-End Sealed'
                    : securityMode === 'weblink'
                    ? 'Zero-Knowledge Link'
                    : 'Standard Delivery'}
                </span>
              </div>
            </div>

            {/* WebLink Security Controls (Sleek Dark/Light Unified Security Bar) */}
            {securityMode === 'weblink' && (
              <div className="px-4 py-2.5 bg-slate-100/90 dark:bg-[#0B111E] border-b border-slate-200/80 dark:border-slate-800/80 flex flex-wrap items-center justify-between gap-3 text-xs transition-colors select-none">
                <div className="flex items-center space-x-2 text-cyan-600 dark:text-cyan-400 font-semibold">
                  <UseAnimations animation={lock} size={16} strokeColor="#0284c7" />
                  <span className="tracking-wide">Private Link Settings</span>
                  <span className="text-[10px] font-extrabold uppercase px-1.5 py-0.5 rounded-full bg-cyan-500/10 text-cyan-700 dark:text-cyan-300 border border-cyan-500/20">
                    Zero-Knowledge
                  </span>
                </div>
                <div className="flex items-center space-x-2.5">
                  {/* Themed Expiry Dropdown with custom Clock icon */}
                  <div className="relative inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-lg bg-white dark:bg-[#161F33] border border-slate-200 dark:border-slate-700/80 text-slate-700 dark:text-slate-200 text-xs font-semibold shadow-2xs hover:border-cyan-500/50 dark:hover:border-cyan-400/50 transition-colors">
                    <Clock className="w-3.5 h-3.5 text-cyan-500 shrink-0" />
                    <select
                      value={expiresInHours}
                      onChange={(e) => setExpiresInHours(Number(e.target.value) as 1 | 24 | 168 | 720)}
                      className="bg-transparent border-none outline-none focus:outline-none focus:ring-0 text-slate-800 dark:text-slate-200 text-xs font-semibold cursor-pointer pr-1"
                      title="Link expiration duration"
                    >
                      <option value={1} className="bg-white dark:bg-[#161F33] text-slate-800 dark:text-slate-200">Expires: 1 hour</option>
                      <option value={24} className="bg-white dark:bg-[#161F33] text-slate-800 dark:text-slate-200">Expires: 24 hours</option>
                      <option value={168} className="bg-white dark:bg-[#161F33] text-slate-800 dark:text-slate-200">Expires: 7 days</option>
                      <option value={720} className="bg-white dark:bg-[#161F33] text-slate-800 dark:text-slate-200">Expires: 30 days</option>
                    </select>
                  </div>

                  {/* Interactive Burn-on-Read Toggle Pill */}
                  <button
                    type="button"
                    onClick={() => setBurnAfterRead(!burnAfterRead)}
                    title="Burn message immediately after first recipient decodes it"
                    className={`inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer border ${
                      burnAfterRead
                        ? 'bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-500/40 shadow-xs'
                        : 'bg-white dark:bg-[#161F33] text-slate-500 dark:text-slate-400 border-slate-200 dark:border-slate-700/80 hover:text-slate-700 dark:hover:text-slate-200'
                    }`}
                  >
                    <Flame className={`w-3.5 h-3.5 ${burnAfterRead ? 'text-rose-500' : 'text-slate-400'}`} />
                    <span>Burn on Read</span>
                    <span className={`w-1.5 h-1.5 rounded-full ${burnAfterRead ? 'bg-rose-500' : 'bg-slate-300 dark:bg-slate-600'}`} />
                  </button>

                  {/* Interactive Email OTP Toggle Pill */}
                  <button
                    type="button"
                    onClick={() => setRequireEmailOtp(!requireEmailOtp)}
                    title="Require recipient to verify identity via one-time email passcode"
                    className={`inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer border ${
                      requireEmailOtp
                        ? 'bg-cyan-500/15 text-cyan-700 dark:text-cyan-300 border-cyan-500/40 shadow-xs'
                        : 'bg-white dark:bg-[#161F33] text-slate-500 dark:text-slate-400 border-slate-200 dark:border-slate-700/80 hover:text-slate-700 dark:hover:text-slate-200'
                    }`}
                  >
                    <KeyRound className={`w-3.5 h-3.5 ${requireEmailOtp ? 'text-cyan-500' : 'text-slate-400'}`} />
                    <span>OTP Required</span>
                    <span className={`w-1.5 h-1.5 rounded-full ${requireEmailOtp ? 'bg-cyan-500' : 'bg-slate-300 dark:bg-slate-600'}`} />
                  </button>
                </div>
              </div>
            )}

            {/* Recipients Field with Email Autocomplete & Removable Chips */}
            <div
              ref={toContainerRef}
              onClick={() => toInputRef.current?.focus()}
              className="relative flex flex-wrap items-center gap-1.5 px-4 py-2 border-b border-[#F2F2F2] dark:border-[#1F2C47]/60 cursor-text min-h-[44px] focus-within:border-b-sky-500/60 dark:focus-within:border-b-sky-400/60 focus-within:bg-slate-50/50 dark:focus-within:bg-[#111A2E]/40 transition-colors duration-150"
            >
              <span className="text-xs font-semibold text-[#5F6368] dark:text-[#94A3B8] shrink-0 mr-1 select-none">
                To
              </span>

              {/* Recipient Chips */}
              {recipientsList.map((rEmail, idx) => (
                <span
                  key={`${rEmail}-${idx}`}
                  className="inline-flex items-center gap-1.5 pl-2.5 pr-1.5 py-1 rounded-full text-xs font-medium bg-blue-50/90 dark:bg-blue-950/70 border border-blue-200/90 dark:border-blue-800 text-blue-900 dark:text-blue-200 shadow-sm transition-all animate-in fade-in zoom-in-95 duration-100"
                >
                  <span className="max-w-[220px] truncate select-all font-mono text-[11px]" title={rEmail}>
                    {rEmail}
                  </span>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      removeRecipient(idx);
                    }}
                    className="w-4 h-4 rounded-full flex items-center justify-center text-blue-500 hover:text-white hover:bg-blue-600 dark:hover:bg-blue-500 transition-colors cursor-pointer shrink-0"
                    title={`Remove ${rEmail}`}
                  >
                    <X className="w-2.5 h-2.5" />
                  </button>
                </span>
              ))}

              {/* Input for typing next recipient */}
              <input
                ref={toInputRef}
                type="text"
                placeholder={recipientsList.length === 0 ? t(language, 'to_placeholder') : ''}
                value={recipientInput}
                onFocus={() => {
                  if (recipientInput.trim()) {
                    setToAutocompleteOpen(true);
                  }
                }}
                onChange={(e) => {
                  const val = e.target.value;
                  // If user typed comma or semicolon, commit immediately
                  if (val.includes(',') || val.includes(';')) {
                    commitRecipientInput(val);
                  } else {
                    setRecipientInput(val);
                    setToAutocompleteOpen(Boolean(val.trim()));
                    setSelectedSuggestionIdx(0);
                  }
                }}
                onPaste={(e) => {
                  const pasteText = e.clipboardData.getData('text');
                  if (pasteText && (pasteText.includes(',') || pasteText.includes(';') || pasteText.includes('\n'))) {
                    e.preventDefault();
                    commitRecipientInput(pasteText);
                  }
                }}
                onKeyDown={(e) => {
                  if (toAutocompleteOpen && recipientSuggestions.length > 0) {
                    if (e.key === 'ArrowDown') {
                      e.preventDefault();
                      setSelectedSuggestionIdx((prev) =>
                        Math.min(prev + 1, recipientSuggestions.length - 1)
                      );
                      return;
                    }
                    if (e.key === 'ArrowUp') {
                      e.preventDefault();
                      setSelectedSuggestionIdx((prev) => Math.max(prev - 1, 0));
                      return;
                    }
                    if (e.key === 'Enter' || e.key === 'Tab') {
                      if (recipientSuggestions[selectedSuggestionIdx]) {
                        e.preventDefault();
                        applyRecipientSuggestion(recipientSuggestions[selectedSuggestionIdx].email);
                        return;
                      }
                    }
                    if (e.key === 'Escape') {
                      setToAutocompleteOpen(false);
                      return;
                    }
                  }

                  if (e.key === 'Enter' || e.key === 'Tab' || e.key === ',' || e.key === ';') {
                    const candidate = recipientInput.trim().replace(/^[,;\s]+|[,;\s]+$/g, '');
                    if (candidate) {
                      e.preventDefault();
                      commitRecipientInput(candidate);
                    } else if (e.key === ',' || e.key === ';') {
                      e.preventDefault();
                    }
                  } else if (e.key === 'Backspace' && !recipientInput && recipientsList.length > 0) {
                    e.preventDefault();
                    setRecipientsList((prev) => prev.slice(0, prev.length - 1));
                  }
                }}
                onBlur={() => {
                  const candidate = recipientInput.trim().replace(/^[,;\s]+|[,;\s]+$/g, '');
                  if (candidate) {
                    commitRecipientInput(candidate);
                  }
                }}
                className="flex-1 min-w-[130px] bg-transparent border-0 border-none outline-none focus:outline-none focus:ring-0 ring-0 focus-visible:outline-none text-sm text-[#202124] dark:text-white py-1"
              />

              {/* Autocomplete Dropdown Popover */}
              {toAutocompleteOpen && recipientSuggestions.length > 0 && (
                <div className="absolute top-full left-12 right-4 mt-1 bg-white/98 dark:bg-[#161F33]/98 border border-slate-200 dark:border-slate-700 rounded-xl shadow-2xl backdrop-blur-xl p-1.5 z-[100] animate-in fade-in duration-100">
                  <div className="text-[10px] font-bold text-slate-400 dark:text-slate-500 px-2 py-1 uppercase tracking-wider">
                    Suggested Contacts
                  </div>
                  {recipientSuggestions.map((s, idx) => (
                    <div
                      key={s.email}
                      onMouseDown={(e) => {
                        e.preventDefault(); // prevent input blur
                        applyRecipientSuggestion(s.email);
                      }}
                      onMouseEnter={() => setSelectedSuggestionIdx(idx)}
                      className={`px-2.5 py-2 rounded-lg flex items-center justify-between text-xs cursor-pointer transition-colors ${
                        idx === selectedSuggestionIdx
                          ? 'bg-blue-50/90 dark:bg-blue-950/60 text-[#0B57D0] dark:text-sky-300'
                          : 'hover:bg-slate-50 dark:hover:bg-slate-800/60 text-slate-800 dark:text-slate-200'
                      }`}
                    >
                      <div className="flex items-center space-x-2.5 min-w-0">
                        <div className="w-6 h-6 rounded-full bg-gradient-to-tr from-sky-500 to-indigo-600 text-white font-bold text-[10px] flex items-center justify-center shrink-0">
                          {(s.name || s.email).slice(0, 2).toUpperCase()}
                        </div>
                        <div className="min-w-0 truncate">
                          {s.name && <div className="font-semibold truncate">{s.name}</div>}
                          <div className="font-mono text-[11px] text-slate-500 dark:text-slate-400 truncate">
                            {s.email}
                          </div>
                        </div>
                      </div>
                      <span className="text-[10px] font-semibold text-slate-400 shrink-0 ml-2">
                        Insert ↵
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Subject Field */}
            <div className="flex items-center px-4 py-2 border-b border-[#F2F2F2] dark:border-[#1F2C47]/60 gap-2 focus-within:border-b-sky-500/60 dark:focus-within:border-b-sky-400/60 focus-within:bg-slate-50/50 dark:focus-within:bg-[#111A2E]/40 transition-colors duration-150">
              <span className="w-12 text-xs font-semibold text-[#5F6368] dark:text-[#94A3B8]">Subject</span>
              <input
                type="text"
                placeholder={t(language, 'subject_placeholder')}
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                className="flex-1 bg-transparent border-0 border-none outline-none focus:outline-none focus:ring-0 ring-0 focus-visible:outline-none text-sm text-[#202124] dark:text-white"
              />
              {cloakSubjectHeaders && securityMode !== 'standard' && (
                <span
                  title="Hide Subject Line active: external Gmail header will read 'Encrypted QuMail Message'; real subject is sealed inside the encrypted payload."
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold qumail-accent-soft qumail-accent-text shrink-0"
                >
                  <Shield className="w-2.5 h-2.5" />
                  <span>Hidden Subject</span>
                </span>
              )}
            </div>

            {/* Confirm Before Send Overlay */}
            {showSendConfirm && (
              <div className="mx-4 mt-3 p-3.5 rounded-xl border border-amber-300 dark:border-amber-700 bg-amber-50/90 dark:bg-amber-950/40 text-xs space-y-2.5 shrink-0">
                <div className="font-bold text-amber-900 dark:text-amber-200 flex items-center gap-1.5">
                  <Shield className="w-4 h-4" />
                  <span>Confirm Dispatch</span>
                </div>
                <div className="space-y-1 text-amber-900/90 dark:text-amber-100/90">
                  <div><b>To:</b> {to}</div>
                  <div>
                    <b>Subject:</b> {subject.trim() || '(No Subject)'}
                    {cloakSubjectHeaders && securityMode !== 'standard' && ' (Subject Hidden)'}
                  </div>
                  <div>
                    <b>Protection:</b>{' '}
                    {securityMode === 'pq'
                      ? 'Quantum-Safe Private (ML-KEM-768)'
                      : securityMode === 'weblink'
                      ? 'Secure Private Link (Zero-Knowledge)'
                      : 'Standard Email'}
                  </div>
                </div>
                <div className="flex items-center justify-end gap-2 pt-1">
                  <button
                    type="button"
                    onClick={() => setShowSendConfirm(false)}
                    className="px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 font-semibold hover:bg-white/60 dark:hover:bg-black/20 cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={() => dispatchSend()}
                    className="px-3.5 py-1.5 rounded-lg qumail-accent-bg text-white font-bold shadow-sm cursor-pointer"
                  >
                    Confirm & Send
                  </button>
                </div>
              </div>
            )}

            {/* Unregistered Recipients Warning with 1-Click Fallback to WebLink */}
            {unregisteredWarning && (
              <div className="mx-4 mt-3 p-3.5 rounded-xl border border-sky-300 dark:border-sky-700 bg-sky-50/95 dark:bg-sky-950/60 text-xs space-y-2.5 shrink-0 animate-in fade-in">
                <div className="font-bold text-sky-950 dark:text-sky-200 flex items-center gap-1.5">
                  <ExternalLink className="w-4 h-4 text-sky-600 dark:text-sky-400" />
                  <span>External Recipient(s) Detected</span>
                </div>
                <div className="space-y-1.5 text-sky-900/90 dark:text-sky-100/90">
                  <p>
                    The following recipient(s) do not have registered Post-Quantum ML-KEM keys:
                  </p>
                  <div className="p-2 rounded-lg bg-sky-100/60 dark:bg-sky-900/40 font-mono text-[11px] break-all">
                    {unregisteredWarning.join(', ')}
                  </div>
                  <p className="text-[11px] text-sky-800 dark:text-sky-300">
                    Switch to <b>Secure Private Link</b> to send this email end-to-end encrypted with zero installation required for external recipients.
                  </p>
                </div>
                <div className="flex items-center justify-end gap-2 pt-1">
                  <button
                    type="button"
                    onClick={() => setUnregisteredWarning(null)}
                    className="px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 font-semibold hover:bg-white/60 dark:hover:bg-black/20 cursor-pointer"
                  >
                    Edit Recipients
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setSecurityMode('weblink');
                      setUnregisteredWarning(null);
                      dispatchSend('weblink');
                    }}
                    className="px-3.5 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-700 text-white font-bold shadow-sm cursor-pointer flex items-center gap-1.5"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                    <span>Switch to Secure Private Link & Send</span>
                  </button>
                </div>
              </div>
            )}

            {/* Large Attachment Size Warning */}
            {attachWarning && (
              <div className="mx-4 mt-2 px-3 py-2 rounded-lg bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 text-[11px] text-amber-800 dark:text-amber-200 flex items-center justify-between">
                <span>{attachWarning}</span>
                <button
                  type="button"
                  onClick={() => setAttachWarning(null)}
                  className="text-amber-600 dark:text-amber-400 font-bold ml-2 hover:underline cursor-pointer"
                >
                  Dismiss
                </button>
              </div>
            )}

            {/* Message Body Editor */}
            <div className="flex-1 p-4 overflow-y-auto focus-within:bg-slate-50/30 dark:focus-within:bg-[#111A2E]/20 transition-colors duration-150">
              <textarea
                placeholder={t(language, 'body_placeholder')}
                value={body}
                onChange={(e) => setBody(e.target.value)}
                style={{
                  fontFamily: FONT_FAMILY_STYLE[fontFamily],
                  fontSize: FONT_SIZE_STYLE[fontSize],
                }}
                className="w-full h-full bg-transparent border-0 border-none outline-none focus:outline-none focus:ring-0 ring-0 focus-visible:outline-none resize-none text-[#202124] dark:text-[#F1F5F9] leading-relaxed placeholder-[#5F6368]"
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
                  className="flex items-center space-x-2 px-6 py-2.5 rounded-full qumail-accent-bg text-white font-bold text-sm shadow-md hover:shadow-lg transition-all outline-none disabled:opacity-50 cursor-pointer"
                >
                  <UseAnimations animation={send} size={18} strokeColor="#ffffff" className="shrink-0" />
                  <span>{isSending ? t(language, 'sending') : t(language, 'send')}</span>
                </button>

                <button
                  type="button"
                  onClick={handleSimulateAttach}
                  disabled={isAttaching || isSending}
                  title={t(language, 'attach_files')}
                  className="p-2 text-[#5F6368] dark:text-[#94A3B8] hover:bg-[#F2F6FC] dark:hover:bg-[#1E2740] rounded-full transition-colors disabled:opacity-50 flex items-center gap-1.5 text-xs"
                >
                  <Paperclip className="w-5 h-5" />
                  {isAttaching && <span className="text-[11px] font-medium animate-pulse">Reading…</span>}
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
                  setRecipientsList([]);
                  setRecipientInput('');
                  setSubject('');
                  setBody('');
                  setAttachments([]);
                  onClose();
                }}
                title={t(language, 'discard')}
                className="p-2 text-[#5F6368] dark:text-[#94A3B8] hover:bg-red-50 dark:hover:bg-red-950/40 hover:text-red-600 rounded-full transition-colors cursor-pointer"
              >
                <UseAnimations animation={trash2} size={20} strokeColor="currentColor" className="shrink-0" />
              </button>
            </div>
          </form>
        )}
      </motion.div>
    </AnimatePresence>
  );
};
