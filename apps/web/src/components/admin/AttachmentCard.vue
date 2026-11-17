<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  describeError,
  type ApiClient,
  type AttachmentOut,
  type AttachmentStatus,
  type SourceDetail,
} from '../../api'
import { ATTACHMENT_STATUS_LABELS, REUPLOAD_RESET_NOTE, fmtBytes, shortTime } from '../../copy'
import { getMediaTypeLabel } from '../../config/knowledge'
import HelpBubble from '../../components/HelpBubble.vue'
import type { NoticeTone } from '../../components/Notice.vue'
import ConfirmImportForm from './ConfirmImportForm.vue'
import StepFlowWorkspace from './StepFlowWorkspace.vue'
import type { StepDefinition } from './stepFlow'

type Notify = (text: string, tone?: NoticeTone) => void
type AttachmentStepId = 'queue' | 'import'

const MAX_BYTES = 25 * 1024 * 1024
const DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
const ALLOWED_TYPES = new Set(['application/pdf', DOCX_MIME, 'image/png', 'image/jpeg', 'audio/mpeg', 'audio/mp4'])
const EXT_TYPES: Record<string, string> = {
  pdf: 'application/pdf',
  docx: DOCX_MIME,
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  mp3: 'audio/mpeg',
  m4a: 'audio/mp4',
}
const STATUS_CHIP: Record<AttachmentStatus, 'wait' | 'mid' | 'good'> = {
  uploaded: 'wait',
  parsed: 'mid',
  needs_manual_input: 'wait',
  confirmed: 'good',
}

function pickMime(file: File): string | null {
  if (ALLOWED_TYPES.has(file.type)) return file.type
  const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
  return EXT_TYPES[ext] ?? null
}

const props = defineProps<{
  client: ApiClient
  source: SourceDetail
  initialKnowledgeId?: string
  notify: Notify
}>()

const emit = defineEmits<{
  (e: 'changed'): void
  (e: 'go-versions'): void
}>()

const attStep = ref<AttachmentStepId>('queue')
const file = ref<File | null>(null)
const uploading = ref(false)
const uploadError = ref('')
const parseBusyId = ref<string | null>(null)
const confirmingId = ref<string | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)

const readyToImportAttachments = computed(() =>
  props.source.attachments.filter(
    a => a.status === 'parsed' || a.status === 'needs_manual_input',
  ),
)

const hasConfirmedAttachments = computed(() =>
  props.source.attachments.some(a => a.status === 'confirmed'),
)

const confirmingAttachment = computed(
  () =>
    readyToImportAttachments.value.find(a => a.id === confirmingId.value) ??
    readyToImportAttachments.value[0] ??
    null,
)

watch(readyToImportAttachments, list => {
  if (confirmingId.value && !list.some(a => a.id === confirmingId.value)) {
    confirmingId.value = list[0]?.id ?? null
  }
})

const steps = computed<StepDefinition[]>(() => [
  {
    id: 'queue',
    title: '1. 上传原始附件与解析',
    subtitle: props.source.attachments.length > 0 ? `已上传 ${props.source.attachments.length} 份` : '上传原卷后点击解析',
    badge: `${props.source.attachments.length} 份`,
    done: readyToImportAttachments.value.length > 0 || hasConfirmedAttachments.value,
    prereqMet: true,
  },
  {
    id: 'import',
    title: '2. 逐题人工录入工作台',
    subtitle:
      readyToImportAttachments.value.length > 0
        ? `待录入 ${readyToImportAttachments.value.length} 份`
        : '须先解析至少 1 份附件',
    badge: readyToImportAttachments.value.length > 0 ? `${readyToImportAttachments.value.length} 待录` : undefined,
    badgeTone: readyToImportAttachments.value.length > 0 ? 'wait' : 'subtle',
    done: hasConfirmedAttachments.value && readyToImportAttachments.value.length === 0,
    prereqMet: readyToImportAttachments.value.length > 0,
    lockReason: '请先在第 1 步上传原始附件并点击「解析」，提取对照文本后才可逐题录入。',
  },
])

function openImportFor(attId: string) {
  confirmingId.value = attId
  attStep.value = 'import'
}

function handleConfirmed() {
  confirmingId.value = null
  attStep.value = 'queue'
  emit('changed')
}

function onFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  file.value = target.files?.[0] ?? null
  if (file.value) {
    uploadError.value = ''
  }
}

