<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  describeError,
  SCHOOL_SUBJECTS,
  SCHOOL_SUBJECT_LABELS,
  type ApiClient,
  type SchoolErrorCategory,
  type SchoolSubject,
  type StudentSchoolReflectionItem,
  type Subject,
  type WrongQuestionSummary,
} from '../api'
import { fmtPoints } from '../copy'
import { getSchoolErrorCategoryLabel, SCHOOL_ERROR_CATEGORY_OPTIONS } from '../config/knowledge'
import {
  formatQuestionLabelHeading,
  groupSchoolReflectionsByExam,
  validateReflectionDraftLocally,
} from '../examSync'
import TutorDrawer from '../components/TutorDrawer.vue'
import type { NoticeTone } from '../components/Notice.vue'
import { RichText } from '../rich'

const props = defineProps<{
  client: ApiClient
  subject: Subject
  notify: (text: string, tone?: NoticeTone) => void
}>()

const emit = defineEmits<{
  (e: 'pendingCount', total: number): void
}>()

type ReflectionFilter = 'pending' | 'all' | 'completed'

const activeSubject = ref<SchoolSubject>(props.subject)
const filterMode = ref<ReflectionFilter>('pending')
const activeExamId = ref<string | null>(null)
const loading = ref(false)
const items = ref<StudentSchoolReflectionItem[]>([])
const pendingBySubject = ref<Record<string, number>>({})
const totalPending = ref(0)

const drafts = ref<
  Record<
    string,
    {
      errorCategory: SchoolErrorCategory | ''
      stuckPoint: string
      fixStrategy: string
      feedback: string
      submitting: boolean
    }
  >
>({})

const dailyWrongs = ref<WrongQuestionSummary[]>([])
const activeTutorItem = ref<WrongQuestionSummary | null>(null)

function countEffective(text: string): number {
  return (text.match(/[\u4e00-\u9fffA-Za-z]/g) ?? []).length
}

function initDrafts(rows: StudentSchoolReflectionItem[]) {
  const next: typeof drafts.value = {}
  for (const row of rows) {
    const prev = drafts.value[row.item_id]
    next[row.item_id] = prev ?? {
      errorCategory: row.error_category ?? '',
      stuckPoint: row.stuck_point ?? '',
      fixStrategy: row.fix_strategy ?? '',
      feedback: '',
      submitting: false,
    }
  }
  drafts.value = next
}

async function loadReflections() {
  loading.value = true
  try {
    const res = await props.client.schoolExamReflections(activeSubject.value)
    items.value = res.items
    pendingBySubject.value = res.pending_counts_by_subject
    totalPending.value = res.total_pending
    emit('pendingCount', res.total_pending)
    initDrafts(res.items)
  } catch (e) {
    props.notify(`加载校考错题复盘失败：${describeError(e)}`, 'error')
  } finally {
    loading.value = false
  }

  if (activeSubject.value !== 'ethics') {
    try {
      dailyWrongs.value = await props.client.wrongAttempts(activeSubject.value as Subject, 6)
    } catch {
      dailyWrongs.value = []
    }
  } else {
    dailyWrongs.value = []
  }
}

const examGroups = computed(() => groupSchoolReflectionsByExam(items.value))

const activeExamGroup = computed(() =>
  activeExamId.value ? examGroups.value.find(g => g.examId === activeExamId.value) ?? null : null,
)

const activeExamCounts = computed(() => {
  const list = activeExamGroup.value?.items ?? []
  let pending = 0
  let completed = 0
  for (const it of list) {
    if (it.reflection_status === 'completed') completed += 1
    else pending += 1
  }
  return { all: list.length, pending, completed }
})

const activeExamFilteredItems = computed(() => {
  const list = activeExamGroup.value?.items ?? []
  if (filterMode.value === 'pending') {
    return list.filter(it => it.reflection_status === 'pending' || it.reflection_status === 'needs_revision')
  }
  if (filterMode.value === 'completed') {
    return list.filter(it => it.reflection_status === 'completed')
  }
  return list
})

function enterExam(examId: string) {
  activeExamId.value = examId
  const group = examGroups.value.find(g => g.examId === examId)
  filterMode.value = group && group.pendingCount > 0 ? 'pending' : 'all'
}

