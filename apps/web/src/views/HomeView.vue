<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
  ApiError,
  describeError,
  type ApiClient,
  type Plan,
  type ProfileEntry,
  type Subject,
  type Validation,
} from '../api'
import { GOAL_NOTE, pct, type ViewId } from '../copy'
import Note from '../components/Note.vue'
import PlanStepList from '../components/PlanStepList.vue'
import ValidationPanel from '../components/ValidationPanel.vue'

type Notify = (text: string, tone?: 'info' | 'success' | 'caution' | 'error') => void
type PlanState = { status: 'loading' | 'goal' | 'error' | 'ok'; plan: Plan | null; errorText: string }

const props = defineProps<{
  client: ApiClient
  subject: Subject
  notify: Notify
}>()

const emit = defineEmits<{
  (e: 'goView', view: ViewId): void
}>()

const planState = ref<PlanState>({ status: 'loading', plan: null, errorText: '' })
const profiles = ref<Record<string, ProfileEntry>>({})
const validation = ref<Validation | null>(null)
const loading = ref(true)
const goalOpen = ref(false)
const target = ref(props.subject === 'physics' ? 70 : 90)
const minutes = ref(15)
const savingGoal = ref(false)

const maxPoints = computed(() => (props.subject === 'physics' ? 80 : 100))

async function refresh() {
  loading.value = true
  const [planRes, profileRes, validationRes] = await Promise.allSettled([
    props.client.plan(props.subject),
    props.client.profile(props.subject),
    props.client.validation(props.subject),
  ])
  if (planRes.status === 'fulfilled') {
    planState.value = { status: 'ok', plan: planRes.value, errorText: '' }
  } else {
    const goalRequired = planRes.reason instanceof ApiError && planRes.reason.status === 409
    planState.value = {
      status: goalRequired ? 'goal' : 'error',
      plan: null,
      errorText: describeError(planRes.reason),
    }
  }
  if (profileRes.status === 'fulfilled') {
    profiles.value = Object.fromEntries(
      profileRes.value.knowledge.map(entry => [entry.topic, entry])
    )
  }
  if (validationRes.status === 'fulfilled') validation.value = validationRes.value
  loading.value = false
}

watch(
  [() => props.client, () => props.subject],
  () => {
    target.value = props.subject === 'physics' ? 70 : 90
    void refresh()
  },
  { immediate: true }
)

async function saveGoal() {
  savingGoal.value = true
  try {
    const saved = await props.client.setGoal({
      subject: props.subject,
      targetPoints: Number(target.value),
      maxPoints: maxPoints.value,
      minutesPerDay: Number(minutes.value),
    })
    props.notify(`目标已保存（第 ${saved.version} 版）。${GOAL_NOTE}`, 'success')
    goalOpen.value = false
    await refresh()
  } catch (e) {
    props.notify(describeError(e), 'error')
  } finally {
    savingGoal.value = false
  }
}
</script>

<template>
  <div class="home-grid">
    <section class="card" aria-label="目标与学习计划">
      <div class="card-head">
        <h2>目标与学习计划</h2>
        <button
          v-if="planState.plan"
          type="button"
          class="ghost small"
          @click="goalOpen = !goalOpen"
        >
          {{ goalOpen ? '收起目标表单' : '修改目标' }}
        </button>
      </div>

      <div v-if="planState.plan" class="goal-summary">
        <span class="goal-stat">目标版本 v{{ planState.plan.goal_version }}</span>
        <span class="goal-stat">每天 {{ planState.plan.minutes_per_day }} 分钟</span>
        <span class="goal-stat">规划阈值 {{ pct(planState.plan.planning_threshold) }}（未校准）</span>
      </div>
      <Note v-else-if="planState.status === 'goal'" tone="caution">
        还没有设定目标：设定目标后才会生成学习计划。
      </Note>
      <Note v-else-if="planState.status === 'error'" tone="caution">
        学习计划加载失败：{{ planState.errorText }}
      </Note>
      <p v-else class="muted">学习计划加载中…</p>

      <div v-if="goalOpen || planState.status === 'goal'" class="goal-form">
        <div class="goal-fields">
          <label>
            科目目标分（满分 {{ maxPoints }}）
            <input type="number" :min="0" :max="maxPoints" v-model.number="target" />
          </label>
          <label>
            每天练习分钟数
            <input type="number" :min="5" :max="240" v-model.number="minutes" />
          </label>
        </div>
        <button type="button" class="primary" @click="saveGoal" :disabled="savingGoal">
          {{ savingGoal ? '保存中…' : '保存目标' }}
        </button>
        <p class="muted">
          英语听说和物理实验部分暂未覆盖完整训练；规划阈值按目标比例取 70% / 80% / 90%，是未校准的规划假设。{{ GOAL_NOTE }}
        </p>
      </div>

      <template v-if="planState.plan">
        <p class="muted plan-meta">
          计划模型：{{ planState.plan.model_version }} · 未校准规则推荐，不代表分数。
        </p>
        <PlanStepList
          :steps="planState.plan.steps"
          :threshold="planState.plan.planning_threshold"
          :profiles="profiles"
          @goPractice="emit('goView', 'practice')"
          @goDiagnosis="emit('goView', 'diagnosis')"
        />
        <p class="muted tiny disclaimer">{{ planState.plan.disclaimer }}</p>
      </template>
    </section>

    <div class="home-side">
      <section class="card" aria-label="阶段对比摘要">
        <div class="card-head">
          <h2>阶段对比</h2>
          <button type="button" class="ghost small" @click="emit('goView', 'diagnosis')">
            查看详情
          </button>
        </div>
        <ValidationPanel v-if="validation" :validation="validation" />
        <p v-else class="muted">{{ loading ? '加载中…' : '阶段对比加载失败。' }}</p>
      </section>

      <Note title="这里的数字是什么">
        「观察作答率」只统计独立完成、首次见题、已审核答案自动比对的题目，样本很小；它是未校准的观察值，不是能力值，也不推算中考成绩。证据不足时只显示原因，不显示 0 分。
      </Note>
    </div>
  </div>
</template>
