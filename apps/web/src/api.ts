/* API surface (contracts/openapi.yaml) + in-memory bearer client. Token never persists. */

export type Subject = 'math' | 'chinese' | 'english' | 'physics'
// 学校考试额外支持「道法（道德与法治）」归档，核心练习/画像仍严格保持四科不变
export type SchoolSubject = Subject | 'ethics'
export type Kind = 'single_choice' | 'short_answer' | 'subjective'
export type Purpose = 'training' | 'evaluation'
export type GapType = 'INSUFFICIENT_EVIDENCE' | 'KNOWLEDGE_GAP' | 'NO_CONFIRMED_GAP'

export const SUBJECTS: Subject[] = ['math', 'chinese', 'english', 'physics']
export const SUBJECT_LABELS: Record<Subject, string> = { math: '数学', chinese: '语文', english: '英语', physics: '物理' }
export const SCHOOL_SUBJECTS: SchoolSubject[] = ['math', 'chinese', 'english', 'physics', 'ethics']
export const SCHOOL_SUBJECT_LABELS: Record<SchoolSubject, string> = {
  ...SUBJECT_LABELS,
  ethics: '道法',
}

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
  selection_reason?: string | null
  knowledge_titles?: string[]
}

export interface PracticeSessionItemPlan {
  seq: number
  question_version_id: string
  selection_reason: string
  focus_knowledge_codes: string[]
  answered: boolean
  attempt_id: string | null
  earned_points: number | null
  max_points: number
}

export interface PracticeSession {
  id: string
  subject: Subject
  purpose: Purpose
  status: 'active' | 'in_progress' | 'completed'
  target_count: number
  total_items: number
  completed_count: number
  focus_knowledge_code?: string | null
  composition_summary: Record<string, number>
  items: PracticeSessionItemPlan[]
  current_item: NextItem | null
}

export interface WrongQuestionSummary {
  attempt_id: string
  question_version_id: string
  subject: Subject
  stem: string
  kind: Kind
  options: string[]
  student_answer: string
  earned_points: number | null
  max_points: number
  selection_reason?: string | null
  knowledge_codes: string[]
  knowledge_titles: string[]
  tutor_session_id?: string | null
  created_at?: string | null
}

export interface PracticeSessionComplete {
  session_id: string
  status: 'completed'
  answered_count: number
  correct_count: number
  wrong_count: number
  subjective_count: number
  wrong_items: WrongQuestionSummary[]
}

export interface TutorTurn {
  id: string
  turn_index: number
  role: 'assistant' | 'user'
  content: string
  sanitized_guard_triggered: boolean
  created_at: string
}

export interface TutorSession {
  started: boolean
  id?: string | null
  attempt_id: string
  status?: string | null
  model_name?: string | null
  stem?: string | null
  student_answer?: string | null
  knowledge_titles: string[]
  turns: TutorTurn[]
}

export type MasteryStatus = 'mastered' | 'weak' | 'insufficient' | 'untested'

export interface KnowledgeMasteryItem {
  code: string
  name: string
  domain?: string | null
  parent_code?: string | null
  level: number
  description?: string | null
  is_leaf: boolean
  sample_size: number
  observed_rate: number | null
  mastery_status: MasteryStatus
}

export interface DomainRadarItem {
  domain_code: string
  domain_name: string
  total_topics: number
  tested_topics: number
  mastered_count: number
  weak_count: number
  insufficient_count: number
  untested_count: number
  observed_rate: number | null
}

export interface GrowthStatus {
  subject: Subject
  model_version: string
  release_version?: string | null
  planning_threshold: number
  summary_counts: Record<string, number>
  strengths: KnowledgeMasteryItem[]
  weaknesses: KnowledgeMasteryItem[]
  developing: KnowledgeMasteryItem[]
  untested_highlights: KnowledgeMasteryItem[]
  domain_radar: DomainRadarItem[]
  recent_wrong_count: number
  current_goal?: {
    version: number
    target_points: number
    max_points: number
    minutes_per_day: number
  } | null
  disclaimer: string
}

export interface KnowledgeEdge {
  source: string
  target: string
  relation: string
  edge_type: 'hierarchy' | 'prerequisite'
}

export interface KnowledgeGraph {
  subject: Subject
  release_version?: string | null
  model_version: string
  summary_counts: Record<string, number>
  nodes: KnowledgeMasteryItem[]
  edges: KnowledgeEdge[]
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
  topic: string
  gap_type: GapType
  action: string
  reason: string
  advice?: string
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
  topic: string
  status?: string
  sample_size: number
  observed_rate?: number
  score_rate?: number
  evidence_status?: string
  advice?: string
}

