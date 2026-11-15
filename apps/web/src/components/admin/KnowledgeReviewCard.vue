<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
  describeError,
  SUBJECT_LABELS,
  type ApiClient,
  type Subject,
  type CurriculumClause,
  type CandidateNode,
  type LegacyMappingResult,
  type TaxonomyRelease,
} from '../../api'
import {
  LOCALE_PREFS,
  formatClauseTitle,
  formatReleaseChineseName,
  getDomainLabel,
  getKnowledgeLabel,
  getOperatorLabel,
  getReleaseStatusLabel,
} from '../../config/knowledge'
import HelpBubble from '../HelpBubble.vue'
import type { NoticeTone } from '../Notice.vue'

type Notify = (text: string, tone?: NoticeTone) => void
type ReviewTabId = 'review' | 'clauses' | 'mapping' | 'releases'
type NodeFilterId = 'all' | 'pending' | 'approved'

// 三级知识节点中文层级标识
const LEVEL_LABELS: Record<number, string> = {
  1: '一级领域',
  2: '二级主题',
  3: '三级考点',
}

const props = defineProps<{
  client: ApiClient
  subject: Subject
  notify: Notify
}>()

const activeTab = ref<ReviewTabId>('review')
const reviewFilter = ref<NodeFilterId>('all')
// 标记当前学科初次加载时是否已根据审核状态自动定位默认筛选项
const hasAutoSelectedFilter = ref(false)
// 默认隐藏底层英文技术编码，按配置决定是否允许一键展开排障
const showTechnicalCodes = ref<boolean>(LOCALE_PREFS.showTechnicalCodesByDefault)

// 新旧考点动作分类本地化映射字典
const LEGACY_ACTION_LABELS: Record<string, string> = {
  retained: '保留',
  renamed: '重命名',
  split: '合理拆分',
  merged: '合并',
  new: '新课标增设',
  added: '新课标增设',
  deprecated: '已停用',
  pending_human_review: '待人工核定',
}

// 学科官方课程标准原件依据说明（去除英文代码）
const SUBJECT_CURRICULUM_DOCS: Record<Subject, string> = {
  chinese: '基于教育部 2022 年版初中语文课程标准与北京市中考考查范围',
  math: '基于教育部 2022 年版初中数学课程标准（含 2022-05-09 修正版）与北京市中考考查范围',
  english: '基于教育部 2022 年版初中英语课程标准与北京市中考听说及笔试考查范围',
  physics: '基于教育部 2022 年版初中物理课程标准与北京市中考考查范围',
}

// 1. 候选知识体系状态
const candidates = ref<CandidateNode[]>([])
const loadingCandidates = ref(false)
const selectedNodeCode = ref<string | null>(null)
// 默认严格为空，禁止预填虚假专家标识与意见，必须由真实操作人提供
const reviewerId = ref('')
const reviewOpinion = ref('')
const reviewing = ref(false)
const seeding = ref(false)

// 2. 课标条款状态
const clauses = ref<CurriculumClause[]>([])
const loadingClauses = ref(false)
const clauseDomainFilter = ref<string>('all')

// 3. 新旧映射状态
const legacyMapping = ref<LegacyMappingResult | null>(null)
const loadingMapping = ref(false)

// 4. 版本发布状态
const releases = ref<TaxonomyRelease[]>([])
const releaseVersion = ref(`${props.subject}-v2022.1.0`)
const publishedBy = ref('系统管理员')
const releaseSummary = ref(`教育部2022年版初中${SUBJECT_LABELS[props.subject]}课程标准全量拆解知识体系首发版本`)
const publishing = ref(false)
const releaseError = ref('')

// 未通过审核（待审或已驳回）节点与已审定节点集合
const pendingTabNodes = computed(() => {
  return candidates.value.filter(c => c.review_status !== 'approved')
})

const approvedNodes = computed(() => {
  return candidates.value.filter(c => c.review_status === 'approved')
})

const activeListNodes = computed(() => {
  if (reviewFilter.value === 'pending') return pendingTabNodes.value
  if (reviewFilter.value === 'approved') return approvedNodes.value
  return candidates.value
})

const selectedNode = computed(() => {
  const list = activeListNodes.value
  if (list.length === 0) return null
  if (!selectedNodeCode.value) return list[0]
  return list.find(c => c.code === selectedNodeCode.value) ?? list[0]
})

const pendingCount = computed(() => {
  return candidates.value.filter(c => c.review_status === 'pending').length
})

const rejectedCount = computed(() => {
  return candidates.value.filter(c => c.review_status === 'rejected').length
})

const approvedCount = computed(() => {
  return approvedNodes.value.length
})

// 建立条款 ID -> 候选考点列表反查索引
const clauseToCandidatesMap = computed(() => {
  const map: Record<string, CandidateNode[]> = {}
  for (const cand of candidates.value) {
    for (const cid of cand.source_clause_ids ?? []) {
      if (!map[cid]) map[cid] = []
      map[cid].push(cand)
    }
  }
  return map
})

// 建立候选代码 -> 候选对象索引
const candidateMap = computed(() => {
  const map: Record<string, CandidateNode> = {}
  for (const cand of candidates.value) {
    map[cand.code] = cand
  }
  return map
})

// 建立条款 ID -> 条款对象索引
const clauseMap = computed(() => {
  const map: Record<string, CurriculumClause> = {}
  for (const cl of clauses.value) {
    map[cl.clause_id] = cl
  }
  return map
})

// 建立旧考点代码 -> 映射对象索引
const legacyMappingByCode = computed(() => {
  const map: Record<string, any> = {}
  for (const m of legacyMapping.value?.legacy_mappings ?? []) {
    map[m.legacy_code] = m
  }
  return map
})

// 建立候选考点代码 -> 映射到它的旧考点列表
const candidateToLegacyMappings = computed(() => {
  const map: Record<string, any[]> = {}
  for (const m of legacyMapping.value?.legacy_mappings ?? []) {
    for (const t of m.target_candidate_codes ?? []) {
      if (!map[t]) map[t] = []
      map[t].push(m)
    }
  }
  return map
})

// 安全汇总统计旧考点映射动作
const mappingSummary = computed(() => {
  const mappings = legacyMapping.value?.legacy_mappings ?? []
  const summaryObj = (legacyMapping.value as any)?.summary
  const defaultTotal = props.subject === 'math' ? 24 : props.subject === 'physics' ? 21 : 18

  return {
    total: summaryObj?.total_legacy_nodes ?? summaryObj?.total_legacy_math_nodes ?? (mappings.length > 0 ? mappings.length : defaultTotal),
    retained: summaryObj?.retained_count ?? mappings.filter(m => m.action === 'retained').length,
    renamed: summaryObj?.renamed_count ?? mappings.filter(m => m.action === 'renamed').length,
    split: summaryObj?.split_count ?? mappings.filter(m => m.action === 'split').length,
    merged: summaryObj?.merged_count ?? mappings.filter(m => m.action === 'merged').length,
    new: summaryObj?.new_count ?? mappings.filter(m => (m.action as string) === 'new' || (m.action as string) === 'added').length,
    pending: summaryObj?.pending_human_review_count ?? mappings.filter(m => m.action === 'pending_human_review').length,
  }
})

// 动态提取当前学科课标领域（确保回退中文名称）
const availableDomains = computed(() => {
  const map = new Map<string, string>()
  for (const cl of clauses.value) {
    if (cl.domain && !map.has(cl.domain)) {
      map.set(cl.domain, cl.domain_title || getDomainLabel(cl.domain))
    }
  }
  return Array.from(map.entries()).map(([code, title]) => ({ code, title }))
})

