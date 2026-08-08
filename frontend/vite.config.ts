import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// The client calls "/api/v1" relative by default, so both the dev server and the preview
// server proxy that prefix to the backend. Without this, `npm run dev` gives a wall of 404s
// against Vite itself and every developer has to rediscover the same fix.
// VITE_API_TARGET points the proxy elsewhere — the E2E suite uses it to reach the
// throwaway SQLite instance on 18010 instead of a developer's real backend on 18000.
const target = process.env.VITE_API_TARGET || "http://127.0.0.1:18000";
const proxy = { "/api/v1": { target, changeOrigin: true } };

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: { proxy },
  preview: { proxy },
});
