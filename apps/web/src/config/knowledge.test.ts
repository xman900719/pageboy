import { describe, expect, it } from 'vitest'
import { formatKnowledgeTitle, getKnowledgeLabel } from './knowledge'

describe('knowledge 配置文件读取与本地化解析', () => {
  it('正确解析配置文件中已配置的 math.ok 与 math.listen', () => {
    expect(getKnowledgeLabel('math.ok')).toBe('达标考点（对照）')
    expect(getKnowledgeLabel('math.listen')).toBe('听力理解（音频单选）')
    expect(getKnowledgeLabel('math.gap')).toBe('差距考点（薄弱短板）')
  })

  it('未在配置文件中配置的未知知识点回退返回原始 ID', () => {
    expect(getKnowledgeLabel('physics.optics.demo')).toBe('physics.optics.demo')
    expect(getKnowledgeLabel('')).toBe('')
  })

  it('格式化标题统一返回规范纯中文', () => {
    expect(formatKnowledgeTitle('math.ok')).toBe('达标考点（对照）')
    expect(formatKnowledgeTitle('unknown.code')).toBe('unknown.code')
  })
})
