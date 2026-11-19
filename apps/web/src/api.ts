/* API surface (contracts/openapi.yaml) + in-memory bearer client. Token never persists. */

export type Subject = 'math' | 'chinese' | 'english' | 'physics'
// 学校考试额外支持「道法（道德与法治）」归档，核心练习/画像仍严格保持四科不变
export type SchoolSubject = Subject | 'ethics'
export type Kind = 'single_choice' | 'short_answer' | 'subjective'
export type Purpose = 'training' | 'evaluation'
export type GapType = 'INSUFFICIENT_EVIDENCE' | 'KNOWLEDGE_GAP' | 'NO_CONFIRMED_GAP'
export type SchoolErrorCategory = 'concept' | 'calculation' | 'reading' | 'method' | 'norm' | 'other'
export type SchoolDraftConfidence =
  | 'high'
  | 'medium'
  | 'low'
  | 'skeleton_only'
  | 'external_sync'
  | 'auto_matched'
  | 'ai_matched'
  | 'ai_recommended'
  | 'type_inferred'

export interface DraftKnowledgeCandidate {
  knowledge_id: string
  title: string
  reason: string
}

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
  correct_answer?: string | null
  earned_points: number | null
  max_points: number
  selection_reason?: string | null
  knowledge_codes: string[]
  knowledge_titles: string[]
  tutor_session_id?: string | null
  adopted_solution?: AdoptedSolution | null
  created_at?: string | null
}

export interface AdoptedSolution {
  option_id: string
  title: string
  approach_focus: string
  action_steps: string[]
  admin_note?: string | null
  selected_at?: string | null
}

export type CognitiveGapType =
  | 'concept_confusion'
  | 'condition_omission'
  | 'method_misuse'
  | 'reasoning_break'
  | 'calculation_slip'

export interface DiagnosisSolutionOption {
  option_id: 'opt_1' | 'opt_2' | 'opt_3'
  title: string
  approach_focus: string
  rationale: string
  action_steps: string[]
}

export interface AdminErrorDiagnosis {
  id: string
  attempt_id: string
  tutor_session_id?: string | null
  root_cause_summary: string
  cognitive_gap_type: CognitiveGapType
  evidence_from_dialogue: string
  solutions: DiagnosisSolutionOption[]
  selected_option_id?: 'opt_1' | 'opt_2' | 'opt_3' | null
  admin_note?: string | null
  model_used?: string | null
  created_at: string
  updated_at: string
  selected_at?: string | null
}

export interface AdminWrongDiagnosticListItem {
  attempt_id: string
  question_version_id: string
  subject: Subject
  stem_excerpt: string
  kind: Kind
  options?: string[]
  correct_answer?: string
  student_answer: string
  earned_points: number | null
  max_points: number
  knowledge_codes: string[]
  knowledge_titles: string[]
  tutor_session_id?: string | null
  tutor_turn_count: number
  has_diagnosis: boolean
  selected_option_id?: string | null
  selected_solution_title?: string | null
  cognitive_gap_type?: string | null
  created_at: string
}

export interface AdminWrongDiagnosticDetail {
  attempt_id: string
  question_version_id: string
  subject: Subject
  stem: string
  kind: Kind
  options: string[]
  correct_answer: string
  student_answer: string
  earned_points: number | null
  max_points: number
  knowledge_codes: string[]
  knowledge_titles: string[]
  tutor_session_id?: string | null
  tutor_turns: TutorTurn[]
  diagnosis?: AdminErrorDiagnosis | null
  created_at: string
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
  school_name?: string | null
  grade?: string | null
  exam_type?: 'monthly' | 'midterm' | 'final' | 'unified_practice' | 'other' | null
  exam_type_label?: string | null
  academic_year?: string | null
  term?: 'first' | 'second' | null
  series_title?: string | null
  external_exam_id?: string | null
  source_kind?: string
}

export interface SchoolPaperAttachment {
  id: string
  filename: string
  media_type: string
  sha256: string
  byte_size: number
  created_at: string
}

export type ReflectionStatus = 'not_required' | 'pending' | 'completed' | 'needs_revision'
export type StemState = 'extracting' | 'embedded_draft' | 'vision_draft' | 'not_found' | 'confirmed'

export interface SchoolExamItem {
  id: string
  question_label: string
  knowledge_id: string
  knowledge_name?: string
  earned_points: number
  max_points: number
  lost_points?: number
  scoring_origin: 'manual_entry' | 'ocr_draft'
  confirmed_by_user: boolean
  error_category?: SchoolErrorCategory | null
  error_note?: string | null
  reflection_status?: ReflectionStatus
  stuck_point?: string
  fix_strategy?: string
  return_reason?: string | null
  draft_source_attachment_id?: string | null
  draft_confidence?: SchoolDraftConfidence | null
  draft_reason?: string | null
  draft_knowledge_candidates?: DraftKnowledgeCandidate[] | null
  stem_text?: string | null
  student_answer_text?: string | null
  stem_state?: StemState | null
  stem_source?: string | null
  coach_turn_count?: number
}

export interface SchoolCoachTurn {
  id: string
  turn_index: number
  role: 'user' | 'assistant'
  content: string
  model_used?: string | null
  sanitized_guard_triggered?: boolean
  created_at: string
}

export interface SchoolCoachDraft {
  error_category?: SchoolErrorCategory | null
  stuck_point: string
  fix_strategy: string
  ready: boolean
}

export interface SchoolCoachSession {
  id?: string | null
  item_id: string
  started: boolean
  status: string
  user_turn_count: number
  max_user_turns: number
  can_summarize: boolean
  draft_summary?: SchoolCoachDraft | null
  turns: SchoolCoachTurn[]
}

export interface StudentSchoolReflectionItem {
  item_id: string
  exam_id: string
  subject: SchoolSubject
  exam_title: string
  exam_date: string
  question_label: string
  topic: string
  earned_points: number
  max_points: number
  lost_points: number
  stem_excerpt?: string | null
  student_answer_excerpt?: string | null
  reflection_status: ReflectionStatus
  error_category?: SchoolErrorCategory | null
  stuck_point: string
  fix_strategy: string
  return_reason?: string | null
  ai_audit_mode?: string | null
  coach_turn_count?: number
}

export interface StudentSchoolReflectionsPayload {
  items: StudentSchoolReflectionItem[]
  pending_counts_by_subject: Record<string, number>
  total_pending: number
}

