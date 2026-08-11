import type { Config } from "tailwindcss";

// shadcn/ui is layered on top of this when the console UI lands (M1 slice 5).
export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: { extend: {} },
  plugins: [],
} satisfies Config;
