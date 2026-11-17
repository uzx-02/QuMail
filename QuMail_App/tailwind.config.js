/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./App.{js,jsx,ts,tsx}", "./src/**/*.{js,jsx,ts,tsx}"],
  presets: [require("nativewind/preset")],
  theme: {
    extend: {
      colors: {
        midnight: {
          bg: '#0A0D14',
          card: '#121722',
          border: '#1F293D',
          hover: '#192231',
          accent: '#00F0FF',
          accentSecondary: '#7928CA',
          text: '#F3F4F6',
          muted: '#9CA3AF',
        },
      },
    },
  },
  plugins: [],
};
