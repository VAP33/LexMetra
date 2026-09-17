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
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        border: "hsl(var(--border))",
        brand: {
          DEFAULT: "#6B21A8", // Brand Royal Purple
          50: "#FAF5FF",
          100: "#F3E8FF",
          200: "#E9D5FF",
          300: "#D8B4FE",
          400: "#A855F7",
          500: "#8B5CF6",
          600: "#7C3AED",
          700: "#6B21A8",
          800: "#581C87",
          900: "#3B0764",
          soft: "rgba(107, 33, 168, 0.12)",
        },
        saffron: {
          DEFAULT: "#FF671F", // National Saffron (Bhagwa / Kesari)
          50: "#FFF7ED",
          100: "#FFEDD5",
          200: "#FED7AA",
          300: "#FDBA74",
          400: "#FB923C",
          500: "#FF671F",
          600: "#EA580C",
          700: "#C2410C",
          800: "#9A3412",
          soft: "rgba(255, 103, 31, 0.14)",
        },
        govgreen: {
          DEFAULT: "#046A38", // National India Green
          50: "#F0FDF4",
          100: "#DCFCE7",
          200: "#BBF7D0",
          300: "#86EFAC",
          400: "#4ADE80",
          500: "#046A38",
          600: "#03542C",
          700: "#15803D",
          800: "#166534",
          soft: "rgba(4, 106, 56, 0.14)",
        },
        navy: {
          DEFAULT: "#06038D", // Ashoka Chakra Navy Blue
          50: "#EFF6FF",
          100: "#DBEAFE",
          500: "#1E40AF",
          600: "#1E3A8A",
          700: "#06038D",
          soft: "rgba(6, 3, 141, 0.12)",
        },
        success: {
          DEFAULT: "#046A38",
          soft: "rgba(4, 106, 56, 0.12)",
        },
        warning: {
          DEFAULT: "#FF671F",
          soft: "rgba(255, 103, 31, 0.14)",
        },
        destructive: {
          DEFAULT: "#DC2626",
          soft: "rgba(220, 38, 38, 0.12)",
        },
        "danger-soft": "rgba(220, 38, 38, 0.12)",
        "success-soft": "rgba(4, 106, 56, 0.12)",
        "warning-soft": "rgba(255, 103, 31, 0.14)",
        "brand-soft": "rgba(107, 33, 168, 0.12)",
        "saffron-soft": "rgba(255, 103, 31, 0.14)",
        "govgreen-soft": "rgba(4, 106, 56, 0.14)",
      },
    },
  },
  plugins: [],
}
