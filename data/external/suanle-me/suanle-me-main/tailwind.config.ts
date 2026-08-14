import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/app/**/*.{ts,tsx,mdx}",
    "./src/components/**/*.{ts,tsx,mdx}",
    "./src/lib/**/*.{ts,tsx,mdx}",
  ],
  theme: {
    extend: {
      borderRadius: {
        "2xl": "1.5rem",
      },
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "PingFang SC",
          "Hiragino Sans GB",
          "Microsoft YaHei",
          "sans-serif",
        ],
        serif: [
          "STSong",
          "Songti SC",
          "Noto Serif CJK SC",
          "Georgia",
          "serif",
        ],
      },
      boxShadow: {
        glass: "0 24px 80px rgba(0, 0, 0, 0.25)",
        gold: "0 18px 45px rgba(201, 168, 106, 0.2)",
      },
    },
  },
};

export default config;
