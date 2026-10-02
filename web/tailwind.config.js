/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        gov: {
          50: '#f0f4f9',
          100: '#e1e9f2',
          200: '#c5d5e5',
          300: '#9cb9d3',
          400: '#6c96be',
          500: '#4a79a7',
          600: '#38608b',
          700: '#2d4d70',
          800: '#26405c',
          900: '#1e334a',
          950: '#132130',
        },
        slateCustom: {
          50: '#f8fafc',
          100: '#f1f5f9',
          200: '#e2e8f0',
          300: '#cbd5e1',
          400: '#94a3b8',
          500: '#64748b',
          600: '#475569',
          700: '#334155',
          800: '#1e293b',
          900: '#0f172a',
        }
      }
    },
  },
  plugins: [],
}
