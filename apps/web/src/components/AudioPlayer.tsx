import { useEffect, useState } from 'react'
import type { ApiClient } from '../api'

/**
 * Listening material: same-origin attachment fetched with the Authorization header,
 * then object-URL'd into a native audio element. Object URL is revoked on unmount.
 */
export function AudioPlayer({ client, attachmentId }: { client: ApiClient; attachmentId: string }) {
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [url, setUrl] = useState('')
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    let cancelled = false
    let objectUrl: string | null = null
    setStatus('loading')
    client
      .fetchAttachment(attachmentId)
      .then(blob => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
        setStatus('ready')
      })
      .catch(() => {
        if (!cancelled) setStatus('error')
      })
    return () => {
      cancelled = true
      if (objectUrl !== null) URL.revokeObjectURL(objectUrl)
    }
  }, [client, attachmentId, retry])

  return (
    <div className="audio">
      <span className="audio-label">听力材料</span>
      {status === 'ready' && <audio controls src={url} preload="metadata" />}
      {status === 'loading' && <span className="muted">音频加载中…</span>}
      {status === 'error' && (
        <>
          <span className="muted">音频加载失败</span>
          <button type="button" className="ghost small" onClick={() => setRetry(n => n + 1)}>
            重试
          </button>
        </>
      )}
    </div>
  )
}
