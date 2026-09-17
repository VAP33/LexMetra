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
          DEFAULT: "#0A369D", // Indian Gov Blue (DBIM standard)
          50: "#F0F5FF",
          100: "#E0EBFF",
          200: "#BAD3FF",
          300: "#85B4FF",
          400: "#4D8DFF",
          500: "#1A66FF",
          600: "#0A4DD6",
          700: "#0A369D", // Primary Gov Blue
          800: "#082976",
          900: "#061C52", // Ashoka Deep Navy
          950: "#030F2D",
          soft: "rgba(10, 54, 157, 0.10)",
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
