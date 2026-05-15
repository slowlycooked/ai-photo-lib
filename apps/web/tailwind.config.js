/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Brand
        primary: "#e60023",
        "primary-pressed": "#cc001f",
        // Surfaces — from DESIGN.md
        canvas: "#ffffff",
        "surface-soft": "#fbfbf9",
        "surface-card": "#f6f6f3",
        "secondary-bg": "#e5e5e0",
        "secondary-pressed": "#c8c8c1",
        "surface-dark": "#262622",
        hairline: "#dadad3",
        // Text
        ink: "#000000",
        "ink-soft": "#211922",
        body: "#33332e",
        charcoal: "#262622",
        mute: "#62625b",
        ash: "#91918c",
        stone: "#c8c8c1",
        // Focus
        "focus-outer": "#435ee5",
      },
      borderRadius: {
        // Three-radius vocabulary from DESIGN.md
        sm: "8px",
        md: "16px",
        lg: "32px",
      },
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "system-ui",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
      fontSize: {
        // Typography scale from DESIGN.md
        "display-xl": ["70px", { lineHeight: "1.1", letterSpacing: "-1.2px", fontWeight: "600" }],
        "display-lg": ["44px", { lineHeight: "1.15", letterSpacing: "-0.8px", fontWeight: "700" }],
        "heading-xl": ["28px", { lineHeight: "1.2", letterSpacing: "-1.2px", fontWeight: "700" }],
        "heading-lg": ["22px", { lineHeight: "1.25", fontWeight: "600" }],
        "heading-md": ["18px", { lineHeight: "1.3", fontWeight: "600" }],
        "body-md": ["16px", { lineHeight: "1.4" }],
        "body-sm": ["14px", { lineHeight: "1.4" }],
        "caption-md": ["12px", { lineHeight: "1.5", fontWeight: "500" }],
        "caption-sm": ["12px", { lineHeight: "1.4" }],
        "btn-md": ["14px", { lineHeight: "1", fontWeight: "700" }],
        "btn-sm": ["12px", { lineHeight: "1", fontWeight: "700" }],
      },
    },
  },
  plugins: [],
};