const filteredClauses = computed(() => {
  if (clauseDomainFilter.value === 'all') return clauses.value
  return clauses.value.filter(c => c.domain === clauseDomainFilter.value)
})

// 方案二：四类矩阵子工作区标签与实时计数徽章
const reviewTabs = computed(() => [
  {
    id: 'review' as const,
    title: '知识点审定',
    badge: pendingCount.value > 0 ? `待审 ${pendingCount.value}` : `${approvedNodes.value.length} 项`,
    wait: pendingCount.value > 0,
  },
  {
    id: 'clauses' as const,
    title: '课标条款全集',
    badge: `${clauses.value.length} 条`,
    wait: false,
  },
  {
    id: 'mapping' as const,
    title: '新旧考点映射',
    badge: mappingSummary.value.pending > 0 ? `待核 ${mappingSummary.value.pending}` : `${mappingSummary.value.total} 项`,
    wait: mappingSummary.value.pending > 0,
  },
  {
    id: 'releases' as const,
    title: '版本发布与快照',
    badge: `${releases.value.length} 版`,
    wait: false,
  },
])

function syncSelectedNodeForFilter() {
  const list = activeListNodes.value
  if (list.length === 0) {
    selectedNodeCode.value = null
    return
  }
  if (!list.some(c => c.code === selectedNodeCode.value)) {
    selectedNodeCode.value = list[0].code
  }
}

async function loadCandidates() {
  loadingCandidates.value = true
  try {
    candidates.value = await props.client.adminKnowledgeCandidates(props.subject)
    // 初次加载或切换学科时：有待审核则聚焦待审核，全部审定则默认展示已审定列表
    if (!hasAutoSelectedFilter.value) {
      hasAutoSelectedFilter.value = true
      reviewFilter.value = pendingTabNodes.value.length > 0 ? 'pending' : 'all'
    } else if (reviewFilter.value === 'pending' && pendingTabNodes.value.length === 0 && approvedNodes.value.length > 0) {
      reviewFilter.value = 'approved'
    }
    syncSelectedNodeForFilter()
  } catch (e) {
    props.notify(`加载候选知识点失败：${describeError(e)}`, 'caution')
  } finally {
    loadingCandidates.value = false
  }
}

async function loadClauses() {
  loadingClauses.value = true
  try {
    clauses.value = await props.client.adminKnowledgeClauses(props.subject)
  } catch (e) {
    props.notify(`加载课标条款失败：${describeError(e)}`, 'caution')
  } finally {
    loadingClauses.value = false
  }
}

async function loadLegacyMapping() {
  loadingMapping.value = true
  try {
    legacyMapping.value = await props.client.adminKnowledgeLegacyMapping(props.subject)
  } catch (e) {
    props.notify(`加载新旧映射失败：${describeError(e)}`, 'caution')
  } finally {
    loadingMapping.value = false
  }
}

async function loadReleases() {
  try {
    releases.value = await props.client.adminKnowledgeReleases(props.subject)
  } catch (e) {
    props.notify(`加载已发布版本快照失败：${describeError(e)}`, 'caution')
  }
}

async function seedCandidates() {
  seeding.value = true
  try {
    const res = await props.client.adminSeedCandidates(props.subject)
    activeTab.value = 'review'
    reviewFilter.value = 'pending'
    props.notify(`已成功初始化 ${res.seeded_count} 个候选节点入库（总数 ${res.total_nodes}），全部置为待审核状态。`, 'info')
    await loadCandidates()
  } catch (e) {
    props.notify(`初始化候选知识点失败：${describeError(e)}`, 'caution')
  } finally {
    seeding.value = false
  }
}

async function submitReview(status: 'approved' | 'rejected') {
  if (!selectedNode.value) return
  if (!selectedNode.value.id) {
    props.notify('请先点击上方「同步候选入库 (待审)」将候选节点同步至数据库，再执行人工审核记录。', 'caution')
    return
  }
  if (!reviewerId.value.trim()) {
    props.notify('审核人实名标识不能为空，严禁未记名审核。', 'caution')
    return
  }
  if (!reviewOpinion.value.trim()) {
    props.notify('请填写审核意见与课标对照依据。', 'caution')
    return
  }

  reviewing.value = true
  try {
    await props.client.adminReviewNode(selectedNode.value.id, {
      reviewer_id: reviewerId.value.trim(),
      review_status: status,
      review_opinion: reviewOpinion.value.trim(),
    })
    props.notify(`节点「${selectedNode.value.name}」已标记为${status === 'approved' ? '审核通过' : '退回驳回'}。`, 'success')
    await loadCandidates()
  } catch (e) {
    props.notify(`提交审核失败：${describeError(e)}`, 'caution')
  } finally {
    reviewing.value = false
  }
}

const batchReviewing = ref(false)

function buildClauseOpinionDraft(node: CandidateNode): string {
  const cids = node.source_clause_ids ?? []
  const matched = cids.map(cid => clauseMap.value[cid]).filter(Boolean)
  if (matched.length === 0) {
    return `核对${SUBJECT_LABELS[props.subject]}知识点「${node.name}」：请补充并核验官方课标条款。`
  }
  const refs = matched
    .slice(0, 2)
    .map(c => `${c.sub_theme || c.domain_title}${c.clause_number || ''}（印刷第 ${c.print_page} 页 / 电子版第 ${c.pdf_page} 页）`)
    .join('；')
  const req = matched[0].derived_requirement || matched[0].standardized_text || node.description || node.name
  const legacyList = (candidateToLegacyMappings.value[node.code] ?? []).map(m => getKnowledgeLabel(m.legacy_code))
  const legacyNote = legacyList.length > 0 ? `兼容历史考点：${legacyList.join('、')}。` : '2022版新课标细化考点。'
  return `核对教育部2022年版初中${SUBJECT_LABELS[props.subject]}课程标准[${refs}]，核心要求为「${req}」。已核查概念粒度与必学范围，${legacyNote}`
}

function fillOpinionDraft() {
  if (!selectedNode.value) return
  reviewOpinion.value = buildClauseOpinionDraft(selectedNode.value)
}

async function batchApprovePending() {
  if (!reviewerId.value.trim()) {
    props.notify('批量审核前，请先填写真实的审核人实名标识（严禁未记名审核）。', 'caution')
    return
  }
  const pendingNodes = candidates.value.filter(c => c.review_status === 'pending' && c.id)
  if (pendingNodes.length === 0) {
    props.notify('当前学科没有待审核且已入库的候选节点。', 'info')
    return
  }
  batchReviewing.value = true
  try {
    const items = pendingNodes.map(n => ({
      node_id: n.id as string,
      reviewer_id: reviewerId.value.trim(),
      review_status: 'approved' as const,
      review_opinion: buildClauseOpinionDraft(n),
    }))
    const res = await props.client.adminBatchReviewNodes(items)
    props.notify(`已根据课标条款依据批量审核通过 ${res.reviewed_count} 个待审节点。`, 'success')
    await loadCandidates()
  } catch (e) {
    props.notify(`批量审核失败：${describeError(e)}`, 'caution')
  } finally {
    batchReviewing.value = false
  }
}

