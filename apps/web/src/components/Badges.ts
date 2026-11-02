import { h } from 'vue'
import { GAP_LABELS, KIND_LABELS, PER_KNOWLEDGE_VERDICT_LABELS } from '../copy'
import type { GapType, Kind } from '../api'

export function GapBadge(props: { gap: GapType }) {
  return h('span', { class: `badge gap-${props.gap.toLowerCase()}` }, [
    GAP_LABELS[props.gap],
    h('code', props.gap),
  ])
}

export function KindBadge(props: { kind: Kind }) {
  return h('span', { class: 'badge kind' }, KIND_LABELS[props.kind])
}

export function VerdictChip(props: { verdict: 'improved' | 'no_improvement' | 'cannot_compare' }) {
  return h('span', { class: `badge verdict-${props.verdict}` }, PER_KNOWLEDGE_VERDICT_LABELS[props.verdict])
}
