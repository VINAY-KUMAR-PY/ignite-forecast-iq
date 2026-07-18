import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import { defineConfig } from "vite";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [
    tanstackRouter({
      target: "react",
      autoCodeSplitting: true,
      routeFileIgnorePattern: String.raw`\.test\.`,
    }),
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
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
          if (
            id.includes("@radix-ui") ||
            id.includes("@floating-ui") ||
            id.includes("react-remove-scroll") ||
            id.includes("aria-hidden") ||
            id.includes("use-callback-ref") ||
            id.includes("use-sidecar")
          ) {
            return "radix-vendor";
          }
          if (id.includes("lucide-react") || id.includes("lucide")) return "icons-vendor";
          if (id.includes("jspdf") || id.includes("fflate")) return "pdf-core-vendor";
          if (
            id.includes("html2canvas") ||
            id.includes("canvg") ||
            id.includes("dompurify") ||
            id.includes("pako") ||
            id.includes("fast-png") ||
            id.includes("iobuffer") ||
            id.includes("svg-pathdata") ||
            id.includes("stackblur-canvas") ||
            id.includes("rgbcolor") ||
            id.includes("core-js")
          ) {
            return "pdf-renderer-vendor";
          }
          if (id.includes("date-fns")) return "date-vendor";
          if (id.includes("lodash")) return "utilities-vendor";
          if (
            id.includes("tailwind-merge") ||
            id.includes("class-variance-authority") ||
            id.includes("node_modules/clsx")
          ) {
            return "styles-vendor";
          }
          if (
            id.includes("embla-carousel") ||
            id.includes("cmdk") ||
            id.includes("sonner") ||
            id.includes("vaul")
          ) {
            return "ui-vendor";
          }
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
