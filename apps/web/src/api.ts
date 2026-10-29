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

export interface PoolHealthKnowledge {
  knowledge_id: string
  published: number
  unseen_for_evaluation: number
  exposed: number
}

export interface PoolHealth {
  subject: Subject
  model_version: string
  knowledge: PoolHealthKnowledge[]
  questions_published: number
  questions_unseen_for_evaluation: number
  evaluation_available: boolean
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

/* ---------- 题库审核台（ST-011）：题源 → 附件 → 逐题确认 → 审核 → 发布 ---------- */

export type RightsStatus = 'unknown' | 'personal_use_reviewed' | 'licensed'
export type AttachmentStatus = 'uploaded' | 'parsed' | 'needs_manual_input' | 'confirmed'
export type QuestionVersionStatus = 'draft' | 'reviewed' | 'published'

export interface SourceMeta {
  title: string
  subject: Subject
  exam_year: number | null
  source_url: string | null
  rights_status: RightsStatus
  verified: boolean
}

export interface SourceReviewMeta {
  exam_year: number
  source_url: string
  acquired_at: string
  rights_status: RightsStatus
  rights_basis: string
  applicable: boolean
  applicability_note: string
  reviewed_by_human: boolean
}

export interface SourceReviewRecord {
  id: string
  metadata: SourceReviewMeta
  reviewed_by: string
  created_at: string
}

export interface AttachmentOut {
  id: string
  source_document_id: string
  filename: string
  media_type: 'application/pdf' | 'image/png' | 'image/jpeg' | 'audio/mpeg' | 'audio/mp4'
  sha256: string
  byte_size: number
  status: AttachmentStatus
  extracted_text: string | null
  parser_version: string | null
  parsed_at: string | null
  confirmed_at: string | null
  created_at: string
  question_version_ids: string[]
}

export interface SourceDetail {
  id: string
  source: SourceMeta
  reviews: SourceReviewRecord[]
  attachments: AttachmentOut[]
}

export interface QuestionVersion {
  id: string
  question_id: string
  version: number
  status: QuestionVersionStatus
  reviewed_by_human: boolean
  stem: string
  kind: Kind
  options: string[]
  correct_answer: string
  knowledge_ids: string[]
  max_points: number
  group_context: string | null
  media_attachment_id: string | null
}

export interface QuestionDraftInput {
  source_document_id: string
  stem: string
  kind: Kind
  options: string[]
  correct_answer: string
  knowledge_ids: string[]
  max_points: number
  group_context?: string | null
  media_attachment_id?: string | null
}

export interface Client {
  verify(): Promise<unknown>
  nextItem(subject: Subject, purpose: Purpose, knowledgeId?: string): Promise<NextItem>
  resume(subject: Subject): Promise<{ item: NextItem | null }>
  submitAttempt(input: { exposureId: string; answer: string }): Promise<AttemptResult>
  reference(attemptId: string): Promise<ReferenceAnswer>
  selfAssessment(attemptId: string, points: number): Promise<SelfAssessmentResult>
  attempts(subject: Subject): Promise<AttemptRow[]>
  profile(subject: Subject): Promise<{ knowledge: ProfileEntry[] }>
  plan(subject: Subject): Promise<Plan>
  validation(subject: Subject): Promise<Validation>
  poolHealth(subject: Subject): Promise<PoolHealth>
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
  /* 题库审核台（ST-011）。 */
  adminSources(): Promise<SourceDetail[]>
  addSource(input: { title: string; subject: Subject; rightsStatus: RightsStatus }): Promise<{ id: string; status: string }>
  reviewSource(sourceId: string, review: SourceReviewMeta): Promise<unknown>
  uploadAttachment(sourceId: string, file: File): Promise<AttachmentOut>
  parseAttachment(attachmentId: string): Promise<AttachmentOut>
  confirmImport(attachmentId: string, questions: QuestionDraftInput[]): Promise<AttachmentOut>
  sourceQuestions(sourceId: string): Promise<QuestionVersion[]>
  reviewQuestion(versionId: string): Promise<unknown>
  publishQuestion(versionId: string): Promise<unknown>
}

export function createClient(token: string): Client {
  // 统一请求与错误解析：detail 字符串原样保留（409 等业务码由 describeError 如实呈现）。
  const request = async (path: string, init: RequestInit = {}): Promise<unknown> => {
    const res = await fetch(path, {
      ...init,
      headers: { Authorization: `Bearer ${token}`, ...(init.headers as Record<string, string>) },
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
    return payload
  }
  const call = async <T>(path: string, method = 'GET', body?: unknown): Promise<T> =>
    request(path, {
      method,
      ...(body === undefined ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
    }) as Promise<T>

  return {
    verify: () => call<unknown>('/api/subjects'),
    nextItem: (subject, purpose, knowledgeId) =>
      call<NextItem>(`/api/practice/next?subject=${subject}&purpose=${purpose}${knowledgeId ? `&knowledge_id=${encodeURIComponent(knowledgeId)}` : ''}`),
    resume: subject => call<{ item: NextItem | null }>(`/api/practice/resume?subject=${subject}`),
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
    poolHealth: subject => call<PoolHealth>(`/api/guidance/pool-health?subject=${subject}`),
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
    adminSources: () => call<SourceDetail[]>('/api/admin/sources'),
    addSource: ({ title, subject, rightsStatus }) =>
      call<{ id: string; status: string }>('/api/admin/sources', 'POST', { title, subject, rights_status: rightsStatus }),
    reviewSource: (sourceId, review) => call<unknown>(`/api/admin/sources/${encodeURIComponent(sourceId)}/review`, 'POST', review),
    // 附件上传走原始二进制请求体（Content-Type 限五种媒体类型，≤10MiB 由 UI 预检）。
    uploadAttachment: (sourceId, file) =>
      request(`/api/admin/sources/${encodeURIComponent(sourceId)}/attachments?filename=${encodeURIComponent(file.name)}`, {
        method: 'POST',
        headers: { 'Content-Type': file.type },
        body: file,
      }) as Promise<AttachmentOut>,
    parseAttachment: attachmentId => call<AttachmentOut>(`/api/admin/attachments/${encodeURIComponent(attachmentId)}/parse`, 'POST'),
    confirmImport: (attachmentId, questions) =>
      call<AttachmentOut>(`/api/admin/attachments/${encodeURIComponent(attachmentId)}/confirm`, 'POST', {
        confirmed_by_human: true,
        questions,
      }),
    sourceQuestions: sourceId => call<QuestionVersion[]>(`/api/admin/sources/${encodeURIComponent(sourceId)}/questions`),
    reviewQuestion: versionId => call<unknown>(`/api/admin/questions/${encodeURIComponent(versionId)}/review`, 'POST'),
    publishQuestion: versionId => call<unknown>(`/api/admin/questions/${encodeURIComponent(versionId)}/publish`, 'POST'),
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
  /* 题库审核台（原文码缺映射时直接显示 code）。 */
  UPLOAD_HASH_MISMATCH: '附件校验失败：上传内容的哈希与预期不一致，请重新上传。',
  UNSUPPORTED_FILE_TYPE: '不支持的附件类型：仅接受 PDF / PNG / JPG / MP3 / M4A。',
  INVALID_FILE_SIZE: '附件大小不符合要求（上限 10 MiB）。',
  ATTACHMENT_STORAGE_UNAVAILABLE: '附件存储暂不可用，请稍后重试。',
  IMPORT_ALREADY_CONFIRMED: '该附件已确认导入过，不能再次解析或导入。',
  IMPORT_SOURCE_MISMATCH: '附件与题目来源不匹配，请检查录入内容。',
  IMPORT_NOT_READY_OR_ALREADY_CONFIRMED: '该附件尚未解析（或已确认导入），不能确认导入。',
  MEDIA_ATTACHMENT_INVALID: '媒体附件无效：须与题目同属一个来源且已上传。',
  IMPORT_TRANSACTION_FAILED: '导入保存失败，请重试。',
  IMPORTED_QUESTION_CONFIRMATION_REQUIRED: '导入的题目缺少确认记录，请先在附件区完成逐题确认导入。',
  QUESTION_NOT_APPROVED_FOR_PRIVATE_PUBLICATION: '来源尚未通过人工审核（或版权状态未核实）：请先完成来源人工审核，再发布题目。',
}

export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return '访问令牌无效或已过期，请重新输入。'
    return API_CODE_TEXT[error.code] ?? error.code
  }
  if (error instanceof TypeError) return '无法连接服务器，请检查网络连接后重试。'
  return String(error)
}
