import { useState, type ReactNode } from 'react'
import { describeError, ApiError, type ApiClient, type AttemptResult, type NextItem, type ReferenceAnswer, type SelfAssessmentResult } from '../api'
import { fmtPoints, SCORING_LABELS, SELF_ASSESS_NOTE, splitOption } from '../copy'
import { KindBadge } from './Badges'
import { AudioPlayer } from './AudioPlayer'
import { Note } from './Note'
import { RichText } from '../rich'

type Phase = 'answering' | 'sending' | 'answered'

/**
 * One question exposure: stem (+ optional reading-material block, listening audio),
 * answer input per kind, submit → score feedback, and the subjective chain:
 * reference answer → self-score → recorded (repeat submission disabled).
 */
export function QuestionCard({
  client,
  item,
  badge,
  onSubmitted,
  onSelfRecorded,
  footer,
}: {
  client: ApiClient
  item: NextItem
  badge: string
  onSubmitted: (result: AttemptResult) => void
  onSelfRecorded?: (record: SelfAssessmentResult) => void
  footer?: ReactNode
}) {
  const [answer, setAnswer] = useState('')
  const [phase, setPhase] = useState<Phase>('answering')
  const [error, setError] = useState('')
  const [result, setResult] = useState<AttemptResult | null>(null)
  const [reference, setReference] = useState<ReferenceAnswer | null>(null)
  const [referenceError, setReferenceError] = useState('')
  const [selfPoints, setSelfPoints] = useState('')
  const [selfPhase, setSelfPhase] = useState<'open' | 'saving' | 'recorded'>('open')
  const [selfRecordedPoints, setSelfRecordedPoints] = useState<number | null>(null)
  const [selfError, setSelfError] = useState('')

  const subjective = result !== null && result.scoring_origin === 'ungraded_subjective'

  function loadReference(attemptId: string) {
    setReferenceError('')
    client
      .reference(attemptId)
      .then(setReference)
      .catch(e => setReferenceError(describeError(e)))
  }

  async function submit() {
    if (!answer.trim()) {
      setError('请先作答。')
      return
    }
    setError('')
    setPhase('sending')
    try {
      const record = await client.submitAttempt({ exposureId: item.exposure_id, answer })
      setResult(record)
      setPhase('answered')
      onSubmitted(record)
      if (record.scoring_origin === 'ungraded_subjective') loadReference(record.id)
    } catch (e) {
      setPhase('answering')
      setError(describeError(e))
    }
  }

  async function submitSelf() {
    if (result === null) return
    const max = result.max_points
    const value = Number(selfPoints)
    if (selfPoints === '' || Number.isNaN(value) || value < 0 || value > max) {
      setSelfError(`请输入 0 到 ${fmtPoints(max)} 之间的分数。`)
      return
    }
    setSelfError('')
    setSelfPhase('saving')
    try {
      const record = await client.selfAssessment(result.id, value)
      setSelfRecordedPoints(record.self_earned_points)
      setSelfPhase('recorded')
      onSelfRecorded?.(record)
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setSelfRecordedPoints(null)
        setSelfPhase('recorded')
      } else {
        setSelfPhase('open')
        setSelfError(describeError(e))
      }
    }
  }

  const fullScore = result !== null && result.earned_points !== null && result.earned_points === result.max_points
  const resultTone = result === null ? '' : result.earned_points === null ? 'pending' : fullScore ? 'full' : 'partial'

  return (
    <section className="card question-card" aria-label="题目">
      <div className="question-head">
        <span className="eyebrow">
          {badge} · {item.knowledge_ids.join(' / ')}
        </span>
        <KindBadge kind={item.kind} />
      </div>

      {item.group_context && (
        <figure className="reading">
          <figcaption>阅读材料</figcaption>
          <blockquote>
            <RichText text={item.group_context} />
          </blockquote>
        </figure>
      )}
      <p className="stem">
        <RichText text={item.stem} />
      </p>
      {item.media_attachment_id && <AudioPlayer client={client} attachmentId={item.media_attachment_id} />}

      {item.kind === 'single_choice' && item.options.length > 0 ? (
        <div className="options" role="radiogroup" aria-label="选项">
          {item.options.map(option => {
            const { key, text } = splitOption(option)
            return (
              <button
                type="button"
                key={option}
                role="radio"
                aria-checked={answer === key}
                disabled={phase !== 'answering'}
                className={answer === key ? 'option selected' : 'option'}
                onClick={() => setAnswer(key)}
              >
                <span className="option-key">{key}</span>
                <span>
                  <RichText text={text} />
                </span>
              </button>
            )
          })}
        </div>
      ) : item.kind === 'subjective' ? (
        <label className="answer-field">
          解答
          <textarea
            rows={5}
            value={answer}
            disabled={phase !== 'answering'}
            onChange={e => setAnswer(e.target.value)}
            placeholder="写下完整的解答或论述过程…"
          />
        </label>
      ) : (
        <label className="answer-field">
          答案
          <input
            value={answer}
            disabled={phase !== 'answering'}
            onChange={e => setAnswer(e.target.value)}
            placeholder={item.kind === 'single_choice' ? '输入选项键，如 A' : '输入答案'}
          />
        </label>
      )}

      {error && <p className="form-error">{error}</p>}
      {phase !== 'answered' && (
        <button type="button" className="primary" onClick={submit} disabled={phase === 'sending'}>
          {phase === 'sending' ? '提交中…' : '提交答案'}
        </button>
      )}

      {result && (
        <div className={`result ${resultTone}`}>
          {result.earned_points === null ? (
            <b className="result-line">暂未评分，等待自评</b>
          ) : (
            <b className="result-line">
              本题得分 {fmtPoints(result.earned_points)} / {fmtPoints(result.max_points)}
            </b>
          )}
          <span className="muted">评分来源：{SCORING_LABELS[result.scoring_origin] ?? result.scoring_origin}</span>
          {item.purpose === 'evaluation' && result.evaluation_valid_unseen !== undefined && !subjective && (
            <span className="muted">
              {result.evaluation_valid_unseen
                ? '符合独立验证条件（首次见题、独立完成），已计入阶段对比。'
                : '未计入独立验证（不满足首次见题且无提示），仅作复练记录。'}
            </span>
          )}
          {item.purpose === 'evaluation' && subjective && <span className="muted">已按独立验证条件记录；主观题不自动评分，完成后请对照参考答案自评。</span>}
        </div>
      )}

      {subjective && (
        <div className="self-chain">
          <div className="reference">
            <span className="eyebrow">参考答案</span>
            {reference ? (
              <p>
                <RichText text={reference.reference_answer} />
              </p>
            ) : referenceError ? (
              <p className="muted">
                {referenceError}{' '}
                <button type="button" className="ghost small" onClick={() => result && loadReference(result.id)}>
                  重试
                </button>
              </p>
            ) : (
              <p className="muted">加载中…</p>
            )}
          </div>
          {selfPhase === 'recorded' ? (
            <Note>
              {selfRecordedPoints !== null ? (
                <>
                  自评已记录：{fmtPoints(selfRecordedPoints)} / {fmtPoints(result?.max_points ?? item.max_points)}。
                </>
              ) : (
                '自评已记录过，不能重复提交。'
              )}
              {SELF_ASSESS_NOTE}
            </Note>
          ) : (
            <div className="self-form">
              <label>
                对照参考答案，给自己评分（0 – {fmtPoints(result?.max_points ?? item.max_points)}）
                <input
                  type="number"
                  inputMode="decimal"
                  min={0}
                  max={result?.max_points ?? item.max_points}
                  value={selfPoints}
                  onChange={e => setSelfPoints(e.target.value)}
                />
              </label>
              <button type="button" className="primary" onClick={submitSelf} disabled={selfPhase === 'saving'}>
                {selfPhase === 'saving' ? '提交中…' : '提交自评'}
              </button>
              {selfError && <p className="form-error">{selfError}</p>}
              <p className="muted">{SELF_ASSESS_NOTE}</p>
            </div>
          )}
        </div>
      )}

      {footer && <div className="question-foot">{footer}</div>}
    </section>
  )
}
