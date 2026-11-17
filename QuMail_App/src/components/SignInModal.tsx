import React, { useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
  Alert,
  ScrollView,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Shield, Fingerprint, Lock, KeyRound, CheckCircle2, Mail, ArrowLeft, Eye, EyeOff } from 'lucide-react-native';
import { LanguageOption } from '../types';
import { t } from '../lib/i18n';

interface SignInModalProps {
  visible: boolean;
  isInitialized: boolean;
  forceFreshSignIn?: boolean;
  onToggleFreshSignIn?: (fresh: boolean) => void;
  onGoogleSignIn: () => Promise<void>;
  onBiometricUnlock: () => Promise<boolean>;
  onPinUnlock: (pin: string) => Promise<boolean>;
  onAppPasswordSignIn: (email: string, appPassword: string) => Promise<void>;
  language?: LanguageOption;
}

export const SignInModal: React.FC<SignInModalProps> = ({
  visible,
  isInitialized,
  forceFreshSignIn,
  onToggleFreshSignIn,
  onGoogleSignIn,
  onBiometricUnlock,
  onPinUnlock,
  onAppPasswordSignIn,
  language = 'en',
}) => {
  const insets = useSafeAreaInsets();
  const [loading, setLoading] = useState(false);
  const [pin, setPin] = useState('');
  const [showPinInput, setShowPinInput] = useState(false);
  const [internalForceFresh, setInternalForceFresh] = useState(false);
  const effectiveForceFresh = forceFreshSignIn !== undefined ? forceFreshSignIn : internalForceFresh;
  const setForceFreshSignIn = (val: boolean) => {
    setInternalForceFresh(val);
    onToggleFreshSignIn?.(val);
  };

  // App Password Mode
  const [showAppPasswordMode, setShowAppPasswordMode] = useState(false);
  const [appEmail, setAppEmail] = useState('');
  const [appPassword, setAppPassword] = useState('');
  const [showAppPassEye, setShowAppPassEye] = useState(false);

  if (!visible) return null;

  const showLockedView = isInitialized && !effectiveForceFresh;

  const handleBiometrics = async () => {
    setLoading(true);
    try {
      const ok = await onBiometricUnlock();
      if (!ok) {
        Alert.alert('Unlock Required', 'Please use your fingerprint, face unlock, or device PIN.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handlePin = async () => {
    if (pin.length < 4) {
      Alert.alert('Security PIN', 'Please enter your 4+ digit PIN.');
      return;
    }
    setLoading(true);
    try {
      const ok = await onPinUnlock(pin);
      if (!ok) {
        Alert.alert('Incorrect PIN', 'The PIN entered does not match.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleGoogle = async () => {
    setLoading(true);
    try {
      await onGoogleSignIn();
    } finally {
      setLoading(false);
    }
  };

  const handleConnectWithAppPassword = async () => {
    if (!appEmail.trim() || !appPassword.trim()) {
      Alert.alert('Account Setup', 'Please enter your email and 16-character App Password.');
      return;
    }
    setLoading(true);
    try {
      await onAppPasswordSignIn(appEmail.trim(), appPassword.trim());
      Alert.alert('Account Connected', `Successfully connected ${appEmail} with post-quantum keys.`);
    } catch (err: any) {
      Alert.alert('Connection Failed', err?.message || 'Could not connect with provided credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <View
      style={{
        flex: 1,
        width: '100%',
        height: '100%',
        backgroundColor: '#020617',
        alignItems: 'center',
        justifyContent: 'center',
        paddingHorizontal: 20,
        paddingTop: insets.top,
        paddingBottom: insets.bottom,
      }}
    >
      {/* Background glow */}
      <View
        style={{
          position: 'absolute',
          width: 320,
          height: 320,
          borderRadius: 160,
          backgroundColor: 'rgba(16, 185, 129, 0.08)',
        }}
      />

      {/* Brand Icon */}
      <View
        style={{
          width: 76,
          height: 76,
          borderRadius: 22,
          backgroundColor: 'rgba(5, 46, 22, 0.8)',
          borderWidth: 1,
          borderColor: 'rgba(16, 185, 129, 0.35)',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: 14,
          elevation: 8,
        }}
      >
        <Shield size={40} color="#10b981" />
      </View>

      <Text
        style={{
          fontSize: 22,
          fontWeight: '900',
          color: '#ffffff',
          letterSpacing: 0.5,
          marginBottom: 4,
          textAlign: 'center',
        }}
      >
        QuMail
      </Text>
      <Text
        style={{
          fontSize: 12,
          color: '#34d399',
          fontWeight: '600',
          letterSpacing: 0.5,
          marginBottom: 20,
          textAlign: 'center',
        }}
      >
        {t('about_tagline', language)}
      </Text>

      {/* Main Container Card */}
      <View
        style={{
          width: '100%',
          maxWidth: 380,
          padding: 20,
          borderRadius: 20,
          backgroundColor: '#090d16',
          borderWidth: 1,
          borderColor: '#1e293b',
          elevation: 6,
        }}
      >
        {showLockedView ? (
          <>
            <Text style={{ fontSize: 15, fontWeight: '700', color: '#ffffff', marginBottom: 6, textAlign: 'center' }}>
              {t('mailbox_locked', language) || 'Mailbox Locked'}
            </Text>
            <Text style={{ fontSize: 11, color: '#94a3b8', textAlign: 'center', marginBottom: 18, lineHeight: 16 }}>
              Your post-quantum keys are securely protected on this device. Unlock with your biometric scan or PIN to view your inbox.
            </Text>

            {/* Biometric Unlock Trigger */}
            <TouchableOpacity
              onPress={handleBiometrics}
              disabled={loading}
              activeOpacity={0.8}
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                justifyContent: 'center',
                paddingVertical: 13,
                borderRadius: 14,
                backgroundColor: '#059669',
                marginBottom: 10,
              }}
            >
              {loading ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <>
                  <Fingerprint size={20} color="#fff" />
                  <Text style={{ fontSize: 13, fontWeight: '700', color: '#ffffff', marginLeft: 8 }}>
                    {t('unlock_button', language) || 'Unlock with Biometrics'}
                  </Text>
                </>
              )}
            </TouchableOpacity>

            {/* PIN Fallback Toggle */}
            {!showPinInput ? (
              <TouchableOpacity
                onPress={() => setShowPinInput(true)}
                style={{ paddingVertical: 8, alignItems: 'center', justifyContent: 'center' }}
              >
                <Text style={{ fontSize: 11, color: '#94a3b8', fontWeight: '500' }}>
                  Use Security PIN instead →
                </Text>
              </TouchableOpacity>
            ) : (
              <View style={{ marginTop: 6 }}>
                <View
                  style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    backgroundColor: '#020617',
                    borderRadius: 12,
                    borderWidth: 1,
                    borderColor: '#1e293b',
                    paddingHorizontal: 12,
                    paddingVertical: 8,
                    marginBottom: 8,
                  }}
                >
                  <KeyRound size={16} color="#64748b" />
                  <TextInput
                    placeholder="Enter Security PIN"
                    placeholderTextColor="#64748b"
                    value={pin}
                    onChangeText={setPin}
                    secureTextEntry
                    keyboardType="numeric"
                    style={{ flex: 1, marginLeft: 8, fontSize: 13, color: '#ffffff' }}
                  />
                </View>
                <TouchableOpacity
                  onPress={handlePin}
                  disabled={loading}
                  style={{
                    paddingVertical: 10,
                    backgroundColor: '#1e293b',
                    borderRadius: 12,
                    alignItems: 'center',
                    borderWidth: 1,
                    borderColor: '#334155',
                  }}
                >
                  <Text style={{ fontSize: 12, fontWeight: '700', color: '#ffffff' }}>Unlock with PIN</Text>
                </TouchableOpacity>
              </View>
            )}

            {/* Switch Account Button */}
            <TouchableOpacity
              onPress={() => setForceFreshSignIn(true)}
              style={{
                marginTop: 14,
                paddingVertical: 10,
                borderRadius: 12,
                borderWidth: 1,
                borderColor: '#1e293b',
                backgroundColor: 'rgba(30, 41, 59, 0.4)',
                alignItems: 'center',
              }}
            >
              <Text style={{ fontSize: 11, fontWeight: '700', color: '#38bdf8' }}>
                ⇄ {t('switch_account', language)} / Sign in to another account
              </Text>
            </TouchableOpacity>
          </>
        ) : (
          <>
            {isInitialized && (
              <TouchableOpacity
                onPress={() => setForceFreshSignIn(false)}
                style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 12 }}
              >
                <ArrowLeft size={14} color="#94a3b8" />
                <Text style={{ fontSize: 11, color: '#94a3b8', marginLeft: 6 }}>
                  Back to Locked Mailbox
                </Text>
              </TouchableOpacity>
            )}

            <Text style={{ fontSize: 15, fontWeight: '700', color: '#ffffff', marginBottom: 4, textAlign: 'center' }}>
              {t('active_mailbox_identity', language)}
            </Text>
            <Text style={{ fontSize: 11, color: '#94a3b8', textAlign: 'center', marginBottom: 14, lineHeight: 16 }}>
              Connect your account with on-device post-quantum encryption.
            </Text>

            {/* Mode 1: Main Sign-In Buttons */}
            {!showAppPasswordMode && (
              <>
                <TouchableOpacity
                  onPress={handleGoogle}
                  disabled={loading}
                  activeOpacity={0.8}
                  style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    justifyContent: 'center',
                    paddingVertical: 12,
                    borderRadius: 14,
                    backgroundColor: '#059669',
                    marginBottom: 10,
                  }}
                >
                  {loading ? (
                    <ActivityIndicator color="#fff" />
                  ) : (
                    <>
                      <Shield size={18} color="#fff" />
                      <Text style={{ fontSize: 13, fontWeight: '700', color: '#ffffff', marginLeft: 8 }}>
                        {t('sign_in_with_google', language)}
                      </Text>
                    </>
                  )}
                </TouchableOpacity>

                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', marginBottom: 12 }}>
                  <CheckCircle2 size={12} color="#10b981" />
                  <Text style={{ fontSize: 10, color: '#10b981', marginLeft: 6, fontWeight: '600' }}>
                    OAuth 2.0 PKCE • On-Device Cryptography
                  </Text>
                </View>

                {/* Option 2: Connect with App Password */}
                <TouchableOpacity
                  onPress={() => setShowAppPasswordMode(true)}
                  style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    justifyContent: 'center',
                    paddingVertical: 11,
                    borderRadius: 14,
                    borderWidth: 1,
                    borderColor: '#334155',
                    backgroundColor: '#1e293b',
                    marginBottom: 10,
                  }}
                >
                  <Mail size={16} color="#38bdf8" />
                  <Text style={{ fontSize: 12, fontWeight: '700', color: '#ffffff', marginLeft: 8 }}>
                    Connect with App Password
                  </Text>
                </TouchableOpacity>
              </>
            )}

            {/* Mode 2: App Password Form */}
            {showAppPasswordMode && (
              <View style={{ gap: 8 }}>
                <TouchableOpacity
                  onPress={() => setShowAppPasswordMode(false)}
                  style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 4 }}
                >
                  <ArrowLeft size={13} color="#94a3b8" />
                  <Text style={{ fontSize: 11, color: '#94a3b8', marginLeft: 4 }}>Back</Text>
                </TouchableOpacity>

                <Text style={{ fontSize: 11, fontWeight: '600', color: '#cbd5e1' }}>
                  Email Address:
                </Text>
                <TextInput
                  placeholder="you@gmail.com or you@company.com"
                  placeholderTextColor="#475569"
                  value={appEmail}
                  onChangeText={setAppEmail}
                  autoCapitalize="none"
                  keyboardType="email-address"
                  style={{
                    backgroundColor: '#020617',
                    borderRadius: 12,
                    borderWidth: 1,
                    borderColor: '#1e293b',
                    paddingHorizontal: 12,
                    paddingVertical: 8,
                    fontSize: 12,
                    color: '#ffffff',
                  }}
                />

                <Text style={{ fontSize: 11, fontWeight: '600', color: '#cbd5e1', marginTop: 4 }}>
                  16-Character App Password:
                </Text>
                <View
                  style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    backgroundColor: '#020617',
                    borderRadius: 12,
                    borderWidth: 1,
                    borderColor: '#1e293b',
                    paddingHorizontal: 12,
                  }}
                >
                  <TextInput
                    placeholder="abcd efgh ijkl mnop"
                    placeholderTextColor="#475569"
                    value={appPassword}
                    onChangeText={setAppPassword}
                    secureTextEntry={!showAppPassEye}
                    style={{
                      flex: 1,
                      paddingVertical: 8,
                      fontSize: 12,
                      color: '#ffffff',
                      fontFamily: 'monospace',
                    }}
                  />
                  <TouchableOpacity onPress={() => setShowAppPassEye(!showAppPassEye)}>
                    {showAppPassEye ? <EyeOff size={16} color="#94a3b8" /> : <Eye size={16} color="#94a3b8" />}
                  </TouchableOpacity>
                </View>

                <TouchableOpacity
                  onPress={handleConnectWithAppPassword}
                  disabled={loading}
                  style={{
                    marginTop: 8,
                    paddingVertical: 12,
                    backgroundColor: '#059669',
                    borderRadius: 12,
                    alignItems: 'center',
                  }}
                >
                  <Text style={{ fontSize: 12, fontWeight: '700', color: '#ffffff' }}>
                    Connect & Initialize Vault
                  </Text>
                </TouchableOpacity>
              </View>
            )}
          </>
        )}
      </View>

      <Text style={{ fontSize: 10, color: '#64748b', marginTop: 20, textAlign: 'center' }}>
        QuMail Mobile • NIST FIPS 203 / 204 On-Device Cryptography • 16 KB ELF
      </Text>
    </View>
  );
};
