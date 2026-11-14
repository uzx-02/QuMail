/**
 * OnboardingTour — first-run guided tour for QuMail.
 *
 * Renders a spotlight overlay that highlights specific DOM elements
 * (found via data-tour="<id>" attributes) while darkening everything else.
 * Animated tooltip with an arrow, Next / Back / Skip controls.
 *
 * Usage:
 *   <OnboardingTour isOpen={showTour} onClose={() => setShowTour(false)} />
 *
 * Add   data-tour="compose"   etc. to target elements in Sidebar / Header.
 */

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, ChevronRight, ChevronLeft, Sparkles, ShieldCheck, Lock, Mail, Settings, HelpCircle, Pencil } from 'lucide-react';

// ─── Tour step definitions ────────────────────────────────────────────────────

type Placement = 'right' | 'left' | 'bottom' | 'top' | 'center';

interface TourStep {
  id: string;             // matches data-tour="<id>" on the target element
  title: string;
  body: string;
  icon: React.ReactNode;
  placement: Placement;   // which side of the element the tooltip appears on
  padding?: number;       // extra space around the highlighted element (default 12)
}

const STEPS: TourStep[] = [
  {
    id: '__welcome__',
    title: 'Welcome to QuMail',
    body: 'QuMail is an email client designed with post-quantum encryption standards. This brief walkthrough introduces the core interface and security controls.',
    icon: <Sparkles className="w-5 h-5 text-indigo-400" />,
    placement: 'center',
  },
  {
    id: 'tour-compose',
    title: 'Compose Messages',
    body: 'Create and dispatch emails using your chosen security mode: Standard email, Post-Quantum sealed (ML-KEM-768), or a zero-knowledge Secure Private Link.',
    icon: <Pencil className="w-5 h-5 text-indigo-400" />,
    placement: 'right',
    padding: 10,
  },
  {
    id: 'tour-inbox',
    title: 'Inbox & Mail Folders',
    body: 'Access your messages and folders from the sidebar. Messages indicate their encryption status with cryptographic badges in the list.',
    icon: <Mail className="w-5 h-5 text-indigo-400" />,
    placement: 'right',
    padding: 14,
  },
  {
    id: 'tour-search',
    title: 'Search & Filtering',
    body: 'Search across message subjects, senders, and content. The filter menu provides granular filters for date ranges, folders, and security tiers.',
    icon: <ShieldCheck className="w-5 h-5 text-indigo-400" />,
    placement: 'bottom',
    padding: 10,
  },
  {
    id: 'tour-security',
    title: 'Post-Quantum Security Status',
    body: 'Displays connection security and active cryptographic primitives. QuMail implements NIST FIPS 203 (ML-KEM-768) and FIPS 204 (ML-DSA-65).',
    icon: <Lock className="w-5 h-5 text-indigo-400" />,
    placement: 'bottom',
    padding: 10,
  },
  {
    id: 'tour-settings',
    title: 'Settings & Customization',
    body: 'Configure mailbox preferences, dark/light themes, typography, key management, security policies, and offline translation.',
    icon: <Settings className="w-5 h-5 text-indigo-400" />,
    placement: 'bottom',
    padding: 10,
  },
  {
    id: 'tour-help',
    title: 'Help & FAQs',
    body: 'Access detailed documentation, cryptographic architecture FAQs, or replay this interactive walkthrough at any time.',
    icon: <HelpCircle className="w-5 h-5 text-indigo-400" />,
    placement: 'bottom',
    padding: 10,
  },
  {
    id: '__done__',
    title: 'Walkthrough Complete',
    body: 'You are ready to use QuMail. If you need documentation or wish to revisit this tour, use the Help menu in the top bar.',
    icon: <Sparkles className="w-5 h-5 text-emerald-400" />,
    placement: 'center',
  },
];

// ─── Spotlight rect ───────────────────────────────────────────────────────────

interface SpotRect {
  top: number;
  left: number;
  width: number;
  height: number;
  borderRadius: number;
}

const NULL_RECT: SpotRect = { top: 0, left: 0, width: 0, height: 0, borderRadius: 0 };

