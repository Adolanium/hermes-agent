import { execFileSync } from 'node:child_process'
import { createRequire } from 'node:module'
import { runInNewContext } from 'node:vm'

import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import type { DesktopSyncReceipt, HermesConnection } from '../../electron/ipc-contract'

import { SyncStatusCard } from './sync-status-card'

const host = {
  invoke: vi.fn<(channel: string, ...args: unknown[]) => Promise<unknown>>()
}

const requireFromTest = createRequire(import.meta.url)

beforeEach((): void => {
  host.invoke.mockReset()

  // Compile in Node: jsdom's typed-array realm cannot host esbuild itself.
  const bundle = execFileSync(process.execPath, [
    requireFromTest.resolve('esbuild/bin/esbuild'),
    requireFromTest.resolve('../../electron/preload.ts'),
    '--bundle', '--platform=node', '--format=cjs', '--external:electron'
  ], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] })

  runInNewContext(bundle, {
    require: (name: string): object => {
      if (name !== 'electron') {
        throw new Error(`Unavailable in sandboxed preload: ${name}`)
      }

      return {
        contextBridge: {
          exposeInMainWorld: (key: string, bridge: unknown): void => {
            vi.stubGlobal(key, bridge)
          }
        },
        ipcRenderer: { invoke: host.invoke, sendSync: (): object => ({}) },
        webFrame: {},
        webUtils: {}
      }
    },
    process: { platform: process.platform, env: {} }
  })
})

afterEach((): void => {
  cleanup()
  vi.unstubAllGlobals()
})

it('paints an update receipt through the real preload bridge', async (): Promise<void> => {
  const receipt: DesktopSyncReceipt = {
    plugin_checks: [{ name: 'notes', current: '1.0.0', latest: '1.1.0', update_available: true }]
  }

  host.invoke.mockImplementation(async (channel: string): Promise<unknown> => {
    if (channel !== 'hermes:sync-status') {
      throw new Error(`Unexpected IPC channel: ${channel}`)
    }

    return receipt
  })

  render(<SyncStatusCard />)

  expect((await screen.findByText('Plugin updates available (1)')).textContent).toBe('Plugin updates available (1)')
  expect(screen.getByText('notes: 1.0.0 → 1.1.0').textContent).toBe('notes: 1.0.0 → 1.1.0')
})

it('forwards a connection profile without the unused options argument', async (): Promise<void> => {
  const connection: HermesConnection = {
    baseUrl: 'http://127.0.0.1:1234',
    wsUrl: 'ws://127.0.0.1:1234/api/ws',
    token: '',
    logs: [],
    isFullscreen: false,
    nativeOverlayWidth: 0,
    windowButtonPosition: null,
    profile: 'work'
  }

  host.invoke.mockResolvedValue(connection)

  expect(await window.hermesDesktop.getConnection('work')).toEqual(connection)
  expect(host.invoke.mock.lastCall).toEqual(['hermes:connection', 'work'])
})
