<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
  describeError,
  SUBJECT_LABELS,
  type ApiClient,
  type KnowledgeEdge,
  type KnowledgeGraph,
  type KnowledgeMasteryItem,
  type MasteryStatus,
  type Subject,
} from '../api'
import { MASTERY_LABELS } from '../copy'
import { formatReleaseChineseName, getDomainLabel, getKnowledgeLabel } from '../config/knowledge'
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
const showLegend = ref(true)
const viewMode = ref<'graph' | 'list'>('graph')
const selectedCode = ref<string | null>(null)

interface PrereqLink {
  code: string
  name: string
  relation: string
  status: MasteryStatus
}

interface ModuleGroup {
  code: string
  name: string
  node: KnowledgeMasteryItem
  leaves: KnowledgeMasteryItem[]
}

interface DomainGroup {
  root: KnowledgeMasteryItem
  modules: ModuleGroup[]
  totalLeaves: number
  masteredCount: number
  weakCount: number
}

interface BridgeGroupRow {
  key: string
  sourceDomainName: string
  targetDomainName: string
  bridges: {
    key: string
    source: string
    sourceName: string
    target: string
    targetName: string
    relation: string
    weakWarning: boolean
    active: boolean
  }[]
}

function nodeDisplayName(node: KnowledgeMasteryItem): string {
  if (node.name && node.name !== node.code) return node.name
  return getKnowledgeLabel(node.code)
}

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
      const key = n.domain || n.code
      // 优先通过本地化领域词典映射，防止跨多根共享域时（如语文 reading）名称错乱
      const mapped = n.domain ? getDomainLabel(n.domain) : ''
      const label = mapped && mapped !== n.domain ? mapped : nodeDisplayName(n)
      if (!map.has(key)) {
        map.set(key, label)
      }
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

const nodeByCode = computed(() => {
  const map = new Map<string, KnowledgeMasteryItem>()
  for (const n of graph.value?.nodes ?? []) {
    map.set(n.code, n)
  }
  return map
})

// 预计算每个节点的前置基础与后续进阶关联表
const prereqRelations = computed(() => {
  const upstream = new Map<string, PrereqLink[]>()
  const downstream = new Map<string, PrereqLink[]>()
  const map = nodeByCode.value

  for (const e of graph.value?.edges ?? []) {
    if (e.edge_type !== 'prerequisite') continue
    const src = map.get(e.source)
    const tgt = map.get(e.target)
    if (!src || !tgt) continue

    const upList = upstream.get(tgt.code) ?? []
    upList.push({
      code: src.code,
      name: nodeDisplayName(src),
      relation: e.relation || '前置基础',
      status: src.mastery_status,
    })
    upstream.set(tgt.code, upList)

    const downList = downstream.get(src.code) ?? []
    downList.push({
      code: tgt.code,
      name: nodeDisplayName(tgt),
      relation: e.relation || '进阶应用',
      status: tgt.mastery_status,
    })
    downstream.set(src.code, downList)
  }

  return { upstream, downstream }
})

function getUpstream(code: string): PrereqLink[] {
  return prereqRelations.value.upstream.get(code) ?? []
}

function getDownstream(code: string): PrereqLink[] {
  return prereqRelations.value.downstream.get(code) ?? []
}

function hasWeakUpstream(code: string): boolean {
  return getUpstream(code).some(item => item.status === 'weak')
}

