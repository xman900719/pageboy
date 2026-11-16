/* 开发模式自动登录辅助函数单测（正反例）。 */
import { describe, expect, it } from 'vitest'
import {
  clearDevAuthArtifacts,
  markDevLoggedIn,
  markDevLoggedOut,
  resolveDevAutoToken,
  type StorageLike,
} from './devAuth'

function makeMemoryStorage(initial: Record<string, string> = {}): StorageLike {
  const map = new Map<string, string>(Object.entries(initial))
  return {
    getItem: (key) => map.get(key) ?? null,
    setItem: (key, value) => {
      map.set(key, value)
    },
    removeItem: (key) => {
      map.delete(key)
    },
  }
}

describe('devAuth', () => {
  it('非开发模式（isDev=false）严禁读取环境变量或会话开发令牌', () => {
    const storage = makeMemoryStorage({ 'shutong.dev_token_student': 'cached-stu' })
    expect(resolveDevAutoToken('student', 'env-stu', { isDev: false, storage })).toBeNull()
    expect(resolveDevAutoToken('admin', 'env-adm', { isDev: false, storage })).toBeNull()

    markDevLoggedIn('admin', 'new-adm', { isDev: false, storage })
    expect(storage.getItem('shutong.dev_token_admin')).toBeNull()
  })

  it('显式禁用自动登录时忽略环境令牌与会话令牌', () => {
    const storage = makeMemoryStorage({ 'shutong.dev_token_admin': 'cached-adm' })
    expect(
      resolveDevAutoToken('admin', 'env-adm', { isDev: true, disabled: true, storage })
    ).toBeNull()
  })

  it('开发模式优先使用环境变量配置令牌（学生端与管理端严格按角色隔离）', () => {
    const storage = makeMemoryStorage({
      'shutong.dev_token_student': 'old-stu',
      'shutong.dev_token_admin': 'old-adm',
    })
    expect(resolveDevAutoToken('student', ' dev-student-abc ', { isDev: true, storage })).toBe(
      'dev-student-abc'
    )
    expect(resolveDevAutoToken('admin', ' dev-admin-xyz ', { isDev: true, storage })).toBe(
      'dev-admin-xyz'
    )
  })

  it('未配置环境变量时可回退同角色会话令牌，空白串返回 null', () => {
    const storage = makeMemoryStorage({ 'shutong.dev_token_student': 'session-stu' })
    expect(resolveDevAutoToken('student', undefined, { isDev: true, storage })).toBe('session-stu')
    expect(resolveDevAutoToken('admin', '   ', { isDev: true, storage })).toBeNull()
  })

  it('主动退出后返回 null 以停留令牌门；重新登录后恢复可用', () => {
    const storage = makeMemoryStorage()
    markDevLoggedIn('admin', 'dev-admin-xyz', { isDev: true, storage })
    expect(resolveDevAutoToken('admin', 'dev-admin-xyz', { isDev: true, storage })).toBe(
      'dev-admin-xyz'
    )

    markDevLoggedOut('admin', { isDev: true, storage })
    expect(storage.getItem('shutong.dev_token_admin')).toBeNull()
    expect(storage.getItem('shutong.dev_logout_admin')).toBe('true')
    expect(resolveDevAutoToken('admin', 'dev-admin-xyz', { isDev: true, storage })).toBeNull()
    // 管理端退出不得影响学生端
    expect(resolveDevAutoToken('student', 'dev-student-abc', { isDev: true, storage })).toBe(
      'dev-student-abc'
    )

    markDevLoggedIn('admin', 'dev-admin-xyz', { isDev: true, storage })
    expect(storage.getItem('shutong.dev_logout_admin')).toBeNull()
    expect(resolveDevAutoToken('admin', 'dev-admin-xyz', { isDev: true, storage })).toBe(
      'dev-admin-xyz'
    )
  })

  it('clearDevAuthArtifacts 彻底清理对应角色的会话令牌与退出标记', () => {
    const storage = makeMemoryStorage({
      'shutong.dev_token_admin': 'adm',
      'shutong.dev_logout_admin': 'true',
      'shutong.dev_token_student': 'stu',
    })
    clearDevAuthArtifacts('admin', storage)
    expect(storage.getItem('shutong.dev_token_admin')).toBeNull()
    expect(storage.getItem('shutong.dev_logout_admin')).toBeNull()
    expect(storage.getItem('shutong.dev_token_student')).toBe('stu')
  })
})
