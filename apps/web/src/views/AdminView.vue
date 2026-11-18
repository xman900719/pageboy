<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import {
  describeError,
  SUBJECT_LABELS,
  type ApiClient,
  type PoolHealth,
  type RightsStatus,
  type SourceDetail,
  type Subject,
} from '../api'
import { ADMIN_PIPELINE_NOTE, ATTACHMENT_STATUS_LABELS, RIGHTS_STATUS_LABELS, fmtBytes, shortTime } from '../copy'
import { getKnowledgeLabel, getOperatorLabel } from '../config/knowledge'
import HelpBubble from '../components/HelpBubble.vue'
import PoolHealthCard from '../components/PoolHealthCard.vue'
import type { NoticeTone } from '../components/Notice.vue'
import AttachmentCard from '../components/admin/AttachmentCard.vue'
import QuestionVersionsCard from '../components/admin/QuestionVersionsCard.vue'
import SourceReviewCard from '../components/admin/SourceReviewCard.vue'
import StageTabStrip from '../components/admin/StageTabStrip.vue'
import StepFlowWorkspace from '../components/admin/StepFlowWorkspace.vue'
import type { StageGroup, StepDefinition, StepFlowContext } from '../components/admin/stepFlow'

type Notify = (text: string, tone?: NoticeTone) => void
export type LedgerSubTab = 'sources' | 'attachments' | 'versions' | 'health'
export type SourceStepId = 'pick' | 'detail' | 'review'

const props = withDefaults(
  defineProps<{
    client: ApiClient
    subject: Subject
    notify: Notify
    subTab?: LedgerSubTab
  }>(),
  {
    subTab: 'sources',
  },
)

const emit = defineEmits<{
  (e: 'update:subTab', next: LedgerSubTab): void
}>()

const activeSubTab = ref<LedgerSubTab>(props.subTab)
watch(
  () => props.subTab,
  next => {
    if (next) activeSubTab.value = next
  },
)

function setSubTab(next: LedgerSubTab) {
  activeSubTab.value = next
  emit('update:subTab', next)
}

const sources = ref<SourceDetail[] | null>(null)
const loadError = ref('')
const selectedId = ref<string | null>(null)
const sourceStep = ref<SourceStepId>('pick')
const sourcePickMode = ref<'list' | 'create'>('list')
const detailPaneRef = ref<HTMLElement | null>(null)
const newTitle = ref('')
const newRights = ref<RightsStatus>('unknown')
const creating = ref(false)
const formError = ref('')
const prefillKnowledgeId = ref<string | undefined>(undefined)

const poolHealth = ref<PoolHealth | null>(null)
const poolLoading = ref(false)

const filteredSources = computed(() => {
  if (!sources.value) return []
  return sources.value.filter(s => s.source.subject === props.subject)
})

const unverifiedCount = computed(
  () => filteredSources.value.filter(s => !s.source.verified).length,
)

const verifiedCount = computed(
  () => filteredSources.value.filter(s => s.source.verified).length,
)

const emptyPoolCount = computed(
  () => (poolHealth.value?.knowledge ?? []).filter(k => k.unseen_for_evaluation === 0).length,
)

const selected = computed(
  () => filteredSources.value.find(s => s.id === selectedId.value) ?? null,
)

const latestReview = computed(() => {
  const s = selected.value
  if (!s || s.reviews.length === 0) return null
  return s.reviews[s.reviews.length - 1]
})

const ledgerStages = computed<StageGroup[]>(() => [
  {
    id: 'stage-1',
    title: '第一阶段 · 立源核查',
    tabs: [
      {
        id: 'sources',
        title: '题源与来源审核',
        badge: sources.value
          ? unverifiedCount.value > 0
            ? `${unverifiedCount.value} 待审`
            : `${filteredSources.value.length} 份`
          : undefined,
        wait: unverifiedCount.value > 0,
        done: Boolean(selected.value?.source.verified),
      },
    ],
  },
  {
    id: 'stage-2',
    title: '第二阶段 · 附件录题',
    tabs: [
      {
        id: 'attachments',
        title: '附件解析与录入',
        badge: selected.value ? `${selected.value.attachments.length} 份` : undefined,
        done: Boolean(selected.value?.attachments.some(a => a.status === 'confirmed')),
      },
    ],
  },
  {
    id: 'stage-3',
    title: '第三阶段 · 审题入池',
    tabs: [
      {
        id: 'versions',
        title: '题目审核与发布',
        done: Boolean(selected.value?.attachments.some(a => a.question_version_ids.length > 0)),
      },
    ],
  },
  {
    id: 'stage-4',
    title: '第四阶段 · 余量补缺',
    tabs: [
      {
        id: 'health',
        title: '题库余量盘点',
        badge: poolHealth.value
          ? emptyPoolCount.value > 0
            ? `${emptyPoolCount.value} 缺口`
            : '充足'
          : undefined,
        wait: emptyPoolCount.value > 0,
      },
    ],
  },
])

