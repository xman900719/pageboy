<script setup lang="ts">
withDefaults(
  defineProps<{
    tone?: 'neutral' | 'caution' | 'discipline'
    title?: string
  }>(),
  {
    tone: 'neutral',
  }
)
</script>

<template>
  <div :class="['note', tone]">
    <b v-if="title" class="note-title">{{ title }}</b>
    <div class="note-body">
      <slot />
    </div>
  </div>
</template>
