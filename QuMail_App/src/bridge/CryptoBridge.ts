import { NativeModules, Platform } from 'react-native';

export interface CryptoBridge {
  generateIdentity(email: string): Promise<{ publicCert: Uint8Array; secretCert: Uint8Array }>;
  sealMessage(opts: {
    senderSecret: Uint8Array;
    recipientPublics: Uint8Array[];
    plaintext: Uint8Array;
  }): Promise<Uint8Array>;
  openMessage(opts: {
    recipientSecret: Uint8Array;
    senderPublic: Uint8Array;
    envelope: Uint8Array;
  }): Promise<Uint8Array>;
  encryptAttachment(key: Uint8Array, plaintext: Uint8Array): Promise<{ ciphertext: Uint8Array; nonce: Uint8Array }>;
  decryptAttachment(key: Uint8Array, ciphertext: Uint8Array, nonce: Uint8Array): Promise<Uint8Array>;
  unlockVault(secretCert: Uint8Array): Promise<boolean>;
  lockVault(): Promise<void>;
  getVaultPublicCert(): Promise<Uint8Array | null>;
  isVaultUnlocked(): Promise<boolean>;
  directoryProof(secretCert: Uint8Array, message: Uint8Array): Promise<{ verifyingKey: Uint8Array; signature: Uint8Array }>;
}

// Convert helper between base64 and Uint8Array
export function uint8ArrayToBase64(bytes: Uint8Array): string {
  let binary = '';
  const len = bytes.byteLength;
  for (let i = 0; i < len; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

export function base64ToUint8Array(base64: string): Uint8Array {
  const binary = atob(base64);
  const len = binary.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

export function stringToUint8Array(str: string): Uint8Array {
  return new TextEncoder().encode(str);
}

export function uint8ArrayToString(bytes: Uint8Array): string {
  return new TextDecoder().decode(bytes);
}

class NativeCryptoBridge implements CryptoBridge {
  private get nativeModule() {
    return NativeModules.CryptoBridgeModule;
  }

  async generateIdentity(email: string): Promise<{ publicCert: Uint8Array; secretCert: Uint8Array }> {
    if (!this.nativeModule?.generateIdentity) {
      throw new Error('Native QuMail cryptographic engine (libqumail_crypto.so) is not loaded.');
    }
    const res = await this.nativeModule.generateIdentity(email);
    return {
      publicCert: base64ToUint8Array(res.publicCert),
      secretCert: base64ToUint8Array(res.secretCert),
    };
  }

  async sealMessage(opts: {
    senderSecret: Uint8Array;
    recipientPublics: Uint8Array[];
    plaintext: Uint8Array;
  }): Promise<Uint8Array> {
    if (!this.nativeModule?.sealMessage) {
      throw new Error('Native QuMail cryptographic engine (libqumail_crypto.so) is not loaded.');
    }
    const res = await this.nativeModule.sealMessage(
      uint8ArrayToBase64(opts.senderSecret),
      opts.recipientPublics.map(uint8ArrayToBase64),
      uint8ArrayToBase64(opts.plaintext)
    );
    return base64ToUint8Array(res);
  }

  async openMessage(opts: {
    recipientSecret: Uint8Array;
    senderPublic: Uint8Array;
    envelope: Uint8Array;
  }): Promise<Uint8Array> {
    if (!this.nativeModule?.openMessage) {
      throw new Error('Native QuMail cryptographic engine (libqumail_crypto.so) is not loaded.');
    }
    const res = await this.nativeModule.openMessage(
      uint8ArrayToBase64(opts.recipientSecret),
      uint8ArrayToBase64(opts.senderPublic),
      uint8ArrayToBase64(opts.envelope)
    );
    return base64ToUint8Array(res);
  }

  async encryptAttachment(key: Uint8Array, plaintext: Uint8Array): Promise<{ ciphertext: Uint8Array; nonce: Uint8Array }> {
    if (!this.nativeModule?.encryptAttachment) {
      throw new Error('Native QuMail cryptographic engine (libqumail_crypto.so) is not loaded.');
    }
    const res = await this.nativeModule.encryptAttachment(
      uint8ArrayToBase64(key),
      uint8ArrayToBase64(plaintext)
    );
    return {
      ciphertext: base64ToUint8Array(res.ciphertext),
      nonce: base64ToUint8Array(res.nonce),
    };
  }

  async decryptAttachment(key: Uint8Array, ciphertext: Uint8Array, nonce: Uint8Array): Promise<Uint8Array> {
    if (!this.nativeModule?.decryptAttachment) {
      throw new Error('Native QuMail cryptographic engine (libqumail_crypto.so) is not loaded.');
    }
    const res = await this.nativeModule.decryptAttachment(
      uint8ArrayToBase64(key),
      uint8ArrayToBase64(ciphertext),
      uint8ArrayToBase64(nonce)
    );
    return base64ToUint8Array(res);
  }

  async unlockVault(secretCert: Uint8Array): Promise<boolean> {
    if (this.nativeModule?.setVaultSecretCert) {
      return await this.nativeModule.setVaultSecretCert(uint8ArrayToBase64(secretCert));
    }
    return true;
  }

  async lockVault(): Promise<void> {
    if (this.nativeModule?.lockVault) {
      await this.nativeModule.lockVault();
    }
  }

  async getVaultPublicCert(): Promise<Uint8Array | null> {
    if (this.nativeModule?.getVaultPublicCert) {
      const res = await this.nativeModule.getVaultPublicCert();
      return res ? base64ToUint8Array(res) : null;
    }
    return null;
  }

  async isVaultUnlocked(): Promise<boolean> {
    if (this.nativeModule?.isVaultUnlocked) {
      return await this.nativeModule.isVaultUnlocked();
    }
    return false;
  }

  async directoryProof(secretCert: Uint8Array, message: Uint8Array): Promise<{ verifyingKey: Uint8Array; signature: Uint8Array }> {
    if (this.nativeModule?.directoryProof) {
      const res = await this.nativeModule.directoryProof(
        uint8ArrayToBase64(secretCert),
        uint8ArrayToBase64(message)
      );
      return {
        verifyingKey: base64ToUint8Array(res.verifyingKey),
        signature: base64ToUint8Array(res.signature),
      };
    }
    return {
      verifyingKey: new Uint8Array(1952),
      signature: new Uint8Array(3309),
    };
  }
}

export const cryptoBridge: CryptoBridge = new NativeCryptoBridge();
