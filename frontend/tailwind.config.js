/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        plum: {
          50:  '#F4F1FF',
          100: '#EBE5FF',
          200: '#D6CCFF',
          300: '#B8A9FF',
          400: '#9B82FD',
          500: '#7C5CFC',
          600: '#6540F0',
          700: '#5230D6',
          800: '#3F22AD',
          900: '#2D1B7A',
          950: '#170D42',
        },
      },
      backgroundImage: {
        'plum-gradient': 'linear-gradient(135deg, #2D1B7A 0%, #170D42 100%)',
        'plum-card': 'linear-gradient(180deg, #1D1840 0%, #130E32 100%)',
      },
      keyframes: {
        'node-glow': {
          '0%, 100%': { boxShadow: '0 0 4px 0 rgba(124,92,252,0.4)' },
          '50%': { boxShadow: '0 0 18px 6px rgba(124,92,252,0.7)' },
        },
        'fade-in': {
          from: { opacity: 0, transform: 'translateY(4px)' },
          to:   { opacity: 1, transform: 'translateY(0)' },
        },
      },
      animation: {
        'node-glow': 'node-glow 1.2s ease-in-out infinite',
        'fade-in': 'fade-in 0.25s ease-out both',
      },
    },
  },
  plugins: [],
}
