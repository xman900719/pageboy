<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  describeError,
  ApiError,
  type ApiClient,
  type AttemptResult,
  type NextItem,
  type ReferenceAnswer,
  type SelfAssessmentResult,
} from '../api'
import { fmtPoints, SCORING_LABELS, SELF_ASSESS_NOTE, splitOption } from '../copy'
import { KindBadge } from './Badges'
import AudioPlayer from './AudioPlayer.vue'
import Note from './Note.vue'
import { RichText } from '../rich'

type Phase = 'answering' | 'sending' | 'answered'

const props = defineProps<{
  client: ApiClient
  item: NextItem
  badge: string
}>()

const emit = defineEmits<{
  (e: 'submitted', result: AttemptResult): void
  (e: 'selfRecorded', record: SelfAssessmentResult): void
}>()

const answer = ref('')
const phase = ref<Phase>('answering')
const error = ref('')
const result = ref<AttemptResult | null>(null)
const reference = ref<ReferenceAnswer | null>(null)
const referenceError = ref('')
const selfPoints = ref('')
const selfPhase = ref<'open' | 'saving' | 'recorded'>('open')
const selfRecordedPoints = ref<number | null>(null)
const selfError = ref('')

const subjective = computed(
  () => result.value !== null && result.value.scoring_origin === 'ungraded_subjective'
)

function loadReference(attemptId: string) {
  referenceError.value = ''
  props.client
    .reference(attemptId)
    .then(data => {
      reference.value = data
    })
    .catch(e => {
      referenceError.value = describeError(e)
    })
}

async function submit() {
  if (!answer.value.trim()) {
    error.value = '请先作答。'
    return
  }
  error.value = ''
  phase.value = 'sending'
  try {
    const record = await props.client.submitAttempt({
      exposureId: props.item.exposure_id,
      answer: answer.value,
    })
    result.value = record
    phase.value = 'answered'
    emit('submitted', record)
    if (record.scoring_origin === 'ungraded_subjective') {
      loadReference(record.id)
    }
  } catch (e) {
    phase.value = 'answering'
    error.value = describeError(e)
  }
}

async function submitSelf() {
  if (result.value === null) return
  const max = result.value.max_points
  const value = Number(selfPoints.value)
  if (selfPoints.value === '' || Number.isNaN(value) || value < 0 || value > max) {
    selfError.value = `请输入 0 到 ${fmtPoints(max)} 之间的分数。`
    return
  }
  selfError.value = ''
  selfPhase.value = 'saving'
  try {
    const record = await props.client.selfAssessment(result.value.id, value)
    selfRecordedPoints.value = record.self_earned_points
    selfPhase.value = 'recorded'
    emit('selfRecorded', record)
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) {
      selfRecordedPoints.value = null
      selfPhase.value = 'recorded'
    } else {
      selfPhase.value = 'open'
      selfError.value = describeError(e)
    }
  }
}

const fullScore = computed(
  () =>
    result.value !== null &&
    result.value.earned_points !== null &&
    result.value.earned_points === result.value.max_points
)

const resultTone = computed(() =>
  result.value === null
    ? ''
    : result.value.earned_points === null
      ? 'pending'
      : fullScore.value
        ? 'full'
        : 'partial'
)
</script>

