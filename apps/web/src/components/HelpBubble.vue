<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

/**
 * 统一折叠式说明气泡组件（替代常驻占位的 Note 说明条与警告横幅）
 *
 * 交互规范：点击「?」触发器展开浮层，支持点击关闭按钮、点击气泡外部区域或按 Esc 键收起。
 */
const props = withDefaults(
  defineProps<{
    /** 气泡标题（同时作为无障碍 dialog 名称） */
    title: string
    /** 触发按钮显示文本，默认与标题一致 */
    label?: string
    /** 色彩倾向：teal 为规范/口径说明，caution 为红线/阻塞提醒 */
    tone?: 'teal' | 'caution'
    /** 浮层水平对齐方向，防止靠近边缘时溢出视口 */
    align?: 'right' | 'left'
    /** 紧凑模式，适合嵌套在小型卡片标题栏 */
    compact?: boolean
  }>(),
  {
    tone: 'teal',
    align: 'right',
    compact: false,
  }
)

const open = ref(false)
const anchorRef = ref<HTMLElement | null>(null)
const triggerRef = ref<HTMLButtonElement | null>(null)

function toggle() {
  open.value = !open.value
}

function close(restoreFocus = false) {
  if (!open.value) return
  open.value = false
  if (restoreFocus) {
    triggerRef.value?.focus()
  }
}

function handleDocumentPointerDown(event: PointerEvent) {
  if (!open.value) return
  const target = event.target as Node | null
  if (anchorRef.value && target && !anchorRef.value.contains(target)) {
    close(false)
  }
}

function handleDocumentKeydown(event: KeyboardEvent) {
  if (!open.value) return
  if (event.key === 'Escape') {
    event.preventDefault()
    close(true)
  }
}

onMounted(() => {
  document.addEventListener('pointerdown', handleDocumentPointerDown)
  document.addEventListener('keydown', handleDocumentKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', handleDocumentPointerDown)
  document.removeEventListener('keydown', handleDocumentKeydown)
})
</script>

<template>
  <div ref="anchorRef" class="help-bubble-anchor">
    <button
      ref="triggerRef"
      type="button"
      :class="[
        'help-trigger',
        props.tone === 'caution' ? 'tone-caution' : '',
        props.compact ? 'compact' : '',
      ]"
      :aria-expanded="open"
      @click="toggle"
    >
      <span class="help-dot" aria-hidden="true">?</span>
      <span>{{ props.label ?? props.title }}</span>
    </button>

    <div
      v-if="open"
      :class="[
        'help-popover',
        props.align === 'left' ? 'align-left' : '',
        props.tone === 'caution' ? 'tone-caution' : '',
      ]"
      role="dialog"
      :aria-label="props.title"
    >
      <div class="help-popover-head">
        <b>{{ props.title }}</b>
        <button type="button" class="help-close" aria-label="关闭说明" @click="close(true)">×</button>
      </div>
      <div class="help-popover-body">
        <slot />
      </div>
    </div>
  </div>
</template>