export type ValidationVerdict = 'CANNOT_COMPARE' | 'IMPROVED_ON_COMPARABLE_SCOPE' | 'NO_OBSERVED_IMPROVEMENT'

export interface KnowledgeComparison {
  topic: string
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

export interface SchoolPaperAttachment {
  id: string
  filename: string
  media_type: string
  sha256: string
  byte_size: number
  created_at: string
}

export interface SchoolExamItem {
  id: string
  question_label: string
  knowledge_id: string
  earned_points: number
  max_points: number
  scoring_origin: 'manual_entry' | 'ocr_draft'
  confirmed_by_user: boolean
}

export interface SchoolExamItemInput {
  question_label: string
  knowledge_id: string
  earned_points: number
  max_points: number
  scoring_origin: 'manual_entry' | 'ocr_draft'
}

export interface SchoolExamDetail extends SchoolExam {
  subject: SchoolSubject
  items: SchoolExamItem[]
  attachments: SchoolPaperAttachment[]
}

export interface GoalResult {
  id: string
  version: number
  status: string
}

export interface SchoolExamResult {
  id: string
  status?: string
  confirmed_by_user?: boolean
  earned_points?: number
  max_points?: number
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
  source_class?: string | null
  sha256?: string | null
  paper_key?: string | null
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
  media_type:
    | 'application/pdf'
    | 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    | 'image/png'
    | 'image/jpeg'
    | 'audio/mpeg'
    | 'audio/mp4'
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
  schoolExams(subject: SchoolSubject): Promise<SchoolExam[]>
  schoolExamDetail(examId: string): Promise<SchoolExamDetail>
  addSchoolExam(input: {
    subject: SchoolSubject
    title: string
    examDate: string
    earnedPoints: number
    maxPoints: number
    confirmedByUser: boolean
  }): Promise<SchoolExamResult>
  confirmSchoolExam(examId: string, earnedPoints: number): Promise<SchoolExamResult>
  uploadSchoolPaper(examId: string, file: File): Promise<SchoolPaperAttachment>
  addSchoolExamItems(examId: string, items: SchoolExamItemInput[]): Promise<{ evidence_created: number }>
  confirmSchoolExamItem(examId: string, itemId: string, earnedPoints: number): Promise<SchoolExamItem>
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
  /* 知识点审核台（ST-019-B）。 */
  adminKnowledgeClauses(subject?: string, domain?: string): Promise<CurriculumClause[]>
  adminKnowledgeCandidates(subject?: Subject): Promise<CandidateNode[]>
  adminSeedCandidates(subject?: Subject): Promise<{ subject: Subject; seeded_count: number; total_nodes: number }>
  adminKnowledgeLegacyMapping(subject?: Subject): Promise<LegacyMappingResult>
  adminReviewNode(nodeId: string, review: { reviewer_id: string; review_status: 'approved' | 'rejected'; review_opinion: string }): Promise<unknown>
  adminBatchReviewNodes(items: { node_id: string; reviewer_id: string; review_status: 'approved' | 'rejected'; review_opinion: string }[]): Promise<{ reviewed_count: number }>
  adminPublishRelease(release: { subject: Subject; release_version: string; published_by: string; summary?: string }): Promise<unknown>
  adminKnowledgeReleases(subject?: Subject): Promise<TaxonomyRelease[]>
  /* 智能练习会话、AI 错题引导、成长状态与知识图谱。 */
  createPracticeSession(input: { subject: Subject; targetCount?: number; purpose?: Purpose; focusKnowledgeCode?: string | null }): Promise<PracticeSession>
  getPracticeSession(sessionId: string): Promise<PracticeSession>
  nextPracticeSessionItem(sessionId: string): Promise<PracticeSession>
  completePracticeSession(sessionId: string): Promise<PracticeSessionComplete>
  wrongAttempts(subject: Subject, limit?: number): Promise<WrongQuestionSummary[]>
  getTutorForAttempt(attemptId: string): Promise<TutorSession>
  startTutorForAttempt(attemptId: string): Promise<TutorSession>
  sendTutorMessage(tutorSessionId: string, content: string): Promise<TutorSession>
  growthStatus(subject: Subject): Promise<GrowthStatus>
  knowledgeGraph(subject: Subject): Promise<KnowledgeGraph>
}

export interface CurriculumClause {
  clause_id: string
  source_id: string
  subject: string
  stage: string
  domain: string
  part_title: string
  domain_title: string
  theme_title: string
  sub_theme: string
  section_type: string
  clause_number: string
  pdf_page: number
  print_page: number
  raw_text: string
  standardized_text: string
  collation_note: string
  is_elective: boolean
  derived_requirement: string
  review_status: string
  legacy_mappings: string[]
}

export interface CandidateNode {
  id?: string
  code: string
  name: string
  domain?: string
  parent_code?: string | null
  parent_id?: string | null
  level?: number
  version?: number
  description?: string | null
  origin?: string
  review_status: string
  source_clause_ids?: string[]
  reviewer_id?: string | null
  review_opinion?: string | null
  reviewed_at?: string | null
}

export interface LegacyMappingRecord {
  legacy_code: string
  legacy_name: string
  legacy_parent_code: string | null
  action: 'retained' | 'renamed' | 'split' | 'merged' | 'new' | 'deprecated' | 'pending_human_review'
  target_candidate_codes: string[]
  mapping_reason: string
  compatibility_assurance: string
}

export interface LegacyMappingResult {
  legacy_mappings: LegacyMappingRecord[]
  new_candidate_additions: {
    candidate_code: string
    candidate_name: string
    domain: string
    action: string
    reason: string
  }[]
  summary: {
    total_legacy_nodes?: number
    total_legacy_math_nodes?: number
    retained_count: number
    renamed_count: number
    split_count: number
    merged_count: number
    new_count: number
    deprecated_count?: number
    pending_human_review_count?: number
  }
}

export interface TaxonomyRelease {
  id: string
  subject: Subject
  release_version: string
  status: string
  published_by: string | null
  published_at: string | null
  summary: string | null
  total_nodes: number
  created_at: string
}

export function createClient(token: string, role: 'student' | 'admin' = 'student'): Client {
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
    verify: () => call<unknown>(role === 'admin' ? '/api/admin/verify' : '/api/student/verify'),
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
    schoolExamDetail: examId => call<SchoolExamDetail>(`/api/school-exams/${encodeURIComponent(examId)}`),
    addSchoolExam: ({ subject, title, examDate, earnedPoints, maxPoints, confirmedByUser }) =>
      call<SchoolExamResult>('/api/school-exams', 'POST', {
        subject,
        title,
        exam_date: examDate,
        earned_points: earnedPoints,
        max_points: maxPoints,
        confirmed_by_user: confirmedByUser,
      }),
    confirmSchoolExam: (examId, earnedPoints) =>
      call<SchoolExamResult>(`/api/school-exams/${encodeURIComponent(examId)}/confirm`, 'POST', {
        confirmed_by_user: true,
        earned_points: earnedPoints,
      }),
    // 私人校卷附件上传（与内容附件共享底层校验，≤35 MiB，绝不提供公开下载接口）
    uploadSchoolPaper: (examId, file) =>
      request(`/api/school-exams/${encodeURIComponent(examId)}/paper?filename=${encodeURIComponent(file.name)}`, {
        method: 'POST',
        headers: { 'Content-Type': file.type },
        body: file,
      }) as Promise<SchoolPaperAttachment>,
    addSchoolExamItems: (examId, items) =>
      call<{ evidence_created: number }>(`/api/school-exams/${encodeURIComponent(examId)}/items`, 'POST', { items }),
    confirmSchoolExamItem: (examId, itemId, earnedPoints) =>
      call<SchoolExamItem>(`/api/school-exams/${encodeURIComponent(examId)}/items/${encodeURIComponent(itemId)}/confirm`, 'POST', {
        confirmed_by_human: true,
        earned_points: earnedPoints,
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
    adminKnowledgeClauses: (subject = 'math', domain) =>
      call<CurriculumClause[]>(`/api/admin/knowledge/clauses?subject=${encodeURIComponent(subject)}${domain ? `&domain=${encodeURIComponent(domain)}` : ''}`),
    adminKnowledgeCandidates: (subject = 'math') =>
      call<CandidateNode[]>(`/api/admin/knowledge/candidates?subject=${encodeURIComponent(subject)}`),
    adminSeedCandidates: (subject = 'math') =>
      call<{ subject: Subject; seeded_count: number; revised_count?: number; total_nodes: number }>(`/api/admin/knowledge/candidates/seed?subject=${encodeURIComponent(subject)}`, 'POST'),
    adminKnowledgeLegacyMapping: (subject = 'math') =>
      call<LegacyMappingResult>(`/api/admin/knowledge/legacy-mapping?subject=${encodeURIComponent(subject)}`),
    adminReviewNode: (nodeId, review) =>
      call<unknown>(`/api/admin/knowledge/nodes/${encodeURIComponent(nodeId)}/review`, 'POST', review),
    adminBatchReviewNodes: items =>
      call<{ reviewed_count: number }>('/api/admin/knowledge/nodes/batch-review', 'POST', { items }),
    adminPublishRelease: release => call<unknown>('/api/admin/knowledge/releases', 'POST', release),
    adminKnowledgeReleases: (subject = 'math') =>
      call<TaxonomyRelease[]>(`/api/admin/knowledge/releases?subject=${encodeURIComponent(subject)}`),
    createPracticeSession: ({ subject, targetCount = 5, purpose = 'training', focusKnowledgeCode = null }) =>
      call<PracticeSession>('/api/practice/sessions', 'POST', {
        subject,
        target_count: targetCount,
        purpose,
        focus_knowledge_code: focusKnowledgeCode,
      }),
    getPracticeSession: sessionId => call<PracticeSession>(`/api/practice/sessions/${encodeURIComponent(sessionId)}`),
    nextPracticeSessionItem: sessionId =>
      call<PracticeSession>(`/api/practice/sessions/${encodeURIComponent(sessionId)}/next`, 'POST'),
    completePracticeSession: sessionId =>
      call<PracticeSessionComplete>(`/api/practice/sessions/${encodeURIComponent(sessionId)}/complete`, 'POST'),
    wrongAttempts: (subject, limit = 20) =>
      call<WrongQuestionSummary[]>(`/api/practice/wrong-attempts?subject=${subject}&limit=${limit}`),
    getTutorForAttempt: attemptId =>
      call<TutorSession>(`/api/tutor/attempts/${encodeURIComponent(attemptId)}`),
    startTutorForAttempt: attemptId =>
      call<TutorSession>(`/api/tutor/attempts/${encodeURIComponent(attemptId)}/start`, 'POST'),
    sendTutorMessage: (tutorSessionId, content) =>
      call<TutorSession>(`/api/tutor/sessions/${encodeURIComponent(tutorSessionId)}/message`, 'POST', { content }),
    growthStatus: subject => call<GrowthStatus>(`/api/growth/status?subject=${subject}`),
    knowledgeGraph: subject => call<KnowledgeGraph>(`/api/knowledge/graph?subject=${subject}`),
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
  UNSUPPORTED_FILE_TYPE: '不支持的附件类型：仅接受 PDF / DOCX / PNG / JPG / MP3 / M4A。',
  INVALID_DOCX: 'Word 文档（.docx）损坏或缺少有效正文结构，请检查文件后重新上传。',
  INVALID_FILE_SIZE: '附件大小不符合要求（上限 25 MiB）。',
  ATTACHMENT_STORAGE_UNAVAILABLE: '附件存储暂不可用，请稍后重试。',
  IMPORT_ALREADY_CONFIRMED: '该附件已确认导入过，不能再次解析或导入。',
  IMPORT_SOURCE_MISMATCH: '附件与题目来源不匹配，请检查录入内容。',
  IMPORT_NOT_READY_OR_ALREADY_CONFIRMED: '该附件尚未解析（或已确认导入），不能确认导入。',
  MEDIA_ATTACHMENT_INVALID: '媒体附件无效：须与题目同属一个来源且已上传。',
  IMPORT_TRANSACTION_FAILED: '导入保存失败，请重试。',
  IMPORTED_QUESTION_CONFIRMATION_REQUIRED: '导入的题目缺少确认记录，请先在附件区完成逐题确认导入。',
  QUESTION_NOT_APPROVED_FOR_PRIVATE_PUBLICATION: '来源尚未通过人工审核（或版权状态未核实）：请先完成来源人工审核，再发布题目。',
  KNOWLEDGE_NODE_NOT_FOUND: '未找到对应的已发布知识点节点。',
}

export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return '访问令牌无效或已过期，请重新输入。'
    if (error.status === 403) return '凭据权限不足或使用了错误的角色凭据（如学生凭据访问管理端）。'
    return API_CODE_TEXT[error.code] ?? error.code
  }
  if (error instanceof TypeError) return '无法连接服务器，请检查网络连接后重试。'
  return String(error)
}