async function submitReflection(item: StudentSchoolReflectionItem) {
  const d = drafts.value[item.item_id]
  if (!d || d.submitting) return
  if (!d.errorCategory) {
    d.feedback = '请先选择本题对应的错因分类。'
    return
  }
  const localErr = validateReflectionDraftLocally(d.stuckPoint, d.fixStrategy)
  if (localErr) {
    d.feedback = localErr
    return
  }
  d.submitting = true
  d.feedback = ''
  try {
    const updated = await props.client.submitSchoolExamReflection(item.item_id, {
      errorCategory: d.errorCategory,
      stuckPoint: d.stuckPoint.trim(),
      fixStrategy: d.fixStrategy.trim(),
    })
    d.stuckPoint = updated.stuck_point
    d.fixStrategy = updated.fix_strategy
    d.errorCategory = updated.error_category ?? ''
    d.feedback = ''
    props.notify(`「${formatQuestionLabelHeading(item.question_label)}」已完成高质量复盘。`, 'success')
    await loadReflections()
  } catch (e) {
    const msg = describeError(e)
    d.feedback = msg
      .replace(/^REFLECTION_TOO_PERFUNCTORY:\s*/i, '')
      .replace(/^REFLECTION_AI_COACH_REJECTED:\s*/i, 'AI 审阅追问：')
  } finally {
    d.submitting = false
  }
}

watch(
  () => props.subject,
  sub => {
    activeSubject.value = sub
  },
)

watch(
  [() => props.client, () => activeSubject.value],
  () => {
    activeTutorItem.value = null
    activeExamId.value = null
    void loadReflections()
  },
  { immediate: true },
)
</script>

