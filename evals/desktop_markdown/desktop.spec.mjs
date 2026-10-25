import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { _electron, expect, test } from '@playwright/test'

import { buildAppEnv, createSandbox, findElectron } from '../../apps/desktop/e2e/fixtures.ts'
import transcript from '../../apps/desktop/scripts/perf/scenarios/transcript.mjs'
import { startMockServer } from '../../tests-js/scripts/mock-server.ts'
import { writeMockProviderConfig, writeEnvFile } from '../../tests-js/scripts/mock-provider-config.ts'

test('production renderer: transcript and complete prose stream', async () => {
  const root = process.cwd()
  const output = resolve(process.env.DESKTOP_BENCH_OUTPUT || '.cache/desktop-markdown')
  mkdirSync(output, { recursive: true })
  const sandbox = createSandbox('perf-markdown')
  mkdirSync(join(sandbox.root, 'AppData/Roaming'), { recursive: true })
  mkdirSync(join(sandbox.root, 'AppData/Local'), { recursive: true })
  const mock = await startMockServer()
  writeMockProviderConfig(sandbox.hermesHome, mock.url)
  writeEnvFile(sandbox.hermesHome)
  const env = buildAppEnv(sandbox, {
    HERMES_RUNTIME_DIR: join(sandbox.root, 'runtime'),
    HERMES_PYTHON: resolve(process.env.HERMES_PYTHON || '.venv/Scripts/python.exe'),
    USERPROFILE: sandbox.root,
    APPDATA: join(sandbox.root, 'AppData/Roaming'),
    LOCALAPPDATA: join(sandbox.root, 'AppData/Local')
  })
  delete env.ELECTRON_RUN_AS_NODE
  writeFileSync(join(output, 'sandbox.json'), JSON.stringify({ root: sandbox.root, home: sandbox.hermesHome }))
  const app = await _electron.launch({
    executablePath: findElectron(),
    args: [
      resolve(root, 'apps/desktop'),
      `--user-data-dir=${sandbox.userDataDir}`,
      '--disable-background-timer-throttling',
      '--disable-renderer-backgrounding',
      '--disable-backgrounding-occluded-windows',
      '--disable-features=CalculateNativeWinOcclusion'
    ],
    env,
    timeout: 120000
  })
  try {
    const page = await app.firstWindow()
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await page.waitForFunction(() => Boolean(window.__PERF_DRIVE__?.connected()), undefined, { timeout: 120000 })
    await page.waitForSelector('[data-slot="composer-rich-input"]')
    await page.waitForTimeout(3000)
    const session = await page.context().newCDPSession(page)
    const cdp = {
      send: (method, params = {}) => session.send(method, params),
      eval: async expression => {
        const result = await session.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
        if (result.exceptionDetails)
          throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text)
        return result.result.value
      }
    }
    await cdp.send('Emulation.setFocusEmulationEnabled', { enabled: true })
    await cdp.send('Performance.enable')
    const taskSeconds = async () => {
      const result = await cdp.send('Performance.getMetrics')
      return result.metrics.find(metric => metric.name === 'TaskDuration').value
    }
    const results = []
    await transcript.run(cdp, { turns: 50 })
    for (const turns of [200, 1000]) {
      for (let sample = 0; sample < 3; sample++) {
        results.push({ scenario: 'transcript', sample, ...(await transcript.run(cdp, { turns })) })
      }
    }
    const chunk = `${'This sentence explains how the worker handles queued requests. '.repeat(8)}**Ready** with \`code\`.\n\n`
    const tokens = 128
    for (let sample = 0; sample < 3; sample++) {
      await cdp.eval('window.__PERF_DRIVE__.loadTranscript(0)')
      await page.waitForTimeout(500)
      const cpuStart = await taskSeconds()
      const start = performance.now()
      await cdp.eval(
        `window.__PERF_DRIVE__.stream(${JSON.stringify({ chunk, totalTokens: tokens, intervalMs: 16, flushMinMs: 33 })})`
      )
      const content = page.locator('[data-slot="aui_assistant-message-content"]').last()
      await expect
        .poll(async () => (await content.textContent()).match(/Ready with/g)?.length, { timeout: 60000 })
        .toBe(tokens)
      await cdp.eval('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
      results.push({
        scenario: 'complete-stream',
        sample,
        chars: chunk.length * tokens,
        elapsedMs: performance.now() - start,
        rendererTaskMs: ((await taskSeconds()) - cpuStart) * 1000
      })
      expect(await content.locator('code').count()).toBe(tokens)
      expect((await content.textContent()).match(/queued requests/g)).toHaveLength(tokens * 8)
      if (sample === 2) await page.screenshot({ path: join(output, 'stream.png') })
      await cdp.eval('window.__PERF_DRIVE__.reset()')
    }
    expect(errors).toEqual([])
    const environment = await page.evaluate(() => ({
      userAgent: navigator.userAgent,
      width: innerWidth,
      height: innerHeight
    }))
    const rendererIndexSha256 = createHash('sha256')
      .update(readFileSync(resolve(root, 'apps/desktop/dist/index.html')))
      .digest('hex')
    writeFileSync(
      join(output, 'results.json'),
      `${JSON.stringify({ environment, rendererIndexSha256, rendererErrors: errors, results }, null, 2)}\n`
    )
    await session.detach()
  } finally {
    await app.close()
    try {
      execFileSync(env.HERMES_PYTHON, ['-m', 'hermes_cli.main', 'gateway', 'stop'], { env, timeout: 60000 })
    } finally {
      await mock.close()
    }
    // Preserve this isolated profile for diagnosis. Never stop gateways with --all.
  }
})
