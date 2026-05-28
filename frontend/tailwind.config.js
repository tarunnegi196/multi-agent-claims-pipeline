/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'Arial', 'sans-serif'],
      },
      fontSize: {
        base: ['14px', '20px'],
      },
      colors: {
        /* Dark backgrounds — exact Plum values */
        pdark: {
          darkest: '#11040d',
          dark:    '#1d0716',
          2:       '#2c0b21',
          3:       '#340926',
          4:       '#3a0e2b',
        },
        /* Brand purples — exact Plum values */
        pp: {
          deep:  '#460932',
          mid:   '#570e40',
          btn:   '#7b4067',
          hover: '#733c61',
          muted: '#9e708c',
          light: '#bea0b3',
          pale:  '#d8c5d1',
        },
        /* Light backgrounds — exact Plum values */
        pwarm: {
          DEFAULT: '#fffaf2',
          2:       '#fff8f1',
          3:       '#fffbf7',
          peach:   '#ffebdb',
          blush:   '#eae1e7',
        },
        /* Status — exact Plum values */
        pstatus: {
          red:       '#ff4052',
          'red-dk':  '#e23744',
          'red-dp':  '#cc3342',
          'red-lt':  '#ffe4e5',
          green:     '#92bd33',
          'green-l': '#a9cb62',
          'green-p': '#d4e5b2',
          yellow:    '#ffbf21',
          teal:      '#28c9c9',
          blue:      '#429cd8',
          orange:    '#ff5600',
        },
        /* Text / borders — exact Plum values */
        ptxt: {
          primary: '#2d2d2d',
          dark:    '#41495e',
          muted:   '#55657d',
          light:   '#a0a5ab',
          border:  '#ced5dd',
          divider: '#ebebeb',
        },
      },
      borderRadius: {
        pill: '30px',
        sm:   '0.625rem',
      },
      keyframes: {
        /* Plum's exact loading spinner */
        spin: {
          '0%':   { transform: 'rotate(0deg)'   },
          '100%': { transform: 'rotate(360deg)' },
        },
        /* Pipeline node glow */
        'node-glow': {
          '0%,100%': { boxShadow: '0 0 4px 0 rgba(123,64,103,0.35)' },
          '50%':     { boxShadow: '0 0 18px 6px rgba(123,64,103,0.7)' },
        },
        'fade-in': {
          from: { opacity: 0, transform: 'translateY(4px)' },
          to:   { opacity: 1, transform: 'translateY(0)' },
        },
      },
      animation: {
        /* Plum's exact 0.8s linear infinite spinner */
        spin:        '0.8s linear infinite spin',
        'node-glow': 'node-glow 1.2s ease-in-out infinite',
        'fade-in':   'fade-in 0.2s ease-out both',
      },
    },
  },
  plugins: [],
}
