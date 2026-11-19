<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
  describeError,
  SUBJECT_LABELS,
  type ApiClient,
  type AttemptResult,
  type AttemptRow,
  type GrowthStatus,
  type PracticeSession,
  type PracticeSessionComplete,
  type Purpose,
  type Subject,
  type WrongQuestionSummary,
} from '../api'
import { DISCIPLINE_TEXT, fmtPoints, KIND_LABELS, resolveAnswerContent, SCORING_LABELS } from '../copy'
import QuestionCard from '../components/QuestionCard.vue'
import TutorDrawer from '../components/TutorDrawer.vue'
import Note from '../components/Note.vue'
import type { NoticeTone } from '../components/Notice.vue'
import { RichText } from '../rich'

const props = defineProps<{
  client: ApiClient
  subject: Subject
  notify: (text: string, tone?: NoticeTone) => void
  focusKnowledgeCode?: string | null
}>()

const emit = defineEmits<{
  (e: 'clearFocus'): void
  (e: 'goView', view: 'practice' | 'growth' | 'knowledge'): void
}>()

const purpose = ref<Purpose>('training')
const targetCount = ref<number>(5)
const lobbyMode = ref<'practice' | 'review'>('practice')
const wrongFilter = ref<'all' | 'active'>('all')
const localFocusCode = ref<string | null>(null)
const starting = ref(false)
const advancing = ref(false)
const completing = ref(false)
const error = ref('')

const session = ref<PracticeSession | null>(null)
const currentAnswered = ref(false)
const completion = ref<PracticeSessionComplete | null>(null)
const activeTutorItem = ref<WrongQuestionSummary | null>(null)

const growthBrief = ref<GrowthStatus | null>(null)
const recentWrong = ref<WrongQuestionSummary[]>([])
const attempts = ref<AttemptRow[]>([])
const loadingContext = ref(false)

const effectiveFocusCode = computed(() => props.focusKnowledgeCode ?? localFocusCode.value)

const focusedTopicName = computed(() => {
  if (!effectiveFocusCode.value || !growthBrief.value) return effectiveFocusCode.value ?? ''
  const all = [
    ...growthBrief.value.weaknesses,
    ...growthBrief.value.strengths,
    ...growthBrief.value.developing,
    ...growthBrief.value.untested_highlights,
  ]
  return all.find(x => x.code === effectiveFocusCode.value)?.name ?? effectiveFocusCode.value
})

const activeTutorCount = computed(() => recentWrong.value.filter(w => Boolean(w.tutor_session_id)).length)

const filteredRecentWrong = computed(() =>
  wrongFilter.value === 'active'
    ? recentWrong.value.filter(w => Boolean(w.tutor_session_id))
    : recentWrong.value
)

const hasMoreQuestions = computed(() => {
  if (!session.value) return false
  return session.value.completed_count < session.value.total_items
})

function sessionStorageKey(sub: Subject): string {
  return `shutong.practice_session_id.${sub}`
}

function saveActiveSessionId(sub: Subject, id: string | null) {
  try {
    const key = sessionStorageKey(sub)
    if (id) window.sessionStorage.setItem(key, id)
    else window.sessionStorage.removeItem(key)
  } catch {
    // 忽略无痕模式或存储受限
  }
}

function readActiveSessionId(sub: Subject): string | null {
  try {
    return window.sessionStorage.getItem(sessionStorageKey(sub))
  } catch {
    return null
  }
}

async function loadContext() {
  loadingContext.value = true
  try {
    const [g, wrongs, atts] = await Promise.all([
      props.client.growthStatus(props.subject),
      props.client.wrongAttempts(props.subject, 10),
      props.client.attempts(props.subject),
    ])
    growthBrief.value = g
    recentWrong.value = wrongs
    attempts.value = atts

    // 刷新页面后如仍有未完成的同会话 ID，只读恢复进度，不重复消耗未见题曝光。
    if (!session.value && !completion.value) {
      const savedId = readActiveSessionId(props.subject)
      if (savedId) {
        try {
          const restored = await props.client.getPracticeSession(savedId)
          if (restored.status !== 'completed') {
            session.value = restored
            currentAnswered.value = false
            props.notify('已恢复上次未完成的练习会话。', 'info')
          } else {
            saveActiveSessionId(props.subject, null)
          }
        } catch {
          saveActiveSessionId(props.subject, null)
        }
      }
    }
  } catch (e) {
    props.notify(`加载练习背景失败：${describeError(e)}`, 'caution')
  } finally {
    loadingContext.value = false
  }
}