<template>
  <div class="view-stack">
    <section class="card" aria-label="校考错题复盘工作台">
      <div class="card-head">
        <div>
          <h2>校考错题复盘</h2>
        </div>
        <div class="head-actions">
          <span v-if="totalPending > 0" class="chip wait">全科待复盘 {{ totalPending }} 题</span>
          <span v-else class="chip good">全科失分已复盘 ✓</span>
          <button type="button" class="ghost small" :disabled="loading" @click="loadReflections">
            {{ loading ? '刷新中…' : '刷新列表' }}
          </button>
        </div>
      </div>

      <div class="reflection-subject-row" role="group" aria-label="选择复盘学科">
        <button
          v-for="sub in SCHOOL_SUBJECTS"
          :key="sub"
          type="button"
          :class="['chip-btn', activeSubject === sub ? 'selected' : '']"
          @click="activeSubject = sub"
        >
          <span>{{ SCHOOL_SUBJECT_LABELS[sub] }}</span>
          <span v-if="(pendingBySubject[sub] ?? 0) > 0" class="nav-count-badge">
            {{ pendingBySubject[sub] }}
          </span>
        </button>
      </div>

      <!-- 第一屏：校考台账目录（绝不把多场题目平铺在同一页） -->
      <template v-if="!activeExamGroup">
        <p v-if="!loading && examGroups.length === 0" class="muted" style="margin-top: 12px;">
          {{ SCHOOL_SUBJECT_LABELS[activeSubject] }}暂无需要复盘的校考失分记录。
        </p>

        <div v-else class="reflection-exam-catalog" aria-label="校考台账目录">
          <article
            v-for="eg in examGroups"
            :key="eg.examId"
            :class="['reflection-exam-tile', eg.pendingCount > 0 ? 'has-pending' : 'is-done']"
          >
            <div class="reflection-exam-tile-head">
              <b>{{ eg.examTitle }}</b>
              <span class="muted tiny">{{ eg.examDate }}</span>
            </div>
            <div class="reflection-exam-tile-stats">
              <span v-if="eg.pendingCount > 0" class="chip wait">
                待复盘 {{ eg.pendingCount }} 题
              </span>
              <span v-else class="chip good">本场已全部复盘 ✓</span>
              <span v-if="eg.needsRevisionCount > 0" class="chip bad">
                退回重写 {{ eg.needsRevisionCount }}
              </span>
              <span v-if="eg.completedCount > 0" class="chip subtle">
                已完成 {{ eg.completedCount }} 题
              </span>
            </div>
            <div class="reflection-exam-tile-foot">
              <button
                type="button"
                :class="eg.pendingCount > 0 ? 'primary small' : 'ghost small'"
                @click="enterExam(eg.examId)"
              >
                {{ eg.pendingCount > 0 ? '进入本场复盘 →' : '查看 / 修改' }}
              </button>
            </div>
          </article>
        </div>
      </template>

      <!-- 第二屏：单场错题复盘专注页 -->
      <template v-else>
        <div class="reflection-breadcrumb">
          <button type="button" class="ghost small" @click="activeExamId = null">
            ← 返回校考台账
          </button>
          <div class="reflection-exam-meta">
            <b>{{ activeExamGroup.examTitle }}</b>
            <span class="muted tiny">{{ activeExamGroup.examDate }}</span>
            <span v-if="activeExamGroup.pendingCount > 0" class="chip wait">
              待复盘 {{ activeExamGroup.pendingCount }} 题
            </span>
            <span v-else class="chip good">本场已全部复盘 ✓</span>
          </div>
        </div>

        <div class="draft-toolbar">
          <div class="draft-filter-pills" role="group" aria-label="筛选复盘状态">
            <button
              type="button"
              :class="['chip-btn', filterMode === 'pending' ? 'selected' : '']"
              @click="filterMode = 'pending'"
            >
              待复盘 / 退回 ({{ activeExamCounts.pending }})
            </button>
            <button
              type="button"
              :class="['chip-btn', filterMode === 'completed' ? 'selected' : '']"
              @click="filterMode = 'completed'"
            >
              已完成 ({{ activeExamCounts.completed }})
            </button>
            <button
              type="button"
              :class="['chip-btn', filterMode === 'all' ? 'selected' : '']"
              @click="filterMode = 'all'"
            >
              全部失分题 ({{ activeExamCounts.all }})
            </button>
          </div>
        </div>

        <p v-if="activeExamFilteredItems.length === 0" class="muted" style="margin-top: 12px;">
          {{
            filterMode === 'pending'
              ? '本场错题已全部完成复盘，可切换「已完成」查看或返回校考台账。'
              : '当前筛选下暂无错题记录。'
          }}
        </p>

        <ul v-else class="reflection-card-list" aria-label="校考待复盘错题列表">
          <li
            v-for="it in activeExamFilteredItems"
            :key="it.item_id"
            :class="['reflection-card', `status-${it.reflection_status}`]"
          >
            <div class="reflection-card-head">
              <div class="reflection-title-group">
                <b>{{ formatQuestionLabelHeading(it.question_label) }}</b>
                <span class="chip">{{ it.topic }}</span>
                <span class="chip bad">
                  实得 {{ fmtPoints(it.earned_points) }} / {{ fmtPoints(it.max_points) }}（失 {{ fmtPoints(it.lost_points) }} 分）
                </span>
              </div>
              <span
                :class="[
                  'chip',
                  it.reflection_status === 'completed'
                    ? 'good'
                    : it.reflection_status === 'needs_revision'
                      ? 'bad'
                      : 'wait',
                ]"
              >
                {{
                  it.reflection_status === 'completed'
                    ? '已完成复盘 ✓'
                    : it.reflection_status === 'needs_revision'
                      ? '家长退回重写'
                      : '待复盘'
                }}
              </span>
            </div>

            <p v-if="it.return_reason" class="reflection-return-banner" role="alert">
              退回重写原因：{{ it.return_reason }}
            </p>

            <p v-if="it.stem_excerpt" class="reflection-stem-excerpt">
              原卷题干摘要：{{ it.stem_excerpt }}
            </p>

            <div v-if="drafts[it.item_id]" class="reflection-form">
              <div class="reflection-cat-group">
                <span class="reflection-label">1. 选择错因分类（必选）</span>
                <div class="reflection-cat-pills" role="group" :aria-label="`${formatQuestionLabelHeading(it.question_label)} 错因分类`">
                  <button
                    v-for="opt in SCHOOL_ERROR_CATEGORY_OPTIONS"
                    :key="opt.value"
                    type="button"
                    :class="['chip-btn', drafts[it.item_id].errorCategory === opt.value ? 'selected' : '']"
                    @click="drafts[it.item_id].errorCategory = opt.value; drafts[it.item_id].feedback = ''"
                  >
                    {{ opt.label }}
                  </button>
                </div>
              </div>

              <label class="reflection-field">
                <div class="reflection-field-head">
                  <span>2. 具体失分卡点（有效字数 {{ countEffective(drafts[it.item_id].stuckPoint) }} / 建议 ≥ 8）</span>
                </div>
                <textarea
                  v-model="drafts[it.item_id].stuckPoint"
                  rows="2"
                  maxlength="300"
                  :aria-label="`${formatQuestionLabelHeading(it.question_label)} 具体失分卡点`"
                  placeholder="写明具体错在第几步、漏掉了哪个题干条件或哪条公式用反了…"
                  @input="drafts[it.item_id].feedback = ''"
                />
              </label>

              <label class="reflection-field">
                <div class="reflection-field-head">
                  <span>3. 正确思路与改进对策（有效字数 {{ countEffective(drafts[it.item_id].fixStrategy) }} / 建议 ≥ 8）</span>
                </div>
                <textarea
                  v-model="drafts[it.item_id].fixStrategy"
                  rows="2"
                  maxlength="300"
                  :aria-label="`${formatQuestionLabelHeading(it.question_label)} 改进对策`"
                  placeholder="写明本题正确关键步骤，以及下次遇到同类题的具体检查动作…"
                  @input="drafts[it.item_id].feedback = ''"
                />
              </label>

              <p v-if="drafts[it.item_id].feedback" class="reflection-reject-alert" role="alert">
                {{ drafts[it.item_id].feedback }}
              </p>

              <div class="reflection-actions">
                <span v-if="it.error_category && it.reflection_status === 'completed'" class="muted tiny">
                  当前归类：{{ getSchoolErrorCategoryLabel(it.error_category) }}
                </span>
                <button
                  type="button"
                  class="primary small"
                  :disabled="drafts[it.item_id].submitting"
                  @click="submitReflection(it)"
                >
                  {{
                    drafts[it.item_id].submitting
                      ? '提交检查中…'
                      : it.reflection_status === 'completed'
                        ? '更新复盘内容'
                        : '提交复盘'
                  }}
                </button>
              </div>
            </div>
          </li>
        </ul>
      </template>
    </section>

    <section
      v-if="activeSubject !== 'ethics' && dailyWrongs.length > 0"
      class="card"
      aria-label="近期日常练习错题引导"
    >
      <div class="card-head">
        <div>
          <h3>{{ SCHOOL_SUBJECT_LABELS[activeSubject] }}日常练习错题引导</h3>
          <p class="card-sub">同步回顾日常智能练习中的错题，随时开启苏格拉底式 AI 引导。</p>
        </div>
      </div>
      <div class="wrong-review-layout">
        <div class="wrong-list-col">
          <ul class="wrong-list">
            <li
              v-for="w in dailyWrongs"
              :key="w.attempt_id"
              :class="['wrong-item-card', activeTutorItem?.attempt_id === w.attempt_id ? 'active' : '']"
            >
              <div class="wrong-meta">
                <span class="chip bad">作答：{{ w.student_answer }}</span>
                <span class="muted">{{ fmtPoints(w.earned_points ?? 0) }} / {{ fmtPoints(w.max_points) }}</span>
              </div>
              <p class="wrong-stem"><RichText :text="w.stem" /></p>
              <div class="wrong-foot">
                <span v-for="t in w.knowledge_titles" :key="t" class="chip">{{ t }}</span>
                <button type="button" class="ghost small" @click="activeTutorItem = w">
                  {{ w.tutor_session_id ? '继续 AI 引导' : 'AI 引导讲解' }}
                </button>
              </div>
            </li>
          </ul>
        </div>
        <div v-if="activeTutorItem" class="tutor-col">
          <TutorDrawer :client="client" :wrong-item="activeTutorItem" @close="activeTutorItem = null" />
        </div>
      </div>
    </section>
  </div>
</template>
