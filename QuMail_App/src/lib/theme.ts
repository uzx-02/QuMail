import { ThemeMode, AccentColor, FontSizeOption, ListDensityOption } from '../types';

export interface ThemePalette {
  bg: string;
  card: string;
  innerCard: string;
  border: string;
  text: string;
  subtext: string;
  headerBg: string;
  inputBg: string;
  statusBarStyle: 'light' | 'dark';
}

export const THEMES: Record<ThemeMode, ThemePalette> = {
  light: {
    bg: '#f8fafc',
    card: '#ffffff',
    innerCard: '#f1f5f9',
    border: '#e2e8f0',
    text: '#0f172a',
    subtext: '#64748b',
    headerBg: '#ffffff',
    inputBg: '#f1f5f9',
    statusBarStyle: 'dark',
  },
  dark: {
    bg: '#0f172a',
    card: '#1e293b',
    innerCard: '#0f172a',
    border: '#334155',
    text: '#f8fafc',
    subtext: '#94a3b8',
    headerBg: '#1e293b',
    inputBg: '#0f172a',
    statusBarStyle: 'light',
  },
  midnight: {
    bg: '#020617',
    card: '#090d16',
    innerCard: '#020617',
    border: '#1e293b',
    text: '#ffffff',
    subtext: '#64748b',
    headerBg: '#090d16',
    inputBg: '#020617',
    statusBarStyle: 'light',
  },
};

export const ACCENT_COLORS: Record<AccentColor, { primary: string; light: string; border: string }> = {
  emerald: {
    primary: '#10b981',
    light: 'rgba(16, 185, 129, 0.15)',
    border: 'rgba(16, 185, 129, 0.4)',
  },
  blue: {
    primary: '#3b82f6',
    light: 'rgba(59, 130, 246, 0.15)',
    border: 'rgba(59, 130, 246, 0.4)',
  },
  indigo: {
    primary: '#6366f1',
    light: 'rgba(99, 102, 241, 0.15)',
    border: 'rgba(99, 102, 241, 0.4)',
  },
  cyan: {
    primary: '#06b6d4',
    light: 'rgba(6, 182, 212, 0.15)',
    border: 'rgba(6, 182, 212, 0.4)',
  },
  rose: {
    primary: '#f43f5e',
    light: 'rgba(244, 63, 94, 0.15)',
    border: 'rgba(244, 63, 94, 0.4)',
  },
};

export const FONT_SIZE_FACTORS: Record<FontSizeOption, number> = {
  small: 0.9,
  medium: 1.0,
  large: 1.15,
};

export function getTheme(mode: ThemeMode = 'midnight', highContrast: boolean = false): ThemePalette {
  const base = THEMES[mode] || THEMES.midnight;
  if (!highContrast) return base;

  if (mode === 'light') {
    return {
      ...base,
      bg: '#ffffff',
      card: '#ffffff',
      innerCard: '#f8fafc',
      border: '#000000',
      text: '#000000',
      subtext: '#1e293b',
      headerBg: '#ffffff',
      inputBg: '#ffffff',
    };
  }

  return {
    ...base,
    bg: '#000000',
    card: '#0a0a0a',
    innerCard: '#000000',
    border: '#ffffff',
    text: '#ffffff',
    subtext: '#e2e8f0',
    headerBg: '#000000',
    inputBg: '#000000',
  };
}

export function getAccent(color: AccentColor = 'emerald') {
  return ACCENT_COLORS[color] || ACCENT_COLORS.emerald;
}