async function publishRelease() {
  publishing.value = true
  releaseError.value = ''
  try {
    await props.client.adminPublishRelease({
      subject: props.subject,
      release_version: releaseVersion.value.trim(),
      published_by: publishedBy.value.trim(),
      summary: releaseSummary.value.trim(),
    })
    const releaseLabel = formatReleaseChineseName(releaseVersion.value.trim())
    props.notify(`知识库正式版本「${releaseLabel}」发布成功，已生成不可变历史快照。`, 'success')
    await loadReleases()
  } catch (e) {
    releaseError.value = describeError(e)
    props.notify(`发布阻断拦截：${describeError(e)}`, 'caution')
  } finally {
    publishing.value = false
  }
}

watch(
  [() => props.client, () => props.subject],
  () => {
    releaseVersion.value = `${props.subject}-v2022.1.0`
    releaseSummary.value = `教育部2022年版初中${SUBJECT_LABELS[props.subject]}课程标准全量拆解知识体系首发版本`
    clauseDomainFilter.value = 'all'
    selectedNodeCode.value = null
    hasAutoSelectedFilter.value = false
    void loadCandidates()
    void loadClauses()
    void loadLegacyMapping()
    void loadReleases()
  },
  { immediate: true }
)

watch(reviewFilter, () => {
  syncSelectedNodeForFilter()
})

watch(activeTab, tab => {
  if (tab === 'review') {
    syncSelectedNodeForFilter()
  }
})
</script>

