/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        gmail: {
          bg: '#F6F8FC',
          surface: '#FFFFFF',
          hover: '#F2F6FC',
          selected: '#D3E3FD',
          primary: '#0B57D0',
          primaryHover: '#0842A0',
          compose: '#C2E7FF',
          composeHover: '#B3DCF5',
          text: '#202124',
          textMuted: '#5F6368',
          textSubtle: '#80868B',
          border: '#E0E3E7',
          borderSubtle: '#F2F2F2',
        },
        quantum: {
          secure: '#137333',
          secureBg: '#E6F4EA',
          caution: '#B06000',
          cautionBg: '#FEF7E0',
          alert: '#C5221F',
          alertBg: '#FCE8E6',
          brand: '#0B57D0',
          glow: '#C2E7FF',
        },
        dark: {
          bg: '#0A0E17',
          sidebar: '#111726',
          surface: '#161F33',
          card: '#1C2740',
          cardHover: '#243252',
          cardSelected: '#2C3D63',
          border: '#2A3B5F',
          borderSubtle: '#1F2C47',
          text: '#F1F5F9',
          textMuted: '#94A3B8',
          accent: '#6366F1',
        }
      },
      fontFamily: {
        sans: ['"Google Sans"', '"Segoe UI"', '-apple-system', 'BlinkMacSystemFont', 'Roboto', 'sans-serif'],
      },
      animation: {
        'shimmer': 'shimmer 2.5s infinite linear',
        'pulse-subtle': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
      keyframes: {
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        }
      }
    },
  },
  plugins: [],
}
