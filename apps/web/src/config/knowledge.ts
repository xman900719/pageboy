/**
 * 考点、课标条款与系统术语本地化配置加载器
 *
 * 契约：严禁在业务组件中对知识点、媒体格式、模型版本或技术编码硬编码中文映射；
 * 统一通过读取 knowledge-labels.json 与 locale-labels.json 配置文件进行动态解析。
 */
import knowledgeLabels from './knowledge-labels.json' with { type: 'json' }
import localeLabels from './locale-labels.json' with { type: 'json' }

// 类型定义：以配置文件为唯一权威事实源
export type KnowledgeMap = Record<string, string>

const LABELS: KnowledgeMap = knowledgeLabels as unknown as KnowledgeMap

export const LOCALE_PREFS = localeLabels.uiPreferences

/**
 * 获取知识点的本地化中文标签
 * @param id 知识点代号（支持经典 81 节点、2022 课标 135 候选节点及测试节点）
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

/**
 * 将 MIME 媒体类型映射为中文文件类型名称
 */
export function getMediaTypeLabel(mediaType: string): string {
  if (!mediaType) return '未知文件类型'
  const map = localeLabels.mediaTypeLabels as Record<string, string>
  return map[mediaType] ?? '通用附件文件'
}

/**
 * 将阶段对比模型版本号映射为中文说明
 */
export function getModelVersionLabel(version: string): string {
  if (!version) return '默认规则模型'
  const map = localeLabels.modelVersionLabels as Record<string, string>
  return map[version] ?? version
}

/**
 * 将默认系统操作员/审核人标识映射为中文展示名（若为人工输入的实名标识则原样保留）
 */
export function getOperatorLabel(operatorId: string | null | undefined): string {
  if (!operatorId) return '未署名操作人'
  const map = localeLabels.operatorLabels as Record<string, string>
  return map[operatorId] ?? operatorId
}

/**
 * 将版本号状态映射为中文状态标签
 */
export function getReleaseStatusLabel(status: string): string {
  const map = localeLabels.releaseStatusLabels as Record<string, string>
  return map[status] ?? status
}

/**
 * 将领域编码（如 num_alg、geom、motion_energy）映射为中文领域名称
 */
export function getDomainLabel(domainCode: string | null | undefined): string {
  if (!domainCode) return ''
  const map = localeLabels.domainLabels as Record<string, string>
  return map[domainCode] ?? getKnowledgeLabel(domainCode)
}

/**
 * 将知识库发布版本号格式化为中文主标题（如 math-v2022.1.0 -> 数学 2022 课标版 v1.0）
 */
export function formatReleaseChineseName(releaseVersion: string): string {
  if (!releaseVersion) return ''
  const match = releaseVersion.match(/^(math|chinese|english|physics)-v(\d+)(?:\.(.+))?$/)
  if (!match) return releaseVersion
  const subjMap = localeLabels.subjectLabels as Record<string, string>
  const subjName = subjMap[match[1]] ?? match[1]
  const verSuffix = match[3] ? ` 第 ${match[3]} 版` : ''
  return `${subjName} ${match[2]} 课标正式版${verSuffix}`
}

/**
 * 将课标条款 ID（如 cs:math:2022-errata:s4:num_alg:content_req:rat_num:c01）转换为易读的中文条款标题
 */
export function formatClauseTitle(
  clauseId: string,
  clauseObj?: {
    domain_title?: string | null
    theme_title?: string | null
    sub_theme?: string | null
    clause_number?: string | null
  }
): string {
  if (clauseObj) {
    const parts = [
      clauseObj.domain_title,
      clauseObj.theme_title,
      clauseObj.sub_theme,
    ].filter((x): x is string => Boolean(x && x.trim()))
    const num = clauseObj.clause_number ? `（${clauseObj.clause_number}）` : ''
    if (parts.length > 0) {
      return `${parts.join(' · ')}${num}`
    }
  }
  if (!clauseId) return ''
  const segs = clauseId.split(':')
  if (segs.length >= 6 && segs[0] === 'cs') {
    const subjMap = localeLabels.subjectLabels as Record<string, string>
    const domMap = localeLabels.domainLabels as Record<string, string>
    const modMap = localeLabels.clauseModuleLabels as Record<string, string>
    const subjName = subjMap[segs[1]] ?? segs[1]
    const domName = domMap[segs[4]] ?? segs[4]
    const modName = modMap[segs[5]] ?? segs[5]
    const tail = segs[segs.length - 1] ? `（条目 ${segs[segs.length - 1].toUpperCase()}）` : ''
    return `${subjName}课标 · ${domName} · ${modName}${tail}`
  }
  return clauseId
}

/** 校考标准错因分类有序枚举与选项（统一从本地化配置读取标签） */
export const SCHOOL_ERROR_CATEGORY_KEYS = [
  'concept',
  'calculation',
  'reading',
  'method',
  'norm',
  'other',
] as const

export const SCHOOL_ERROR_CATEGORY_OPTIONS = SCHOOL_ERROR_CATEGORY_KEYS.map(key => ({
  value: key,
  label: (localeLabels.schoolErrorCategoryLabels as Record<string, string>)[key] ?? key,
}))

/** 获取校考错因分类的中文标签 */
export function getSchoolErrorCategoryLabel(category: string | null | undefined): string {
  if (!category) return (localeLabels.schoolErrorCategoryLabels as Record<string, string>).uncategorized ?? '未归类错因'
  const map = localeLabels.schoolErrorCategoryLabels as Record<string, string>
  return map[category] ?? category
}
