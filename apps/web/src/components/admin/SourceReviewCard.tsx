import { useState, type FormEvent } from 'react'
import { describeError, SUBJECT_LABELS, type ApiClient, type RightsStatus, type SourceDetail } from '../../api'
import { REVIEW_CHECK_LABEL, RIGHTS_STATUS_LABELS, shortTime } from '../../copy'

type Notify = (text: string, tone?: 'info' | 'success' | 'caution' | 'error') => void

/**
 * 来源人工审核：提交后 source.verified = applicable（适用才视为已审核）。
 * 上传附件会复位 verified，需重新在此提交审核。
 */
export function SourceReviewCard({
  client,
  source,
  notify,
  onReviewed,
}: {
  client: ApiClient
  source: SourceDetail
  notify: Notify
  onReviewed: () => Promise<void>
}) {
  const latest = source.reviews[source.reviews.length - 1]?.metadata ?? null
  const [examYear, setExamYear] = useState(String(latest?.exam_year ?? new Date().getFullYear()))
  const [sourceUrl, setSourceUrl] = useState(latest?.source_url ?? '')
  const [acquiredAt, setAcquiredAt] = useState(latest?.acquired_at ?? new Date().toISOString().slice(0, 10))
  const [rightsStatus, setRightsStatus] = useState<RightsStatus>(latest?.rights_status ?? source.source.rights_status)
  const [rightsBasis, setRightsBasis] = useState(latest?.rights_basis ?? '')
  const [applicable, setApplicable] = useState(latest?.applicable ?? true)
  const [applicabilityNote, setApplicabilityNote] = useState(latest?.applicability_note ?? '')
  const [checked, setChecked] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent) {
    event.preventDefault()
    const year = Number(examYear)
    if (!Number.isInteger(year) || year < 1990 || year > 2100) {
      setError('考试年份须为 1990–2100 之间的整数。')
      return
    }
    if (!sourceUrl.trim().startsWith('https://')) {
      setError('来源链接必须以 https:// 开头。')
      return
    }
    const basis = rightsBasis.trim()
    if (basis === '' || basis.length > 2000) {
      setError('版权依据必填，长度 1–2000 字。')
      return
    }
    const note = applicabilityNote.trim()
    if (note === '' || note.length > 2000) {
      setError('适用性说明必填，长度 1–2000 字。')
      return
    }
    if (!checked) {
      setError('请先勾选人工核查确认。')
      return
    }
    setBusy(true)
    setError('')
    try {
      await client.reviewSource(source.id, {
        exam_year: year,
        source_url: sourceUrl.trim(),
        acquired_at: acquiredAt,
        rights_status: rightsStatus,
        rights_basis: basis,
        applicable,
        applicability_note: note,
        reviewed_by_human: true,
      })
      notify(
        applicable
          ? '来源人工审核已记录，题源标记为已审核。'
          : '审核已记录：适用性为「不适用」，题源仍视为未审核，题目无法发布。',
        applicable ? 'success' : 'caution',
      )
      await onReviewed()
    } catch (e) {
      setError(describeError(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card" aria-label="来源人工审核">
      <div className="card-head">
        <h2>来源人工审核</h2>
        <span className={`chip ${source.source.verified ? 'good' : 'wait'}`}>{source.source.verified ? '已人工审核' : '未审核'}</span>
      </div>
      <p className="muted">
        题源「{source.source.title}」 · {SUBJECT_LABELS[source.source.subject]} · 版权状态：
        {RIGHTS_STATUS_LABELS[source.source.rights_status]}
        {source.reviews.length > 0 && ` · 已有 ${source.reviews.length} 次审核记录（最近 ${shortTime(source.reviews[source.reviews.length - 1].created_at)}）`}
      </p>
      <form className="admin-form" onSubmit={submit}>
        <div className="admin-grid">
          <label>
            考试年份（1990–2100）
            <input
              type="number"
              min={1990}
              max={2100}
              value={examYear}
              onChange={e => setExamYear(e.target.value)}
              placeholder="虚构测试数据：2025"
            />
          </label>
          <label>
            来源链接（必须 https）
            <input
              value={sourceUrl}
              onChange={e => setSourceUrl(e.target.value)}
              placeholder="https://example.org/exam.pdf"
              autoComplete="off"
            />
          </label>
          <label>
            获取日期
            <input type="date" value={acquiredAt} onChange={e => setAcquiredAt(e.target.value)} />
          </label>
          <label>
            版权状态
            <select value={rightsStatus} onChange={e => setRightsStatus(e.target.value as RightsStatus)}>
              {(Object.keys(RIGHTS_STATUS_LABELS) as RightsStatus[]).map(id => (
                <option key={id} value={id}>
                  {RIGHTS_STATUS_LABELS[id]}
                </option>
              ))}
            </select>
          </label>
          <label className="wide">
            版权依据（1–2000 字，必填）
            <textarea
              rows={2}
              maxLength={2000}
              value={rightsBasis}
              onChange={e => setRightsBasis(e.target.value)}
              placeholder="虚构测试数据：个人购入纸质教辅，仅自用"
            />
          </label>
          <div className="wide confirm-box">
            <input
              id={`applicable-${source.id}`}
              type="checkbox"
              checked={applicable}
              onChange={e => setApplicable(e.target.checked)}
            />
            <label htmlFor={`applicable-${source.id}`}>来源适用：内容可用于本工具的练习与诊断取题（不适用则题源保持未审核）</label>
          </div>
          <label className="wide">
            适用性说明（1–2000 字，必填）
            <textarea
              rows={2}
              maxLength={2000}
              value={applicabilityNote}
              onChange={e => setApplicabilityNote(e.target.value)}
              placeholder="虚构测试数据：覆盖本地中考数学题型，与教学进度一致"
            />
          </label>
        </div>
        <div className="confirm-box">
          <input
            id={`review-check-${source.id}`}
            type="checkbox"
            checked={checked}
            onChange={e => setChecked(e.target.checked)}
          />
          <label htmlFor={`review-check-${source.id}`}>{REVIEW_CHECK_LABEL}（勾选后才能提交）</label>
        </div>
        {error && <p className="form-error">{error}</p>}
        <button type="submit" className="primary" disabled={busy || !checked}>
          {busy ? '提交中…' : '提交人工审核'}
        </button>
      </form>
    </section>
  )
}
