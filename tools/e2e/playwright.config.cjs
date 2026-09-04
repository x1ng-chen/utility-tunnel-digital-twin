const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: __dirname,
  testMatch: ['ops.spec.cjs', 'visual.spec.cjs'],
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 120000,
  expect: { timeout: 15000 },
  use: {
    headless: true,
    viewport: { width: 1440, height: 960 },
    // CI runners use software WebGL. Respecting the application's reduced
    // motion/performance path keeps business controls responsive while the
    // suite still exercises the real Three.js scene and camera gestures.
    reducedMotion: 'reduce',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  outputDir: 'test-results',
});
