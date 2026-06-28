import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "tests/e2e",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: "python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000",
      url: "http://127.0.0.1:8000/health",
      env: {
        ...process.env,
        GEMINI_API_KEY: "",
        GEMINI_MAX_ATTEMPTS: "1",
        GEMINI_TIMEOUT_SECONDS: "5",
      },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 5173",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
