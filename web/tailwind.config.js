/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#070B10",
        panel: "#0C1219",
        raised: "#111A23",
        line: "#1E2A36",
        ink: "#E6EDF3",
        muted: "#8A9AA9",
        accent: {
          DEFAULT: "#5EEAD4",
          dim: "#2DD4BF",
          wash: "rgba(94, 234, 212, 0.12)",
        },
        danger: "#FB7185",
        warn: "#FBBF24",
        ok: "#4ADE80",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      boxShadow: {
        panel: "0 1px 0 rgba(255,255,255,0.03), 0 18px 50px rgba(0,0,0,0.45)",
        glow: "0 0 0 1px rgba(94,234,212,0.35), 0 0 34px rgba(94,234,212,0.12)",
      },
      keyframes: {
        "pulse-line": {
          "0%, 100%": { opacity: "0.35" },
          "50%": { opacity: "1" },
        },
        scan: {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(400%)" },
        },
      },
      animation: {
        "pulse-line": "pulse-line 1.8s ease-in-out infinite",
        scan: "scan 2.4s linear infinite",
      },
    },
  },
  plugins: [],
};
