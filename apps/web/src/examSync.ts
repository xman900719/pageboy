import type {
  K12100ReportJobResult,
  K12100ReportSubjectAction,
  SchoolExamDetail,
  SchoolExamPaper,
  SchoolExamRanksPayload,
  SchoolSubject,
} from './api'

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
