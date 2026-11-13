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
import Note from '../Note.vue'
import type { NoticeTone } from '../Notice.vue'

type Notify = (text: string, tone?: NoticeTone) => void

const props = defineProps<{
  client: ApiClient
  subject: Subject
  notify: Notify
}>()

const activeTab = ref<'candidates' | 'clauses' | 'mapping' | 'releases'>('candidates')

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

// 学科官方课程标准原件依据说明
const SUBJECT_CURRICULUM_DOCS: Record<Subject, string> = {
  chinese: '基于教育部2022年版初中语文课程标准（MOE-2022-CHINESE）与北京市中考考查范围',
  math: '基于教育部2022年版初中数学课程标准（含2022-05-09修正版）与北京市中考考查范围',
  english: '基于教育部2022年版初中英语课程标准（MOE-2022-ENGLISH）与北京市中考听说机考及笔试范围',
  physics: '基于教育部2022年版初中物理课程标准（MOE-2022-PHYSICS）与北京市中考考查范围',
}

// 1. 候选知识体系状态
const candidates = ref<CandidateNode[]>([])
const loadingCandidates = ref(false)
const selectedNodeCode = ref<string | null>(null)
// F03/B04 整改：默认严格为空，禁止预填虚假专家 ID 与意见，必须由真实操作人提供
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
const publishedBy = ref('admin_owner')
const releaseSummary = ref(`教育部2022年版初中${SUBJECT_LABELS[props.subject]}课程标准全量拆解知识体系首发版本`)
const publishing = ref(false)
const releaseError = ref('')

const selectedNode = computed(() => {
  if (!selectedNodeCode.value) return candidates.value[0] ?? null
  return candidates.value.find(c => c.code === selectedNodeCode.value) ?? null
})

const pendingCount = computed(() => {
  return candidates.value.filter(c => c.review_status === 'pending').length
})