export interface SchoolExamItemInput {
  question_label: string
  knowledge_id: string
  earned_points: number
  max_points: number
  scoring_origin: 'manual_entry' | 'ocr_draft'
  error_category?: SchoolErrorCategory | null
  error_note?: string | null
  draft_source_attachment_id?: string | null
  draft_confidence?: SchoolDraftConfidence | null
  draft_reason?: string | null
  draft_knowledge_candidates?: DraftKnowledgeCandidate[] | null
}

export interface SchoolItemConfirmInput {
  earnedPoints: number
  maxPoints?: number
  knowledgeId?: string
  errorCategory?: SchoolErrorCategory | null
  errorNote?: string | null
}

export interface SchoolItemConfirmBatchEntry extends SchoolItemConfirmInput {
  itemId: string
}

export interface ParseDraftsResult {
  parser_mode_used: string
  meta: { pages_sent?: number; masked_pages?: number; model?: string }
  created_items: SchoolExamItem[]
  skipped_labels: string[]
  evidence_created: number
}

export interface SchoolExamErrorOverview {
  confirmed_item_count: number
  lost_item_count: number
  unconfirmed_draft_count: number
  earned_points: number
  max_points: number
  paper_lost_points: number | null
  itemized_earned_points: number
  itemized_max_points: number
  itemized_lost_points: number
  unaccounted_lost_points: number | null
  categorized_item_count: number
  uncategorized_item_count: number
  primary_error_category: string | null
  primary_knowledge_id: string | null
  primary_knowledge_name: string | null
}

export interface SchoolExamErrorCategoryStat {
  category: string
  item_count: number
  lost_points: number
  share_of_itemized_loss: number
  question_labels: string[]
}

export interface SchoolExamErrorKnowledge {
  knowledge_id: string
  knowledge_name: string
  item_count: number
  lost_item_count: number
  earned_points: number
  max_points: number
  lost_points: number
  exam_observed_rate: number
  share_of_itemized_loss: number
  categories: string[]
  question_labels: string[]
  notes: { question_label: string; note: string }[]
  practice_status: 'mastered' | 'weak' | 'insufficient' | 'untested' | 'not_applicable'
  practice_observed_rate: number | null
  practice_sample_size: number
  diagnosis_tag: 'double_weak' | 'exam_slip' | 'blind_spot' | 'archive_review'
}

export interface SchoolExamErrorItem {
  id: string
  question_label: string
  knowledge_id: string
  knowledge_name: string
  earned_points: number
  max_points: number
  lost_points: number
  error_category: SchoolErrorCategory | null
  error_note: string | null
}

export interface SchoolExamRecurringKnowledge {
  knowledge_id: string
  knowledge_name: string
  exam_count: number
  total_lost_points: number
  total_item_count: number
  repeat_in_current_exam: boolean
  categories: string[]
  exams: {
    exam_id: string
    title: string
    exam_date: string
    lost_points: number
    item_count: number
  }[]
}

export interface SchoolExamErrorAnalysis {
  exam_id: string
  subject: SchoolSubject
  title: string
  exam_date: string
  confirmed_by_user: boolean
  has_taxonomy: boolean
  status: 'insufficient_items' | 'no_errors_recorded' | 'analyzed'
  overview: SchoolExamErrorOverview
  diagnosis_summary: string
  by_category: SchoolExamErrorCategoryStat[]
  by_knowledge: SchoolExamErrorKnowledge[]
  lost_items: SchoolExamErrorItem[]
  history_summary: {
    same_subject_exam_count: number
    same_subject_exams_with_items: number
    recurring_count: number
  }
  recurring_knowledge: SchoolExamRecurringKnowledge[]
  disclaimer: string
}

export interface SchoolExamDetail extends SchoolExam {
  subject: SchoolSubject
  class_highest?: number | null
  grade_highest?: number | null
  items: SchoolExamItem[]
  attachments: SchoolPaperAttachment[]
}

export type SchoolExamMatchState =
  | 'EXACT_MATCH'
  | 'AMBIGUOUS'
  | 'CONFLICT'
  | 'NOT_FOUND'
  | 'NEEDS_REVIEW'
  | 'AWAITING_EXAM_DATE'
  | 'MANUAL_CONFIRMED'
  | 'REJECTED'

export interface SchoolPaperHeaderField {
  status: 'found' | 'missing' | 'ambiguous'
  value: string | null
  evidence: string | null
}

export interface SchoolPaperHeader {
  subject: SchoolSubject | null
  academic_year: string | null
  grade: string | null
  exam_type: 'monthly' | 'midterm' | 'final' | 'unified_practice' | 'other' | null
  exam_type_label: string | null
  exam_date: string | null
  confidence: 'high' | 'medium' | 'low' | string | null
  complete: boolean
  fields: Record<string, SchoolPaperHeaderField>
  text_excerpt: string
  text_sha256?: string
  warnings: string[]
}

export interface SchoolPaperFieldComparison {
  field: string
  label: string
  expected: string | null
  actual: string | null
  state: 'match' | 'conflict' | 'different' | 'missing'
}

export interface SchoolPaperMatchCandidate {
  exam_id: string
  title: string
  exam_date: string | null
  score?: number
  exact?: boolean
  comparisons?: SchoolPaperFieldComparison[]
  conflicts?: string[]
  missing?: string[]
  manual?: boolean
  confirmed_by_human?: boolean
}

export interface SchoolExamPaper {
  id: string
  filename: string
  sha256: string
  media_type: string
  byte_size: number
  source_kind: string
  source_name: string
  source_ref: string
  status: 'needs_review' | 'matched' | 'imported' | 'rejected' | string
  match_state: SchoolExamMatchState | null
  header: SchoolPaperHeader
  candidates: SchoolPaperMatchCandidate[]
  school_exam_id: string | null
  exam: {
    id: string
    title: string
    subject: SchoolSubject
    exam_date: string
    confirmed_by_user: boolean
  } | null
  error_code: string | null
  imported_at: string | null
  created_at: string
  updated_at: string
}

export interface SchoolExamScanRun {
  id: string
  status: string
  discovered_count: number
  imported_count: number
  duplicate_count: number
  invalid_count: number
  needs_review_count: number
  error_count: number
  errors: { path?: string; code: string }[]
  started_at: string
  finished_at: string | null
}

export interface SchoolExamSyncSource {
  environment: string
  directory: string
  directory_display: string
  real_source_configured: boolean
  source_kind: string
  ready: boolean
  source_code: string | null
  message: string
  supported_formats: string[]
  max_file_bytes: number
}

