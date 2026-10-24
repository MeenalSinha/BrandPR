import type { Config } from "tailwindcss";

// Palette is named after its job in the interface (paper, ink, rule, signal), not after hue.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#EEF1F5",
        sheet: "#FFFFFF",
        ink: { DEFAULT: "#17232F", soft: "#44566A", faint: "#6B7C8E" },
        rule: { DEFAULT: "#D3DAE2", strong: "#B4BFCB" },
        signal: { DEFAULT: "#24488A", dark: "#1A3568", wash: "#E6ECF7" },
        marker: "#FFE27A",
        state: {
          current: "#16623D", "current-wash": "#E1F1E8",
          expired: "#A1241C", "expired-wash": "#FBE6E3",
          unapproved: "#80530A", "unapproved-wash": "#FBEFD3",
          retired: "#4B5864", "retired-wash": "#E6EAEE",
          pending: "#2A579E", "pending-wash": "#E3EBF8",
        },
      },
      fontFamily: {
        serif: ['"Source Serif 4 Variable"', "Georgia", "serif"],
        sans: ['"Atkinson Hyperlegible"', "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
