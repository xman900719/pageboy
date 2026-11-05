<script setup lang="ts">
import { ref } from 'vue'
import {
  describeError,
  type ApiClient,
  type AttachmentOut,
  type Kind,
  type QuestionDraftInput,
} from '../../api'
import { CONFIRM_CHECK_LABEL, KIND_LABELS, excerpt } from '../../copy'
import type { NoticeTone } from '../../components/Notice.vue'

type Notify = (text: string, tone?: NoticeTone) => void
const KINDS: Kind[] = ['single_choice', 'short_answer', 'subjective']

function letter(i: number): string {
  return String.fromCharCode(65 + i)
}

const props = defineProps<{
  client: ApiClient
  attachment: AttachmentOut
  notify: Notify
}>()

const emit = defineEmits<{
  (e: 'confirmed'): void
}>()

const entries = ref<QuestionDraftInput[]>([])
const stem = ref('')
const kind = ref<Kind>('single_choice')
const options = ref<string[]>(['', ''])
const correctIdx = ref(0)
const answer = ref('')
const knowledgeInput = ref('')
const maxPoints = ref('3')
const groupContext = ref('')
const mediaId = ref(
  props.attachment.media_type.startsWith('audio/') ? props.attachment.id : ''
)
const checked = ref(false)
const error = ref('')
const busy = ref(false)

function resetEntry() {
  stem.value = ''
  options.value = ['', '']
  correctIdx.value = 0
  answer.value = ''
}

function switchKind(next: Kind) {
  kind.value = next
  resetEntry()
}

function addEntry() {
  const cleanStem = stem.value.trim()
  if (cleanStem === '') {
    error.value = '请填写题干。'
    return
  }
  let draftOptions: string[] = []
  let correctAnswer = ''
  if (kind.value === 'single_choice') {
    const texts = options.value.map(o => o.trim())
    if (texts.filter(t => t !== '').length < 2) {
      error.value = '单选题至少需要 2 个非空选项。'
      return
    }
    if (correctIdx.value < 0 || correctIdx.value >= texts.length || texts[correctIdx.value] === '') {
      error.value = '请为正确选项填写内容。'
      return
    }
    draftOptions = texts.map((t, i) => `${letter(i)}. ${t}`)
    correctAnswer = letter(correctIdx.value)
  } else {
    correctAnswer = answer.value.trim()
    if (correctAnswer === '') {
      error.value = kind.value === 'subjective' ? '请填写参考答案文本（供自评对照）。' : '请填写答案。'
      return
    }
  }
  const knowledgeIds = knowledgeInput.value.split(/[,，、\s]+/).filter(Boolean)
  if (knowledgeIds.length < 1) {
    error.value = '知识点 ID 至少填 1 个（逗号或空格分隔）。'
    return
  }
  const points = Number(maxPoints.value)
  if (Number.isNaN(points) || points <= 0 || points > 100) {
    error.value = '分值须大于 0 且不超过 100。'
    return
  }
  const context = groupContext.value.trim()
  if (context.length > 20000) {
    error.value = '组内材料不能超过 20000 字。'
    return
  }

  entries.value.push({
    source_document_id: props.attachment.source_document_id,
    stem: cleanStem,
    kind: kind.value,
    options: draftOptions,
    correct_answer: correctAnswer,
    knowledge_ids: knowledgeIds,
    max_points: points,
    group_context: context === '' ? null : context,
    media_attachment_id: mediaId.value.trim() === '' ? null : mediaId.value.trim(),
  })
  error.value = ''
  resetEntry()
}

