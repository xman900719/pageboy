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
  const match = releaseVersion.match(/^(math|chinese|english|physics|chemistry|ethics)-v(\d+)(?:\.(.+))?$/)
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

/** 将科目标识映射为中文学科名 */
export function getSubjectLabel(subject: string | null | undefined): string {
  if (!subject) return '未知学科'
  const map = localeLabels.subjectLabels as Record<string, string>
  return map[subject] ?? subject
}

/** 将后台校考同步任务状态映射为中文进度描述 */
export function getSyncJobStateLabel(state: string | null | undefined): string {
  if (!state) return '状态未知'
  const map = localeLabels.syncJobStateLabels as Record<string, string>
  return map[state] ?? state
}

/** 将解析方式枚举（含模型后缀）映射为中文解析模式名称 */
export function getParserModeLabel(mode: string | null | undefined): string {
  if (!mode) return '标准解析'
  const map = localeLabels.parserModeLabels as Record<string, string>
  if (map[mode]) return map[mode]
  const baseMode = mode.split(':', 1)[0]
  if (map[baseMode]) return map[baseMode]
  if (mode.startsWith('deepseek_vision')) return map.deepseek_vision ?? '多模态智能识图'
  if (mode.startsWith('deepseek_')) return map.deepseek_text ?? '智能语义解析'
  if (mode.startsWith('external_')) return map.external_local_rules ?? '本地规则匹配'
  return mode
}

/** 将全科补全总分处理状态映射为中文描述 */
export function getK12ScoreStatusLabel(status: string | null | undefined): string {
  if (!status) return '状态未知'
  const map = localeLabels.k12ScoreStatusLabels as Record<string, string>
  return map[status] ?? status
}

/** 将原卷题干提取模式映射为中文描述 */
export function getStemModeLabel(mode: string | null | undefined): string {
  if (!mode) return '常规提取'
  const map = localeLabels.stemModeLabels as Record<string, string>
  return map[mode] ?? mode
}

/** 将分析报告册处理状态映射为中文状态标签 */
export function getReportStatusLabel(status: string | null | undefined): string {
  if (!status) return '待处理'
  const map = localeLabels.reportStatusLabels as Record<string, string>
  return map[status] ?? status
}

/** 将分析报告册匹配状态映射为中文描述 */
export function getReportMatchStateLabel(state: string | null | undefined): string {
  if (!state) return '待处理'
  const map = localeLabels.reportMatchStateLabels as Record<string, string>
  return map[state] ?? state
}

/** 将报告册学科关联状态映射为中文描述 */
export function getReportLinkMatchLabel(match: string | null | undefined): string {
  if (!match) return '待关联'
  const map = localeLabels.reportLinkMatchLabels as Record<string, string>
  return map[match] ?? match
}

/** 将报告册统计口径比对状态映射为中文描述 */
export function getReportScopeStatusLabel(scope: string | null | undefined): string {
  if (!scope) return '待核对'
  const map = localeLabels.reportScopeStatusLabels as Record<string, string>
  return map[scope] ?? scope
}

/** 将知识节点层级数字映射为中文层级标识 */
export function getKnowledgeNodeLevelLabel(level: number | null | undefined): string {
  const key = String(level ?? 3)
  const map = localeLabels.knowledgeNodeLevelLabels as Record<string, string>
  return map[key] ?? '知识节点'
}

/** 将新旧考点迁移映射动作枚举映射为中文操作标签 */
export function getLegacyMappingActionLabel(action: string | null | undefined): string {
  if (!action) return '待核定'
  const map = localeLabels.legacyMappingActionLabels as Record<string, string>
  return map[action] ?? action
}

export interface KnowledgeOption {
  code: string
  label: string
  isCandidate: boolean
}

/**
 * 获取指定科目的可选知识点中文列表（从配置字典实时提取）
 * @param subject 学科英文标识
 * @param includeCandidate 是否包含 *_cand. 候选体系节点，默认不包含以保持与正式题库一致
 */
export function getSubjectKnowledgeOptions(
  subject: string | null | undefined,
  includeCandidate = false
): KnowledgeOption[] {
  if (!subject) return []
  const formalPrefix = `${subject}.`
  const candPrefix = `${subject}_cand.`
  const out: KnowledgeOption[] = []
  for (const [code, label] of Object.entries(LABELS)) {
    if (code === '$comment') continue
    if (code.startsWith(formalPrefix)) {
      out.push({ code, label, isCandidate: false })
    } else if (includeCandidate && code.startsWith(candPrefix)) {
      out.push({ code, label, isCandidate: true })
    }
  }
  return out
}

/**
 * 将用户在输入框或下拉中选择的中文知识点名称还原为规范知识点代码；
 * 若本身已是代码或自定义文本（如道法综合主题），则原样返回去空白后的字符串。
 */
export function resolveKnowledgeCodeInput(input: string, subject?: string | null): string {
  const trimmed = input.trim()
  if (!trimmed) return ''
  if (LABELS[trimmed]) return trimmed

  const entries = Object.entries(LABELS).filter(([k]) => k !== '$comment')
  // 若指定了学科，优先在该学科正式知识点、其次候选知识点中反查中文名称
  if (subject) {
    const formalPrefix = `${subject}.`
    const candPrefix = `${subject}_cand.`
    const formalMatch = entries.find(([k, v]) => k.startsWith(formalPrefix) && v === trimmed)
    if (formalMatch) return formalMatch[0]
    const candMatch = entries.find(([k, v]) => k.startsWith(candPrefix) && v === trimmed)
    if (candMatch) return candMatch[0]
  }
  const anyFormal = entries.find(([k, v]) => !k.includes('_cand.') && v === trimmed)
  if (anyFormal) return anyFormal[0]
  const anyMatch = entries.find(([, v]) => v === trimmed)
  return anyMatch ? anyMatch[0] : trimmed
}
