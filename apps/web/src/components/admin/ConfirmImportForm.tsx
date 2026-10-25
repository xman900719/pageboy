import { useState } from 'react'
import { describeError, type ApiClient, type AttachmentOut, type Kind, type QuestionDraftInput } from '../../api'
import { CONFIRM_CHECK_LABEL, KIND_LABELS, excerpt } from '../../copy'
import type { NoticeTone } from '../../components/Notice'

type Notify = (text: string, tone?: NoticeTone) => void
const KINDS: Kind[] = ['single_choice', 'short_answer', 'subjective']

function letter(i: number): string {
  return String.fromCharCode(65 + i)
}

/**
 * 逐题人工录入（每个附件一份）：题干 / 题型 / 选项 / 答案 / 知识点 / 分值，
 * 攒成待导入列表后经显式勾选一次性确认导入（confirmed_by_human = true）。
 * 导入成功后题目成为「待人工审核」草稿。
 */
export function ConfirmImportForm({
  client,
  attachment,
  notify,
  onConfirmed,
}: {
  client: ApiClient
  attachment: AttachmentOut
  notify: Notify
  onConfirmed: () => Promise<void>
}) {
  const [entries, setEntries] = useState<QuestionDraftInput[]>([])
  const [stem, setStem] = useState('')
  const [kind, setKind] = useState<Kind>('single_choice')
  const [options, setOptions] = useState<string[]>(['', ''])
  const [correctIdx, setCorrectIdx] = useState(0)
  const [answer, setAnswer] = useState('')
  const [knowledgeInput, setKnowledgeInput] = useState('')
  const [maxPoints, setMaxPoints] = useState('3')
  const [groupContext, setGroupContext] = useState('')
  const [mediaId, setMediaId] = useState(attachment.media_type.startsWith('audio/') ? attachment.id : '')
  const [checked, setChecked] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  function resetEntry() {
    setStem('')
    setOptions(['', ''])
    setCorrectIdx(0)
    setAnswer('')
  }

  function switchKind(next: Kind) {
    setKind(next)
    resetEntry()
  }

  function setOptionAt(index: number, value: string) {
    setOptions(prev => prev.map((opt, i) => (i === index ? value : opt)))
  }

  function addEntry() {
    const cleanStem = stem.trim()
    if (cleanStem === '') {
      setError('请填写题干。')
      return
    }
    let draftOptions: string[] = []
    let correctAnswer = ''
    if (kind === 'single_choice') {
      const texts = options.map(o => o.trim())
      if (texts.filter(t => t !== '').length < 2) {
        setError('单选题至少需要 2 个非空选项。')
        return
      }
      if (correctIdx < 0 || correctIdx >= texts.length || texts[correctIdx] === '') {
        setError('请为正确选项填写内容。')
        return
      }
      draftOptions = texts.map((t, i) => `${letter(i)}. ${t}`)
      correctAnswer = letter(correctIdx)
    } else {
      correctAnswer = answer.trim()
      if (correctAnswer === '') {
        setError(kind === 'subjective' ? '请填写参考答案文本（供自评对照）。' : '请填写答案。')
        return
      }
    }
    const knowledgeIds = knowledgeInput.split(/[,，、\s]+/).filter(Boolean)
    if (knowledgeIds.length < 1) {
      setError('知识点 ID 至少填 1 个（逗号或空格分隔）。')
      return
    }
    const points = Number(maxPoints)
    if (Number.isNaN(points) || points <= 0 || points > 100) {
      setError('分值须大于 0 且不超过 100。')
      return
    }
    const context = groupContext.trim()
    if (context.length > 20000) {
      setError('组内材料不能超过 20000 字。')
      return
    }
    setEntries(prev => [
      ...prev,
      {
        // 后端按「题目所属题源 == 附件所属题源」校验（IMPORT_SOURCE_MISMATCH），此处必须用题源 id 而非附件 id。
        source_document_id: attachment.source_document_id,
        stem: cleanStem,
        kind,
        options: draftOptions,
        correct_answer: correctAnswer,
        knowledge_ids: knowledgeIds,
        max_points: points,
        group_context: context === '' ? null : context,
        media_attachment_id: mediaId.trim() === '' ? null : mediaId.trim(),
      },
    ])
    setError('')
    resetEntry()
  }

  async function confirm() {
    if (entries.length === 0) {
      setError('请先录入至少 1 道题。')
      return
    }
    if (!checked) {
      setError('请先勾选「我已逐题人工核对」。')
      return
    }
    setBusy(true)
    setError('')
    try {
      await client.confirmImport(attachment.id, entries)
      notify(`已确认导入 ${entries.length} 题，草稿待人工审核。`, 'success')
      setEntries([])
      setChecked(false)
      await onConfirmed()
    } catch (e) {
      setError(describeError(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="confirm-import">
      <h3 className="sub-head">逐题人工录入（导入为「{attachment.filename}」）</h3>
      <div className="admin-grid">
        <label className="wide">
          题干
          <textarea rows={2} value={stem} onChange={e => setStem(e.target.value)} placeholder="虚构测试数据：计算 12 + 15 的结果。" />
        </label>
        <label>
          题型
          <select value={kind} onChange={e => switchKind(e.target.value as Kind)}>
            {KINDS.map(id => (
              <option key={id} value={id}>
                {KIND_LABELS[id]}
              </option>
            ))}
          </select>
        </label>
        <label>
          分值（大于 0，不超过 100）
          <input type="number" min={0} max={100} step={0.5} value={maxPoints} onChange={e => setMaxPoints(e.target.value)} />
        </label>
        {kind === 'single_choice' ? (
          <div className="wide" role="group" aria-label="选项与正确答案">
            <span className="field-label">选项（至少 2 个非空，自动编号 A / B / C…）</span>
            <div className="option-rows">
              {options.map((opt, i) => (
                <div className="option-row" key={i}>
                  <span className="option-key" aria-hidden="true">
                    {letter(i)}
                  </span>
                  <input
                    value={opt}
                    onChange={e => setOptionAt(i, e.target.value)}
                    aria-label={`选项 ${letter(i)} 内容`}
                    placeholder={`虚构测试数据：选项 ${letter(i)} 内容`}
                  />
                  {options.length > 2 && (
                    <button
                      type="button"
                      className="ghost small"
                      aria-label={`删除选项 ${letter(i)}`}
                      onClick={() => {
                        setOptions(prev => prev.filter((_, idx) => idx !== i))
                        setCorrectIdx(0)
                      }}
                    >
                      删除
                    </button>
                  )}
                </div>
              ))}
            </div>
            <button type="button" className="ghost small" onClick={() => setOptions(prev => [...prev, ''])}>
              加一个选项
            </button>
            <label>
              正确选项
              <select value={String(correctIdx)} onChange={e => setCorrectIdx(Number(e.target.value))}>
                {options.map((opt, i) => (
                  <option key={i} value={i}>
                    {letter(i)}
                    {opt.trim() === '' ? '（未填写）' : ` · ${excerpt(opt, 16)}`}
                  </option>
                ))}
              </select>
            </label>
          </div>
        ) : (
          <label className="wide">
            {kind === 'subjective' ? '参考答案（文本，供自评对照）' : '答案（已审核后用于自动比对）'}
            <textarea rows={2} value={answer} onChange={e => setAnswer(e.target.value)} placeholder="虚构测试数据：参考答案文本" />
          </label>
        )}
        <label className="wide">
          知识点 ID（至少 1 个，逗号或空格分隔）
          <input value={knowledgeInput} onChange={e => setKnowledgeInput(e.target.value)} placeholder="虚构测试数据：math.gap, math.alg" />
        </label>
        <label className="wide">
          组内材料（可选，与同组题共用，如阅读材料，≤20000 字）
          <textarea rows={2} value={groupContext} onChange={e => setGroupContext(e.target.value)} placeholder="虚构测试数据：阅读材料文本" />
        </label>
        <label className="wide">
          媒体附件 ID（可选：听力题填音频附件 id，须属于本来源）
          <input className="mono-input" value={mediaId} onChange={e => setMediaId(e.target.value)} placeholder="留空表示无媒体" autoComplete="off" />
        </label>
      </div>
      {error && <p className="form-error">{error}</p>}
      <div className="confirm-import-actions">
        <button type="button" className="ghost" onClick={addEntry}>
          加入待导入列表
        </button>
        {entries.length > 0 && <span className="muted tiny">已录入 {entries.length} 题</span>}
      </div>

      {entries.length > 0 && (
        <>
          <ul className="entry-list">
            {entries.map((entry, i) => (
              <li key={i} className="entry-row">
                <span className="muted tiny">#{i + 1}</span>
                <span className="entry-stem">{excerpt(entry.stem, 48)}</span>
                <span className="badge kind">{KIND_LABELS[entry.kind]}</span>
                <span className="muted tiny">{entry.max_points} 分</span>
                <button type="button" className="ghost small" aria-label={`移除第 ${i + 1} 题`} onClick={() => setEntries(prev => prev.filter((_, idx) => idx !== i))}>
                  移除
                </button>
              </li>
            ))}
          </ul>
          <div className="confirm-box">
            <input
              id={`confirm-check-${attachment.id}`}
              type="checkbox"
              checked={checked}
              onChange={e => setChecked(e.target.checked)}
            />
            <label htmlFor={`confirm-check-${attachment.id}`}>{CONFIRM_CHECK_LABEL}（勾选后才能确认导入）</label>
          </div>
          <button type="button" className="primary" onClick={() => void confirm()} disabled={busy || !checked}>
            {busy ? '导入中…' : `确认导入 ${entries.length} 题`}
          </button>
        </>
      )}
    </div>
  )
}