async function confirm() {
  if (entries.value.length === 0) {
    error.value = '请先录入至少 1 道题。'
    return
  }
  if (!checked.value) {
    error.value = '请先勾选「我已逐题人工核对」。'
    return
  }
  busy.value = true
  error.value = ''
  try {
    await props.client.confirmImport(props.attachment.id, entries.value)
    props.notify(`已确认导入 ${entries.value.length} 题，草稿待人工审核。`, 'success')
    entries.value = []
    checked.value = false
    emit('confirmed')
  } catch (e) {
    error.value = describeError(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="confirm-import">
    <h3 class="sub-head">逐题人工录入（导入为「{{ attachment.filename }}」）</h3>
    <div class="admin-grid">
      <label class="wide">
        题干
        <textarea
          rows="2"
          v-model="stem"
          placeholder="虚构测试数据：计算 12 + 15 的结果。"
        />
      </label>
      <label>
        题型
        <select :value="kind" @change="switchKind(($event.target as HTMLSelectElement).value as Kind)">
          <option v-for="id in KINDS" :key="id" :value="id">
            {{ KIND_LABELS[id] }}
          </option>
        </select>
      </label>
      <label>
        分值（大于 0，不超过 100）
        <input
          type="number"
          min="0"
          max="100"
          step="0.5"
          v-model="maxPoints"
        />
      </label>
      <div v-if="kind === 'single_choice'" class="wide" role="group" aria-label="选项与正确答案">
        <span class="field-label">选项（至少 2 个非空，自动编号 A / B / C…）</span>
        <div class="option-rows">
          <div v-for="(_, i) in options" :key="i" class="option-row">
            <span class="option-key" aria-hidden="true">
              {{ letter(i) }}
            </span>
            <input
              v-model="options[i]"
              :aria-label="`选项 ${letter(i)} 内容`"
              :placeholder="`虚构测试数据：选项 ${letter(i)} 内容`"
            />
            <button
              v-if="options.length > 2"
              type="button"
              class="ghost small"
              :aria-label="`删除选项 ${letter(i)}`"
              @click="options.splice(i, 1); correctIdx = 0"
            >
              删除
            </button>
          </div>
        </div>
        <button
          type="button"
          class="ghost small"
          @click="options.push('')"
        >
          加一个选项
        </button>
        <label>
          正确选项
          <select v-model="correctIdx">
            <option v-for="(opt, i) in options" :key="i" :value="i">
              {{ letter(i) }}
              {{ opt.trim() === '' ? '（未填写）' : ` · ${excerpt(opt, 16)}` }}
            </option>
          </select>
        </label>
      </div>
      <label v-else class="wide">
        {{ kind === 'subjective' ? '参考答案（文本，供自评对照）' : '答案（已审核后用于自动比对）' }}
        <textarea
          rows="2"
          v-model="answer"
          placeholder="虚构测试数据：参考答案文本"
        />
      </label>
      <label class="wide">
        知识点 ID（至少 1 个，逗号或空格分隔）
        <input
          v-model="knowledgeInput"
          placeholder="虚构测试数据：math.gap, math.alg"
        />
      </label>
      <label class="wide">
        组内材料（可选，与同组题共用，如阅读材料，≤20000 字）
        <textarea
          rows="2"
          v-model="groupContext"
          placeholder="虚构测试数据：阅读材料文本"
        />
      </label>
      <label class="wide">
        媒体附件 ID（可选：听力题填音频附件 id，须属于本来源）
        <input
          class="mono-input"
          v-model="mediaId"
          placeholder="留空表示无媒体"
          autocomplete="off"
        />
      </label>
    </div>
    <p v-if="error" class="form-error">{{ error }}</p>
    <div class="confirm-import-actions">
      <button type="button" class="ghost" @click="addEntry">
        加入待导入列表
      </button>
      <span v-if="entries.length > 0" class="muted tiny">
        已录入 {{ entries.length }} 题
      </span>
    </div>

    <template v-if="entries.length > 0">
      <ul class="entry-list">
        <li v-for="(entry, i) in entries" :key="i" class="entry-row">
          <span class="muted tiny">#{{ i + 1 }}</span>
          <span class="entry-stem">{{ excerpt(entry.stem, 48) }}</span>
          <span class="badge kind">{{ KIND_LABELS[entry.kind] }}</span>
          <span class="muted tiny">{{ entry.max_points }} 分</span>
          <button
            type="button"
            class="ghost small"
            :aria-label="`移除第 ${i + 1} 题`"
            @click="entries.splice(i, 1)"
          >
            移除
          </button>
        </li>
      </ul>
      <div class="confirm-box">
        <input
          :id="`confirm-check-${attachment.id}`"
          type="checkbox"
          v-model="checked"
        />
        <label :for="`confirm-check-${attachment.id}`">
          {{ CONFIRM_CHECK_LABEL }}（勾选后才能确认导入）
        </label>
      </div>
      <button
        type="button"
        class="primary"
        @click="confirm"
        :disabled="busy || !checked"
      >
        {{ busy ? '导入中…' : `确认导入 ${entries.length} 题` }}
      </button>
    </template>
  </div>
</template>
