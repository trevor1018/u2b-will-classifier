/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // 案件偵探板配色
        ink: {
          950: "#06080d",
          900: "#0b1018",
          800: "#111827",
          700: "#1f2937",
          600: "#374151",
        },
        accent: {
          neon: "#a3e635",   // lime — solved
          warn: "#fbbf24",   // amber — partial
          danger: "#f87171", // red   — cold/unsolved
          info: "#60a5fa",   // blue  — pending
          ghost: "#9ca3af",  // gray  — unknown
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
        sans: ["Noto Sans TC", "Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