const sourceContext = computed<StepFlowContext | null>(() => {
  if (!selected.value) return null
  return {
    eyebrow: '当前题源',
    title: selected.value.source.title,
    statusText: `${SUBJECT_LABELS[selected.value.source.subject]} · ${selected.value.source.verified ? '已人工审核' : '未审核'}`,
    statusTone: selected.value.source.verified ? 'good' : 'wait',
  }
})

const sourceSteps = computed<StepDefinition[]>(() => [
  {
    id: 'pick',
    title: '1. 选定或新建题源',
    subtitle: selected.value ? '已选定当前题源' : '先从台账选择或新建',
    badge: sources.value ? `${filteredSources.value.length} 份` : undefined,
    done: selected.value !== null,
    prereqMet: true,
  },
  {
    id: 'detail',
    title: '2. 题源概览与顺序核查',
    subtitle: '确认元数据与附件防返工提示',
    badge: selected.value ? `${selected.value.attachments.length} 附件` : undefined,
    done: Boolean(selected.value && (selected.value.attachments.length > 0 || selected.value.source.verified)),
    prereqMet: selected.value !== null,
    lockReason: '请先在第 1 步选定或登记一份题源。',
  },
  {
    id: 'review',
    title: '3. 来源人工审核',
    subtitle: selected.value?.source.verified ? '已完成人工核查' : '核查版权与适用性',
    badge: selected.value?.source.verified ? '已审核' : '待审',
    badgeTone: selected.value?.source.verified ? 'good' : 'wait',
    done: Boolean(selected.value?.source.verified),
    prereqMet: selected.value !== null,
    lockReason: '请先在第 1 步选定或登记一份题源。',
  },
])

