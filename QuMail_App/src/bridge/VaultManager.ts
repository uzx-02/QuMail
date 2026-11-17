import * as SecureStore from 'expo-secure-store';
import * as LocalAuthentication from 'expo-local-authentication';
import { cryptoBridge, base64ToUint8Array, uint8ArrayToBase64 } from './CryptoBridge';
import { AccountSession, INITIAL_ACCOUNT } from '../types';

const VAULT_SECRET_KEY = 'qumail_vault_secret_cert_v1';
const VAULT_PUBLIC_KEY = 'qumail_vault_public_cert_v1';
const VAULT_EMAIL_KEY = 'qumail_vault_email_v1';
const VAULT_PIN_HASH_KEY = 'qumail_vault_pin_hash_v1';

export class VaultManager {
  private static instance: VaultManager;
  private currentAccount: AccountSession = { ...INITIAL_ACCOUNT };

  static getInstance(): VaultManager {
    if (!VaultManager.instance) {
      VaultManager.instance = new VaultManager();
    }
    return VaultManager.instance;
  }

  private normalizeEmail(email?: string | null): string {
    return (email || '').trim().toLowerCase();
  }

  private safeKey(email?: string | null): string {
    return this.normalizeEmail(email).replace(/[^a-zA-Z0-9._-]/g, '_');
  }

  async isVaultInitialized(email?: string): Promise<boolean> {
    const norm = this.normalizeEmail(email || this.currentAccount.email || (await this.getStoredEmail()));
    if (norm) {
      const perAccountPub = await SecureStore.getItemAsync(`${VAULT_PUBLIC_KEY}_${this.safeKey(norm)}`);
      if (perAccountPub) return true;
    }
    const pub = await SecureStore.getItemAsync(VAULT_PUBLIC_KEY);
    return !!pub;
  }

  async getPublicCert(email?: string): Promise<string | null> {
    const norm = this.normalizeEmail(email || this.currentAccount.email || (await this.getStoredEmail()));
    if (norm) {
      const perAccountPub = await SecureStore.getItemAsync(`${VAULT_PUBLIC_KEY}_${this.safeKey(norm)}`);
      if (perAccountPub) return perAccountPub;
    }
    return await SecureStore.getItemAsync(VAULT_PUBLIC_KEY);
  }

  async getPublicCertBytes(email?: string): Promise<Uint8Array | null> {
    const pubBase64 = await this.getPublicCert(email);
    if (!pubBase64) return null;
    return base64ToUint8Array(pubBase64);
  }

  async getSecretCert(email?: string): Promise<string | null> {
    const norm = this.normalizeEmail(email || this.currentAccount.email || (await this.getStoredEmail()));
    if (norm) {
      const perAccountSec = await SecureStore.getItemAsync(`${VAULT_SECRET_KEY}_${this.safeKey(norm)}`);
      if (perAccountSec) return perAccountSec;
    }
    return await SecureStore.getItemAsync(VAULT_SECRET_KEY);
  }

  async getSecretCertBytes(email?: string): Promise<Uint8Array | null> {
    const secBase64 = await this.getSecretCert(email);
    if (!secBase64) return null;
    return base64ToUint8Array(secBase64);
  }

  async getStoredEmail(): Promise<string | null> {
    return await SecureStore.getItemAsync(VAULT_EMAIL_KEY);
  }

