/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        nasa: {
          blue: '#1d4ed8',     // NASA Deep Mission Blue
          lightBlue: '#3b82f6',
          dark: '#0b0f19',     // Slate scientific background
          surface: '#111827',  // Neutral panel surface
          border: '#1f2937',   // Clean 1px border
          subtle: '#374151',
          textMuted: '#9ca3af',
          textMain: '#f3f4f6',
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
