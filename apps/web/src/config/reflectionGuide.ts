import type { SchoolErrorCategory } from '../api'
import { SCHOOL_ERROR_CATEGORY_KEYS } from './knowledge'

export type ReflectionScene = 'had_idea' | 'stuck_midway' | 'no_idea' | 'no_time'

export interface ReflectionSceneOption {
  value: ReflectionScene
  label: string
  hint: string
  suggest: readonly SchoolErrorCategory[]
}

export const REFLECTION_SCENE_OPTIONS: readonly ReflectionSceneOption[] = [
  {
    value: 'had_idea',
    label: '一看就有思路',
    hint: '原本能做出来，后来出了偏差',
    suggest: ['reading', 'calculation', 'norm'],
  },
  {
    value: 'stuck_midway',
    label: '有思路但中途卡住',
    hint: '开头会做，走到某一步接不上了',
    suggest: ['method', 'concept'],
  },
  {
    value: 'no_idea',
    label: '完全没头绪',
    hint: '读完题不知道从哪里下手',
    suggest: ['concept', 'method'],
  },
  {
    value: 'no_time',
    label: '时间不够没做完',
    hint: '会做或能写，但没来得及写完/检查',
    suggest: ['method', 'other'],
  },
] as const

export const STUCK_STARTERS: Record<SchoolErrorCategory, readonly string[]> = {
  reading: [
    '题目里的「」条件我没用上，当时以为',
    '我把「」看成了「」，结果',
  ],
  concept: [
    '我把「」概念和「」混了，其实应该是',
    '套用「」公式时忘记了前提条件',
  ],
  calculation: [
    '在「」这一步，我把「」算成了「」',
    '移项/去括号时「」的符号写反了',
  ],
  method: [
    '做到「」这一步卡住了，没想到要先',
    '辅助线/解题切入点选错了，应该从「」入手',
  ],
  norm: [
    '这步漏写了「」说明/单位/验根，导致扣分',
    '答题格式不完整，少了「」这一步推导',
  ],
  other: [
    '做到这题时时间只剩「」，来不及检查',
    '当时心态有点急，跳过「」直接写了',
  ],
}

export const FIX_STARTERS: readonly string[] = [
  '如果再看到「」，我就先「」。',
  '写完这一步后，我用「」的方法检查一遍。',
  '先把「」圈出来，确认满足条件再往下算。',
]

/**
 * 与后端 `_REFLECTION_STARTER_FRAGMENTS` 同源：
 * 统计实质有效字数前剥离句式起头的固定模板外壳，确保只点按钮不补全具体内容时无法过线。
 */
export const REFLECTION_STARTER_FRAGMENTS: readonly string[] = [
  '条件我没用上，当时以为',
  '辅助线/解题切入点选错了，应该从',
  '圈出来，确认满足条件再往下算',
  '说明/单位/验根，导致扣分',
  '这一步卡住了，没想到要先',
  '当时心态有点急，跳过',
  '公式时忘记了前提条件',
  '做到这题时时间只剩',
  '答题格式不完整，少了',
  '移项/去括号时',
  '写完这一步后，我用',
  '混了，其实应该是',
  '条件我没用上',
  '的方法检查一遍',
  '这一步，我把',
  '的符号写反了',
  '这一步推导',
  '如果再看到',
  '来不及检查',
  '题目里的',
  '我就先',
  '直接写了',
  '这步漏写了',
  '看成了',
  '概念和',
  '算成了',
  '做到',
  '入手',
  '先把',
]

export function getStuckStarters(category: SchoolErrorCategory | ''): readonly string[] {
  if (!category) return []
  return STUCK_STARTERS[category] ?? []
}

/** 根据考场情境给出推荐优先排序后的错因列表（其余错因仍全部保留可选）。 */
export function getOrderedCategoriesForScene(
  scene: ReflectionScene | '',
): { category: SchoolErrorCategory; recommended: boolean }[] {
  const matched = REFLECTION_SCENE_OPTIONS.find(o => o.value === scene)
  const suggested = matched ? matched.suggest : []
  const suggestedSet = new Set<SchoolErrorCategory>(suggested)
  const rest = SCHOOL_ERROR_CATEGORY_KEYS.filter(k => !suggestedSet.has(k))
  return [
    ...suggested.map(category => ({ category, recommended: true })),
    ...rest.map(category => ({ category, recommended: false })),
  ]
}
