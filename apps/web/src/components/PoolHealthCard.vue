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
</script>

<template>
  <div class="pool-health">
    <div class="goal-summary">
      <span class="goal-stat">已发布 {{ data.questions_published }} 题</span>
      <span class="goal-stat">未见题余量 {{ data.questions_unseen_for_evaluation }} 题</span>
      <span class="goal-stat">已曝光 {{ exposedTotal }} 题</span>
    </div>
    <p v-if="data.knowledge.length === 0" class="muted">暂无可体检的已发布知识点。</p>
    <ul v-else class="comparison">
      <li v-for="entry in data.knowledge" :key="entry.knowledge_id">
        <code class="kid">
          <span class="k-label">{{ getKnowledgeLabel(entry.knowledge_id) }}</span>
          <span class="k-code"> · {{ entry.knowledge_id }}</span>
        </code>
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
          <span v-if="entry.unseen_for_evaluation === 0" class="muted">暂无未见题余量</span>
        </span>
      </li>
    </ul>
    <p class="muted tiny disclaimer">{{ data.disclaimer }}</p>
  </div>
</template>
