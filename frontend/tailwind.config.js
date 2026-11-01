/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        cream: {
          50: '#fdfcf9',
          100: '#faf7f2', // Base light canvas
          200: '#f4ede2', // Card background / warm neutral
          300: '#ebdccb', // Border tone
          400: '#dec7af',
          500: '#cfb395',
        },
        caramel: {
          50: '#fdf8f2',
          100: '#f8eedf',
          200: '#edd8be',
          300: '#dfbe97',
          400: '#d0a271',
          500: '#be854b', // Core rich caramel
          600: '#a86f3b', // Deep roasted caramel
          700: '#895530',
          800: '#71452c',
          900: '#5c3926',
          950: '#331c12',
        },
        champagne: {
          50: '#fdfbf7',
          100: '#f9f5ed',
          200: '#f1e6d4',
          300: '#e5d1b3',
          400: '#d5b78d',
          500: '#c19c69',
        },
        espresso: {
          700: '#3d3027',
          800: '#2e231c',
          850: '#241a14',
          900: '#1b130e',
          950: '#120d09',
        },
      },
      boxShadow: {
        'caramel-glow': '0 4px 20px -2px rgba(190, 133, 75, 0.2)',
        'caramel-sm': '0 2px 10px -2px rgba(190, 133, 75, 0.15)',
        'soft': '0 2px 12px 0 rgba(70, 48, 28, 0.06)',
      },
    },
  },
  plugins: [],
}
