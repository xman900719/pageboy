<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  describeError,
  SCHOOL_SUBJECTS,
  SCHOOL_SUBJECT_LABELS,
  type ApiClient,
  type SchoolCoachDraft,
  type SchoolErrorCategory,
  type SchoolSubject,
  type StudentSchoolReflectionItem,
  type Subject,
} from '../api'
import { fmtPoints } from '../copy'
import { RichText } from '../rich'
import ReflectionCoachPanel from '../components/ReflectionCoachPanel.vue'
import { getSchoolErrorCategoryLabel } from '../config/knowledge'
import {
  FIX_STARTERS,
  getOrderedCategoriesForScene,
  getStuckStarters,
  REFLECTION_SCENE_OPTIONS,
  type ReflectionScene,
} from '../config/reflectionGuide'
import {
  formatQuestionLabelHeading,
  groupSchoolReflectionsByExam,
  validateReflectionDraftLocally,
} from '../examSync'
import type { NoticeTone } from '../components/Notice.vue'

const props = defineProps<{
  client: ApiClient
  subject: Subject
  notify: (text: string, tone?: NoticeTone) => void
}>()

const emit = defineEmits<{
  (e: 'pendingCount', total: number): void
}>()

type ReflectionFilter = 'pending' | 'all' | 'completed'
type GuideStep = 1 | 2 | 3

interface ReflectionDraft {
  mode: 'guide' | 'coach'
  step: GuideStep
  scene: ReflectionScene | ''
  errorCategory: SchoolErrorCategory | ''
  stuckPoint: string
  fixStrategy: string
  coachDraftHint: string
  feedback: string
  submitting: boolean
  editingCompleted: boolean
}

const activeSubject = ref<SchoolSubject>(props.subject)
const filterMode = ref<ReflectionFilter>('pending')
const activeExamId = ref<string | null>(null)
const activeItemId = ref<string | null>(null)
const loading = ref(false)
const items = ref<StudentSchoolReflectionItem[]>([])
const pendingBySubject = ref<Record<string, number>>({})
const totalPending = ref(0)
const drafts = ref<Record<string, ReflectionDraft>>({})

function createInitialDraft(row: StudentSchoolReflectionItem): ReflectionDraft {
  const initialStep: GuideStep =
    row.reflection_status === 'completed'
      ? 3
      : row.reflection_status === 'needs_revision'
        ? 2
        : 1
  return {
    mode: 'guide',
    step: initialStep,
    scene: '',
    errorCategory: row.error_category ?? '',
    stuckPoint: row.stuck_point ?? '',
    fixStrategy: row.fix_strategy ?? '',
    coachDraftHint: '',
    feedback: '',
    submitting: false,
    editingCompleted: false,
  }
}

