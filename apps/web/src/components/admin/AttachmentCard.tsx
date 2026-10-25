import { useRef, useState } from 'react'
import { describeError, type ApiClient, type AttachmentOut, type AttachmentStatus, type SourceDetail } from '../../api'
import { ATTACHMENT_STATUS_LABELS, REUPLOAD_RESET_NOTE, fmtBytes, shortTime } from '../../copy'
import { Note } from '../../components/Note'
import type { NoticeTone } from '../../components/Notice'
import { ConfirmImportForm } from './ConfirmImportForm'

type Notify = (text: string, tone?: NoticeTone) => void

const MAX_BYTES = 10 * 1024 * 1024
const ALLOWED_TYPES = new Set(['application/pdf', 'image/png', 'image/jpeg', 'audio/mpeg', 'audio/mp4'])
/* Windows 资源管理器等场景下 file.type 可能为空：按扩展名兜底判定媒体类型。 */
const EXT_TYPES: Record<string, string> = {
  pdf: 'application/pdf',
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

/** 附件区：原始二进制上传（≤10MiB）→ 解析 → 逐题录入确认导入。上传会复位题源的已审核状态。 */
export function AttachmentCard({
  client,
  source,
  notify,
  onChanged,
}: {
  client: ApiClient
  source: SourceDetail
  notify: Notify
  onChanged: () => Promise<void>
}) {
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [parseBusyId, setParseBusyId] = useState<string | null>(null)
  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  async function upload() {
    if (!file) {
      setUploadError('请先选择附件文件。')
      return
    }
    const mime = pickMime(file)
    if (mime === null) {
      setUploadError('仅支持 PDF / PNG / JPG / MP3 / M4A 附件。')
      return
    }
    if (file.size > MAX_BYTES) {
      setUploadError('附件超过 10 MiB 上限。')
      return
    }
    if (file.size === 0) {
      setUploadError('附件内容为空，无法上传。')
      return
    }
    setUploading(true)
    setUploadError('')
    try {
      // File 对象不可变：以判定的媒体类型重建后上传（Content-Type 为原始二进制类型）。
      const named = new File([file], file.name, { type: mime })
      const saved = await client.uploadAttachment(source.id, named)
      setFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
      notify(`附件已上传（${saved.filename}）。${REUPLOAD_RESET_NOTE}`, 'caution')
      await onChanged()
    } catch (e) {
      setUploadError(describeError(e))
    } finally {
      setUploading(false)
    }
  }

  async function parse(attachment: AttachmentOut) {
    setParseBusyId(attachment.id)
    try {
      const parsed = await client.parseAttachment(attachment.id)
      notify(
        parsed.status === 'needs_manual_input'
          ? '解析完成：该类型暂不能自动结构化，请逐题人工录入。'
          : '解析完成：请对照解析文本逐题人工录入。',
        'success',
      )
      await onChanged()
    } catch (e) {
      notify(describeError(e), 'error')
    } finally {
      setParseBusyId(null)
    }
  }

  return (
    <section className="card" aria-label="附件与解析">
      <div className="card-head">
        <h2>附件与解析</h2>
      </div>
      <Note tone="caution">{REUPLOAD_RESET_NOTE}</Note>

      <div className="attachment-upload">
        <label>
          选择原始附件（PDF / PNG / JPG / MP3 / M4A，不超过 10 MiB）
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,.mp3,.m4a,application/pdf,image/png,image/jpeg,audio/mpeg,audio/mp4"
            onChange={e => setFile(e.target.files?.[0] ?? null)}
          />
        </label>
        <button type="button" className="primary" onClick={() => void upload()} disabled={uploading || !file}>
          {uploading ? '上传中…' : '上传附件'}
        </button>
        {uploadError && <p className="form-error">{uploadError}</p>}
      </div>

      {source.attachments.length === 0 ? (
        <p className="muted">还没有附件：上传后点「解析」生成对照文本，再逐题人工录入并确认导入。</p>
      ) : (
        <ul className="attachment-list">
          {source.attachments.map(a => (
            <li key={a.id} className="attachment-row">
              <div className="attachment-main">
                <b>{a.filename}</b>
                <span className={`chip ${STATUS_CHIP[a.status]}`}>{ATTACHMENT_STATUS_LABELS[a.status]}</span>
                <span className="muted tiny">
                  {fmtBytes(a.byte_size)} · {a.media_type}
                </span>
              </div>
              <div className="attachment-meta">
                sha256 {a.sha256.slice(0, 16)}… · 上传于 {shortTime(a.created_at)}
              </div>
              <div className="attachment-actions">
                {a.status === 'uploaded' && (
                  <button type="button" className="ghost small" onClick={() => void parse(a)} disabled={parseBusyId !== null}>
                    {parseBusyId === a.id ? '解析中…' : '解析'}
                  </button>
                )}
                {(a.status === 'parsed' || a.status === 'needs_manual_input') && (
                  <button
                    type="button"
                    className={confirmingId === a.id ? 'small' : 'ghost small'}
                    aria-expanded={confirmingId === a.id}
                    onClick={() => setConfirmingId(prev => (prev === a.id ? null : a.id))}
                  >
                    {confirmingId === a.id ? '收起逐题录入' : '逐题录入并确认导入'}
                  </button>
                )}
                {a.status === 'confirmed' && (
                  <span className="muted tiny">已导入 {a.question_version_ids.length} 题，等待在下方逐题人工审核。</span>
                )}
              </div>
              {a.extracted_text && (
                <details className="parsed-text">
                  <summary>查看解析文本（供人工录入对照）</summary>
                  <blockquote>{a.extracted_text}</blockquote>
                </details>
              )}
              {confirmingId === a.id && (
                <ConfirmImportForm
                  client={client}
                  attachment={a}
                  notify={notify}
                  onConfirmed={async () => {
                    setConfirmingId(null)
                    await onChanged()
                  }}
                />
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