  async initializeIdentity(email: string): Promise<{ publicCertBase64: string }> {
    const normEmail = this.normalizeEmail(email);
    const keySuffix = this.safeKey(normEmail);
    const secKey = `${VAULT_SECRET_KEY}_${keySuffix}`;
    const pubKey = `${VAULT_PUBLIC_KEY}_${keySuffix}`;

    // 1. Check if identity already exists for this account
    let pubBase64 = await SecureStore.getItemAsync(pubKey);
    let secBase64 = await SecureStore.getItemAsync(secKey);

    // Also check global keys if previously stored under this email
    if (!secBase64) {
      const storedEmail = this.normalizeEmail(await SecureStore.getItemAsync(VAULT_EMAIL_KEY));
      if (storedEmail === normEmail) {
        pubBase64 = await SecureStore.getItemAsync(VAULT_PUBLIC_KEY);
        secBase64 = await SecureStore.getItemAsync(VAULT_SECRET_KEY);
      }
    }

    let secretBytes: Uint8Array;
    if (pubBase64 && secBase64) {
      console.log(`Reusing existing verified post-quantum identity for ${normEmail}`);
      secretBytes = base64ToUint8Array(secBase64);
    } else {
      console.log(`Generating fresh post-quantum identity for ${normEmail}`);
      const { publicCert, secretCert } = await cryptoBridge.generateIdentity(normEmail);
      pubBase64 = uint8ArrayToBase64(publicCert);
      secBase64 = uint8ArrayToBase64(secretCert);
      secretBytes = secretCert;

      await SecureStore.setItemAsync(pubKey, pubBase64);
      await SecureStore.setItemAsync(secKey, secBase64, {
        keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK,
      });
    }

    // Always mirror to active pointers for hardware Keystore operations
    await SecureStore.setItemAsync(VAULT_PUBLIC_KEY, pubBase64);
    await SecureStore.setItemAsync(VAULT_SECRET_KEY, secBase64, {
      keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK,
    });
    await SecureStore.setItemAsync(VAULT_EMAIL_KEY, normEmail);

    // Keep active vault unlocked in Rust memory for initial session
    await cryptoBridge.unlockVault(secretBytes);

    this.currentAccount = {
      ...this.currentAccount,
      email: normEmail,
      pqcIdentity: pubBase64.substring(0, 32) + '...',
      isUnlocked: true,
      vaultState: 'ACTIVE',
    };

    return { publicCertBase64: pubBase64 };
  }

  async initializeVault(email: string): Promise<{ publicCertBase64: string }> {
    return this.initializeIdentity(email);
  }

  async unlockWithBiometrics(): Promise<boolean> {
    const hasHardware = await LocalAuthentication.hasHardwareAsync();
    const isEnrolled = await LocalAuthentication.isEnrolledAsync();

    if (hasHardware && isEnrolled) {
      const auth = await LocalAuthentication.authenticateAsync({
        promptMessage: 'Unlock QuMail Quantum-Safe Vault',
        fallbackLabel: 'Enter Device PIN / Password',
        cancelLabel: 'Cancel',
        disableDeviceFallback: false,
      });

      if (!auth.success) {
        return false;
      }
    }

    const secBase64 = await SecureStore.getItemAsync(VAULT_SECRET_KEY);
    if (!secBase64) return false;

    const secretBytes = base64ToUint8Array(secBase64);
    const success = await cryptoBridge.unlockVault(secretBytes);

    if (success) {
      this.currentAccount.isUnlocked = true;
      this.currentAccount.vaultState = 'ACTIVE';
    }
    return success;
  }

  async lockVault(): Promise<void> {
    await cryptoBridge.lockVault();
    this.currentAccount.isUnlocked = false;
    this.currentAccount.vaultState = 'LOCKED';
  }

  async getAccount(): Promise<AccountSession> {
    const unlocked = await cryptoBridge.isVaultUnlocked();
    const email = (await this.getStoredEmail()) || this.currentAccount.email;
    const isInit = await this.isVaultInitialized();

    return {
      ...this.currentAccount,
      email,
      isUnlocked: unlocked,
      vaultState: isInit ? (unlocked ? 'ACTIVE' : 'LOCKED') : 'NOT_INITIALIZED',
    };
  }

  async setPin(pin: string): Promise<void> {
    // Base64-encoded PIN for the UI gate; not a cryptographic control
    await SecureStore.setItemAsync(VAULT_PIN_HASH_KEY, btoa(pin));
    this.currentAccount.hasSecurityPin = true;
  }

  async verifyPin(pin: string): Promise<boolean> {
    const stored = await SecureStore.getItemAsync(VAULT_PIN_HASH_KEY);
    if (!stored) return false;
    if (atob(stored) === pin) {
      const secBase64 = await SecureStore.getItemAsync(VAULT_SECRET_KEY);
      if (secBase64) {
        const secretBytes = base64ToUint8Array(secBase64);
        await cryptoBridge.unlockVault(secretBytes);
        this.currentAccount.isUnlocked = true;
        this.currentAccount.vaultState = 'ACTIVE';
        return true;
      }
    }
    return false;
  }

  async unlockWithPin(pin: string): Promise<boolean> {
    return this.verifyPin(pin);
  }
}

export const vaultManager = VaultManager.getInstance();
