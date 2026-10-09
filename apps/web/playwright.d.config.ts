import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/d',
  fullyParallel: false,
  workers: 1,
  use: { baseURL: 'http://127.0.0.1:8079', trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
  webServer: [
    { command: 'PYTHONPATH=../api:../api/tests ../../.venv/bin/python -m uvicorn e2e_app:app --host 127.0.0.1 --port 8078 --no-access-log', url: 'http://127.0.0.1:8078/api/v1/ready', reuseExistingServer: false },
    { command: 'VITE_DEV_API_TARGET=http://127.0.0.1:8078 npm run dev -- --port 8079', url: 'http://127.0.0.1:8079', reuseExistingServer: false },
  ],
});
