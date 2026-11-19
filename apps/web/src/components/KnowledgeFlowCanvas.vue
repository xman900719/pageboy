<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import {
  Background,
  Handle,
  MiniMap,
  Position,
  VueFlow,
  setupVueFlow,
  type Node,
} from '@xyflow/vue'
import '@xyflow/vue/style.css'
import type { KnowledgeGraph, MasteryStatus } from '../api'
import { MASTERY_LABELS } from '../copy'
import {
  LEAF_NODE_HEIGHT,
  LEAF_NODE_WIDTH,
  buildKnowledgeFlowGraph,
  type DomainGroupNodeData,
  type KnowledgeLeafNodeData,
} from '../config/knowledgeFlowLayout'

const props = defineProps<{
  graph: KnowledgeGraph
  domainFilter: string
  onlyWeakHighlight: boolean
  selectedCode: string | null
}>()

const emit = defineEmits<{
  (e: 'select', code: string): void
}>()

const focusOnly = ref(false)
const isFullscreen = ref(false)
const currentZoom = ref(1)
const { fitView, zoomIn, zoomOut, getViewport } = setupVueFlow()

const built = computed(() =>
  buildKnowledgeFlowGraph(props.graph, {
    domainFilter: props.domainFilter,
    selectedCode: props.selectedCode,
    onlyWeakHighlight: props.onlyWeakHighlight,
    focusOnly: focusOnly.value,
  }),
)

const nodes = computed(() => built.value.nodes)
const edges = computed(() => built.value.edges)
const crossBridges = computed(() => built.value.crossDomainBridges)

const zoomPct = computed(() => Math.round(currentZoom.value * 100))

function masteryIcon(status: MasteryStatus): string {
  switch (status) {
    case 'mastered':
      return '✓'
    case 'weak':
      return '!'
    case 'insufficient':
      return '◌'
    default:
      return '○'
  }
}

function fmtPct(rate: number | null | undefined): string {
  if (rate === null || rate === undefined) return '样本不足'
  const val = Math.round(rate * 1000) / 10
  return `${Number.isInteger(val) ? val : val.toFixed(1)}%`
}

function nodeSubText(data: KnowledgeLeafNodeData): string {
  if (data.observedRate !== null && data.observedRate !== undefined) {
    return fmtPct(data.observedRate)
  }
  return MASTERY_LABELS[data.status] ?? '待测'
}

function miniMapNodeColor(node: Node): string {
  if (node.type === 'domainGroup') return 'rgba(233, 244, 238, 0.45)'
  const d = node.data as KnowledgeLeafNodeData | undefined
  if (!d) return '#cfc5b7'
  if (d.lineageRole === 'selected') return '#2a6f4e'
  if (d.lineageRole === 'upstream') return '#d97724'
  if (d.lineageRole === 'downstream') return '#265d75'
  if (d.status === 'weak') return '#a82e20'
  if (d.status === 'mastered') return '#236143'
  return '#cfc5b7'
}

async function runFitView() {
  await nextTick()
  if (nodes.value.length === 0) return
  await fitView({ padding: 0.06, duration: 220 })
  currentZoom.value = getViewport().zoom
}

async function focusSelectedNode() {
  if (!props.selectedCode) {
    void runFitView()
    return
  }
  await nextTick()
  await fitView({ nodes: [{ id: props.selectedCode }], padding: 0.9, maxZoom: 1.15, duration: 260 })
  currentZoom.value = getViewport().zoom
}

function toggleFocusOnly() {
  focusOnly.value = !focusOnly.value
}

function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
  void runFitView()
}

watch(
  [() => props.graph.subject, () => props.domainFilter, focusOnly],
  () => {
    void runFitView()
  },
  { flush: 'post' },
)

watch(
  () => props.graph.subject,
  () => {
    focusOnly.value = false
  },
)
</script>

