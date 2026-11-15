<script setup lang="ts">
import { computed, ref } from 'vue'
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

type Notify = (text: string, tone?: NoticeTone) => void

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

const file = ref<File | null>(null)
const uploading = ref(false)
const uploadError = ref('')
const parseBusyId = ref<string | null>(null)
const confirmingId = ref<string | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)

const confirmingAttachment = computed(
  () => props.source.attachments.find(a => a.id === confirmingId.value) ?? null
)

const readyToImportAttachments = computed(() =>
  props.source.attachments.filter(
    a => a.status === 'parsed' || a.status === 'needs_manual_input'
  )
)

function onFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  file.value = target.files?.[0] ?? null
  if (file.value) {
    uploadError.value = ''
  }
}

function onInputClick() {
  // 点击 input 任意区域（含右侧空白与文本）均可靠唤起系统文件选择窗口
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
      'success'
    )
    emit('changed')
  } catch (e) {
    props.notify(describeError(e), 'error')
  } finally {
    parseBusyId.value = null
  }
}
</script>

<template>
  <div role="region" aria-label="附件与解析" class="matrix-2col">
    <!-- 左栏：上传原始附件与解析队列 -->
    <section class="card" aria-label="附件上传与解析清单">
      <div class="card-head">
        <h2>附件与解析</h2>
        <div class="card-head-tools">
          <HelpBubble tone="caution" compact title="提交规范与重传重置说明" label="提交与重传规范">
            <ul>
              <li><strong>重传复位提醒：</strong>{{ REUPLOAD_RESET_NOTE }}</li>
              <li><strong>试卷 / 资料要求：</strong>请提交包含完整题面、选项与分值的清晰原件或扫描件（单文件上限 25 MiB）。</li>
              <li><strong>英语听力配套：</strong>除试题文本外，请同步上传 MP3 或 M4A 音频文件以便录入时直接关联。</li>
              <li><strong>标准流程：</strong>上传附件 → 点击「解析」提取文本 → 点击「逐题录入并确认导入」在右侧完成录入。</li>
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
            @click="upload"
            :disabled="uploading || !file"
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
        还没有附件：上传后点击「解析」提取对照文本，随后即可在右侧逐题录入并确认导入。
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
              @click="parse(a)"
              :disabled="parseBusyId !== null"
            >
              {{ parseBusyId === a.id ? '解析中…' : '解析' }}
            </button>
            <button
              v-if="a.status === 'parsed' || a.status === 'needs_manual_input'"
              type="button"
              :class="confirmingId === a.id ? 'small' : 'ghost small'"
              :aria-expanded="confirmingId === a.id"
              @click="confirmingId = confirmingId === a.id ? null : a.id"
            >
              {{ confirmingId === a.id ? '收起逐题录入' : '逐题录入并确认导入' }}
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
    </section>

    <!-- 右栏：协同对照文本与逐题人工录入表单 -->
    <section class="card" aria-label="逐题人工录入台">
      <template v-if="confirmingAttachment">
        <div class="card-head" style="margin-bottom: 8px;">
          <h2>逐题人工录入工作台</h2>
          <button type="button" class="ghost small" @click="confirmingId = null">
            收起录入台
          </button>
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
          @confirmed="confirmingId = null; emit('changed')"
        />
      </template>
      <template v-else>
        <div class="card-head">
          <h2>逐题人工录入工作台</h2>
        </div>
        <p class="muted">
          在左侧上传附件并点击「解析」后，点击对应附件的「逐题录入并确认导入」，此处将展开并排录入表单与解析文本对照视图。
        </p>
        <div v-if="readyToImportAttachments.length > 0" style="margin-top: 10px; display: flex; gap: 8px; flex-wrap: wrap;">
          <button
            v-for="att in readyToImportAttachments"
            :key="att.id"
            type="button"
            class="ghost small"
            @click="confirmingId = att.id"
          >
            打开「{{ att.filename }}」录入
          </button>
        </div>
      </template>
    </section>
  </div>
</template>