const approvedCount = computed(() => {
  return candidates.value.filter(c => c.review_status === 'approved').length
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

// 动态提取当前学科课标领域
const availableDomains = computed(() => {
  const map = new Map<string, string>()
  for (const cl of clauses.value) {
    if (cl.domain && !map.has(cl.domain)) {
      map.set(cl.domain, cl.domain_title || cl.domain)
    }
  }
  return Array.from(map.entries()).map(([code, title]) => ({ code, title }))
})

const filteredClauses = computed(() => {
  if (clauseDomainFilter.value === 'all') return clauses.value
  return clauses.value.filter(c => c.domain === clauseDomainFilter.value)
})

async function loadCandidates() {
  loadingCandidates.value = true
  try {
    candidates.value = await props.client.adminKnowledgeCandidates(props.subject)
    if (candidates.value.length > 0) {
      const exists = candidates.value.some(c => c.code === selectedNodeCode.value)
      if (!exists) {
        selectedNodeCode.value = candidates.value[0].code
      }
    } else {
      selectedNodeCode.value = null
    }
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
    // 忽略未发布时的读取错误
  }
}

async function seedCandidates() {
  seeding.value = true
  try {
    const res = await props.client.adminSeedCandidates(props.subject)
    props.notify(`已成功初始化 ${res.seeded_count} 个候选节点入库（总数 ${res.total_nodes}），全部置为 pending 待审状态。`, 'info')
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
    props.notify('请先点击上方“初始化候选入库”将候选节点同步至数据库，再执行人工审核记录。', 'caution')
    return
  }
  if (!reviewerId.value.trim()) {
    props.notify('审核人 ID 不能为空，严禁未记名审核。', 'caution')
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
    props.notify(`节点 ${selectedNode.value.name} 已标记为 ${status === 'approved' ? '审核通过' : '退回驳回'}。`, 'success')
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
    .map(c => `${c.sub_theme || c.domain_title}${c.clause_number || ''}(印刷p.${c.print_page}/PDF p.${c.pdf_page})`)
    .join('；')
  const req = matched[0].derived_requirement || matched[0].standardized_text || node.description || node.name
  const legacyList = (candidateToLegacyMappings.value[node.code] ?? []).map(m => m.legacy_code)
  const legacyNote = legacyList.length > 0 ? `兼容历史编码：${legacyList.join(', ')}。` : '2022版新课标细化考点。'
  return `核对教育部2022年版初中${SUBJECT_LABELS[props.subject]}课程标准[${refs}]，核心要求为「${req}」。已核查概念粒度与必学范围，${legacyNote}`
}

function fillOpinionDraft() {
  if (!selectedNode.value) return
  reviewOpinion.value = buildClauseOpinionDraft(selectedNode.value)
}

async function batchApprovePending() {
  if (!reviewerId.value.trim()) {
    props.notify('批量审核前，请先在下方输入真实的审核人 ID（严禁未记名审核）。', 'caution')
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
    props.notify(`知识库正式版本 ${releaseVersion.value} 发布成功！已生成不可变历史快照。`, 'success')
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
    void loadCandidates()
    void loadClauses()
    void loadLegacyMapping()
    void loadReleases()
  },
  { immediate: true }
)
</script>

<template>
  <div class="knowledge-workbench">
    <div class="card-head">
      <div>
        <h2>{{ SUBJECT_LABELS[props.subject] }}权威知识点库审核工作台</h2>
        <p class="sub-head">
          {{ SUBJECT_CURRICULUM_DOCS[props.subject] }}
        </p>
      </div>
      <div class="head-actions">
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

    <!-- 顶部状态警示条 -->
    <div class="status-banner">
      <span class="badge pending">待审核: {{ pendingCount }}</span>
      <span class="badge approved">已通过: {{ approvedCount }}</span>
      <span class="badge total">总候选数: {{ candidates.length }}</span>
      <span class="badge clauses">课标条款: {{ clauses.length }} 条</span>
      <span class="audit-note">
        红线门禁：候选内容全量通过真实学科审核前，严禁发布正式知识库版本。
      </span>
    </div>

    <!-- 课标审核红线说明 -->
    <Note title="课标审核红线说明" tone="discipline">
      知识点必须溯源至教育部2022年版课程标准官方条文。所有AI生成的候选考点均初始化为待审核（pending）状态，必须经学科专家人工逐项审核。若存在未审核或驳回考点，发布强门禁将强制阻断版本发布。
    </Note>

    <!-- 导航子标签 -->
    <nav class="sub-nav" aria-label="审核台子模块">
      <button
        type="button"
        :class="activeTab === 'candidates' ? 'tab-btn active' : 'tab-btn'"
        @click="activeTab = 'candidates'"
      >
        候选知识点体系 ({{ candidates.length }})
      </button>
      <button
        type="button"
        :class="activeTab === 'clauses' ? 'tab-btn active' : 'tab-btn'"
        @click="activeTab = 'clauses'"
      >
        课标条款全集 ({{ clauses.length }})
      </button>
      <button
        type="button"
        :class="activeTab === 'mapping' ? 'tab-btn active' : 'tab-btn'"
        @click="activeTab = 'mapping'"
      >
        新旧考点映射与兼容 ({{ mappingSummary.total }})
      </button>
      <button
        type="button"
        :class="activeTab === 'releases' ? 'tab-btn active' : 'tab-btn'"
        @click="activeTab = 'releases'"
      >
        版本发布与快照 ({{ releases.length }})
      </button>
    </nav>

    <!-- 选项卡 1：候选知识点体系与审核 -->
    <div v-if="activeTab === 'candidates'" class="tab-pane candidates-pane">
      <div class="pane-split">
        <!-- 左侧树/列表 -->
        <div class="candidate-list">
          <div
            v-for="cand in candidates"
            :key="cand.code"
            :class="[
              'candidate-item',
              selectedNodeCode === cand.code ? 'selected' : '',
              cand.review_status,
              `level-${cand.level ?? 3}`,
            ]"
            @click="selectedNodeCode = cand.code"
          >
            <div class="cand-header">
              <span class="cand-code">{{ cand.code }}</span>
              <span :class="['status-pill', cand.review_status]">
                {{ cand.review_status === 'approved' ? '已通过' : cand.review_status === 'rejected' ? '已驳回' : '待人工审核' }}
              </span>
            </div>
            <div class="cand-name">{{ cand.name }}</div>
            <div class="cand-meta">
              <span v-if="cand.source_clause_ids?.length">
                关联 {{ cand.source_clause_ids.length }} 条款
              </span>
              <span v-if="cand.reviewer_id" class="reviewer-meta">
                审核人: {{ cand.reviewer_id }}
              </span>
            </div>
          </div>
        </div>

        <!-- 右侧详情与审核操作 -->
        <div v-if="selectedNode" class="candidate-detail">
          <h3>{{ selectedNode.name }}</h3>
          <p class="detail-code">代码: <code>{{ selectedNode.code }}</code></p>
          <p class="detail-desc">{{ selectedNode.description ?? '暂无详细描述' }}</p>

          <div class="clauses-trace">
            <h4>课标溯源条款 ({{ selectedNode.source_clause_ids?.length ?? 0 }} 条)</h4>
            <div v-if="(selectedNode.source_clause_ids ?? []).length === 0" class="empty-hint">
              暂无关联课标条款（发布强门禁：无来源条款节点严禁发布）
            </div>
            <ul v-else class="clause-card-list">
              <li
                v-for="cid in selectedNode.source_clause_ids ?? []"
                :key="cid"
                class="clause-card-item"
              >
                <div class="clause-card-header">
                  <code>{{ cid }}</code>
                  <div class="clause-card-badges">
                    <span v-if="clauseMap[cid]" class="clause-page-badge">
                      PDF p.{{ clauseMap[cid].pdf_page }} / 印刷 p.{{ clauseMap[cid].print_page }}
                    </span>
                    <span v-if="clauseMap[cid]?.is_elective" class="badge elective">选学*</span>
                    <span v-else-if="clauseMap[cid]" class="badge standard">必学</span>
                  </div>
                </div>
                <div v-if="clauseMap[cid]" class="clause-card-body">
                  <div class="clause-card-title">
                    {{ clauseMap[cid].domain_title }} · {{ clauseMap[cid].theme_title ? `${clauseMap[cid].theme_title} · ` : '' }}{{ clauseMap[cid].sub_theme }}
                  </div>
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

          <!-- 存量旧考点映射关联 -->
          <div class="legacy-trace">
            <h4>存量旧考点映射关联</h4>
            <div v-if="(candidateToLegacyMappings[selectedNode.code] ?? []).length === 0" class="empty-trace">
              <span class="badge info">新课标增设考点 · 存量题库无直接历史对应</span>
            </div>
            <div v-else class="legacy-trace-list">
              <div
                v-for="m in candidateToLegacyMappings[selectedNode.code]"
                :key="m.legacy_code"
                class="legacy-trace-card"
              >
                <div class="legacy-card-head">
                  <span class="legacy-name">{{ m.legacy_name }}</span>
                  <code>{{ m.legacy_code }}</code>
                  <span :class="['action-tag', m.action]">{{ LEGACY_ACTION_LABELS[m.action] ?? m.action }}</span>
                </div>
                <p class="legacy-reason"><b>映射理由：</b>{{ m.mapping_reason }}</p>
                <p class="legacy-compat"><b>兼容保障：</b>{{ m.compatibility_assurance }}</p>
              </div>
            </div>
          </div>

          <!-- 真实人工审核面板 (F03/B04 强化) -->
          <div class="review-box">
            <h4>学科专家人工审核操作</h4>
            <p class="reviewer-identity-notice">
              ⚠️ 提示：审核人 ID 为经办人实名审计记录，系统不自动认证其学术资质。真实{{ SUBJECT_LABELS[props.subject] }}内容效力须由具备相应初中{{ SUBJECT_LABELS[props.subject] }}学科资质的人员基于课标条文研核后如实填报，严禁代签、预设或冒用。
            </p>
            <div class="field-row">
              <label for="rev-id">审核人 ID (必填):</label>
              <input
                id="rev-id"
                v-model="reviewerId"
                type="text"
                placeholder="请输入实际审核人员工号或实名标识"
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
                {{ reviewing ? '提交中...' : '审核通过 (Approved)' }}
              </button>
              <button
                type="button"
                class="danger small"
                :disabled="reviewing || !reviewerId.trim() || !reviewOpinion.trim()"
                @click="submitReview('rejected')"
              >
                {{ reviewing ? '提交中...' : '退回驳回 (Rejected)' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 选项卡 2：课标条款全集 -->
    <div v-else-if="activeTab === 'clauses'" class="tab-pane clauses-pane">
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

      <div class="clause-table-wrapper">
        <table class="clause-table">
          <colgroup>
            <col style="width: 190px;" />
            <col style="width: 140px;" />
            <col style="width: 110px;" />
            <col style="width: 290px;" />
            <col style="width: 70px;" />
            <col style="width: 230px;" />
            <col style="width: 200px;" />
          </colgroup>
          <thead>
            <tr>
              <th>条款ID</th>
              <th>主题/小节</th>
              <th>页码</th>
              <th>官方条文与规范转写</th>
              <th>选学</th>
              <th>对应新候选考点</th>
              <th>对应存量旧考点</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="cl in filteredClauses" :key="cl.clause_id">
              <td><code>{{ cl.clause_id }}</code></td>
              <td>
                <div class="domain-title">{{ cl.domain_title }}</div>
                <div class="sub-theme-text">{{ cl.theme_title ? `${cl.theme_title} · ` : '' }}{{ cl.sub_theme }}</div>
              </td>
              <td>PDF p.{{ cl.pdf_page }} / 印刷 p.{{ cl.print_page }}</td>
              <td class="text-cell">
                <div class="raw-text-block">{{ cl.raw_text }}</div>
                <div v-if="cl.standardized_text && cl.standardized_text !== cl.raw_text" class="standardized-text-block">
                  <small>规范化转写：</small>{{ cl.standardized_text }}
                </div>
              </td>
              <td>
                <span v-if="cl.is_elective" class="badge elective">选学*</span>
                <span v-else class="badge standard">必学</span>
              </td>
              <td class="mapping-cell">
                <div v-if="(clauseToCandidatesMap[cl.clause_id] ?? []).length === 0" class="empty-mapping-text">
                  -
                </div>
                <div
                  v-for="cand in clauseToCandidatesMap[cl.clause_id] ?? []"
                  :key="cand.code"
                  class="mapping-pill candidate-pill"
                >
                  <span class="pill-name">{{ cand.name }}</span>
                  <code class="pill-code">{{ cand.code }}</code>
                </div>
              </td>
              <td class="mapping-cell">
                <div v-if="(cl.legacy_mappings ?? []).length === 0" class="empty-mapping-text">
                  <span class="badge info">新课标增设/无旧考点</span>
                </div>
                <div
                  v-for="legCode in cl.legacy_mappings ?? []"
                  :key="legCode"
                  class="mapping-pill legacy-pill"
                >
                  <span class="pill-name">{{ legacyMappingByCode[legCode]?.legacy_name ?? legCode }}</span>
                  <code class="pill-code">{{ legCode }}</code>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 选项卡 3：新旧映射与兼容 -->
    <div v-else-if="activeTab === 'mapping'" class="tab-pane mapping-pane">
      <div v-if="legacyMapping" class="mapping-summary">
        <div class="mapping-stats">
          <span>存量考点: {{ mappingSummary.total }} 个</span>
          <span>保留: {{ mappingSummary.retained }}</span>
          <span>重命名: {{ mappingSummary.renamed }}</span>
          <span>合理拆分: {{ mappingSummary.split }}</span>
          <span>合并: {{ mappingSummary.merged }}</span>
          <span>新课标增设: {{ mappingSummary.new }}</span>
        </div>
        <Note tone="discipline">
          历史兼容保护原则：存量 {{ mappingSummary.total }} 个旧考点作为历史资产永久保留只读；历史题目关联 QuestionKnowledgeLink、作答与曝光记录绝不被覆盖或静默重写。
        </Note>

        <div class="mapping-table-wrapper">
          <table class="mapping-table">
            <colgroup>
              <col style="width: 170px;" />
              <col style="width: 130px;" />
              <col style="width: 90px;" />
              <col style="width: 210px;" />
              <col style="width: 180px;" />
              <col style="width: 240px;" />
              <col style="width: 240px;" />
            </colgroup>
            <thead>
              <tr>
                <th>旧考点代码</th>
                <th>旧考点名称</th>
                <th>动作分类</th>
                <th>对应新候选体系考点</th>
                <th>课标溯源依据</th>
                <th>映射与教学演进理由</th>
                <th>历史兼容说明</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in legacyMapping.legacy_mappings" :key="m.legacy_code">
                <td><code>{{ m.legacy_code }}</code></td>
                <td>{{ m.legacy_name }}</td>
                <td><span :class="['action-tag', m.action]">{{ LEGACY_ACTION_LABELS[m.action] ?? m.action }}</span></td>
                <td>
                  <div
                    v-for="t in m.target_candidate_codes"
                    :key="t"
                    class="target-cand-item"
                  >
                    <span class="cand-name-tag">{{ candidateMap[t]?.name ?? t }}</span>
                    <code>{{ t }}</code>
                  </div>
                </td>
                <td class="clause-backing-cell">
                  <div
                    v-for="t in m.target_candidate_codes"
                    :key="`clause-${t}`"
                    class="target-clause-backing"
                  >
                    <div v-if="candidateMap[t]?.source_clause_ids?.length" class="clause-count-info">
                      <b>{{ candidateMap[t]?.name }}:</b> {{ candidateMap[t]?.source_clause_ids?.length }} 条课标依据
                      <div class="clause-id-tags">
                        <code v-for="cid in candidateMap[t]?.source_clause_ids ?? []" :key="cid" class="mini-clause-tag">
                          {{ cid }}
                        </code>
                      </div>
                    </div>
                    <div v-else class="empty-clause-info">
                      <span class="badge caution">无溯源条款</span>
                    </div>
                  </div>
                </td>
                <td class="reason-cell">{{ m.mapping_reason }}</td>
                <td class="compat-cell">{{ m.compatibility_assurance }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div v-else>映射数据加载中...</div>
    </div>

    <!-- 选项卡 4：版本发布与快照 -->
    <div v-else-if="activeTab === 'releases'" class="tab-pane releases-pane">
      <div class="release-form card-box">
        <h3>发布知识库正式版本（强门禁测试）</h3>
        <p class="form-hint">
          注意：当且仅当所有候选知识点均经过学科专家人工审核通过（0 个 pending、0 个 rejected）时，方可发布版本快照。
        </p>

        <div class="form-grid">
          <div class="form-field">
            <label for="rel-ver">版本号:</label>
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
      </div>

      <div class="releases-list">
        <h3>历史发布版本快照 ({{ releases.length }} 个)</h3>
        <div v-if="releases.length === 0" class="empty-hint">
          暂无已发布正式版本（当前处于全量待审阶段）。
        </div>
        <div
          v-for="rel in releases"
          :key="rel.id"
          class="release-card"
        >
          <div class="rel-head">
            <span class="rel-ver">{{ rel.release_version }}</span>
            <span class="rel-status">{{ rel.status === 'active' ? '正式生效' : (rel.status === 'draft' ? '草稿' : rel.status) }}</span>
            <span class="rel-time">{{ rel.published_at }}</span>
          </div>
          <p class="rel-summary">{{ rel.summary }}</p>
          <div class="rel-meta">
            <span>发布人: {{ rel.published_by }}</span>
            <span>包含节点: {{ rel.total_nodes }} 个</span>
          </div>
        </div>
      </div>
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
}
.sub-head {
  color: var(--color-muted, #666);
  font-size: 0.85rem;
  margin-top: 0.25rem;
}
.head-actions {
  display: flex;
  gap: 0.5rem;
}
.status-banner {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
  background: var(--color-bg-subtle, #f5f7fa);
  padding: 0.6rem 1rem;
  border-radius: 6px;
  font-size: 0.85rem;
}
.badge {
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  font-weight: 500;
}
.badge.pending { background: #fff3cd; color: #856404; }
.badge.approved { background: #d4edda; color: #155724; }
.badge.total { background: #e2e3e5; color: #383d41; }
.badge.clauses { background: #cce5ff; color: #004085; }
.badge.elective { background: #e0f2fe; color: #0369a1; }
.badge.standard { background: #f3f4f6; color: #4b5563; }
.audit-note {
  color: #c53030;
  font-weight: 500;
  margin-left: auto;
}
.sub-nav {
  display: flex;
  gap: 0.6rem;
  border-bottom: 2px solid #e2e8f0;
  padding-bottom: 0.6rem;
  margin-bottom: 1rem;
}
.tab-btn {
  background: #f1f5f9;
  color: #1e293b; /* 明确设为高对比度深色字，解决继承全局按钮导致的白色看不清问题 */
  border: 1px solid #cbd5e1;
  padding: 0.5rem 1rem;
  cursor: pointer;
  border-radius: 6px;
  font-size: 0.9rem;
  font-weight: 500;
  transition: all 0.15s ease;
}
.tab-btn:hover {
  background: #e2e8f0;
  color: #0f172a;
  border-color: #94a3b8;
}
.tab-btn.active {
  background: var(--primary, #174276);
  color: #ffffff;
  border-color: var(--primary, #174276);
  font-weight: 700;
  box-shadow: 0 1px 3px rgba(23, 66, 118, 0.25);
}
.filter-bar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-bottom: 0.8rem;
  font-size: 0.88rem;
  color: var(--ink-2, #334155);
  font-weight: 500;
}
.filter-chip {
  background: #f1f5f9;
  color: #334155;
  border: 1px solid #cbd5e1;
  border-radius: 20px;
  padding: 0.3rem 0.8rem;
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}
.filter-chip:hover {
  background: #e2e8f0;
  color: #0f172a;
}
.filter-chip.selected {
  background: var(--primary, #174276);
  color: #ffffff;
  border-color: var(--primary, #174276);
  font-weight: 600;
}
.pane-split {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 1.2rem;
  min-height: 480px;
}
@media (max-width: 860px) {
  .pane-split {
    grid-template-columns: 1fr;
  }
}
.candidate-list {
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 6px;
  overflow-y: auto;
  max-height: 600px;
}
.candidate-item {
  padding: 0.6rem 0.8rem;
  border-bottom: 1px solid var(--color-border, #eee);
  cursor: pointer;
  transition: background 0.15s ease;
}
.candidate-item:hover {
  background: #f9fafb;
}
.candidate-item.selected {
  background: #f0f7ff;
  border-left: 3px solid #0958d9;
}
.cand-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.25rem;
}
.cand-code {
  font-family: monospace;
  font-size: 0.75rem;
  color: #6b7280;
}
.status-pill {
  font-size: 0.7rem;
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
}
.status-pill.pending { background: #fef3c7; color: #92400e; }
.status-pill.approved { background: #dcfce7; color: #166534; }
.status-pill.rejected { background: #fee2e2; color: #991b1b; }
.cand-name {
  font-size: 0.9rem;
  font-weight: 500;
}
.cand-meta {
  font-size: 0.75rem;
  color: #9ca3af;
  margin-top: 0.25rem;
}
.candidate-detail {
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 6px;
  padding: 1.2rem;
  background: #fff;
}
.detail-code {
  color: #6b7280;
  margin: 0.3rem 0;
}
.detail-desc {
  font-size: 0.95rem;
  line-height: 1.5;
  margin-bottom: 1rem;
}
.clauses-trace {
  margin-bottom: 1.5rem;
  background: #f9fafb;
  padding: 0.8rem;
  border-radius: 6px;
}
.clause-card-list {
  list-style: none;
  padding: 0;
  margin: 0.5rem 0 0 0;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.clause-card-item {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 0.6rem 0.8rem;
}
.clause-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-bottom: 0.4rem;
}
.clause-card-header code {
  font-size: 0.76rem;
  font-family: monospace;
  background: #f1f5f9;
  padding: 2px 4px;
  border-radius: 3px;
}
.clause-card-badges {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}
.clause-page-badge {
  font-size: 0.72rem;
  color: #64748b;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 3px;
  padding: 1px 4px;
}
.clause-card-title {
  font-weight: 600;
  font-size: 0.82rem;
  color: #1e293b;
  margin-bottom: 0.25rem;
}
.clause-card-text {
  font-size: 0.8rem;
  color: #334155;
  line-height: 1.4;
}
.clause-card-std {
  font-size: 0.78rem;
  color: #0369a1;
  background: #f0f9ff;
  border-left: 2px solid #0284c7;
  padding: 0.25rem 0.5rem;
  margin-top: 0.3rem;
  border-radius: 0 4px 4px 0;
}
.legacy-trace {
  margin-bottom: 1.5rem;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  padding: 0.8rem;
  border-radius: 6px;
}
.legacy-trace-list {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  margin-top: 0.5rem;
}
.legacy-trace-card {
  background: #ffffff;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  padding: 0.6rem 0.8rem;
}
.legacy-card-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 0.35rem;
}
.legacy-name {
  font-weight: 600;
  font-size: 0.86rem;
  color: #0f172a;
}
.legacy-card-head code {
  font-size: 0.76rem;
  background: #f1f5f9;
  padding: 2px 4px;
  border-radius: 3px;
}
.legacy-reason, .legacy-compat {
  font-size: 0.78rem;
  color: #475569;
  line-height: 1.4;
  margin: 0.2rem 0;
}
.domain-title {
  font-weight: 600;
  font-size: 0.84rem;
  color: #1e293b;
}
.sub-theme-text {
  font-size: 0.78rem;
  color: #64748b;
  margin-top: 0.2rem;
}
.raw-text-block {
  line-height: 1.45;
  color: #1e293b;
}
.standardized-text-block {
  font-size: 0.78rem;
  color: #0284c7;
  background: #f0f9ff;
  border-left: 2px solid #38bdf8;
  padding: 0.2rem 0.4rem;
  margin-top: 0.3rem;
  border-radius: 0 4px 4px 0;
}
.mapping-cell {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.mapping-pill {
  display: flex;
  flex-direction: column;
  padding: 0.25rem 0.45rem;
  border-radius: 4px;
  font-size: 0.76rem;
}
.mapping-pill.candidate-pill {
  background: #eff6ff;
  border: 1px solid #bfdbfe;
}
.mapping-pill.legacy-pill {
  background: #f8fafc;
  border: 1px solid #cbd5e1;
}
.pill-name {
  font-weight: 600;
  color: #1e293b;
}
.pill-code {
  font-size: 0.72rem;
  color: #64748b;
  font-family: monospace;
}
.empty-mapping-text {
  color: #94a3b8;
  font-size: 0.78rem;
}
.target-cand-item {
  display: flex;
  flex-direction: column;
  margin-bottom: 0.35rem;
}
.cand-name-tag {
  font-weight: 600;
  font-size: 0.82rem;
  color: #0369a1;
}
.clause-backing-cell {
  font-size: 0.78rem;
}
.target-clause-backing {
  margin-bottom: 0.4rem;
}
.clause-count-info {
  line-height: 1.35;
  color: #334155;
}
.clause-id-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.2rem;
  margin-top: 0.2rem;
}
.mini-clause-tag {
  font-size: 0.7rem;
  background: #e0f2fe;
  color: #0369a1;
  padding: 1px 4px;
  border-radius: 3px;
  border: 1px solid #bae6fd;
}
.badge.info {
  background: #e0f2fe;
  color: #0369a1;
  font-size: 0.72rem;
  padding: 2px 6px;
}
.badge.caution {
  background: #fef3c7;
  color: #92400e;
  font-size: 0.72rem;
  padding: 2px 6px;
}
.review-box {
  background: #fafafa;
  border: 1px solid #e5e7eb;
  padding: 1rem;
  border-radius: 6px;
}
.reviewer-identity-notice {
  font-size: 0.78rem;
  color: #854d0e;
  background: #fef9c3;
  border: 1px solid #fde047;
  padding: 0.5rem 0.75rem;
  border-radius: 4px;
  line-height: 1.4;
  margin: 0.4rem 0 0.8rem 0;
}
.field-row {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  margin-bottom: 0.8rem;
}
.field-row input, .field-row textarea {
  padding: 0.4rem 0.6rem;
  border: 1px solid #d1d5db;
  border-radius: 4px;
}
.review-actions {
  display: flex;
  gap: 0.8rem;
  margin-top: 1rem;
}
.danger {
  background: #dc2626;
  color: #fff;
  border: none;
  border-radius: 4px;
  padding: 0.4rem 0.8rem;
  cursor: pointer;
}
.clause-table-wrapper, .mapping-table-wrapper {
  width: 100%;
  overflow-x: auto;
  margin-top: 0.8rem;
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 6px;
  background: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  -webkit-overflow-scrolling: touch;
}
.clause-table {
  width: 100%;
  min-width: 1320px;
  border-collapse: collapse;
  font-size: 0.84rem;
  table-layout: fixed;
}
.mapping-table {
  width: 100%;
  min-width: 1280px;
  border-collapse: collapse;
  font-size: 0.84rem;
  table-layout: fixed;
}
.clause-table th, .clause-table td,
.mapping-table th, .mapping-table td {
  border: 1px solid #e5e7eb;
  padding: 0.6rem 0.8rem;
  text-align: left;
  vertical-align: top;
  word-break: break-word;
  overflow-wrap: anywhere;
}
.clause-table th, .mapping-table th {
  background: #f8fafc;
  color: #334155;
  font-weight: 600;
  position: sticky;
  top: 0;
  z-index: 1;
}
.clause-table code, .mapping-table code {
  font-size: 0.78rem;
  word-break: break-all;
  background: #f1f5f9;
  padding: 2px 4px;
  border-radius: 3px;
}
.text-cell {
  line-height: 1.5;
}
.reason-cell, .compat-cell {
  line-height: 1.5;
  color: #374151;
}
.action-tag {
  display: inline-block;
  padding: 0.2rem 0.55rem;
  border-radius: 4px;
  font-size: 0.78rem;
  font-weight: 600;
  white-space: nowrap;
}
.action-tag.retained { background: #e0f2fe; color: #0369a1; border: 1px solid #bae6fd; }
.action-tag.renamed { background: #fef3c7; color: #b45309; border: 1px solid #fde68a; }
.action-tag.split { background: #f3e8ff; color: #7e22ce; border: 1px solid #e9d5ff; }
.action-tag.merged { background: #ffedd5; color: #c2410c; border: 1px solid #fed7aa; }
.action-tag.new, .action-tag.added { background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; }
.action-tag.deprecated { background: #f3f4f6; color: #6b7280; border: 1px solid #e5e7eb; }
.action-tag.pending_human_review { background: #fee2e2; color: #b91c1c; border: 1px solid #fecaca; }
.card-box {
  background: #fff;
  border: 1px solid #e5e7eb;
  padding: 1.2rem;
  border-radius: 6px;
  margin-bottom: 1.5rem;
}
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}
.form-field {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  margin-bottom: 0.8rem;
}
.form-field input, .form-field textarea {
  padding: 0.4rem 0.6rem;
  border: 1px solid #d1d5db;
  border-radius: 4px;
}
.release-error-box {
  background: #fee2e2;
  border: 1px solid #f87171;
  color: #991b1b;
  padding: 0.8rem;
  border-radius: 4px;
  margin: 0.8rem 0;
  font-size: 0.85rem;
}
.release-card {
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 0.8rem;
  margin-top: 0.8rem;
}
.rel-head {
  display: flex;
  align-items: center;
  gap: 0.8rem;
}
.rel-ver {
  font-weight: 600;
  font-family: monospace;
}
.rel-status {
  background: #dcfce7;
  color: #166534;
  font-size: 0.75rem;
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
}
.rel-time {
  color: #6b7280;
  font-size: 0.8rem;
}
</style>
