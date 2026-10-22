import type { ReactNode } from 'react'

/** Honest-note block: neutral facts, caution (evidence shortage), or discipline (evaluation rules). */
export function Note({ tone = 'neutral', title, children }: { tone?: 'neutral' | 'caution' | 'discipline'; title?: string; children: ReactNode }) {
  return (
    <div className={`note ${tone}`}>
      {title && <b className="note-title">{title}</b>}
      <div className="note-body">{children}</div>
    </div>
  )
}
