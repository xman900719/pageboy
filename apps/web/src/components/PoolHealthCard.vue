<script setup lang="ts">
import { computed } from 'vue'
import type { PoolHealth } from '../api'
import { getKnowledgeLabel } from '../config/knowledge'

const props = defineProps<{
  data: PoolHealth
}>()

const exposedTotal = computed(() =>
  props.data.knowledge.reduce((total, entry) => total + entry.exposed, 0)
)

// 计算未见题占已发布题量的比例（用于进度条展示）
function unseenRatio(published: number, unseen: number): number {
  if (published <= 0) return 0
  return Math.max(0, Math.min(100, Math.round((unseen / published) * 100)))
}
</script>

<template>
  <div class="pool-health">
    <div class="pool-kpi-grid">
      <div class="kpi-tile neutral">
        <b>{{ data.questions_published }} 题</b>
        <span>已发布题目总量</span>
      </div>
      <div class="kpi-tile ok">
        <b>{{ data.questions_unseen_for_evaluation }} 题</b>
        <span>未见题余量（可用于阶段诊断）</span>
      </div>
      <div class="kpi-tile wait">
        <b>{{ exposedTotal }} 题</b>
        <span>已曝光题目次</span>
      </div>
    </div>
    <p v-if="data.knowledge.length === 0" class="muted">暂无可体检的已发布知识点。</p>
    <ul v-else class="pool-card-grid">
      <li
        v-for="entry in data.knowledge"
        :key="entry.knowledge_id"
        :class="['pool-node-card', entry.unseen_for_evaluation === 0 ? 'empty-pool' : '']"
      >
        <div class="pool-node-head">
          <code class="kid">
            <span class="k-label">{{ getKnowledgeLabel(entry.knowledge_id) }}</span>
          </code>
          <span
            v-if="entry.unseen_for_evaluation === 0"
            class="chip bad"
          >
            暂无未见题余量
          </span>
          <span v-else class="chip good">
            未见余量充足
          </span>
        </div>
        <div class="bar-track" aria-hidden="true">
          <div
            class="bar-fill"
            :style="{ width: `${unseenRatio(entry.published, entry.unseen_for_evaluation)}%` }"
          />
        </div>
        <span class="step-facts">
          <span>
            已发布 <b>{{ entry.published }}</b>
          </span>
          <span>
            未见 <b>{{ entry.unseen_for_evaluation }}</b>
          </span>
          <span>
            已曝光 <b>{{ entry.exposed }}</b>
          </span>
        </span>
      </li>
    </ul>
    <p class="muted tiny disclaimer">{{ data.disclaimer }}</p>
  </div>
</template>
