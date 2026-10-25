import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: '.',
  testMatch: 'desktop.spec.mjs',
  timeout: 240000,
  workers: 1,
  reporter: 'list',
  outputDir: '../../.cache/desktop-markdown-playwright'
})
