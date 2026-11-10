<script setup lang="ts">
import { computed } from 'vue'
import { CANNOT_COMPARE_EXPLAIN, VALIDATION_HEADLINES } from '../copy'
import type { Validation } from '../api'
import { VerdictChip } from './Badges'

const props = defineProps<{
  validation: Validation
}>()

const headline = computed(() => VALIDATION_HEADLINES[props.validation.verdict] ?? props.validation.verdict)
const bannerTone = computed(() =>
  props.validation.verdict === 'IMPROVED_ON_COMPARABLE_SCOPE'
    ? 'good'
    : props.validation.verdict === 'CANNOT_COMPARE'
      ? 'caution'
      : 'neutral'
)

function fmtRate(value: number | undefined): string {
  if (value === undefined) return '—'
  const v = Math.round(value * 1000) / 10
  return `${Number.isInteger(v) ? v : v.toFixed(1)}%`
}
</script>

<template>
  <div class="validation">
    <div :class="['verdict-banner', bannerTone]">
      <b>{{ headline }}</b>
      <p>{{ validation.disclaimer }}</p>
    </div>
    <p v-if="validation.verdict === 'CANNOT_COMPARE'" class="muted">{{ CANNOT_COMPARE_EXPLAIN }}</p>
    <p v-if="validation.knowledge.length === 0" class="muted">还没有可用于对比的独立验证记录。</p>
    <ul v-else class="comparison">
      <li v-for="entry in validation.knowledge" :key="entry.topic">
        <span class="comp-topic">{{ entry.topic }}</span>
        <span v-if="entry.verdict === 'cannot_compare'" class="comp-main">
          <VerdictChip verdict="cannot_compare" />
          <span class="muted">
            {{ entry.reason === 'insufficient_retest' ? '复测侧独立题不足' : '基线侧独立题不足' }}
            （基线 {{ entry.baseline_items }} 题 · 复测 {{ entry.retest_items }} 题）
          </span>
        </span>
        <span v-else class="comp-main">
          <VerdictChip :verdict="entry.verdict" />
          <span>
            基线 <b>{{ fmtRate(entry.baseline_rate) }}</b> → 复测 <b>{{ fmtRate(entry.retest_rate) }}</b>
            <span class="muted">（基线 {{ entry.baseline_items }} 题 · 复测 {{ entry.retest_items }} 题）</span>
          </span>
        </span>
      </li>
    </ul>
    <p class="muted tiny">对比模型：{{ validation.model_version }} · 小样本可观察对比，不是涨分结论。</p>
  </div>
</template>
