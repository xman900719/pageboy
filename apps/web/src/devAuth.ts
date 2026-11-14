/**
 * 开发模式（import.meta.env.DEV）自动登录辅助模块。
 *
 * 安全边界：
 * - 所有逻辑均受 `isDev`（默认 `import.meta.env.DEV`）与调用侧 `if (import.meta.env.DEV)` 双重门禁保护；
 * - 在 `vite build` 生产构建中，`import.meta.env.DEV` 为编译期常量 `false`，且 `.env.development.local`
 *   不会被 Vite 生产构建加载，确保开发凭据与自动进入逻辑彻底被 Tree-Shaking 移除。
 */

export type DevAuthRole = 'student' | 'admin'

export interface StorageLike {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
}

export interface DevAuthOptions {
  isDev?: boolean
  storage?: StorageLike | null
}

function getKeys(role: DevAuthRole) {
  return {
    tokenKey: `shutong.dev_token_${role}`,
    logoutKey: `shutong.dev_logout_${role}`,
  }
}

function resolveStorage(storage?: StorageLike | null): StorageLike | null {
  if (storage !== undefined) return storage
  try {
    return typeof sessionStorage !== 'undefined' ? sessionStorage : null
  } catch {
    return null
  }
}

function safeGet(storage: StorageLike | null, key: string): string | null {
  if (!storage) return null
  try {
    return storage.getItem(key)
  } catch {
    return null
  }
}

function safeSet(storage: StorageLike | null, key: string, value: string): void {
  if (!storage) return
  try {
    storage.setItem(key, value)
  } catch {
    // 忽略沙箱存储受限异常
  }
}

function safeRemove(storage: StorageLike | null, key: string): void {
  if (!storage) return
  try {
    storage.removeItem(key)
  } catch {
    // 忽略沙箱存储受限异常
  }
}

/** 解析开发模式可用的自动进入令牌；非开发模式或已主动退出时返回 null。 */
export function resolveDevAutoToken(
  role: DevAuthRole,
  envToken: string | undefined,
  options: DevAuthOptions = {}
): string | null {
  const isDev = options.isDev ?? import.meta.env.DEV
  if (!isDev) return null

  const storage = resolveStorage(options.storage)
  const { tokenKey, logoutKey } = getKeys(role)
  if (safeGet(storage, logoutKey) === 'true') return null

  const configured = envToken?.trim()
  if (configured) return configured

  const sessionToken = safeGet(storage, tokenKey)?.trim()
  return sessionToken ? sessionToken : null
}

/** 在开发模式登录成功后记录会话级令牌并清除退出标记。 */
export function markDevLoggedIn(
  role: DevAuthRole,
  token: string,
  options: DevAuthOptions = {}
): void {
  const isDev = options.isDev ?? import.meta.env.DEV
  if (!isDev) return
  const trimmed = token.trim()
  if (!trimmed) return

  const storage = resolveStorage(options.storage)
  const { tokenKey, logoutKey } = getKeys(role)
  safeSet(storage, tokenKey, trimmed)
  safeRemove(storage, logoutKey)
}

/** 在开发模式主动退出后清除会话级令牌并标记不再自动进入（便于验证令牌门）。 */
export function markDevLoggedOut(role: DevAuthRole, options: DevAuthOptions = {}): void {
  const isDev = options.isDev ?? import.meta.env.DEV
  if (!isDev) return

  const storage = resolveStorage(options.storage)
  const { tokenKey, logoutKey } = getKeys(role)
  safeRemove(storage, tokenKey)
  safeSet(storage, logoutKey, 'true')
}

/** 清理开发模式会话存储痕迹（用于生产构建保持无残留状态或令牌失效兜底）。 */
export function clearDevAuthArtifacts(role: DevAuthRole, storage?: StorageLike | null): void {
  const target = resolveStorage(storage)
  const { tokenKey, logoutKey } = getKeys(role)
  safeRemove(target, tokenKey)
  safeRemove(target, logoutKey)
}
