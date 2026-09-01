import { defineConfig } from "vite";

// Backend is locked to loopback only. Never proxy or bind 0.0.0.0.
// Operator is http://127.0.0.1:8788 (dist/ + same-origin /api). Vite 5173 is npm run dev only.
const BACKEND = "http://127.0.0.1:8788";

export default defineConfig({
  base: "./",
  server: {
    host: "127.0.0.1",
    proxy: {
      "/api": {
        target: BACKEND,
        changeOrigin: false,
      },
    },
  },
  preview: {
    host: "127.0.0.1",
    proxy: {
      "/api": {
        target: BACKEND,
        changeOrigin: false,
      },
    },
  },
});