async function selectSource(id: string) {
  selectedId.value = id
  await nextTick()
  if (typeof window !== 'undefined' && window.innerWidth < 900) {
    detailPaneRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

async function selectSourceAndAdvance(id: string, nextStep: SourceStepId = 'detail') {
  await selectSource(id)
  sourceStep.value = nextStep
}

async function refresh() {
  try {
    const list = await props.client.adminSources()
    sources.value = list
    loadError.value = ''
    const subjectList = list.filter(s => s.source.subject === props.subject)
    selectedId.value =
      selectedId.value !== null && subjectList.some(s => s.id === selectedId.value)
        ? selectedId.value
        : (subjectList[0]?.id ?? null)
    if (subjectList.length === 0) {
      sourcePickMode.value = 'create'
    }
  } catch (e) {
    loadError.value = describeError(e)
  }
}

async function loadPoolHealth() {
  poolLoading.value = true
  try {
    poolHealth.value = await props.client.poolHealth(props.subject)
  } catch {
    poolHealth.value = null
  } finally {
    poolLoading.value = false
  }
}

async function handleSourceAndPoolRefresh() {
  await Promise.all([refresh(), loadPoolHealth()])
}

function handleFillGap(knowledgeId: string) {
  prefillKnowledgeId.value = knowledgeId
  setSubTab('attachments')
  props.notify(
    `已定位待补录知识点「${getKnowledgeLabel(knowledgeId)}」，请在附件录入工作台补充题目。`,
    'info',
  )
}

function goSourceReviewStep() {
  setSubTab('sources')
  sourceStep.value = 'review'
}

watch(
  () => props.client,
  () => {
    void refresh()
    void loadPoolHealth()
  },
  { immediate: true },
)

watch(
  () => props.subject,
  () => {
    void loadPoolHealth()
  },
)

async function createSource() {
  if (newTitle.value.trim() === '') {
    formError.value = '请填写题源标题。'
    return
  }
  creating.value = true
  formError.value = ''
  try {
    const created = await props.client.addSource({
      title: newTitle.value.trim(),
      subject: props.subject,
      rightsStatus: newRights.value,
    })
    props.notify(`题源已登记（${created.id.slice(0, 8)}…）。下一步：上传附件或完成来源人工审核。`, 'success')
    newTitle.value = ''
    await refresh()
    sourcePickMode.value = 'list'
    await selectSourceAndAdvance(created.id, 'detail')
  } catch (e) {
    formError.value = describeError(e)
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <div class="admin-workspace">
    <!-- 顶部信息汇总卡（与知识点审核工作台同款紧凑摘要条） -->
    <div class="slim-tool-bar" role="region" aria-label="题库工作台总览">
      <div class="slim-tool-main">
        <div class="slim-tool-title-row">
          <h2>{{ SUBJECT_LABELS[subject] }}题库工作台</h2>
          <div class="status-badges-row status-banner" role="region" aria-label="题库状态统计">
            <span class="badge pending">待审核: {{ unverifiedCount }}</span>
            <span class="badge approved">已审题源: {{ verifiedCount }}</span>
            <span class="badge total">题源总数: {{ filteredSources.length }}</span>
            <span :class="['badge', emptyPoolCount > 0 ? 'pending' : 'clauses']">
              零余量缺口: {{ emptyPoolCount }}
            </span>
          </div>
        </div>
        <div class="sub-head">
          <span>当前科目：{{ SUBJECT_LABELS[subject] }} · 仅显示与所选科目相关的题源台账、附件解析、审题入池与余量盘点</span>
          <span
            v-if="filteredSources.length > 0 && unverifiedCount === 0 && emptyPoolCount === 0"
            class="audit-note audit-ok"
          >
            当前科目题源已全部审核，题库未见题余量充足。
          </span>
          <span v-else-if="emptyPoolCount > 0" class="audit-note">
            当前存在 {{ emptyPoolCount }} 个零余量知识点，建议在「题库余量盘点」中及时补录新题。
          </span>
          <span v-else-if="unverifiedCount > 0" class="audit-note">
            尚有 {{ unverifiedCount }} 份题源待完成来源人工审核，未审核题源不得发布题目。
          </span>
        </div>
      </div>

      <div class="slim-tool-actions">
        <HelpBubble compact title="人工审核流水线" label="流程与红线">
          <p>{{ ADMIN_PIPELINE_NOTE }}</p>
        </HelpBubble>
        <button type="button" class="ghost small" @click="handleSourceAndPoolRefresh">
          刷新
        </button>
      </div>
    </div>

    <!-- 四阶段分组子 Tab 导航 -->
    <StageTabStrip
      :groups="ledgerStages"
      :model-value="activeSubTab"
      region-label="题库四阶段工作区"
      id-prefix="ledger"
      @update:model-value="setSubTab($event as LedgerSubTab)"
    />

    <!-- 阶段 1：题源与来源审核（方式 A 严格锁步单卡） -->
    <div
      v-if="activeSubTab === 'sources'"
      id="ledger-panel-sources"
      role="tabpanel"
      aria-labelledby="ledger-tab-sources"
    >
      <StepFlowWorkspace
        v-model="sourceStep"
        :steps="sourceSteps"
        :context="sourceContext"
        steps-aria-label="题源与来源审核步骤"
      >
        <template #context-actions>
          <button
            v-if="sourceStep !== 'pick'"
            type="button"
            class="ghost small"
            @click="sourceStep = 'pick'"
          >
            切换 / 新建题源
          </button>
        </template>

        <!-- 第 1 步：选定或新建题源 -->
        <template #step-pick>
          <section class="card" aria-label="题源台账">
            <div class="card-head">
              <div>
                <h2>
                  第 1 步 · 选定或新建{{ SUBJECT_LABELS[subject] }}题源
                  <span v-if="sources" class="muted tiny">({{ filteredSources.length }})</span>
                </h2>
                <p class="card-sub">先确定本次要处理的{{ SUBJECT_LABELS[subject] }}题源档案，再推进至概览与来源人工审核。</p>
              </div>
              <div class="card-head-tools">
                <div class="mode-switch" role="group" aria-label="台账或新建切换">
                  <button
                    type="button"
                    :class="['mode-switch-btn', sourcePickMode === 'list' ? 'active' : '']"
                    @click="sourcePickMode = 'list'"
                  >
                    已有题源台账 ({{ filteredSources.length }})
                  </button>
                  <button
                    type="button"
                    :class="['mode-switch-btn', sourcePickMode === 'create' ? 'active' : '']"
                    @click="sourcePickMode = 'create'"
                  >
                    ＋ 登记新题源
                  </button>
                </div>
                <button type="button" class="ghost small" @click="refresh">
                  刷新
                </button>
              </div>
            </div>

            <template v-if="sourcePickMode === 'list'">
              <p v-if="sources === null" class="muted">
                {{ loadError === '' ? '题源加载中…' : `题源加载失败：${loadError}` }}
              </p>
              <div v-else-if="filteredSources.length === 0" class="muted">
                <p>当前科目（{{ SUBJECT_LABELS[subject] }}）下还没有题源：可点击右上角「＋ 登记新题源」。</p>
                <button type="button" class="primary small" @click="sourcePickMode = 'create'">
                  ＋ 登记新题源
                </button>
              </div>
              <ul v-else class="source-list source-list-scroll">
                <li
                  v-for="s in filteredSources"
                  :key="s.id"
                  :class="['source-item', s.id === selectedId ? 'selected' : '']"
                >
                  <button
                    type="button"
                    class="source-pick"
                    :aria-pressed="s.id === selectedId"
                    @click="selectSource(s.id)"
                  >
                    <span class="source-title">{{ s.source.title }}</span>
                    <span class="muted tiny">
                      {{ SUBJECT_LABELS[s.source.subject] }} · {{ s.attachments.length }} 个附件 · {{ s.reviews.length }} 次审核
                    </span>
                  </button>
                  <span :class="['chip', s.source.verified ? 'good' : 'wait']">
                    {{ s.source.verified ? '已人工审核' : '未审核' }}
                  </span>
                  <button
                    type="button"
                    class="ghost small"
                    @click="selectSourceAndAdvance(s.id, 'detail')"
                  >
                    查看详情 →
                  </button>
                </li>
              </ul>

              <div v-if="selected" class="card-footer-flow">
                <span class="muted tiny">已选中「{{ selected.source.title }}」</span>
                <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                  <button type="button" class="primary small" @click="sourceStep = 'detail'">
                    下一步：题源概览与顺序核查 →
                  </button>
                </div>
              </div>
            </template>

            <form v-else class="admin-form" style="border-top: none; padding-top: 4px; margin-top: 4px;" @submit.prevent="createSource">
              <div class="card-head" style="margin-bottom: 8px;">
                <span class="field-label" style="margin: 0;">登记新题源</span>
                <HelpBubble compact align="left" tone="caution" title="新建题源版权提醒" label="版权提示">
                  <p>版权状态为「版权状态未核实」的题源，即使完成人工审核也无法发布题目；请先补全授权依据或个人学习核查说明。</p>
                </HelpBubble>
              </div>
              <div class="admin-grid">
                <label>
                  题源标题
                  <input
                    v-model="newTitle"
                    placeholder="例如：2025年北京市初中学业水平考试数学试卷"
                    maxlength="256"
                  />
                </label>
                <label>
                  科目
                  <input :value="SUBJECT_LABELS[subject]" disabled />
                </label>
                <label class="wide">
                  版权状态
                  <select v-model="newRights">
                    <option
                      v-for="id in (Object.keys(RIGHTS_STATUS_LABELS) as RightsStatus[])"
                      :key="id"
                      :value="id"
                    >
                      {{ RIGHTS_STATUS_LABELS[id] }}
                    </option>
                  </select>
                </label>
              </div>
              <p v-if="formError" class="form-error">{{ formError }}</p>
              <div class="card-footer-flow">
                <button
                  v-if="filteredSources.length > 0"
                  type="button"
                  class="ghost small"
                  @click="sourcePickMode = 'list'"
                >
                  ← 返回已有题源台账
                </button>
                <button type="submit" class="primary" :disabled="creating">
                  {{ creating ? '登记中…' : '新建题源' }}
                </button>
              </div>
            </form>
          </section>
        </template>

        <!-- 第 2 步：题源概览与顺序防返工核查 -->
        <template #step-detail>
          <section v-if="selected" ref="detailPaneRef" :key="selected.id" class="card source-overview-card" aria-label="当前题源详情">
            <div class="card-head">
              <div>
                <span class="eyebrow">第 2 步 · 已选中题源详情</span>
                <h2 class="overview-title">{{ selected.source.title }}</h2>
              </div>
              <div class="overview-chips">
                <span :class="['chip', selected.source.verified ? 'good' : 'wait']">
                  {{ selected.source.verified ? '已人工审核' : '未审核' }}
                </span>
                <span class="chip">{{ SUBJECT_LABELS[selected.source.subject] }}</span>
                <span v-if="selected.source.exam_year" class="chip">{{ selected.source.exam_year }} 年</span>
              </div>
            </div>

            <div class="gate-alert-banner">
              <span>
                <b>防返工顺序提醒：</b>向已审核题源上传新附件会让题源自动复位为「未审核」。
                当前已上传附件 <b>{{ selected.attachments.length }} 份</b>
                {{ selected.attachments.length === 0 ? '——建议先前往「第二阶段 · 附件解析与录入」上传原卷，再回来完成来源人工审核。' : '——可继续完成第 3 步「来源人工审核」。' }}
              </span>
              <button
                v-if="selected.attachments.length === 0"
                type="button"
                class="ghost small"
                @click="setSubTab('attachments')"
              >
                先去上传附件 →
              </button>
            </div>

            <dl class="source-meta-grid">
              <div>
                <dt>来源分类</dt>
                <dd>{{ selected.source.source_class === 'official_exam' ? '官方历年真题原卷' : '自建/日常题源' }}</dd>
              </div>
              <div>
                <dt>版权与授权状态</dt>
                <dd>{{ RIGHTS_STATUS_LABELS[selected.source.rights_status] }}</dd>
              </div>
              <div>
                <dt>原卷完整性校验</dt>
                <dd :title="selected.source.sha256 ? `校验摘要：${selected.source.sha256}` : undefined">
                  {{ selected.source.sha256 ? '已绑定原卷校验摘要' : '未绑定原卷校验摘要' }}
                </dd>
              </div>
              <div>
                <dt>最近审核人 / 时间</dt>
                <dd>
                  <template v-if="latestReview">
                    {{ getOperatorLabel(latestReview.reviewed_by) }} · {{ shortTime(latestReview.created_at) }}
                  </template>
                  <template v-else>暂未提交人工审核</template>
                </dd>
              </div>
            </dl>

            <div v-if="latestReview" class="overview-review-box">
              <p><b>版权依据：</b>{{ latestReview.metadata.rights_basis }}</p>
              <p><b>适用性说明：</b>{{ latestReview.metadata.applicability_note }}</p>
              <p><b>来源路径/链接：</b>{{ latestReview.metadata.source_url }}（获取日期：{{ latestReview.metadata.acquired_at }}）</p>
            </div>

            <div class="overview-attachments">
              <div class="overview-subhead">关联附件快照 ({{ selected.attachments.length }} 份)</div>
              <p v-if="selected.attachments.length === 0" class="muted tiny">暂无上传附件。</p>
              <ul v-else class="overview-att-list">
                <li v-for="att in selected.attachments" :key="att.id">
                  <b>{{ att.filename }}</b>
                  <span class="chip good">{{ ATTACHMENT_STATUS_LABELS[att.status] }}</span>
                  <span class="muted tiny">{{ fmtBytes(att.byte_size) }} · 关联 {{ att.question_version_ids.length }} 题</span>
                </li>
              </ul>
            </div>

            <div class="card-footer-flow">
              <button type="button" class="ghost small" @click="sourceStep = 'pick'">
                ← 返回台账切换
              </button>
              <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                <button type="button" class="ghost small" @click="setSubTab('attachments')">
                  前往附件解析与录入
                </button>
                <button type="button" class="primary small" @click="sourceStep = 'review'">
                  下一步：来源人工审核 →
                </button>
              </div>
            </div>
          </section>
        </template>

        <!-- 第 3 步：来源人工审核 -->
        <template #step-review>
          <div v-if="selected" :key="`review-${selected.id}`">
            <SourceReviewCard
              :client="client"
              :source="selected"
              :notify="notify"
              @reviewed="refresh"
            />
            <div v-if="selected.source.verified" class="handoff-box">
              <div>
                <strong>来源人工审核已通过！</strong>
                <span>
                  {{
                    selected.attachments.some(a => a.question_version_ids.length > 0)
                      ? '该题源已有导入题目，下一步可前往「第三阶段 · 题目审核与发布」入池。'
                      : '下一步请前往「第二阶段 · 附件解析与录入」上传原卷并逐题录入。'
                  }}
                </span>
              </div>
              <button
                type="button"
                class="primary small"
                @click="setSubTab(selected.attachments.some(a => a.question_version_ids.length > 0) ? 'versions' : 'attachments')"
              >
                {{
                  selected.attachments.some(a => a.question_version_ids.length > 0)
                    ? '前往题目审核与发布 →'
                    : '前往附件解析与录入 →'
                }}
              </button>
            </div>
          </div>
        </template>
      </StepFlowWorkspace>
    </div>

    <!-- 阶段 2：附件解析与录入 -->
    <div
      v-else-if="activeSubTab === 'attachments'"
      id="ledger-panel-attachments"
      role="tabpanel"
      aria-labelledby="ledger-tab-attachments"
    >
      <div v-if="selected" class="stage-wrap">
        <div class="matrix-context-bar" style="margin-bottom: 12px;">
          <div class="matrix-context-main">
            <span class="eyebrow">当前题源</span>
            <b>{{ selected.source.title }}</b>
            <span class="chip">{{ SUBJECT_LABELS[selected.source.subject] }}</span>
            <span :class="['chip', selected.source.verified ? 'good' : 'wait']">
              {{ selected.source.verified ? '已人工审核' : '未审核' }}
            </span>
          </div>
          <div v-if="filteredSources.length > 1" class="matrix-context-actions">
            <label style="margin: 0; font-size: 0.78rem; display: flex; align-items: center; gap: 6px;">
              <span class="muted tiny">切换题源</span>
              <select
                aria-label="切换当前题源"
                :value="selectedId ?? ''"
                style="width: auto; margin: 0; padding: 5px 10px; font-size: 0.8rem;"
                @change="selectSource(($event.target as HTMLSelectElement).value)"
              >
                <option v-for="s in filteredSources" :key="s.id" :value="s.id">
                  {{ s.source.title }}（{{ SUBJECT_LABELS[s.source.subject] }}）
                </option>
              </select>
            </label>
          </div>
        </div>
        <AttachmentCard
          :key="`att-${selected.id}`"
          :client="client"
          :source="selected"
          :initial-knowledge-id="prefillKnowledgeId"
          :notify="notify"
          @changed="refresh"
          @go-versions="setSubTab('versions')"
        />
      </div>
      <section v-else class="card stage-wrap" aria-label="附件与解析">
        <h2>附件与解析（前置未就绪）</h2>
        <p class="muted">请先在「第一阶段 · 题源与来源审核」中新建或选择一份题源。</p>
        <button type="button" class="primary small" @click="setSubTab('sources')">
          返回第一阶段选题源 →
        </button>
      </section>
    </div>

    <!-- 阶段 3：题目审核与发布 -->
    <div
      v-else-if="activeSubTab === 'versions'"
      id="ledger-panel-versions"
      role="tabpanel"
      aria-labelledby="ledger-tab-versions"
    >
      <div v-if="selected" class="stage-wrap">
        <div class="matrix-context-bar" style="margin-bottom: 12px;">
          <div class="matrix-context-main">
            <span class="eyebrow">当前题源</span>
            <b>{{ selected.source.title }}</b>
            <span class="chip">{{ SUBJECT_LABELS[selected.source.subject] }}</span>
            <span :class="['chip', selected.source.verified ? 'good' : 'wait']">
              {{ selected.source.verified ? '已人工审核' : '未审核' }}
            </span>
          </div>
          <div v-if="filteredSources.length > 1" class="matrix-context-actions">
            <label style="margin: 0; font-size: 0.78rem; display: flex; align-items: center; gap: 6px;">
              <span class="muted tiny">切换题源</span>
              <select
                aria-label="切换当前题源"
                :value="selectedId ?? ''"
                style="width: auto; margin: 0; padding: 5px 10px; font-size: 0.8rem;"
                @change="selectSource(($event.target as HTMLSelectElement).value)"
              >
                <option v-for="s in filteredSources" :key="s.id" :value="s.id">
                  {{ s.source.title }}（{{ SUBJECT_LABELS[s.source.subject] }}）
                </option>
              </select>
            </label>
          </div>
        </div>
        <QuestionVersionsCard
          :key="`ver-${selected.id}`"
          :client="client"
          :source="selected"
          :notify="notify"
          @source-changed="handleSourceAndPoolRefresh"
          @go-source-review="goSourceReviewStep"
          @go-attachments="setSubTab('attachments')"
          @go-health="setSubTab('health')"
        />
      </div>
      <section v-else class="card stage-wrap" aria-label="题目草稿与发布">
        <h2>题目草稿与发布（前置未就绪）</h2>
        <p class="muted">请先在「第一阶段 · 题源与来源审核」中选择一份题源。</p>
        <button type="button" class="primary small" @click="setSubTab('sources')">
          返回第一阶段选题源 →
        </button>
      </section>
    </div>

    <!-- 阶段 4：题库余量盘点 -->
    <div
      v-else
      id="ledger-panel-health"
      role="tabpanel"
      aria-labelledby="ledger-tab-health"
    >
      <section class="card stage-wrap" aria-label="题库余量">
        <div class="card-head">
          <h2>题库余量盘点（{{ SUBJECT_LABELS[subject] }}）</h2>
          <div class="card-head-tools">
            <HelpBubble title="题库余量口径说明" label="余量口径">
              <ul>
                <li><strong>统计范围：</strong>反映当前科目各知识点的已发布题目储备量、未见题余量与已曝光消耗次。</li>
                <li><strong>未见题重要性：</strong>阶段诊断仅抽取从未曝光过的新题；若某一知识点提示「零余量」，请点击「去补录新题」及时扩充题源。</li>
                <li v-if="poolHealth?.disclaimer"><strong>口径备注：</strong>{{ poolHealth.disclaimer }}</li>
              </ul>
            </HelpBubble>
            <button type="button" class="ghost small" @click="loadPoolHealth">
              刷新
            </button>
          </div>
        </div>
        <PoolHealthCard
          v-if="poolHealth"
          :data="poolHealth"
          :hide-disclaimer="true"
          @fill-gap="handleFillGap"
        />
        <p v-else class="muted">{{ poolLoading ? '加载中…' : '题库余量加载失败。' }}</p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.source-list-scroll {
  max-height: 440px;
  overflow-y: auto;
  padding-right: 2px;
}
.source-overview-card {
  background: var(--card-warm, #fbf9f5);
  border-color: var(--primary-line, #bcd9c8);
}
.overview-title {
  margin: 2px 0 0;
  font-size: 1.08rem;
  color: var(--ink, #2c2623);
}
.overview-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.source-meta-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 14px;
  margin: 12px 0;
  padding: 10px 12px;
  background: #ffffff;
  border: 1px solid var(--line, #e7dfd2);
  border-radius: var(--radius-s, 10px);
}
.source-meta-grid dt {
  font-size: 0.75rem;
  color: var(--ink-3, #6b6056);
  margin-bottom: 2px;
}
.source-meta-grid dd {
  margin: 0;
  font-size: 0.86rem;
  font-weight: 600;
  color: var(--ink, #2c2623);
  overflow-wrap: anywhere;
}
.overview-review-box {
  background: #ffffff;
  border: 1px solid var(--line-soft, #f1ebe1);
  border-radius: var(--radius-s, 10px);
  padding: 10px 12px;
  margin-bottom: 10px;
  font-size: 0.83rem;
  line-height: 1.55;
  color: var(--ink-2, #5c5248);
}
.overview-review-box p {
  margin: 3px 0;
}
.overview-attachments {
  background: #ffffff;
  border: 1px solid var(--line-soft, #f1ebe1);
  border-radius: var(--radius-s, 10px);
  padding: 10px 12px;
}
.overview-subhead {
  font-size: 0.82rem;
  font-weight: 700;
  color: var(--ink, #2c2623);
  margin-bottom: 6px;
}
.overview-att-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}
.overview-att-list li {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-size: 0.83rem;
  padding: 6px 8px;
  border: 1px solid var(--line-soft, #f1ebe1);
  border-radius: 8px;
  background: var(--card-warm, #fbf9f5);
}
@media (max-width: 900px) {
  .source-list-scroll {
    max-height: 320px;
  }
  .source-meta-grid {
    grid-template-columns: 1fr;
  }
  .overview-att-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 640px) {
  .overview-att-list {
    grid-template-columns: 1fr;
  }
}
</style>
