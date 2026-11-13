<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
  describeError,
  SUBJECT_LABELS,
  type ApiClient,
  type KnowledgeEdge,
  type KnowledgeGraph,
  type KnowledgeMasteryItem,
  type Subject,
} from '../api'
import { MASTERY_LABELS } from '../copy'
import type { NoticeTone } from '../components/Notice.vue'

const props = defineProps<{
  client: ApiClient
  subject: Subject
  notify: (text: string, tone?: NoticeTone) => void
}>()

const emit = defineEmits<{
  (e: 'goPracticeFocus', code: string): void
}>()

const graph = ref<KnowledgeGraph | null>(null)
const loading = ref(false)
const error = ref('')

const domainFilter = ref<string>('all')
const onlyWeakHighlight = ref(false)
const viewMode = ref<'graph' | 'list'>('graph')
const zoom = ref(1)
const selectedCode = ref<string | null>(null)

async function loadGraph() {
  loading.value = true
  error.value = ''
  try {
    const data = await props.client.knowledgeGraph(props.subject)
    graph.value = data
    if (data.nodes.length > 0 && !data.nodes.some(n => n.code === selectedCode.value)) {
      const firstWeak = data.nodes.find(n => n.is_leaf && n.mastery_status === 'weak')
      const firstLeaf = data.nodes.find(n => n.is_leaf)
      selectedCode.value = (firstWeak ?? firstLeaf ?? data.nodes[0]).code
    }
  } catch (e) {
    error.value = describeError(e)
  } finally {
    loading.value = false
  }
}

const topDomains = computed(() => {
  if (!graph.value) return []
  const map = new Map<string, string>()
  for (const n of graph.value.nodes) {
    if (!n.parent_code) {
      map.set(n.domain || n.code, n.name)
    }
  }
  return Array.from(map.entries()).map(([key, name]) => ({ key, name }))
})

const filteredNodes = computed(() => {
  if (!graph.value) return []
  return graph.value.nodes.filter(n => {
    if (domainFilter.value !== 'all') {
      const matchDomain = n.domain === domainFilter.value || n.code === domainFilter.value
      if (!matchDomain) return false
    }
    return true
  })
})

interface PositionedNode extends KnowledgeMasteryItem {
  x: number
  y: number
  w: number
  h: number
}

