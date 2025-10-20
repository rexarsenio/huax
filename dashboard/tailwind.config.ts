import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        background: "var(--color-bg)",
        "background-secondary": "var(--color-bg-secondary)",
        "background-elevated": "var(--color-bg-elevated)",
        foreground: "var(--color-fg)",
        "foreground-muted": "var(--color-fg-muted)",
        accent: "var(--color-accent)",
        "accent-hover": "var(--color-accent-hover)",
        muted: "var(--color-muted)",
        border: "var(--color-border)",
        "border-subtle": "var(--color-border-subtle)",
        success: "var(--color-success)",
        "success-bg": "var(--color-success-bg)",
        danger: "var(--color-danger)",
        "danger-bg": "var(--color-danger-bg)",
        warning: "var(--color-warning)",
        "warning-bg": "var(--color-warning-bg)",
        info: "var(--color-info)",
        "info-bg": "var(--color-info-bg)",
      },
      borderRadius: {
        '2xl': '1rem',
        '3xl': '1.5rem',
      },
      boxShadow: {
        'glow': '0 0 20px rgba(59, 130, 246, 0.15)',
        'glow-lg': '0 0 40px rgba(59, 130, 246, 0.2)',
        'card': '0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -1px rgba(0, 0, 0, 0.2)',
        'card-hover': '0 10px 15px -3px rgba(0, 0, 0, 0.4), 0 4px 6px -2px rgba(0, 0, 0, 0.3)',
      },
      animation: {
        'fade-in': 'fadeIn 0.4s ease-out',
        'slide-in': 'slideIn 0.3s ease-out',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
};

export default config;
