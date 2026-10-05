import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  use: { baseURL: process.env.E2E_URL ?? 'http://localhost:8080', trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
});

