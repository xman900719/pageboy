<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
  ApiError,
  describeError,
  type ApiClient,
  type AttemptResult,
  type NextItem,
  type PlanStep,
  type ProfileEntry,
  type Subject,
  type Validation,
} from '../api'
import { DISCIPLINE_TEXT, DISCIPLINE_TITLE, GAP_LABELS } from '../copy'
import QuestionCard from '../components/QuestionCard.vue'
import Note from '../components/Note.vue'
import PlanStepList from '../components/PlanStepList.vue'
import ValidationPanel from '../components/ValidationPanel.vue'
import type { NoticeTone } from '../components/Notice.vue'

type Notify = (text: string, tone?: NoticeTone) => void
type Transition = { topic: string; from: string; to: string }

const props = defineProps<{
  client: ApiClient
  subject: Subject
  notify: Notify
}>()

const emit = defineEmits<{
  (e: 'goHome'): void
}>()

const item = ref<NextItem | null>(null)
const result = ref<AttemptResult | null>(null)
const busy = ref(false)
const validation = ref<Validation | null>(null)
const validationLoading = ref(true)
const beforeSteps = ref<PlanStep[] | null>(null)
const planSteps = ref<PlanStep[] | null>(null)
const planThreshold = ref(0)
const planStatus = ref<'loading' | 'goal' | 'error' | 'ok'>('loading')
const profiles = ref<Record<string, ProfileEntry>>({})
const refreshed = ref(false)
const resumed = ref(false)

async function loadPlan(): Promise<PlanStep[] | null> {
  try {
    const plan = await props.client.plan(props.subject)
    planSteps.value = plan.steps
    planThreshold.value = plan.planning_threshold
    planStatus.value = 'ok'
    return plan.steps
  } catch (e) {
    planStatus.value = e instanceof ApiError && e.status === 409 ? 'goal' : 'error'
    return null
  }
}

async function loadValidation() {
  validationLoading.value = true
  try {
    validation.value = await props.client.validation(props.subject)
  } catch {
    validation.value = null
  } finally {
    validationLoading.value = false
  }
}

watch(
  [() => props.client, () => props.subject],
  () => {
    refreshed.value = false
    item.value = null
    result.value = null
    resumed.value = false

    // ST-018：刷新/重开/切后台后恢复最近未作答曝光，未见题不因会话丢失而空烧。
    props.client
      .resume(props.subject)
      .then(r => {
        if (r.item !== null) {
          item.value = r.item
          resumed.value = true
        }
      })
      .catch(() => {
        resumed.value = false
      })

    void loadPlan().then(steps => {
      if (steps !== null) beforeSteps.value = steps
    })
    void loadValidation()

    props.client
      .profile(props.subject)
      .then(profile => {
        profiles.value = Object.fromEntries(
          profile.knowledge.map(entry => [entry.topic, entry])
        )
      })
      .catch(() => {
        profiles.value = {}
      })
  },
  { immediate: true }
)

const transitions = computed<Transition[]>(() => {
  if (beforeSteps.value === null || planSteps.value === null) return []
  return planSteps.value.flatMap(after => {
    const before = beforeSteps.value!.find(step => step.topic === after.topic)
    if (before === undefined || before.gap_type === after.gap_type) return []
    return [{ topic: after.topic, from: GAP_LABELS[before.gap_type], to: GAP_LABELS[after.gap_type] }]
  })
})

async function claim() {
  busy.value = true
  try {
    const next = await props.client.nextItem(props.subject, 'evaluation')
    item.value = next
    result.value = null
    refreshed.value = false
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) {
      props.notify('暂无可诊断的未见题：当前科目已发布的题都已曝光，可先回练习区复练。', 'caution')
    } else {
      props.notify(describeError(e), 'error')
    }
  } finally {
    busy.value = false
  }
}

async function onSubmitted(submitted: AttemptResult) {
  result.value = submitted
  props.notify(
    submitted.evaluation_valid_unseen
      ? '作答已提交，正在刷新计划与阶段对比。'
      : '作答已提交（未计入独立验证），正在刷新计划。',
    submitted.evaluation_valid_unseen ? 'success' : 'caution'
  )
  const [planRes, validationRes] = await Promise.allSettled([loadPlan(), loadValidation()])
  if (planRes.status === 'fulfilled' && planRes.value !== null) refreshed.value = true
  void validationRes
}
</script>

<template>
  <Note tone="discipline" :title="DISCIPLINE_TITLE">
    {{ DISCIPLINE_TEXT }}
  </Note>

  <section class="card" aria-label="领取未见题">
    <div class="card-head">
      <h2>领取未见题</h2>
      <span v-if="item" class="muted">已领取本题，作答后自动刷新计划</span>
    </div>
    <p class="muted">
      「未见题」指你从未曝光过的题。提交作答后，下方会自动刷新学习计划与阶段对比，展示知识点状态变化。
    </p>
    <Note v-if="resumed" tone="discipline">
      已恢复上次未完成作答的题目：刷新、重开或切换应用都不会让已领取的未见题作废。
    </Note>
    <button
      type="button"
      class="primary"
      @click="claim"
      :disabled="busy || item !== null"
    >
      {{ busy ? '领取中…' : item ? '已领取，请在本页作答' : '领取未见题诊断' }}
    </button>
  </section>

  <Note v-if="planStatus === 'error'" tone="caution">
    学习计划加载失败：诊断后将无法展示计划刷新结果，可稍后重试。
  </Note>

  <QuestionCard
    v-if="item"
    :key="item.exposure_id"
    :client="client"
    :item="item"
    badge="阶段诊断 · 未见题"
    @submitted="onSubmitted"
  >
    <template v-if="result" #footer>
      <button
        type="button"
        class="primary"
        @click="item = null; result = null; resumed = false"
      >
        完成本题
      </button>
    </template>
  </QuestionCard>

  <section v-if="refreshed" class="card" aria-label="计划刷新结果">
    <h2>计划已刷新</h2>
    <template v-if="transitions.length > 0">
      <p class="muted">本次诊断后，考点状态发生了以下变化：</p>
      <ul class="transitions">
        <li v-for="transition in transitions" :key="transition.topic">
          <span class="step-topic">{{ transition.topic }}</span>
          <span>
            {{ transition.from }} → <b>{{ transition.to }}</b>
          </span>
        </li>
      </ul>
    </template>
    <p v-else class="muted">
      各考点状态暂无变化；再积累一些独立未见题作答后，状态才会推进。
    </p>
    <template v-if="planSteps !== null">
      <h3 class="sub-head">刷新后的考点能力状态</h3>
      <PlanStepList :steps="planSteps" :threshold="planThreshold" :profiles="profiles" />
    </template>
  </section>

  <section class="card" aria-label="阶段对比判决">
    <div class="card-head">
      <h2>阶段对比 · 基线 → 复测</h2>
      <button type="button" class="ghost small" @click="loadValidation">
        刷新
      </button>
    </div>
    <ValidationPanel v-if="validation" :validation="validation" />
    <p v-else class="muted">{{ validationLoading ? '加载中…' : '阶段对比加载失败。' }}</p>
  </section>

  <Note v-if="planStatus === 'goal'" tone="caution" title="还没有目标">
    设定目标后，诊断结果才能刷新学习计划。
    <button type="button" class="ghost small" @click="emit('goHome')">
      去首页设定目标
    </button>
  </Note>
</template>
