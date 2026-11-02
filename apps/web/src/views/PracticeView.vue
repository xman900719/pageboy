<script setup lang="ts">
import { ref, watch } from 'vue'
import {
  ApiError,
  describeError,
  type ApiClient,
  type AttemptResult,
  type AttemptRow,
  type NextItem,
  type PlanStep,
  type SelfAssessmentResult,
  type Subject,
} from '../api'
import { excerpt, fmtPoints, KIND_LABELS, SCORING_LABELS, shortTime } from '../copy'
import QuestionCard from '../components/QuestionCard.vue'
import type { NoticeTone } from '../components/Notice.vue'
import { getKnowledgeLabel } from '../config/knowledge'

type Notify = (text: string, tone?: NoticeTone) => void
type SessionEntry = { n: number; excerptText: string; outcome: string; tone: 'good' | 'mid' | 'wait' }

const props = defineProps<{
  client: ApiClient
  subject: Subject
  notify: Notify
}>()

const item = ref<NextItem | null>(null)
const busy = ref(false)
const session = ref<SessionEntry[]>([])
const history = ref<AttemptRow[] | null>(null)
const steps = ref<PlanStep[] | null>(null)
const knowledgeId = ref('')

async function refreshHistory() {
  try {
    history.value = await props.client.attempts(props.subject)
  } catch {
    history.value = null
  }
}

watch(
  [() => props.client, () => props.subject],
  () => {
    void refreshHistory()
    props.client
      .plan(props.subject)
      .then(plan => {
        steps.value = plan.steps
      })
      .catch(() => {
        steps.value = null
      })
  },
  { immediate: true }
)

async function start() {
  busy.value = true
  try {
    item.value = await props.client.nextItem(props.subject, 'training', knowledgeId.value || undefined)
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) {
      props.notify('暂无可练的题目：请先在管理端发布已审核题目。', 'caution')
    } else {
      props.notify(describeError(e), 'error')
    }
  } finally {
    busy.value = false
  }
}

function onSubmitted(result: AttemptResult) {
  if (!item.value) return
  const outcome =
    result.earned_points === null ? '待自评' : `${fmtPoints(result.earned_points)} / ${fmtPoints(result.max_points)}`
  const tone: SessionEntry['tone'] =
    result.earned_points === null
      ? 'wait'
      : result.earned_points === result.max_points
        ? 'good'
        : 'mid'
  session.value.push({
    n: session.value.length + 1,
    excerptText: excerpt(item.value.stem),
    outcome,
    tone,
  })
  void refreshHistory()
}

function onSelfRecorded(_record: SelfAssessmentResult) {
  void refreshHistory()
}
</script>

<template>
  <section class="card" aria-label="练习控制">
    <div class="card-head">
      <h2>专项训练 · 复练</h2>
      <span v-if="session.length > 0" class="muted">本次已练 {{ session.length }} 题</span>
    </div>
    <p class="muted">
      复练会在全部已发布题中轮换取题（包括做过的题），连续取题就能看到不同题目；每次取题都会记一次曝光。
    </p>
    <div class="controls">
      <button type="button" class="primary" @click="start" :disabled="busy">
        {{ busy ? '取题中…' : item ? '换一题（轮换取题）' : '开始练习' }}
      </button>
      <label class="inline-select">
        按知识点
        <select v-if="steps" v-model="knowledgeId">
          <option value="">全部知识点</option>
          <option v-for="step in steps" :key="step.knowledge_id" :value="step.knowledge_id">
            {{ getKnowledgeLabel(step.knowledge_id) }}
          </option>
        </select>
        <select v-else disabled>
          <option>全部知识点</option>
        </select>
      </label>
    </div>
    <ol v-if="session.length > 0" class="session-log">
      <li v-for="entry in session" :key="entry.n">
        <b>#{{ entry.n }}</b>
        <span class="session-stem">{{ entry.excerptText }}</span>
        <span :class="['chip', entry.tone]">{{ entry.outcome }}</span>
      </li>
    </ol>
  </section>

  <QuestionCard
    v-if="item"
    :key="item.exposure_id"
    :client="client"
    :item="item"
    badge="专项训练"
    @submitted="onSubmitted"
    @selfRecorded="onSelfRecorded"
  >
    <template #footer>
      <button type="button" class="primary" @click="start" :disabled="busy">
        {{ busy ? '取题中…' : '下一题（轮换取题）' }}
      </button>
    </template>
  </QuestionCard>

  <section class="card" aria-label="作答溯源记录">
    <div class="card-head">
      <h2>作答溯源记录</h2>
      <button type="button" class="ghost small" @click="refreshHistory">
        刷新
      </button>
    </div>
    <p v-if="history === null" class="muted">作答记录加载中…</p>
    <p v-else-if="history.length === 0" class="muted">还没有作答记录。</p>
    <div v-else class="table-scroll">
      <table class="trace">
        <thead>
          <tr>
            <th>时间</th>
            <th>类型</th>
            <th>我的作答</th>
            <th>结果</th>
            <th>评分来源</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in history.slice(0, 12)" :key="row.id">
            <td>{{ shortTime(row.created_at) }}</td>
            <td>
              {{ KIND_LABELS[row.kind] }}
              {{ row.purpose === 'evaluation' ? ' · 诊断' : '' }}
            </td>
            <td class="answer-cell">
              {{ row.answer.trim() === '' ? '—' : excerpt(row.answer, 40) }}
            </td>
            <td>
              {{
                row.earned_points === null
                  ? row.self_assessment
                    ? `自评 ${fmtPoints(row.self_assessment.self_earned_points)} / ${fmtPoints(row.self_assessment.max_points)}`
                    : '待自评'
                  : `${fmtPoints(row.earned_points)} / ${fmtPoints(row.max_points)}`
              }}
            </td>
            <td class="muted">
              {{ SCORING_LABELS[row.scoring_origin] ?? row.scoring_origin }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="muted tiny">自评记录与自动判分并列保存，只作溯源对照，不会进入客观证据。</p>
  </section>
</template>
