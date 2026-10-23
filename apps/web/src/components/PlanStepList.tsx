import { ACTION_LABELS, pct } from '../copy'
import type { PlanStep, ProfileEntry } from '../api'
import { GapBadge } from './Badges'

/**
 * Per-knowledge plan row. Red-lines enforced here: INSUFFICIENT_EVIDENCE shows the
 * backend `reason` verbatim (缺证据解释); KNOWLEDGE_GAP shows observed_rate vs
 * planning_threshold labeled as uncalibrated observation — never as ability or score.
 */
export function PlanStepRow({
  step,
  threshold,
  profile,
  onGoPractice,
  onGoDiagnosis,
}: {
  step: PlanStep
  threshold: number
  profile?: ProfileEntry
  onGoPractice?: () => void
  onGoDiagnosis?: () => void
}) {
  return (
    <li className={`step gap-${step.gap_type.toLowerCase()}`}>
      <div className="step-head">
        <code className="kid">{step.knowledge_id}</code>
        <GapBadge gap={step.gap_type} />
      </div>
      <p className="step-reason">{step.reason}</p>
      <div className="step-facts">
        {step.gap_type === 'KNOWLEDGE_GAP' && step.observed_rate !== undefined && (
          <span>
            观察作答率 <b>{pct(step.observed_rate)}</b> · 规划阈值 <b>{pct(threshold)}</b>（未校准假设）
          </span>
        )}
        {profile && <span>独立题样本 {profile.sample_size} 题</span>}
        {ACTION_LABELS[step.action] && <span className="muted">{ACTION_LABELS[step.action]}</span>}
        {step.gap_type === 'INSUFFICIENT_EVIDENCE' && onGoDiagnosis && (
          <button type="button" className="ghost small" onClick={onGoDiagnosis}>
            去诊断
          </button>
        )}
        {step.gap_type === 'KNOWLEDGE_GAP' && onGoPractice && (
          <button type="button" className="ghost small" onClick={onGoPractice}>
            去练习
          </button>
        )}
      </div>
    </li>
  )
}

export function PlanStepList({
  steps,
  threshold,
  profiles,
  onGoPractice,
  onGoDiagnosis,
}: {
  steps: PlanStep[]
  threshold: number
  profiles?: Record<string, ProfileEntry>
  onGoPractice?: () => void
  onGoDiagnosis?: () => void
}) {
  if (steps.length === 0) {
    return (
      <ul className="steps">
        <li className="step">暂无已发布知识点：请先在管理端导入、审核并发布题目。</li>
      </ul>
    )
  }
  return (
    <ul className="steps">
      {steps.map(step => (
        <PlanStepRow
          key={step.knowledge_id}
          step={step}
          threshold={threshold}
          profile={profiles?.[step.knowledge_id]}
          onGoPractice={onGoPractice}
          onGoDiagnosis={onGoDiagnosis}
        />
      ))}
    </ul>
  )
}
