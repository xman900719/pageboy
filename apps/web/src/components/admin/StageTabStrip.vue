<script setup lang="ts">
import type { StageGroup } from './stepFlow'

const props = withDefaults(
  defineProps<{
    groups: StageGroup[]
    modelValue: string
    regionLabel?: string
    idPrefix: string
    panelIdPrefix?: string
  }>(),
  {
    regionLabel: '工作区阶段导航',
    panelIdPrefix: '',
  },
)

const emit = defineEmits<{
  (e: 'update:modelValue', id: string): void
}>()

const colsClass = props.groups.length <= 3 ? 'cols-3' : 'cols-4'

function resolvedPanelPrefix(): string {
  return props.panelIdPrefix || `${props.idPrefix}-panel-`
}
</script>

<template>
  <div class="stage-strip-wrap" role="region" :aria-label="regionLabel">
    <div :class="['stage-strip', colsClass]">
      <div
        v-for="group in groups"
        :key="group.id"
        :class="['stage-group', group.tabs.some(t => t.id === modelValue) ? 'active-group' : '']"
      >
        <div class="stage-head">
          <span>{{ group.title }}</span>
        </div>
        <div class="stage-group-tabs" role="tablist" :aria-label="group.title">
          <button
            v-for="tab in group.tabs"
            :key="tab.id"
            :id="`${idPrefix}-tab-${tab.id}`"
            type="button"
            role="tab"
            :aria-selected="modelValue === tab.id"
            :aria-controls="modelValue === tab.id ? `${resolvedPanelPrefix()}${tab.id}` : undefined"
            :class="[
              'stage-tab-btn',
              modelValue === tab.id ? 'active' : tab.done ? 'done-tab' : '',
            ]"
            @click="emit('update:modelValue', tab.id)"
          >
            <span class="stage-tab-title">{{ tab.title }}</span>
            <span class="stage-tab-trailing">
              <span
                v-if="tab.badge"
                :class="['admin-subtab-badge', tab.wait ? 'wait' : '']"
              >
                {{ tab.badge }}
              </span>
              <span v-if="tab.done && modelValue !== tab.id" class="stage-tab-check" aria-hidden="true">✓</span>
            </span>
          </button>
        </div>
      </div>
    </div>
    <div v-if="$slots.tools" class="stage-strip-tools">
      <slot name="tools" />
    </div>
  </div>
</template>
