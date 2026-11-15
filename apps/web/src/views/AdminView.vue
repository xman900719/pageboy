<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import {
  describeError,
  SUBJECTS,
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
import SourceReviewCard from '../components/admin/SourceReviewCard.vue'
import AttachmentCard from '../components/admin/AttachmentCard.vue'
import QuestionVersionsCard from '../components/admin/QuestionVersionsCard.vue'

type Notify = (text: string, tone?: NoticeTone) => void
export type LedgerSubTab = 'sources' | 'attachments' | 'versions' | 'health'

const props = withDefaults(
  defineProps<{
    client: ApiClient
    subject: Subject
    notify: Notify
    subTab?: LedgerSubTab
  }>(),
  {
    subTab: 'sources',
  }
)

const emit = defineEmits<{
  (e: 'update:subTab', next: LedgerSubTab): void
}>()

const activeSubTab = ref<LedgerSubTab>(props.subTab)
watch(
  () => props.subTab,
  next => {
    if (next) activeSubTab.value = next
  }
)

function setSubTab(next: LedgerSubTab) {
  activeSubTab.value = next
  emit('update:subTab', next)
}

const sources = ref<SourceDetail[] | null>(null)
const loadError = ref('')
const selectedId = ref<string | null>(null)
const subjectFilter = ref<'all' | Subject>('all')
const detailPaneRef = ref<HTMLElement | null>(null)
const newTitle = ref('')
const newSubject = ref<Subject>(props.subject)
const newRights = ref<RightsStatus>('unknown')
const creating = ref(false)
const formError = ref('')
const prefillKnowledgeId = ref<string | undefined>(undefined)

const poolHealth = ref<PoolHealth | null>(null)
const poolLoading = ref(false)

const filteredSources = computed(() => {
  if (!sources.value) return []
  if (subjectFilter.value === 'all') return sources.value
  return sources.value.filter(s => s.source.subject === subjectFilter.value)
})

const unverifiedCount = computed(
  () => (sources.value ?? []).filter(s => !s.source.verified).length
)

const emptyPoolCount = computed(
  () => (poolHealth.value?.knowledge ?? []).filter(k => k.unseen_for_evaluation === 0).length
)

const latestReview = computed(() => {
  const s = selected.value
  if (!s || s.reviews.length === 0) return null
  return s.reviews[s.reviews.length - 1]
})

async function selectSource(id: string) {
  selectedId.value = id
  await nextTick()
  // 在竖屏/窄屏堆叠布局下点击题源后自动滚动至详情区，保证点击反馈立即可见
  if (typeof window !== 'undefined' && window.innerWidth < 900) {
    detailPaneRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

async function refresh() {
  try {
    const list = await props.client.adminSources()
    sources.value = list
    loadError.value = ''
    selectedId.value =
      selectedId.value !== null && list.some(s => s.id === selectedId.value)
        ? selectedId.value
        : (list[0]?.id ?? null)
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
    'info'
  )
}

watch(
  () => props.client,
  () => {
    void refresh()
    void loadPoolHealth()
  },
  { immediate: true }
)

watch(
  () => props.subject,
  nextSubj => {
    newSubject.value = nextSubj
    void loadPoolHealth()
  }
)

const selected = computed(
  () => sources.value?.find(s => s.id === selectedId.value) ?? null
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
      subject: newSubject.value,
      rightsStatus: newRights.value,
    })
    props.notify(`题源已登记（${created.id.slice(0, 8)}…）。下一步：上传附件并完成来源人工审核。`, 'success')
    newTitle.value = ''
    await refresh()
    subjectFilter.value = 'all'
    await selectSource(created.id)
  } catch (e) {
    formError.value = describeError(e)
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <div class="admin-workspace">
    <!-- 二级工作区子 Tab 条（方案二：矩阵协同） -->
    <div class="admin-subtab-strip">
      <div class="admin-subtab-list" role="tablist" aria-label="题库与体检工作区">
        <button
          id="ledger-tab-sources"
          type="button"
          role="tab"
          :aria-selected="activeSubTab === 'sources'"
          aria-controls="ledger-panel-sources"
          :class="['admin-subtab', activeSubTab === 'sources' ? 'active' : '']"
          @click="setSubTab('sources')"
        >
          <span>题源与来源审核</span>
          <span v-if="sources" :class="['admin-subtab-badge', unverifiedCount > 0 ? 'wait' : '']">
            {{ unverifiedCount > 0 ? `${unverifiedCount} 待审` : `${sources.length} 份` }}
          </span>
        </button>

        <button
          id="ledger-tab-attachments"
          type="button"
          role="tab"
          :aria-selected="activeSubTab === 'attachments'"
          aria-controls="ledger-panel-attachments"
          :class="['admin-subtab', activeSubTab === 'attachments' ? 'active' : '']"
          @click="setSubTab('attachments')"
        >
          <span>附件解析与录入</span>
          <span v-if="selected" class="admin-subtab-badge">
            {{ selected.attachments.length }} 份
          </span>
        </button>

        <button
          id="ledger-tab-versions"
          type="button"
          role="tab"
          :aria-selected="activeSubTab === 'versions'"
          aria-controls="ledger-panel-versions"
          :class="['admin-subtab', activeSubTab === 'versions' ? 'active' : '']"
          @click="setSubTab('versions')"
        >
          <span>题目审核与发布</span>
        </button>

        <button
          id="ledger-tab-health"
          type="button"
          role="tab"
          :aria-selected="activeSubTab === 'health'"
          aria-controls="ledger-panel-health"
          :class="['admin-subtab', activeSubTab === 'health' ? 'active' : '']"
          @click="setSubTab('health')"
        >
          <span>题库余量体检</span>
          <span v-if="poolHealth" :class="['admin-subtab-badge', emptyPoolCount > 0 ? 'wait' : '']">
            {{ emptyPoolCount > 0 ? `${emptyPoolCount} 缺口` : '充足' }}
          </span>
        </button>
      </div>

      <div class="admin-subtab-tools">
        <HelpBubble title="人工审核流水线" label="流程与红线">
          <p>{{ ADMIN_PIPELINE_NOTE }}</p>
        </HelpBubble>
      </div>
    </div>

    <!-- 协同上下文状态条（附件解析/题目发布子 Tab 显示当前选中题源） -->
    <div
      v-if="selected && (activeSubTab === 'attachments' || activeSubTab === 'versions')"
      class="matrix-context-bar"
    >
      <div class="matrix-context-main">
        <span class="eyebrow">当前题源</span>
        <b>{{ selected.source.title }}</b>
        <span class="chip">{{ SUBJECT_LABELS[selected.source.subject] }}</span>
        <span :class="['chip', selected.source.verified ? 'good' : 'wait']">
          {{ selected.source.verified ? '已人工审核' : '未审核' }}
        </span>
      </div>
      <div v-if="sources && sources.length > 1" class="matrix-context-actions">
        <label style="margin: 0; font-size: 0.78rem; display: flex; align-items: center; gap: 6px;">
          <span class="muted tiny">切换题源</span>
          <select
            aria-label="切换当前题源"
            :value="selectedId ?? ''"
            style="width: auto; margin: 0; padding: 5px 10px; font-size: 0.8rem;"
            @change="selectSource(($event.target as HTMLSelectElement).value)"
          >
            <option v-for="s in sources" :key="s.id" :value="s.id">
              {{ s.source.title }}（{{ SUBJECT_LABELS[s.source.subject] }}）
            </option>
          </select>
        </label>
      </div>
    </div>

    <!-- 子 Tab 1：题源与来源审核（3 列协同矩阵：台账列表与建档 | 选中题源详情 | 来源人工审核） -->
    <div
      v-if="activeSubTab === 'sources'"
      id="ledger-panel-sources"
      role="tabpanel"
      aria-labelledby="ledger-tab-sources"
      class="matrix-3col"
    >
      <section class="card" aria-label="题源台账">
        <div class="card-head">
          <h2>题源台账 <span v-if="sources" class="muted tiny">({{ filteredSources.length }} / {{ sources.length }})</span></h2>
          <button type="button" class="ghost small" @click="refresh">
            刷新
          </button>
        </div>

        <div v-if="sources && sources.length > 0" class="ledger-filter-row" role="group" aria-label="按学科筛选题源">
          <button
            type="button"
            :class="subjectFilter === 'all' ? 'chip-btn selected' : 'chip-btn'"
            @click="subjectFilter = 'all'"
          >
            全部 ({{ sources.length }})
          </button>
          <button
            v-for="id in SUBJECTS"
            :key="id"
            type="button"
            :class="subjectFilter === id ? 'chip-btn selected' : 'chip-btn'"
            @click="subjectFilter = id"
          >
            {{ SUBJECT_LABELS[id] }} ({{ sources.filter(s => s.source.subject === id).length }})
          </button>
        </div>

        <p v-if="sources === null" class="muted">
          {{ loadError === '' ? '题源加载中…' : `题源加载失败：${loadError}` }}
        </p>
        <p v-else-if="filteredSources.length === 0" class="muted">
          当前筛选条件下还没有题源：可切换筛选或使用下方表单登记新题源。
        </p>
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
          </li>
        </ul>

        <form class="admin-form" @submit.prevent="createSource">
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
              <select v-model="newSubject">
                <option v-for="id in SUBJECTS" :key="id" :value="id">
                  {{ SUBJECT_LABELS[id] }}
                </option>
              </select>
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
          <button type="submit" class="primary" :disabled="creating">
            {{ creating ? '登记中…' : '新建题源' }}
          </button>
        </form>
      </section>

      <div ref="detailPaneRef" class="matrix-col-stack">
        <section v-if="selected" :key="selected.id" class="card source-overview-card" aria-label="当前题源详情">
          <div class="card-head">
            <div>
              <span class="eyebrow">已选中题源详情</span>
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

          <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px;">
            <button type="button" class="ghost small" @click="setSubTab('attachments')">
              前往附件解析与录入
            </button>
            <button type="button" class="ghost small" @click="setSubTab('versions')">
              查看题目审核与发布
            </button>
          </div>
        </section>

        <section v-else class="card" aria-label="当前题源详情">
          <h2>当前题源详情</h2>
          <p class="muted">请在左侧选择或新建一份题源，即可查看详情并发起人工审核。</p>
        </section>
      </div>

      <div v-if="selected" :key="`review-${selected.id}`" class="matrix-col-stack">
        <SourceReviewCard
          :client="client"
          :source="selected"
          :notify="notify"
          @reviewed="refresh"
        />
      </div>
      <section v-else class="card" aria-label="来源人工审核">
        <h2>来源人工审核</h2>
        <p class="muted">先选择或登记一份题源后，在此完成来源、版权与适用性人工核查。</p>
      </section>
    </div>

    <!-- 子 Tab 2：附件解析与录入（2 列协同矩阵） -->
    <div
      v-else-if="activeSubTab === 'attachments'"
      id="ledger-panel-attachments"
      role="tabpanel"
      aria-labelledby="ledger-tab-attachments"
    >
      <AttachmentCard
        v-if="selected"
        :key="`att-${selected.id}`"
        :client="client"
        :source="selected"
        :initial-knowledge-id="prefillKnowledgeId"
        :notify="notify"
        @changed="refresh"
        @go-versions="setSubTab('versions')"
      />
      <section v-else class="card" aria-label="附件与解析">
        <h2>附件与解析</h2>
        <p class="muted">请先在「题源与来源审核」中新建或选择一份题源。</p>
        <button type="button" class="primary small" @click="setSubTab('sources')">
          返回题源台账
        </button>
      </section>
    </div>

    <!-- 子 Tab 3：题目审核与发布（双栏协同列表） -->
    <div
      v-else-if="activeSubTab === 'versions'"
      id="ledger-panel-versions"
      role="tabpanel"
      aria-labelledby="ledger-tab-versions"
    >
      <QuestionVersionsCard
        v-if="selected"
        :key="`ver-${selected.id}`"
        :client="client"
        :source="selected"
        :notify="notify"
        @source-changed="handleSourceAndPoolRefresh"
      />
      <section v-else class="card" aria-label="题目草稿与发布">
        <h2>题目草稿与发布</h2>
        <p class="muted">请先在「题源与来源审核」中选择一份题源。</p>
        <button type="button" class="primary small" @click="setSubTab('sources')">
          返回题源台账
        </button>
      </section>
    </div>

    <!-- 子 Tab 4：题库余量体检（全宽诊断大屏 + 缺口跳转） -->
    <div
      v-else
      id="ledger-panel-health"
      role="tabpanel"
      aria-labelledby="ledger-tab-health"
    >
      <section class="card" aria-label="题库体检">
        <div class="card-head">
          <h2>题库余量体检（{{ SUBJECT_LABELS[subject] }}）</h2>
          <div class="card-head-tools">
            <HelpBubble title="题库体检口径说明" label="体检口径">
              <ul>
                <li><strong>体检范围：</strong>反映当前科目各知识点的已发布题目储备量、未见题余量与已曝光消耗次。</li>
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
        <p v-else class="muted">{{ poolLoading ? '加载中…' : '题库体检加载失败。' }}</p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.ledger-filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 10px 0 4px;
}
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
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.overview-att-list li {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 0.83rem;
}
@media (max-width: 900px) {
  .source-list-scroll {
    max-height: 320px;
  }
  .source-meta-grid {
    grid-template-columns: 1fr;
  }
}
</style>
