import { describe, expect, it } from 'vitest'
import { SCHOOL_ERROR_CATEGORY_KEYS } from './knowledge'
import {
  FIX_STARTERS,
  getOrderedCategoriesForScene,
  REFLECTION_SCENE_OPTIONS,
  STUCK_STARTERS,
} from './reflectionGuide'

describe('reflectionGuide 校考复盘三步引导配置', () => {
  it('每类错因均有 2-3 条句式起头，且不包含内部编码', () => {
    for (const key of SCHOOL_ERROR_CATEGORY_KEYS) {
      const starters = STUCK_STARTERS[key]
      expect(starters.length).toBeGreaterThanOrEqual(2)
      expect(starters.length).toBeLessThanOrEqual(3)
      for (const s of starters) {
        expect(s).not.toMatch(/math_cand|physics_cand|_cand\./)
      }
    }
    expect(FIX_STARTERS.length).toBeGreaterThanOrEqual(2)
  })

  it('根据考场情境优先推荐对应错因，且保留全部 6 类错因', () => {
    expect(REFLECTION_SCENE_OPTIONS).toHaveLength(4)
    const ordered = getOrderedCategoriesForScene('had_idea')
    expect(ordered).toHaveLength(SCHOOL_ERROR_CATEGORY_KEYS.length)
    expect(ordered.slice(0, 3).map(o => o.category)).toEqual(['reading', 'calculation', 'norm'])
    expect(ordered.slice(0, 3).every(o => o.recommended)).toBe(true)
    expect(ordered.slice(3).every(o => !o.recommended)).toBe(true)

    const fallback = getOrderedCategoriesForScene('')
    expect(fallback.map(o => o.category)).toEqual([...SCHOOL_ERROR_CATEGORY_KEYS])
    expect(fallback.every(o => !o.recommended)).toBe(true)
  })
})
