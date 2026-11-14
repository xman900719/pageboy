<script setup lang="ts">
import { ref } from 'vue'
import {
  describeError,
  type ApiClient,
  type AttachmentOut,
  type AttachmentStatus,
  type SourceDetail,
} from '../../api'
import { ATTACHMENT_STATUS_LABELS, REUPLOAD_RESET_NOTE, fmtBytes, shortTime } from '../../copy'
import { getMediaTypeLabel } from '../../config/knowledge'
import Note from '../../components/Note.vue'
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
  notify: Notify
}>()

const emit = defineEmits<{
  (e: 'changed'): void
}>()

const file = ref<File | null>(null)
const uploading = ref(false)
const uploadError = ref('')
const parseBusyId = ref<string | null>(null)
const confirmingId = ref<string | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)

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
  <section class="card" aria-label="附件与解析">
    <div class="card-head">
      <h2>附件与解析</h2>
    </div>
    <Note tone="caution">{{ REUPLOAD_RESET_NOTE }}</Note>

    <div class="attachment-upload">
      <!-- 月考/试卷等附件提交内容明确指引说明 -->
      <div class="note note-neutral" style="margin-bottom: 12px; font-size: 0.9rem;">
        <b>📄 试卷与教学资料提交规范指引</b>
        <ul style="margin: 6px 0 0 18px; padding: 0;">
          <li><b>月考 / 单元检测卷 / 历年真题</b>：请提交包含完整题面、选项与分值的整卷清晰原件或扫描件（PDF / DOCX / PNG / JPG，单文件上限 25 MiB）。</li>
          <li><b>英语听力试卷</b>：除试题文本扫描件外，请同时上传配套的 MP3 / M4A 录音音频，以支持听力播放组件关联。</li>
          <li><b>上传后操作流程</b>：上传成功后点击「解析」提取机读文本，随后在下方「逐题录入并确认导入」中录入各题干、题型与考点。</li>
        </ul>
      </div>

      <label for="attachment-file-input">
        选择原始附件（PDF / DOCX / PNG / JPG / MP3 / M4A，不超过 25 MiB）
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

    <p v-if="source.attachments.length === 0" class="muted">
      还没有附件：上传后点「解析」生成对照文本，再逐题人工录入并确认导入。
    </p>
    <ul v-else class="attachment-list">
      <li v-for="a in source.attachments" :key="a.id" class="attachment-row">
        <div class="attachment-main">
          <b>{{ a.filename }}</b>
          <span :class="['chip', STATUS_CHIP[a.status]]">
            {{ ATTACHMENT_STATUS_LABELS[a.status] }}
          </span>
          <span class="muted tiny">
            {{ fmtBytes(a.byte_size) }} · {{ getMediaTypeLabel(a.media_type) }}
          </span>
        </div>
        <div class="attachment-meta">
          文件校验摘要 {{ a.sha256.slice(0, 16) }}… · 上传于 {{ shortTime(a.created_at) }}
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
          <span v-if="a.status === 'confirmed'" class="muted tiny">
            已导入 {{ a.question_version_ids.length }} 题，等待在下方逐题人工审核。
          </span>
        </div>
        <details v-if="a.extracted_text" class="parsed-text">
          <summary>查看解析文本（供人工录入对照）</summary>
          <blockquote>{{ a.extracted_text }}</blockquote>
        </details>
        <ConfirmImportForm
          v-if="confirmingId === a.id"
          :client="client"
          :attachment="a"
          :notify="notify"
          @confirmed="confirmingId = null; emit('changed')"
        />
      </li>
    </ul>
  </section>
</template>
