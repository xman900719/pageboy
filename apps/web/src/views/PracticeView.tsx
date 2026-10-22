import { useCallback, useEffect, useState } from 'react'
import { ApiError, describeError, type ApiClient, type AttemptResult, type AttemptRow, type NextItem, type PlanStep, type SelfAssessmentResult, type Subject } from '../api'
import { excerpt, fmtPoints, KIND_LABELS, SCORING_LABELS, shortTime } from '../copy'
import { QuestionCard } from '../components/QuestionCard'
import type { NoticeTone } from '../components/Notice'

type Notify = (text: string, tone?: NoticeTone) => void
type SessionEntry = { n: number; excerptText: string; outcome: string; tone: 'good' | 'mid' | 'wait' }

/** ② 练习/复练: rotation-visible training, per-kind answering, traceable attempt list. */
export function PracticeView({ client, subject, notify }: { client: ApiClient; subject: Subject; notify: Notify }) {
  const [item, setItem] = useState<NextItem | null>(null)
  const [busy, setBusy] = useState(false)
  const [session, setSession] = useState<SessionEntry[]>([])
  const [history, setHistory] = useState<AttemptRow[] | null>(null)
  const [steps, setSteps] = useState<PlanStep[] | null>(null)
  const [knowledgeId, setKnowledgeId] = useState('')

  const refreshHistory = useCallback(async () => {
    try {
      setHistory(await client.attempts(subject))
    } catch {
      setHistory(null)
    }
  }, [client, subject])

  useEffect(() => {
    void refreshHistory()
    client
      .plan(subject)
      .then(plan => setSteps(plan.steps))
      .catch(() => setSteps(null))
  }, [client, subject, refreshHistory])

  async function start() {
    setBusy(true)
    try {
      setItem(await client.nextItem(subject, 'training', knowledgeId || undefined))
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        notify('暂无可练的题目：请先在管理端发布已审核题目。', 'caution')
      } else {
        notify(describeError(e), 'error')
      }
    } finally {
      setBusy(false)
    }
  }

  function onSubmitted(result: AttemptResult) {
    if (!item) return
    const outcome =
      result.earned_points === null ? '待自评' : `${fmtPoints(result.earned_points)} / ${fmtPoints(result.max_points)}`
    const tone: SessionEntry['tone'] = result.earned_points === null ? 'wait' : result.earned_points === result.max_points ? 'good' : 'mid'
    setSession(entries => [...entries, { n: entries.length + 1, excerptText: excerpt(item.stem), outcome, tone }])
    void refreshHistory()
  }

  function onSelfRecorded(_record: SelfAssessmentResult) {
    void refreshHistory()
  }

  return (
    <>
      <section className="card" aria-label="练习控制">
        <div className="card-head">
          <h2>专项训练 · 复练</h2>
          {session.length > 0 && <span className="muted">本次已练 {session.length} 题</span>}
        </div>
        <p className="muted">复练会在全部已发布题中轮换取题（包括做过的题），连续取题就能看到不同题目；每次取题都会记一次曝光。</p>
        <div className="controls">
          <button type="button" className="primary" onClick={start} disabled={busy}>
            {busy ? '取题中…' : item ? '换一题（轮换取题）' : '开始练习'}
          </button>
          <label className="inline-select">
            按知识点
            {steps ? (
              <select value={knowledgeId} onChange={e => setKnowledgeId(e.target.value)}>
                <option value="">全部知识点</option>
                {steps.map(step => (
                  <option key={step.knowledge_id} value={step.knowledge_id}>
                    {step.knowledge_id}
                  </option>
                ))}
              </select>
            ) : (
              <select disabled>
                <option>全部知识点</option>
              </select>
            )}
          </label>
        </div>
        {session.length > 0 && (
          <ol className="session-log">
            {session.map(entry => (
              <li key={entry.n}>
                <b>#{entry.n}</b>
                <span className="session-stem">{entry.excerptText}</span>
                <span className={`chip ${entry.tone}`}>{entry.outcome}</span>
              </li>
            ))}
          </ol>
        )}
      </section>

      {item && (
        <QuestionCard
          key={item.exposure_id}
          client={client}
          item={item}
          badge="专项训练"
          onSubmitted={onSubmitted}
          onSelfRecorded={onSelfRecorded}
          footer={
            <button type="button" className="primary" onClick={start} disabled={busy}>
              {busy ? '取题中…' : '下一题（轮换取题）'}
            </button>
          }
        />
      )}

      <section className="card" aria-label="作答溯源记录">
        <div className="card-head">
          <h2>作答溯源记录</h2>
          <button type="button" className="ghost small" onClick={() => void refreshHistory()}>
            刷新
          </button>
        </div>
        {history === null ? (
          <p className="muted">作答记录加载中…</p>
        ) : history.length === 0 ? (
          <p className="muted">还没有作答记录。</p>
        ) : (
          <div className="table-scroll">
            <table className="trace">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>类型</th>
                  <th>我的作答</th>
                  <th>结果</th>
                  <th>评分来源</th>
                </tr>
              </thead>
              <tbody>
                {history.slice(0, 12).map(row => (
                  <tr key={row.id}>
                    <td>{shortTime(row.created_at)}</td>
                    <td>
                      {KIND_LABELS[row.kind]}
                      {row.purpose === 'evaluation' ? ' · 诊断' : ''}
                    </td>
                    <td className="answer-cell">{row.answer.trim() === '' ? '—' : excerpt(row.answer, 40)}</td>
                    <td>
                      {row.earned_points === null
                        ? row.self_assessment
                          ? `自评 ${fmtPoints(row.self_assessment.self_earned_points)} / ${fmtPoints(row.self_assessment.max_points)}`
                          : '待自评'
                        : `${fmtPoints(row.earned_points)} / ${fmtPoints(row.max_points)}`}
                    </td>
                    <td className="muted">{SCORING_LABELS[row.scoring_origin] ?? row.scoring_origin}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted tiny">自评记录与自动判分并列保存，只作溯源对照，不会进入客观证据。</p>
      </section>
    </>
  )
}