export interface K12100SyncedReportExam {
  exam_id: string
  subject: SchoolSubject
  subject_label: string
  exam_title: string
  exam_date: string
  earned_points: number
  max_points: number
  confirmed_by_user: boolean
  draft_count: number
  confirmed_item_count: number
  attachment_count: number
  class_rank?: number | null
  grade_rank?: number | null
  participants?: number | null
  class_highest?: number | null
  grade_highest?: number | null
  rank_synced_count?: number
}

export interface K12100SyncedReportUnlinkedSubject {
  subject: SchoolSubject
  subject_label: string
  score: number | null
  max_score: number | null
}

export interface K12100SyncedReportSummary {
  id: string
  title: string | null
  external_exam_id: string | null
  exam_date: string | null
  academic_year: string | null
  grade: string | null
  exam_type: string | null
  status: string
  match_state: string
  report_total_score: number | null
  report_total_max: number | null
  total_class_rank?: number | null
  total_grade_rank?: number | null
  total_participants?: number | null
  total_class_highest?: number | null
  total_grade_highest?: number | null
  pages: number
  updated_at: string | null
  exams: K12100SyncedReportExam[]
  unlinked_subjects: K12100SyncedReportUnlinkedSubject[]
  completeness?: {
    complete: boolean
    missing: string[]
  }
}

export interface K12100SyncReadiness {
  total_reports: number
  complete_reports: number
  incomplete_reports: number
  all_complete: boolean
}

export interface SchoolExamSyncCenter {
  source: SchoolExamSyncSource
  latest_scan: SchoolExamScanRun | null
  counts: {
    total: number
    needs_review: number
    matched: number
    imported: number
    rejected: number
  }
  papers: SchoolExamPaper[]
  synced_reports?: K12100SyncedReportSummary[]
  sync_readiness?: K12100SyncReadiness
}

export interface SchoolExamScanResult {
  run: SchoolExamScanRun
  papers: SchoolExamPaper[]
  source: SchoolExamSyncSource
}

export interface SchoolExamMatchResult {
  state: SchoolExamMatchState
  confidence: string
  best_exam_id: string | null
  candidates: SchoolPaperMatchCandidate[]
  reasons: string[]
  missing_fields: string[]
}

export interface SchoolExamRank {
  id: string
  subject_scope: string
  scope: 'class' | 'grade' | 'school' | 'region'
  rank_value: number
  participant_count: number | null
  percentile: number | null
  highest_score?: number | null
  source_name: string
  source_field: string
  ownership_status: 'verified' | 'unverified' | 'conflict' | string
  ownership_basis: string | null
  review_status: 'pending' | 'confirmed' | string
  captured_at: string
  history_count: number
}

export interface SchoolExamRanksPayload {
  exam_id: string
  class_highest?: number | null
  grade_highest?: number | null
  ranks: SchoolExamRank[]
  total_ranks?: SchoolExamRank[]
  report_total?: {
    report_total_score: number | null
    report_total_max: number | null
    total_class_rank: number | null
    total_grade_rank: number | null
    total_participants: number | null
    total_class_highest: number | null
    total_grade_highest: number | null
  } | null
  missing_scopes: string[]
  disclaimer: string
}

export interface K12100CredentialsSummary {
  status: string
  username_masked: string | null
  deepseek_configured: boolean
  deepseek_masked: string | null
  message: string
}

export interface K12100SubjectResult {
  subject: SchoolSubject
  subject_label: string
  exam_id: string
  exam_title: string
  exam_date: string
  earned_points: number
  max_points: number
  confirmed_by_user: boolean
  score_status: string
  stem_mode: string
  parser_mode_used: string
  attachments_uploaded: number
  drafts_created: number
  skipped_labels: string[]
  warning: string | null
  match_state?: SchoolExamMatchState | null
  rank_ownership?: string | null
  rank_ownership_basis?: string | null
  match_confidence?: string | null
  match_reasons?: string[]
  match_candidates?: SchoolPaperMatchCandidate[]
  ranks_created?: number
  rank_issues?: { scope: string; code: string; field?: string }[]
}

export interface K12100BackfillResult {
  source_exam_title: string
  source_exam_date: string | null
  subjects: K12100SubjectResult[]
  totals: {
    subjects_processed: number
    subjects_blocked?: number
    created_exams: number
    confirmed_now: number
    locked_conflicts: number
    attachments_uploaded: number
    drafts_created: number
    ranks_created?: number
  }
  knowledge_evidence_created: number
}

export interface K12100HomeExamSummary {
  external_exam_id: string
  exam_name: string
  exam_date: string
  grade: string
  academic_year: string
  exam_type: string
  already_synced: boolean
}

export interface K12100ReportSubjectAction {
  subject: SchoolSubject
  subject_label: string
  action:
    | 'created'
    | 'updated'
    | 'filled'
    | 'unchanged'
    | 'locked_conflict'
    | 'identity_conflict'
    | 'awaiting_exam_date'
    | 'ambiguous'
    | 'skipped'
  exam_id: string
  exam_title: string
  exam_date: string
  earned_points: number | null
  max_points: number | null
  confirmed_by_user: boolean
  filled_fields: string[]
  conflict_fields: string[]
  message: string
  report_id: string
  report_title: string
  external_exam_id: string | null
  report_exam_date: string | null
  academic_year: string | null
  grade: string | null
  exam_type: string | null
}

export interface K12100ReportJobResult {
  home_exams: K12100HomeExamSummary[]
  reports: Array<{
    report_id: string
    title: string | null
    external_exam_id: string | null
    exam_date: string | null
    academic_year: string | null
    grade: string | null
    exam_type: string | null
    match_state: string
    counts: Record<string, number>
    drafts_created: number
    drafts_updated: number
    cards_synced: number
  }>
  subject_actions: K12100ReportSubjectAction[]
  totals: {
    home_exams: number
    skipped_existing: number
    downloaded: number
    reports_registered: number
    created_exams: number
    updated_exams: number
    filled_exams: number
    unchanged_exams: number
    locked_conflicts: number
    identity_conflicts: number
    awaiting_exam_date: number
    ambiguous_exams: number
    drafts_created: number
    drafts_updated: number
    auto_mapped: number
    cards_created: number
    cards_synced: number
    failures: number
  }
  failures: Array<{
    external_exam_id?: string
    exam_name?: string
    code: string
    reason: string
  }>
  knowledge_evidence_created: number
}

export interface K12100SyncJob {
  job_id: string
  kind?: 'report' | 'legacy_collect'
  state: 'queued' | 'collecting' | 'backfilling' | 'completed' | 'failed'
  stage_message: string
  created_at: string
  updated_at: string
  exam_keyword: string | null
  confirm_total_scores: boolean
  error_code: string | null
  error_message: string | null
  result: K12100BackfillResult | null
  report_result?: K12100ReportJobResult | null
}

