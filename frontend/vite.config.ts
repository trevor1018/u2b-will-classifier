import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `base` is the path the site is served from on GitHub Pages.
// In dev (`npm run dev`) we want plain `/` so localhost works without subpath.
export default defineConfig(({ command }) => ({
  base: command === "build" ? "/u2b-will-classifier/" : "/",
  plugins: [react()],
  server: { port: 5173 },
  build: {
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        // Split heavy viz libs so initial paint downloads less JS up-front.
        // (Cytoscape and vis-timeline were dropped along with the Network /
        // per-case Timeline views.)
        manualChunks: {
          echarts: ["echarts", "echarts-for-react"],
          leaflet: ["leaflet", "react-leaflet"],
        },
      },
    },
  },
}));
