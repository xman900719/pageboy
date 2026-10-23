import { CANNOT_COMPARE_EXPLAIN, VALIDATION_HEADLINES } from '../copy'
import type { Validation } from '../api'
import { VerdictChip } from './Badges'

/**
 * Observable baseline→retest comparison. Red-lines enforced here:
 * improved is always paired with the backend disclaimer verbatim; CANNOT_COMPARE is
 * always "证据不足，无法比较"; never any up/down-score or ability language.
 */
export function ValidationPanel({ validation }: { validation: Validation }) {
  const headline = VALIDATION_HEADLINES[validation.verdict] ?? validation.verdict
  const bannerTone =
    validation.verdict === 'IMPROVED_ON_COMPARABLE_SCOPE' ? 'good' : validation.verdict === 'CANNOT_COMPARE' ? 'caution' : 'neutral'
  return (
    <div className="validation">
      <div className={`verdict-banner ${bannerTone}`}>
        <b>{headline}</b>
        <p>{validation.disclaimer}</p>
      </div>
      {validation.verdict === 'CANNOT_COMPARE' && <p className="muted">{CANNOT_COMPARE_EXPLAIN}</p>}
      {validation.knowledge.length === 0 ? (
        <p className="muted">还没有可用于对比的独立验证记录。</p>
      ) : (
        <ul className="comparison">
          {validation.knowledge.map(entry => (
            <li key={entry.knowledge_id}>
              <code className="kid">{entry.knowledge_id}</code>
              {entry.verdict === 'cannot_compare' ? (
                <span className="comp-main">
                  <VerdictChip verdict="cannot_compare" />
                  <span className="muted">
                    {entry.reason === 'insufficient_retest' ? '复测侧独立题不足' : '基线侧独立题不足'}
                    （基线 {entry.baseline_items} 题 · 复测 {entry.retest_items} 题）
                  </span>
                </span>
              ) : (
                <span className="comp-main">
                  <VerdictChip verdict={entry.verdict} />
                  <span>
                    基线 <b>{fmtRate(entry.baseline_rate)}</b> → 复测 <b>{fmtRate(entry.retest_rate)}</b>
                    <span className="muted">（基线 {entry.baseline_items} 题 · 复测 {entry.retest_items} 题）</span>
                  </span>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="muted tiny">对比模型：{validation.model_version} · 小样本可观察对比，不是涨分结论。</p>
    </div>
  )
}

function fmtRate(value: number | undefined): string {
  if (value === undefined) return '—'
  const v = Math.round(value * 1000) / 10
  return `${Number.isInteger(v) ? v : v.toFixed(1)}%`
}