export interface K12100RuntimeStatus {
  environment: string
  mode: 'host_direct' | 'isolated_import_only'
  can_run_local: boolean
  is_isolated: boolean
  browser_ready: boolean
  node_available: boolean
  playwright_available: boolean
  unavailable_code: string | null
  unavailable_reason: string | null
  credentials: K12100CredentialsSummary
  deepseek_configured: boolean
  active_job_id: string | null
  latest_job: K12100SyncJob | null
  recommended_cli_command: string
}

export interface K12100BackfillOptions {
  examKeyword?: string
  targetExamDate?: string
  seriesTitlePrefix?: string
  maxExams?: number
  confirmTotalScores?: boolean
  extractExistingPdfs?: boolean
  uploadMissingCards?: boolean
  replaceUnconfirmedDrafts?: boolean
  useAi?: boolean
  headless?: boolean
}

export interface GoalResult {
  id: string
  version: number
  status: string
}

export interface SchoolExamReportSubject {
  subject: string
  name: string
  score: number | null
  max_score: number | null
  class_rank: number | null
  grade_rank: number | null
  participants: number | null
  class_highest: number | null
  grade_highest: number | null
  page: number | null
}

export interface SchoolExamReportQuestion {
  subject: string
  number: string
  question_type: string | null
  difficulty: string | null
  max_score: number | null
  score: number | null
  score_rate: number | null
  page: number
}

export interface SchoolExamReport {
  id: string
  sha256: string
  filename: string
  byte_size: number
  source_ref: string
  title: string | null
  academic_year: string | null
  grade: string | null
  exam_type: string | null
  exam_sequence: number | null
  report_time: string | null
  external_exam_id?: string | null
  exam_date?: string | null
  report_total_score: number | null
  report_total_max: number | null
  total_class_rank: number | null
  total_grade_rank: number | null
  total_participants: number | null
  total_class_highest?: number | null
  total_grade_highest?: number | null
  listed_subject_score: number | null
  listed_subject_max: number | null
  scope_status: string
  pages: number
  confidence: string
  status: string
  match_state: string
  linked_exam_ids: Array<{ subject: string; exam_id: string; title: string; exam_date: string; match: string }>
  subjects: SchoolExamReportSubject[]
  questions: SchoolExamReportQuestion[]
  answer_card_pages: Record<string, number[]>
  warnings: string[]
  created_at: string | null
  updated_at: string | null
}

export interface SchoolExamReportAttachment {
  id: string
  subject: string
  page_number: number
  filename: string
  media_type: string
  byte_size: number
  rotation: number
  created_at: string | null
}

