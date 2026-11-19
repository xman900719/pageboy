<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
  describeError,
  SUBJECT_LABELS,
  type ApiClient,
  type KnowledgeGameSubjectConfig,
  type KnowledgeGraph,
  type KnowledgeMasteryItem,
  type MasteryStatus,
  type Subject,
} from '../api'
import { MASTERY_LABELS } from '../copy'
import { formatReleaseChineseName, getDomainLabel, getKnowledgeLabel } from '../config/knowledge'
import { DEFAULT_GAME_CONFIG } from '../config/knowledgeGames'
import KnowledgeAlchemyGame from '../components/KnowledgeAlchemyGame.vue'
import KnowledgeExpeditionGame from '../components/KnowledgeExpeditionGame.vue'
import KnowledgeFlowCanvas from '../components/KnowledgeFlowCanvas.vue'
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
const gameConfigs = ref<Record<Subject, KnowledgeGameSubjectConfig>>({ ...DEFAULT_GAME_CONFIG })
const loading = ref(false)
const error = ref('')

const domainFilter = ref<string>('all')
const onlyWeakHighlight = ref(false)
const showLegend = ref(false)
const viewMode = ref<'graph' | 'list' | 'alchemy' | 'expedition'>('graph')
const selectedCode = ref<string | null>(null)

const currentGameConfig = computed<KnowledgeGameSubjectConfig>(
  () => gameConfigs.value[props.subject] ?? DEFAULT_GAME_CONFIG[props.subject],
)

interface PrereqLink {
  code: string
  name: string
  relation: string
  status: MasteryStatus
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
    const [data, cfgRes] = await Promise.all([
      props.client.knowledgeGraph(props.subject),
      props.client.knowledgeGameConfig().catch(() => null),
    ])
    graph.value = data
    if (cfgRes?.subjects) {
      gameConfigs.value = cfgRes.subjects
    }
    const curCfg = gameConfigs.value[props.subject] ?? DEFAULT_GAME_CONFIG[props.subject]
    if (viewMode.value === 'alchemy' && !curCfg.alchemy_enabled) {
      viewMode.value = 'graph'
    }
    if (viewMode.value === 'expedition' && !curCfg.expedition_enabled) {
      viewMode.value = 'graph'
    }
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
            依据教育部 2022 版课标构建的正式知识体系（已自动排除选学*内容），按领域分组展示先修拓扑流向、跨章桥梁与实时掌握状态。
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
            v-if="viewMode === 'graph'"
            type="button"
            class="ghost small"
            @click="showLegend = !showLegend"
          >
            {{ showLegend ? '收起图例' : '展开图例' }}
          </button>
          <button type="button" class="ghost small" @click="loadGraph" :disabled="loading">
            {{ loading ? '刷新中…' : '刷新图谱' }}
          </button>
        </div>
      </div>

      <!-- 知识点展示子模式与双闯关游戏切换栏 -->
      <div class="kg-subnav-bar">
        <div class="kg-subnav-tabs" role="group" aria-label="知识点展示模式与闯关游戏">
          <button
            type="button"
            :class="['kg-subtab', viewMode === 'graph' ? 'active' : '']"
            :aria-pressed="viewMode === 'graph'"
            @click="viewMode = 'graph'"
          >
            🗺️ 关系图谱
          </button>
          <button
            type="button"
            :class="['kg-subtab', viewMode === 'list' ? 'active' : '']"
            :aria-pressed="viewMode === 'list'"
            @click="viewMode = 'list'"
          >
            📋 切换清单视图
          </button>
          <button
            v-if="currentGameConfig.alchemy_enabled"
            type="button"
            :class="['kg-subtab', viewMode === 'alchemy' ? 'active' : '']"
            :aria-pressed="viewMode === 'alchemy'"
            @click="viewMode = 'alchemy'"
          >
            ⚗️ 知识合成工坊
          </button>
          <button
            v-if="currentGameConfig.expedition_enabled"
            type="button"
            :class="['kg-subtab', viewMode === 'expedition' ? 'active' : '']"
            :aria-pressed="viewMode === 'expedition'"
            @click="viewMode = 'expedition'"
          >
            🧭 迷雾科技树探险
          </button>
        </div>
      </div>

      <p v-if="error" class="form-error">{{ error }}</p>

      <template v-if="graph">
        <!-- 游戏一：知识合成工坊（大留白金字塔布局） -->
        <KnowledgeAlchemyGame
          v-if="viewMode === 'alchemy'"
          :graph="graph"
          :subject="subject"
          :config="currentGameConfig"
          @go-practice-focus="emit('goPracticeFocus', $event)"
        />

        <!-- 游戏二：迷雾科技树探险（大留白三岛破甲星盘） -->
        <KnowledgeExpeditionGame
          v-else-if="viewMode === 'expedition'"
          :graph="graph"
          :subject="subject"
          :config="currentGameConfig"
          @go-practice-focus="emit('goPracticeFocus', $event)"
        />

        <!-- 交互式图谱与清单视图 -->
        <template v-else>
        <!-- 标准图例总览面板 -->
        <section v-if="showLegend" class="legend-board" aria-label="知识点关系与掌握度标准图例">
          <div class="legend-board-head">
            <strong>标准图例说明</strong>
            <span class="muted tiny">图谱以色彩与符号双编码区分掌握度；点击任意知识节点即可高亮完整上下游先修脉络</span>
          </div>
          <div class="legend-grid">
            <div class="legend-section">
              <div class="legend-section-title">1. 领域分组与连线流向</div>
              <div class="legend-items">
                <span class="legend-chip container-box">虚线大框：一级知识领域</span>
                <span class="legend-chip leaf-box">实线箭头：同领域先修推导</span>
                <span class="legend-chip down-tag">虚线弧箭：跨领域桥梁</span>
              </div>
            </div>
            <div class="legend-section">
              <div class="legend-section-title">2. 脉络高亮与阻断提醒</div>
              <div class="legend-items">
                <span class="legend-chip prereq-tag">橙框：前置基础链</span>
                <span class="legend-chip down-tag">青框：后续进阶链</span>
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

        <!-- 主体：Vue Flow 交互式拓扑画布（全宽大视窗） / 清单视图 + 详情栏 -->
        <div :class="['graph-workspace', viewMode === 'graph' ? 'graph-wide' : '']">
          <KnowledgeFlowCanvas
            v-if="viewMode === 'graph'"
            :graph="graph"
            :domain-filter="domainFilter"
            :only-weak-highlight="onlyWeakHighlight"
            :selected-code="selectedCode"
            @select="selectedCode = $event"
          />

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
      </template>
    </section>
  </div>
</template>
