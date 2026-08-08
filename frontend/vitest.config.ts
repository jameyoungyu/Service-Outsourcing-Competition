import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  test: {
    globals: true,
    environment: "jsdom",
    // Playwright owns e2e/. Vitest would collect those specs and fail on the missing
    // browser runtime, which looks like a broken unit suite and is not one.
    exclude: ["**/node_modules/**", "**/dist/**", "e2e/**"],
  },
});
