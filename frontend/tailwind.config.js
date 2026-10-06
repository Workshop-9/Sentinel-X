/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        dark: {
          900: '#0b0f19',
          800: '#111827',
          700: '#1f2937',
        },
        sentinel: {
          orange: '#fa8c16',
          cyan: '#13c2c2',
          red: '#ff4d4f',
          green: '#52c41a'
        }
      }
    },
  },
  plugins: [],
}