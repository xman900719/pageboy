import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { createClient, describeError, SUBJECTS, SUBJECT_LABELS, type Subject } from './api'
import { VIEWS, type ViewId } from './copy'
import { Notice, type NoticeData, type NoticeTone } from './components/Notice'
import { HomeView } from './views/HomeView'
import { PracticeView } from './views/PracticeView'
import { DiagnosisView } from './views/DiagnosisView'
import { AdminView } from './views/AdminView'

/** 本机记住的令牌（ST-012）：仅当用户在令牌门显式勾选「在本机记住令牌」才写入。
 *  值不出设备、不经网络传给任何第三方（verify 只是带 Authorization 的本服务请求）；
 *  退出即清除；令牌失效时自动清除并回到令牌门。默认行为不变：仅页面内存。 */
const TOKEN_STORE_KEY = 'shutong.token'

export default function App() {
  const [token, setToken] = useState('')
  const [subject, setSubject] = useState<Subject>('math')
  const [view, setView] = useState<ViewId>('home')
  const [notice, setNotice] = useState<NoticeData | null>(null)

  const client = useMemo(() => (token === '' ? null : createClient(token)), [token])
  const notify = useCallback((text: string, tone: NoticeTone = 'info') => setNotice({ text, tone }), [])
  const clearNotice = useCallback(() => setNotice(null), [])

  // 冷启动（PWA/主屏幕图标重开）：本机记住的令牌经 verify 后自动进入；已手动进入则不打扰。
  const tokenRef = useRef(token)
  useEffect(() => {
    tokenRef.current = token
  }, [token])
  useEffect(() => {
    const saved = localStorage.getItem(TOKEN_STORE_KEY)
    if (saved === null || saved === '') return
    let cancelled = false
    createClient(saved)
      .verify()
      .then(() => {
        if (cancelled || tokenRef.current !== '') return
        notify('已用本机记住的令牌自动进入。', 'success')
        setToken(saved)
      })
      .catch(() => {
        // 令牌已失效（如服务端轮换）：如实清除，不留在本机。
        localStorage.removeItem(TOKEN_STORE_KEY)
      })
    return () => {
      cancelled = true
    }
  }, [notify])

  async function enter(nextToken: string, remember: boolean) {
    const candidate = createClient(nextToken)
    await candidate.verify() // throws on invalid token; nothing is kept on failure
    if (remember) localStorage.setItem(TOKEN_STORE_KEY, nextToken)
    else localStorage.removeItem(TOKEN_STORE_KEY)
    setToken(nextToken)
    notify('已进入私有学习空间。', 'success')
  }

  function signOut() {
    localStorage.removeItem(TOKEN_STORE_KEY) // 退出 = 完整登出：本机记住的令牌一并清除
    setToken('')
    setNotice(null)
  }

  const body = client ? (
    <main className="view" key={`${view}:${subject}`}>
      {view === 'home' && <HomeView client={client} subject={subject} notify={notify} goView={setView} />}
      {view === 'practice' && <PracticeView client={client} subject={subject} notify={notify} />}
      {view === 'diagnosis' && <DiagnosisView client={client} subject={subject} notify={notify} goHome={() => setView('home')} />}
      {view === 'admin' && <AdminView client={client} subject={subject} notify={notify} />}
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

/** Token gate: verified before entry; the token stays in page memory unless the
 *  user explicitly opts into 「在本机记住令牌」 (ST-012, private-device convenience). */
function Gate({ onEnter }: { onEnter: (token: string, remember: boolean) => Promise<void> }) {
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [visible, setVisible] = useState(false)
  const [remember, setRemember] = useState(() => localStorage.getItem(TOKEN_STORE_KEY) !== null)

  async function pasteToken() {
    // 优先走剪贴板 API（HTTPS 站点，点击授权一次即可）；拒绝/不支持时提示手动粘贴兜底。
    try {
      const text = (await navigator.clipboard.readText()).trim()
      if (text === '') {
        setError('剪贴板为空：请先复制访问令牌，或在输入框长按 / Ctrl+V 粘贴。')
        return
      }
      setValue(text)
      setError('')
    } catch {
      setError('无法读取剪贴板：请在输入框长按 / Ctrl+V 粘贴。')
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (value.trim() === '') {
      setError('请输入访问令牌。')
      return
    }
    setBusy(true)
    setError('')
    try {
      await onEnter(value.trim(), remember)
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
            <span className="token-row">
              <input
                type={visible ? 'text' : 'password'}
                value={value}
                onChange={e => setValue(e.target.value)}
                placeholder="SHUTONG_TOKEN"
                autoComplete="off"
                autoFocus
              />
              <button
                type="button"
                className="ghost"
                onClick={() => setVisible(v => !v)}
                aria-pressed={visible}
                aria-label={visible ? '隐藏令牌' : '显示令牌'}
              >
                {visible ? '隐藏' : '显示'}
              </button>
              <button type="button" className="ghost" onClick={pasteToken} disabled={busy} aria-label="粘贴令牌">
                粘贴
              </button>
            </span>
          </label>
          <div className="confirm-box gate-remember">
            <input
              id="gate-remember"
              type="checkbox"
              checked={remember}
              onChange={e => setRemember(e.target.checked)}
            />
            <label htmlFor="gate-remember">在本机记住令牌（私有设备：冷启动免输入；退出即清除）</label>
          </div>
          {error && <p className="form-error">{error}</p>}
          <button type="submit" className="primary" disabled={busy}>
            {busy ? '验证中…' : '进入'}
          </button>
        </form>
        <ul className="gate-notes">
          <li>令牌默认只保留在当前页面内存；仅当你显式勾选「在本机记住令牌」后才写入本机存储（仅限个人私有设备，不会经网络传给第三方），退出即清除。</li>
          <li>私有单人工具：练习记录、学校试卷与个人信息不会被公开传播。</li>
          <li>只有管理员人工审核发布的题目才会出现；当前演示数据均为虚构测试数据。</li>
        </ul>
      </section>
    </main>
  )
}
