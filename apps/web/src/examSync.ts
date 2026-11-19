import type {
  K12100ReportJobResult,
  K12100ReportSubjectAction,
  SchoolExamDetail,
  SchoolExamPaper,
  SchoolExamRanksPayload,
  SchoolSubject,
  StudentSchoolReflectionItem,
} from './api'
import { REFLECTION_STARTER_FRAGMENTS } from './config/reflectionGuide'

export type SyncStep = 1 | 2 | 3 | 4

export interface MatchMeta {
  label: string
  tone: string
  action: string
}

export const MATCH_STATE_META: Record<string, MatchMeta> = {
  EXACT_MATCH: { label: '唯一精确匹配', tone: 'good', action: '可进入获取信息' },
  MATCHED: { label: '全科已关联', tone: 'good', action: '已关联校考档案' },
  PARTIAL_MATCH: { label: '部分学科已关联', tone: 'wait', action: '可补建缺失学科档案' },
  MANUAL_CONFIRMED: { label: '人工确认匹配', tone: 'good', action: '可进入获取信息' },
  AMBIGUOUS: { label: '多个候选', tone: 'wait', action: '需要人工选择' },
  CONFLICT: { label: '身份字段冲突', tone: 'bad', action: '必须人工核对' },
  NOT_FOUND: { label: '未找到候选', tone: 'wait', action: '可手工关联已有档案' },
  NEEDS_REVIEW: { label: '证据不足', tone: 'wait', action: '需要人工核对' },
  AWAITING_EXAM_DATE: { label: '平台日期不足', tone: 'bad', action: '停止自动建档，补日期后重试' },
  REJECTED: { label: '已人工忽略', tone: 'subtle', action: '原件仍保留' },
}

export const RANK_SCOPE_LABELS: Record<string, string> = {
  class: '班级排名',
  grade: '年级排名',
  school: '学校排名',
  region: '区域排名',
}

const SUBJECT_LABELS: Record<SchoolSubject, string> = {
  math: '数学',
  chinese: '语文',
  english: '英语',
  physics: '物理',
  ethics: '道法',
}

const EXAM_TYPE_LABELS: Record<string, string> = {
  monthly: '月考',
  midterm: '期中',
  final: '期末',
  unified_practice: '统一练习',
  other: '其他',
}

export function getMatchMeta(state: string | null | undefined): MatchMeta {
  return MATCH_STATE_META[state ?? ''] ?? {
    label: state || '未匹配',
    tone: 'subtle',
    action: '待处理',
  }
}

/** 下一处理步骤只由真实状态决定；没有“默认跳到成功”的分支。 */
export function getPaperNextStep(paper: Pick<SchoolExamPaper, 'status'> | null | undefined): SyncStep {
  if (!paper) return 1
  if (paper.status === 'imported') return 4
  if (paper.status === 'matched') return 3
  return 2
}

export function formatPaperExamIdentity(paper: SchoolExamPaper | null): string {
  if (!paper) return '—'
  const typeLabel = paper.header.exam_type_label
    || (paper.header.exam_type ? EXAM_TYPE_LABELS[paper.header.exam_type] ?? paper.header.exam_type : null)
  const bits = [paper.header.grade, typeLabel, paper.header.exam_date]
  return bits.filter(Boolean).join(' · ') || '卷头身份不完整'
}

export function formatPaperSubject(paper: SchoolExamPaper | null): string {
  if (!paper?.header.subject) return '学科待识别'
  return SUBJECT_LABELS[paper.header.subject] ?? paper.header.subject
}

export function formatRankValue(rank: Pick<SchoolExamRanksPayload['ranks'][number], 'rank_value' | 'participant_count'>): string {
  const total = rank.participant_count === null ? '' : ` / ${rank.participant_count} 人`
  return `第 ${rank.rank_value} 名${total}`
}

export interface ReviewCoverage {
  hasExam: boolean
  totalStatus: 'confirmed' | 'pending' | 'missing'
  totalText: string
  confirmedItems: number
  draftItems: number
  attachments: number
  rankScopes: string[]
  missingRankScopes: string[]
}

/** 派生第四步核对覆盖；缺失值不会被补成 0 分或已确认。 */
export function deriveReviewCoverage(
  detail: SchoolExamDetail | null,
  ranks: SchoolExamRanksPayload | null,
): ReviewCoverage {
  if (!detail) {
    return {
      hasExam: false,
      totalStatus: 'missing',
      totalText: '待关联考试档案',
      confirmedItems: 0,
      draftItems: 0,
      attachments: 0,
      rankScopes: [],
      missingRankScopes: ranks?.missing_scopes ?? ['class', 'grade', 'school', 'region'],
    }
  }
  return {
    hasExam: true,
    totalStatus: detail.confirmed_by_user ? 'confirmed' : 'pending',
    totalText: `${detail.earned_points} / ${detail.max_points}`,
    confirmedItems: detail.items.filter(item => item.confirmed_by_user).length,
    draftItems: detail.items.filter(item => !item.confirmed_by_user).length,
    attachments: detail.attachments.length,
    rankScopes: ranks?.ranks.map(rank => rank.scope) ?? [],
    missingRankScopes: ranks?.missing_scopes ?? ['class', 'grade', 'school', 'region'],
  }
}

