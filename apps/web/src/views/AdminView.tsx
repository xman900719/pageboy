import { useCallback, useEffect, useState, type FormEvent } from 'react'
import {
  describeError,
  SUBJECTS,
  SUBJECT_LABELS,
  type ApiClient,
  type RightsStatus,
  type SourceDetail,
  type Subject,
} from '../api'
import { ADMIN_PIPELINE_NOTE, RIGHTS_STATUS_LABELS } from '../copy'
import { Note } from '../components/Note'
import type { NoticeTone } from '../components/Notice'
import { SourceReviewCard } from '../components/admin/SourceReviewCard'
import { AttachmentCard } from '../components/admin/AttachmentCard'
import { QuestionVersionsCard } from '../components/admin/QuestionVersionsCard'

type Notify = (text: string, tone?: NoticeTone) => void

/** ④ 题库审核台：题源台账 → 来源人工审核 → 附件解析 → 逐题确认导入 → 草稿审核与发布。 */
export function AdminView({ client, subject, notify }: { client: ApiClient; subject: Subject; notify: Notify }) {
  const [sources, setSources] = useState<SourceDetail[] | null>(null)
  const [loadError, setLoadError] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [newTitle, setNewTitle] = useState('')
  const [newSubject, setNewSubject] = useState<Subject>(subject)
  const [newRights, setNewRights] = useState<RightsStatus>('unknown')
  const [creating, setCreating] = useState(false)
  const [formError, setFormError] = useState('')

  const refresh = useCallback(async () => {
    try {
      const list = await client.adminSources()
      setSources(list)
      setLoadError('')
      setSelectedId(prev => (prev !== null && list.some(s => s.id === prev) ? prev : (list[0]?.id ?? null)))
    } catch (e) {
      setLoadError(describeError(e))
    }
  }, [client])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const selected = sources?.find(s => s.id === selectedId) ?? null

  async function createSource(event: FormEvent) {
    event.preventDefault()
    if (newTitle.trim() === '') {
      setFormError('请填写题源标题。')
      return
    }
    setCreating(true)
    setFormError('')
    try {
      const created = await client.addSource({ title: newTitle.trim(), subject: newSubject, rightsStatus: newRights })
      notify(`题源已登记（${created.id.slice(0, 8)}…）。下一步：上传附件并完成来源人工审核。`, 'success')
      setNewTitle('')
      await refresh()
      setSelectedId(created.id)
    } catch (e) {
      setFormError(describeError(e))
    } finally {
      setCreating(false)
    }
  }

  return (
    <>
      <Note tone="discipline" title="人工审核流水线">
        {ADMIN_PIPELINE_NOTE}
      </Note>

      <section className="card" aria-label="题源台账">
        <div className="card-head">
          <h2>题源台账</h2>
          <button type="button" className="ghost small" onClick={() => void refresh()}>
            刷新
          </button>
        </div>
        <p className="muted">登记试卷 / 教辅来源，逐个完成附件上传、来源人工审核与题目发布。数据只保存在本机私有库。</p>
        {sources === null ? (
          <p className="muted">{loadError === '' ? '题源加载中…' : `题源加载失败：${loadError}`}</p>
        ) : sources.length === 0 ? (
          <p className="muted">还没有题源：用下方表单登记第一个来源（示例文案均为虚构测试数据）。</p>
        ) : (
          <ul className="source-list">
            {sources.map(s => {
              const isSelected = s.id === selectedId
              return (
                <li key={s.id} className={isSelected ? 'source-item selected' : 'source-item'}>
                  <button type="button" className="source-pick" aria-pressed={isSelected} onClick={() => setSelectedId(s.id)}>
                    <span className="source-title">{s.source.title}</span>
                    <span className="muted tiny">
                      {SUBJECT_LABELS[s.source.subject]} · {s.attachments.length} 个附件 · {s.reviews.length} 次审核记录
                    </span>
                  </button>
                  <span className={`chip ${s.source.verified ? 'good' : 'wait'}`}>{s.source.verified ? '已人工审核' : '未审核'}</span>
                </li>
              )
            })}
          </ul>
        )}

        <form className="admin-form" onSubmit={createSource}>
          <div className="admin-grid">
            <label>
              题源标题
              <input
                value={newTitle}
                onChange={e => setNewTitle(e.target.value)}
                placeholder="虚构测试数据：2025 区模拟卷（数学）"
                maxLength={256}
              />
            </label>
            <label>
              科目
              <select value={newSubject} onChange={e => setNewSubject(e.target.value as Subject)}>
                {SUBJECTS.map(id => (
                  <option key={id} value={id}>
                    {SUBJECT_LABELS[id]}
                  </option>
                ))}
              </select>
            </label>
            <label className="wide">
              版权状态
              <select value={newRights} onChange={e => setNewRights(e.target.value as RightsStatus)}>
                {(Object.keys(RIGHTS_STATUS_LABELS) as RightsStatus[]).map(id => (
                  <option key={id} value={id}>
                    {RIGHTS_STATUS_LABELS[id]}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="muted tiny">版权状态为「未核实」的题源，即使完成人工审核也无法发布题目；请先补全授权或核查依据。</p>
          {formError && <p className="form-error">{formError}</p>}
          <button type="submit" className="primary" disabled={creating}>
            {creating ? '登记中…' : '新建题源'}
          </button>
        </form>
      </section>

      {selected && (
        <div key={selected.id}>
          <SourceReviewCard client={client} source={selected} notify={notify} onReviewed={() => refresh()} />
          <AttachmentCard client={client} source={selected} notify={notify} onChanged={() => refresh()} />
          <QuestionVersionsCard client={client} source={selected} notify={notify} onSourceChanged={() => refresh()} />
        </div>
      )}
    </>
  )
}
