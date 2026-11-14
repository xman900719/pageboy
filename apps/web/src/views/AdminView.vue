<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import {
  describeError,
  SUBJECTS,
  SUBJECT_LABELS,
  type ApiClient,
  type RightsStatus,
  type SourceDetail,
  type Subject,
} from '../api'
import { ADMIN_PIPELINE_NOTE, ATTACHMENT_STATUS_LABELS, RIGHTS_STATUS_LABELS, fmtBytes, shortTime } from '../copy'
import Note from '../components/Note.vue'
import type { NoticeTone } from '../components/Notice.vue'
import SourceReviewCard from '../components/admin/SourceReviewCard.vue'
import AttachmentCard from '../components/admin/AttachmentCard.vue'
import QuestionVersionsCard from '../components/admin/QuestionVersionsCard.vue'

type Notify = (text: string, tone?: NoticeTone) => void

const props = defineProps<{
  client: ApiClient
  subject: Subject
  notify: Notify
}>()

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

const filteredSources = computed(() => {
  if (!sources.value) return []
  if (subjectFilter.value === 'all') return sources.value
  return sources.value.filter(s => s.source.subject === subjectFilter.value)
})

const latestReview = computed(() => {
  const s = selected.value
  if (!s || s.reviews.length === 0) return null
  return s.reviews[s.reviews.length - 1]
})

async function selectSource(id: string) {
  selectedId.value = id
  await nextTick()
  // 在竖屏/窄屏堆叠布局下点击题源后自动滚动至详情区，保证点击反馈立即可见
  if (typeof window !== 'undefined' && window.innerWidth < 960) {
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

watch(
  () => props.client,
  () => {
    void refresh()
  },
  { immediate: true }
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
  <Note tone="discipline" title="人工审核流水线">
    {{ ADMIN_PIPELINE_NOTE }}
  </Note>

  <div class="admin-ledger-workbench">
    <section class="card admin-ledger-col" aria-label="题源台账">
      <div class="card-head">
        <h2>题源台账 <span v-if="sources" class="muted tiny">({{ filteredSources.length }} / {{ sources.length }})</span></h2>
        <button type="button" class="ghost small" @click="refresh">
          刷新
        </button>
      </div>
      <p class="muted">
        登记试卷 / 教辅来源，点击条目即可在右侧（或下方）查看完整详情、附件清单与题目版本。
      </p>

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
              {{ SUBJECT_LABELS[s.source.subject] }} · {{ s.attachments.length }} 个附件 · {{ s.reviews.length }} 次审核记录
            </span>
          </button>
          <span :class="['chip', s.source.verified ? 'good' : 'wait']">
            {{ s.source.verified ? '已人工审核' : '未审核' }}
          </span>
        </li>
      </ul>

      <form class="admin-form" @submit.prevent="createSource">
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
        <p class="muted tiny">
          版权状态为「未核实」的题源，即使完成人工审核也无法发布题目；请先补全授权或核查依据。
        </p>
        <p v-if="formError" class="form-error">{{ formError }}</p>
        <button type="submit" class="primary" :disabled="creating">
          {{ creating ? '登记中…' : '新建题源' }}
        </button>
      </form>
    </section>

    <div v-if="selected" :key="selected.id" ref="detailPaneRef" class="admin-detail-col">
      <!-- 选中题源完整详情概览卡 -->
      <section class="card source-overview-card" aria-label="当前题源详情">
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
            <dt>文件校验 SHA256</dt>
            <dd><code>{{ selected.source.sha256 ? `${selected.source.sha256.slice(0, 20)}…` : '未绑定原卷校验和' }}</code></dd>
          </div>
          <div>
            <dt>最近审核人 / 时间</dt>
            <dd>
              <template v-if="latestReview">
                {{ latestReview.reviewed_by }} · {{ shortTime(latestReview.created_at) }}
              </template>
              <template v-else>暂未提交人工审核</template>
            </dd>
          </div>
        </dl>

        <div v-if="latestReview" class="overview-review-box">
          <p><b>版权依据：</b>{{ latestReview.metadata.rights_basis }}</p>
          <p><b>适用性说明：</b>{{ latestReview.metadata.applicability_note }}</p>
          <p><b>来源路径/链接：</b><code>{{ latestReview.metadata.source_url }}</code>（获取日期：{{ latestReview.metadata.acquired_at }}）</p>
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
      </section>

      <SourceReviewCard
        :client="client"
        :source="selected"
        :notify="notify"
        @reviewed="refresh"
      />
      <AttachmentCard
        :client="client"
        :source="selected"
        :notify="notify"
        @changed="refresh"
      />
      <QuestionVersionsCard
        :client="client"
        :source="selected"
        :notify="notify"
        @sourceChanged="refresh"
      />
    </div>
  </div>
</template>

<style scoped>
.admin-ledger-workbench {
  display: grid;
  grid-template-columns: 400px minmax(0, 1fr);
  gap: 14px;
  align-items: start;
}
.admin-ledger-col {
  min-width: 0;
}
.admin-detail-col {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.admin-detail-col > .card {
  margin-bottom: 0;
}
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
@media (max-width: 960px) {
  .admin-ledger-workbench {
    grid-template-columns: 1fr;
  }
  .source-list-scroll {
    max-height: 320px;
  }
  .source-meta-grid {
    grid-template-columns: 1fr;
  }
}
</style>