export interface ReportActionMeta {
  label: string
  tone: 'good' | 'mid' | 'wait' | 'bad' | 'subtle'
}

export const REPORT_ACTION_META: Record<K12100ReportSubjectAction['action'], ReportActionMeta> = {
  created: { label: '新建待核对', tone: 'good' },
  updated: { label: '更新待核对', tone: 'mid' },
  filled: { label: '补全信息', tone: 'good' },
  unchanged: { label: '已最新', tone: 'subtle' },
  locked_conflict: { label: '锁分冲突', tone: 'bad' },
  identity_conflict: { label: '身份冲突', tone: 'bad' },
  awaiting_exam_date: { label: '缺日期未建档', tone: 'wait' },
  ambiguous: { label: '多候选歧义', tone: 'wait' },
  skipped: { label: '已跳过', tone: 'subtle' },
}

export function getReportActionMeta(action: string | null | undefined): ReportActionMeta {
  return REPORT_ACTION_META[(action ?? '') as K12100ReportSubjectAction['action']] ?? {
    label: action || '未知',
    tone: 'subtle',
  }
}

export interface ReportJobSummary {
  homeExams: number
  skippedExisting: number
  downloaded: number
  created: number
  updated: number
  filled: number
  conflicts: number
  awaitingOrAmbiguous: number
  draftsChanged: number
  cardsSynced: number
  hasIssues: boolean
}

export function summarizeReportJob(result: K12100ReportJobResult | null | undefined): ReportJobSummary {
  if (!result) {
    return {
      homeExams: 0,
      skippedExisting: 0,
      downloaded: 0,
      created: 0,
      updated: 0,
      filled: 0,
      conflicts: 0,
      awaitingOrAmbiguous: 0,
      draftsChanged: 0,
      cardsSynced: 0,
      hasIssues: false,
    }
  }
  const t = result.totals
  const conflicts = (t.locked_conflicts ?? 0) + (t.identity_conflicts ?? 0)
  const awaitingOrAmbiguous = (t.awaiting_exam_date ?? 0) + (t.ambiguous_exams ?? 0)
  return {
    homeExams: t.home_exams ?? 0,
    skippedExisting: t.skipped_existing ?? 0,
    downloaded: t.downloaded ?? 0,
    created: t.created_exams ?? 0,
    updated: t.updated_exams ?? 0,
    filled: t.filled_exams ?? 0,
    conflicts,
    awaitingOrAmbiguous,
    draftsChanged: (t.drafts_created ?? 0) + (t.drafts_updated ?? 0),
    cardsSynced: t.cards_synced ?? 0,
    hasIssues: conflicts > 0 || awaitingOrAmbiguous > 0 || (t.failures ?? 0) > 0,
  }
}

function extractLabelNumbers(label: string): number[] {
  const matches = label.match(/\d+/g)
  return matches ? matches.map(n => Number.parseInt(n, 10)) : []
}

/** 按题号中的数字序列自然升序比较（1, 2, ..., 10），无数字项排在末尾。 */
export function compareQuestionLabel(a: string, b: string): number {
  const numsA = extractLabelNumbers(a)
  const numsB = extractLabelNumbers(b)
  if (numsA.length === 0 && numsB.length === 0) {
    return a.localeCompare(b, 'zh-CN', { numeric: true })
  }
  if (numsA.length === 0) return 1
  if (numsB.length === 0) return -1
  const len = Math.min(numsA.length, numsB.length)
  for (let i = 0; i < len; i += 1) {
    if (numsA[i] !== numsB[i]) return numsA[i] - numsB[i]
  }
  if (numsA.length !== numsB.length) return numsA.length - numsB.length
  return a.localeCompare(b, 'zh-CN', { numeric: true })
}

/** 纯数字题号格式化为「第 N 题」，其余保留原样。 */
export function formatQuestionLabelHeading(label: string): string {
  const trimmed = label.trim()
  if (/^\d+$/.test(trimmed)) return `第 ${trimmed} 题`
  return trimmed
}

/** 实得分与满分一致（含浮点容差）视为作答正确。 */
export function isSchoolItemFullScore(earnedPoints: number, maxPoints: number): boolean {
  return earnedPoints >= maxPoints - 1e-6
}