// 方案三核心数据结构：一级领域容器 -> 二级模块子盒 -> 三级/叶子知识点卡片
const nestedDomains = computed<DomainGroup[]>(() => {
  const nodes = filteredNodes.value
  if (nodes.length === 0) return []

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

  const collectLeaves = (startCode: string): KnowledgeMasteryItem[] => {
    const out: KnowledgeMasteryItem[] = []
    const visited = new Set<string>()
    const stack = [...(childrenMap.get(startCode) ?? [])].reverse()
    while (stack.length > 0) {
      const cur = stack.pop()!
      if (visited.has(cur.code)) continue
      visited.add(cur.code)
      const kids = childrenMap.get(cur.code) ?? []
      if (cur.is_leaf || kids.length === 0) {
        out.push(cur)
      } else {
        for (let i = kids.length - 1; i >= 0; i--) {
          stack.push(kids[i])
        }
      }
    }
    return out
  }

  return roots.map(root => {
    const directChildren = childrenMap.get(root.code) ?? []
    const modules: ModuleGroup[] = []
    const directLeaves: KnowledgeMasteryItem[] = []

    for (const child of directChildren) {
      const grandKids = childrenMap.get(child.code) ?? []
      if (!child.is_leaf || grandKids.length > 0) {
        const leaves = collectLeaves(child.code)
        modules.push({
          code: child.code,
          name: nodeDisplayName(child),
          node: child,
          leaves: leaves.length > 0 ? leaves : [child],
        })
      } else {
        directLeaves.push(child)
      }
    }

    if (directLeaves.length > 0) {
      modules.push({
        code: `${root.code}::direct`,
        name: modules.length > 0 ? '综合核心考点' : `${nodeDisplayName(root)}核心考点`,
        node: root,
        leaves: directLeaves,
      })
    }

    if (modules.length === 0) {
      modules.push({
        code: `${root.code}::self`,
        name: nodeDisplayName(root),
        node: root,
        leaves: [root],
      })
    }

    const allLeaves = modules.flatMap(m => m.leaves)
    return {
      root,
      modules,
      totalLeaves: allLeaves.length,
      masteredCount: allLeaves.filter(l => l.mastery_status === 'mastered').length,
      weakCount: allLeaves.filter(l => l.mastery_status === 'weak').length,
    }
  })
})

// 跨章 / 跨模块前置关联桥梁矩阵
const bridgeMatrixRows = computed<BridgeGroupRow[]>(() => {
  if (!graph.value) return []
  const map = nodeByCode.value
  const visibleSet = new Set(filteredNodes.value.map(n => n.code))

  const domainNameOf = (node: KnowledgeMasteryItem): string => {
    // 1. 优先从本地化配置解析标准领域英文编码（如 num_alg -> 数与代数）
    if (node.domain) {
      const mapped = getDomainLabel(node.domain)
      if (mapped && mapped !== node.domain) return mapped
    }
    // 2. 沿 parent_code 向上溯源至所属一级领域节点名称
    let cur: KnowledgeMasteryItem | undefined = node
    const seen = new Set<string>()
    while (cur?.parent_code && !seen.has(cur.code)) {
      seen.add(cur.code)
      const parent = map.get(cur.parent_code)
      if (!parent) break
      cur = parent
    }
    if (cur && cur.code !== node.code) {
      return nodeDisplayName(cur)
    }
    const domCode = node.domain || node.parent_code || node.code
    const domNode = map.get(domCode)
    return domNode ? nodeDisplayName(domNode) : getDomainLabel(domCode)
  }

  const grouped = new Map<string, BridgeGroupRow>()

  for (let i = 0; i < graph.value.edges.length; i++) {
    const e: KnowledgeEdge = graph.value.edges[i]
    if (e.edge_type !== 'prerequisite') continue
    if (domainFilter.value !== 'all' && !visibleSet.has(e.source) && !visibleSet.has(e.target)) {
      continue
    }
    const src = map.get(e.source)
    const tgt = map.get(e.target)
    if (!src || !tgt) continue

    const sDom = domainNameOf(src)
    const tDom = domainNameOf(tgt)
    const rowKey = `${sDom}=>${tDom}`
    let row = grouped.get(rowKey)
    if (!row) {
      row = {
        key: rowKey,
        sourceDomainName: sDom,
        targetDomainName: tDom,
        bridges: [],
      }
      grouped.set(rowKey, row)
    }

    row.bridges.push({
      key: `${e.source}-${e.target}-${i}`,
      source: src.code,
      sourceName: nodeDisplayName(src),
      target: tgt.code,
      targetName: nodeDisplayName(tgt),
      relation: e.relation || '前置支撑',
      weakWarning: src.mastery_status === 'weak',
      active: selectedCode.value === src.code || selectedCode.value === tgt.code,
    })
  }

  return Array.from(grouped.values())
})