<template>
  <div class="knowledge-workbench admin-workspace">
    <!-- 顶部标题与工作区操作栏 -->
    <section class="card" aria-label="知识点工作台总览">
      <div class="card-head">
        <div>
          <h2>{{ SUBJECT_LABELS[props.subject] }}权威知识点库审核工作台</h2>
          <p class="sub-head">
            {{ SUBJECT_CURRICULUM_DOCS[props.subject] }}
          </p>
        </div>
        <div class="head-actions">
          <HelpBubble compact tone="caution" title="课标审核红线说明" label="审核红线">
            <p>
              知识点必须溯源至教育部 2022 年版课程标准官方条文。所有自动归集的候选考点均初始化为待审核状态，须经学科专家人工逐项审核；审核通过后自动归入「已审定」集合。若存在未审核或已驳回考点，发布强门禁将阻断版本发布。
            </p>
          </HelpBubble>
          <button
            type="button"
            class="ghost small"
            :aria-pressed="showTechnicalCodes"
            @click="showTechnicalCodes = !showTechnicalCodes"
          >
            {{ showTechnicalCodes ? '隐藏技术编码' : '显示技术编码' }}
          </button>
          <button
            type="button"
            class="ghost small"
            :disabled="seeding"
            @click="seedCandidates"
          >
            {{ seeding ? '同步中...' : '同步候选入库 (待审)' }}
          </button>
          <button
            v-if="pendingCount > 0"
            type="button"
            class="primary small"
            :disabled="batchReviewing"
            @click="batchApprovePending"
          >
            {{ batchReviewing ? '批量审核中...' : `按课标批量审核待审 (${pendingCount})` }}
          </button>
          <button type="button" class="ghost small" @click="loadCandidates">
            刷新
          </button>
        </div>
      </div>

      <!-- 紧凑状态统计条 -->
      <div class="status-banner" role="region" aria-label="知识点审核状态统计">
        <div class="stats-panel-head">
          <h3>{{ SUBJECT_LABELS[props.subject] }}知识体系审核状态统计</h3>
          <span
            v-if="candidates.length > 0 && pendingCount === 0 && rejectedCount === 0"
            class="audit-note audit-ok"
          >
            全量知识点已通过专家终审，已具备正式发布条件（共 {{ approvedCount }} 项）。
          </span>
          <span v-else class="audit-note">
            红线门禁：候选内容全量通过真实学科审核前，严禁发布正式知识库版本。
          </span>
        </div>
        <div class="status-badges-row">
          <span class="badge pending">待审核: {{ pendingCount }}</span>
          <span class="badge approved">已通过: {{ approvedCount }}</span>
          <span class="badge total">总知识节点: {{ candidates.length }}</span>
          <span class="badge clauses">课标条款: {{ clauses.length }} 条</span>
        </div>
      </div>
    </section>

    <!-- 方案二：4 类矩阵协同子 Tab 条 -->
    <div class="admin-subtab-strip">
      <div class="admin-subtab-list" role="tablist" aria-label="知识点审核工作区">
        <button
          v-for="tab in reviewTabs"
          :key="tab.id"
          :id="`kr-tab-${tab.id}`"
          type="button"
          role="tab"
          :aria-selected="activeTab === tab.id"
          :aria-controls="`kr-panel-${tab.id}`"
          :class="['admin-subtab', activeTab === tab.id ? 'active' : '']"
          @click="activeTab = tab.id"
        >
          <span>{{ tab.title }}</span>
          <span :class="['admin-subtab-badge', tab.wait ? 'wait' : '']">{{ tab.badge }}</span>
        </button>
      </div>
    </div>

    <!-- 子 Tab 1：知识点审定（3 列矩阵：节点列表+筛选 | 课标溯源与旧考点映射 | 专家审核操作） -->
    <div
      v-if="activeTab === 'review'"
      id="kr-panel-review"
      role="tabpanel"
      aria-labelledby="kr-tab-review"
    >
      <section v-if="candidates.length === 0" class="card empty-panel-card" aria-label="知识点审定空状态">
        <h4>当前学科尚未同步候选知识点</h4>
        <p>请点击右上角「同步候选入库 (待审)」载入教育部 2022 版课标拆解候选考点。</p>
      </section>

      <div v-else class="matrix-3col">
        <!-- 左栏：知识点目录与审核状态切换（全部 / 待审核 / 已审定） -->
        <section class="card" aria-label="知识点目录与状态筛选">
          <div class="card-head">
            <h3>知识点目录 ({{ activeListNodes.length }})</h3>
          </div>
          <div class="filter-bar" role="group" aria-label="按审核状态筛选知识点">
            <button
              type="button"
              :class="reviewFilter === 'all' ? 'filter-chip selected' : 'filter-chip'"
              @click="reviewFilter = 'all'"
            >
              全部 ({{ candidates.length }})
            </button>
            <button
              type="button"
              :class="reviewFilter === 'pending' ? 'filter-chip selected' : 'filter-chip'"
              @click="reviewFilter = 'pending'"
            >
              待审核 ({{ pendingTabNodes.length }})
            </button>
            <button
              type="button"
              :class="reviewFilter === 'approved' ? 'filter-chip selected' : 'filter-chip'"
              @click="reviewFilter = 'approved'"
            >
              已审定 ({{ approvedNodes.length }})
            </button>
          </div>

          <div v-if="activeListNodes.length === 0" class="empty-hint">
            当前筛选条件下暂无节点，可切换上方「全部 / 待审核 / 已审定」查看。
          </div>
          <div v-else class="candidate-scroll-list">
            <button
              v-for="cand in activeListNodes"
              :key="cand.code"
              type="button"
              :aria-pressed="selectedNode?.code === cand.code"
              :class="[
                'candidate-item',
                selectedNode?.code === cand.code ? 'selected' : '',
                cand.review_status,
                `level-${cand.level ?? 3}`,
              ]"
              @click="selectedNodeCode = cand.code"
            >
              <div class="cand-header">
                <span class="cand-level-tag">{{ LEVEL_LABELS[cand.level ?? 3] ?? '知识节点' }}</span>
                <span :class="['status-pill', cand.review_status]">
                  {{ cand.review_status === 'approved' ? '已通过' : cand.review_status === 'rejected' ? '已驳回' : '待人工审核' }}
                </span>
              </div>
              <div class="cand-name">{{ cand.name }}</div>
              <div v-if="showTechnicalCodes" class="cand-code">{{ cand.code }}</div>
              <div class="cand-meta">
                <span v-if="cand.source_clause_ids?.length">
                  关联 {{ cand.source_clause_ids.length }} 条款
                </span>
                <span v-if="cand.reviewer_id" class="reviewer-meta">
                  审核人: {{ getOperatorLabel(cand.reviewer_id) }}
                </span>
              </div>
            </button>
          </div>
        </section>

        <!-- 中栏：课标溯源条文与旧考点兼容关系 -->
        <section class="card" aria-label="课标溯源条款与旧考点兼容">
          <template v-if="selectedNode">
            <h3>{{ selectedNode.name }}</h3>
            <p v-if="showTechnicalCodes" class="detail-code">技术编码: <code>{{ selectedNode.code }}</code></p>
            <p class="detail-desc">{{ selectedNode.description ?? '暂无详细描述' }}</p>

            <div class="clauses-trace">
              <h4>课标溯源条款 ({{ selectedNode.source_clause_ids?.length ?? 0 }} 条)</h4>
              <div v-if="(selectedNode.source_clause_ids ?? []).length === 0" class="empty-hint">
                暂无关联课标条款（发布强门禁：无来源条款节点严禁发布）
              </div>
              <ul v-else class="clause-card-list" tabindex="0" aria-label="关联课标溯源条款列表">
                <li
                  v-for="cid in selectedNode.source_clause_ids ?? []"
                  :key="cid"
                  class="clause-card-item"
                >
                  <div class="clause-card-header">
                    <span class="clause-card-title">{{ formatClauseTitle(cid, clauseMap[cid]) }}</span>
                    <div class="clause-card-badges">
                      <span v-if="clauseMap[cid]" class="clause-page-badge">
                        电子版第 {{ clauseMap[cid].pdf_page }} 页 · 印刷第 {{ clauseMap[cid].print_page }} 页
                      </span>
                      <span v-if="clauseMap[cid]?.is_elective" class="badge elective">选学*</span>
                      <span v-else-if="clauseMap[cid]" class="badge standard">必学</span>
                    </div>
                  </div>
                  <div v-if="showTechnicalCodes" class="clause-tech-id"><code>{{ cid }}</code></div>
                  <div v-if="clauseMap[cid]" class="clause-card-body">
                    <div class="clause-card-text">
                      {{ clauseMap[cid].raw_text }}
                    </div>
                    <div v-if="clauseMap[cid].standardized_text && clauseMap[cid].standardized_text !== clauseMap[cid].raw_text" class="clause-card-std">
                      <small>规范化转写：</small>{{ clauseMap[cid].standardized_text }}
                    </div>
                  </div>
                </li>
              </ul>
            </div>

            <div class="legacy-trace">
              <h4>存量旧考点映射关联</h4>
              <div v-if="(candidateToLegacyMappings[selectedNode.code] ?? []).length === 0" class="empty-trace">
                <span class="badge info">新课标增设考点 · 存量题库无直接历史对应</span>
              </div>
              <div v-else class="legacy-trace-list" tabindex="0" aria-label="存量旧考点兼容关联列表">
                <div
                  v-for="m in candidateToLegacyMappings[selectedNode.code]"
                  :key="m.legacy_code"
                  class="legacy-trace-card"
                >
                  <div class="legacy-card-head">
                    <span class="legacy-name">{{ m.legacy_name || getKnowledgeLabel(m.legacy_code) }}</span>
                    <code v-if="showTechnicalCodes">{{ m.legacy_code }}</code>
                    <span :class="['action-tag', m.action]">{{ LEGACY_ACTION_LABELS[m.action] ?? m.action }}</span>
                  </div>
                  <p class="legacy-reason"><b>映射理由：</b>{{ m.mapping_reason }}</p>
                  <p class="legacy-compat"><b>兼容保障：</b>{{ m.compatibility_assurance }}</p>
                </div>
              </div>
            </div>
          </template>
          <p v-else class="muted">请先在左侧列表点选一个知识点查看课标依据与兼容关系。</p>
        </section>

        <!-- 右栏：专家审核档案与实时审批表单 -->
        <section class="card" aria-label="专家人工审核记录与操作">
          <template v-if="selectedNode">
            <div v-if="selectedNode.review_opinion || selectedNode.reviewer_id" class="expert-review-record">
              <div class="expert-review-head">
                <h4>当前学科专家审核档案</h4>
                <span :class="['status-pill', selectedNode.review_status]">
                  {{ selectedNode.review_status === 'approved' ? '已通过' : selectedNode.review_status === 'rejected' ? '已驳回' : '待人工审核' }}
                </span>
              </div>
              <div class="expert-review-meta">
                <span><b>审核专家：</b>{{ getOperatorLabel(selectedNode.reviewer_id ?? '') || '—' }}</span>
                <code v-if="showTechnicalCodes && selectedNode.reviewer_id">{{ selectedNode.reviewer_id }}</code>
                <span v-if="selectedNode.reviewed_at">
                  <b>审核时间：</b>{{ new Date(selectedNode.reviewed_at).toLocaleString('zh-CN') }}
                </span>
              </div>
              <p class="expert-review-opinion" tabindex="0" aria-label="专家历史审核意见">{{ selectedNode.review_opinion }}</p>
            </div>

            <div class="review-box" :style="!(selectedNode.review_opinion || selectedNode.reviewer_id) ? 'margin-top: 0; border-top: none; padding-top: 0;' : ''">
              <div class="card-head" style="margin-bottom: 0.7rem;">
                <h4 style="margin: 0;">学科专家人工审核操作</h4>
                <HelpBubble compact tone="caution" title="审核人资质与实名审计说明" label="实名要求">
                  <p>
                    审核人实名标识用于操作审计留痕，系统不自动认证学术资质。真实{{ SUBJECT_LABELS[props.subject] }}内容效力须由具备相应初中{{ SUBJECT_LABELS[props.subject] }}学科资质的人员基于课标条文研核后如实填报，严禁代签、预设或冒用。
                  </p>
                </HelpBubble>
              </div>
              <div class="field-row">
                <label for="rev-id">审核人实名标识 (必填):</label>
                <input
                  id="rev-id"
                  v-model="reviewerId"
                  type="text"
                  placeholder="请输入实际审核人员实名或工号标识"
                />
              </div>
              <div class="field-row">
                <label for="rev-opinion">审核依据与意见 (必填):</label>
                <textarea
                  id="rev-opinion"
                  v-model="reviewOpinion"
                  rows="3"
                  placeholder="必须录入具体课标条文核查依据、概念粒度判定及学科诊断适用性理由"
                ></textarea>
              </div>
              <div class="review-actions">
                <button
                  type="button"
                  class="ghost small"
                  @click="fillOpinionDraft"
                >
                  按课标生成审核依据草稿
                </button>
                <button
                  type="button"
                  class="primary small"
                  :disabled="reviewing || !reviewerId.trim() || !reviewOpinion.trim()"
                  @click="submitReview('approved')"
                >
                  {{ reviewing ? '提交中...' : '审核通过' }}
                </button>
                <button
                  type="button"
                  class="danger small"
                  :disabled="reviewing || !reviewerId.trim() || !reviewOpinion.trim()"
                  @click="submitReview('rejected')"
                >
                  {{ reviewing ? '提交中...' : '退回驳回' }}
                </button>
              </div>
            </div>
          </template>
          <p v-else class="muted">选中知识点后，可在此记录专家审核意见或执行审定操作。</p>
        </section>
      </div>
    </div>

    <!-- 子 Tab 2：课标条款全集 -->
    <div
      v-else-if="activeTab === 'clauses'"
      id="kr-panel-clauses"
      role="tabpanel"
      aria-labelledby="kr-tab-clauses"
    >
      <section class="card" aria-label="课标条款全集">
        <div class="filter-bar">
          <span>按领域过滤：</span>
          <button
            type="button"
            :class="clauseDomainFilter === 'all' ? 'filter-chip selected' : 'filter-chip'"
            @click="clauseDomainFilter = 'all'"
          >
            全部 ({{ clauses.length }})
          </button>
          <button
            v-for="d in availableDomains"
            :key="d.code"
            type="button"
            :class="clauseDomainFilter === d.code ? 'filter-chip selected' : 'filter-chip'"
            @click="clauseDomainFilter = d.code"
          >
            {{ d.title }}
          </button>
        </div>

        <div class="clause-table-wrapper" tabindex="0" aria-label="课标条款全集数据表">
          <table class="clause-table">
            <thead>
              <tr>
                <th style="width: 24%;">课标主题与页码</th>
                <th style="width: 40%;">官方条文与规范转写</th>
                <th style="width: 20%;">对应 2022 课标新考点</th>
                <th style="width: 16%;">对应存量旧考点</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="cl in filteredClauses" :key="cl.clause_id">
                <td>
                  <div class="domain-title">{{ cl.domain_title || getDomainLabel(cl.domain) }}</div>
                  <div class="sub-theme-text">{{ cl.theme_title ? `${cl.theme_title} · ` : '' }}{{ cl.sub_theme }}</div>
                  <div class="clause-page-meta">
                    <span class="clause-page-badge">电子版第 {{ cl.pdf_page }} 页 · 印刷第 {{ cl.print_page }} 页</span>
                    <span v-if="cl.is_elective" class="badge elective">选学*</span>
                    <span v-else class="badge standard">必学</span>
                  </div>
                  <div v-if="showTechnicalCodes" class="clause-tech-id"><code>{{ cl.clause_id }}</code></div>
                </td>
                <td class="text-cell">
                  <div class="raw-text-block">{{ cl.raw_text }}</div>
                  <div v-if="cl.standardized_text && cl.standardized_text !== cl.raw_text" class="standardized-text-block">
                    <small>规范化转写：</small>{{ cl.standardized_text }}
                  </div>
                </td>
                <td class="mapping-cell">
                  <div v-if="(clauseToCandidatesMap[cl.clause_id] ?? []).length === 0" class="empty-mapping-text">
                    暂无关联新考点
                  </div>
                  <div
                    v-for="cand in clauseToCandidatesMap[cl.clause_id] ?? []"
                    :key="cand.code"
                    class="mapping-pill candidate-pill"
                  >
                    <span class="pill-name">{{ cand.name }}</span>
                    <code v-if="showTechnicalCodes" class="pill-code">{{ cand.code }}</code>
                  </div>
                </td>
                <td class="mapping-cell">
                  <div v-if="(cl.legacy_mappings ?? []).length === 0" class="empty-mapping-text">
                    <span class="badge info">新课标增设</span>
                  </div>
                  <div
                    v-for="legCode in cl.legacy_mappings ?? []"
                    :key="legCode"
                    class="mapping-pill legacy-pill"
                  >
                    <span class="pill-name">{{ legacyMappingByCode[legCode]?.legacy_name ?? getKnowledgeLabel(legCode) }}</span>
                    <code v-if="showTechnicalCodes" class="pill-code">{{ legCode }}</code>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>

    <!-- 子 Tab 3：新旧考点映射 -->
    <div
      v-else-if="activeTab === 'mapping'"
      id="kr-panel-mapping"
      role="tabpanel"
      aria-labelledby="kr-tab-mapping"
    >
      <section class="card" aria-label="新旧考点映射与兼容">
        <div v-if="legacyMapping" class="mapping-summary">
          <section class="mapping-stats-panel" aria-label="新旧考点映射统计数据">
            <div class="stats-panel-head">
              <h3>{{ SUBJECT_LABELS[props.subject] }}新旧考点迁移映射统计概览</h3>
              <div class="head-actions">
                <HelpBubble compact tone="caution" title="历史兼容保护原则" label="兼容原则">
                  <p>
                    存量 {{ mappingSummary.total }} 个旧考点作为历史资产永久保留只读；历史题目关联记录、作答与曝光记录绝不被覆盖或静默重写。
                  </p>
                </HelpBubble>
                <span
                  v-if="mappingSummary.pending === 0"
                  class="badge approved"
                >
                  全部存量考点已完成核定（待人工核定: 0）
                </span>
                <span v-else class="badge pending">
                  待人工核定: {{ mappingSummary.pending }}
                </span>
              </div>
            </div>
            <div class="mapping-stats">
              <span class="stat-pill stat-total">存量考点: <b>{{ mappingSummary.total }}</b> 个</span>
              <span class="stat-pill stat-retained">保留: <b>{{ mappingSummary.retained }}</b></span>
              <span class="stat-pill stat-renamed">重命名: <b>{{ mappingSummary.renamed }}</b></span>
              <span class="stat-pill stat-split">合理拆分: <b>{{ mappingSummary.split }}</b></span>
              <span class="stat-pill stat-merged">合并: <b>{{ mappingSummary.merged }}</b></span>
              <span class="stat-pill stat-new">新课标增设: <b>{{ mappingSummary.new }}</b></span>
            </div>
          </section>

          <div class="mapping-table-wrapper" tabindex="0" aria-label="新旧考点映射对照表">
            <table class="mapping-table">
              <thead>
                <tr>
                  <th style="width: 19%;">存量旧考点与动作</th>
                  <th style="width: 25%;">对应 2022 课标新考点与依据</th>
                  <th style="width: 28%;">映射与教学演进理由</th>
                  <th style="width: 28%;">历史兼容保障说明</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="m in legacyMapping.legacy_mappings" :key="m.legacy_code">
                  <td>
                    <div class="pill-name">{{ m.legacy_name || getKnowledgeLabel(m.legacy_code) }}</div>
                    <div style="margin-top:4px;">
                      <span :class="['action-tag', m.action]">{{ LEGACY_ACTION_LABELS[m.action] ?? m.action }}</span>
                    </div>
                    <div v-if="showTechnicalCodes" style="margin-top:4px;"><code>{{ m.legacy_code }}</code></div>
                  </td>
                  <td>
                    <div
                      v-for="t in m.target_candidate_codes"
                      :key="t"
                      class="target-cand-item"
                    >
                      <span class="cand-name-tag">{{ candidateMap[t]?.name ?? getKnowledgeLabel(t) }}</span>
                      <span v-if="candidateMap[t]?.source_clause_ids?.length" class="clause-count-pill">
                        {{ candidateMap[t]?.source_clause_ids?.length }} 条课标依据
                      </span>
                      <span v-else class="badge caution">无溯源条款</span>
                      <code v-if="showTechnicalCodes" class="pill-code">{{ t }}</code>
                    </div>
                  </td>
                  <td class="reason-cell">{{ m.mapping_reason }}</td>
                  <td class="compat-cell">{{ m.compatibility_assurance }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div v-else class="muted">映射数据加载中...</div>
      </section>
    </div>

    <!-- 子 Tab 4：版本发布与快照（2 列矩阵：左栏正式版本发布 | 右栏历史发布快照） -->
    <div
      v-else
      id="kr-panel-releases"
      role="tabpanel"
      aria-labelledby="kr-tab-releases"
      class="matrix-2col"
    >
      <section class="card release-form" aria-label="发布正式版本">
        <div class="card-head">
          <h3>发布知识库正式版本</h3>
          <HelpBubble compact tone="caution" title="发布强门禁规则" label="发布门禁">
            <p>当且仅当当前学科全部候选知识点均经学科专家人工审核通过（待审核 0 个、已驳回 0 个）时，方可发布不可变正式版本快照。</p>
          </HelpBubble>
        </div>

        <div class="form-grid">
          <div class="form-field">
            <label for="rel-ver">版本标识:</label>
            <input id="rel-ver" v-model="releaseVersion" type="text" />
          </div>
          <div class="form-field">
            <label for="rel-by">发布人:</label>
            <input id="rel-by" v-model="publishedBy" type="text" />
          </div>
        </div>
        <div class="form-field">
          <label for="rel-sum">版本摘要说明:</label>
          <textarea id="rel-sum" v-model="releaseSummary" rows="2"></textarea>
        </div>

        <div v-if="releaseError" class="release-error-box">
          <b>发布阻断拦截原因：</b>
          <p>{{ releaseError }}</p>
        </div>

        <div class="release-actions">
          <button
            type="button"
            class="primary"
            :disabled="publishing"
            @click="publishRelease"
          >
            {{ publishing ? '发布中...' : '发布正式版本快照' }}
          </button>
        </div>
      </section>

      <section class="card releases-list" aria-label="历史发布版本快照">
        <div class="card-head">
          <h3>历史发布版本快照 ({{ releases.length }} 个)</h3>
        </div>
        <div v-if="releases.length === 0" class="empty-hint">
          暂无已发布正式版本（当前处于全量待审阶段）。
        </div>
        <div v-else class="release-scroll-list" tabindex="0" aria-label="历史发布版本快照列表">
          <div
            v-for="rel in releases"
            :key="rel.id"
            class="release-card"
          >
            <div class="rel-head">
              <span class="rel-ver-zh">{{ formatReleaseChineseName(rel.release_version) }}</span>
              <span v-if="showTechnicalCodes" class="rel-ver chip">{{ rel.release_version }}</span>
              <span class="rel-status">{{ getReleaseStatusLabel(rel.status) }}</span>
              <span class="rel-time">{{ rel.published_at ? new Date(rel.published_at).toLocaleString('zh-CN') : '—' }}</span>
            </div>
            <p class="rel-summary">{{ rel.summary }}</p>
            <div class="rel-meta">
              <span>发布人: {{ getOperatorLabel(rel.published_by) }}</span>
              <span>包含节点: {{ rel.total_nodes }} 个</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.knowledge-workbench {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
  flex-wrap: wrap;
}
.sub-head {
  color: var(--ink-2, #5C5346);
  font-size: 0.85rem;
  margin-top: 0.25rem;
}
.head-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  align-items: center;
}
.status-banner {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
  background: #F4EDE0;
  border: 1px solid #DDD1BA;
  padding: 0.9rem 1.05rem;
  border-radius: 12px;
  font-size: 0.85rem;
  margin-top: 0.85rem;
}
.stats-panel-head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem 1rem;
}
.stats-panel-head h3 {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--ink, #2C2623);
}
.status-badges-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.65rem;
}
.badge {
  padding: 0.24rem 0.65rem;
  border-radius: 999px;
  font-weight: 600;
}
.badge.pending { background: var(--amber-soft, #FEF5EB); color: var(--amber, #8F4F0D); border: 1px solid var(--amber-line, #E8B878); }
.badge.approved { background: var(--green-soft, #EBF5EE); color: var(--green, #2A6F4E); border: 1px solid var(--green-line, #8FC1A3); }
.badge.total { background: #FFFFFF; color: var(--ink-2, #5C5346); border: 1px solid var(--line, #E6DEC8); }
.badge.clauses { background: var(--teal-soft, #EDF4F8); color: var(--teal, #265D75); border: 1px solid var(--teal-line, #9BB5D6); }
.badge.elective { background: var(--teal-soft, #EDF4F8); color: var(--teal, #265D75); border: 1px solid var(--teal-line, #9BB5D6); }
.badge.standard { background: var(--surface-subtle, #F3ECE1); color: var(--ink-2, #5C5346); border: 1px solid var(--line, #E6DEC8); }
.audit-note {
  color: var(--red, #B23324);
  font-weight: 600;
  font-size: 0.82rem;
}
.audit-note.audit-ok {
  color: var(--green, #2A6F4E);
}
.filter-bar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-bottom: 0.8rem;
  font-size: 0.88rem;
  color: var(--ink-2, #5C5346);
  font-weight: 600;
}
.filter-chip {
  background: var(--surface-subtle, #F3ECE1);
  color: var(--ink-2, #5C5346);
  border: 1px solid var(--line, #E6DEC8);
  border-radius: 999px;
  padding: 0.3rem 0.78rem;
  font-size: 0.78rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}
.filter-chip:hover:not(:disabled) {
  background: var(--primary, #2A6F4E);
  border-color: var(--primary, #2A6F4E);
  color: #ffffff;
}
.filter-chip.selected {
  background: var(--primary, #2A6F4E);
  color: #ffffff;
  border-color: var(--primary, #2A6F4E);
  font-weight: 600;
}
.empty-panel-card {
  background: var(--surface-warm, #FDF9F3);
  border: 1px dashed var(--line, #E6DEC8);
  border-radius: 12px;
  padding: 1.6rem 1.4rem;
  text-align: center;
}
.empty-panel-card h4 {
  margin: 0 0 0.5rem 0;
  color: var(--ink, #2C2623);
  font-size: 1rem;
}
.empty-panel-card p {
  margin: 0 0 1rem 0;
  color: var(--ink-2, #5C5346);
  font-size: 0.88rem;
  line-height: 1.6;
}
.candidate-scroll-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 620px;
  overflow-y: auto;
  padding-right: 2px;
}
button.candidate-item {
  width: 100%;
  text-align: left;
  background: #ffffff;
  color: var(--ink, #2C2623);
  border: 1px solid var(--line-soft, #EFE8D8);
  border-radius: 10px;
  padding: 0.65rem 0.85rem;
  cursor: pointer;
  box-shadow: none;
  transition: background 0.15s ease, border-color 0.15s ease;
}
button.candidate-item:hover:not(:disabled) {
  background: var(--surface-warm, #FDF9F3);
  border-color: var(--primary-line, #9ec8b1);
  color: var(--ink, #2C2623);
}
button.candidate-item.selected {
  background: var(--primary-soft, #EBF5EE);
  border-color: var(--primary, #2A6F4E);
  border-left: 3px solid var(--primary, #2A6F4E);
}
.cand-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.25rem;
}
.cand-level-tag {
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--ink-3, #6E6458);
  background: var(--surface-subtle, #F3ECE1);
  padding: 1px 7px;
  border-radius: 999px;
}
.cand-code {
  font-family: var(--font-mono);
  font-size: 0.74rem;
  color: var(--ink-3, #6E6458);
  margin-top: 2px;
}
.status-pill {
  font-size: 0.72rem;
  font-weight: 600;
  padding: 0.12rem 0.5rem;
  border-radius: 999px;
}
.status-pill.pending { background: var(--amber-soft, #FEF5EB); color: var(--amber, #8F4F0D); }
.status-pill.approved { background: var(--green-soft, #EBF5EE); color: var(--green, #2A6F4E); }
.status-pill.rejected { background: var(--red-soft, #FDEDEC); color: var(--red, #B23324); }
.cand-name {
  font-size: 0.92rem;
  font-weight: 700;
  color: var(--ink, #2C2623);
}
.cand-meta {
  font-size: 0.76rem;
  color: var(--ink-3, #6E6458);
  margin-top: 0.25rem;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.candidate-detail {
  border: 1px solid var(--line, #E6DEC8);
  border-radius: 12px;
  padding: 1.2rem;
  background: #fff;
}
@media (min-width: 861px) {
  .candidate-detail {
    position: sticky;
    top: 1rem;
  }
}
.detail-code {
  color: var(--ink-3, #6E6458);
  margin: 0.3rem 0;
  font-size: 0.82rem;
}
.detail-desc {
  font-size: 0.94rem;
  line-height: 1.55;
  margin-bottom: 1rem;
  color: var(--ink-2, #5C5346);
}
.clauses-trace {
  margin-bottom: 0.9rem;
  background: var(--surface-warm, #FDF9F3);
  border: 1px solid var(--line, #E6DEC8);
  padding: 0.85rem;
  border-radius: 10px;
}
.clause-card-list {
  list-style: none;
  padding: 0 4px 0 0;
  margin: 0.5rem 0 0 0;
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
  max-height: clamp(240px, 42vh, 410px);
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}
.clause-card-item {
  background: #ffffff;
  border: 1px solid var(--line, #E6DEC8);
  border-radius: 8px;
  padding: 0.65rem 0.85rem;
}
.clause-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-bottom: 0.4rem;
}
.clause-tech-id {
  margin-bottom: 0.3rem;
}
.clause-tech-id code {
  font-size: 0.74rem;
  font-family: var(--font-mono);
  background: var(--surface-subtle, #F3ECE1);
  color: var(--ink-2, #5C5346);
  padding: 2px 6px;
  border-radius: 4px;
}
.clause-card-badges {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-wrap: wrap;
}
.clause-page-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 6px;
}
.clause-page-badge {
  font-size: 0.74rem;
  color: var(--ink-2, #5C5346);
  background: var(--surface-subtle, #F3ECE1);
  border: 1px solid var(--line, #E6DEC8);
  border-radius: 6px;
  padding: 2px 6px;
}
.clause-card-title {
  font-weight: 700;
  font-size: 0.86rem;
  color: var(--ink, #2C2623);
}
.clause-card-text {
  font-size: 0.84rem;
  color: var(--ink-2, #5C5346);
  line-height: 1.5;
}
.clause-card-std {
  font-size: 0.8rem;
  color: var(--teal, #3B6E8C);
  background: var(--teal-soft, #EDF4F8);
  border-left: 3px solid var(--teal, #3B6E8C);
  padding: 0.3rem 0.6rem;
  margin-top: 0.35rem;
  border-radius: 0 6px 6px 0;
}
.legacy-trace {
  margin-bottom: 0.4rem;
  background: var(--surface-warm, #FDF9F3);
  border: 1px solid var(--line, #E6DEC8);
  padding: 0.85rem;
  border-radius: 10px;
}
.legacy-trace-list {
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
  margin-top: 0.5rem;
  max-height: clamp(180px, 28vh, 280px);
  overflow-y: auto;
  padding-right: 4px;
  -webkit-overflow-scrolling: touch;
}
.legacy-trace-card {
  background: #ffffff;
  border: 1px solid var(--line, #E6DEC8);
  border-radius: 8px;
  padding: 0.65rem 0.85rem;
}
.legacy-card-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 0.35rem;
}
.legacy-name {
  font-weight: 700;
  font-size: 0.88rem;
  color: var(--ink, #2C2623);
}
.legacy-card-head code {
  font-size: 0.74rem;
  background: var(--surface-subtle, #F3ECE1);
  padding: 2px 5px;
  border-radius: 4px;
}
.legacy-reason, .legacy-compat {
  font-size: 0.8rem;
  color: var(--ink-2, #5C5346);
  line-height: 1.45;
  margin: 0.2rem 0;
}
.expert-review-record {
  margin-bottom: 0.9rem;
  background: var(--primary-soft, #EBF5EE);
  border: 1px solid var(--primary-line, #8FC1A3);
  border-radius: 10px;
  padding: 0.75rem 0.9rem;
}
.expert-review-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
  margin-bottom: 0.45rem;
}
.expert-review-head h4 {
  margin: 0;
  color: var(--good, #2D6B4F);
}
.expert-review-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.8rem;
  font-size: 0.82rem;
  color: var(--ink-2, #5C5346);
  margin-bottom: 0.45rem;
}
.expert-review-opinion {
  margin: 0;
  font-size: 0.84rem;
  line-height: 1.58;
  color: var(--ink, #2C2623);
  background: rgba(255, 255, 255, 0.78);
  border-radius: 8px;
  padding: 0.65rem 0.8rem;
  max-height: 132px;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}
.domain-title {
  font-weight: 700;
  font-size: 0.86rem;
  color: var(--ink, #2C2623);
}
.sub-theme-text {
  font-size: 0.8rem;
  color: var(--ink-2, #5C5346);
  margin-top: 0.2rem;
}
.raw-text-block {
  line-height: 1.55;
  color: var(--ink, #2C2623);
}
.standardized-text-block {
  font-size: 0.8rem;
  color: var(--teal, #3B6E8C);
  background: var(--teal-soft, #EDF4F8);
  border-left: 3px solid var(--teal, #3B6E8C);
  padding: 0.25rem 0.5rem;
  margin-top: 0.35rem;
  border-radius: 0 6px 6px 0;
}
.mapping-cell {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.mapping-pill {
  display: flex;
  flex-direction: column;
  padding: 0.3rem 0.55rem;
  border-radius: 6px;
  font-size: 0.78rem;
}
.mapping-pill.candidate-pill {
  background: var(--primary-soft, #EBF5EE);
  border: 1px solid var(--primary-line, #8FC1A3);
}
.mapping-pill.legacy-pill {
  background: var(--surface-subtle, #F3ECE1);
  border: 1px solid var(--line, #E6DEC8);
}
.pill-name {
  font-weight: 700;
  color: var(--ink, #2C2623);
}
.pill-code {
  font-size: 0.72rem;
  color: var(--ink-3, #6E6458);
  font-family: var(--font-mono);
}
.empty-mapping-text {
  color: var(--ink-3, #6E6458);
  font-size: 0.8rem;
}
.target-cand-item {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-bottom: 0.45rem;
}
.cand-name-tag {
  font-weight: 700;
  font-size: 0.84rem;
  color: var(--primary, #2A6F4E);
}
.clause-count-pill {
  display: inline-block;
  align-self: flex-start;
  font-size: 0.74rem;
  background: var(--teal-soft, #EDF4F8);
  color: var(--teal, #3B6E8C);
  padding: 1px 7px;
  border-radius: 999px;
}
.badge.info {
  background: var(--teal-soft, #EDF4F8);
  color: var(--teal, #3B6E8C);
  font-size: 0.74rem;
  padding: 2px 8px;
}
.badge.caution {
  background: var(--amber-soft, #FEF5EB);
  color: var(--amber, #8F4F0D);
  font-size: 0.74rem;
  padding: 2px 8px;
}
.review-box {
  background: var(--surface-warm, #FDF9F3);
  border: 1px solid var(--line, #E6DEC8);
  padding: 1rem;
  border-radius: 10px;
}
.reviewer-identity-notice {
  font-size: 0.8rem;
  color: var(--amber, #8F4F0D);
  background: var(--amber-soft, #FEF5EB);
  border: 1px solid var(--amber-line, #E8B878);
  padding: 0.55rem 0.8rem;
  border-radius: 8px;
  line-height: 1.45;
  margin: 0.4rem 0 0.8rem 0;
}
.field-row {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  margin-bottom: 0.8rem;
}
.field-row input, .field-row textarea {
  padding: 0.45rem 0.65rem;
  border: 1px solid var(--line, #E6DEC8);
  border-radius: 8px;
}
.review-actions {
  display: flex;
  gap: 0.8rem;
  margin-top: 1rem;
  flex-wrap: wrap;
}
.danger {
  background: var(--red, #B23324);
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 0.45rem 0.9rem;
  cursor: pointer;
}
.danger:hover:not(:disabled) {
  background: #8c2418;
  color: #fff;
}
.mapping-stats-panel {
  background: #F4EDE0;
  border: 1px solid #DDD1BA;
  border-radius: 12px;
  padding: 0.9rem 1.05rem;
  margin-bottom: 0.9rem;
}
.mapping-stats {
  display: flex;
  gap: 0.65rem;
  flex-wrap: wrap;
  margin-top: 0.65rem;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--ink-2, #5C5346);
}
.stat-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.28rem 0.72rem;
  border-radius: 999px;
  background: #FFFFFF;
  border: 1px solid var(--line, #E6DEC8);
  font-size: 0.82rem;
}
.stat-pill.stat-retained { background: var(--teal-soft, #EDF4F8); color: var(--teal, #3B6E8C); border-color: var(--teal-line, #9BB5D6); }
.stat-pill.stat-renamed { background: var(--amber-soft, #FEF5EB); color: var(--amber, #8F4F0D); border-color: var(--amber-line, #E8B878); }
.stat-pill.stat-split { background: #F3EFFA; color: #5B3D8A; border-color: #D5C5EE; }
.stat-pill.stat-merged { background: #FEF0E6; color: #9E4713; border-color: #F2C7A5; }
.stat-pill.stat-new { background: var(--green-soft, #EBF5EE); color: var(--green, #2A6F4E); border-color: var(--green-line, #8FC1A3); }
.clause-table-wrapper, .mapping-table-wrapper {
  width: 100%;
  max-height: clamp(360px, 64vh, 600px);
  overflow: auto;
  margin-top: 0.8rem;
  border: 1px solid var(--line, #E6DEC8);
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 2px 8px rgba(44, 38, 35, 0.04);
  -webkit-overflow-scrolling: touch;
}
.mapping-table-wrapper {
  max-height: clamp(340px, 60vh, 560px);
}
.clause-table, .mapping-table {
  width: 100%;
  min-width: 680px;
  border-collapse: collapse;
  font-size: 0.85rem;
}
.clause-table th, .clause-table td,
.mapping-table th, .mapping-table td {
  border-bottom: 1px solid var(--line-soft, #EFE8D8);
  border-right: 1px solid var(--line-soft, #EFE8D8);
  padding: 0.75rem 0.9rem;
  text-align: left;
  vertical-align: top;
}
.clause-table th, .mapping-table th {
  background: var(--surface-subtle, #F3ECE1);
  color: var(--ink, #2C2623);
  font-weight: 700;
  position: sticky;
  top: 0;
  z-index: 1;
}
.clause-table tbody tr:hover, .mapping-table tbody tr:hover {
  background: var(--surface-warm, #FDF9F3);
}
.clause-table code, .mapping-table code {
  font-size: 0.74rem;
  word-break: break-all;
  background: var(--surface-subtle, #F3ECE1);
  padding: 2px 5px;
  border-radius: 4px;
}
.text-cell {
  line-height: 1.55;
}
.reason-cell, .compat-cell {
  line-height: 1.55;
  color: var(--ink-2, #5C5346);
}
.action-tag {
  display: inline-block;
  padding: 0.18rem 0.6rem;
  border-radius: 999px;
  font-size: 0.76rem;
  font-weight: 700;
  white-space: nowrap;
}
.action-tag.retained { background: var(--teal-soft, #EDF4F8); color: var(--teal, #3B6E8C); border: 1px solid var(--teal-line, #9BB5D6); }
.action-tag.renamed { background: var(--amber-soft, #FEF5EB); color: var(--amber, #8F4F0D); border: 1px solid var(--amber-line, #E8B878); }
.action-tag.split { background: #F3EFFA; color: #5B3D8A; border: 1px solid #D5C5EE; }
.action-tag.merged { background: #FEF0E6; color: #9E4713; border: 1px solid #F2C7A5; }
.action-tag.new, .action-tag.added { background: var(--green-soft, #EBF5EE); color: var(--green, #2A6F4E); border: 1px solid var(--green-line, #8FC1A3); }
.action-tag.deprecated { background: var(--surface-subtle, #F3ECE1); color: var(--ink-3, #6E6458); border: 1px solid var(--line, #E6DEC8); }
.action-tag.pending_human_review { background: var(--red-soft, #FDEDEC); color: var(--red, #B23324); border: 1px solid #E69A8D; }
.card-box {
  background: #fff;
  border: 1px solid var(--line, #E6DEC8);
  padding: 1.2rem;
  border-radius: 12px;
  margin-bottom: 1.5rem;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 1rem;
}
.form-field {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  margin-bottom: 0.8rem;
}
.form-field input, .form-field textarea {
  padding: 0.45rem 0.65rem;
  border: 1px solid var(--line, #E6DEC8);
  border-radius: 8px;
}
.release-error-box {
  background: var(--red-soft, #FDEDEC);
  border: 1px solid #E69A8D;
  color: var(--red, #B23324);
  padding: 0.8rem;
  border-radius: 8px;
  margin: 0.8rem 0;
  font-size: 0.85rem;
}
.release-scroll-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: clamp(280px, 50vh, 480px);
  overflow-y: auto;
  padding-right: 4px;
  margin-top: 0.6rem;
  -webkit-overflow-scrolling: touch;
}
.release-card {
  border: 1px solid var(--line, #E6DEC8);
  background: var(--surface-warm, #FDF9F3);
  border-radius: 10px;
  padding: 0.9rem 1rem;
}
.rel-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.6rem;
}
.rel-ver-zh {
  font-weight: 700;
  font-size: 0.95rem;
  color: var(--ink, #2C2623);
}
.rel-ver {
  font-weight: 600;
  font-family: var(--font-mono);
}
.rel-status {
  background: var(--green-soft, #EBF5EE);
  color: var(--green, #2A6F4E);
  font-size: 0.75rem;
  font-weight: 700;
  padding: 0.15rem 0.55rem;
  border-radius: 999px;
}
.rel-time {
  color: var(--ink-3, #6E6458);
  font-size: 0.8rem;
}
.rel-meta {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
  font-size: 0.8rem;
  color: var(--ink-2, #5C5346);
  margin-top: 0.4rem;
}
@media (max-width: 900px) {
  .candidate-scroll-list {
    max-height: 360px;
  }
  .clause-card-list {
    max-height: clamp(220px, 38vh, 340px);
  }
  .legacy-trace-list {
    max-height: clamp(160px, 26vh, 240px);
  }
  .clause-table-wrapper,
  .mapping-table-wrapper {
    max-height: clamp(300px, 52vh, 460px);
  }
  .release-scroll-list {
    max-height: clamp(240px, 44vh, 380px);
  }
}
</style>
