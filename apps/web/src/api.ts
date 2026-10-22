/* API surface (contracts/openapi.yaml) + in-memory bearer client. Token never persists. */

export type Subject = 'math' | 'chinese' | 'english' | 'physics'
export type Kind = 'single_choice' | 'short_answer' | 'subjective'
export type Purpose = 'training' | 'evaluation'
export type GapType = 'INSUFFICIENT_EVIDENCE' | 'KNOWLEDGE_GAP' | 'NO_CONFIRMED_GAP'

export const SUBJECTS: Subject[] = ['math', 'chinese', 'english', 'physics']
export const SUBJECT_LABELS: Record<Subject, string> = { math: '数学', chinese: '语文', english: '英语', physics: '物理' }

export class ApiError extends Error {
  constructor(readonly status: number, readonly code: string) {
    super(code)
  }
}

export interface NextItem {
  exposure_id: string
  question_version_id: string
  purpose: Purpose
  unseen_at_exposure: boolean
  stem: string
  kind: Kind
  group_context: string | null
  media_attachment_id: string | null
  options: string[]
  max_points: number
  subject: Subject
  knowledge_ids: string[]
}

export interface AttemptResult {
  id: string
  status: 'recorded' | 'already_recorded'
  earned_points: number | null
  max_points: number
  scoring_origin: 'reviewed_answer_key' | 'ungraded_subjective'
  evaluation_valid_unseen?: boolean
}

export interface ReferenceAnswer {
  reference_answer: string
  max_points: number
}

export interface SelfAssessmentResult {
  id: string
  attempt_id: string
  self_earned_points: number
  max_points: number
  scoring_origin: string
}

export interface PlanStep {
  knowledge_id: string
  gap_type: GapType
  action: string
  reason: string
  priority: number
  observed_rate?: number
}

export interface Plan {
  subject: Subject
  goal_version: number
  model_version: string
  target_mapping_status: string
  planning_threshold: number
  minutes_per_day: number
  steps: PlanStep[]
  disclaimer: string
}

export interface ProfileEntry {
  knowledge_id: string
  sample_size: number
  observed_rate: number
  evidence_status: string
}

export type ValidationVerdict = 'CANNOT_COMPARE' | 'IMPROVED_ON_COMPARABLE_SCOPE' | 'NO_OBSERVED_IMPROVEMENT'

export interface KnowledgeComparison {
  knowledge_id: string
  verdict: 'improved' | 'no_improvement' | 'cannot_compare'
  baseline_rate?: number
  retest_rate?: number
  baseline_items: number
  retest_items: number
  reason?: string
}

export interface Validation {
  subject: Subject
  model_version: string
  verdict: ValidationVerdict
  comparable: boolean
  knowledge: KnowledgeComparison[]
  disclaimer: string
}

export interface AttemptRow {
  id: string
  question_version_id: string
  purpose: Purpose
  kind: Kind
  answer: string
  earned_points: number | null
  max_points: number
  scoring_origin: string
  hints_used: boolean
  self_assessment: { id: string; self_earned_points: number; max_points: number; scoring_origin: string } | null
  created_at: string
}

export interface SchoolExam {
  id: string
  title: string
  exam_date: string
  earned_points: number
  max_points: number
  confirmed_by_user: boolean
}

export interface GoalResult {
  id: string
  version: number
  status: string
}

export interface SchoolExamResult {
  id: string
  status: string
  knowledge_evidence_created: boolean
}

export interface Client {
  verify(): Promise<unknown>
  nextItem(subject: Subject, purpose: Purpose, knowledgeId?: string): Promise<NextItem>
  submitAttempt(input: { exposureId: string; answer: string }): Promise<AttemptResult>
  reference(attemptId: string): Promise<ReferenceAnswer>
  selfAssessment(attemptId: string, points: number): Promise<SelfAssessmentResult>
  attempts(subject: Subject): Promise<AttemptRow[]>
  profile(subject: Subject): Promise<{ knowledge: ProfileEntry[] }>
  plan(subject: Subject): Promise<Plan>
  validation(subject: Subject): Promise<Validation>
  setGoal(input: { subject: Subject; targetPoints: number; maxPoints: number; minutesPerDay: number }): Promise<GoalResult>
  schoolExams(subject: Subject): Promise<SchoolExam[]>
  addSchoolExam(input: {
    subject: Subject
    title: string
    examDate: string
    earnedPoints: number
    maxPoints: number
    confirmedByUser: boolean
  }): Promise<SchoolExamResult>
  fetchAttachment(attachmentId: string): Promise<Blob>
}

