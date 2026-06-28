import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vitest/config";
import tsConfigPaths from "vite-tsconfig-paths";

export default defineConfig({
  plugins: [react(), tailwindcss(), tsConfigPaths()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["src/test/setup.tsx"],
    css: true,
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
