/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './templates/**/*.html',
    './static/js/**/*.js'
  ],
  theme: {
    extend: {
      colors: {
        ink: '#101820',
        science: '#087F73',
        signal: '#FF5A4F',
        paper: '#F5F7F8'
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        serif: ['Georgia', 'serif']
      }
    }
  },
  plugins: []
};