function initDrafts(rows: StudentSchoolReflectionItem[]) {
  const next: Record<string, ReflectionDraft> = {}
  for (const row of rows) {
    const prev = drafts.value[row.item_id]
    if (prev && row.reflection_status !== 'completed') {
      next[row.item_id] = prev
    } else if (prev && row.reflection_status === 'completed' && prev.editingCompleted) {
      next[row.item_id] = prev
    } else {
      next[row.item_id] = createInitialDraft(row)
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
    props.notify(`加载校考复盘失败：${describeError(e)}`, 'error')
  } finally {
    loading.value = false
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

const activeReflectionItem = computed(() => {
  const list = activeExamFilteredItems.value
  if (list.length === 0) return null
  return list.find(it => it.item_id === activeItemId.value) ?? list[0]
})

watch(
  activeExamFilteredItems,
  list => {
    if (list.length === 0) {
      activeItemId.value = null
    } else if (!list.some(it => it.item_id === activeItemId.value)) {
      activeItemId.value = list[0].item_id
    }
  },
  { immediate: true },
)

function enterExam(examId: string) {
  activeExamId.value = examId
  const group = examGroups.value.find(g => g.examId === examId)
  filterMode.value = group && group.pendingCount > 0 ? 'pending' : 'all'
  activeItemId.value = null
}

function chooseScene(itemId: string, scene: ReflectionScene) {
  const d = drafts.value[itemId]
  if (!d) return
  d.scene = scene
  d.feedback = ''
  d.step = 2
}

function appendStarter(target: 'stuckPoint' | 'fixStrategy', itemId: string, starter: string) {
  const d = drafts.value[itemId]
  if (!d) return
  const current = d[target].trim()
  d[target] = current ? `${current}\n${starter}` : starter
  d.feedback = ''
}

function goStep(itemId: string, nextStep: GuideStep) {
  const d = drafts.value[itemId]
  if (!d) return
  if (nextStep === 3 && !d.errorCategory) {
    d.feedback = '先选一下这题更像哪一类卡点，再写给下次的提醒。'
    d.step = 2
    return
  }
  d.feedback = ''
  d.step = nextStep
}

function applyCoachDraft(itemId: string, draft: SchoolCoachDraft) {
  const d = drafts.value[itemId]
  if (!d) return
  if (draft.error_category) d.errorCategory = draft.error_category
  if (draft.stuck_point) d.stuckPoint = draft.stuck_point
  if (draft.fix_strategy) d.fixStrategy = draft.fix_strategy
  d.mode = 'guide'
  d.step = d.errorCategory && d.stuckPoint ? 3 : 2
  d.feedback = ''
  d.coachDraftHint = '书童按你刚才聊的内容起草了草稿，看看要不要改一改，再点「收好提醒卡 ✓」吧！'
}

function updateCoachTurnCount(itemId: string, count: number) {
  const target = items.value.find(it => it.item_id === itemId)
  if (target) target.coach_turn_count = count
}

async function submitReflection(item: StudentSchoolReflectionItem) {
  const d = drafts.value[item.item_id]
  if (!d || d.submitting) return
  if (!d.errorCategory) {
    d.step = 2
    d.feedback = '先选一下这题更像哪一类卡点吧。'
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
    d.editingCompleted = false
    d.feedback = ''
    props.notify(`「${formatQuestionLabelHeading(item.question_label)}」的提醒卡已收好 ✓`, 'success')
    await loadReflections()
  } catch (e) {
    const msg = describeError(e)
    d.feedback = msg
      .replace(/^REFLECTION_TOO_PERFUNCTORY:\s*/i, '')
      .replace(/^REFLECTION_AI_COACH_REJECTED:\s*/i, '书童想再追问一句：')
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
    activeExamId.value = null
    void loadReflections()
  },
  { immediate: true },
)
</script>

<template>
  <div class="view-stack">
    <section class="card" aria-label="校考复盘工作台">
      <div class="card-head">
        <div>
          <h2>校考复盘</h2>
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
              <span v-if="eg.needsRevisionCount > 0" class="chip wait">
                待再聊聊 {{ eg.needsRevisionCount }}
              </span>
              <span v-if="eg.completedCount > 0" class="chip subtle">
                已收好提醒卡 {{ eg.completedCount }} 题
              </span>
            </div>
            <div class="reflection-exam-tile-foot">
              <button
                type="button"
                :class="eg.pendingCount > 0 ? 'primary small' : 'ghost small'"
                @click="enterExam(eg.examId)"
              >
                {{ eg.pendingCount > 0 ? '进入本场复盘 →' : '查看提醒卡' }}
              </button>
            </div>
          </article>
        </div>
      </template>

      <!-- 第二屏：单场校考复盘专注页 -->
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
              待复盘 ({{ activeExamCounts.pending }})
            </button>
            <button
              type="button"
              :class="['chip-btn', filterMode === 'completed' ? 'selected' : '']"
              @click="filterMode = 'completed'"
            >
              已收好提醒卡 ({{ activeExamCounts.completed }})
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
              ? '本场错题都收好提醒卡了，可以切换「已收好提醒卡」回看或返回校考台账。'
              : '当前筛选下暂无失分记录。'
          }}
        </p>

        <template v-else-if="activeReflectionItem">
          <div class="reflection-item-tabs" role="tablist" aria-label="错题切换">
            <button
              v-for="tabItem in activeExamFilteredItems"
              :key="tabItem.item_id"
              type="button"
              role="tab"
              :aria-selected="activeReflectionItem.item_id === tabItem.item_id"
              :class="['reflection-item-tab', activeReflectionItem.item_id === tabItem.item_id ? 'active' : '']"
              @click="activeItemId = tabItem.item_id"
            >
              <span>{{ formatQuestionLabelHeading(tabItem.question_label) }}</span>
              <span
                :class="[
                  'reflection-tab-dot',
                  tabItem.reflection_status === 'completed'
                    ? 'is-done'
                    : tabItem.reflection_status === 'needs_revision'
                      ? 'is-chat'
                      : 'is-wait',
                ]"
                aria-hidden="true"
              />
            </button>
          </div>

          <ul class="reflection-card-list" aria-label="校考待复盘错题列表">
            <li
              v-for="it in [activeReflectionItem]"
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
                  it.reflection_status === 'completed' ? 'good' : 'wait',
                ]"
              >
                {{
                  it.reflection_status === 'completed'
                    ? '提醒卡已收好 ✓'
                    : it.reflection_status === 'needs_revision'
                      ? '家长想和你再聊聊这题'
                      : '待复盘'
                }}
              </span>
            </div>

            <p v-if="it.return_reason" class="reflection-return-banner" role="alert">
              家长留言：{{ it.return_reason }}
            </p>

            <div v-if="it.stem_excerpt" class="reflection-stem-box">
              <div class="reflection-stem-row">
                <span class="reflection-stem-tag">原题</span>
                <div class="reflection-stem-body"><RichText :text="it.stem_excerpt" /></div>
              </div>
              <div v-if="it.student_answer_excerpt" class="reflection-stem-row reflection-answer-row">
                <span class="reflection-stem-tag answer">我当时的作答</span>
                <div class="reflection-stem-body"><RichText :text="it.student_answer_excerpt" /></div>
              </div>
            </div>
            <p v-else class="reflection-stem-placeholder muted tiny">
              对照纸质原卷 {{ formatQuestionLabelHeading(it.question_label) }}
            </p>

            <!-- 已完成且未开启编辑：展示清爽的「给下次的提醒卡」 -->
            <div
              v-if="it.reflection_status === 'completed' && drafts[it.item_id] && !drafts[it.item_id].editingCompleted"
              class="reflection-reminder-card"
            >
              <div class="reflection-reminder-head">
                <span class="chip subtle">{{ getSchoolErrorCategoryLabel(it.error_category) }}</span>
                <button
                  type="button"
                  class="ghost small"
                  @click="drafts[it.item_id].editingCompleted = true; drafts[it.item_id].step = 2"
                >
                  调整一下
                </button>
              </div>
              <div class="reflection-reminder-block">
                <span class="reflection-label">给下次的提醒</span>
                <p class="reflection-reminder-fix">{{ it.fix_strategy }}</p>
              </div>
              <div class="reflection-reminder-block">
                <span class="muted tiny">当时卡点</span>
                <p class="reflection-reminder-stuck muted tiny">{{ it.stuck_point }}</p>
              </div>
            </div>

            <!-- 三步引导 / 书童陪你想 双轨工作区 -->
            <div v-else-if="drafts[it.item_id]" class="reflection-form">
              <div class="reflection-mode-bar" role="group" :aria-label="`${formatQuestionLabelHeading(it.question_label)} 复盘方式`">
                <button
                  type="button"
                  :class="['chip-btn', drafts[it.item_id].mode === 'guide' ? 'selected' : '']"
                  @click="drafts[it.item_id].mode = 'guide'"
                >
                  三步引导卡片
                </button>
                <button
                  type="button"
                  :class="['chip-btn coach-toggle', drafts[it.item_id].mode === 'coach' ? 'selected' : '']"
                  @click="drafts[it.item_id].mode = 'coach'"
                >
                  <img class="coach-mini-icon" src="/icons/apple-touch-icon.png" alt="" aria-hidden="true" width="16" height="16" />
                  <span>
                    书童陪你想{{ (it.coach_turn_count ?? 0) > 0 ? `（${it.coach_turn_count} 条对话）` : '' }}
                  </span>
                </button>
              </div>

              <ReflectionCoachPanel
                v-if="drafts[it.item_id].mode === 'coach'"
                :client="client"
                :item-id="it.item_id"
                :question-heading="formatQuestionLabelHeading(it.question_label)"
                :scene-hint="drafts[it.item_id].scene"
                @back-to-guide="drafts[it.item_id].mode = 'guide'"
                @apply-draft="draft => applyCoachDraft(it.item_id, draft)"
                @turns-updated="cnt => updateCoachTurnCount(it.item_id, cnt)"
              />

              <template v-else>
                <p v-if="drafts[it.item_id].coachDraftHint" class="reflection-coach-hint">
                  {{ drafts[it.item_id].coachDraftHint }}
                </p>

                <div class="reflection-step-bar" role="group" :aria-label="`${formatQuestionLabelHeading(it.question_label)} 复盘步骤`">
                <button
                  type="button"
                  :class="['reflection-step-pill', drafts[it.item_id].step === 1 ? 'active' : 'done']"
                  @click="goStep(it.item_id, 1)"
                >
                  ① 回到考场
                </button>
                <button
                  type="button"
                  :class="[
                    'reflection-step-pill',
                    drafts[it.item_id].step === 2 ? 'active' : drafts[it.item_id].step > 2 ? 'done' : '',
                  ]"
                  @click="goStep(it.item_id, 2)"
                >
                  ② 找到那一步
                </button>
                <button
                  type="button"
                  :class="['reflection-step-pill', drafts[it.item_id].step === 3 ? 'active' : '']"
                  @click="goStep(it.item_id, 3)"
                >
                  ③ 给下次的提醒
                </button>
              </div>

              <!-- 第 1 步：回到考场 -->
              <div v-if="drafts[it.item_id].step === 1" class="reflection-guide-step">
                <p class="reflection-label">做这题时，当时更像哪种情况？</p>
                <div class="reflection-scene-grid">
                  <button
                    v-for="sc in REFLECTION_SCENE_OPTIONS"
                    :key="sc.value"
                    type="button"
                    :class="['reflection-scene-btn', drafts[it.item_id].scene === sc.value ? 'selected' : '']"
                    @click="chooseScene(it.item_id, sc.value)"
                  >
                    <b>{{ sc.label }}</b>
                    <span>{{ sc.hint }}</span>
                  </button>
                </div>
                <div class="reflection-actions">
                  <button type="button" class="ghost small" @click="goStep(it.item_id, 2)">
                    跳过这一步，直接找卡点 →
                  </button>
                </div>
              </div>

              <!-- 第 2 步：找到那一步 -->
              <div v-else-if="drafts[it.item_id].step === 2" class="reflection-guide-step">
                <div class="reflection-cat-group">
                  <span class="reflection-label">更像哪一类卡点？（选一项）</span>
                  <div class="reflection-cat-pills" role="group" :aria-label="`${formatQuestionLabelHeading(it.question_label)} 错因分类`">
                    <button
                      v-for="entry in getOrderedCategoriesForScene(drafts[it.item_id].scene)"
                      :key="entry.category"
                      type="button"
                      :class="[
                        'chip-btn',
                        drafts[it.item_id].errorCategory === entry.category ? 'selected' : '',
                        entry.recommended ? 'recommended' : '',
                      ]"
                      @click="drafts[it.item_id].errorCategory = entry.category; drafts[it.item_id].feedback = ''"
                    >
                      {{ getSchoolErrorCategoryLabel(entry.category) }}
                      <em v-if="entry.recommended" class="reflection-rec-tag">常见</em>
                    </button>
                  </div>
                </div>

                <div v-if="drafts[it.item_id].errorCategory" class="reflection-starter-box">
                  <span class="muted tiny">不知道怎么开头？点一句接下去写（可自由修改）：</span>
                  <div class="reflection-starter-chips">
                    <button
                      v-for="st in getStuckStarters(drafts[it.item_id].errorCategory)"
                      :key="st"
                      type="button"
                      class="chip-btn starter"
                      @click="appendStarter('stuckPoint', it.item_id, st)"
                    >
                      + {{ st }}
                    </button>
                  </div>
                </div>

                <label class="reflection-field">
                  <span>说说当时卡在哪一步</span>
                  <textarea
                    v-model="drafts[it.item_id].stuckPoint"
                    rows="2"
                    maxlength="300"
                    :aria-label="`${formatQuestionLabelHeading(it.question_label)} 当时卡在哪一步`"
                    placeholder="用自己的话写下具体漏了哪个条件、或哪一步算岔了…"
                    @input="drafts[it.item_id].feedback = ''"
                  />
                </label>

                <p v-if="drafts[it.item_id].feedback" class="reflection-reject-alert" role="alert">
                  {{ drafts[it.item_id].feedback }}
                </p>

                <div class="reflection-actions space-between">
                  <button type="button" class="ghost small" @click="goStep(it.item_id, 1)">
                    ← 回到考场
                  </button>
                  <button type="button" class="primary small" @click="goStep(it.item_id, 3)">
                    下一步：写给下次的自己 →
                  </button>
                </div>
              </div>

              <!-- 第 3 步：给下次的自己一张提醒卡 -->
              <div v-else class="reflection-guide-step">
                <div class="reflection-starter-box">
                  <span class="muted tiny">用「如果…我就先…」定一个下次能直接用上的小动作：</span>
                  <div class="reflection-starter-chips">
                    <button
                      v-for="st in FIX_STARTERS"
                      :key="st"
                      type="button"
                      class="chip-btn starter"
                      @click="appendStarter('fixStrategy', it.item_id, st)"
                    >
                      + {{ st }}
                    </button>
                  </div>
                </div>

                <label class="reflection-field">
                  <span>给下次遇到同类题的自己留一句提醒</span>
                  <textarea
                    v-model="drafts[it.item_id].fixStrategy"
                    rows="2"
                    maxlength="300"
                    :aria-label="`${formatQuestionLabelHeading(it.question_label)} 给下次的提醒`"
                    placeholder="如果再看到…，我就先…；做完后我用…检查。"
                    @input="drafts[it.item_id].feedback = ''"
                  />
                </label>

                <p v-if="drafts[it.item_id].feedback" class="reflection-reject-alert" role="alert">
                  {{ drafts[it.item_id].feedback }}
                </p>

                <div class="reflection-actions space-between">
                  <button type="button" class="ghost small" @click="goStep(it.item_id, 2)">
                    ← 上一步
                  </button>
                  <div class="reflection-actions">
                    <button
                      v-if="it.reflection_status === 'completed'"
                      type="button"
                      class="ghost small"
                      @click="drafts[it.item_id].editingCompleted = false"
                    >
                      取消
                    </button>
                    <button
                      type="button"
                      class="primary small"
                      :disabled="drafts[it.item_id].submitting"
                      @click="submitReflection(it)"
                    >
                      {{
                        drafts[it.item_id].submitting
                          ? '正在收好…'
                          : it.reflection_status === 'completed'
                            ? '更新提醒卡 ✓'
                            : '收好提醒卡 ✓'
                      }}
                    </button>
                  </div>
                </div>
              </div>
              </template>
            </div>
            </li>
          </ul>
        </template>
      </template>
    </section>
  </div>
</template>
