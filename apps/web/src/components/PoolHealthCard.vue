<script setup lang="ts">
import { computed, ref } from 'vue'
import type { PoolHealth } from '../api'
import { getKnowledgeLabel } from '../config/knowledge'

const props = defineProps<{
  data: PoolHealth
  /** 是否在矩阵工作台中隐藏底部免责声明（改为顶部气泡承载） */
  hideDisclaimer?: boolean
}>()

const emit = defineEmits<{
  (e: 'fill-gap', knowledgeId: string): void
}>()

const filterMode = ref<'all' | 'empty' | 'ok'>('all')

const emptyCount = computed(
  () => props.data.knowledge.filter(entry => entry.unseen_for_evaluation === 0).length
)
const sufficientCount = computed(
  () => props.data.knowledge.filter(entry => entry.unseen_for_evaluation > 0).length
)

const visibleKnowledge = computed(() => {
  if (filterMode.value === 'empty') {
    return props.data.knowledge.filter(entry => entry.unseen_for_evaluation === 0)
  }
  if (filterMode.value === 'ok') {
    return props.data.knowledge.filter(entry => entry.unseen_for_evaluation > 0)
  }
  return props.data.knowledge
})

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
    <div v-if="data.knowledge.length > 0" class="pool-filter-bar">
      <div class="pool-filter-tabs" role="group" aria-label="按未见题余量筛选知识点">
        <button
          type="button"
          :class="filterMode === 'all' ? 'chip-btn selected' : 'chip-btn'"
          @click="filterMode = 'all'"
        >
          全部知识点 ({{ data.knowledge.length }})
        </button>
        <button
          type="button"
          :class="filterMode === 'empty' ? 'chip-btn selected' : 'chip-btn'"
          @click="filterMode = 'empty'"
        >
          零余量告警 ({{ emptyCount }})
        </button>
        <button
          type="button"
          :class="filterMode === 'ok' ? 'chip-btn selected' : 'chip-btn'"
          @click="filterMode = 'ok'"
        >
          余量充足 ({{ sufficientCount }})
        </button>
      </div>
    </div>
    <p v-if="data.knowledge.length === 0" class="muted">暂无可体检的已发布知识点。</p>
    <p v-else-if="visibleKnowledge.length === 0" class="muted">当前筛选条件下没有对应知识点。</p>
    <ul v-else class="pool-card-grid" tabindex="0" aria-label="知识点余量体检网格">
      <li
        v-for="entry in visibleKnowledge"
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
        <div v-if="entry.unseen_for_evaluation === 0" class="pool-node-foot">
          <button
            type="button"
            class="ghost small"
            @click="emit('fill-gap', entry.knowledge_id)"
          >
            去补录新题
          </button>
        </div>
      </li>
    </ul>
    <p v-if="!props.hideDisclaimer" class="muted tiny disclaimer">{{ data.disclaimer }}</p>
  </div>
</template>