const selectedNode = computed(() => {
  if (!graph.value || !selectedCode.value) return null
  return graph.value.nodes.find(n => n.code === selectedCode.value) ?? null
})

const selectedNodePrereqs = computed(() => {
  if (!selectedNode.value) {
    return { upstream: [] as PrereqLink[], downstream: [] as PrereqLink[] }
  }
  return {
    upstream: getUpstream(selectedNode.value.code),
    downstream: getDownstream(selectedNode.value.code),
  }
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

function nodeSubText(node: KnowledgeMasteryItem): string {
  if (node.observed_rate !== null && node.observed_rate !== undefined) {
    return fmtPct(node.observed_rate)
  }
  return MASTERY_LABELS[node.mastery_status] ?? '待测'
}

function nodeAriaLabel(node: KnowledgeMasteryItem): string {
  return `${nodeDisplayName(node)} ${nodeSubText(node)}`
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
            依据教育部 2022 版课标构建的正式知识体系（已自动排除选学*内容），采用「嵌套模块卡片 + 跨章关联矩阵」清晰呈现从属结构、先修桥梁与掌握状态。
          </p>
        </div>
        <div class="head-actions">
          <span
            v-if="graph?.release_version"
            class="chip good"
            :title="`技术版本号：${graph.release_version}`"
          >
            已发布版本：{{ formatReleaseChineseName(graph.release_version) }}
          </span>
          <button
            type="button"
            class="ghost small"
            @click="showLegend = !showLegend"
          >
            {{ showLegend ? '收起图例' : '展开图例' }}
          </button>
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
        <!-- 标准图例总览面板 -->
        <section v-if="showLegend" class="legend-board" aria-label="知识点关系与掌握度标准图例">
          <div class="legend-board-head">
            <strong>标准图例说明</strong>
            <span class="muted tiny">图谱同时以色彩与符号双编码区分掌握度，并用容器嵌套与跨章桥梁明确展示三种知识关系</span>
          </div>
          <div class="legend-grid">
            <div class="legend-section">
              <div class="legend-section-title">1. 层级与包含关系</div>
              <div class="legend-items">
                <span class="legend-chip container-box">虚线大框：一级知识领域</span>
                <span class="legend-chip module-box">浅色子盒：二级模块主题</span>
                <span class="legend-chip leaf-box">圆角卡片：三级/叶子核心考点</span>
              </div>
            </div>
            <div class="legend-section">
              <div class="legend-section-title">2. 先修依赖与阻断提醒</div>
              <div class="legend-items">
                <span class="legend-chip prereq-tag">⬅️ 先修：依赖上游基础</span>
                <span class="legend-chip down-tag">➡️ 支撑：开启后续专题</span>
                <span class="legend-chip warn-tag">🔒 先补前置：上游基础未掌握</span>
              </div>
            </div>
            <div class="legend-section">
              <div class="legend-section-title">3. 掌握度状态统计</div>
              <div class="legend-items" aria-label="图谱状态图例">
                <span class="legend-pill mastered">✓ 已掌握 ({{ graph.summary_counts.mastered_count ?? 0 }})</span>
                <span class="legend-pill weak">! 未掌握 / 待突破 ({{ graph.summary_counts.weak_count ?? 0 }})</span>
                <span class="legend-pill insufficient">◌ 证据不足 ({{ graph.summary_counts.insufficient_count ?? 0 }})</span>
                <span class="legend-pill untested">○ 暂未测验 ({{ graph.summary_counts.untested_count ?? 0 }})</span>
              </div>
            </div>
          </div>
        </section>

        <!-- 过滤控制条 -->
        <div class="graph-toolbar">
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

          <div class="filter-controls">
            <button
              type="button"
              :class="onlyWeakHighlight ? 'chip-btn selected' : 'chip-btn'"
              @click="onlyWeakHighlight = !onlyWeakHighlight"
            >
              仅高亮未掌握
            </button>
          </div>
        </div>

        <!-- 主体：方案三（跨章关联矩阵 + 嵌套模块卡片） / 清单视图 + 右侧详情栏 -->
        <div class="graph-workspace">
          <div v-if="viewMode === 'graph'" class="choice3-board">
            <!-- 跨章 / 跨模块前置关联桥梁矩阵 -->
            <div class="cross-matrix-card" aria-label="跨章前置关联桥梁矩阵">
              <div class="cross-matrix-head">
                <div>
                  <h3>跨章与先修关联桥梁</h3>
                  <p class="muted tiny">
                    彻底告别斜线交叉遮挡；点击下方任意关系桥梁，即可在右侧定位详情并跳转先修或进阶知识点。
                  </p>
                </div>
                <span class="chip subtle">{{ bridgeMatrixRows.reduce((acc, r) => acc + r.bridges.length, 0) }} 条前置关系</span>
              </div>

              <div v-if="bridgeMatrixRows.length > 0" class="matrix-table-scroll">
                <table class="rel-matrix-table">
                  <thead>
                    <tr>
                      <th>前置支撑领域</th>
                      <th>前置因果关联链（点击定位）</th>
                      <th>后继应用领域</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="row in bridgeMatrixRows" :key="row.key">
                      <td><span class="matrix-domain-tag">{{ row.sourceDomainName }}</span></td>
                      <td>
                        <div class="matrix-bridge-list">
                          <button
                            v-for="b in row.bridges"
                            :key="b.key"
                            type="button"
                            :class="[
                              'matrix-bridge-pill',
                              b.weakWarning ? 'has-warn' : '',
                              b.active ? 'active' : '',
                            ]"
                            @click="selectedCode = b.target"
                          >
                            <span class="bridge-src">{{ b.sourceName }}</span>
                            <span class="bridge-rel">──[{{ b.relation }}]──▶</span>
                            <span class="bridge-tgt">{{ b.targetName }}</span>
                            <span v-if="b.weakWarning" class="bridge-warn-dot" title="前置基础待突破">🔒</span>
                          </button>
                        </div>
                      </td>
                      <td><span class="matrix-domain-tag target">{{ row.targetDomainName }}</span></td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p v-else class="muted tiny">当前筛选范围内暂无跨节点先修依赖边，可在下方嵌套模块中浏览全部考点。</p>
            </div>

            <!-- 嵌套模块卡片主看板 -->
            <div
              class="nested-domains-grid"
              role="group"
              aria-label="知识点层级与前置关联图谱"
            >
              <section
                v-for="dom in nestedDomains"
                :key="dom.root.code"
                class="domain-container-card"
              >
                <header class="domain-container-head">
                  <div class="domain-head-title">
                    <h3>{{ nodeDisplayName(dom.root) }}</h3>
                    <span class="muted tiny">一级领域 · {{ dom.modules.length }} 个模块 · {{ dom.totalLeaves }} 项考点</span>
                  </div>
                  <div class="domain-head-stats">
                    <span class="mini-stat good">已掌握 {{ dom.masteredCount }}</span>
                    <span v-if="dom.weakCount > 0" class="mini-stat bad">待突破 {{ dom.weakCount }}</span>
                  </div>
                </header>

                <div class="module-grid">
                  <div
                    v-for="mod in dom.modules"
                    :key="mod.code"
                    class="module-subbox"
                  >
                    <div class="module-subbox-head">
                      <span class="module-subbox-title">{{ mod.name }}</span>
                      <span class="muted tiny">{{ mod.leaves.length }} 项</span>
                    </div>

                    <div class="leaf-rel-list">
                      <div
                        v-for="leaf in mod.leaves"
                        :key="leaf.code"
                        :class="[
                          'leaf-rel-item',
                          leaf.mastery_status,
                          selectedCode === leaf.code ? 'selected' : '',
                          isDimmed(leaf) ? 'dimmed' : '',
                        ]"
                      >
                        <button
                          type="button"
                          class="leaf-rel-btn"
                          :aria-label="nodeAriaLabel(leaf)"
                          @click="selectedCode = leaf.code"
                        >
                          <div class="leaf-rel-top">
                            <span class="leaf-rel-title">{{ nodeDisplayName(leaf) }}</span>
                            <span :class="['leaf-status-badge', leaf.mastery_status]">
                              {{ masteryIcon(leaf.mastery_status) }} {{ nodeSubText(leaf) }}
                            </span>
                          </div>
                        </button>

                        <div
                          v-if="hasWeakUpstream(leaf.code) || getUpstream(leaf.code).length > 0 || getDownstream(leaf.code).length > 0"
                          class="leaf-rel-badges"
                        >
                          <span v-if="hasWeakUpstream(leaf.code)" class="mini-rel-chip alert">
                            🔒 先补前置
                          </span>
                          <span
                            v-for="up in getUpstream(leaf.code).slice(0, 2)"
                            :key="`up-${leaf.code}-${up.code}`"
                            class="mini-rel-chip prereq"
                            :title="`前置基础：${up.name}（${up.relation}）`"
                          >
                            ⬅️ 先修：{{ up.name }}
                          </span>
                          <span
                            v-for="down in getDownstream(leaf.code).slice(0, 2)"
                            :key="`down-${leaf.code}-${down.code}`"
                            class="mini-rel-chip down"
                            :title="`支撑后续：${down.name}（${down.relation}）`"
                          >
                            ➡️ 支撑：{{ down.name }}
                          </span>
                          <span
                            v-if="getUpstream(leaf.code).length + getDownstream(leaf.code).length > 4"
                            class="mini-rel-chip more"
                          >
                            +{{ getUpstream(leaf.code).length + getDownstream(leaf.code).length - 4 }} 关联
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </section>
            </div>
          </div>

          <!-- 清单模式保留作为极简辅助视图 -->
          <div v-else class="graph-list-fallback" aria-label="知识点清单视图">
            <ul class="kg-list">
              <li
                v-for="node in filteredNodes"
                :key="node.code"
                :class="['kg-list-row', node.mastery_status, selectedCode === node.code ? 'selected' : '', isDimmed(node) ? 'dimmed' : '']"
              >
                <button type="button" class="kg-list-btn" @click="selectedCode = node.code">
                  <div>
                    <b>{{ nodeDisplayName(node) }}</b>
                    <small class="muted">{{ node.is_leaf ? '具体知识点' : '知识领域模块' }}</small>
                  </div>
                  <span :class="['legend-pill', node.mastery_status]">
                    {{ masteryIcon(node.mastery_status) }}
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
                {{ masteryIcon(selectedNode.mastery_status) }}
                {{ MASTERY_LABELS[selectedNode.mastery_status] ?? selectedNode.mastery_status }}
              </span>
              <h3>{{ nodeDisplayName(selectedNode) }}</h3>
            </div>
            <p class="muted">{{ selectedNode.description || '教育部 2022 版课标核心知识节点。' }}</p>

            <div v-if="hasWeakUpstream(selectedNode.code)" class="prereq-alert-box">
              <strong>学习路径建议：</strong>检测到该知识点依赖的前置基础尚未掌握，建议先巩固下方红色前置节点后再突破本专题。
            </div>

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
                  :class="['chip-btn', up.status === 'weak' ? 'prereq-weak-chip' : '']"
                  @click="selectedCode = up.code"
                >
                  ⬅️ {{ up.name }}<span class="muted tiny"> · {{ up.relation }}</span>
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
                  {{ down.name }} ➡️<span class="muted tiny"> · {{ down.relation }}</span>
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
