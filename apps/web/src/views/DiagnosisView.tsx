import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ApiError,
  describeError,
  type ApiClient,
  type AttemptResult,
  type NextItem,
  type PlanStep,
  type ProfileEntry,
  type SchoolExam,
  type Subject,
  type Validation,
} from '../api'
import { DISCIPLINE_TEXT, DISCIPLINE_TITLE, EXAM_NOTE, fmtPoints, GAP_LABELS } from '../copy'
import { QuestionCard } from '../components/QuestionCard'
import { Note } from '../components/Note'
import { PlanStepList } from '../components/PlanStepList'
import { ValidationPanel } from '../components/ValidationPanel'
import type { NoticeTone } from '../components/Notice'

type Notify = (text: string, tone?: NoticeTone) => void
type Transition = { kid: string; from: string; to: string }

/** ③ 阶段诊断: unseen-item discipline, evaluation flow → plan refresh + verdict panel, school-exam totals. */
export function DiagnosisView({ client, subject, notify, goHome }: { client: ApiClient; subject: Subject; notify: Notify; goHome: () => void }) {
  const [item, setItem] = useState<NextItem | null>(null)
  const [result, setResult] = useState<AttemptResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [validation, setValidation] = useState<Validation | null>(null)
  const [validationLoading, setValidationLoading] = useState(true)
  const [beforeSteps, setBeforeSteps] = useState<PlanStep[] | null>(null)
  const [planSteps, setPlanSteps] = useState<PlanStep[] | null>(null)
  const [planThreshold, setPlanThreshold] = useState(0)
  const [planStatus, setPlanStatus] = useState<'loading' | 'goal' | 'error' | 'ok'>('loading')
  const [profiles, setProfiles] = useState<Record<string, ProfileEntry>>({})
  const [refreshed, setRefreshed] = useState(false)
  const [resumed, setResumed] = useState(false)
  const [exams, setExams] = useState<SchoolExam[] | null>(null)
  const [examTitle, setExamTitle] = useState('学校考试')
  const [examDate, setExamDate] = useState(new Date().toISOString().slice(0, 10))
  const [examEarned, setExamEarned] = useState(72)
  const [examMax, setExamMax] = useState(100)
  const [savingExam, setSavingExam] = useState(false)

  const loadPlan = useCallback(async () => {
    try {
      const plan = await client.plan(subject)
      setPlanSteps(plan.steps)
      setPlanThreshold(plan.planning_threshold)
      setPlanStatus('ok')
      return plan.steps
    } catch (e) {
      setPlanStatus(e instanceof ApiError && e.status === 409 ? 'goal' : 'error')
      return null
    }
  }, [client, subject])

  const loadValidation = useCallback(async () => {
    setValidationLoading(true)
    try {
      setValidation(await client.validation(subject))
    } catch {
      setValidation(null)
    } finally {
      setValidationLoading(false)
    }
  }, [client, subject])

  useEffect(() => {
    setRefreshed(false)
    setItem(null)
    setResult(null)
    setResumed(false)
    // ST-018：刷新/重开/切后台后恢复最近未作答曝光，未见题不因会话丢失而空烧。
    client
      .resume(subject)
      .then(r => {
        if (r.item !== null) {
          setItem(r.item)
          setResumed(true)
        }
      })
      .catch(() => setResumed(false))
    void loadPlan().then(steps => {
      if (steps !== null) setBeforeSteps(steps)
    })
    void loadValidation()
    client
      .profile(subject)
      .then(profile => setProfiles(Object.fromEntries(profile.knowledge.map(entry => [entry.knowledge_id, entry]))))
      .catch(() => setProfiles({}))
    client
      .schoolExams(subject)
      .then(setExams)
      .catch(() => setExams(null))
  }, [client, subject, loadPlan, loadValidation])

  const transitions = useMemo<Transition[]>(() => {
    if (beforeSteps === null || planSteps === null) return []
    return planSteps.flatMap(after => {
      const before = beforeSteps.find(step => step.knowledge_id === after.knowledge_id)
      if (before === undefined || before.gap_type === after.gap_type) return []
      return [{ kid: after.knowledge_id, from: GAP_LABELS[before.gap_type], to: GAP_LABELS[after.gap_type] }]
    })
  }, [beforeSteps, planSteps])

  async function claim() {
    setBusy(true)
    try {
      const next = await client.nextItem(subject, 'evaluation')
      setItem(next)
      setResult(null)
      setRefreshed(false)
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        notify('暂无可诊断的未见题：当前科目已发布的题都已曝光，可先回练习区复练。', 'caution')
      } else {
        notify(describeError(e), 'error')
      }
    } finally {
      setBusy(false)
    }
  }

  async function onSubmitted(submitted: AttemptResult) {
    setResult(submitted)
    notify(
      submitted.evaluation_valid_unseen ? '作答已提交，正在刷新计划与阶段对比。' : '作答已提交（未计入独立验证），正在刷新计划。',
      submitted.evaluation_valid_unseen ? 'success' : 'caution',
    )
    const [planRes, validationRes] = await Promise.allSettled([loadPlan(), loadValidation()])
    if (planRes.status === 'fulfilled' && planRes.value !== null) setRefreshed(true)
    void validationRes
  }

  async function saveExam() {
    setSavingExam(true)
    try {
      const saved = await client.addSchoolExam({
        subject,
        title: examTitle.trim() === '' ? '学校考试' : examTitle.trim(),
        examDate,
        earnedPoints: Number(examEarned),
        maxPoints: Number(examMax),
        confirmedByUser: true,
      })
      notify(`学校考试已记录（${saved.id.slice(0, 8)}…）。总分不产生考点证据。`, 'success')
      setExams(await client.schoolExams(subject))
    } catch (e) {
      notify(describeError(e), 'error')
    } finally {
      setSavingExam(false)
    }
  }

  return (
    <>
      <Note tone="discipline" title={DISCIPLINE_TITLE}>
        {DISCIPLINE_TEXT}
      </Note>

      <section className="card" aria-label="领取未见题">
        <div className="card-head">
          <h2>领取未见题</h2>
          {item && <span className="muted">已领取本题，作答后自动刷新计划</span>}
        </div>
        <p className="muted">「未见题」指你从未曝光过的题。提交作答后，下方会自动刷新学习计划与阶段对比，展示知识点状态变化。</p>
        {resumed && <Note tone="discipline">已恢复上次未完成作答的题目：刷新、重开或切换应用都不会让已领取的未见题作废。</Note>}
        <button type="button" className="primary" onClick={claim} disabled={busy || item !== null}>
          {busy ? '领取中…' : item ? '已领取，请在本页作答' : '领取未见题诊断'}
        </button>
      </section>

      {planStatus === 'error' && <Note tone="caution">学习计划加载失败：诊断后将无法展示计划刷新结果，可稍后重试。</Note>}

      {item && (
        <QuestionCard
          key={item.exposure_id}
          client={client}
          item={item}
          badge="阶段诊断 · 未见题"
          onSubmitted={onSubmitted}
          footer={
            result ? (
              <button
                type="button"
                className="primary"
                onClick={() => {
                  setItem(null)
                  setResult(null)
                  setResumed(false)
                }}
              >
                完成本题
              </button>
            ) : undefined
          }
        />
      )}

      {refreshed && (
        <section className="card" aria-label="计划刷新结果">
          <h2>计划已刷新</h2>
          {transitions.length > 0 ? (
            <>
              <p className="muted">本次诊断后，知识点状态发生了以下变化：</p>
              <ul className="transitions">
                {transitions.map(transition => (
                  <li key={transition.kid}>
                    <code className="kid">{transition.kid}</code>
                    <span>
                      {transition.from} → <b>{transition.to}</b>
                    </span>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="muted">各知识点状态暂无变化；再积累一些独立未见题作答后，状态才会推进。</p>
          )}
          {planSteps !== null && (
            <>
              <h3 className="sub-head">刷新后的知识点状态</h3>
              <PlanStepList steps={planSteps} threshold={planThreshold} profiles={profiles} />
            </>
          )}
        </section>
      )}

      <section className="card" aria-label="阶段对比判决">
        <div className="card-head">
          <h2>阶段对比 · 基线 → 复测</h2>
          <button type="button" className="ghost small" onClick={() => void loadValidation()}>
            刷新
          </button>
        </div>
        {validation ? (
          <ValidationPanel validation={validation} />
        ) : (
          <p className="muted">{validationLoading ? '加载中…' : '阶段对比加载失败。'}</p>
        )}
      </section>

      <section className="card" aria-label="学校考试总分">
        <div className="card-head">
          <h2>学校考试总分</h2>
        </div>
        <Note tone="caution">{EXAM_NOTE}</Note>
        <div className="exam-form">
          <div className="goal-fields">
            <label>
              考试名称
              <input value={examTitle} onChange={e => setExamTitle(e.target.value)} placeholder="如：学校月考" />
            </label>
            <label>
              考试日期
              <input type="date" value={examDate} onChange={e => setExamDate(e.target.value)} />
            </label>
            <label>
              获得分数
              <input type="number" min={0} value={examEarned} onChange={e => setExamEarned(Number(e.target.value))} />
            </label>
            <label>
              考试满分
              <input type="number" min={1} value={examMax} onChange={e => setExamMax(Number(e.target.value))} />
            </label>
          </div>
          <button type="button" className="primary" onClick={saveExam} disabled={savingExam}>
            {savingExam ? '保存中…' : '记录已核对总分'}
          </button>
        </div>
        {exams === null ? (
          <p className="muted">已录入考试加载中…</p>
        ) : exams.length === 0 ? (
          <p className="muted">还没有录入过学校考试总分。</p>
        ) : (
          <ul className="exam-list">
            {exams.map(exam => (
              <li key={exam.id}>
                <span>{exam.exam_date}</span>
                <span className="exam-title">{exam.title}</span>
                <span>
                  <b>
                    {fmtPoints(exam.earned_points)} / {fmtPoints(exam.max_points)}
                  </b>
                </span>
                <span className={`chip ${exam.confirmed_by_user ? 'good' : 'wait'}`}>{exam.confirmed_by_user ? '已核对' : '未核对'}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {planStatus === 'goal' && (
        <Note tone="caution" title="还没有目标">
          设定目标后，诊断结果才能刷新学习计划。
          <button type="button" className="ghost small" onClick={goHome}>
            去首页设定目标
          </button>
        </Note>
      )}
    </>
  )
}