function getElementRect(id: string, padding = 12): SpotRect | null {
  const el = document.querySelector(`[data-tour="${id}"]`);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return {
    top: r.top - padding,
    left: r.left - padding,
    width: r.width + padding * 2,
    height: r.height + padding * 2,
    borderRadius: 14,
  };
}

// ─── Tooltip positioning ──────────────────────────────────────────────────────

const TOOLTIP_W = 320;
const TOOLTIP_H_EST = 180; // rough estimate

function computeTooltipPos(rect: SpotRect, placement: Placement, vw: number, vh: number) {
  const GAP = 18; // gap between spotlight edge and tooltip
  const cx = rect.left + rect.width / 2;
  const cy = rect.top + rect.height / 2;

  switch (placement) {
    case 'right':
      return {
        left: Math.min(rect.left + rect.width + GAP, vw - TOOLTIP_W - 12),
        top: Math.max(12, cy - TOOLTIP_H_EST / 2),
        arrowSide: 'left' as const,
      };
    case 'left':
      return {
        left: Math.max(12, rect.left - TOOLTIP_W - GAP),
        top: Math.max(12, cy - TOOLTIP_H_EST / 2),
        arrowSide: 'right' as const,
      };
    case 'bottom':
      return {
        left: Math.max(12, Math.min(cx - TOOLTIP_W / 2, vw - TOOLTIP_W - 12)),
        top: Math.min(rect.top + rect.height + GAP, vh - TOOLTIP_H_EST - 12),
        arrowSide: 'top' as const,
      };
    case 'top':
      return {
        left: Math.max(12, Math.min(cx - TOOLTIP_W / 2, vw - TOOLTIP_W - 12)),
        top: Math.max(12, rect.top - TOOLTIP_H_EST - GAP),
        arrowSide: 'bottom' as const,
      };
    case 'center':
    default:
      return {
        left: vw / 2 - TOOLTIP_W / 2,
        top: vh / 2 - TOOLTIP_H_EST / 2,
        arrowSide: null as null,
      };
  }
}

// ─── Arrow component ──────────────────────────────────────────────────────────

function Arrow({ side }: { side: 'left' | 'right' | 'top' | 'bottom' | null }) {
  if (!side) return null;
  const baseClass = 'absolute w-0 h-0';
  const styles: Record<string, React.CSSProperties> = {
    left:   { borderTop: '8px solid transparent', borderBottom: '8px solid transparent', borderRight: '12px solid #1E2740', left: -12, top: '50%', transform: 'translateY(-50%)' },
    right:  { borderTop: '8px solid transparent', borderBottom: '8px solid transparent', borderLeft: '12px solid #1E2740',  right: -12, top: '50%', transform: 'translateY(-50%)' },
    top:    { borderLeft: '8px solid transparent', borderRight: '8px solid transparent', borderBottom: '12px solid #1E2740', top: -12, left: '50%', transform: 'translateX(-50%)' },
    bottom: { borderLeft: '8px solid transparent', borderRight: '8px solid transparent', borderTop: '12px solid #1E2740',    bottom: -12, left: '50%', transform: 'translateX(-50%)' },
  };

  // Subtle directional floating bounce towards the highlighted element
  const bounceAnim: Record<string, any> = {
    left:   { x: [0, -4, 0] },
    right:  { x: [0, 4, 0] },
    top:    { y: [0, -4, 0] },
    bottom: { y: [0, 4, 0] },
  };

  return (
    <motion.div
      className={baseClass}
      style={styles[side]}
      animate={bounceAnim[side]}
      transition={{ duration: 1.4, repeat: Infinity, ease: 'easeInOut' }}
    />
  );
}

// ─── Pulsing ring around spotlight ───────────────────────────────────────────

