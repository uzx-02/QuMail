import React, { useState, useMemo } from 'react';
import {
  X,
  ShieldCheck,
  Mail,
  User,
  KeyRound,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Eye,
  EyeOff,
  Server,
  Lock,
  ChevronDown,
  ChevronUp,
  FileCode,
} from 'lucide-react';
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
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [displayName, setDisplayName] = useState('');
  const [organization, setOrganization] = useState('');

  // Custom IMAP / SMTP server settings
  const [showAdvancedServer, setShowAdvancedServer] = useState(false);
  const [customImapHost, setCustomImapHost] = useState('');
  const [customImapPort, setCustomImapPort] = useState(993);
  const [customSmtpHost, setCustomSmtpHost] = useState('');
  const [customSmtpPort, setCustomSmtpPort] = useState(587);

  // Status flags
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [verificationStep, setVerificationStep] = useState('');
  const [isGoogleAuthenticating, setIsGoogleAuthenticating] = useState(false);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  // Auto-detect provider metadata based on domain
  const providerInfo = useMemo(() => {
    const trimmed = email.trim().toLowerCase();
    if (!trimmed.includes('@')) return null;
    const domain = trimmed.split('@')[1];
    if (!domain) return null;

    if (domain.includes('gmail') || domain.includes('googlemail')) {
      return {
        name: 'Google Workspace / Gmail',
        defaultImap: 'imap.gmail.com',
        defaultSmtp: 'smtp.gmail.com',
        badgeColor: 'text-red-500 bg-red-50 dark:bg-red-950/40 border-red-200 dark:border-red-900',
        note: 'For Gmail custom login, please generate an App Password from your Google Account Security settings.',
      };
    }
    if (domain.includes('outlook') || domain.includes('hotmail') || domain.includes('live') || domain.includes('office365')) {
      return {
        name: 'Microsoft Outlook / 365',
        defaultImap: 'outlook.office365.com',
        defaultSmtp: 'smtp.office365.com',
        badgeColor: 'text-blue-500 bg-blue-50 dark:bg-blue-950/40 border-blue-200 dark:border-blue-900',
        note: 'Microsoft accounts with 2FA require an App Password from Microsoft Account Security.',
      };
    }
    if (domain.includes('yahoo') || domain.includes('ymail') || domain.includes('rocketmail')) {
      return {
        name: 'Yahoo Mail',
        defaultImap: 'imap.mail.yahoo.com',
        defaultSmtp: 'smtp.mail.yahoo.com',
        badgeColor: 'text-purple-500 bg-purple-50 dark:bg-purple-950/40 border-purple-200 dark:border-purple-900',
        note: 'Yahoo Mail requires an App Password generated under Account Security.',
      };
    }
    if (domain.includes('zoho')) {
      return {
        name: 'Zoho Mail',
        defaultImap: 'imap.zoho.com',
        defaultSmtp: 'smtp.zoho.com',
        badgeColor: 'text-emerald-500 bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-900',
        note: 'Zoho accounts with TFA enabled require an Application-Specific Password.',
      };
    }
    if (domain.includes('icloud') || domain.includes('me.com') || domain.includes('mac.com')) {
      return {
        name: 'Apple iCloud',
        defaultImap: 'imap.mail.me.com',
        defaultSmtp: 'smtp.mail.me.com',
        badgeColor: 'text-cyan-500 bg-cyan-50 dark:bg-cyan-950/40 border-cyan-200 dark:border-cyan-900',
        note: 'Apple requires an app-specific password from appleid.apple.com.',
      };
    }
    return {
      name: 'Corporate / Custom IMAP',
      defaultImap: `imap.${domain}`,
      defaultSmtp: `smtp.${domain}`,
      badgeColor: 'text-gray-500 bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700',
      note: 'Connecting to standard TLS-encrypted IMAP (port 993) and SMTP (port 587).',
    };
  }, [email]);

  if (!isOpen) return null;

  const handleGoogleAuth = async () => {
    setError('');
    setSuccessMsg('');
    setVerificationStep('Opening secure Google sign-in in your browser...');
    setIsGoogleAuthenticating(true);
    try {
      const res = await api.signInWithGoogle();
      if (res.success && res.account) {
        setVerificationStep('Verifying the Google identity and restoring your QuMail vault...');
        await onSignIn(res.account.email, res.account.displayName, res.account.provider);
        if (onClose) onClose();
      } else {
        setError(res.message || 'Google authentication was not completed.');
      }
    } catch (err: any) {
      setError(err?.message || 'Google authentication encountered an error.');
    } finally {
      setIsGoogleAuthenticating(false);
      setVerificationStep('');
    }
  };

  const handleCustomSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !email.includes('@')) {
      setError('Please enter a valid email address (e.g. name@domain.com).');
      return;
    }
    if (!password) {
      setError('Password or App Password is required to authenticate mailbox access.');
      return;
    }

    setError('');
    setSuccessMsg('');
    setIsSubmitting(true);
    setVerificationStep('Conducting TLS connection and IMAP authentication check...');

    try {
      const res = await api.authenticateCustomMailbox({
        email: email.trim(),
        password,
        displayName: displayName.trim() || undefined,
        organization: organization.trim() || undefined,
        imapHost: customImapHost.trim() || undefined,
        imapPort: customImapPort || undefined,
        smtpHost: customSmtpHost.trim() || undefined,
        smtpPort: customSmtpPort || undefined,
      });

      if (res.success && res.account) {
        setSuccessMsg('Mailbox verified! Initializing post-quantum vault...');
        await onSignIn(res.account.email, displayName.trim(), res.account.provider);
        if (onClose) onClose();
      } else {
        setError(res.message || 'Authentication check failed. Please verify credentials or server settings.');
      }
    } catch (err: any) {
      setError(err?.message || 'Authentication verification encountered a network error.');
    } finally {
      setIsSubmitting(false);
      setVerificationStep('');
    }
  };

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/65 backdrop-blur-md">
        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: 12 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: 12 }}
          transition={{ duration: 0.22 }}
          className="w-full max-w-lg bg-white dark:bg-[#141B2D] rounded-3xl shadow-2xl border border-gray-200 dark:border-gray-800 overflow-hidden flex flex-col max-h-[92vh]"
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

            <div className="w-13 h-13 rounded-2xl bg-gradient-to-tr from-[#0B57D0] to-[#4F46E5] flex items-center justify-center shadow-lg shadow-blue-500/25 mb-2.5">
              <ShieldCheck className="w-7 h-7 text-white" />
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
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 max-w-sm">
              Zero-Trust Post-Quantum Secure Mailbox with Live Server Authentication.
            </p>
          </div>

          <div className="p-6 space-y-5 overflow-y-auto">
            {/* Error banner */}
            {error && (
              <div className="p-3.5 rounded-2xl bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/60 text-xs text-red-600 dark:text-red-400 flex items-start space-x-2">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <div className="leading-relaxed">{error}</div>
              </div>
            )}

            {/* Success banner */}
            {successMsg && (
              <div className="p-3.5 rounded-2xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-900/60 text-xs text-emerald-700 dark:text-emerald-400 flex items-start space-x-2">
                <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
                <div className="leading-relaxed">{successMsg}</div>
              </div>
            )}

            {/* 1. ONE-CLICK SIGN IN WITH GOOGLE */}
            <div className="space-y-2">
              <button
                type="button"
                onClick={handleGoogleAuth}
                disabled={isGoogleAuthenticating || isSubmitting}
                className="w-full py-3.5 px-4 rounded-2xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#0E1526] hover:bg-gray-50 dark:hover:bg-[#1A233A] text-gray-800 dark:text-white font-semibold text-sm shadow-sm hover:shadow transition-all flex items-center justify-center space-x-3 disabled:opacity-50"
              >
                {isGoogleAuthenticating ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin text-blue-600" />
                    <span>{verificationStep || 'Authorizing in browser...'}</span>
                  </>
                ) : (
                  <>
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
            </div>

            {/* DIVIDER */}
            <div className="relative flex py-1 items-center">
              <div className="flex-grow border-t border-gray-200 dark:border-gray-800"></div>
              <span className="flex-shrink mx-3 text-xs text-gray-400 dark:text-gray-500 uppercase font-semibold tracking-wider">
                Or Authenticate Custom Mailbox
              </span>
              <div className="flex-grow border-t border-gray-200 dark:border-gray-800"></div>
            </div>

            {/* 2. AUTHENTICATED CUSTOM MAILBOX FORM */}
            <form onSubmit={handleCustomSubmit} className="space-y-4">
              {/* Email Address */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-xs font-semibold text-gray-700 dark:text-gray-300">
                    Email Address <span className="text-red-500">*</span>
                  </label>
                  {providerInfo && (
                    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${providerInfo.badgeColor}`}>
                      {providerInfo.name}
                    </span>
                  )}
                </div>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-gray-400">
                    <Mail className="w-4 h-4" />
                  </div>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="user@outlook.com, user@gmail.com, or user@company.com"
                    required
                    className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-gray-50/50 dark:bg-[#0A0E17] text-sm text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 transition-all"
                  />
                </div>
              </div>

              {/* Password / App Password */}
              <div>
                <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1.5">
                  Password / App Password <span className="text-red-500">*</span>
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-gray-400">
                    <Lock className="w-4 h-4" />
                  </div>
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Mail password or 16-character App Password"
                    required
                    className="w-full pl-10 pr-10 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-gray-50/50 dark:bg-[#0A0E17] text-sm text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 transition-all"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                    title={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>

                {providerInfo && (
                  <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-1.5 leading-relaxed">
                    💡 {providerInfo.note}
                  </p>
                )}
              </div>

              {/* Display Name */}
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

              {/* Advanced Server Settings Accordion */}
              <div className="border border-gray-200 dark:border-gray-800 rounded-2xl overflow-hidden">
                <button
                  type="button"
                  onClick={() => setShowAdvancedServer(!showAdvancedServer)}
                  className="w-full px-4 py-2.5 bg-gray-50/70 dark:bg-gray-900/40 flex items-center justify-between text-xs font-semibold text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-900 transition-colors"
                >
                  <div className="flex items-center space-x-2">
                    <Server className="w-3.5 h-3.5 text-blue-500" />
                    <span>Server &amp; Port Settings</span>
                    {providerInfo && (
                      <span className="text-[10px] text-gray-400 font-normal">
                        ({providerInfo.defaultImap}:993)
                      </span>
                    )}
                  </div>
                  {showAdvancedServer ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                </button>

                {showAdvancedServer && (
                  <div className="p-4 space-y-3 bg-white dark:bg-[#0B101C] border-t border-gray-200 dark:border-gray-800">
                    <div className="grid grid-cols-3 gap-2">
                      <div className="col-span-2">
                        <label className="block text-[11px] font-semibold text-gray-600 dark:text-gray-400 mb-1">
                          IMAP Host
                        </label>
                        <input
                          type="text"
                          value={customImapHost}
                          onChange={(e) => setCustomImapHost(e.target.value)}
                          placeholder={providerInfo?.defaultImap || 'imap.domain.com'}
                          className="w-full px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-700 bg-gray-50/50 dark:bg-[#070B13] text-xs text-gray-900 dark:text-white"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] font-semibold text-gray-600 dark:text-gray-400 mb-1">
                          IMAP Port
                        </label>
                        <input
                          type="number"
                          value={customImapPort}
                          onChange={(e) => setCustomImapPort(Number(e.target.value))}
                          className="w-full px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-700 bg-gray-50/50 dark:bg-[#070B13] text-xs text-gray-900 dark:text-white"
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-3 gap-2">
                      <div className="col-span-2">
                        <label className="block text-[11px] font-semibold text-gray-600 dark:text-gray-400 mb-1">
                          SMTP Host
                        </label>
                        <input
                          type="text"
                          value={customSmtpHost}
                          onChange={(e) => setCustomSmtpHost(e.target.value)}
                          placeholder={providerInfo?.defaultSmtp || 'smtp.domain.com'}
                          className="w-full px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-700 bg-gray-50/50 dark:bg-[#070B13] text-xs text-gray-900 dark:text-white"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] font-semibold text-gray-600 dark:text-gray-400 mb-1">
                          SMTP Port
                        </label>
                        <input
                          type="number"
                          value={customSmtpPort}
                          onChange={(e) => setCustomSmtpPort(Number(e.target.value))}
                          className="w-full px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-700 bg-gray-50/50 dark:bg-[#070B13] text-xs text-gray-900 dark:text-white"
                        />
                      </div>
                    </div>

                    <p className="text-[10px] text-gray-400">
                      TLS encryption is enforced for all inbound and outbound sockets.
                    </p>
                  </div>
                )}
              </div>

              {/* Security info card */}
              <div className="p-3 rounded-2xl bg-blue-50/60 dark:bg-blue-950/30 border border-blue-100 dark:border-blue-900/40 flex items-start space-x-2.5">
                <KeyRound className="w-4 h-4 text-blue-600 dark:text-blue-400 shrink-0 mt-0.5" />
                <div className="text-[11px] text-blue-800 dark:text-blue-300 leading-relaxed">
                  A live TLS security handshake validates server access before generating local <b>NIST FIPS 203 (ML-KEM-768)</b> &amp; <b>FIPS 204 (ML-DSA-65)</b> keypairs.
                </div>
              </div>

              {/* Submit button */}
              <button
                type="submit"
                disabled={isSubmitting || isGoogleAuthenticating}
                className="w-full py-3.5 rounded-2xl bg-[#0B57D0] hover:bg-[#0842A0] text-white font-semibold text-sm shadow-md hover:shadow-lg transition-all disabled:opacity-50 flex items-center justify-center space-x-2"
              >
                {isSubmitting ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    <span>{verificationStep || 'Authenticating Mailbox...'}</span>
                  </>
                ) : (
                  <>
                    <ShieldCheck className="w-4 h-4" />
                    <span>Authenticate &amp; Connect Mailbox</span>
                  </>
                )}
              </button>
            </form>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
};