export function createClient(token: string): Client {
  const call = async <T>(path: string, method = 'GET', body?: unknown): Promise<T> => {
    const res = await fetch(path, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
    const text = await res.text()
    let payload: unknown = null
    try {
      payload = text ? JSON.parse(text) : null
    } catch {
      payload = null
    }
    if (!res.ok) {
      const detail =
        payload !== null && typeof payload === 'object' && 'detail' in payload && typeof (payload as { detail: unknown }).detail === 'string'
          ? (payload as { detail: string }).detail
          : `HTTP ${res.status}`
      throw new ApiError(res.status, detail)
    }
    return payload as T
  }

  return {
    verify: () => call<unknown>('/api/subjects'),
    nextItem: (subject, purpose, knowledgeId) =>
      call<NextItem>(`/api/practice/next?subject=${subject}&purpose=${purpose}${knowledgeId ? `&knowledge_id=${encodeURIComponent(knowledgeId)}` : ''}`),
    submitAttempt: ({ exposureId, answer }) =>
      call<AttemptResult>('/api/practice/attempts', 'POST', {
        client_attempt_id: crypto.randomUUID(),
        exposure_id: exposureId,
        answer,
        hints_used: false,
      }),
    reference: attemptId => call<ReferenceAnswer>(`/api/practice/attempts/${attemptId}/reference`),
    selfAssessment: (attemptId, points) =>
      call<SelfAssessmentResult>(`/api/practice/attempts/${attemptId}/self-assessment`, 'POST', { self_earned_points: points }),
    attempts: subject => call<AttemptRow[]>(`/api/practice/attempts?subject=${subject}`),
    profile: subject => call<{ knowledge: ProfileEntry[] }>(`/api/guidance/profile?subject=${subject}`),
    plan: subject => call<Plan>(`/api/guidance/plan?subject=${subject}`),
    validation: subject => call<Validation>(`/api/guidance/validation?subject=${subject}`),
    setGoal: ({ subject, targetPoints, maxPoints, minutesPerDay }) =>
      call<GoalResult>('/api/goals', 'POST', { subject, target_points: targetPoints, max_points: maxPoints, minutes_per_day: minutesPerDay }),
    schoolExams: subject => call<SchoolExam[]>(`/api/school-exams?subject=${subject}`),
    addSchoolExam: ({ subject, title, examDate, earnedPoints, maxPoints, confirmedByUser }) =>
      call<SchoolExamResult>('/api/school-exams', 'POST', {
        subject,
        title,
        exam_date: examDate,
        earned_points: earnedPoints,
        max_points: maxPoints,
        confirmed_by_user: confirmedByUser,
      }),
    fetchAttachment: async attachmentId => {
      const res = await fetch(`/api/admin/attachments/${attachmentId}/download`, { headers: { Authorization: `Bearer ${token}` } })
      if (!res.ok) throw new ApiError(res.status, 'ATTACHMENT_UNAVAILABLE')
      return await res.blob()
    },
  }
}

export type ApiClient = ReturnType<typeof createClient>

const API_CODE_TEXT: Record<string, string> = {
  GOAL_REQUIRED: '需要先设定目标，才能生成学习计划。',
  NO_ELIGIBLE_QUESTION: '暂无可取的题目。',
  SELF_ASSESSMENT_ALREADY_RECORDED: '自评已记录过，不能重复提交。',
  EXPOSURE_ALREADY_SUBMITTED: '这道题已经提交过作答。',
  IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD: '提交冲突，请重试。',
  REFERENCE_NOT_APPLICABLE: '该题型没有参考答案。',
}

export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return '访问令牌无效或已过期，请重新输入。'
    return API_CODE_TEXT[error.code] ?? error.code
  }
  if (error instanceof TypeError) return '无法连接本地服务（默认 :8000），请确认 API 是否在运行。'
  return String(error)
}
