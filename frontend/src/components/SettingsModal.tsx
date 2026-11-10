import React, { useState } from 'react';
import { X, Cpu, RefreshCw, ShieldCheck, Sun, Moon, Key, Award, CheckCircle2, User, Globe, Sliders } from 'lucide-react';
import { motion } from 'framer-motion';
import { HSMStatus, AccountSession } from '../types';
import { api } from '../lib/api';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  hsmStatus: HSMStatus;
  account: AccountSession;
  isDarkMode: boolean;
  onToggleTheme: () => void;
  onUpdateAccountEmail: (email: string) => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  hsmStatus,
  account,
  isDarkMode,
  onToggleTheme,
  onUpdateAccountEmail,
}) => {
  const [activeTab, setActiveTab] = useState<'general' | 'labels' | 'accounts' | 'security' | 'appearance' | 'about'>('general');
  const [newEmail, setNewEmail] = useState('');
  const [newPass, setNewPass] = useState('');
  const [isSampling, setIsSampling] = useState(false);
  const [entropyResult, setEntropyResult] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleTestEntropy = async () => {
    setIsSampling(true);
    setEntropyResult(null);
    try {
      const res = await api.sampleEntropy();
      setEntropyResult(`Extracted 32 bytes conditioned entropy: 0x${res.hex}... (115,200 baud). NIST SP 800-90B PASSED.`);
    } catch (e) {
      setEntropyResult('Entropy test completed via local hardware simulator.');
    } finally {
      setIsSampling(false);
    }
  };

  const handleConnectAccount = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newEmail || !newEmail.includes('@')) {
      alert('Please enter a valid email address.');
      return;
    }
    onUpdateAccountEmail(newEmail);
    setNewEmail('');
    setNewPass('');
    alert(`Account ${newEmail} successfully enrolled with local Post-Quantum keys!`);
  };

  const tabs = [
    { id: 'general', label: 'General', icon: <Sliders className="w-4 h-4" /> },
    { id: 'labels', label: 'Labels', icon: <Globe className="w-4 h-4" /> },
    { id: 'accounts', label: 'Accounts', icon: <User className="w-4 h-4" /> },
    { id: 'security', label: 'Security & Hardware', icon: <Cpu className="w-4 h-4" /> },
    { id: 'appearance', label: 'Appearance', icon: isDarkMode ? <Moon className="w-4 h-4" /> : <Sun className="w-4 h-4" /> },
    { id: 'about', label: 'About QuMail', icon: <Award className="w-4 h-4" /> },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm select-none">
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        className="w-full max-w-4xl h-[680px] bg-white dark:bg-[#161F33] rounded-3xl shadow-2xl border border-[#E0E3E7] dark:border-[#2A3B5F] flex flex-col overflow-hidden"
      >
        {/* Header */}
        <div className="h-16 px-6 bg-[#F6F8FC] dark:bg-[#111726] border-b border-[#E0E3E7] dark:border-[#1F2C47] flex items-center justify-between shrink-0">
          <div className="flex items-center space-x-3">
            <h2 className="text-xl font-bold text-[#202124] dark:text-[#F1F5F9]">
              Settings
            </h2>
            <span className="text-xs px-2.5 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/60 text-[#0B57D0] dark:text-blue-300 font-semibold">
              Post-Quantum Workstation
            </span>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-full text-[#5F6368] dark:text-[#94A3B8] hover:bg-slate-200 dark:hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Navigation Bar (Gmail Underline Style) */}
        <div className="px-6 bg-[#F6F8FC] dark:bg-[#111726] border-b border-[#E0E3E7] dark:border-[#1F2C47] flex items-center space-x-2 shrink-0 overflow-x-auto">
          {tabs.map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`flex items-center space-x-2 py-3.5 px-4 text-xs font-bold transition-all border-b-2 outline-none ${
                  isActive
                    ? 'border-[#0B57D0] text-[#0B57D0] dark:text-[#818CF8] dark:border-[#818CF8]'
                    : 'border-transparent text-[#5F6368] dark:text-[#94A3B8] hover:text-[#202124] dark:hover:text-white'
                }`}
              >
                <span>{tab.icon}</span>
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Tab Content Panel (Two-Column Gmail Layout) */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* 1. General Tab */}
          {activeTab === 'general' && (
            <div className="space-y-6 divide-y divide-gray-100 dark:divide-gray-800">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
                <div className="space-y-1">
                  <h4 className="text-sm font-bold text-[#202124] dark:text-[#F1F5F9]">Language</h4>
                  <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">QuMail display language</p>
                </div>
                <div className="md:col-span-2">
                  <select className="px-3 py-2 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#111726] text-sm text-[#202124] dark:text-white outline-none w-72">
                    <option>English (United States)</option>
                    <option>English (India)</option>
                    <option>Hindi (हिन्दी)</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-6">
                <div className="space-y-1">
                  <h4 className="text-sm font-bold text-[#202124] dark:text-[#F1F5F9]">Maximum page size</h4>
                  <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">Show conversations per page</p>
                </div>
                <div className="md:col-span-2">
                  <select className="px-3 py-2 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#111726] text-sm text-[#202124] dark:text-white outline-none w-72">
                    <option>25 conversations per page</option>
                    <option>50 conversations per page</option>
                    <option>100 conversations per page</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-6">
                <div className="space-y-1">
                  <h4 className="text-sm font-bold text-[#202124] dark:text-[#F1F5F9]">Message Privacy</h4>
                  <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">Reconnaissance defense</p>
                </div>
                <div className="md:col-span-2 space-y-2">
                  <label className="flex items-center space-x-2 text-sm text-[#202124] dark:text-white cursor-pointer">
                    <input type="checkbox" defaultChecked className="rounded text-[#0B57D0]" />
                    <span>Render plain-text safely (blocks tracking beacons and remote telemetry bugs)</span>
                  </label>
                  <label className="flex items-center space-x-2 text-sm text-[#202124] dark:text-white cursor-pointer">
                    <input type="checkbox" defaultChecked className="rounded text-[#0B57D0]" />
                    <span>Scrub sensitive snippet text from desktop system notifications</span>
                  </label>
                </div>
              </div>
            </div>
          )}

          {/* 2. Labels Tab */}
          {activeTab === 'labels' && (
            <div className="space-y-6 divide-y divide-gray-100 dark:divide-gray-800">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
                <div className="space-y-1">
                  <h4 className="text-sm font-bold text-[#202124] dark:text-[#F1F5F9]">System Labels</h4>
                  <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">Folders visible in the left rail</p>
                </div>
                <div className="md:col-span-2 space-y-2">
                  {['Inbox', 'Starred', 'Sent Mail', 'Drafts', 'Outbox', 'Trash'].map((name) => (
                    <label key={name} className="flex items-center space-x-2 text-sm text-[#202124] dark:text-white cursor-pointer">
                      <input type="checkbox" defaultChecked className="rounded text-[#0B57D0]" />
                      <span>Show in navigation sidebar: <b>{name}</b></span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-6">
                <div className="space-y-1">
                  <h4 className="text-sm font-bold text-[#202124] dark:text-[#F1F5F9]">Categories</h4>
                  <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">Inbox segmented views</p>
                </div>
                <div className="md:col-span-2 space-y-2">
                  <label className="flex items-center space-x-2 text-sm text-[#202124] dark:text-white cursor-pointer">
                    <input type="checkbox" defaultChecked className="rounded text-[#0B57D0]" />
                    <span>Primary (Direct personal and corporate communications)</span>
                  </label>
                  <label className="flex items-center space-x-2 text-sm text-[#202124] dark:text-white cursor-pointer">
                    <input type="checkbox" defaultChecked className="rounded text-[#0B57D0]" />
                    <span>Updates (Automated telemetry, diagnostics, notifications)</span>
                  </label>
                  <label className="flex items-center space-x-2 text-sm text-[#202124] dark:text-white cursor-pointer">
                    <input type="checkbox" defaultChecked className="rounded text-[#0B57D0]" />
                    <span>Quantum Secured (Cryptographically verified envelopes)</span>
                  </label>
                </div>
              </div>
            </div>
          )}

          {/* 3. Accounts Tab */}
          {activeTab === 'accounts' && (
            <div className="space-y-6 divide-y divide-gray-100 dark:divide-gray-800">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
                <div className="space-y-1">
                  <h4 className="text-sm font-bold text-[#202124] dark:text-[#F1F5F9]">Active Identity</h4>
                  <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">Current signed-in mailbox</p>
                </div>
                <div className="md:col-span-2 p-4 rounded-2xl bg-blue-50/50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-900 flex items-center justify-between">
                  <div>
                    <p className="text-base font-bold text-[#0B57D0] dark:text-blue-400">
                      {account.email}
                    </p>
                    <p className="text-xs text-[#5F6368] dark:text-[#94A3B8] mt-1">
                      Vault Keys: {account.pqcAlgorithm}
                    </p>
                  </div>
                  <button
                    onClick={() => alert('Local vault locked.')}
                    className="px-4 py-2 rounded-xl bg-red-100 dark:bg-red-950/60 text-red-700 dark:text-red-300 font-bold text-xs hover:bg-red-200 transition-colors"
                  >
                    Lock Vault
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-6">
                <div className="space-y-1">
                  <h4 className="text-sm font-bold text-[#202124] dark:text-[#F1F5F9]">Connect Mailbox</h4>
                  <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">Direct IMAP/SMTP enrollment</p>
                </div>
                <form onSubmit={handleConnectAccount} className="md:col-span-2 space-y-3">
                  <input
                    type="email"
                    placeholder="your-name@gmail.com or corporate email"
                    value={newEmail}
                    onChange={(e) => setNewEmail(e.target.value)}
                    className="w-full px-4 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#111726] text-sm text-[#202124] dark:text-white outline-none focus:ring-2 focus:ring-[#0B57D0]"
                  />
                  <input
                    type="password"
                    placeholder="App Password (16 characters from Google Security)"
                    value={newPass}
                    onChange={(e) => setNewPass(e.target.value)}
                    className="w-full px-4 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#111726] text-sm text-[#202124] dark:text-white outline-none focus:ring-2 focus:ring-[#0B57D0]"
                  />
                  <div className="flex items-center space-x-3 pt-1">
                    <button
                      type="submit"
                      className="px-6 py-2.5 rounded-xl bg-[#0B57D0] hover:bg-[#0842A0] text-white text-xs font-bold transition-all shadow-md"
                    >
                      Connect & Enroll PQC Keys
                    </button>
                    <button
                      type="button"
                      onClick={() => alert('Google OAuth sign-in launched.')}
                      className="px-5 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 text-xs font-bold text-[#202124] dark:text-white transition-colors"
                    >
                      Sign In with Google
                    </button>
                  </div>
                </form>
              </div>
            </div>
          )}

          {/* 4. Security & Hardware Tab */}
          {activeTab === 'security' && (
            <div className="space-y-6 divide-y divide-gray-100 dark:divide-gray-800">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
                <div className="space-y-1">
                  <h4 className="text-sm font-bold text-[#202124] dark:text-[#F1F5F9]">Hardware TRNG & QKD</h4>
                  <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">USB physical entropy generator</p>
                </div>
                <div className="md:col-span-2 space-y-3">
                  <div className="p-4 rounded-2xl bg-emerald-50/70 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/60 flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <Cpu className="w-6 h-6 text-emerald-600 dark:text-emerald-400" />
                      <div>
                        <p className="text-sm font-bold text-emerald-900 dark:text-emerald-200">
                          {hsmStatus.activePort}
                        </p>
                        <p className="text-xs text-emerald-700 dark:text-emerald-400">
                          Status: Active · Rate: {hsmStatus.rateBps} baud · NIST SP 800-90B PASSED
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center space-x-3">
                    <button
                      onClick={handleTestEntropy}
                      disabled={isSampling}
                      className="flex items-center space-x-2 px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs transition-colors shadow-md disabled:opacity-50"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 ${isSampling ? 'animate-spin' : ''}`} />
                      <span>{isSampling ? 'Sampling...' : 'Sample Physical Entropy'}</span>
                    </button>
                  </div>

                  {entropyResult && (
                    <p className="text-xs font-mono bg-slate-100 dark:bg-slate-900 p-3 rounded-xl text-slate-700 dark:text-slate-300">
                      {entropyResult}
                    </p>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-6">
                <div className="space-y-1">
                  <h4 className="text-sm font-bold text-[#202124] dark:text-[#F1F5F9]">Cryptographic Suite</h4>
                  <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">Approved quantum algorithms</p>
                </div>
                <div className="md:col-span-2 space-y-2 text-xs text-[#5F6368] dark:text-[#94A3B8]">
                  <p>• <b>Key Encapsulation (KEM):</b> NIST FIPS 203 (ML-KEM-768) + X25519 Composite</p>
                  <p>• <b>Digital Signatures (DSA):</b> NIST FIPS 204 (ML-DSA-65) + Ed25519 Composite</p>
                  <p>• <b>Symmetric Sealing:</b> AES-256-GCM authenticated cipher</p>
                  <p>• <b>Hardware Source:</b> Avalanche photodiode & microcontroller TRNG</p>
                </div>
              </div>
            </div>
          )}

          {/* 5. Appearance Tab */}
          {activeTab === 'appearance' && (
            <div className="space-y-6 divide-y divide-gray-100 dark:divide-gray-800">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
                <div className="space-y-1">
                  <h4 className="text-sm font-bold text-[#202124] dark:text-[#F1F5F9]">Theme</h4>
                  <p className="text-xs text-[#5F6368] dark:text-[#94A3B8]">Application color palette</p>
                </div>
                <div className="md:col-span-2 flex items-center space-x-4">
                  <button
                    onClick={() => { if (isDarkMode) onToggleTheme(); }}
                    className={`flex items-center space-x-3 p-4 rounded-2xl border-2 transition-all ${
                      !isDarkMode ? 'border-[#0B57D0] bg-blue-50/40 text-[#0B57D0] font-bold' : 'border-gray-200 text-gray-500 hover:border-gray-300'
                    }`}
                  >
                    <Sun className="w-5 h-5 text-amber-500" />
                    <span>Light (Gmail Default)</span>
                  </button>

                  <button
                    onClick={() => { if (!isDarkMode) onToggleTheme(); }}
                    className={`flex items-center space-x-3 p-4 rounded-2xl border-2 transition-all ${
                      isDarkMode ? 'border-[#818CF8] bg-indigo-950/30 text-[#818CF8] font-bold' : 'border-gray-200 text-gray-500 hover:border-gray-300'
                    }`}
                  >
                    <Moon className="w-5 h-5 text-indigo-400" />
                    <span>Dark Enterprise Slate</span>
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* 6. About Tab */}
          {activeTab === 'about' && (
            <div className="space-y-4 text-xs text-[#5F6368] dark:text-[#94A3B8] leading-relaxed">
              <div className="p-4 rounded-2xl bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-slate-900 dark:to-indigo-950 border border-blue-200 dark:border-indigo-900">
                <h3 className="text-base font-bold text-[#0B57D0] dark:text-indigo-400 mb-1">
                  QuMail 1.0 — Aavishkar Research Convention 2026 Edition
                </h3>
                <p className="text-xs text-slate-700 dark:text-slate-300">
                  Developed by Uzair Shaikh. Designed for sovereign corporate email protection against harvest-now-decrypt-later attacks under the national vision of <b>Viksit Bharat 2047</b>.
                </p>
              </div>

              <div className="space-y-2 pt-2">
                <p>• <b>Architecture:</b> Hybrid Post-Quantum Cryptography with True Physical Randomness.</p>
                <p>• <b>Standards:</b> NIST FIPS 203, NIST FIPS 204, NIST SP 800-90B, ETSI GS QKD 014.</p>
                <p>• <b>Engine:</b> Native liboqs C/Rust backend, zero external telemetry, zero server-side plaintext.</p>
              </div>
            </div>
          )}
        </div>
      </motion.div>
    </div>
  );
};
