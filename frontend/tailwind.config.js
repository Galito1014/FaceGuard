/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Inter Variable"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      colors: {
        ink: {
          950: "#05070a",
          900: "#080b10",
          850: "#0b0f15",
          800: "#0f141b",
          750: "#131a23",
          700: "#18212c",
          600: "#222d3a",
          500: "#2e3b4b",
          400: "#4a5a6e",
          300: "#7b8a9e",
          200: "#a9b5c4",
          100: "#d6dde6",
        },
        volt: { 300: "#7cc4ff", 400: "#45a6ff", 500: "#1f8bff", 600: "#0b6fe0", 700: "#0a56ad" },
        alert: { 400: "#ff6b6b", 500: "#f43f4e", 600: "#d42a3a" },
        ok: { 400: "#4ade80", 500: "#22c55e" },
        warn: { 400: "#fbbf24", 500: "#f59e0b" },
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(31,139,255,.35), 0 0 24px -4px rgba(31,139,255,.45)",
        "glow-red": "0 0 0 1px rgba(244,63,78,.45), 0 0 28px -4px rgba(244,63,78,.55)",
      },
      keyframes: {
        "fade-in": { from: { opacity: 0, transform: "translateY(4px)" }, to: { opacity: 1, transform: "none" } },
        "slide-in": { from: { opacity: 0, transform: "translateX(24px)" }, to: { opacity: 1, transform: "none" } },
        pulseRing: { "0%": { boxShadow: "0 0 0 0 rgba(244,63,78,.55)" }, "100%": { boxShadow: "0 0 0 12px rgba(244,63,78,0)" } },
        scan: { "0%": { top: "0%" }, "100%": { top: "100%" } },
      },
      animation: {
        "fade-in": "fade-in .25s ease-out both",
        "slide-in": "slide-in .3s ease-out both",
        "pulse-ring": "pulseRing 1.6s ease-out infinite",
        scan: "scan 3.5s linear infinite",
      },
    },
  },
  plugins: [],
};
