<script setup lang="ts">
import { ref, watch } from 'vue'
import type { ApiClient } from '../api'

const props = defineProps<{
  client: ApiClient
  attachmentId: string
}>()

const status = ref<'loading' | 'ready' | 'error'>('loading')
const url = ref('')
const retry = ref(0)

watch(
  [() => props.client, () => props.attachmentId, retry],
  (_, __, onCleanup) => {
    let cancelled = false
    let objectUrl: string | null = null
    status.value = 'loading'

    props.client
      .fetchAttachment(props.attachmentId)
      .then(blob => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        url.value = objectUrl
        status.value = 'ready'
      })
      .catch(() => {
        if (!cancelled) status.value = 'error'
      })

    onCleanup(() => {
      cancelled = true
      if (objectUrl !== null) URL.revokeObjectURL(objectUrl)
    })
  },
  { immediate: true }
)
</script>

<template>
  <div class="audio">
    <span class="audio-label">听力材料</span>
    <audio v-if="status === 'ready'" controls :src="url" preload="metadata" />
    <span v-else-if="status === 'loading'" class="muted">音频加载中…</span>
    <template v-else-if="status === 'error'">
      <span class="muted">音频加载失败</span>
      <button type="button" class="ghost small" @click="retry++">
        重试
      </button>
    </template>
  </div>
</template>
