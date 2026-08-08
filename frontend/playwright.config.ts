import { defineConfig, devices } from "@playwright/test";

import { existsSync } from "node:fs";

const API_PORT = Number(process.env.E2E_API_PORT || 18010);
const WEB_PORT = Number(process.env.E2E_WEB_PORT || 4173);

// Some environments ship a preinstalled Chromium whose build number does not match the one
// this @playwright/test version would download. Point at the preinstalled binary when it is
// there rather than fetching a second copy; fall back to Playwright's own resolution
// everywhere else, so a normal `npx playwright install` checkout still works untouched.
const PREINSTALLED = ["/opt/pw-browsers/chromium-1194/chrome-linux/chrome"];
const executablePath =
  process.env.PLAYWRIGHT_CHROMIUM_PATH || PREINSTALLED.find((path) => existsSync(path));

export default defineConfig({
  testDir: "./e2e",
  // The suite drives real algorithms — a benchmark run or an Optuna study is seconds, not
  // milliseconds — so the timeouts are sized for real work rather than for a mocked API.
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: process.env.CI ? "line" : "list",
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        launchOptions: executablePath ? { executablePath } : {},
      },
    },
  ],
  webServer: [
    {
      // A disposable SQLite instance of the real API. Not the deployment path — Alembic
      // against PostgreSQL is — but the same application code and the same algorithms.
      command: `python scripts/serve_e2e.py --port ${API_PORT}`,
      cwd: "../backend",
      url: `http://127.0.0.1:${API_PORT}/api/v1/health/live`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      command: "npm run build && npm run preview -- --port " + WEB_PORT + " --strictPort",
      url: `http://127.0.0.1:${WEB_PORT}`,
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
      env: { VITE_API_TARGET: `http://127.0.0.1:${API_PORT}` },
    },
  ],
});
