/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#050505",
        chatSurface: "#0A0A0A",
        aiMessage: "#171717",
        userMessage: "#4F46E5",
        textPrimary: "#FAFAFA",
        textSecondary: "#A3A3A3",
      },
      fontFamily: {
        sans: ['Inter', 'Satoshi', 'system-ui', '-apple-system', 'sans-serif'],
      },
      animation: {
        'fade-in': 'fadeIn 0.3s cubic-bezier(0.4, 0, 0.2, 1) forwards',
        'slide-up': 'slideUp 0.3s cubic-bezier(0.4, 0, 0.2, 1) forwards',
        'bounce-custom': 'bounceCustom 1.4s infinite ease-in-out both',
        'shimmer': 'shimmer 1.5s infinite linear',
        'orb-glow': 'orbGlow 2s infinite alternate ease-in-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(16px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        bounceCustom: {
          '0%, 80%, 100%': { transform: 'scale(0)', opacity: '0.3' },
          '40%': { transform: 'scale(1)', opacity: '1' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        orbGlow: {
          '0%': { transform: 'scale(0.9)', opacity: '0.7', boxShadow: '0 0 8px #FAFAFA, 0 0 15px rgba(250, 250, 250, 0.3)' },
          '100%': { transform: 'scale(1.15)', opacity: '1', boxShadow: '0 0 14px #FAFAFA, 0 0 28px rgba(250, 250, 250, 0.6)' },
        }
      }
    },
  },
  plugins: [],
}
