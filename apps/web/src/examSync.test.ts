import { describe, expect, it } from 'vitest'
import {
  compareQuestionLabel,
  deriveReviewCoverage,
  formatPaperExamIdentity,
  formatPaperSubject,
  formatQuestionLabelHeading,
  formatRankValue,
  getMatchMeta,
  getPaperNextStep,
  getReportActionMeta,
  groupSchoolReflectionsByExam,
  inferSchoolAttachmentSubject,
  inferSchoolExamItemSubject,
  isSchoolItemFullScore,
  parseDraftBasisTags,
  summarizeReportJob,
  summarizeSchoolExamItemScores,
  validateReflectionDraftLocally,
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

    const multiRanks: SchoolExamRanksPayload = {
      exam_id: 'e-all',
      ranks: [
        { ...ranks.ranks[0], id: 'r-math', subject_scope: 'math', scope: 'class', rank_value: 13 },
        { ...ranks.ranks[0], id: 'r-eng-c', subject_scope: 'english', scope: 'class', rank_value: 16 },
        { ...ranks.ranks[0], id: 'r-eng-g', subject_scope: 'english', scope: 'grade', rank_value: 525 },
      ],
      missing_scopes: ['school', 'region'],
      disclaimer: '不进入画像',
    }
    const mathCov = deriveReviewCoverage(detail({ subject: 'all' }), multiRanks, 'math')
    expect(mathCov.rankScopes).toEqual(['class'])
    expect(mathCov.missingRankScopes).toEqual(['grade', 'school', 'region'])
    const engCov = deriveReviewCoverage(detail({ subject: 'all' }), multiRanks, 'english')
    expect(engCov.rankScopes).toEqual(['class', 'grade'])
    expect(engCov.missingRankScopes).toEqual(['school', 'region'])
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

  it('校考小题按题号自然升序排列、纯数字题号规范化且分值对账精确', () => {
    const raw = ['10', '第2题', '1', '18(2)', '18(1)', '附加题']
    expect([...raw].sort(compareQuestionLabel)).toEqual(['1', '第2题', '10', '18(1)', '18(2)', '附加题'])
    expect(formatQuestionLabelHeading('1')).toBe('第 1 题')
    expect(formatQuestionLabelHeading('第10题')).toBe('第10题')
    expect(isSchoolItemFullScore(2, 2)).toBe(true)
    expect(isSchoolItemFullScore(1.5, 2)).toBe(false)

    const scoreSum = summarizeSchoolExamItemScores(
      detail({
        earned_points: 4,
        max_points: 4,
        confirmed_by_user: true,
        items: [
          {
            id: 'i1',
            question_label: '1',
            knowledge_id: 'math.arithmetic',
            earned_points: 2,
            max_points: 2,
            scoring_origin: 'ocr_draft',
            confirmed_by_user: true,
          },
          {
            id: 'i2',
            question_label: '2',
            knowledge_id: 'unmapped',
            earned_points: 2,
            max_points: 2,
            scoring_origin: 'ocr_draft',
            confirmed_by_user: false,
          },
        ],
      }),
    )
    expect(scoreSum.totalEarned).toBe(4)
    expect(scoreSum.totalMax).toBe(4)
    expect(scoreSum.correctPendingCount).toBe(1)
    expect(scoreSum.lostPendingCount).toBe(0)
    expect(scoreSum.earnedDiff).toBe(0)
    expect(scoreSum.maxDiff).toBe(0)
  })

  it('parseDraftBasisTags 将识别依据拆解为来源/题型/匹配方式微标签', () => {
    expect(parseDraftBasisTags('分析报告册第13页；题型=单选题；单选题第1题考纲先验', 'type_inferred')).toEqual([
      { kind: 'source', label: '报告册P13' },
      { kind: 'qtype', label: '单选题' },
      { kind: 'match', label: '单选题第1题考纲先验' },
    ])
    expect(parseDraftBasisTags('从原卷文字层提取题号与分值', 'auto_matched')).toEqual([
      { kind: 'source', label: '原卷文字层' },
      { kind: 'match', label: '关键词匹配' },
    ])
    expect(parseDraftBasisTags(null, null)).toEqual([])
  })

  it('validateReflectionDraftLocally 拦截套话、刷屏与未补全的句式起头，并放行具体复盘', () => {
    expect(validateReflectionDraftLocally('太粗心了没看清', '下次一定注意认真审题')).not.toBeNull()
    expect(validateReflectionDraftLocally('1111111111111', 'aaaaaaaaaaaaa')).not.toBeNull()
    expect(
      validateReflectionDraftLocally(
        '题目里的「」条件我没用上，当时以为',
        '如果再看到「」，我就先「」。',
      ),
    ).not.toBeNull()
    expect(
      validateReflectionDraftLocally(
        '题目里的「x大于零」条件我没用上，当时以为可以直接代入负一求解',
        '如果再看到「分式不等式」，我就先「圈出定义域再求解并逐个验根」。',
      ),
    ).toBeNull()
    expect(
      validateReflectionDraftLocally(
        '解分式方程时两边同乘最简公分母后忘记检验增根 x=2',
        '解出未知数后必须立即代回原分母验证不为零再作答',
      ),
    ).toBeNull()
  })

  it('groupSchoolReflectionsByExam 按校考台账场次分组并汇总状态计数', () => {
    const groups = groupSchoolReflectionsByExam([
      {
        item_id: 'i1',
        exam_id: 'e2',
        subject: 'math',
        exam_title: '十月月考',
        exam_date: '2026-10-20',
        question_label: '第1题',
        topic: '有理数',
        earned_points: 0,
        max_points: 2,
        lost_points: 2,
        reflection_status: 'pending',
        stuck_point: '',
        fix_strategy: '',
      },
      {
        item_id: 'i2',
        exam_id: 'e1',
        subject: 'math',
        exam_title: '九月练习',
        exam_date: '2026-09-18',
        question_label: '第5题',
        topic: '二次方程',
        earned_points: 1,
        max_points: 3,
        lost_points: 2,
        reflection_status: 'completed',
        stuck_point: 'abc',
        fix_strategy: 'def',
      },
      {
        item_id: 'i3',
        exam_id: 'e2',
        subject: 'math',
        exam_title: '十月月考',
        exam_date: '2026-10-20',
        question_label: '第2题',
        topic: '整式',
        earned_points: 0,
        max_points: 2,
        lost_points: 2,
        reflection_status: 'needs_revision',
        stuck_point: '',
        fix_strategy: '',
      },
    ])
    expect(groups).toHaveLength(2)
    expect(groups[0].examId).toBe('e2')
    expect(groups[0].pendingCount).toBe(2)
    expect(groups[0].needsRevisionCount).toBe(1)
    expect(groups[0].items.map(i => i.item_id)).toEqual(['i1', 'i3'])
    expect(groups[1].examId).toBe('e1')
    expect(groups[1].completedCount).toBe(1)
  })

  it('全科档案按当前科目推断学科（含 *_cand. 新版编码）并分别统计覆盖与分值汇总', () => {
    expect(inferSchoolExamItemSubject({ question_label: '数学·1', knowledge_id: 'unmapped' })).toBe('math')
    expect(inferSchoolExamItemSubject({ question_label: '第8题', knowledge_id: 'chinese_cand.base.contextual_expression' })).toBe('chinese')
    expect(inferSchoolExamItemSubject({ question_label: '第2题', knowledge_id: 'ethics.general' })).toBe('ethics')
    expect(inferSchoolAttachmentSubject({ filename: '报告答题卡-physics-第19页.png' })).toBe('physics')

    const allDetail = detail({
      subject: 'all',
      earned_points: 273,
      max_points: 420,
      confirmed_by_user: true,
      items: [
        {
          id: 'm1',
          question_label: '数学·1',
          knowledge_id: 'math_cand.num.rational',
          earned_points: 2,
          max_points: 2,
          scoring_origin: 'ocr_draft',
          confirmed_by_user: true,
        },
        {
          id: 'm2',
          question_label: '数学·2',
          knowledge_id: 'math_cand.num.rational',
          earned_points: 1,
          max_points: 2,
          scoring_origin: 'ocr_draft',
          confirmed_by_user: false,
        },
        {
          id: 'c1',
          question_label: '语文·1',
          knowledge_id: 'chinese_cand.base.contextual_expression',
          earned_points: 2,
          max_points: 2,
          scoring_origin: 'ocr_draft',
          confirmed_by_user: true,
        },
      ],
      attachments: [
        {
          id: 'am',
          filename: '报告答题卡-math-第9页.png',
          media_type: 'image/png',
          sha256: 'c'.repeat(64),
          byte_size: 100,
          created_at: '2026-11-21T00:00:00Z',
        },
        {
          id: 'ac',
          filename: '报告答题卡-chinese-第4页.png',
          media_type: 'image/png',
          sha256: 'd'.repeat(64),
          byte_size: 100,
          created_at: '2026-11-21T00:00:00Z',
        },
      ],
    })

    const mathCoverage = deriveReviewCoverage(allDetail, null, 'math')
    expect(mathCoverage.confirmedItems).toBe(1)
    expect(mathCoverage.draftItems).toBe(1)
    expect(mathCoverage.attachments).toBe(1)

    const mathSummary = summarizeSchoolExamItemScores(allDetail, 'math', {
      earned_points: 3,
      max_points: 4,
      confirmed_by_user: true,
    })
    expect(mathSummary.totalEarned).toBe(3)
    expect(mathSummary.totalMax).toBe(4)
    expect(mathSummary.pendingCount).toBe(1)
    expect(mathSummary.confirmedCount).toBe(1)
    expect(mathSummary.earnedDiff).toBe(0)
    expect(mathSummary.maxDiff).toBe(0)
  })
})
