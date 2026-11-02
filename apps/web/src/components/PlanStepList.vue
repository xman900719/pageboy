<script setup lang="ts">
import { ACTION_LABELS, pct } from '../copy'
import type { PlanStep, ProfileEntry } from '../api'
import { GapBadge } from './Badges'

defineProps<{
  steps: PlanStep[]
  threshold: number
  profiles?: Record<string, ProfileEntry>
}>()

const emit = defineEmits<{
  (e: 'goPractice'): void
  (e: 'goDiagnosis'): void
}>()
</script>

<template>
  <ul v-if="steps.length === 0" class="steps">
    <li class="step">暂无已发布知识点：请先在管理端导入、审核并发布题目。</li>
  </ul>
  <ul v-else class="steps">
    <li
      v-for="step in steps"
      :key="step.knowledge_id"
      :class="['step', `gap-${step.gap_type.toLowerCase()}`]"
    >
      <div class="step-head">
        <code class="kid">{{ step.knowledge_id }}</code>
        <GapBadge :gap="step.gap_type" />
      </div>
      <p class="step-reason">{{ step.reason }}</p>
      <div class="step-facts">
        <span v-if="step.gap_type === 'KNOWLEDGE_GAP' && step.observed_rate !== undefined">
          观察作答率 <b>{{ pct(step.observed_rate) }}</b> · 规划阈值 <b>{{ pct(threshold) }}</b>（未校准假设）
        </span>
        <span v-if="profiles?.[step.knowledge_id]">
          独立题样本 {{ profiles[step.knowledge_id].sample_size }} 题
        </span>
        <span v-if="ACTION_LABELS[step.action]" class="muted">
          {{ ACTION_LABELS[step.action] }}
        </span>
        <button
          v-if="step.gap_type === 'INSUFFICIENT_EVIDENCE'"
          type="button"
          class="ghost small"
          @click="emit('goDiagnosis')"
        >
          去诊断
        </button>
        <button
          v-if="step.gap_type === 'KNOWLEDGE_GAP'"
          type="button"
          class="ghost small"
          @click="emit('goPractice')"
        >
          去练习
        </button>
      </div>
    </li>
  </ul>
</template>
