import { GAP_LABELS, KIND_LABELS, PER_KNOWLEDGE_VERDICT_LABELS } from '../copy'
import type { GapType, Kind } from '../api'

export function GapBadge({ gap }: { gap: GapType }) {
  return (
    <span className={`badge gap-${gap.toLowerCase()}`}>
      {GAP_LABELS[gap]}
      <code>{gap}</code>
    </span>
  )
}

export function KindBadge({ kind }: { kind: Kind }) {
  return <span className="badge kind">{KIND_LABELS[kind]}</span>
}

export function VerdictChip({ verdict }: { verdict: 'improved' | 'no_improvement' | 'cannot_compare' }) {
  return <span className={`badge verdict-${verdict}`}>{PER_KNOWLEDGE_VERDICT_LABELS[verdict]}</span>
}
