import { useCallback, useMemo, useState, type FormEvent } from 'react'
import { createClient, describeError, SUBJECTS, SUBJECT_LABELS, type Subject } from './api'
import { VIEWS, type ViewId } from './copy'
import { Notice, type NoticeData, type NoticeTone } from './components/Notice'
import { HomeView } from './views/HomeView'
import { PracticeView } from './views/PracticeView'
import { DiagnosisView } from './views/DiagnosisView'

export default function App() {
  const [token, setToken] = useState('')
  const [subject, setSubject] = useState<Subject>('math')
  const [view, setView] = useState<ViewId>('home')
  const [notice, setNotice] = useState<NoticeData | null>(null)

  const client = useMemo(() => (token === '' ? null : createClient(token)), [token])
  const notify = useCallback((text: string, tone: NoticeTone = 'info') => setNotice({ text, tone }), [])
  const clearNotice = useCallback(() => setNotice(null), [])

  async function enter(nextToken: string) {
    const candidate = createClient(nextToken)
    await candidate.verify() // throws on invalid token; nothing is kept on failure
    setToken(nextToken)
    notify('已进入私有学习空间。', 'success')
  }

  function signOut() {
    setToken('')
    setNotice(null)
  }

  const body = client ? (
    <main className="view" key={`${view}:${subject}`}>
      {view === 'home' && <HomeView client={client} subject={subject} notify={notify} goView={setView} />}
      {view === 'practice' && <PracticeView client={client} subject={subject} notify={notify} />}
      {view === 'diagnosis' && <DiagnosisView client={client} subject={subject} notify={notify} goHome={() => setView('home')} />}
    </main>
  ) : (
    <Gate onEnter={enter} />
  )

  return (
    <div className="page">
      {client && (
        <header className="masthead">
          <div className="masthead-row">
            <div className="wordmark-block">
              <span className="seal" aria-hidden="true">
                书
              </span>
              <div>
                <span className="wordmark">书童</span>
                <span className="tagline">目标驱动的中考练习 · 私人学习空间</span>
              </div>
            </div>
            <div className="masthead-side">
              <span className="pill">本地 · 私有</span>
              <button type="button" className="ghost small" onClick={signOut}>
                退出
              </button>
            </div>
          </div>
          <nav className="views" aria-label="主要视图">
            {VIEWS.map(entry => (
              <button
                type="button"
                key={entry.id}
                className={view === entry.id ? 'view-tab selected' : 'view-tab'}
                onClick={() => setView(entry.id)}
              >
                <b>{entry.label}</b>
                <small>{entry.hint}</small>
              </button>
            ))}
            <div className="subject-row" role="group" aria-label="科目">
              {SUBJECTS.map(id => (
                <button
                  type="button"
                  key={id}
                  className={subject === id ? 'subject-chip selected' : 'subject-chip'}
                  onClick={() => {
                    setSubject(id)
                    notify(`已切换到${SUBJECT_LABELS[id]}。`)
                  }}
                >
                  {SUBJECT_LABELS[id]}
                </button>
              ))}
            </div>
          </nav>
        </header>
      )}

      {body}

      <footer>开发验证版 · 演示数据均为虚构测试数据 · 不作中考分数预测</footer>
      <Notice notice={notice} onClose={clearNotice} />
    </div>
  )
}

/** Token gate: the token lives in page memory only; it is verified before entry. */
function Gate({ onEnter }: { onEnter: (token: string) => Promise<void> }) {
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (value.trim() === '') {
      setError('请输入访问令牌。')
      return
    }
    setBusy(true)
    setError('')
    try {
      await onEnter(value.trim())
    } catch (e) {
      setError(describeError(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="gate">
      <section className="card gate-card">
        <div className="gate-head">
          <span className="seal big" aria-hidden="true">
            书
          </span>
          <div>
            <span className="wordmark">书童</span>
            <span className="tagline">目标驱动的中考练习 · 私人学习空间</span>
          </div>
        </div>
        <form onSubmit={submit}>
          <label>
            访问令牌
            <input
              type="password"
              value={value}
              onChange={e => setValue(e.target.value)}
              placeholder="SHUTONG_TOKEN"
              autoComplete="off"
              autoFocus
            />
          </label>
          {error && <p className="form-error">{error}</p>}
          <button type="submit" className="primary" disabled={busy}>
            {busy ? '验证中…' : '进入'}
          </button>
        </form>
        <ul className="gate-notes">
          <li>令牌只保留在当前页面内存里：刷新或关闭页面后需重新输入，不会写入任何存储。</li>
          <li>私有单人工具：练习记录、学校试卷与个人信息不会被公开传播。</li>
          <li>只有管理员人工审核发布的题目才会出现；当前演示数据均为虚构测试数据。</li>
        </ul>
      </section>
    </main>
  )
}
