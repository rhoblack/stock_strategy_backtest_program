import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright E2E 설정.
 *
 * - baseURL: http://localhost:4173 (vite preview 기본 포트)
 * - webServer: npm run preview (dist/ 기반 서빙, CI에서는 build 선행 필요)
 * - API 호출은 page.route()로 모킹 → 백엔드 서버 불필요
 * - Chromium 단일 브라우저로 실행
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],

  use: {
    baseURL: "http://localhost:4173",
    headless: true,
    viewport: { width: 1280, height: 800 },
    ignoreHTTPSErrors: true,
    /** 실패 시 스크린샷 */
    screenshot: "only-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  webServer: {
    /** dist/ 기반 preview 서버 — 테스트 전 npm run build 필요 */
    command: "npm run preview",
    url: "http://localhost:4173",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    stdout: "pipe",
    stderr: "pipe",
  },
});