export interface SchoolExamItemScoreSummary {
  totalEarned: number
  totalMax: number
  pendingCount: number
  confirmedCount: number
  correctPendingCount: number
  lostPendingCount: number
  earnedDiff: number | null
  maxDiff: number | null
}

/** 汇总本场校考已确认与待核对小题分值，并与卷面总分只读对账。 */
export function summarizeSchoolExamItemScores(
  detail: Pick<SchoolExamDetail, 'items' | 'earned_points' | 'max_points' | 'confirmed_by_user'> | null,
): SchoolExamItemScoreSummary {
  if (!detail) {
    return {
      totalEarned: 0,
      totalMax: 0,
      pendingCount: 0,
      confirmedCount: 0,
      correctPendingCount: 0,
      lostPendingCount: 0,
      earnedDiff: null,
      maxDiff: null,
    }
  }
  let totalEarned = 0
  let totalMax = 0
  let pendingCount = 0
  let confirmedCount = 0
  let correctPendingCount = 0
  let lostPendingCount = 0
  for (const it of detail.items) {
    totalEarned += it.earned_points
    totalMax += it.max_points
    if (it.confirmed_by_user) {
      confirmedCount += 1
    } else {
      pendingCount += 1
      if (isSchoolItemFullScore(it.earned_points, it.max_points)) {
        correctPendingCount += 1
      } else {
        lostPendingCount += 1
      }
    }
  }
  totalEarned = Math.round(totalEarned * 100) / 100
  totalMax = Math.round(totalMax * 100) / 100
  const earnedDiff = detail.confirmed_by_user
    ? Math.round((totalEarned - detail.earned_points) * 100) / 100
    : null
  const maxDiff = detail.max_points > 0
    ? Math.round((totalMax - detail.max_points) * 100) / 100
    : null
  return {
    totalEarned,
    totalMax,
    pendingCount,
    confirmedCount,
    correctPendingCount,
    lostPendingCount,
    earnedDiff,
    maxDiff,
  }
}

export interface DraftBasisTag {
  kind: 'source' | 'qtype' | 'match'
  label: string
}

const CONFIDENCE_MATCH_TAG: Record<string, string> = {
  auto_matched: '关键词匹配',
  ai_matched: 'AI 语义匹配',
  type_inferred: '题型考纲先验',
  external_sync: '同步平台推荐',
  high: '高置信识别',
  medium: '常规草稿',
  skeleton_only: '骨架匹配',
}

/** 将后端冗长的 draft_reason 与 draft_confidence 拆解为方式一结构化识别依据微标签（最多 3 枚）。 */
export function parseDraftBasisTags(draftReason?: string | null, draftConfidence?: string | null): DraftBasisTag[] {
  const raw = String(draftReason || '').trim()
  const conf = String(draftConfidence || '').trim().toLowerCase()
  const tags: DraftBasisTag[] = []

  const pageMatch = raw.match(/分析报告册第\s*(\d+)\s*页/)
  if (pageMatch) {
    tags.push({ kind: 'source', label: `报告册P${pageMatch[1]}` })
  } else if (/原卷/.test(raw)) {
    tags.push({ kind: 'source', label: '原卷文字层' })
  } else if (/平台/.test(raw) || conf === 'external_sync') {
    tags.push({ kind: 'source', label: '成绩平台同步' })
  } else if (raw) {
    tags.push({ kind: 'source', label: '识别草稿' })
  }

  const qtypeMatch = raw.match(/题型\s*[=＝:]\s*([^\s；;，,]+)/)
  if (qtypeMatch && qtypeMatch[1] && !['未知', 'None'].includes(qtypeMatch[1])) {
    tags.push({ kind: 'qtype', label: qtypeMatch[1] })
  }

  const segments = raw
    .split(/[；;]/)
    .map(s => s.trim())
    .filter(Boolean)
  const matchSeg = [...segments]
    .reverse()
    .find(seg => /(?:关键词|特征词|命中|AI|先验|道法主题|DeepSeek|考纲)/i.test(seg) && !/^分析报告册第/.test(seg) && !/^题型/.test(seg))

  if (matchSeg) {
    const cleanMatch = matchSeg.length > 18 ? `${matchSeg.slice(0, 17)}…` : matchSeg
    tags.push({ kind: 'match', label: cleanMatch })
  } else if (conf && CONFIDENCE_MATCH_TAG[conf]) {
    tags.push({ kind: 'match', label: CONFIDENCE_MATCH_TAG[conf] })
  }

  return tags
}