<template>
  <section class="card question-card" aria-label="题目">
    <div class="question-head">
      <span class="eyebrow">
        {{ badge }} · {{ item.knowledge_ids.join(' / ') }}
      </span>
      <KindBadge :kind="item.kind" />
    </div>

    <figure v-if="item.group_context" class="reading">
      <figcaption>阅读材料</figcaption>
      <blockquote>
        <RichText :text="item.group_context" />
      </blockquote>
    </figure>

    <p class="stem">
      <RichText :text="item.stem" />
    </p>

    <AudioPlayer
      v-if="item.media_attachment_id"
      :client="client"
      :attachment-id="item.media_attachment_id"
    />

    <div
      v-if="item.kind === 'single_choice' && item.options.length > 0"
      class="options"
      role="radiogroup"
      aria-label="选项"
    >
      <button
        v-for="option in item.options"
        :key="option"
        type="button"
        role="radio"
        :aria-checked="answer === splitOption(option).key"
        :disabled="phase !== 'answering'"
        :class="answer === splitOption(option).key ? 'option selected' : 'option'"
        @click="answer = splitOption(option).key"
      >
        <span class="option-key">{{ splitOption(option).key }}</span>
        <span>
          <RichText :text="splitOption(option).text" />
        </span>
      </button>
    </div>

    <label v-else-if="item.kind === 'subjective'" class="answer-field">
      解答
      <textarea
        rows="5"
        v-model="answer"
        :disabled="phase !== 'answering'"
        placeholder="写下完整的解答或论述过程…"
      />
    </label>

    <label v-else class="answer-field">
      答案
      <input
        v-model="answer"
        :disabled="phase !== 'answering'"
        :placeholder="item.kind === 'single_choice' ? '输入选项键，如 A' : '输入答案'"
      />
    </label>

    <p v-if="error" class="form-error">{{ error }}</p>

    <button
      v-if="phase !== 'answered'"
      type="button"
      class="primary"
      @click="submit"
      :disabled="phase === 'sending'"
    >
      {{ phase === 'sending' ? '提交中…' : '提交答案' }}
    </button>

    <div v-if="result" :class="['result', resultTone]">
      <b v-if="result.earned_points === null" class="result-line">暂未评分，等待自评</b>
      <b v-else class="result-line">
        本题得分 {{ fmtPoints(result.earned_points) }} / {{ fmtPoints(result.max_points) }}
      </b>
      <span class="muted">
        评分来源：{{ SCORING_LABELS[result.scoring_origin] ?? result.scoring_origin }}
      </span>
      <span
        v-if="item.purpose === 'evaluation' && result.evaluation_valid_unseen !== undefined && !subjective"
        class="muted"
      >
        {{
          result.evaluation_valid_unseen
            ? '符合独立验证条件（首次见题、独立完成），已计入阶段对比。'
            : '未计入独立验证（不满足首次见题且无提示），仅作复练记录。'
        }}
      </span>
      <span v-if="item.purpose === 'evaluation' && subjective" class="muted">
        已按独立验证条件记录；主观题不自动评分，完成后请对照参考答案自评。
      </span>
    </div>

    <div v-if="subjective" class="self-chain">
      <div class="reference">
        <span class="eyebrow">参考答案</span>
        <p v-if="reference">
          <RichText :text="reference.reference_answer" />
        </p>
        <p v-else-if="referenceError" class="muted">
          {{ referenceError }}
          <button
            type="button"
            class="ghost small"
            @click="result && loadReference(result.id)"
          >
            重试
          </button>
        </p>
        <p v-else class="muted">加载中…</p>
      </div>

      <Note v-if="selfPhase === 'recorded'">
        <template v-if="selfRecordedPoints !== null">
          自评已记录：{{ fmtPoints(selfRecordedPoints) }} / {{ fmtPoints(result?.max_points ?? item.max_points) }}。
        </template>
        <template v-else>
          自评已记录过，不能重复提交。
        </template>
        {{ SELF_ASSESS_NOTE }}
      </Note>

      <div v-else class="self-form">
        <label>
          对照参考答案，给自己评分（0 – {{ fmtPoints(result?.max_points ?? item.max_points) }}）
          <input
            type="number"
            inputmode="decimal"
            :min="0"
            :max="result?.max_points ?? item.max_points"
            v-model="selfPoints"
          />
        </label>
        <button
          type="button"
          class="primary"
          @click="submitSelf"
          :disabled="selfPhase === 'saving'"
        >
          {{ selfPhase === 'saving' ? '提交中…' : '提交自评' }}
        </button>
        <p v-if="selfError" class="form-error">{{ selfError }}</p>
        <p class="muted">{{ SELF_ASSESS_NOTE }}</p>
      </div>
    </div>

    <div v-if="$slots.footer" class="question-foot">
      <slot name="footer" />
    </div>
  </section>
</template>
