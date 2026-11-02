/**
 * 考点与知识点本地化配置加载器
 *
 * 契约：严禁在业务组件中对知识点硬编码中文名称；
 * 统一通过读取 knowledge-labels.json 配置文件进行动态解析与回退。
 */
import knowledgeLabels from './knowledge-labels.json' with { type: 'json' }

// 类型定义：以配置文件为唯一权威事实源
export type KnowledgeMap = Record<string, string>

const LABELS: KnowledgeMap = knowledgeLabels as unknown as KnowledgeMap

/**
 * 获取知识点的本地化中文标签
 * @param id 知识点代号（如 math.ok, math.listen 等）
 * @returns 配置文件中配置的中文名称；若配置文件未定义则回退返回原始代号
 */
export function getKnowledgeLabel(id: string): string {
  if (!id) return ''
  return LABELS[id] ?? id
}

/**
 * 格式化展示知识点标题（统一返回纯净的本地化中文名称，杜绝英文代码裸露）
 */
export function formatKnowledgeTitle(id: string): string {
  if (!id) return ''
  return LABELS[id] ?? id
}
