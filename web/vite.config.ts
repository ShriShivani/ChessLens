import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const backend = "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    // In dev the page and API share an origin, so the app needs no CORS or absolute URLs.
    proxy: {
      "/api": backend,
      "/health": backend,
      "/ws": { target: backend, ws: true },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    css: false,
  },
});
