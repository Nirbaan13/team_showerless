/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        paper: {
          50: '#faf8f5',
          100: '#f4f1ea',  // Warm Editorial Cream
          200: '#e8e4da',
          300: '#d7d2c6',
          400: '#a8a29e',  // Muted Sand
          500: '#78716c',
          600: '#57534e',
          700: '#292524',
          800: '#1c1c22',  // Soft Stone
          900: '#121216',  // Warm Charcoal
          950: '#0a0a0c',  // Deep Ink Black
        },
        ochre: {
          400: '#fbbf24',
          500: '#d97706',  // Warm scientific accent
          600: '#b45309',
        }
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', 'ui-monospace', 'Menlo', 'monospace'],
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
