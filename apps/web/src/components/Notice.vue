<script setup lang="ts">
import { watchEffect } from 'vue'

export type NoticeTone = 'info' | 'success' | 'caution' | 'error'
export type NoticeData = { text: string; tone: NoticeTone }

const props = defineProps<{
  notice: NoticeData | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

watchEffect((onCleanup) => {
  if (!props.notice) return
  const timer = window.setTimeout(() => emit('close'), 6000)
  onCleanup(() => window.clearTimeout(timer))
})
</script>

<template>
  <div v-if="notice" :class="['toast', notice.tone]" role="status">
    <span>{{ notice.text }}</span>
    <button type="button" @click="emit('close')" aria-label="关闭提示">
      ×
    </button>
  </div>
</template>
