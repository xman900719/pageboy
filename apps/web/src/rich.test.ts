/* ST-013：splitMathSegments 纯函数单测（正反例）。
 * 覆盖：行内 / 独立公式、文本+公式混合、不配对 `$`、空数学段、相邻公式块、换行保留、CJK 原样。 */
import { describe, expect, it } from 'vitest'
import { splitMathSegments } from './rich'

describe('splitMathSegments', () => {
  it('行内 $…$ 拆为 display:false 的数学段', () => {
    expect(splitMathSegments('设 $x^2$ 为')).toEqual([
      { type: 'text', value: '设 ' },
      { type: 'math', value: 'x^2', display: false },
      { type: 'text', value: ' 为' },
    ])
  })

  it('独立 $$…$$ 拆为 display:true 的数学段', () => {
    expect(splitMathSegments('解 $$x=1$$')).toEqual([
      { type: 'text', value: '解 ' },
      { type: 'math', value: 'x=1', display: true },
    ])
  })

  it('文本、行内与独立公式混合成有序片段', () => {
    expect(splitMathSegments('由 $a+b$ 得 $$c$$')).toEqual([
      { type: 'text', value: '由 ' },
      { type: 'math', value: 'a+b', display: false },
      { type: 'text', value: ' 得 ' },
      { type: 'math', value: 'c', display: true },
    ])
  })

  it('不配对 `$`（奇数个）整串按字面文本渲染', () => {
    expect(splitMathSegments('价格为 $5 元')).toEqual([{ type: 'text', value: '价格为 $5 元' }])
    // 前两个 `$` 原本配对，但总数为奇数 → 整串按字面文本渲染（不做局部猜测）。
    expect(splitMathSegments('解 $x$ 与 $y')).toEqual([{ type: 'text', value: '解 $x$ 与 $y' }])
  })

  it('空数学段（$$$$）按字面文本渲染', () => {
    expect(splitMathSegments('$$$$')).toEqual([{ type: 'text', value: '$$$$' }])
    expect(splitMathSegments('前 $$$$ 后')).toEqual([{ type: 'text', value: '前 $$$$ 后' }])
  })

  it('相邻公式块之间不产生空文本段', () => {
    expect(splitMathSegments('$$a$$$$b$$')).toEqual([
      { type: 'math', value: 'a', display: true },
      { type: 'math', value: 'b', display: true },
    ])
  })

  it('纯文本（CJK）原样保留为单一文本段', () => {
    expect(splitMathSegments('解方程：求根公式')).toEqual([{ type: 'text', value: '解方程：求根公式' }])
  })

  it('文本段保留换行', () => {
    expect(splitMathSegments('行一\n$x$\n行二')).toEqual([
      { type: 'text', value: '行一\n' },
      { type: 'math', value: 'x', display: false },
      { type: 'text', value: '\n行二' },
    ])
  })

  it('空字符串返回空数组', () => {
    expect(splitMathSegments('')).toEqual([])
  })
})
