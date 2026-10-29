import type { PoolHealth } from '../api'

/** ST-015 题库体检：只如实呈现后端计数（已发布/未见/已曝光），不推断重要性、不给分数结论。 */
export function PoolHealthCard({ data }: { data: PoolHealth }) {
  const exposedTotal = data.knowledge.reduce((total, entry) => total + entry.exposed, 0)
  return (
    <div className="pool-health">
      <div className="goal-summary">
        <span className="goal-stat">已发布 {data.questions_published} 题</span>
        <span className="goal-stat">未见题余量 {data.questions_unseen_for_evaluation} 题</span>
        <span className="goal-stat">已曝光 {exposedTotal} 题</span>
      </div>
      {data.knowledge.length === 0 ? (
        <p className="muted">暂无可体检的已发布知识点。</p>
      ) : (
        <ul className="comparison">
          {data.knowledge.map(entry => (
            <li key={entry.knowledge_id}>
              <code className="kid">{entry.knowledge_id}</code>
              <span className="step-facts">
                <span>
                  已发布 <b>{entry.published}</b>
                </span>
                <span>
                  未见 <b>{entry.unseen_for_evaluation}</b>
                </span>
                <span>
                  已曝光 <b>{entry.exposed}</b>
                </span>
                {entry.unseen_for_evaluation === 0 && <span className="muted">暂无未见题余量</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="muted tiny disclaimer">{data.disclaimer}</p>
    </div>
  )
}
