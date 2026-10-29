import { useCallback, useEffect, useState } from 'react'
import { ApiError, describeError, type ApiClient, type Plan, type PoolHealth, type ProfileEntry, type Subject, type Validation } from '../api'
import { GOAL_NOTE, pct, type ViewId } from '../copy'
import { Note } from '../components/Note'
import { PlanStepList } from '../components/PlanStepList'
import { PoolHealthCard } from '../components/PoolHealthCard'
import { ValidationPanel } from '../components/ValidationPanel'

type Notify = (text: string, tone?: 'info' | 'success' | 'caution' | 'error') => void
type PlanState = { status: 'loading' | 'goal' | 'error' | 'ok'; plan: Plan | null; errorText: string }

/** ① 精简首页: goal state + per-knowledge plan status (缺证据解释) + compact validation line. */
export function HomeView({ client, subject, notify, goView }: { client: ApiClient; subject: Subject; notify: Notify; goView: (view: ViewId) => void }) {
  const [planState, setPlanState] = useState<PlanState>({ status: 'loading', plan: null, errorText: '' })
  const [profiles, setProfiles] = useState<Record<string, ProfileEntry>>({})
  const [validation, setValidation] = useState<Validation | null>(null)
  const [poolHealth, setPoolHealth] = useState<PoolHealth | null>(null)
  const [loading, setLoading] = useState(true)
  const [goalOpen, setGoalOpen] = useState(false)
  const [target, setTarget] = useState(subject === 'physics' ? 70 : 90)
  const [minutes, setMinutes] = useState(15)
  const [savingGoal, setSavingGoal] = useState(false)

  const maxPoints = subject === 'physics' ? 80 : 100

  const refresh = useCallback(async () => {
    setLoading(true)
    const [planRes, profileRes, validationRes, poolRes] = await Promise.allSettled([client.plan(subject), client.profile(subject), client.validation(subject), client.poolHealth(subject)])
    if (planRes.status === 'fulfilled') {
      setPlanState({ status: 'ok', plan: planRes.value, errorText: '' })
    } else {
      const goalRequired = planRes.reason instanceof ApiError && planRes.reason.status === 409
      setPlanState({ status: goalRequired ? 'goal' : 'error', plan: null, errorText: describeError(planRes.reason) })
    }
    if (profileRes.status === 'fulfilled') {
      setProfiles(Object.fromEntries(profileRes.value.knowledge.map(entry => [entry.knowledge_id, entry])))
    }
    if (validationRes.status === 'fulfilled') setValidation(validationRes.value)
    if (poolRes.status === 'fulfilled') setPoolHealth(poolRes.value)
    setLoading(false)
  }, [client, subject])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function saveGoal() {
    setSavingGoal(true)
    try {
      const saved = await client.setGoal({ subject, targetPoints: Number(target), maxPoints, minutesPerDay: Number(minutes) })
      notify(`目标已保存（第 ${saved.version} 版）。${GOAL_NOTE}`, 'success')
      setGoalOpen(false)
      await refresh()
    } catch (e) {
      notify(describeError(e), 'error')
    } finally {
      setSavingGoal(false)
    }
  }

  const plan = planState.plan
  const goalForm = (
    <div className="goal-form">
      <div className="goal-fields">
        <label>
          科目目标分（满分 {maxPoints}）
          <input type="number" min={0} max={maxPoints} value={target} onChange={e => setTarget(Number(e.target.value))} />
        </label>
        <label>
          每天练习分钟数
          <input type="number" min={5} max={240} value={minutes} onChange={e => setMinutes(Number(e.target.value))} />
        </label>
      </div>
      <button type="button" className="primary" onClick={saveGoal} disabled={savingGoal}>
        {savingGoal ? '保存中…' : '保存目标'}
      </button>
      <p className="muted">
        英语听说和物理实验部分暂未覆盖完整训练；规划阈值按目标比例取 70% / 80% / 90%，是未校准的规划假设。{GOAL_NOTE}
      </p>
    </div>
  )

  return (
    <div className="home-grid">
      <section className="card" aria-label="目标与学习计划">
        <div className="card-head">
          <h2>目标与学习计划</h2>
          {plan && (
            <button type="button" className="ghost small" onClick={() => setGoalOpen(open => !open)}>
              {goalOpen ? '收起目标表单' : '修改目标'}
            </button>
          )}
        </div>

        {plan ? (
          <div className="goal-summary">
            <span className="goal-stat">目标版本 v{plan.goal_version}</span>
            <span className="goal-stat">每天 {plan.minutes_per_day} 分钟</span>
            <span className="goal-stat">规划阈值 {pct(plan.planning_threshold)}（未校准）</span>
          </div>
        ) : planState.status === 'goal' ? (
          <Note tone="caution">还没有设定目标：设定目标后才会生成学习计划。</Note>
        ) : planState.status === 'error' ? (
          <Note tone="caution">学习计划加载失败：{planState.errorText}</Note>
        ) : (
          <p className="muted">学习计划加载中…</p>
        )}

        {(goalOpen || planState.status === 'goal') && goalForm}

        {plan && (
          <>
            <p className="muted plan-meta">
              计划模型：{plan.model_version} · 未校准规则推荐，不代表分数。
            </p>
            <PlanStepList
              steps={plan.steps}
              threshold={plan.planning_threshold}
              profiles={profiles}
              onGoPractice={() => goView('practice')}
              onGoDiagnosis={() => goView('diagnosis')}
            />
            <p className="muted tiny disclaimer">{plan.disclaimer}</p>
          </>
        )}
      </section>

      <div className="home-side">
        <section className="card" aria-label="阶段对比摘要">
          <div className="card-head">
            <h2>阶段对比</h2>
            <button type="button" className="ghost small" onClick={() => goView('diagnosis')}>
              查看详情
            </button>
          </div>
          {validation ? (
            <ValidationPanel validation={validation} />
          ) : (
            <p className="muted">{loading ? '加载中…' : '阶段对比加载失败。'}</p>
          )}
        </section>

        <section className="card" aria-label="题库体检">
          <div className="card-head">
            <h2>题库体检</h2>
          </div>
          {poolHealth ? (
            <PoolHealthCard data={poolHealth} />
          ) : (
            <p className="muted">{loading ? '加载中…' : '题库体检加载失败。'}</p>
          )}
        </section>

        <Note title="这里的数字是什么">
          「观察作答率」只统计独立完成、首次见题、已审核答案自动比对的题目，样本很小；它是未校准的观察值，不是能力值，也不推算中考成绩。证据不足时只显示原因，不显示 0 分。
        </Note>
      </div>
    </div>
  )
}
