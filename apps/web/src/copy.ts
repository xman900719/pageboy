/* All user-facing labels & honest-language copy in one place (red-line discipline). */
import type { AttachmentStatus, GapType, Kind, QuestionVersionStatus, RightsStatus } from './api'

export type ViewId = 'home' | 'practice' | 'diagnosis' | 'admin'

export const VIEWS: { id: ViewId; label: string; hint: string }[] = [
  { id: 'home', label: '首页', hint: '目标与知识点状态' },
  { id: 'practice', label: '练习', hint: '复练与轮换取题' },
  { id: 'diagnosis', label: '阶段诊断', hint: '未见题独立验证' },
  { id: 'admin', label: '审核台', hint: '题源 · 附件 · 人工发布' },
]

export const GAP_LABELS: Record<GapType, string> = {
  INSUFFICIENT_EVIDENCE: '证据不足',
  KNOWLEDGE_GAP: '知识点差距',
  NO_CONFIRMED_GAP: '暂未确认短板',
}

export const KIND_LABELS: Record<Kind, string> = {
  single_choice: '单选题',
  short_answer: '短答题',
  subjective: '主观题',
}

export const SCORING_LABELS: Record<string, string> = {
  reviewed_answer_key: '已审核答案自动比对',
  ungraded_subjective: '主观题未自动评分',
  self_assessment: '本人自评',
}

export const ACTION_LABELS: Record<string, string> = {
  diagnostic_unseen_items: '建议：领取未见题诊断',
  targeted_practice_then_unseen_evaluation: '建议：先专项复练，再做未见题验证',
  spaced_review: '建议：间隔复练巩固',
}

export const COMPARISON_REASON_LABELS: Record<string, string> = {
  insufficient_baseline: '基线侧独立题不足',
  insufficient_retest: '复测侧独立题不足',
}

export const PER_KNOWLEDGE_VERDICT_LABELS: Record<string, string> = {
  improved: '复测高于基线',
  no_improvement: '复测未高于基线',
  cannot_compare: '证据不足，无法比较',
}

export const VALIDATION_HEADLINES: Record<string, string> = {
  IMPROVED_ON_COMPARABLE_SCOPE: '可观察对比：基线 → 复测',
  NO_OBSERVED_IMPROVEMENT: '可观察对比：复测未高于基线',
  CANNOT_COMPARE: '证据不足，无法比较',
}

export const CANNOT_COMPARE_EXPLAIN = '每个知识点需要至少 3 道独立未见题的基线记录与 3 道复测记录，才能进行可观察对比。'

export const DISCIPLINE_TITLE = '独立验证纪律'
export const DISCIPLINE_TEXT =
  '阶段诊断使用你从未见过的题。领取后请独立完成：不看资料、不查工具、不问他人；已见过的题只能作为复练，不会计入新题验证。'

export const SELF_ASSESS_NOTE = '自评为独立来源记录，只可提交一次、不能修改，也不会进入客观证据。'
export const EXAM_NOTE = '学校卷只录入总分：总分不产生考点证据，也不折算成知识点表现。'
export const GOAL_NOTE = '目标只用于生成未校准的规划阈值，不作分数预测。'
export const HOME_EMPTY_PLAN = '暂无已发布知识点：请先在管理端导入、审核并发布题目。'

/* ---------- 题库审核台（ST-011） ---------- */

export const RIGHTS_STATUS_LABELS: Record<RightsStatus, string> = {
  unknown: '版权状态未核实',
  personal_use_reviewed: '个人使用已核查',
  licensed: '已获授权',
}

export const ATTACHMENT_STATUS_LABELS: Record<AttachmentStatus, string> = {
  uploaded: '待解析',
  parsed: '已解析',
  needs_manual_input: '需人工录入',
  confirmed: '已确认导入',
}

export const QUESTION_STATUS_LABELS: Record<QuestionVersionStatus, string> = {
  draft: '待人工审核',
  reviewed: '已人工审核',
  published: '已发布',
}

export const ADMIN_PIPELINE_NOTE =
  '题目录入全程由人工完成：① 新建题源 → ② 上传原始附件 → ③ 对照附件逐题录入 → ④ 逐题人工审核 → ⑤ 发布。只有已发布的题目才会进入练习与诊断取题池。'

export const REUPLOAD_RESET_NOTE = '上传附件会让题源回到「未审核」状态：需重新完成来源人工审核，否则该题源的题目无法发布。'

export const REVIEW_CHECK_LABEL = '我已人工核查来源与版权 / 适用性'

export const CONFIRM_CHECK_LABEL = '我已逐题人工核对题干、选项、答案与知识点'

/* Formatting helpers */

export function pct(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const v = Math.round(value * 1000) / 10
  return `${Number.isInteger(v) ? v : v.toFixed(1)}%`
}

export function fmtPoints(value: number): string {
  return String(Number(value.toFixed(2)))
}

export function fmtBytes(size: number): string {
  if (size >= 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MiB`
  if (size >= 1024) return `${Math.round(size / 1024)} KiB`
  return `${size} B`
}

export function shortTime(iso: string): string {
  return iso.slice(5, 16).replace('T', ' ')
}

export function excerpt(text: string, length = 26): string {
  const clean = text.replace(/\s+/g, ' ').trim()
  return clean.length > length ? `${clean.slice(0, length)}…` : clean
}

/** Options look like "A. 1" with the graded key being the bare prefix. */
export function splitOption(option: string): { key: string; text: string } {
  const match = /^([A-Za-z0-9]{1,4})\s*[.、．:：]\s*(.*)$/.exec(option)
  if (match) return { key: match[1], text: match[2] || match[1] }
  return { key: option.trim(), text: option.trim() }
}
