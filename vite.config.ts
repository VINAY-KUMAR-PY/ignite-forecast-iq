import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";
import tsConfigPaths from "vite-tsconfig-paths";

export default defineConfig({
  plugins: [react(), tailwindcss(), tsConfigPaths()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (/[\\/]node_modules[\\/](react|react-dom|scheduler)[\\/]/.test(id)) {
            return "react-vendor";
          }
          if (id.includes("@tanstack")) return "tanstack-vendor";
          if (
            id.includes("recharts") ||
            id.includes("d3-") ||
            id.includes("victory-vendor") ||
            id.includes("react-smooth") ||
            id.includes("decimal.js")
          ) {
            return "charts-vendor";
          }
          if (id.includes("@radix-ui")) return "radix-vendor";
          if (id.includes("lucide-react") || id.includes("lucide")) return "icons-vendor";
          if (id.includes("react-hook-form") || id.includes("@hookform") || id.includes("zod")) {
            return "forms-vendor";
          }
          return "vendor";
        },
      },
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
  },
});
