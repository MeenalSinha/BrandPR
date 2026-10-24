import type { Config } from "tailwindcss";

// Premium executive brand-governance palette
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#F8F9FA", // warm, elegant off-white canvas
        sheet: "#FFFFFF", // crisp white cards & panels
        subtle: "#F1F4F6", // soft container wash
        ink: {
          DEFAULT: "#0F172A", // deep navy/slate
          soft: "#475569",    // secondary slate navy
          faint: "#94A3B8",   // muted text and placeholders
          subtle: "#CBD5E1",
        },
        rule: {
          DEFAULT: "#E2E8F0", // subtle, clean border
          strong: "#CBD5E1",  // emphasized divider
          soft: "#F1F5F9",
        },
        signal: {
          DEFAULT: "#0D766E", // primary executive teal
          dark: "#0F5E56",
          light: "#14B8A6",
          wash: "#F0FDFA",    // delicate teal wash
          border: "#CCFBF1",
        },
        terracotta: {
          DEFAULT: "#C2410C", // muted terracotta for warnings & attention
          dark: "#9A3412",
          wash: "#FFF7ED",
          border: "#FFEDD5",
        },
        marker: "#FEF08A",
        state: {
          current: "#047857",          // approved/verified emerald-teal
          "current-wash": "#ECFDF5",
          "current-border": "#A7F3D0",
          expired: "#BE123C",          // failed/conflict/expired rose-red
          "expired-wash": "#FFF1F2",
          "expired-border": "#FECDD3",
          unapproved: "#C2410C",       // terracotta / warning
          "unapproved-wash": "#FFF7ED",
          "unapproved-border": "#FFEDD5",
          retired: "#475569",          // retired slate
          "retired-wash": "#F1F5F9",
          "retired-border": "#E2E8F0",
          pending: "#1D4ED8",          // in review/draft blue
          "pending-wash": "#EFF6FF",
          "pending-border": "#BFDBFE",
        },
      },
      boxShadow: {
        subtle: "0 1px 3px 0 rgba(15, 23, 42, 0.04), 0 1px 2px -1px rgba(15, 23, 42, 0.04)",
        card: "0 1px 4px 0 rgba(15, 23, 42, 0.05), 0 2px 6px -1px rgba(15, 23, 42, 0.03)",
        floating: "0 10px 25px -5px rgba(15, 23, 42, 0.08), 0 8px 10px -6px rgba(15, 23, 42, 0.04)",
        dialog: "0 20px 35px -10px rgba(15, 23, 42, 0.16), 0 10px 15px -5px rgba(15, 23, 42, 0.08)",
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
