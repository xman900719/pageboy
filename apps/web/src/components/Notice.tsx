import { useEffect } from 'react'

export type NoticeTone = 'info' | 'success' | 'caution' | 'error'
export type NoticeData = { text: string; tone: NoticeTone }

export function Notice({ notice, onClose }: { notice: NoticeData | null; onClose: () => void }) {
  useEffect(() => {
    if (!notice) return
    const timer = window.setTimeout(onClose, 6000)
    return () => window.clearTimeout(timer)
  }, [notice, onClose])

  if (!notice) return null
  return (
    <div className={`toast ${notice.tone}`} role="status">
      <span>{notice.text}</span>
      <button type="button" onClick={onClose} aria-label="关闭提示">
        ×
      </button>
    </div>
  )
}
