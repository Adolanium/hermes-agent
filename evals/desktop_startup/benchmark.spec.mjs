import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { _electron, expect, test } from '@playwright/test'
import { buildAppEnv, createSandbox, findElectron } from '../../apps/desktop/e2e/fixtures.ts'
import { startMockServer } from '../../tests-js/scripts/mock-server.ts'
import { writeMockProviderConfig, writeEnvFile } from '../../tests-js/scripts/mock-provider-config.ts'

test('initialized Desktop startup', async () => {
  const label = process.env.BENCH_LABEL || 'measurement'
  const output = resolve(process.env.BENCH_OUTPUT || '.cache/desktop-startup')
  mkdirSync(output, { recursive: true })
  const sandbox = createSandbox('perf-loading-steady')
  for (const dir of ['AppData/Roaming', 'AppData/Local']) mkdirSync(join(sandbox.root, dir), { recursive: true })
  const mock = await startMockServer()
  writeMockProviderConfig(sandbox.hermesHome, mock.url)
  writeEnvFile(sandbox.hermesHome)
  const env = buildAppEnv(sandbox, {
    HERMES_RUNTIME_DIR: join(sandbox.root, 'runtime'),
    HERMES_PYTHON: resolve(process.env.HERMES_PYTHON || join('.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')),
    USERPROFILE: sandbox.root, APPDATA: join(sandbox.root, 'AppData/Roaming'), LOCALAPPDATA: join(sandbox.root, 'AppData/Local')
  })
  delete env.ELECTRON_RUN_AS_NODE
  const results = []
  const metadata = {
    label, node: process.version, platform: process.platform,
    commit: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
    sourceSha256: createHash('sha256').update(readFileSync('hermes_cli/update_cmd_fleet.py')).digest('hex'),
    sandbox: sandbox.root
  }
  const stop = () => execFileSync(env.HERMES_PYTHON, ['-m', 'hermes_cli.main', 'gateway', 'stop'], { env, timeout: 60000, windowsHide: true, stdio: 'pipe' })
  try {
    for (let repetition = -1; repetition < 3; repetition++) {
      for (const mode of ['cold-gateway', 'warm-gateway']) {
        const started = performance.now()
        const app = await _electron.launch({ executablePath: findElectron(), args: [resolve('apps/desktop'), `--user-data-dir=${sandbox.userDataDir}`,
          '--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows', '--disable-features=CalculateNativeWinOcclusion'], env, timeout: 120000 })
        try {
          const page = await app.firstWindow()
          const windowMs = performance.now() - started
          const errors = []
          page.on('pageerror', error => errors.push(error.message))
          await page.waitForFunction(() => !!window.__PERF_DRIVE__?.connected(), undefined, { timeout: 120000 })
          const connectedMs = performance.now() - started
          const composer = page.locator('[data-slot="composer-rich-input"]')
          await composer.click({ timeout: 120000 })
          const draft = `Startup benchmark ${mode} ${repetition}`
          await composer.fill(draft)
          await expect(composer).toContainText(draft)
          const interactiveMs = performance.now() - started
          expect(errors).toEqual([])
          const row = { repetition, warmup: repetition < 0, mode, windowMs, connectedMs, interactiveMs, errors }
          results.push(row)
          console.log(JSON.stringify(row))
          writeFileSync(join(output, `${label}.json`), JSON.stringify({ metadata, results }, null, 2))
        } finally { await app.close() }
      }
      stop()
    }
  } finally {
    try { stop() } finally { await mock.close() }
  }
})