function PulseRing({ rect }: { rect: SpotRect }) {
  return (
    <motion.div
      key={`${rect.top}-${rect.left}`}
      className="pointer-events-none fixed z-[9997]"
      style={{
        top: rect.top - 6,
        left: rect.left - 6,
        width: rect.width + 12,
        height: rect.height + 12,
        borderRadius: rect.borderRadius + 6,
        border: '2px solid rgba(99, 102, 241, 0.75)',
        boxShadow: '0 0 25px 5px rgba(99, 102, 241, 0.35)',
      }}
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: [0.85, 0.35, 0.85], scale: [1, 1.025, 1] }}
      transition={{ duration: 1.8, repeat: Infinity, ease: 'easeInOut' }}
    />
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

interface OnboardingTourProps {
  isOpen: boolean;
  onClose: () => void;
}

const STORAGE_KEY = 'qumail-tour-completed';

export function OnboardingTour({ isOpen, onClose }: OnboardingTourProps) {
  const [stepIndex, setStepIndex] = useState(0);
  const [spotRect, setSpotRect] = useState<SpotRect | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ left: 0, top: 0, arrowSide: null as 'left' | 'right' | 'top' | 'bottom' | null });
  const [direction, setDirection] = useState<1 | -1>(1);
  const rafRef = useRef<number | null>(null);

  const step = STEPS[stepIndex];
  const isCenter = step.placement === 'center';
  const isFirst = stepIndex === 0;
  const isLast = stepIndex === STEPS.length - 1;

  // Update spotlight position on step change or window resize
  const updatePositions = useCallback(() => {
    if (!isOpen) return;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    if (isCenter) {
      setSpotRect(null);
      setTooltipPos({ left: vw / 2 - TOOLTIP_W / 2, top: vh / 2 - TOOLTIP_H_EST / 2, arrowSide: null });
      return;
    }

    const rect = getElementRect(step.id, step.padding ?? 12);
    if (!rect) {
      // element not found (maybe sidebar collapsed) — show centered
      setSpotRect(null);
      setTooltipPos({ left: vw / 2 - TOOLTIP_W / 2, top: vh / 2 - TOOLTIP_H_EST / 2, arrowSide: null });
      return;
    }

    setSpotRect(rect);
    const tp = computeTooltipPos(rect, step.placement, vw, vh);
    setTooltipPos(tp);
  }, [isOpen, step, isCenter]);

  useEffect(() => {
    if (!isOpen) return;
    // Small delay so elements fully render before measuring
    const t = setTimeout(updatePositions, 80);
    window.addEventListener('resize', updatePositions);
    return () => {
      clearTimeout(t);
      window.removeEventListener('resize', updatePositions);
    };
  }, [isOpen, stepIndex, updatePositions]);

  // Keyboard navigation
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight' || e.key === 'Enter') handleNext();
      if (e.key === 'ArrowLeft') handleBack();
      if (e.key === 'Escape') handleClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, stepIndex]);

  const handleClose = useCallback(() => {
    markTourCompleted();
    onClose();
    setTimeout(() => setStepIndex(0), 400);
  }, [onClose]);

  const handleNext = useCallback(() => {
    if (isLast) { handleClose(); return; }
    setDirection(1);
    setStepIndex((i) => i + 1);
  }, [isLast, handleClose]);

  const handleBack = useCallback(() => {
    if (isFirst) return;
    setDirection(-1);
    setStepIndex((i) => i - 1);
  }, [isFirst]);

  if (!isOpen) return null;

  // ── SVG overlay with cutout ──
  const vw = window.innerWidth;
  const vh = window.innerHeight;

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Dark overlay with SVG cutout */}
          <motion.div
            className="fixed inset-0 z-[9996] pointer-events-auto"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            onClick={handleClose}
          >
            {spotRect ? (
              <svg
                width={vw}
                height={vh}
                className="absolute inset-0 w-full h-full"
                style={{ display: 'block' }}
              >
                <defs>
                  <mask id="tour-mask">
                    {/* White = visible (dark overlay shown) */}
                    <rect width={vw} height={vh} fill="white" />
                    {/* Black = transparent (cutout / spotlight) */}
                    <motion.rect
                      animate={{
                        x: spotRect.left,
                        y: spotRect.top,
                        width: spotRect.width,
                        height: spotRect.height,
                        rx: spotRect.borderRadius,
                        ry: spotRect.borderRadius,
                      }}
                      transition={{ type: 'spring', stiffness: 320, damping: 36 }}
                      fill="black"
                    />
                  </mask>
                </defs>
                <rect
                  width={vw}
                  height={vh}
                  fill="rgba(0,0,0,0.72)"
                  mask="url(#tour-mask)"
                />
              </svg>
            ) : (
              // No spotlight — just a plain dark backdrop
              <div className="absolute inset-0 bg-black/70" />
            )}
          </motion.div>

          {/* Pulsing ring around highlighted element */}
          {spotRect && <PulseRing rect={spotRect} />}

          {/* Tooltip card */}
          <motion.div
            key={stepIndex}
            className="fixed z-[9999] pointer-events-auto select-none"
            style={{
              width: TOOLTIP_W,
              left: tooltipPos.left,
              top: tooltipPos.top,
            }}
            initial={{ opacity: 0, y: direction > 0 ? 14 : -14, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: direction > 0 ? -10 : 10, scale: 0.96 }}
            transition={{ type: 'spring', stiffness: 380, damping: 32, duration: 0.28 }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Arrow */}
            <div className="relative">
              <Arrow side={tooltipPos.arrowSide} />

              {/* Card */}
              <div className="relative rounded-2xl bg-[#1E2740]/98 backdrop-blur-xl border border-indigo-500/25 shadow-2xl shadow-black/60 overflow-hidden">

                {/* Top accent bar */}
                <div className="h-[3px] w-full bg-gradient-to-r from-indigo-500 via-sky-400 to-indigo-500" />

                <div className="px-5 pt-4 pb-5 space-y-3.5">
                  {/* Header row */}
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-2.5">
                      <div className="p-2 rounded-xl bg-indigo-950/60 border border-indigo-800/50 shrink-0">
                        {step.icon}
                      </div>
                      <h3 className="text-sm font-bold text-white leading-snug">
                        {step.title}
                      </h3>
                    </div>
                    <button
                      onClick={handleClose}
                      className="p-1.5 rounded-full text-slate-400 hover:text-white hover:bg-white/10 transition-colors cursor-pointer shrink-0 mt-0.5"
                      title="Skip tour"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  {/* Body text */}
                  <p className="text-[13px] text-slate-300 leading-relaxed">
                    {step.body}
                  </p>

                  {/* Progress dots + buttons */}
                  <div className="flex items-center justify-between pt-1">
                    {/* Step dots */}
                    <div className="flex items-center gap-1.5">
                      {STEPS.map((_, i) => (
                        <motion.div
                          key={i}
                          animate={{
                            width: i === stepIndex ? 20 : 6,
                            backgroundColor: i === stepIndex ? '#818CF8' : i < stepIndex ? '#4F46E5' : '#334155',
                          }}
                          transition={{ duration: 0.25 }}
                          className="h-1.5 rounded-full"
                        />
                      ))}
                    </div>

                    {/* Nav buttons */}
                    <div className="flex items-center gap-2">
                      {!isFirst && (
                        <button
                          onClick={handleBack}
                          className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-white hover:bg-white/8 transition-colors cursor-pointer"
                        >
                          <ChevronLeft className="w-3.5 h-3.5" />
                          Back
                        </button>
                      )}
                      <button
                        onClick={handleNext}
                        className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white transition-colors cursor-pointer shadow-lg shadow-indigo-900/40"
                      >
                        {isLast ? 'Get started' : 'Next'}
                        {!isLast && <ChevronRight className="w-3.5 h-3.5" />}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

/** Returns true if the user has NOT completed the tour yet */
export function shouldShowTour(settings?: { tourCompleted?: boolean }): boolean {
  if (settings?.tourCompleted) return false;
  try {
    if (localStorage.getItem(STORAGE_KEY) === 'true') return false;
  } catch {}
  return true;
}

/** Mark tour completed in local storage */
export function markTourCompleted(): void {
  try {
    localStorage.setItem(STORAGE_KEY, 'true');
  } catch {}
}

/** Programmatically reset the tour (useful for "replay tour" button) */
export function resetTour(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {}
}