function onInputClick() {
  if (typeof fileInputRef.value?.showPicker === 'function') {
    try {
      fileInputRef.value.showPicker()
    } catch {
      // 浏览器已原生处理或不支持时静默忽略
    }
  }
}

function clearFile() {
  file.value = null
  if (fileInputRef.value) fileInputRef.value.value = ''
  uploadError.value = ''
}

async function upload() {
  if (!file.value) {
    uploadError.value = '请先选择附件文件。'
    return
  }
  const mime = pickMime(file.value)
  if (mime === null) {
    uploadError.value = '仅支持 PDF / DOCX / PNG / JPG / MP3 / M4A 附件。'
    return
  }
  if (file.value.size > MAX_BYTES) {
    uploadError.value = '附件超过 25 MiB 上限。'
    return
  }
  if (file.value.size === 0) {
    uploadError.value = '附件内容为空，无法上传。'
    return
  }
  uploading.value = true
  uploadError.value = ''
  try {
    const named = new File([file.value], file.value.name, { type: mime })
    const saved = await props.client.uploadAttachment(props.source.id, named)
    file.value = null
    if (fileInputRef.value) fileInputRef.value.value = ''
    props.notify(`附件已上传（${saved.filename}）。${REUPLOAD_RESET_NOTE}`, 'caution')
    emit('changed')
  } catch (e) {
    uploadError.value = describeError(e)
  } finally {
    uploading.value = false
  }
}

async function parse(attachment: AttachmentOut) {
  parseBusyId.value = attachment.id
  try {
    const parsed = await props.client.parseAttachment(attachment.id)
    props.notify(
      parsed.status === 'needs_manual_input'
        ? '解析完成：该类型暂不能自动结构化，请逐题人工录入。'
        : '解析完成：请对照解析文本逐题人工录入。',
      'success',
    )
    confirmingId.value = attachment.id
    emit('changed')
  } catch (e) {
    props.notify(describeError(e), 'error')
  } finally {
    parseBusyId.value = null
  }
}
</script>

