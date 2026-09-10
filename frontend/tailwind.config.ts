import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // BhoomiLens brand palette — earthy, subdued, serious
        brand: {
          50: "#F4F1EA",
          100: "#E5DFCF",
          400: "#7C6B4D",
          600: "#4B3B22",
          700: "#332815",
        },
        risk: {
          low: "#166534",
          medium: "#B45309",
          high: "#B91C1C",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