async function startSession(overrideFocus?: string | null) {
  starting.value = true
  error.value = ''
  completion.value = null
  activeTutorItem.value = null
  currentAnswered.value = false
  const focus = overrideFocus !== undefined ? overrideFocus : (effectiveFocusCode.value ?? null)
  try {
    const created = await props.client.createPracticeSession({
      subject: props.subject,
      targetCount: targetCount.value,
      purpose: purpose.value,
      focusKnowledgeCode: focus,
    })
    session.value = created
    saveActiveSessionId(props.subject, created.id)
    if (focus) clearEffectiveFocus()
    props.notify(
      `已为你综合编制 ${created.total_items} 道${SUBJECT_LABELS[props.subject]}练习题。`,
      'success'
    )
  } catch (e) {
    error.value = describeError(e)
  } finally {
    starting.value = false
  }
}

function clearEffectiveFocus() {
  localFocusCode.value = null
  emit('clearFocus')
}

function focusAndPractice(knowledgeCode: string) {
  localFocusCode.value = knowledgeCode
  purpose.value = 'training'
  lobbyMode.value = 'practice'
  activeTutorItem.value = null
}

function enterReviewWorkspace() {
  lobbyMode.value = 'review'
  if (!activeTutorItem.value) {
    const startedItem = recentWrong.value.find(w => Boolean(w.tutor_session_id))
    if (startedItem) activeTutorItem.value = startedItem
  }
}

function handleAttemptSubmitted(record: AttemptResult) {
  currentAnswered.value = true
  if (session.value) {
    // 刷新后端会话已完成计数与槽位状态，保留当前题卡完整反馈视图
    void props.client.attempts(props.subject).then(rows => {
      attempts.value = rows
    })
  }
  if (record.earned_points !== null && record.earned_points < record.max_points) {
    props.notify('本题有待巩固，本轮结束后可请「我的书童」一步步引导讲解。', 'info')
  }
}

async function goNextQuestion() {
  if (!session.value || advancing.value) return
  advancing.value = true
  error.value = ''
  try {
    const nextState = await props.client.nextPracticeSessionItem(session.value.id)
    session.value = nextState
    currentAnswered.value = false
    if (!nextState.current_item && nextState.completed_count >= nextState.total_items) {
      await finishSession()
    }
  } catch (e) {
    error.value = describeError(e)
  } finally {
    advancing.value = false
  }
}

async function finishSession() {
  if (!session.value || completing.value) return
  completing.value = true
  error.value = ''
  try {
    const res = await props.client.completePracticeSession(session.value.id)
    saveActiveSessionId(props.subject, null)
    completion.value = res
    session.value = null
    currentAnswered.value = false
    if (res.wrong_items.length > 0) {
      activeTutorItem.value = res.wrong_items[0]
      props.notify(`本轮练习结束，共有 ${res.wrong_items.length} 道错题可立即请「我的书童」对话讲解。`, 'info')
    } else {
      props.notify('本轮练习已完成，客观题全部答对！', 'success')
    }
    await loadContext()
  } catch (e) {
    error.value = describeError(e)
  } finally {
    completing.value = false
  }
}

function resetToLobby(clearSaved = true) {
  if (clearSaved) saveActiveSessionId(props.subject, null)
  session.value = null
  completion.value = null
  activeTutorItem.value = null
  currentAnswered.value = false
  error.value = ''
}

watch(
  () => props.focusKnowledgeCode,
  code => {
    if (code) lobbyMode.value = 'practice'
  }
)

watch(
  [() => props.client, () => props.subject],
  () => {
    localFocusCode.value = null
    lobbyMode.value = 'practice'
    wrongFilter.value = 'all'
    resetToLobby(false)
    void loadContext()
  },
  { immediate: true }
)
</script>

