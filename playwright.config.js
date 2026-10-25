const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests/browser',
  timeout: 30000,
  retries: 1,
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:5000',
    locale: 'pt-MZ',
    headless: true,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure'
  },
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]]
});