// 计算确定性层次结构图谱坐标：一级领域在顶行，二级/三级子节点错落展开
const graphLayout = computed(() => {
  const nodes = filteredNodes.value
  if (nodes.length === 0) {
    return { width: 920, height: 420, positioned: [] as PositionedNode[], edges: [] as { key: string; d: string; edge: KnowledgeEdge; active: boolean }[] }
  }

  const byCode = new Map(nodes.map(n => [n.code, n]))
  const childrenMap = new Map<string, KnowledgeMasteryItem[]>()
  const roots: KnowledgeMasteryItem[] = []
  for (const n of nodes) {
    if (!n.parent_code || !byCode.has(n.parent_code)) {
      roots.push(n)
    } else {
      const list = childrenMap.get(n.parent_code) ?? []
      list.push(n)
      childrenMap.set(n.parent_code, list)
    }
  }

  // 按领域列组水平排版，确保同一大模块及其叶子节点紧凑清晰、永不重叠
  const positionedMap = new Map<string, PositionedNode>()
  let cursorX = 36
  const colGap = 28
  const cardW = 148
  const cardH = 44
  const leafGapX = 16
  const leafPerRow = domainFilter.value === 'all' ? 2 : 3

  let maxY = 360

  for (const root of roots) {
    // 收集该一级根下的直系二级和叶子层级
    const level2 = childrenMap.get(root.code) ?? []
    const allDescendants: KnowledgeMasteryItem[] = []
    const walk = (parentCode: string) => {
      for (const ch of childrenMap.get(parentCode) ?? []) {
        allDescendants.push(ch)
        walk(ch.code)
      }
    }
    walk(root.code)

    const colCols = Math.min(leafPerRow, Math.max(1, allDescendants.length === 1 ? 1 : leafPerRow))
    const groupWidth = Math.max(180, colCols * cardW + (colCols - 1) * leafGapX)

    // 放根节点
    positionedMap.set(root.code, {
      ...root,
      x: cursorX + groupWidth / 2 - 84,
      y: 28,
      w: 168,
      h: 46,
    })

    // 若存在中间层且同时存在第3层，分两层排；否则紧凑两层排布
    const hasLevel3 = level2.some(mid => (childrenMap.get(mid.code) ?? []).length > 0)
    let curY = 114
    if (!hasLevel3) {
      allDescendants.forEach((child, idx) => {
        const col = idx % colCols
        const row = Math.floor(idx / colCols)
        const nx = cursorX + col * (cardW + leafGapX)
        const ny = curY + row * (cardH + 22)
        positionedMap.set(child.code, { ...child, x: nx, y: ny, w: cardW, h: cardH })
        maxY = Math.max(maxY, ny + cardH + 40)
      })
    } else {
      let leafRowOffset = 0
      level2.forEach((mid, mIdx) => {
        const mx = cursorX + (mIdx % colCols) * (cardW + leafGapX)
        const my = 108 + Math.floor(mIdx / colCols) * 64
        positionedMap.set(mid.code, { ...mid, x: mx, y: my, w: cardW, h: 42 })
        leafRowOffset = Math.max(leafRowOffset, my + 74)
      })
      let leafIdx = 0
      for (const mid of level2) {
        for (const lf of childrenMap.get(mid.code) ?? []) {
          const col = leafIdx % colCols
          const row = Math.floor(leafIdx / colCols)
          const lx = cursorX + col * (cardW + leafGapX)
          const ly = leafRowOffset + row * (cardH + 22)
          positionedMap.set(lf.code, { ...lf, x: lx, y: ly, w: cardW, h: cardH })
          maxY = Math.max(maxY, ly + cardH + 40)
          leafIdx += 1
        }
      }
    }

    cursorX += groupWidth + colGap
  }

  const totalWidth = Math.max(820, cursorX + 20)
  const validCodes = new Set(positionedMap.keys())
  const edges = (graph.value?.edges ?? [])
    .filter(e => validCodes.has(e.source) && validCodes.has(e.target))
    .map((e, i) => {
      const s = positionedMap.get(e.source)!
      const t = positionedMap.get(e.target)!
      const x1 = s.x + s.w / 2
      const y1 = s.y + s.h
      const x2 = t.x + t.w / 2
      const y2 = t.y
      const cy = (y1 + y2) / 2
      const d =
        e.edge_type === 'prerequisite'
          ? `M ${x1} ${s.y + s.h / 2} C ${x1} ${cy + 24}, ${x2} ${cy - 24}, ${x2} ${t.y + t.h / 2}`
          : `M ${x1} ${y1} C ${x1} ${cy}, ${x2} ${cy}, ${x2} ${y2}`
      const active = selectedCode.value === e.source || selectedCode.value === e.target
      return { key: `${e.edge_type}-${e.source}-${e.target}-${i}`, d, edge: e, active }
    })

  return {
    width: totalWidth,
    height: maxY,
    positioned: Array.from(positionedMap.values()),
    edges,
  }
})

const selectedNode = computed(() => {
  if (!graph.value || !selectedCode.value) return null
  return graph.value.nodes.find(n => n.code === selectedCode.value) ?? null
})

const selectedNodePrereqs = computed(() => {
  if (!graph.value || !selectedNode.value) return { upstream: [] as { code: string; name: string; relation: string }[], downstream: [] as { code: string; name: string; relation: string }[] }
  const byCode = new Map(graph.value.nodes.map(n => [n.code, n.name]))
  const upstream = graph.value.edges
    .filter(e => e.edge_type === 'prerequisite' && e.target === selectedNode.value?.code)
    .map(e => ({ code: e.source, name: byCode.get(e.source) ?? e.source, relation: e.relation }))
  const downstream = graph.value.edges
    .filter(e => e.edge_type === 'prerequisite' && e.source === selectedNode.value?.code)
    .map(e => ({ code: e.target, name: byCode.get(e.target) ?? e.target, relation: e.relation }))
  return { upstream, downstream }
})

function isDimmed(node: KnowledgeMasteryItem): boolean {
  if (!onlyWeakHighlight.value) return false
  return node.mastery_status !== 'weak'
}

function fmtPct(rate: number | null | undefined): string {
  if (rate === null || rate === undefined) return '样本不足'
  const val = Math.round(rate * 1000) / 10
  return `${Number.isInteger(val) ? val : val.toFixed(1)}%`
}

function nodeTitleText(node: KnowledgeMasteryItem): string {
  return node.name.length > 10 ? `${node.name.slice(0, 10)}…` : node.name
}

function nodeSubText(node: KnowledgeMasteryItem): string {
  if (node.observed_rate !== null && node.observed_rate !== undefined) {
    return fmtPct(node.observed_rate)
  }
  return MASTERY_LABELS[node.mastery_status] ?? '待测'
}

function nodeAriaLabel(node: KnowledgeMasteryItem): string {
  const title = nodeTitleText(node)
  const sub = nodeSubText(node)
  return node.name.length > 10 ? `${title} ${sub}（${node.name}）` : `${title} ${sub}`
}

