import { useCallback, useEffect, useState } from 'react'
import { ApiError, describeError, type ApiClient, type QuestionVersion, type SourceDetail } from '../../api'
import { QUESTION_STATUS_LABELS, excerpt } from '../../copy'
import { KindBadge } from '../../components/Badges'
import { Note } from '../../components/Note'
import { RichText } from '../../rich'
import type { NoticeTone } from '../../components/Notice'

type Notify = (text: string, tone?: NoticeTone) => void

/**
 * 题目草稿列表与发布：draft → 人工审核 → reviewed → 发布 → published。
 * 发布按钮仅在题源「已人工审核且版权已核实」时可用（与后端 409 拦截一致，UI 提前如实禁用）。
 */
export function QuestionVersionsCard({
  client,
  source,
  notify,
  onSourceChanged,
}: {
  client: ApiClient
  source: SourceDetail
  notify: Notify
  onSourceChanged: () => Promise<void>
}) {
  const [versions, setVersions] = useState<QuestionVersion[] | null>(null)
  const [loadError, setLoadError] = useState('')
  const [busyId, setBusyId] = useState<string | null>(null)

  const reload = useCallback(async () => {
    try {
      setVersions(await client.sourceQuestions(source.id))
      setLoadError('')
    } catch (e) {
      setLoadError(describeError(e))
    }
  }, [client, source.id])

  useEffect(() => {
    void reload()
    // source 对象在 AdminView 每次刷新（任何变更后）都是新引用：确认导入令附件转 confirmed
    // 但 attachments/reviews 计数不变，以对象本身为重载信号，草稿列表才不陈旧。
  }, [reload, source])

  // 后端发布条件：版本已人工审核 + 题源 verified + 版权状态已核实（licensed / personal_use_reviewed）。
  const canPublish = source.source.verified && source.source.rights_status !== 'unknown'

  async function review(version: QuestionVersion) {
    setBusyId(version.id)
    try {
      await client.reviewQuestion(version.id)
      notify(`第 ${version.version} 版已标记为人工审核，可以发布。`, 'success')
      await reload()
    } catch (e) {
      notify(describeError(e), 'error')
    } finally {
      setBusyId(null)
    }
  }

  async function publish(version: QuestionVersion) {
    setBusyId(version.id)
    try {
      await client.publishQuestion(version.id)
      notify('题目已发布，现在会进入练习与诊断的取题池。', 'success')
      await reload()
      await onSourceChanged()
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        notify(describeError(e), 'caution')
      } else {
        notify(describeError(e), 'error')
      }
    } finally {
      setBusyId(null)
    }
  }

  return (
    <section className="card" aria-label="题目草稿与发布">
      <div className="card-head">
        <h2>题目草稿与发布</h2>
        <button type="button" className="ghost small" onClick={() => void reload()}>
          刷新
        </button>
      </div>
      {!canPublish && (
        <Note tone="caution">
          发布暂不可用：题源未通过人工审核，或版权状态仍为「未核实」。请先完成上方来源人工审核，再发布题目。
        </Note>
      )}
      {versions === null ? (
        <p className="muted">{loadError === '' ? '题目加载中…' : `题目加载失败：${loadError}`}</p>
      ) : versions.length === 0 ? (
        <p className="muted">该题源还没有题目版本：上传附件并完成逐题确认导入后，草稿会出现在这里。</p>
      ) : (
        <ul className="version-list">
          {versions.map(v => (
            <li key={v.id} className="version-row">
              <div className="version-head">
                <span className={`badge qstatus-${v.status}`}>{QUESTION_STATUS_LABELS[v.status]}</span>
                <KindBadge kind={v.kind} />
                <span className="muted tiny">
                  v{v.version} · {v.question_id.slice(0, 8)}… · {v.max_points} 分
                </span>
              </div>
              <p className="version-stem">
                <RichText text={excerpt(v.stem, 90)} />
              </p>
              <div className="version-meta">
                {v.knowledge_ids.map(kid => (
                  <code className="kid" key={kid}>
                    {kid}
                  </code>
                ))}
                {v.group_context && <span className="muted tiny">含组内材料</span>}
                {v.media_attachment_id && <span className="muted tiny">含媒体附件</span>}
              </div>
              {(v.status === 'draft' || v.status === 'reviewed') && (
                <div className="version-foot">
                  {v.status === 'draft' && (
                    <button
                      type="button"
                      className="ghost small"
                      disabled={busyId !== null}
                      onClick={() => void review(v)}
                    >
                      {busyId === v.id ? '提交中…' : '人工审核通过'}
                    </button>
                  )}
                  {v.status === 'reviewed' && (
                    <>
                      <button
                        type="button"
                        className="primary small"
                        disabled={!canPublish || busyId !== null}
                        title={canPublish ? undefined : '题源未通过人工审核（或版权未核实），发布暂不可用'}
                        onClick={() => void publish(v)}
                      >
                        {busyId === v.id ? '发布中…' : '发布'}
                      </button>
                      {!canPublish && <span className="version-blocked">题源未通过人工审核（或版权未核实），发布暂不可用</span>}
                    </>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
