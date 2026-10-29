/* ST-013：题干富文本与公式渲染。
 *
 * 安全模型：文本段一律作为 React 子节点渲染（React 自动转义，不存在原始 HTML 通道）；
 * 只有 KaTeX 由 LaTeX 生成的 HTML 才经 dangerouslySetInnerHTML 注入，用户文本绝不当作 HTML。
 *
 * 分隔符：`$$…$$` 为独立公式块（display），`$…$` 为行内公式（inline）。
 * `$` 总数为奇数（不配对）或数学段为空时，按字面文本渲染（安全回退，不猜测用户意图）。
 */
import { memo } from 'react'
import katex from 'katex'
import 'katex/dist/katex.min.css'

/** 有序片段：普通文本或 LaTeX 数学段。 */
export type RichSegment =
  | { type: 'text'; value: string }
  | { type: 'math'; value: string; display: boolean }

/**
 * 把带 `$…$` / `$$…$$` 分隔符的文本切成有序片段。纯函数、无副作用，便于单测。
 */
export function splitMathSegments(text: string): RichSegment[] {
  // 奇数个 `$` 必然存在不配对的分隔符：整串按字面文本渲染（不做局部猜测）。
  if ((text.match(/\$/g)?.length ?? 0) % 2 !== 0) {
    return text === '' ? [] : [{ type: 'text', value: text }]
  }

  const segments: RichSegment[] = []
  let buffer = ''
  let i = 0
  while (i < text.length) {
    if (text[i] === '$') {
      const display = text[i + 1] === '$'
      const openLength = display ? 2 : 1
      const close = text.indexOf(display ? '$$' : '$', i + openLength)
      const latex = close === -1 ? '' : text.slice(i + openLength, close)
      if (latex !== '') {
        if (buffer !== '') {
          segments.push({ type: 'text', value: buffer })
          buffer = ''
        }
        segments.push({ type: 'math', value: latex, display })
        i = close + openLength
        continue
      }
    }
    buffer += text[i]
    i += 1
  }
  if (buffer !== '') segments.push({ type: 'text', value: buffer })
  return segments
}

/**
 * 渲染一段可能含公式的文本。memo 按字符串缓存：同一文案不重复切分/渲染。
 */
export const RichText = memo(function RichText({ text }: { text: string }) {
  const segments = splitMathSegments(text)
  // 纯文本走原样子节点，保持既有 DOM/无障碍结构完全不变。
  if (segments.length === 1 && segments[0].type === 'text') {
    return <>{segments[0].value}</>
  }
  return (
    <>
      {segments.map((segment, index) =>
        segment.type === 'text' ? (
          <span key={index} className="rt-text">
            {segment.value}
          </span>
        ) : (
          <span
            key={index}
            className={segment.display ? 'rt-math rt-math-display' : 'rt-math rt-math-inline'}
            // 仅注入 KaTeX 生成的 HTML；LaTeX 源本身来自题干，但渲染路径已被 KaTeX 解析而非当作 HTML。
            dangerouslySetInnerHTML={{
              __html: katex.renderToString(segment.value, { throwOnError: false, displayMode: segment.display }),
            }}
          />
        ),
      )}
    </>
  )
})