const PERFUNCTORY_CLICHES = [
  '下次一定注意',
  '下次注意',
  '下次认真',
  '下次小心',
  '认真审题',
  '仔细审题',
  '多做练习',
  '多刷题',
  '多做题',
  '好好复习',
  '加强练习',
  '粗心大意',
  '太粗心',
  '粗心了',
  '粗心',
  '马虎大意',
  '马虎了',
  '马虎',
  '大意了',
  '大意',
  '不知道',
  '不会做',
  '不会',
  '不懂',
  '忘了',
  '忘记了',
  '没看清',
  '没看懂',
  '看错了',
  '算错了',
  '写错了',
  '做错了',
  '蒙错了',
  '乱写的',
  '随便',
  '哈哈',
  '呵呵',
  '测试',
  '略',
]

function extractEffectiveChars(text: string): string {
  return (text.match(/[\u4e00-\u9fffA-Za-z]/g) ?? []).join('')
}

function stripStarterFragments(text: string): string {
  let cleaned = text
  for (const frag of REFLECTION_STARTER_FRAGMENTS) {
    cleaned = cleaned.split(frag).join('')
  }
  return cleaned
}

function stripPerfunctoryCliches(text: string): string {
  let cleaned = stripStarterFragments(text)
  for (const phrase of PERFUNCTORY_CLICHES) {
    cleaned = cleaned.split(phrase).join('')
  }
  return extractEffectiveChars(cleaned)
}

/** 前端本地预检（与后端 Stage 1 规则同源），不通过时返回书童追问提示。 */
export function validateReflectionDraftLocally(stuckPoint: string, fixStrategy: string): string | null {
  const stuck = stuckPoint.trim()
  const fix = fixStrategy.trim()
  const stuckEff = extractEffectiveChars(stripStarterFragments(stuck))
  const fixEff = extractEffectiveChars(stripStarterFragments(fix))

  if (stuckEff.length < 8) {
    return '能再具体说说当时卡在哪一步、或者漏掉了哪个条件吗？（还需再补充几句具体细节）'
  }
  if (fixEff.length < 8) {
    return '给下次的自己留一句具体的提醒吧：遇到这类题先做什么、或者用什么方法检查？'
  }
  if (stuckEff.length + fixEff.length < 20) {
    return '还差一点点细节，再多写几句关键条件或检查动作，下次遇到就能稳稳拿分啦。'
  }
  if (stuckEff.toLowerCase() === fixEff.toLowerCase()) {
    return '“当时卡在哪”和“下次怎么提醒自己”别写一模一样的哦，分开说说原因和办法。'
  }

  for (const [label, raw, eff] of [
    ['这一步卡点', stuck, stuckEff],
    ['给下次的提醒', fix, fixEff],
  ] as const) {
    if (/(.)\1{3,}/.test(raw.replace(/\s+/g, ''))) {
      return `「${label}」好像出现了连续重复的字符，用自己的话再写清楚一点吧。`
    }
    const chars = eff.toLowerCase().split('')
    const unique = new Set(chars)
    if (unique.size < 5) {
      return `「${label}」用字太重复啦，试着写一句完整的话说明白。`
    }
    let maxCount = 0
    for (const ch of unique) {
      const cnt = chars.filter(c => c === ch).length
      if (cnt > maxCount) maxCount = cnt
    }
    if (maxCount / chars.length > 0.45) {
      return `「${label}」有不少重复字符，再补充一点真实的思考过程吧。`
    }
  }

  if (stripPerfunctoryCliches(stuck).length < 5) {
    return '先别只怪“粗心/没看清”，试着写明是哪一个条件、符号或步骤出了偏差？'
  }
  if (stripPerfunctoryCliches(fix).length < 5) {
    return '“下次注意”容易忘，换成“如果看到…我就先…”的具体动作会更管用哦。'
  }
  return null
}

export interface SchoolReflectionExamGroup {
  examId: string
  examTitle: string
  examDate: string
  pendingCount: number
  needsRevisionCount: number
  completedCount: number
  items: StudentSchoolReflectionItem[]
}

/** 按校考台账（exam_id）将失分复盘条目分组，保留场次先后顺序并汇总各场待复盘/已完成数。 */
export function groupSchoolReflectionsByExam(
  items: StudentSchoolReflectionItem[],
): SchoolReflectionExamGroup[] {
  const map = new Map<string, SchoolReflectionExamGroup>()
  for (const it of items) {
    let group = map.get(it.exam_id)
    if (!group) {
      group = {
        examId: it.exam_id,
        examTitle: it.exam_title,
        examDate: it.exam_date,
        pendingCount: 0,
        needsRevisionCount: 0,
        completedCount: 0,
        items: [],
      }
      map.set(it.exam_id, group)
    }
    group.items.push(it)
    if (it.reflection_status === 'completed') {
      group.completedCount += 1
    } else {
      group.pendingCount += 1
      if (it.reflection_status === 'needs_revision') {
        group.needsRevisionCount += 1
      }
    }
  }
  return [...map.values()]
}
