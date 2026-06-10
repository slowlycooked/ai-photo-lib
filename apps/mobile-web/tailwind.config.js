/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        mobileBg: "#f7f8f5",
        mobileCard: "#ffffff",
        mobileInk: "#1e1e1a",
        mobileMute: "#65665d",
        mobileAccent: "#1f7a5b",
        mobileAccentPressed: "#176148",
        mobileHairline: "#d9dbd2"
      },
      fontFamily: {
        sans: ["Manrope", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        sheet: "0 10px 40px rgba(0, 0, 0, 0.16)",
      },
    },
  },
  plugins: [],
};
