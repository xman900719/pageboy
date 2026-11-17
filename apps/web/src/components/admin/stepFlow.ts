export interface StageTabItem {
  id: string
  title: string
  badge?: string
  wait?: boolean
  done?: boolean
}

export interface StageGroup {
  id: string
  title: string
  tabs: StageTabItem[]
}

export interface StepDefinition {
  id: string
  title: string
  subtitle?: string
  badge?: string
  badgeTone?: 'good' | 'wait' | 'bad' | 'mid' | 'subtle'
  done: boolean
  prereqMet: boolean
  lockReason?: string
}

export interface StepFlowContext {
  eyebrow: string
  title: string
  statusText?: string
  statusTone?: 'good' | 'wait' | 'bad' | 'mid' | 'subtle'
}

/** 根据前置条件解析当前应激活的合法步骤 ID，防止停留在未解锁或不存在的步骤。 */
export function resolveActiveStepId(
  steps: readonly StepDefinition[],
  requestedId?: string | null,
): string {
  if (steps.length === 0) return ''
  if (requestedId) {
    const requested = steps.find(step => step.id === requestedId)
    if (requested && requested.prereqMet) return requested.id
  }
  const firstUnlocked = steps.find(step => step.prereqMet)
  return (firstUnlocked ?? steps[0]).id
}

/** 方式 A 严格锁步点击判定：前置未满时拦截切换并返回明确解锁引导文案。 */
export function evaluateStepClick(
  steps: readonly StepDefinition[],
  targetId: string,
): { allowed: true; nextId: string } | { allowed: false; warning: string } {
  const target = steps.find(step => step.id === targetId)
  if (!target) {
    return { allowed: false, warning: '目标步骤不存在，请按当前可用步骤推进。' }
  }
  if (!target.prereqMet) {
    const reason = target.lockReason?.trim() || '请先完成前置步骤。'
    return {
      allowed: false,
      warning: `不可跳步至「${target.title}」：${reason}`,
    }
  }
  return { allowed: true, nextId: target.id }
}
