import { FontFamilyOption, FontSizeOption } from '../types';

export const FONT_FAMILY_STYLE: Record<FontFamilyOption, string> = {
  sans: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  geometric: '"Plus Jakarta Sans", "Inter", "Segoe UI", system-ui, sans-serif',
  serif: 'Georgia, "Merriweather", "Times New Roman", serif',
  mono: 'ui-monospace, "Cascadia Code", "JetBrains Mono", Consolas, monospace',
};

export const FONT_SIZE_STYLE: Record<FontSizeOption, string> = {
  small: '13px',
  medium: '15px',
  large: '17px',
};