<template>
  <div class="view-stack">
    <!-- 1. 方案 A：意图分流双工作台（未开练且未刚结算时显示） -->
    <template v-if="!session && !completion">
      <div class="workspace-switcher" role="tablist" aria-label="练习页工作模式">
        <button
          type="button"
          role="tab"
          :aria-selected="lobbyMode === 'practice'"
          :class="['ws-tab', lobbyMode === 'practice' ? 'active' : '']"
          @click="lobbyMode = 'practice'"
        >
          <span class="ws-tab-text">
            <b>开始新练习</b>
            <small>选择「综合智能练习」或「阶段诊断 · 未见题」</small>
          </span>
          <span class="chip mid">{{ purpose === 'evaluation' ? '阶段诊断' : '智能练习' }}</span>
        </button>

        <button
          type="button"
          role="tab"
          :aria-selected="lobbyMode === 'review'"
          :class="['ws-tab', lobbyMode === 'review' ? 'active' : '']"
          @click="enterReviewWorkspace"
        >
          <span class="ws-tab-text">
            <b>近期错题回顾</b>
            <small>
              {{
                recentWrong.length > 0
                  ? `${activeTutorCount} 题与我的书童对话中 · 独立双栏专注订正`
                  : '暂无待回顾错题'
              }}
            </small>
          </span>
          <span :class="['ws-count-badge', recentWrong.length === 0 ? 'done' : '']">
            {{ recentWrong.length > 0 ? `${recentWrong.length} 题待回顾` : '已清零 ✓' }}
          </span>
        </button>
      </div>

      <!-- 1A. 工作区一：突出练习模式选择与发车 -->
      <template v-if="lobbyMode === 'practice'">
        <section class="card practice-lobby" aria-label="智能综合练习编排">
          <div class="card-head">
            <div>
              <h2>{{ SUBJECT_LABELS[subject] }} · 选择练习模式</h2>
              <p class="card-sub">
                结合课标知识图谱、已审核真题库曝光与当前短板，先定练习目的与题量，再一键开始。
              </p>
            </div>
            <button type="button" class="ghost small" @click="loadContext" :disabled="loadingContext">
              {{ loadingContext ? '刷新中…' : '刷新诊断摘要' }}
            </button>
          </div>

          <Note v-if="effectiveFocusCode" title="已锁定知识点定向突破" tone="neutral">
            当前将优先围绕知识点「<b>{{ focusedTopicName }}</b>」组卷强化。
            <button type="button" class="ghost small inline-clear" @click="clearEffectiveFocus">
              取消定向
            </button>
          </Note>

          <div v-if="growthBrief" class="compact-status-bar" aria-label="当前学科能力摘要">
            <div class="status-pills">
              <span class="status-dot-item">
                <i class="dot ok" aria-hidden="true" />
                已掌握 <b>{{ growthBrief.summary_counts.mastered_count ?? 0 }}</b>
              </span>
              <span class="status-dot-item">
                <i class="dot bad" aria-hidden="true" />
                薄弱待突破 <b>{{ growthBrief.summary_counts.weak_count ?? 0 }}</b>
              </span>
              <span class="status-dot-item">
                <i class="dot wait" aria-hidden="true" />
                待测与探索盲区
                <b>{{ (growthBrief.summary_counts.insufficient_count ?? 0) + (growthBrief.summary_counts.untested_count ?? 0) }}</b>
              </span>
              <span class="status-dot-item">
                历史错题待复盘 <b>{{ growthBrief.recent_wrong_count }}</b>
              </span>
            </div>
          </div>

          <div class="lobby-controls lobby-controls--mode-first">
            <div class="mode-hero-grid" role="radiogroup" aria-label="练习模式选择">
              <button
                type="button"
                role="radio"
                :aria-checked="purpose === 'training'"
                :class="['mode-card', purpose === 'training' ? 'selected' : '']"
                @click="purpose = 'training'"
              >
                <span class="mode-card-top">
                  <span class="mode-card-title">
                    <span class="mode-radio-dot" aria-hidden="true" />
                    综合智能练习
                  </span>
                  <span class="chip mid">日常推荐</span>
                </span>
                <p class="mode-card-desc">按短板与前驱关系动态配题，错题后接「我的书童」启发引导。</p>
                <span class="mode-bullets">
                  <span class="chip">薄弱突破 + 前置巩固</span>
                  <span class="chip">支持我的书童引导</span>
                </span>
              </button>

              <button
                type="button"
                role="radio"
                :aria-checked="purpose === 'evaluation'"
                :class="['mode-card eval', purpose === 'evaluation' ? 'selected' : '']"
                @click="purpose = 'evaluation'"
              >
                <span class="mode-card-top">
                  <span class="mode-card-title">
                    <span class="mode-radio-dot" aria-hidden="true" />
                    阶段诊断 · 未见题
                  </span>
                  <span class="chip teal">独立验证</span>
                </span>
                <p class="mode-card-desc">严格只取从未曝光新题，用于计入成长阶段客观基线与复测对比。</p>
                <span class="mode-bullets">
                  <span class="chip">100% 未见新题</span>
                  <span class="chip">计入成长对比</span>
                </span>
              </button>
            </div>

            <Note v-if="purpose === 'evaluation'" title="独立验证纪律" tone="discipline">
              {{ DISCIPLINE_TEXT }}
            </Note>

            <p v-if="error" class="form-error">{{ error }}</p>

            <div class="launch-bar">
              <div class="count-row">
                <span class="control-label">本轮题量</span>
                <div class="count-pills" role="group" aria-label="每轮题量">
                  <button
                    v-for="cnt in [3, 5, 8]"
                    :key="cnt"
                    type="button"
                    :class="targetCount === cnt ? 'chip-btn selected' : 'chip-btn'"
                    @click="targetCount = cnt"
                  >
                    {{ cnt }} 题
                  </button>
                </div>
              </div>

              <div class="lobby-actions">
                <button type="button" class="ghost" @click="emit('goView', 'knowledge')">
                  去知识图谱选知识点 →
                </button>
                <button
                  type="button"
                  class="primary"
                  :disabled="starting"
                  @click="startSession()"
                >
                  {{ starting ? '正在编制专属练习…' : `开始本轮${purpose === 'evaluation' ? '未见题诊断' : '智能练习'} (${targetCount} 题)` }}
                </button>
              </div>
            </div>
          </div>
        </section>

        <div v-if="recentWrong.length > 0" class="bottom-bridge">
          <div>
            <b>有 {{ recentWrong.length }} 道近期错题等待巩固</b>
            <span class="muted" style="margin-left: 8px;">
              {{
                activeTutorCount > 0
                  ? `其中 ${activeTutorCount} 道已保存与「我的书童」的对话，可随时切入错题工作台继续。`
                  : '可随时切入独立错题工作台，让「我的书童」陪你一步步理清思路。'
              }}
            </span>
          </div>
          <button type="button" class="ghost small" @click="enterReviewWorkspace">
            进入错题工作台 →
          </button>
        </div>
      </template>

      <!-- 1B. 工作区二：方案 2（左内容+右大按钮双区错题卡 + 纯净「我的书童」聊天窗） -->
      <section v-else class="card" aria-label="近期错题与引导复习">
        <div class="card-head">
          <div>
            <h2>{{ SUBJECT_LABELS[subject] }} · 近期错题回顾</h2>
          </div>
          <div v-if="recentWrong.length > 0" class="filter-pills" role="group" aria-label="筛选近期错题">
            <button
              type="button"
              :class="['chip-btn', wrongFilter === 'all' ? 'selected' : '']"
              @click="wrongFilter = 'all'"
            >
              全部 ({{ recentWrong.length }})
            </button>
            <button
              type="button"
              :class="['chip-btn', wrongFilter === 'active' ? 'selected' : '']"
              @click="wrongFilter = 'active'"
            >
              对话中 ({{ activeTutorCount }})
            </button>
          </div>
        </div>

        <div v-if="recentWrong.length === 0" class="empty-celebrate" style="margin-top: 12px;">
          <b>当前学科暂无近期错题记录！</b>
          <p class="muted" style="margin: 6px 0 10px;">可以切回「开始新练习」继续按薄弱点或未见题诊断练题。</p>
          <button type="button" class="primary small" @click="lobbyMode = 'practice'">
            去开始新练习
          </button>
        </div>

        <p v-else-if="filteredRecentWrong.length === 0" class="muted" style="margin-top: 12px;">
          暂无与「我的书童」开启对话的错题，可切回「全部」任选一题发起对话。
        </p>

        <div v-else class="wrong-review-layout wrong-review-layout--split">
          <div class="wrong-list-col">
            <ul class="wrong-list">
              <li
                v-for="w in filteredRecentWrong"
                :key="w.attempt_id"
                :class="['wcard-2', activeTutorItem?.attempt_id === w.attempt_id ? 'active' : '']"
              >
                <div class="wcard-2-main">
                  <div class="wcard-2-top">
                    <div class="wrong-topic-chips">
                      <span v-for="t in w.knowledge_titles" :key="t" class="chip">{{ t }}</span>
                      <span v-if="w.adopted_solution" class="chip good">
                        已定建议：{{ w.adopted_solution.title }}
                      </span>
                    </div>
                    <span class="muted tiny">{{ fmtPoints(w.earned_points ?? 0) }} / {{ fmtPoints(w.max_points) }}</span>
                  </div>
                  <p class="wrong-stem"><RichText :text="w.stem" /></p>
                  <div class="ans-inline-row">
                    <span class="ans-pill-wrong">
                      ✗ 错答：<RichText :text="resolveAnswerContent(w.student_answer, w.options)" />
                    </span>
                    <span v-if="w.correct_answer" class="ans-pill-right">
                      ✓ 正解：<RichText :text="resolveAnswerContent(w.correct_answer, w.options)" />
                    </span>
                  </div>
                </div>

                <button
                  type="button"
                  :class="[
                    'wcard-2-action',
                    activeTutorItem?.attempt_id === w.attempt_id
                      ? 'current'
                      : w.tutor_session_id
                        ? 'in-progress'
                        : '',
                  ]"
                  @click="activeTutorItem = w"
                >
                  <img
                    class="wcard-action-icon"
                    src="/icons/apple-touch-icon.png"
                    alt=""
                    aria-hidden="true"
                    width="28"
                    height="28"
                  />
                  <b>
                    {{
                      activeTutorItem?.attempt_id === w.attempt_id
                        ? '对话中'
                        : w.tutor_session_id
                          ? '继续对话'
                          : '问我的书童'
                    }}
                  </b>
                  <small>{{ w.tutor_session_id ? '查看历史对话' : '点击开始对话' }}</small>
                </button>
              </li>
            </ul>
          </div>

          <div class="tutor-col">
            <TutorDrawer
              v-if="activeTutorItem"
              :client="client"
              :wrong-item="activeTutorItem"
              @close="activeTutorItem = null"
            >
              <template #banner>
                <div
                  v-if="activeTutorItem.adopted_solution"
                  class="advice-inline-bar"
                  aria-label="家长或老师选定的改进对策"
                >
                  <div class="advice-inline-copy">
                    <b>改进建议：{{ activeTutorItem.adopted_solution.title }}</b>
                    <span v-if="activeTutorItem.adopted_solution.admin_note" class="advice-inline-note">
                      （{{ activeTutorItem.adopted_solution.admin_note }}）
                    </span>
                    <ul class="advice-inline-steps">
                      <li v-for="(step, idx) in activeTutorItem.adopted_solution.action_steps" :key="idx">
                        {{ step }}
                      </li>
                    </ul>
                  </div>
                  <button
                    v-if="activeTutorItem.knowledge_codes.length > 0"
                    type="button"
                    class="ghost small advice-practice-btn"
                    @click="focusAndPractice(activeTutorItem.knowledge_codes[0])"
                  >
                    针对「{{ activeTutorItem.knowledge_titles[0] ?? '此考点' }}」练一轮 →
                  </button>
                </div>
              </template>
            </TutorDrawer>

            <div v-else class="chat-window chat-window--empty" aria-label="我的书童对话窗">
              <div class="chat-header">
                <div class="chat-agent">
                  <img
                    class="ai-avatar-img"
                    src="/icons/apple-touch-icon.png"
                    alt="我的书童"
                    width="36"
                    height="36"
                  />
                  <div class="chat-agent-title">
                    <h3>
                      <span class="online-dot" aria-hidden="true" />
                      我的书童
                    </h3>
                  </div>
                </div>
              </div>
              <div class="chat-messages">
                <div class="msg-row ai">
                  <img
                    class="msg-avatar-img"
                    src="/icons/apple-touch-icon.png"
                    alt=""
                    aria-hidden="true"
                    width="28"
                    height="28"
                  />
                  <div class="msg-bubble-wrap">
                    <div class="msg-sender"><b>我的书童</b></div>
                    <p class="msg-bubble">
                      嗨！点击左边任意错题卡片右侧的「问我的书童」，我们就能立刻在这里聊天，一起找出卡住的地方～
                    </p>
                  </div>
                </div>
              </div>
              <div class="chat-composer chat-composer--preview" aria-hidden="true">
                <input type="text" disabled placeholder="选定左侧一道错题后即可发送对话…" />
                <button type="button" class="chat-send-btn" disabled>发送</button>
              </div>
            </div>
          </div>
        </div>
      </section>
    </template>

    <!-- 2. 进行中练习会话 -->
    <template v-if="session">
      <section class="card session-bar" aria-label="本轮练习进度">
        <div class="session-head">
          <div>
            <span class="eyebrow">
              {{ session.purpose === 'evaluation' ? '阶段诊断 · 未见题' : '智能综合练习' }} · {{ SUBJECT_LABELS[subject] }}
            </span>
            <h3>
              已完成 {{ session.completed_count }} / {{ session.total_items }} 题
            </h3>
          </div>
          <div class="session-head-actions">
            <button
              type="button"
              class="ghost small"
              :disabled="completing"
              @click="finishSession"
            >
              {{ completing ? '结算中…' : '提前交卷看错题' }}
            </button>
          </div>
        </div>

        <div class="composition-pills">
          <span v-if="session.composition_summary.weak_count" class="chip bad">
            薄弱突破 {{ session.composition_summary.weak_count }} 题
          </span>
          <span v-if="session.composition_summary.prereq_count" class="chip wait">
            前置巩固 {{ session.composition_summary.prereq_count }} 题
          </span>
          <span v-if="session.composition_summary.explore_count" class="chip">
            盲区探索 {{ session.composition_summary.explore_count }} 题
          </span>
          <span v-if="session.composition_summary.review_count" class="chip good">
            优势保持 {{ session.composition_summary.review_count }} 题
          </span>
        </div>

        <ol class="slot-strip" aria-label="题组编排槽位">
          <li
            v-for="slot in session.items"
            :key="slot.seq"
            :class="[
              'slot-item',
              slot.answered
                ? (slot.earned_points !== null && slot.earned_points < slot.max_points ? 'wrong' : 'done')
                : (session.current_item?.question_version_id === slot.question_version_id ? 'current' : 'todo'),
            ]"
          >
            <span class="slot-num">第 {{ slot.seq }} 题</span>
            <small>{{ slot.selection_reason }}</small>
          </li>
        </ol>
      </section>

      <div v-if="session.current_item" class="current-question-wrap">
        <div class="question-reason-banner">
          <span class="reason-tag">选题依据：{{ session.current_item.selection_reason || '综合配比' }}</span>
          <span
            v-for="kp in session.current_item.knowledge_titles || []"
            :key="kp"
            class="chip"
          >
            {{ kp }}
          </span>
        </div>
        <QuestionCard
          :key="session.current_item.exposure_id"
          :client="client"
          :item="session.current_item"
          :badge="session.purpose === 'evaluation' ? '阶段诊断 · 未见题' : '智能综合练习'"
          @submitted="handleAttemptSubmitted"
        >
          <template #footer>
            <div v-if="currentAnswered" class="session-next-actions">
              <button
                v-if="session.completed_count + 1 < session.total_items"
                type="button"
                class="primary"
                :disabled="advancing"
                @click="goNextQuestion"
              >
                {{ advancing ? '加载下一题…' : '进入下一题 →' }}
              </button>
              <button
                type="button"
                :class="session.completed_count + 1 < session.total_items ? 'ghost' : 'primary'"
                :disabled="completing"
                @click="finishSession"
              >
                {{ completing ? '正在汇总错题…' : '结束本轮并查看错题讲解' }}
              </button>
            </div>
            <p v-else class="muted tiny">提交本题作答后可进入下一题，全部完成后可请「我的书童」逐题讲评。</p>
          </template>
        </QuestionCard>
      </div>

      <section v-else class="card">
        <p>本轮题组已全部呈现完毕，请点击下方按钮查看错题与引导讲评。</p>
        <div class="lobby-actions">
          <button type="button" class="primary" :disabled="completing" @click="finishSession">
            {{ completing ? '结算中…' : '查看本轮结算与错题讲解' }}
          </button>
          <button
            v-if="hasMoreQuestions"
            type="button"
            class="ghost"
            :disabled="advancing"
            @click="goNextQuestion"
          >
            继续下一题
          </button>
        </div>
      </section>
    </template>

    <!-- 3. 练习完成结算 + AI 错题引导区 -->
    <section v-if="completion" class="card completion-card" aria-label="本轮练习结算与错题讲解">
      <div class="card-head">
        <div>
          <h2>本轮练习结算</h2>
          <p class="card-sub">
            共作答 {{ completion.answered_count }} 题：客观答对 {{ completion.correct_count }} 题，待引导订正错题 {{ completion.wrong_count }} 题{{ completion.subjective_count ? `，主观自评 ${completion.subjective_count} 题` : '' }}。
          </p>
        </div>
        <button type="button" class="primary small" @click="resetToLobby()">
          再练一轮
        </button>
      </div>

      <div v-if="completion.wrong_items.length === 0" class="empty-celebrate">
        <b>本轮已作答的客观题全部掌握！</b>
        <p class="muted">可以前往“成长状态”查看能力分布变化，或从知识图谱挑战未测验盲区。</p>
      </div>

      <div v-else class="wrong-review-layout">
        <div class="wrong-list-col">
          <h3>本轮错题（点击开启「我的书童」对话）</h3>
          <ul class="wrong-list">
            <li
              v-for="w in completion.wrong_items"
              :key="w.attempt_id"
              :class="['wrong-item-card', activeTutorItem?.attempt_id === w.attempt_id ? 'active' : '']"
            >
              <div class="wrong-meta">
                <span class="chip bad">你的作答：{{ w.student_answer }}</span>
                <span class="muted">得分 {{ fmtPoints(w.earned_points ?? 0) }} / {{ fmtPoints(w.max_points) }}</span>
              </div>
              <p class="wrong-stem"><RichText :text="w.stem" /></p>
              <div class="wrong-foot">
                <span v-for="t in w.knowledge_titles" :key="t" class="chip">{{ t }}</span>
                <button
                  type="button"
                  class="primary small"
                  @click="activeTutorItem = w"
                >
                  {{ activeTutorItem?.attempt_id === w.attempt_id ? '正在对话中' : '问我的书童' }}
                </button>
              </div>
            </li>
          </ul>
        </div>

        <div v-if="activeTutorItem" class="tutor-col">
          <TutorDrawer
            :client="client"
            :wrong-item="activeTutorItem"
            @close="activeTutorItem = null"
          />
        </div>
      </div>
    </section>

    <!-- 4. 作答溯源记录（默认折叠为单行面板，保留可访问 region 供练习大厅与结算复核） -->
    <section
      v-if="!session && (lobbyMode === 'practice' || Boolean(completion)) && attempts.length > 0"
      aria-label="作答溯源记录"
    >
      <details class="trace-disclosure">
        <summary>
          <span>作答溯源记录（最近 {{ Math.min(attempts.length, 8) }} 条）</span>
          <span class="muted tiny">展开查看 ▾</span>
        </summary>
        <ul class="attempt-trace" style="margin-top: 8px;">
          <li v-for="row in attempts.slice(0, 8)" :key="row.id">
            <span class="chip">{{ KIND_LABELS[row.kind] ?? row.kind }}</span>
            <span class="muted">{{ SCORING_LABELS[row.scoring_origin] ?? row.scoring_origin }}</span>
            <b v-if="row.earned_points !== null">{{ fmtPoints(row.earned_points) }} / {{ fmtPoints(row.max_points) }}</b>
            <b v-else-if="row.self_assessment">自评 {{ fmtPoints(row.self_assessment.self_earned_points) }} / {{ fmtPoints(row.max_points) }}</b>
            <span v-else class="muted">待自评</span>
          </li>
        </ul>
      </details>
    </section>
  </div>
</template>
