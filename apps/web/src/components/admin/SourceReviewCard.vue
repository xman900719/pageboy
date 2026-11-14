<script setup lang="ts">
import { ref } from 'vue'
import {
  describeError,
  SUBJECT_LABELS,
  type ApiClient,
  type RightsStatus,
  type SourceDetail,
} from '../../api'
import { REVIEW_CHECK_LABEL, RIGHTS_STATUS_LABELS, shortTime } from '../../copy'

type Notify = (text: string, tone?: 'info' | 'success' | 'caution' | 'error') => void

const props = defineProps<{
  client: ApiClient
  source: SourceDetail
  notify: Notify
}>()

const emit = defineEmits<{
  (e: 'reviewed'): void
}>()

const latest = props.source.reviews[props.source.reviews.length - 1]?.metadata ?? null
const examYear = ref(String(latest?.exam_year ?? new Date().getFullYear()))
const sourceUrl = ref(latest?.source_url ?? '')
const acquiredAt = ref(latest?.acquired_at ?? new Date().toISOString().slice(0, 10))
const rightsStatus = ref<RightsStatus>(latest?.rights_status ?? props.source.source.rights_status)
const rightsBasis = ref(latest?.rights_basis ?? '')
const applicable = ref(latest?.applicable ?? true)
const applicabilityNote = ref(latest?.applicability_note ?? '')
const checked = ref(false)
const busy = ref(false)
const error = ref('')

async function submit() {
  const year = Number(examYear.value)
  if (!Number.isInteger(year) || year < 1990 || year > 2100) {
    error.value = '考试年份须为 1990–2100 之间的整数。'
    return
  }
  if (!sourceUrl.value.trim().startsWith('https://')) {
    error.value = '来源链接必须以 https:// 开头。'
    return
  }
  const basis = rightsBasis.value.trim()
  if (basis === '' || basis.length > 2000) {
    error.value = '版权依据必填，长度 1–2000 字。'
    return
  }
  const note = applicabilityNote.value.trim()
  if (note === '' || note.length > 2000) {
    error.value = '适用性说明必填，长度 1–2000 字。'
    return
  }
  if (!checked.value) {
    error.value = '请先勾选人工核查确认。'
    return
  }
  busy.value = true
  error.value = ''
  try {
    await props.client.reviewSource(props.source.id, {
      exam_year: year,
      source_url: sourceUrl.value.trim(),
      acquired_at: acquiredAt.value,
      rights_status: rightsStatus.value,
      rights_basis: basis,
      applicable: applicable.value,
      applicability_note: note,
      reviewed_by_human: true,
    })
    props.notify(
      applicable.value
        ? '来源人工审核已记录，题源标记为已审核。'
        : '审核已记录：适用性为「不适用」，题源仍视为未审核，题目无法发布。',
      applicable.value ? 'success' : 'caution'
    )
    emit('reviewed')
  } catch (e) {
    error.value = describeError(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="card" aria-label="来源人工审核">
    <div class="card-head">
      <h2>来源人工审核</h2>
      <span :class="['chip', source.source.verified ? 'good' : 'wait']">
        {{ source.source.verified ? '已人工审核' : '未审核' }}
      </span>
    </div>
    <p class="muted">
      题源「{{ source.source.title }}」 · {{ SUBJECT_LABELS[source.source.subject] }} · 版权状态：
      {{ RIGHTS_STATUS_LABELS[source.source.rights_status] }}
      <template v-if="source.reviews.length > 0">
        · 已有 {{ source.reviews.length }} 次审核记录（最近 {{ shortTime(source.reviews[source.reviews.length - 1].created_at) }}）
      </template>
    </p>
    <form class="admin-form" @submit.prevent="submit">
      <div class="admin-grid">
        <label>
          考试年份（1990–2100）
          <input
            type="number"
            :min="1990"
            :max="2100"
            v-model="examYear"
            placeholder="例如：2025"
          />
        </label>
        <label>
          来源链接（必须 https）
          <input
            v-model="sourceUrl"
            placeholder="https://example.org/exam.pdf"
            autocomplete="off"
          />
        </label>
        <label>
          获取日期
          <input type="date" v-model="acquiredAt" />
        </label>
        <label>
          版权状态
          <select v-model="rightsStatus">
            <option
              v-for="id in (Object.keys(RIGHTS_STATUS_LABELS) as RightsStatus[])"
              :key="id"
              :value="id"
            >
              {{ RIGHTS_STATUS_LABELS[id] }}
            </option>
          </select>
        </label>
        <label class="wide">
          版权依据（1–2000 字，必填）
          <textarea
            rows="2"
            maxlength="2000"
            v-model="rightsBasis"
            placeholder="例如：北京市初中学业水平考试官方公开真题原卷，仅个人学习自用"
          />
        </label>
        <div class="wide confirm-box">
          <input
            :id="`applicable-${source.id}`"
            type="checkbox"
            v-model="applicable"
          />
          <label :for="`applicable-${source.id}`">
            来源适用：内容可用于本工具的练习与诊断取题（不适用则题源保持未审核）
          </label>
        </div>
        <label class="wide">
          适用性说明（1–2000 字，必填）
          <textarea
            rows="2"
            maxlength="2000"
            v-model="applicabilityNote"
            placeholder="例如：覆盖北京市中考数学核心考点，符合 2022 年版课标学业要求"
          />
        </label>
      </div>
      <div class="confirm-box">
        <input
          :id="`review-check-${source.id}`"
          type="checkbox"
          v-model="checked"
        />
        <label :for="`review-check-${source.id}`">
          {{ REVIEW_CHECK_LABEL }}（勾选后才能提交）
        </label>
      </div>
      <p v-if="error" class="form-error">{{ error }}</p>
      <button type="submit" class="primary" :disabled="busy || !checked">
        {{ busy ? '提交中…' : '提交人工审核' }}
      </button>
    </form>
  </section>
</template>
