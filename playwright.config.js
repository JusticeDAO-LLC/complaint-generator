const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './playwright/tests',
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  fullyParallel: true,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:19000',
    trace: 'on-first-retry',
  },
  webServer: {
    command: 'node ./playwright/server.js',
    url: 'http://localhost:19000/health',
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