<template>
  <div role="region" aria-label="附件与解析">
    <StepFlowWorkspace
      v-model="attStep"
      :steps="steps"
      steps-aria-label="附件解析与录入步骤"
    >
      <!-- 第 1 步：上传原始附件与解析队列 -->
      <template #step-queue>
        <section class="card" aria-label="附件上传与解析清单">
          <div class="card-head">
            <div>
              <h2>第 1 步 · 上传原始附件与解析</h2>
              <p class="card-sub">上传后点击「解析」提取对照文本，随后自动解锁第 2 步逐题录入工作台。</p>
            </div>
            <div class="card-head-tools">
              <HelpBubble tone="caution" compact title="提交规范与重传重置说明" label="提交与重传规范">
                <ul>
                  <li><strong>重传复位提醒：</strong>{{ REUPLOAD_RESET_NOTE }}</li>
                  <li><strong>试卷 / 资料要求：</strong>请提交包含完整题面、选项与分值的清晰原件或扫描件（单文件上限 25 MiB）。</li>
                  <li><strong>英语听力配套：</strong>除试题文本外，请同步上传 MP3 或 M4A 音频文件以便录入时直接关联。</li>
                  <li><strong>标准流程：</strong>上传附件 → 点击「解析」提取文本 → 点击「逐题录入并确认导入」进入第 2 步完成录入。</li>
                </ul>
              </HelpBubble>
            </div>
          </div>

          <div class="attachment-upload" style="border-top: none; padding-top: 4px; margin-top: 6px;">
            <label for="attachment-file-input">
              选择原始附件（支持文档、图片、音频，不超过 25 MiB）
            </label>
            <input
              id="attachment-file-input"
              ref="fileInputRef"
              type="file"
              accept=".pdf,.docx,.png,.jpg,.jpeg,.mp3,.m4a,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/png,image/jpeg,audio/mpeg,audio/mp4"
              @change="onFileChange"
              @click="onInputClick"
            />

            <div style="margin-top: 8px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
              <button
                type="button"
                class="primary"
                :disabled="uploading || !file"
                @click="upload"
              >
                {{ uploading ? '上传中…' : '上传附件' }}
              </button>

              <span v-if="file" class="chip good" style="font-size: 0.85rem;">
                已选文件：<b>{{ file.name }}</b>（{{ fmtBytes(file.size) }}）
              </span>
              <button
                v-if="file && !uploading"
                type="button"
                class="ghost small"
                @click="clearFile"
              >
                清空
              </button>
            </div>

            <p v-if="uploadError" class="form-error">{{ uploadError }}</p>
          </div>

          <p v-if="source.attachments.length === 0" class="muted" style="margin-top: 12px;">
            还没有附件：上传后点击「解析」提取对照文本，随后即可进入第 2 步逐题录入并确认导入。
          </p>
          <ul v-else class="attachment-list" tabindex="0" aria-label="已上传附件列表">
            <li
              v-for="a in source.attachments"
              :key="a.id"
              class="attachment-row"
              :style="confirmingId === a.id ? 'border-color: var(--primary); background: var(--primary-soft);' : undefined"
            >
              <div class="attachment-main">
                <b>{{ a.filename }}</b>
                <span :class="['chip', STATUS_CHIP[a.status]]">
                  {{ ATTACHMENT_STATUS_LABELS[a.status] }}
                </span>
                <span class="muted tiny">
                  {{ fmtBytes(a.byte_size) }} · {{ getMediaTypeLabel(a.media_type) }}
                </span>
              </div>
              <div class="attachment-meta" :title="`校验摘要：${a.sha256}`">
                已校验原始文件 · 上传于 {{ shortTime(a.created_at) }}
              </div>
              <div class="attachment-actions">
                <button
                  v-if="a.status === 'uploaded'"
                  type="button"
                  class="ghost small"
                  :disabled="parseBusyId !== null"
                  @click="parse(a)"
                >
                  {{ parseBusyId === a.id ? '解析中…' : '解析' }}
                </button>
                <button
                  v-if="a.status === 'parsed' || a.status === 'needs_manual_input'"
                  type="button"
                  class="primary small"
                  @click="openImportFor(a.id)"
                >
                  逐题录入并确认导入 →
                </button>
                <template v-if="a.status === 'confirmed'">
                  <span class="muted tiny">
                    已导入 {{ a.question_version_ids.length }} 题，等待逐题人工审核。
                  </span>
                  <button type="button" class="ghost small" @click="emit('go-versions')">
                    前往审核与发布
                  </button>
                </template>
              </div>
              <details v-if="a.extracted_text" class="parsed-text">
                <summary>查看解析文本（供人工录入对照）</summary>
                <blockquote>{{ a.extracted_text }}</blockquote>
              </details>
            </li>
          </ul>

          <div v-if="hasConfirmedAttachments" class="handoff-box">
            <div>
              <strong>已完成题目确认导入！</strong>
              <span>下一步请前往「第三阶段 · 题目审核与发布」逐题人工审核并入池。</span>
            </div>
            <button type="button" class="primary small" @click="emit('go-versions')">
              前往题目审核与发布 →
            </button>
          </div>
        </section>
      </template>

      <!-- 第 2 步：逐题人工录入工作台 -->
      <template #step-import>
        <section v-if="confirmingAttachment" class="card" aria-label="逐题人工录入台">
          <div class="card-head" style="margin-bottom: 10px;">
            <div>
              <h2>第 2 步 · 逐题人工录入工作台</h2>
              <p class="card-sub">正在对照：{{ confirmingAttachment.filename }}</p>
            </div>
            <div class="card-head-tools">
              <select
                v-if="readyToImportAttachments.length > 1"
                aria-label="切换待录入附件"
                :value="confirmingAttachment.id"
                style="width: auto; margin: 0; padding: 5px 10px; font-size: 0.8rem;"
                @change="confirmingId = ($event.target as HTMLSelectElement).value"
              >
                <option v-for="att in readyToImportAttachments" :key="att.id" :value="att.id">
                  {{ att.filename }}
                </option>
              </select>
              <button type="button" class="ghost small" @click="attStep = 'queue'">
                ← 返回附件清单
              </button>
            </div>
          </div>

          <details v-if="confirmingAttachment.extracted_text" class="parsed-text" open style="margin-bottom: 12px;">
            <summary>对照解析文本（{{ confirmingAttachment.filename }}）</summary>
            <blockquote>{{ confirmingAttachment.extracted_text }}</blockquote>
          </details>

          <ConfirmImportForm
            :key="confirmingAttachment.id"
            :client="client"
            :attachment="confirmingAttachment"
            :subject="source.source.subject"
            :source-attachments="source.attachments"
            :initial-knowledge-id="initialKnowledgeId"
            :notify="notify"
            @confirmed="handleConfirmed"
          />
        </section>
      </template>
    </StepFlowWorkspace>
  </div>
</template>
