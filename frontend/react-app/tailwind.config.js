/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        border: "hsl(var(--border))",
        brand: {
          DEFAULT: "#2563eb",
          soft: "rgba(37, 99, 235, 0.12)",
        },
        success: {
          DEFAULT: "#16a34a",
          soft: "rgba(22, 163, 74, 0.12)",
        },
        warning: {
          DEFAULT: "#d97706",
          soft: "rgba(217, 119, 6, 0.12)",
        },
        destructive: {
          DEFAULT: "#dc2626",
          soft: "rgba(220, 38, 38, 0.12)",
        },
        "danger-soft": "rgba(220, 38, 38, 0.12)",
        "success-soft": "rgba(22, 163, 74, 0.12)",
        "warning-soft": "rgba(217, 119, 6, 0.12)",
        "brand-soft": "rgba(37, 99, 235, 0.12)",
      },
    },
  },
  plugins: [],
}