export interface SchoolExamReportScanResult {
  discovered: number
  skipped: number
  reports: SchoolExamReport[]
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
  deleteSchoolExam(examId: string): Promise<{ deleted: boolean; id: string; items_deleted: number; attachments_deleted: number; rank_snapshots_deleted: number; papers_unlinked: number }>
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
  confirmSchoolExamItem(
    examId: string,
    itemId: string,
    input: number | SchoolItemConfirmInput,
  ): Promise<SchoolExamItem>
  confirmSchoolExamItemsBatch(
    examId: string,
    items: SchoolItemConfirmBatchEntry[],
  ): Promise<{ items: SchoolExamItem[]; evidence_created: number }>
  discardSchoolExamItem(
    examId: string,
    itemId: string,
  ): Promise<{ status: string; id: string; question_label: string }>
  parseSchoolExamDrafts(
    examId: string,
    input: {
      attachmentIds: string[]
      mode?: 'auto' | 'skeleton_only'
      maskStudentHeader?: boolean
      replaceUnconfirmedDrafts?: boolean
    },
  ): Promise<ParseDraftsResult>
  autoAssociateSchoolExamItems(
    examId: string,
    input?: { useAi?: boolean; overwriteExisting?: boolean },
  ): Promise<{
    updated: number
    tier1_matched: number
    tier2_ai: number
    tier3_inferred: number
    skipped_confirmed: number
  }>
  updateSchoolExamItemAnalysis(
    examId: string,
    itemId: string,
    input: { errorCategory: SchoolErrorCategory | null; errorNote: string | null },
  ): Promise<SchoolExamItem>
  returnSchoolExamItemReflection(
    examId: string,
    itemId: string,
    reason: string,
  ): Promise<SchoolExamItem>
  extractSchoolExamStems(
    examId: string,
    options?: { maskStudentHeader?: boolean; batchSize?: number },
  ): Promise<{
    requested: number
    embedded: number
    vision: number
    not_found: number
    remaining_unextracted: number
    ai_called: boolean
    ai_unavailable_reason?: string | null
  }>
  patchSchoolExamItemStem(
    examId: string,
    itemId: string,
    input: { stem_text?: string | null; student_answer_text?: string | null; confirm?: boolean },
  ): Promise<SchoolExamItem>
  confirmSchoolExamStems(examId: string): Promise<{ confirmed_count: number }>
  schoolExamReflections(subject?: SchoolSubject): Promise<StudentSchoolReflectionsPayload>
  submitSchoolExamReflection(
    itemId: string,
    input: { errorCategory: SchoolErrorCategory; stuckPoint: string; fixStrategy: string },
  ): Promise<StudentSchoolReflectionItem>
  getSchoolReflectionCoach(itemId: string): Promise<SchoolCoachSession>
  startSchoolReflectionCoach(itemId: string, sceneHint?: string | null): Promise<SchoolCoachSession>
  sendSchoolReflectionCoachMessage(itemId: string, content: string): Promise<SchoolCoachSession>
  summarizeSchoolReflectionCoach(itemId: string): Promise<SchoolCoachSession>
  getAdminSchoolExamItemCoach(examId: string, itemId: string): Promise<SchoolCoachSession>
  schoolExamErrorAnalysis(examId: string): Promise<SchoolExamErrorAnalysis>
  schoolExamReports(): Promise<SchoolExamReport[]>
  scanSchoolExamReports(): Promise<SchoolExamReportScanResult>
  matchSchoolExamReport(reportId: string): Promise<{ report: SchoolExamReport; match: { match_state: string; unresolved_subjects: string[]; ambiguous_subjects: string[] } }>
  confirmSchoolExamReport(reportId: string): Promise<SchoolExamReport & { ledger?: { applied_subjects: string[]; conflict_subjects: string[]; skipped_subjects: string[] } }>
  updateSchoolExamReport(reportId: string, patch: Partial<Pick<SchoolExamReport, 'title' | 'academic_year' | 'grade' | 'exam_type' | 'exam_sequence' | 'report_time'>>): Promise<SchoolExamReport>
  supplementSchoolExamReportSubject(reportId: string, payload: { subject: string; score: number; max_score: number; class_rank?: number | null; grade_rank?: number | null; participants?: number | null }): Promise<SchoolExamReport>
  generateSchoolExamReportItemDrafts(reportId: string): Promise<{ created: number; skipped: number; unmapped_subjects: string[]; auto_mapped: number }>
  aiMapSchoolExamReportItems(reportId: string): Promise<{ mapped: number; failed_subjects: string[] }>
  listSchoolExamReportAnswerCards(reportId: string): Promise<SchoolExamReportAttachment[]>
  buildSchoolExamReportAnswerCards(reportId: string, rotation: number): Promise<{ created: number; attachments: SchoolExamReportAttachment[] }>
  fetchSchoolExamReportAnswerCardImage(reportId: string, attachmentId: string): Promise<Blob>
  k12100SyncStatus(): Promise<K12100RuntimeStatus>
  schoolExamSyncCenter(): Promise<SchoolExamSyncCenter>
  scanSchoolExamPapers(): Promise<SchoolExamScanResult>
  acquireSchoolExamPapers(): Promise<{ source_adapter: string[]; acquired_count: number; files: string[] }>
  matchSchoolExamPaper(
    paperId: string,
    input?: { examId?: string; confirmedByHuman?: boolean },
  ): Promise<{ paper: SchoolExamPaper; match?: SchoolExamMatchResult }>
  importSchoolExamPaper(paperId: string): Promise<{
    already_imported: boolean
    paper: SchoolExamPaper
    attachment_created: boolean
    attachment?: SchoolPaperAttachment
    metadata_updates?: string[]
  }>
  rejectSchoolExamPaper(paperId: string): Promise<{ paper: SchoolExamPaper }>
  schoolExamRanks(examId: string): Promise<SchoolExamRanksPayload>
  confirmSchoolExamRank(examId: string, rankId: string): Promise<SchoolExamRank>
  startK12100SyncJob(options?: K12100BackfillOptions): Promise<K12100SyncJob>
  startK12100ReportJob(options?: { maxExams?: number; headless?: boolean }): Promise<K12100SyncJob>
  hydrateK12100LocalReports(): Promise<{
    deduped_reports: number
    reparsed_reports: number
    ranks_synced: number
    cards_synced: number
    drafts_created: number
    synced_reports: K12100SyncedReportSummary[]
    sync_readiness?: K12100SyncReadiness
  }>
  collectSchoolExamPaper(
    paperId: string,
    options?: {
      useAi?: boolean
      extractExistingPdfs?: boolean
      uploadMissingCards?: boolean
      replaceUnconfirmedDrafts?: boolean
      headless?: boolean
    },
  ): Promise<K12100SyncJob>
  k12100SyncJob(jobId: string): Promise<K12100SyncJob>
  importK12100Bundle(
    bundle: Record<string, unknown>,
    options?: Omit<K12100BackfillOptions, 'headless'>,
  ): Promise<K12100BackfillResult>
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
  adminWrongDiagnostics(subject: Subject, limit?: number): Promise<AdminWrongDiagnosticListItem[]>
  adminWrongDiagnosticDetail(attemptId: string): Promise<AdminWrongDiagnosticDetail>
  adminAnalyzeWrongDiagnostic(attemptId: string): Promise<AdminWrongDiagnosticDetail>
  adminSelectWrongDiagnosticSolution(
    attemptId: string,
    payload: { optionId: 'opt_1' | 'opt_2' | 'opt_3'; adminNote?: string | null }
  ): Promise<AdminWrongDiagnosticDetail>
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
    deleteSchoolExam: examId =>
      call<{ deleted: boolean; id: string; items_deleted: number; attachments_deleted: number; rank_snapshots_deleted: number; papers_unlinked: number }>(
        `/api/school-exams/${encodeURIComponent(examId)}?confirm=true`,
        'DELETE',
      ),
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
    confirmSchoolExamItem: (examId, itemId, input) => {
      const norm = typeof input === 'number' ? { earnedPoints: input } : input
      const body: Record<string, unknown> = {
        confirmed_by_human: true,
        earned_points: norm.earnedPoints,
      }
      if (norm.maxPoints !== undefined) body.max_points = norm.maxPoints
      if (norm.knowledgeId !== undefined) body.knowledge_id = norm.knowledgeId
      if ('errorCategory' in norm) body.error_category = norm.errorCategory ?? null
      if ('errorNote' in norm) body.error_note = norm.errorNote ?? null
      return call<SchoolExamItem>(
        `/api/school-exams/${encodeURIComponent(examId)}/items/${encodeURIComponent(itemId)}/confirm`,
        'POST',
        body,
      )
    },
    confirmSchoolExamItemsBatch: (examId, items) =>
      call<{ items: SchoolExamItem[]; evidence_created: number }>(
        `/api/school-exams/${encodeURIComponent(examId)}/items/confirm-batch`,
        'POST',
        {
          items: items.map(it => ({
            item_id: it.itemId,
            confirmed_by_human: true,
            earned_points: it.earnedPoints,
            ...(it.maxPoints !== undefined ? { max_points: it.maxPoints } : {}),
            ...(it.knowledgeId !== undefined ? { knowledge_id: it.knowledgeId } : {}),
            ...('errorCategory' in it ? { error_category: it.errorCategory ?? null } : {}),
            ...('errorNote' in it ? { error_note: it.errorNote ?? null } : {}),
          })),
        },
      ),
    discardSchoolExamItem: (examId, itemId) =>
      call<{ status: string; id: string; question_label: string }>(
        `/api/school-exams/${encodeURIComponent(examId)}/items/${encodeURIComponent(itemId)}/discard`,
        'POST',
      ),
    parseSchoolExamDrafts: (examId, { attachmentIds, mode = 'auto', maskStudentHeader = true, replaceUnconfirmedDrafts = false }) =>
      call<ParseDraftsResult>(`/api/school-exams/${encodeURIComponent(examId)}/parse-drafts`, 'POST', {
        attachment_ids: attachmentIds,
        mode,
        mask_student_header: maskStudentHeader,
        replace_unconfirmed_drafts: replaceUnconfirmedDrafts,
      }),
    autoAssociateSchoolExamItems: (examId, input = {}) =>
      call<{
        updated: number
        tier1_matched: number
        tier2_ai: number
        tier3_inferred: number
        skipped_confirmed: number
      }>(`/api/school-exams/${encodeURIComponent(examId)}/items/auto-associate`, 'POST', {
        use_ai: input.useAi ?? true,
        overwrite_existing: input.overwriteExisting ?? false,
      }),
    updateSchoolExamItemAnalysis: (examId, itemId, { errorCategory, errorNote }) =>
      call<SchoolExamItem>(
        `/api/school-exams/${encodeURIComponent(examId)}/items/${encodeURIComponent(itemId)}/analysis`,
        'POST',
        { error_category: errorCategory, error_note: errorNote },
      ),
    returnSchoolExamItemReflection: (examId, itemId, reason) =>
      call<SchoolExamItem>(
        `/api/school-exams/${encodeURIComponent(examId)}/items/${encodeURIComponent(itemId)}/return-reflection`,
        'POST',
        { reason },
      ),
    extractSchoolExamStems: (examId, options) =>
      call(`/api/school-exams/${encodeURIComponent(examId)}/extract-stems`, 'POST', {
        mask_student_header: options?.maskStudentHeader ?? true,
        batch_size: options?.batchSize ?? 3,
      }),
    patchSchoolExamItemStem: (examId, itemId, input) =>
      call<SchoolExamItem>(
        `/api/school-exams/${encodeURIComponent(examId)}/items/${encodeURIComponent(itemId)}/stem`,
        'PATCH',
        input,
      ),
    confirmSchoolExamStems: examId =>
      call<{ confirmed_count: number }>(
        `/api/school-exams/${encodeURIComponent(examId)}/confirm-stems`,
        'POST',
      ),
    schoolExamReflections: subject =>
      call<StudentSchoolReflectionsPayload>(
        subject
          ? `/api/student/school-exam-reflections?subject=${encodeURIComponent(subject)}`
          : '/api/student/school-exam-reflections',
      ),
    submitSchoolExamReflection: (itemId, { errorCategory, stuckPoint, fixStrategy }) =>
      call<StudentSchoolReflectionItem>(
        `/api/student/school-exam-reflections/${encodeURIComponent(itemId)}`,
        'POST',
        {
          error_category: errorCategory,
          stuck_point: stuckPoint,
          fix_strategy: fixStrategy,
        },
      ),
    getSchoolReflectionCoach: itemId =>
      call<SchoolCoachSession>(`/api/student/school-exam-reflections/${encodeURIComponent(itemId)}/coach`),
    startSchoolReflectionCoach: (itemId, sceneHint) =>
      call<SchoolCoachSession>(
        `/api/student/school-exam-reflections/${encodeURIComponent(itemId)}/coach/start`,
        'POST',
        sceneHint ? { scene_hint: sceneHint } : {},
      ),
    sendSchoolReflectionCoachMessage: (itemId, content) =>
      call<SchoolCoachSession>(
        `/api/student/school-exam-reflections/${encodeURIComponent(itemId)}/coach/message`,
        'POST',
        { content },
      ),
    summarizeSchoolReflectionCoach: itemId =>
      call<SchoolCoachSession>(
        `/api/student/school-exam-reflections/${encodeURIComponent(itemId)}/coach/summarize`,
        'POST',
      ),
    getAdminSchoolExamItemCoach: (examId, itemId) =>
      call<SchoolCoachSession>(
        `/api/school-exams/${encodeURIComponent(examId)}/items/${encodeURIComponent(itemId)}/coach`,
      ),
    schoolExamErrorAnalysis: examId =>
      call<SchoolExamErrorAnalysis>(`/api/school-exams/${encodeURIComponent(examId)}/error-analysis`),
    schoolExamReports: () => call<SchoolExamReport[]>('/api/school-exams/reports'),
    scanSchoolExamReports: () => call<SchoolExamReportScanResult>('/api/school-exams/reports/scan', 'POST', {}),
    matchSchoolExamReport: reportId =>
      call<{ report: SchoolExamReport; match: { match_state: string; unresolved_subjects: string[]; ambiguous_subjects: string[] } }>(
        `/api/school-exams/reports/${encodeURIComponent(reportId)}/match`,
        'POST',
        {},
      ),
    confirmSchoolExamReport: reportId =>
      call<SchoolExamReport & { ledger?: { applied_subjects: string[]; conflict_subjects: string[]; skipped_subjects: string[] } }>(
        `/api/school-exams/reports/${encodeURIComponent(reportId)}/confirm`,
        'POST',
        { confirmed: true },
      ),
    updateSchoolExamReport: (reportId, patch) =>
      call<SchoolExamReport>(`/api/school-exams/reports/${encodeURIComponent(reportId)}`, 'PATCH', patch),
    supplementSchoolExamReportSubject: (reportId, payload) =>
      call<SchoolExamReport>(`/api/school-exams/reports/${encodeURIComponent(reportId)}/subjects`, 'POST', payload),
    generateSchoolExamReportItemDrafts: reportId =>
      call<{ created: number; skipped: number; unmapped_subjects: string[]; auto_mapped: number }>(
        `/api/school-exams/reports/${encodeURIComponent(reportId)}/items/drafts`,
        'POST',
        {},
      ),
    aiMapSchoolExamReportItems: reportId =>
      call<{ mapped: number; failed_subjects: string[] }>(
        `/api/school-exams/reports/${encodeURIComponent(reportId)}/items/ai-map`,
        'POST',
        {},
      ),
    listSchoolExamReportAnswerCards: reportId =>
      call<SchoolExamReportAttachment[]>(`/api/school-exams/reports/${encodeURIComponent(reportId)}/answer-cards`),
    buildSchoolExamReportAnswerCards: (reportId, rotation) =>
      call<{ created: number; attachments: SchoolExamReportAttachment[] }>(
        `/api/school-exams/reports/${encodeURIComponent(reportId)}/answer-cards?rotation=${rotation}`,
        'POST',
        {},
      ),
    fetchSchoolExamReportAnswerCardImage: async (reportId, attachmentId) => {
      const res = await fetch(
        `/api/school-exams/reports/${encodeURIComponent(reportId)}/answer-cards/${encodeURIComponent(attachmentId)}/image`,
        { headers: { Authorization: `Bearer ${token}` }, cache: 'no-store' },
      )
      if (!res.ok) throw new ApiError(res.status, `HTTP ${res.status}`)
      return res.blob()
    },
    k12100SyncStatus: () => call<K12100RuntimeStatus>('/api/school-exams/k12100-sync/status'),
    schoolExamSyncCenter: () => call<SchoolExamSyncCenter>('/api/school-exams/sync-center'),
    scanSchoolExamPapers: () => call<SchoolExamScanResult>('/api/school-exams/pipeline/scan', 'POST', { apply_imports: false }),
    acquireSchoolExamPapers: () =>
      call<{ source_adapter: string[]; acquired_count: number; files: string[] }>(
        '/api/school-exams/pipeline/acquire',
        'POST',
        {},
      ),
    matchSchoolExamPaper: (paperId, input = {}) =>
      call<{ paper: SchoolExamPaper; match?: SchoolExamMatchResult }>(
        `/api/school-exams/pipeline/papers/${encodeURIComponent(paperId)}/match`,
        'POST',
        {
          ...(input.examId ? { exam_id: input.examId } : {}),
          confirmed_by_human: input.confirmedByHuman ?? false,
        },
      ),
    importSchoolExamPaper: paperId =>
      call<{
        already_imported: boolean
        paper: SchoolExamPaper
        attachment_created: boolean
        attachment?: SchoolPaperAttachment
        metadata_updates?: string[]
      }>(`/api/school-exams/pipeline/papers/${encodeURIComponent(paperId)}/import`, 'POST'),
    rejectSchoolExamPaper: paperId =>
      call<{ paper: SchoolExamPaper }>(
        `/api/school-exams/pipeline/papers/${encodeURIComponent(paperId)}/reject`,
        'POST',
      ),
    schoolExamRanks: examId =>
      call<SchoolExamRanksPayload>(`/api/school-exams/${encodeURIComponent(examId)}/ranks`),
    confirmSchoolExamRank: (examId, rankId) =>
      call<SchoolExamRank>(
        `/api/school-exams/${encodeURIComponent(examId)}/ranks/${encodeURIComponent(rankId)}/confirm`,
        'POST',
        { confirmed_by_human: true },
      ),
    collectSchoolExamPaper: (paperId, options = {}) =>
      call<K12100SyncJob>(
        `/api/school-exams/pipeline/papers/${encodeURIComponent(paperId)}/collect`,
        'POST',
        {
          use_ai: options.useAi ?? true,
          extract_existing_pdfs: options.extractExistingPdfs ?? true,
          upload_missing_cards: options.uploadMissingCards ?? true,
          replace_unconfirmed_drafts: options.replaceUnconfirmedDrafts ?? true,
          headless: options.headless ?? false,
        },
      ),
    startK12100SyncJob: (options = {}) =>
      call<K12100SyncJob>('/api/school-exams/k12100-sync/jobs', 'POST', {
        ...(options.examKeyword ? { exam_keyword: options.examKeyword } : {}),
        ...(options.targetExamDate ? { target_exam_date: options.targetExamDate } : {}),
        ...(options.seriesTitlePrefix ? { series_title_prefix: options.seriesTitlePrefix } : {}),
        max_exams: options.maxExams ?? 1,
        confirm_total_scores: options.confirmTotalScores ?? false,
        extract_existing_pdfs: options.extractExistingPdfs ?? true,
        upload_missing_cards: options.uploadMissingCards ?? true,
        replace_unconfirmed_drafts: options.replaceUnconfirmedDrafts ?? true,
        use_ai: options.useAi ?? true,
        headless: options.headless ?? true,
      }),
    startK12100ReportJob: (options = {}) =>
      call<K12100SyncJob>('/api/school-exams/k12100-sync/report-jobs', 'POST', {
        max_exams: options.maxExams ?? 3,
        headless: options.headless ?? false,
      }),
    hydrateK12100LocalReports: () =>
      call<{
        deduped_reports: number
        reparsed_reports: number
        ranks_synced: number
        cards_synced: number
        drafts_created: number
        synced_reports: K12100SyncedReportSummary[]
        sync_readiness?: K12100SyncReadiness
      }>('/api/school-exams/k12100-sync/hydrate-local', 'POST'),
    k12100SyncJob: jobId => call<K12100SyncJob>(`/api/school-exams/k12100-sync/jobs/${encodeURIComponent(jobId)}`),
    importK12100Bundle: (bundle, options = {}) =>
      call<K12100BackfillResult>('/api/school-exams/k12100-sync/import-bundle', 'POST', {
        bundle,
        ...(options.examKeyword ? { exam_keyword: options.examKeyword } : {}),
        ...(options.targetExamDate ? { target_exam_date: options.targetExamDate } : {}),
        ...(options.seriesTitlePrefix ? { series_title_prefix: options.seriesTitlePrefix } : {}),
        max_exams: options.maxExams ?? 1,
        confirm_total_scores: options.confirmTotalScores ?? false,
        extract_existing_pdfs: options.extractExistingPdfs ?? true,
        upload_missing_cards: options.uploadMissingCards ?? true,
        replace_unconfirmed_drafts: options.replaceUnconfirmedDrafts ?? true,
        use_ai: options.useAi ?? true,
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
    adminWrongDiagnostics: (subject, limit = 20) =>
      call<AdminWrongDiagnosticListItem[]>(`/api/admin/wrong-diagnostics?subject=${subject}&limit=${limit}`),
    adminWrongDiagnosticDetail: attemptId =>
      call<AdminWrongDiagnosticDetail>(`/api/admin/wrong-diagnostics/${encodeURIComponent(attemptId)}`),
    adminAnalyzeWrongDiagnostic: attemptId =>
      call<AdminWrongDiagnosticDetail>(`/api/admin/wrong-diagnostics/${encodeURIComponent(attemptId)}/analyze`, 'POST'),
    adminSelectWrongDiagnosticSolution: (attemptId, { optionId, adminNote }) =>
      call<AdminWrongDiagnosticDetail>(
        `/api/admin/wrong-diagnostics/${encodeURIComponent(attemptId)}/select-solution`,
        'POST',
        { option_id: optionId, admin_note: adminNote ?? null }
      ),
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
  FULL_SCORE_ITEM_HAS_NO_ERROR_CATEGORY: '满分小题无需标注错因分类。',
  SCHOOL_ITEM_LABEL_CONFLICT: '该场考试已存在相同题号，请勿重复录入。',
  SCHOOL_EXAM_ALREADY_CONFIRMED: '该场校考总分已完成人工核对，不能重复确认。',
  SCHOOL_EXAM_IMMUTABLE: '该场校考总分已核对锁定，不可直接修改原总分。',
  ATTEMPT_NOT_WRONG: '该条作答未失分，无需进入错因诊断。',
  DIAGNOSIS_NOT_FOUND: '尚未生成 AI 错因分析，请先点击分析按钮。',
  INVALID_SOLUTION_OPTION: '选定的解决方案编号不在本次诊断方案内。',
  SCHOOL_ITEM_ALREADY_CONFIRMED: '该小题已完成人工确认，不可重复确认。',
  SCHOOL_ITEM_IMMUTABLE: '该小题已人工确认并锁定，不可丢弃或修改已锁得分。',
  SCHOOL_ITEM_DUPLICATE_CONFIRM: '批量确认中包含重复小题编号，请刷新后重试。',
  VISION_PARSER_NOT_CONFIGURED: '服务端未配置智能识图服务密钥，请检查环境配置后重试。',
  VISION_PARSER_TIMEOUT: '智能多模态解析超时（已识别部分已保存，可再次点击继续识别剩余题目）。',
  VISION_PARSER_UNAVAILABLE: '暂时无法连接智能多模态服务（网络中断或服务不可达），请稍后重试。',
  VISION_PARSER_TRUNCATED: 'AI 模型思考/输出长度达到上限被提前截断，未能返回完整 JSON（已自动保留已完成题目，可再次点击继续）。',
  VISION_PARSER_INVALID_JSON: 'AI 模型返回的内容不是有效 JSON 结构（可能返回了纯文本说明或格式异常），无法自动转入草稿。',
  COACH_NOT_CONFIGURED: '我的书童暂时休息中（未配置 AI 密钥），可以直接切回三步卡片完成复盘。',
  COACH_TURN_LIMIT_REACHED: '这道题已经聊得很充分啦，点下方按钮把刚才的想法整理成提醒卡吧。',
  COACH_DIALOGUE_TOO_SHORT: '先和书童多聊一两句，说出自己的真实思路后再整理提醒卡哦。',
  NO_EMBEDDED_TEXT_FOR_SKELETON: '所选附件不含可机读文字层（属纯扫描件），无法本地提取骨架；请改用智能多模态模式。',
  UNSUPPORTED_ATTACHMENT_FOR_PARSING: '所选附件格式不支持自动提取（支持文档或图片格式）。',
  ATTACHMENT_NOT_FOUND: '未找到选中的附件，请刷新列表后重试。',
  K12100_LOCAL_RUNNER_UNAVAILABLE: '当前后端处于容器隔离或未部署宿主机浏览器，请上传宿主机导出的脱敏采集数据包，或在宿主机终端直连补全。',
  K12100_CREDENTIALS_NOT_CONFIGURED: '宿主机尚未配置校考平台账号与私密目录权限，请先在宿主机完成凭据初始化，或直接导入脱敏采集包。',
  K12100_SYNC_ALREADY_RUNNING: '已有全科校考同步任务正在运行中，请等待当前任务完成，避免触发平台限流。',
  K12100_SYNC_JOB_NOT_FOUND: '未找到对应的同步任务记录（服务可能已重启），请重新查看状态或再次启动。',
  K12100_BUNDLE_TOO_LARGE: '上传的采集包体积超过 15 兆字节上限，请减少单次采集场次或剔除大图后重试。',
  K12100_NO_EXAMS: '平台未列出可采集考试，可能关键词不匹配、页面无考试或账号无可见成绩；未写入任何数据。',
  K12100_NO_SUBJECTS: '已找到考试但没有取得任何科目数据；未写入任何数据，请检查平台页面或改用手动采集包。',
  K12100_INVALID_BUNDLE: '采集数据包结构无效，请使用本地命令行采集脚本生成的最新脱敏文件。',
  K12100_UNSAFE_CARD_URL: '检测到不安全的答题卡图片链接（仅允许官方安全加密域名且拒绝内网地址），已安全拦截。',
  K12100_CARD_DOWNLOAD_FAILED: '答题卡图片下载失败（签名链接可能已过期），请重新采集含内嵌图片的数据包后导入。',
  K12100_REPORT_NOT_PDF: '从 k12100 下载的报告文件不是合法 PDF 或超出大小限制。',
  K12100_LOGIN_REQUIRED: 'k12100 会话已失效，请勾选可见浏览器窗口重新登录后再试。',
  K12100_CIRCUIT_BREAKER: '检测到验证码或频控响应，已立即熔断止损。',
  K12100_BROWSER_FAILED: '浏览器未能完成报告下载，请检查网络或改用本地报告导入。',
  SOURCE_NOT_CONFIGURED: '未配置真实授权学校试卷来源；本地扫描仍可用，系统不会伪造远程下载。',
  INBOX_PERMISSIONS_TOO_WIDE: '私有收件箱权限过宽，必须收紧为 0700 后才可扫描。',
  INBOX_SYMLINK_REJECTED: '私有收件箱本身是符号链接，已拒绝读取。',
  SOURCE_SYMLINK_REJECTED: '来源目录是符号链接，已拒绝读取。',
  SCHOOL_EXAM_MATCH_REQUIRED: '该试卷尚未完成唯一匹配或人工确认，不能导入考试档案。',
  SCHOOL_EXAM_SUBJECT_MISMATCH: '候选考试的学科与卷头不一致，不能人工绑定。',
  HUMAN_CONFIRMATION_REQUIRED: '该操作必须由人工显式确认。',
  PAPER_ALREADY_IMPORTED: '该试卷已入档，不能重新匹配或忽略。',
  PAPER_FILE_MISSING: '私有原件不存在，请重新扫描原文件。',
  PAPER_HASH_MISMATCH: '私有原件哈希与登记不一致，已拒绝继续处理。',
  RANK_OWNERSHIP_UNVERIFIED: '该排名未通过本人归属校验，不能确认或入档。',
  AWAITING_EXAM_DATE: '平台未提供可验证考试日期，已停止自动建档，不能用当前日期替代。',
}

export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return '访问令牌无效或已过期，请重新输入。'
    if (error.status === 403) return '凭据权限不足或使用了错误的角色凭据（如学生凭据访问管理端）。'
    const httpMatch = /^VISION_PARSER_HTTP_(\d+)$/.exec(error.code)
    if (httpMatch) {
      return `上游 AI 视觉接口返回 HTTP ${httpMatch[1]} 错误（请检查模型名称、API Key 额度或服务状态）。`
    }
    if (error.code.startsWith('COACH_UNAVAILABLE:')) {
      return error.code.replace(/^COACH_UNAVAILABLE:\s*/i, '') || '我的书童暂时连不上，可以先切回三步卡片完成复盘。'
    }
    return API_CODE_TEXT[error.code] ?? error.code
  }
  if (error instanceof TypeError) return '无法连接服务器，请检查网络连接后重试。'
  return String(error)
}