function startFocusedPractice() {
  if (!selectedNode.value) return
  if (selectedNode.value.is_leaf || !graph.value) {
    emit('goPracticeFocus', selectedNode.value.code)
    return
  }
  const all = graph.value.nodes
  const descendants: KnowledgeMasteryItem[] = []
  const stack = [selectedNode.value.code]
  const seen = new Set<string>()
  while (stack.length > 0) {
    const cur = stack.pop()!
    if (seen.has(cur)) continue
    seen.add(cur)
    for (const n of all) {
      if (n.parent_code === cur) {
        if (n.is_leaf) descendants.push(n)
        else stack.push(n.code)
      }
    }
  }
  const preferred =
    descendants.find(n => n.mastery_status === 'weak') ??
    descendants.find(n => n.mastery_status === 'untested') ??
    descendants.find(n => n.mastery_status === 'insufficient') ??
    descendants[0]
  emit('goPracticeFocus', preferred ? preferred.code : selectedNode.value.code)
}

watch(
  [() => props.client, () => props.subject],
  () => {
    domainFilter.value = 'all'
    selectedCode.value = null
    zoom.value = 1
    void loadGraph()
  },
  { immediate: true }
)
</script>

<template>
  <div class="view-stack">
    <section class="card" aria-label="知识点关系图谱展示">
      <div class="card-head">
        <div>
          <h2>{{ SUBJECT_LABELS[subject] }}知识点关系图谱</h2>
          <p class="card-sub">
            依据教育部 2022 版课标构建的正式知识体系（已自动排除选学*内容），直观标注层级与前置关联，高亮尚未掌握的知识点。
          </p>
        </div>
        <div class="head-actions">
          <span v-if="graph?.release_version" class="chip good">
            已发布版本：{{ graph.release_version }}
          </span>
          <button type="button" class="ghost small" @click="viewMode = viewMode === 'graph' ? 'list' : 'graph'">
            {{ viewMode === 'graph' ? '切换清单视图' : '切换图谱视图' }}
          </button>
          <button type="button" class="ghost small" @click="loadGraph" :disabled="loading">
            {{ loading ? '刷新中…' : '刷新图谱' }}
          </button>
        </div>
      </div>

      <p v-if="error" class="form-error">{{ error }}</p>

      <template v-if="graph">
        <!-- 图例与过滤栏 -->
        <div class="graph-toolbar">
          <div class="legend-row" aria-label="图谱状态图例">
            <span class="legend-pill mastered">● 已掌握 ({{ graph.summary_counts.mastered_count ?? 0 }})</span>
            <span class="legend-pill weak">● 未掌握 / 待突破 ({{ graph.summary_counts.weak_count ?? 0 }})</span>
            <span class="legend-pill insufficient">● 证据不足 ({{ graph.summary_counts.insufficient_count ?? 0 }})</span>
            <span class="legend-pill untested">● 暂未测验 ({{ graph.summary_counts.untested_count ?? 0 }})</span>
            <span class="legend-edge">── 所属模块 &nbsp;&nbsp; ┄▶ 前置知识关联</span>
          </div>

          <div class="filter-controls">
            <button
              type="button"
              :class="onlyWeakHighlight ? 'chip-btn selected' : 'chip-btn'"
              @click="onlyWeakHighlight = !onlyWeakHighlight"
            >
              仅高亮未掌握
            </button>
            <div v-if="viewMode === 'graph'" class="zoom-controls" role="group" aria-label="画布缩放">
              <button type="button" class="ghost small" @click="zoom = Math.max(0.65, Number((zoom - 0.15).toFixed(2)))">－</button>
              <span class="muted tiny">{{ Math.round(zoom * 100) }}%</span>
              <button type="button" class="ghost small" @click="zoom = Math.min(1.45, Number((zoom + 0.15).toFixed(2)))">＋</button>
            </div>
          </div>
        </div>

        <div class="domain-filter-strip" role="group" aria-label="按领域筛选图谱">
          <button
            type="button"
            :class="domainFilter === 'all' ? 'chip-btn selected' : 'chip-btn'"
            @click="domainFilter = 'all'"
          >
            全部领域 ({{ graph.nodes.length }})
          </button>
          <button
            v-for="dom in topDomains"
            :key="dom.key"
            type="button"
            :class="domainFilter === dom.key ? 'chip-btn selected' : 'chip-btn'"
            @click="domainFilter = dom.key"
          >
            {{ dom.name }}
          </button>
        </div>

        <!-- 主体：SVG 图谱画布 / 清单切换 + 右侧详情面板 -->
        <div class="graph-workspace">
          <div v-if="viewMode === 'graph'" class="graph-canvas-scroll" aria-label="交互式知识图谱画布">
            <svg
              :width="Math.round(graphLayout.width * zoom)"
              :height="Math.round(graphLayout.height * zoom)"
              :viewBox="`0 0 ${graphLayout.width} ${graphLayout.height}`"
              class="kg-svg"
              role="group"
              aria-label="知识点层级与前置关联图谱"
            >
              <defs>
                <marker
                  id="prereq-arrow"
                  viewBox="0 0 10 10"
                  refX="8"
                  refY="5"
                  markerWidth="6"
                  markerHeight="6"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 1 L 8 5 L 0 9 z" fill="#b45309" />
                </marker>
              </defs>

              <!-- 边渲染 -->
              <path
                v-for="item in graphLayout.edges"
                :key="item.key"
                :d="item.d"
                :class="[
                  'kg-edge',
                  item.edge.edge_type,
                  item.active ? 'active' : '',
                ]"
                :marker-end="item.edge.edge_type === 'prerequisite' ? 'url(#prereq-arrow)' : undefined"
              />

              <!-- 节点渲染 -->
              <g
                v-for="node in graphLayout.positioned"
                :key="node.code"
                :transform="`translate(${node.x}, ${node.y})`"
                :class="[
                  'kg-node',
                  node.mastery_status,
                  node.is_leaf ? 'leaf' : 'hub',
                  selectedCode === node.code ? 'selected' : '',
                  isDimmed(node) ? 'dimmed' : '',
                ]"
                tabindex="0"
                role="button"
                :aria-label="nodeAriaLabel(node)"
                @click="selectedCode = node.code"
                @keydown.enter.prevent="selectedCode = node.code"
              >
                <rect :width="node.w" :height="node.h" rx="10" ry="10" />
                <text :x="node.w / 2" y="20" text-anchor="middle" class="kg-node-title">
                  {{ nodeTitleText(node) }}
                </text>
                <text :x="node.w / 2" y="35" text-anchor="middle" class="kg-node-sub">
                  {{ nodeSubText(node) }}
                </text>
              </g>
            </svg>
          </div>

          <div v-else class="graph-list-fallback" aria-label="知识点清单视图">
            <ul class="kg-list">
              <li
                v-for="node in filteredNodes"
                :key="node.code"
                :class="['kg-list-row', node.mastery_status, selectedCode === node.code ? 'selected' : '', isDimmed(node) ? 'dimmed' : '']"
              >
                <button type="button" class="kg-list-btn" @click="selectedCode = node.code">
                  <div>
                    <b>{{ node.name }}</b>
                    <small class="muted">{{ node.is_leaf ? '具体知识点' : '知识领域模块' }}</small>
                  </div>
                  <span :class="['legend-pill', node.mastery_status]">
                    {{ MASTERY_LABELS[node.mastery_status] ?? node.mastery_status }}
                    <template v-if="node.observed_rate !== null && node.observed_rate !== undefined">
                      · {{ fmtPct(node.observed_rate) }}
                    </template>
                  </span>
                </button>
              </li>
            </ul>
          </div>

          <!-- 节点详情边栏 -->
          <aside v-if="selectedNode" class="kg-detail-panel" aria-label="选中知识点详情">
            <div class="detail-head">
              <span :class="['legend-pill', selectedNode.mastery_status]">
                {{ MASTERY_LABELS[selectedNode.mastery_status] ?? selectedNode.mastery_status }}
              </span>
              <h3>{{ selectedNode.name }}</h3>
            </div>
            <p class="muted">{{ selectedNode.description || '教育部 2022 版课标核心知识节点。' }}</p>

            <div class="detail-stats">
              <div>
                <small class="muted">有效独立样本</small>
                <b>{{ selectedNode.sample_size }} 题</b>
              </div>
              <div>
                <small class="muted">实测得分率</small>
                <b>{{ fmtPct(selectedNode.observed_rate) }}</b>
              </div>
            </div>

            <div v-if="selectedNodePrereqs.upstream.length > 0" class="rel-block">
              <h4>前置基础知识点</h4>
              <div class="rel-chips">
                <button
                  v-for="up in selectedNodePrereqs.upstream"
                  :key="up.code"
                  type="button"
                  class="chip-btn"
                  @click="selectedCode = up.code"
                >
                  ← {{ up.name }}
                </button>
              </div>
            </div>

            <div v-if="selectedNodePrereqs.downstream.length > 0" class="rel-block">
              <h4>后续进阶知识点</h4>
              <div class="rel-chips">
                <button
                  v-for="down in selectedNodePrereqs.downstream"
                  :key="down.code"
                  type="button"
                  class="chip-btn"
                  @click="selectedCode = down.code"
                >
                  {{ down.name }} →
                </button>
              </div>
            </div>

            <div class="detail-actions">
              <button
                type="button"
                class="primary"
                @click="startFocusedPractice"
              >
                针对此知识点开始练习
              </button>
            </div>
          </aside>
        </div>
      </template>
    </section>
  </div>
</template>
