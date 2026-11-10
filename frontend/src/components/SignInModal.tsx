import React, { useState, useEffect } from 'react';
import { X, ShieldCheck, Mail, User, Building, KeyRound, ExternalLink, FileCode, CheckCircle2, AlertCircle, RefreshCw } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { ShinyText } from './reactbits/ShinyText';
import { api } from '../lib/api';

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
  const [isGoogleAuthenticating, setIsGoogleAuthenticating] = useState(false);
  const [error, setError] = useState('');
  const [showManual, setShowManual] = useState(false);

  // Google OAuth client secret configuration state
  const [needsSecret, setNeedsSecret] = useState(false);
  const [manualClientId, setManualClientId] = useState('');
  const [manualClientSecret, setManualClientSecret] = useState('');
  const [secretSuccess, setSecretSuccess] = useState('');

  if (!isOpen) return null;

  const handleGoogleAuth = async () => {
    setError('');
    setIsGoogleAuthenticating(true);
    try {
      const res = await api.signInWithGoogle();
      if (res.success && res.account) {
        await onSignIn(res.account.email, res.account.displayName, res.account.provider);
        if (onClose) onClose();
      } else if (res.needsClientSecret) {
        setNeedsSecret(true);
        setError('Google OAuth Client Secret is required to launch browser authentication.');
      } else {
        setError(res.message || 'Google authentication failed or was cancelled.');
      }
    } catch (err: any) {
      setError(err?.message || 'Google authentication encountered an error.');
    } finally {
      setIsGoogleAuthenticating(false);
    }
  };

  const handleSelectSecretFile = async () => {
    setError('');
    setSecretSuccess('');
    const res = await api.selectGoogleClientSecret();
    if (res.success) {
      setSecretSuccess('Google Client Secret loaded! You can now Sign In with Google.');
      setNeedsSecret(false);
      // Immediately trigger Google OAuth
      handleGoogleAuth();
    } else {
      setError(res.message);
    }
  };

  const handleSaveCredentialsManually = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    const res = await api.saveGoogleCredentials(manualClientId, manualClientSecret);
    if (res.success) {
      setSecretSuccess('Credentials saved! Launching Google authentication...');
      setNeedsSecret(false);
      handleGoogleAuth();
    } else {
      setError(res.message);
    }
  };

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

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 10 }}
          transition={{ duration: 0.2 }}
          className="w-full max-w-md bg-white dark:bg-[#161F33] rounded-3xl shadow-2xl border border-gray-200 dark:border-gray-800 overflow-hidden flex flex-col max-h-[90vh] overflow-y-auto"
        >
          {/* Header */}
          <div className="relative px-6 pt-6 pb-4 flex flex-col items-center text-center border-b border-gray-100 dark:border-gray-800/80 shrink-0">
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
              Live Post-Quantum Cryptographic Mailbox with Real-World Provider Integration.
            </p>
          </div>

          <div className="p-6 space-y-5">
            {error && (
              <div className="p-3.5 rounded-2xl bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/60 text-xs text-red-600 dark:text-red-400 flex items-start space-x-2">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <div className="leading-relaxed">{error}</div>
              </div>
            )}

            {secretSuccess && (
              <div className="p-3.5 rounded-2xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-900/60 text-xs text-emerald-700 dark:text-emerald-400 flex items-start space-x-2">
                <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
                <div className="leading-relaxed">{secretSuccess}</div>
              </div>
            )}

            {/* 1. PRIMARY: SIGN IN WITH GOOGLE */}
            <div className="space-y-3">
              <button
                type="button"
                onClick={handleGoogleAuth}
                disabled={isGoogleAuthenticating}
                className="w-full py-3.5 px-4 rounded-2xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#111726] hover:bg-gray-50 dark:hover:bg-[#1C2740] text-gray-800 dark:text-white font-semibold text-sm shadow-sm hover:shadow transition-all flex items-center justify-center space-x-3 disabled:opacity-50"
              >
                {isGoogleAuthenticating ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin text-blue-600" />
                    <span>Authorizing in Browser...</span>
                  </>
                ) : (
                  <>
                    {/* Google G Logo SVG */}
                    <svg className="w-5 h-5 shrink-0" viewBox="0 0 24 24">
                      <path
                        fill="#4285F4"
                        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                      />
                      <path
                        fill="#34A853"
                        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                      />
                      <path
                        fill="#FBBC05"
                        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
                      />
                      <path
                        fill="#EA4335"
                        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
                      />
                    </svg>
                    <span>Sign In with Google</span>
                  </>
                )}
              </button>

              {/* If client secret is needed */}
              {needsSecret && (
                <div className="p-4 rounded-2xl bg-blue-50/60 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-900/60 space-y-3">
                  <div className="flex items-start space-x-2 text-xs text-blue-900 dark:text-blue-300 font-semibold">
                    <FileCode className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
                    <span>Google Cloud OAuth Credentials Required</span>
                  </div>
                  <p className="text-[11px] text-gray-600 dark:text-gray-400 leading-relaxed">
                    Select your <code className="text-blue-600 dark:text-blue-400">client_secret_*.json</code> file downloaded from Google Cloud Console (APIs & Services &gt; Credentials &gt; OAuth 2.0 Client ID for Desktop app).
                  </p>
                  <div className="flex items-center space-x-2">
                    <button
                      type="button"
                      onClick={handleSelectSecretFile}
                      className="px-4 py-2 rounded-xl bg-[#0B57D0] hover:bg-[#0842A0] text-white text-xs font-bold transition-all shadow-sm"
                    >
                      Browse &amp; Select client_secret.json
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* DIVIDER */}
            <div className="relative flex py-1 items-center">
              <div className="flex-grow border-t border-gray-200 dark:border-gray-800"></div>
              <span className="flex-shrink mx-3 text-xs text-gray-400 dark:text-gray-500 uppercase font-semibold">
                Or Custom Mailbox
              </span>
              <div className="flex-grow border-t border-gray-200 dark:border-gray-800"></div>
            </div>

            {/* 2. MANUAL ACCOUNT ENROLLMENT */}
            <form onSubmit={handleSubmit} className="space-y-3.5">
              <div>
                <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1.5">
                  Email Address <span className="text-red-500">*</span>
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-gray-400">
                    <Mail className="w-4 h-4" />
                  </div>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="e.g. user@company.com or name@gmail.com"
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
                    placeholder="e.g. Alice Smith"
                    className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-gray-50/50 dark:bg-[#0A0E17] text-sm text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 transition-all"
                  />
                </div>
              </div>

              {/* PQC info badge */}
              <div className="p-3 rounded-2xl bg-blue-50/60 dark:bg-blue-950/30 border border-blue-100 dark:border-blue-900/40 flex items-start space-x-2.5">
                <KeyRound className="w-4 h-4 text-blue-600 dark:text-blue-400 shrink-0 mt-0.5" />
                <div className="text-[11px] text-blue-800 dark:text-blue-300 leading-relaxed">
                  Binds <b>NIST FIPS 203 (ML-KEM-768)</b> &amp; <b>FIPS 204 (ML-DSA-65)</b> key generation locally. Private keys remain strictly on this device.
                </div>
              </div>

              {/* Submit button */}
              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full py-3 rounded-2xl bg-[#0B57D0] hover:bg-[#0842A0] text-white font-semibold text-sm shadow-md hover:shadow-lg transition-all disabled:opacity-50 flex items-center justify-center space-x-2"
              >
                <span>{isSubmitting ? 'Initializing Quantum Keys...' : 'Enter Mailbox'}</span>
              </button>
            </form>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
};
