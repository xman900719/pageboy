import { describe, expect, it } from 'vitest'
import {
  deriveReviewCoverage,
  formatPaperExamIdentity,
  formatPaperSubject,
  formatRankValue,
  getMatchMeta,
  getPaperNextStep,
  getReportActionMeta,
  summarizeReportJob,
} from './examSync'
import type { K12100ReportJobResult, SchoolExamDetail, SchoolExamPaper, SchoolExamRanksPayload } from './api'

function paper(overrides: Partial<SchoolExamPaper> = {}): SchoolExamPaper {
  return {
    id: 'p1',
    filename: '虚构测试数据.docx',
    sha256: 'a'.repeat(64),
    media_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    byte_size: 100,
    source_kind: 'local_scan',
    source_name: 'inbox',
    source_ref: 'inbox/虚构测试数据.docx',
    status: 'needs_review',
    match_state: 'CONFLICT',
    header: {
      subject: 'math',
      academic_year: '2025-2026',
      grade: '九年级',
      exam_type: 'monthly',
      exam_date: '2025-10-12',
      exam_type_label: '月考',
      confidence: 'high',
      complete: true,
      fields: {},
      text_excerpt: '',
      warnings: [],
    },
    candidates: [],
    school_exam_id: null,
    exam: null,
    error_code: null,
    imported_at: null,
    created_at: '2026-11-15T00:00:00Z',
    updated_at: '2026-11-15T00:00:00Z',
    ...overrides,
  }
}

function detail(overrides: Partial<SchoolExamDetail> = {}): SchoolExamDetail {
  return {
    id: 'e1',
    subject: 'math',
    title: '虚构测试数据 月考',
    exam_date: '2025-10-12',
    earned_points: 88,
    max_points: 100,
    confirmed_by_user: false,
    items: [
      {
        id: 'i1',
        question_label: '第1题',
        knowledge_id: 'math.arithmetic',
        earned_points: 2,
        max_points: 2,
        scoring_origin: 'ocr_draft',
        confirmed_by_user: true,
      },
      {
        id: 'i2',
        question_label: '第2题',
        knowledge_id: 'math.arithmetic',
        earned_points: 0,
        max_points: 2,
        scoring_origin: 'ocr_draft',
        confirmed_by_user: false,
      },
    ],
    attachments: [
      {
        id: 'a1',
        filename: '虚构测试数据.pdf',
        media_type: 'application/pdf',
        sha256: 'b'.repeat(64),
        byte_size: 100,
        created_at: '2026-11-15T00:00:00Z',
      },
    ],
    ...overrides,
  }
}

describe('examSync 四步状态与核对覆盖', () => {
  it('只按真实流程状态决定下一步，不把冲突当作成功', () => {
    expect(getPaperNextStep(null)).toBe(1)
    expect(getPaperNextStep(paper())).toBe(2)
    expect(getPaperNextStep(paper({ status: 'matched' }))).toBe(3)
    expect(getPaperNextStep(paper({ status: 'imported' }))).toBe(4)
    expect(getMatchMeta('CONFLICT').tone).toBe('bad')
    expect(getMatchMeta('AMBIGUOUS').label).toBe('多个候选')
    expect(getMatchMeta('AMBIGUOUS').tone).toBe('wait')
    expect(getMatchMeta('EXACT_MATCH').tone).toBe('good')
    expect(getMatchMeta(undefined).label).toBe('未匹配')
  })

  it('卷头身份与学科使用中文展示，缺失不伪造', () => {
    expect(formatPaperExamIdentity(paper())).toBe('九年级 · 月考 · 2025-10-12')
    expect(formatPaperSubject(paper())).toBe('数学')
    const empty = paper()
    empty.header.grade = null
    empty.header.exam_type = null
    empty.header.exam_type_label = null
    empty.header.exam_date = null
    expect(formatPaperExamIdentity(empty)).toBe('卷头身份不完整')
  })

  it('统一练习保留自身类型并显示单一日期', () => {
    const item = paper()
    item.header.exam_type = 'unified_practice'
    item.header.exam_type_label = '统一练习'
    item.header.exam_date = '2026-10'
    expect(formatPaperExamIdentity(item)).toBe('九年级 · 统一练习 · 2026-10')
  })

  it('本人排名缺失人数时不显示 0 人', () => {
    expect(formatRankValue({ rank_value: 5, participant_count: 320 })).toBe('第 5 名 / 320 人')
    expect(formatRankValue({ rank_value: 5, participant_count: null })).toBe('第 5 名')
  })

  it('待核对总分与草稿、附件、排名缺失独立呈现', () => {
    const ranks: SchoolExamRanksPayload = {
      exam_id: 'e1',
      ranks: [
        {
          id: 'r1',
          subject_scope: 'math',
          scope: 'class',
          rank_value: 5,
          participant_count: 320,
          percentile: 0.96,
          source_name: 'k12100',
          source_field: 'classrank',
          ownership_status: 'verified',
          ownership_basis: 'test_fixture',
          review_status: 'pending',
          captured_at: '2026-11-15T00:00:00Z',
          history_count: 1,
        },
      ],
      missing_scopes: ['grade', 'school', 'region'],
      disclaimer: '不进入画像',
    }
    const coverage = deriveReviewCoverage(detail(), ranks)
    expect(coverage.hasExam).toBe(true)
    expect(coverage.totalStatus).toBe('pending')
    expect(coverage.totalText).toBe('88 / 100')
    expect(coverage.confirmedItems).toBe(1)
    expect(coverage.draftItems).toBe(1)
    expect(coverage.attachments).toBe(1)
    expect(coverage.rankScopes).toEqual(['class'])
    expect(coverage.missingRankScopes).toEqual(['grade', 'school', 'region'])
  })

  it('没有考试档案时如实返回缺失，不把 0 当作分数', () => {
    const coverage = deriveReviewCoverage(null, null)
    expect(coverage.hasExam).toBe(false)
    expect(coverage.totalStatus).toBe('missing')
    expect(coverage.totalText).toContain('待关联')
  })

  it('报告同步摘要正确汇总新建/更新/冲突/草稿与徽标色调', () => {
    expect(getReportActionMeta('created')).toEqual({ label: '新建待核对', tone: 'good' })
    expect(getReportActionMeta('locked_conflict')).toEqual({ label: '锁分冲突', tone: 'bad' })
    expect(getReportActionMeta('awaiting_exam_date')).toEqual({ label: '缺日期未建档', tone: 'wait' })

    const sample: K12100ReportJobResult = {
      home_exams: [],
      reports: [],
      subject_actions: [],
      totals: {
        home_exams: 3,
        skipped_existing: 1,
        downloaded: 2,
        reports_registered: 2,
        created_exams: 4,
        updated_exams: 1,
        filled_exams: 2,
        unchanged_exams: 0,
        locked_conflicts: 1,
        identity_conflicts: 0,
        awaiting_exam_date: 0,
        ambiguous_exams: 0,
        drafts_created: 18,
        drafts_updated: 3,
        auto_mapped: 5,
        cards_created: 6,
        cards_synced: 6,
        failures: 0,
      },
      failures: [],
      knowledge_evidence_created: 0,
    }
    const summary = summarizeReportJob(sample)
    expect(summary.homeExams).toBe(3)
    expect(summary.skippedExisting).toBe(1)
    expect(summary.created).toBe(4)
    expect(summary.conflicts).toBe(1)
    expect(summary.draftsChanged).toBe(21)
    expect(summary.hasIssues).toBe(true)
    expect(summarizeReportJob(null).hasIssues).toBe(false)
  })
})
