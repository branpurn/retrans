import { defineConfig } from "vite";

// Backend is locked to loopback only. Never proxy or bind 0.0.0.0.
const BACKEND = "http://127.0.0.1:8788";

export default defineConfig({
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
