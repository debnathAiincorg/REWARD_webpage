// Tailwind config for the committed static/app.css. Railway runs no Node build:
// after changing classes in a template, rebuild with the standalone CLI —
// see "Styles" in README.md.

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./templates/**/*.html", "./static/js/**/*.js"],
  theme: {
    extend: {
      colors: {
        // Deep, trustworthy base.
        navy: {
          50: "#EEF1F7",
          100: "#D9DFEC",
          200: "#B3BED6",
          300: "#8392B5",
          400: "#56678F",
          500: "#3A4C76",
          600: "#2A3D66",
          700: "#1F3157",
          800: "#162544",
          900: "#0F1B33",
          950: "#0A1226",
        },
        // Reward accent: money, points, top performers. gold-700 is the
        // darkest step and the only one used for text on white (AA contrast).
        gold: {
          50: "#FBF7EC",
          100: "#F6EBCB",
          200: "#EED69A",
          300: "#E4BE63",
          400: "#D9A93F",
          500: "#C9962B",
          600: "#A97B1F",
          700: "#7F5C15",
          800: "#5C4210",
          900: "#3E2C0B",
        },
        // Old theme, kept only until every page has moved to navy/gold.
        forest: { DEFAULT: "#2F5233", dark: "#223d26", light: "#e4eae1" },
        ink: "#1B2333",
        page: "#F4F6FA",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Consolas", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(15, 27, 51, 0.06), 0 4px 16px -4px rgba(15, 27, 51, 0.08)",
        lift: "0 2px 4px rgba(15, 27, 51, 0.06), 0 18px 40px -12px rgba(15, 27, 51, 0.25)",
        gold: "0 0 0 1px rgba(201, 150, 43, 0.35), 0 8px 24px -8px rgba(201, 150, 43, 0.45)",
      },
      keyframes: {
        rise: {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        shine: {
          "0%": { transform: "translateX(-120%) skewX(-20deg)" },
          "100%": { transform: "translateX(220%) skewX(-20deg)" },
        },
      },
      animation: {
        rise: "rise 0.5s cubic-bezier(0.2, 0.7, 0.2, 1) both",
        shine: "shine 1.4s ease-in-out 1",
      },
    },
  },
  plugins: [],
};
