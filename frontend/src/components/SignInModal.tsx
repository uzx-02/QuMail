import React, { useState } from 'react';
import { X, ShieldCheck, Mail, User, Building, KeyRound, Sparkles } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { ShinyText } from './reactbits/ShinyText';

interface SignInModalProps {
  isOpen: boolean;
  onClose?: () => void;
  onSignIn: (email: string, displayName?: string, organization?: string) => Promise<void>;
  allowClose?: boolean;
}

export const SignInModal: React.FC<SignInModalProps> = ({
  isOpen,
  onClose,
  onSignIn,
  allowClose = true,
}) => {
  const [email, setEmail] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [organization, setOrganization] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !email.includes('@')) {
      setError('Please enter a valid email address (e.g. name@domain.com).');
      return;
    }
    setError('');
    setIsSubmitting(true);
    try {
      await onSignIn(email.trim(), displayName.trim(), organization.trim());
      if (onClose) onClose();
    } catch (err: any) {
      setError(err?.message || 'Failed to initialize account identity.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleQuickDemo = async () => {
    setError('');
    setIsSubmitting(true);
    try {
      await onSignIn('demo.officer@qumail.sec', 'Demo Officer', 'Defence & Aerospace R&D');
      if (onClose) onClose();
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 10 }}
          transition={{ duration: 0.2 }}
          className="w-full max-w-md bg-white dark:bg-[#161F33] rounded-3xl shadow-2xl border border-gray-200 dark:border-gray-800 overflow-hidden flex flex-col"
        >
          {/* Header */}
          <div className="relative px-6 pt-6 pb-4 flex flex-col items-center text-center border-b border-gray-100 dark:border-gray-800/80">
            {allowClose && onClose && (
              <button
                onClick={onClose}
                className="absolute top-5 right-5 p-2 rounded-full text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                title="Close"
              >
                <X className="w-5 h-5" />
              </button>
            )}

            <div className="w-14 h-14 rounded-2xl bg-gradient-to-tr from-[#0B57D0] to-[#4F46E5] flex items-center justify-center shadow-lg shadow-blue-500/25 mb-3">
              <ShieldCheck className="w-8 h-8 text-white" />
            </div>

            <div className="flex items-center space-x-1.5">
              <span className="text-xl font-bold tracking-tight text-[#202124] dark:text-[#F1F5F9]">
                QuMail
              </span>
              <ShinyText
                text="1.0"
                className="text-xs font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-blue-50 dark:bg-blue-950/60 border border-blue-200 dark:border-blue-800 text-[#0B57D0] dark:text-[#818CF8]"
              />
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 max-w-xs">
              Sign in with your email to bind your local Post-Quantum Cryptographic keypair.
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="p-6 space-y-4">
            {error && (
              <div className="p-3 rounded-xl bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/60 text-xs text-red-600 dark:text-red-400">
                {error}
              </div>
            )}

            <div>
              <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1.5">
                Your Email Address <span className="text-red-500">*</span>
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-gray-400">
                  <Mail className="w-4 h-4" />
                </div>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="e.g. you@company.com"
                  autoFocus
                  required
                  className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-gray-50/50 dark:bg-[#0A0E17] text-sm text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 transition-all"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1.5">
                Display Name (Optional)
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-gray-400">
                  <User className="w-4 h-4" />
                </div>
                <input
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="e.g. John Doe"
                  className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-gray-50/50 dark:bg-[#0A0E17] text-sm text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 transition-all"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1.5">
                Organization / Team (Optional)
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-gray-400">
                  <Building className="w-4 h-4" />
                </div>
                <input
                  type="text"
                  value={organization}
                  onChange={(e) => setOrganization(e.target.value)}
                  placeholder="e.g. Acme Corp / Research Lab"
                  className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-gray-50/50 dark:bg-[#0A0E17] text-sm text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 transition-all"
                />
              </div>
            </div>

            {/* PQC info badge */}
            <div className="p-3 rounded-2xl bg-blue-50/60 dark:bg-blue-950/30 border border-blue-100 dark:border-blue-900/40 flex items-start space-x-2.5">
              <KeyRound className="w-4 h-4 text-blue-600 dark:text-blue-400 shrink-0 mt-0.5" />
              <div className="text-[11px] text-blue-800 dark:text-blue-300 leading-relaxed">
                Signing in binds NIST FIPS 203 (ML-KEM-768) and FIPS 204 (ML-DSA-65) key generation to this mailbox. Private keys never leave this workstation.
              </div>
            </div>

            {/* Submit button */}
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full py-3 rounded-2xl bg-[#0B57D0] hover:bg-[#0842A0] text-white font-semibold text-sm shadow-md hover:shadow-lg transition-all disabled:opacity-50 flex items-center justify-center space-x-2"
            >
              <span>{isSubmitting ? 'Initializing Quantum Keys...' : 'Sign In & Enter Mailbox'}</span>
            </button>

            {/* Quick Demo Option */}
            <div className="pt-2 text-center">
              <button
                type="button"
                onClick={handleQuickDemo}
                className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center justify-center space-x-1.5 mx-auto"
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>Or use 1-click Demo Account</span>
              </button>
            </div>
          </form>
        </motion.div>
      </div>
    </AnimatePresence>
  );
};