<template>
  <div
    :class="['kg-flow-shell', isFullscreen ? 'is-fullscreen' : '']"
    role="group"
    aria-label="知识点层级与前置关联图谱"
  >
    <div class="kg-flow-toolbar">
      <div class="kg-flow-toolbar-group">
        <button
          type="button"
          :class="['flow-ctrl-btn', focusOnly ? 'active' : '']"
          :aria-pressed="focusOnly"
          :disabled="!selectedCode"
          @click="toggleFocusOnly"
        >
          {{ focusOnly ? '🕸️ 退出脉络子图（显示全部）' : '🕸️ 仅看选中脉络' }}
        </button>
        <button
          type="button"
          class="flow-ctrl-btn"
          :disabled="!selectedCode"
          @click="focusSelectedNode"
        >
          🎯 定位选中节点
        </button>
      </div>

      <div class="kg-flow-toolbar-group" role="group" aria-label="画布缩放控制">
        <button type="button" class="flow-ctrl-btn" @click="runFitView">
          ⛶ 自适应全览
        </button>
        <button
          type="button"
          class="flow-ctrl-btn icon-only"
          aria-label="缩小图谱"
          @click="zoomOut({ duration: 180 })"
        >
          －
        </button>
        <span class="flow-zoom-readout">{{ zoomPct }}%</span>
        <button
          type="button"
          class="flow-ctrl-btn icon-only"
          aria-label="放大图谱"
          @click="zoomIn({ duration: 180 })"
        >
          ＋
        </button>
        <button
          type="button"
          :class="['flow-ctrl-btn', isFullscreen ? 'active' : '']"
          :aria-pressed="isFullscreen"
          @click="toggleFullscreen"
        >
          {{ isFullscreen ? '✕ 退出全屏' : '⛶ 全屏放大' }}
        </button>
      </div>
    </div>

    <div v-if="nodes.length > 0" class="kg-flow-viewport">
      <VueFlow
        :nodes="nodes"
        :edges="edges"
        :nodes-draggable="false"
        :nodes-connectable="false"
        :nodes-focusable="false"
        :edges-focusable="false"
        :elements-selectable="false"
        :zoom-on-scroll="false"
        :pan-on-scroll="false"
        :prevent-scrolling="false"
        :min-zoom="0.32"
        :max-zoom="1.5"
        :fit-view-on-init="true"
        @pane-ready="runFitView"
        @viewport-change="currentZoom = $event.zoom"
      >
        <Background pattern-color="#d8cfc0" :gap="20" :size="1.2" />

        <MiniMap
          v-if="!focusOnly && built.leafCount > 8"
          class="kg-flow-minimap"
          pannable
          zoomable
          :node-color="miniMapNodeColor"
          :node-stroke-width="2"
        />

        <template #node-domainGroup="{ data }">
          <div class="kg-domain-group">
            <div class="kg-domain-group-head">
              <span class="kg-domain-group-title">{{ (data as DomainGroupNodeData).label }}</span>
              <span v-if="!(data as DomainGroupNodeData).hideStats" class="kg-domain-group-badge">
                已掌握 {{ (data as DomainGroupNodeData).masteredCount }}
                <template v-if="(data as DomainGroupNodeData).weakCount > 0">
                  · 待突破 {{ (data as DomainGroupNodeData).weakCount }}
                </template>
                / {{ (data as DomainGroupNodeData).totalLeaves }}
              </span>
            </div>
          </div>
        </template>

        <template #node-knowledgeLeaf="{ data }">
          <div
            class="kg-leaf-wrap"
            :style="{ width: `${LEAF_NODE_WIDTH}px`, height: `${LEAF_NODE_HEIGHT}px` }"
          >
            <Handle type="target" :position="Position.Top" class="kg-handle" aria-hidden="true" />
            <button
              type="button"
              :class="[
                'kg-leaf-card-btn',
                (data as KnowledgeLeafNodeData).status,
                (data as KnowledgeLeafNodeData).lineageRole === 'selected' ? 'is-selected' : '',
                (data as KnowledgeLeafNodeData).lineageRole === 'upstream' ? 'is-upstream' : '',
                (data as KnowledgeLeafNodeData).lineageRole === 'downstream' ? 'is-downstream' : '',
                (data as KnowledgeLeafNodeData).dimmed ? 'is-dimmed' : '',
              ]"
              :aria-pressed="(data as KnowledgeLeafNodeData).lineageRole === 'selected'"
              @click="emit('select', (data as KnowledgeLeafNodeData).item.code)"
            >
              <div class="kg-leaf-head-row">
                <span class="kg-leaf-title">{{ (data as KnowledgeLeafNodeData).displayName }}</span>
                <span
                  v-if="(data as KnowledgeLeafNodeData).lineageRole === 'selected'"
                  class="kg-role-tag sel"
                >
                  当前
                </span>
                <span
                  v-else-if="(data as KnowledgeLeafNodeData).lineageRole === 'upstream'"
                  class="kg-role-tag up"
                >
                  前置
                </span>
                <span
                  v-else-if="(data as KnowledgeLeafNodeData).lineageRole === 'downstream'"
                  class="kg-role-tag down"
                >
                  进阶
                </span>
              </div>
              <div class="kg-leaf-meta-row">
                <span :class="['kg-leaf-badge', (data as KnowledgeLeafNodeData).status]">
                  {{ masteryIcon((data as KnowledgeLeafNodeData).status) }}
                  {{ nodeSubText(data as KnowledgeLeafNodeData) }}
                </span>
                <span
                  v-if="(data as KnowledgeLeafNodeData).hasWeakUpstream"
                  class="kg-leaf-lock"
                  title="依赖的前置知识点尚未掌握"
                >
                  🔒 先补前置
                </span>
              </div>
            </button>
            <Handle type="source" :position="Position.Bottom" class="kg-handle" aria-hidden="true" />
          </div>
        </template>
      </VueFlow>
    </div>

    <div v-else class="kg-flow-empty muted">
      当前筛选范围内暂无可展示的知识点。
    </div>

    <div v-if="crossBridges.length > 0" class="kg-cross-strip" aria-label="跨领域先修桥梁快捷跳转">
      <span class="kg-cross-label">跨领域先修桥梁：</span>
      <button
        v-for="b in crossBridges"
        :key="b.key"
        type="button"
        :class="['kg-cross-pill', b.weakWarning ? 'has-warn' : '', b.active ? 'active' : '']"
        :title="`${b.sourceName} ➔ ${b.targetName}（${b.relation}）`"
        @click="emit('select', b.target)"
      >
        <span>{{ b.sourceName }} ➔ {{ b.targetName }}</span>
        <span v-if="b.weakWarning" aria-hidden="true">🔒</span>
      </button>
    </div>
  </div>
</template>
