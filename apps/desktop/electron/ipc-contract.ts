import type { IpcMain, IpcMainInvokeEvent, IpcRenderer } from 'electron'

/** PM receipts evolve independently of Desktop; missing sections remain optional. */
export interface DesktopSyncReceipt {
  schema?: number
  kind?: string
  outcome?: string
  exit_code?: number
  started_at?: string
  finished_at?: string
  steps?: Array<{ name: string; ok: boolean; detail?: string; at?: string }>
  venv_rebuild?: { ok: boolean; reason?: string } | null
  pm_sync_outcome?: string
  pm_steps?: DesktopSyncReceipt['steps']
  pm_venv_rebuild?: DesktopSyncReceipt['venv_rebuild']
  pm_plugin_bisect?: DesktopSyncReceipt['plugin_bisect']
  plugin_bisect?: Array<{ plugin: string; action: string; reason: string }>
  plugin_checks?: Array<{
    name: string
    class?: string
    current?: string | null
    latest?: string | null
    update_available?: boolean | null
    needs_fixing?: string | null
    reason?: string
  }>
  feature_list?: string[] | null
}

export interface HermesConnection {
  baseUrl: string
  customWindowControls?: boolean
  darwinMajor?: number
  isFullscreen: boolean
  isMaximized?: boolean
  // The live, RESOLVED connection mode. Only ever 'local' or 'remote' — a
  // 'cloud' saved-config entry resolves to a 'remote' connection under the hood
  // (cloud-auto-discovery Q3/Q6), so this never carries 'cloud'.
  mode?: 'local' | 'remote'
  // 'native': this machine's gateway; no static token, per-call private grants.
  authMode?: 'native' | 'oauth' | 'token'
  remoteHost?: string
  remoteIdentity?: string
  remoteKind?: 'cloud' | 'ssh' | 'url'
  remoteHermesVersion?: string
  nativeOverlayWidth: number
  source?: 'env' | 'local' | 'settings'
  token: string
  wsUrl: string
  logs: string[]
  // Set for pool (non-primary) backends so the renderer knows which profile a
  // connection belongs to.
  profile?: string
  // The registry connection this descriptor resolves to. Registry-scoped
  // secondaries carry it directly; legacy primary remotes preserve it from
  // their selected stored route before dialing.
  connectionId?: string
  // True only when getConnectionFor explicitly resolved a v2 registry route.
  // An inferred connectionId identifies the visible source but its v1 profile
  // name may still be a client-side routing alias rather than a backend profile.
  registryScoped?: boolean
  // True only when `profile` is a request scope on the shared primary backend.
  // A pooled backend also carries `profile`, so presence alone cannot identify
  // the shared-primary routing case.
  sharedPrimary?: boolean
  // True when `profile` is a request scope on a SHARED registry remote/cloud
  // backend (one host, many profiles) — the registry analogue of sharedPrimary.
  sharedRemote?: boolean
  windowButtonPosition: { x: number; y: number } | null
}

// Type-only imports keep this contract safe for the sandboxed preload.
function invoke<Args extends unknown[], Result>(channel: string) {
  return {
    expose: (renderer: Pick<IpcRenderer, 'invoke'>) =>
      (...args: Args): Promise<Result> => renderer.invoke(channel, ...args),
    handle: (
      main: Pick<IpcMain, 'handle'>,
      handler: (event: IpcMainInvokeEvent, ...args: Args) => Result | Promise<Result>
    ): void => main.handle(channel, handler)
  }
}

export const desktopIpc = {
  // Omit profile for the window's backend; a named profile reuses its descriptor.
  getConnection: invoke<[profile?: string | null], HermesConnection>('hermes:connection'),
  // Null means no operation has written a receipt yet.
  getSyncStatus: invoke<[], DesktopSyncReceipt | null>('hermes:sync-status')
}

export function exposeDesktopIpc(renderer: Pick<IpcRenderer, 'invoke'>) {
  return {
    getConnection: desktopIpc.getConnection.expose(renderer),
    getSyncStatus: desktopIpc.getSyncStatus.expose(renderer)
  } satisfies { [K in keyof typeof desktopIpc]: ReturnType<(typeof desktopIpc)[K]['expose']> }
}

export type DesktopIpcApi = ReturnType<typeof exposeDesktopIpc>
