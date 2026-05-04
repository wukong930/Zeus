import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/**/*.{ts,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Backgrounds
        "bg-base": "#000000",
        "bg-surface": "#0A0A0A",
        "bg-surface-raised": "#141414",
        "bg-surface-overlay": "#1F1F1F",
        "bg-surface-highlight": "#292929",
        "bg-panel": "#0F1110",
        "bg-panel-strong": "#171A18",
        "bg-data-band": "#050705",
        // Text
        "text-primary": "#FFFFFF",
        "text-secondary": "#A3A3A3",
        "text-muted": "#737373",
        "text-disabled": "#404040",
        // Borders
        "border-subtle": "#1A1A1A",
        "border-default": "#262626",
        "border-strong": "#404040",
        // Brand
        "brand-emerald": "#059669",
        "brand-emerald-hover": "#047857",
        "brand-emerald-bright": "#10B981",
        "brand-orange": "#F97316",
        "brand-orange-hover": "#EA580C",
        "brand-cyan": "#38BDF8",
        "brand-blue": "#60A5FA",
        "brand-violet": "#A78BFA",
        // Data
        "data-up": "#10B981",
        "data-down": "#EF4444",
        "data-flat": "#A3A3A3",
        "data-warning": "#F59E0B",
        // Severity
        "severity-critical-fg": "#FCA5A5",
        "severity-high-fg": "#FCD34D",
        "severity-medium-fg": "#FDE68A",
        "severity-low-fg": "#86EFAC",
        // Charts
        "chart-grid": "#1F241F",
        "chart-axis": "#4B5563",
        "chart-band": "#0D1612",
        "chart-1": "#10B981",
        "chart-2": "#F97316",
        "chart-3": "#38BDF8",
        "chart-4": "#C084FC",
        "chart-5": "#FB7185",
        "chart-6": "#FACC15",
        "chart-7": "#22D3EE",
      },
      fontFamily: {
        sans: ["Inter", "PingFang SC", "HarmonyOS Sans", "-apple-system", "sans-serif"],
        mono: ["JetBrains Mono", "IBM Plex Mono", "SF Mono", "Consolas", "monospace"],
      },
      fontSize: {
        display: ["32px", { lineHeight: "1.2", fontWeight: "700" }],
        h1: ["24px", { lineHeight: "1.3", fontWeight: "600" }],
        h2: ["20px", { lineHeight: "1.3", fontWeight: "600" }],
        h3: ["16px", { lineHeight: "1.4", fontWeight: "600" }],
        body: ["14px", { lineHeight: "1.5", fontWeight: "400" }],
        sm: ["13px", { lineHeight: "1.4", fontWeight: "400" }],
        xs: ["12px", { lineHeight: "1.4", fontWeight: "500" }],
        caption: ["11px", { lineHeight: "1.3", fontWeight: "500" }],
      },
      spacing: {
        "1": "4px",
        "2": "8px",
        "3": "12px",
        "4": "16px",
        "5": "24px",
        "6": "32px",
        "8": "48px",
        "10": "64px",
      },
      borderRadius: {
        xs: "2px",
        sm: "4px",
        md: "6px",
        lg: "8px",
      },
      boxShadow: {
        sm: "0 1px 2px rgba(0,0,0,0.5)",
        md: "0 4px 12px rgba(0,0,0,0.6)",
        lg: "0 8px 24px rgba(0,0,0,0.7)",
        "glow-emerald": "0 0 16px rgba(16, 185, 129, 0.35)",
        "glow-orange": "0 0 20px rgba(249, 115, 22, 0.45)",
        "glow-red": "0 0 16px rgba(239, 68, 68, 0.4)",
        "inner-panel": "inset 0 1px 0 rgba(255,255,255,0.035)",
        "data-panel": "0 18px 50px rgba(0,0,0,0.38), inset 0 1px 0 rgba(255,255,255,0.035)",
        "focus-ring": "0 0 0 1px rgba(16,185,129,0.48), 0 0 0 4px rgba(16,185,129,0.10)",
      },
      transitionTimingFunction: {
        standard: "cubic-bezier(0.4, 0, 0.2, 1)",
        decelerate: "cubic-bezier(0, 0, 0.2, 1)",
        accelerate: "cubic-bezier(0.4, 0, 1, 1)",
        spring: "cubic-bezier(0.34, 1.56, 0.64, 1)",
      },
      animation: {
        "fade-in": "fadeIn 400ms cubic-bezier(0, 0, 0.2, 1)",
        "slide-in": "slideIn 400ms cubic-bezier(0, 0, 0.2, 1)",
        "glow-pulse": "glowPulse 2s ease-in-out infinite",
        "heartbeat": "heartbeat 2s ease-in-out infinite",
        "shimmer": "shimmer 1.5s linear infinite",
        "spin-slow": "spin 4s linear infinite",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        slideIn: {
          "0%": { opacity: "0", transform: "translateX(-12px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        glowPulse: {
          "0%, 100%": { boxShadow: "0 0 16px rgba(249, 115, 22, 0.45)" },
          "50%": { boxShadow: "0 0 28px rgba(249, 115, 22, 0.7)" },
        },
        heartbeat: {
          "0%, 100%": { opacity: "0.6" },
          "50%": { opacity: "1" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-1000px 0" },
          "100%": { backgroundPosition: "1000px 0" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
