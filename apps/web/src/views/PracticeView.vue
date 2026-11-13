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
import { DISCIPLINE_TEXT, fmtPoints, KIND_LABELS, SCORING_LABELS } from '../copy'
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

const focusedTopicName = computed(() => {
  if (!props.focusKnowledgeCode || !growthBrief.value) return props.focusKnowledgeCode ?? ''
  const all = [
    ...growthBrief.value.weaknesses,
    ...growthBrief.value.strengths,
    ...growthBrief.value.developing,
    ...growthBrief.value.untested_highlights,
  ]
  return all.find(x => x.code === props.focusKnowledgeCode)?.name ?? props.focusKnowledgeCode
})

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
  const focus = overrideFocus !== undefined ? overrideFocus : (props.focusKnowledgeCode ?? null)
  try {
    const created = await props.client.createPracticeSession({
      subject: props.subject,
      targetCount: targetCount.value,
      purpose: purpose.value,
      focusKnowledgeCode: focus,
    })
    session.value = created
    saveActiveSessionId(props.subject, created.id)
    if (focus) emit('clearFocus')
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

function handleAttemptSubmitted(record: AttemptResult) {
  currentAnswered.value = true
  if (session.value) {
    // 刷新后端会话已完成计数与槽位状态，保留当前题卡完整反馈视图
    void props.client.attempts(props.subject).then(rows => {
      attempts.value = rows
    })
  }
  if (record.earned_points !== null && record.earned_points < record.max_points) {
    props.notify('本题有待巩固，本轮结束后可由书童 AI 一步步引导讲解。', 'info')
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
      props.notify(`本轮练习结束，共有 ${res.wrong_items.length} 道错题可立即开始 AI 引导讲解。`, 'info')
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
  [() => props.client, () => props.subject],
  () => {
    resetToLobby(false)
    void loadContext()
  },
  { immediate: true }
)
</script>

<template>
  <div class="view-stack">
    <!-- 1. 备考选题大厅（未开练且未刚结算时显示） -->
    <section
      v-if="!session && !completion"
      class="card practice-lobby"
      aria-label="智能综合练习编排"
    >
      <div class="card-head">
        <div>
          <h2>{{ SUBJECT_LABELS[subject] }}智能综合练习</h2>
          <p class="card-sub">
            结合课标知识图谱、已审核真题库曝光与你的当前能力短板，自动配比薄弱突破、前置巩固与盲区探索题组。
          </p>
        </div>
        <button type="button" class="ghost small" @click="loadContext" :disabled="loadingContext">
          {{ loadingContext ? '刷新中…' : '刷新诊断摘要' }}
        </button>
      </div>

      <Note v-if="focusKnowledgeCode" title="已锁定知识点定向突破" tone="neutral">
        当前将优先围绕知识点「<b>{{ focusedTopicName }}</b>」组卷强化。
        <button type="button" class="ghost small inline-clear" @click="emit('clearFocus')">
          取消定向
        </button>
      </Note>

      <div v-if="growthBrief" class="lobby-metrics">
        <div class="metric-pill ok">
          <b>{{ growthBrief.summary_counts.mastered_count ?? 0 }}</b>
          <span>已掌握知识点</span>
        </div>
        <div class="metric-pill bad">
          <b>{{ growthBrief.summary_counts.weak_count ?? 0 }}</b>
          <span>薄弱待突破</span>
        </div>
        <div class="metric-pill wait">
          <b>{{ (growthBrief.summary_counts.insufficient_count ?? 0) + (growthBrief.summary_counts.untested_count ?? 0) }}</b>
          <span>待测与探索盲区</span>
        </div>
        <div class="metric-pill neutral">
          <b>{{ growthBrief.recent_wrong_count }}</b>
          <span>历史错题待复盘</span>
        </div>
      </div>

      <div class="lobby-controls">
        <div class="control-block">
          <span class="control-label">练习模式</span>
          <div class="mode-pills" role="radiogroup" aria-label="练习模式选择">
            <button
              type="button"
              role="radio"
              :aria-checked="purpose === 'training'"
              :class="purpose === 'training' ? 'mode-pill selected' : 'mode-pill'"
              @click="purpose = 'training'"
            >
              <b>综合智能练习</b>
              <small>按短板与前驱关系动态配题，错题后接 AI 引导</small>
            </button>
            <button
              type="button"
              role="radio"
              :aria-checked="purpose === 'evaluation'"
              :class="purpose === 'evaluation' ? 'mode-pill selected' : 'mode-pill'"
              @click="purpose = 'evaluation'"
            >
              <b>阶段诊断 · 未见题</b>
              <small>严格只取未曝光新题，计入成长阶段客观对比</small>
            </button>
          </div>
        </div>

        <div class="control-block">
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
      </div>

      <Note v-if="purpose === 'evaluation'" title="独立验证纪律" tone="discipline">
        {{ DISCIPLINE_TEXT }}
      </Note>

      <p v-if="error" class="form-error">{{ error }}</p>

      <div class="lobby-actions">
        <button
          type="button"
          class="primary"
          :disabled="starting"
          @click="startSession()"
        >
          {{ starting ? '正在编制专属练习…' : `开始本轮${purpose === 'evaluation' ? '未见题诊断' : '智能练习'} (${targetCount} 题)` }}
        </button>
        <button type="button" class="ghost" @click="emit('goView', 'knowledge')">
          去知识图谱选知识点 →
        </button>
      </div>
    </section>

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
            <p v-else class="muted tiny">提交本题作答后可进入下一题，全部完成后统一查看 AI 引导讲评。</p>
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
          <h3>本轮错题（点击开启书童 AI 引导）</h3>
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
                  {{ activeTutorItem?.attempt_id === w.attempt_id ? '正在引导中' : 'AI 引导讲解' }}
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

    <!-- 4. 近期历史错题快捷回顾（仅在未开练时展示） -->
    <section
      v-if="!session && !completion && recentWrong.length > 0"
      class="card"
      aria-label="近期错题与引导复习"
    >
      <div class="card-head">
        <div>
          <h2>近期错题回顾</h2>
          <p class="card-sub">不用等一轮结束，随时可以点击任意错题让 AI 老师用提示引导你重新走通思路。</p>
        </div>
      </div>
      <div class="wrong-review-layout">
        <div class="wrong-list-col">
          <ul class="wrong-list">
            <li
              v-for="w in recentWrong"
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
                <button
                  type="button"
                  class="ghost small"
                  @click="activeTutorItem = w"
                >
                  {{ w.tutor_session_id ? '继续 AI 引导' : 'AI 引导讲解' }}
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

    <!-- 5. 作答溯源记录 -->
    <section v-if="attempts.length > 0" class="card" aria-label="作答溯源记录">
      <div class="card-head">
        <h2>作答溯源记录</h2>
        <span class="muted tiny">最近 {{ Math.min(attempts.length, 8) }} 条</span>
      </div>
      <ul class="attempt-trace">
        <li v-for="row in attempts.slice(0, 8)" :key="row.id">
          <span class="chip">{{ KIND_LABELS[row.kind] ?? row.kind }}</span>
          <span class="muted">{{ SCORING_LABELS[row.scoring_origin] ?? row.scoring_origin }}</span>
          <b v-if="row.earned_points !== null">{{ fmtPoints(row.earned_points) }} / {{ fmtPoints(row.max_points) }}</b>
          <b v-else-if="row.self_assessment">自评 {{ fmtPoints(row.self_assessment.self_earned_points) }} / {{ fmtPoints(row.max_points) }}</b>
          <span v-else class="muted">待自评</span>
        </li>
      </ul>
    </section>
  </div>
</template>
