import { describe, expect, it } from 'vitest'
import {
  LOCALE_PREFS,
  formatClauseTitle,
  formatKnowledgeTitle,
  formatReleaseChineseName,
  getDomainLabel,
  getK12ScoreStatusLabel,
  getKnowledgeLabel,
  getMediaTypeLabel,
  getModelVersionLabel,
  getOperatorLabel,
  getParserModeLabel,
  getReleaseStatusLabel,
  getSchoolErrorCategoryLabel,
  getStemModeLabel,
  getSubjectKnowledgeOptions,
  getSubjectLabel,
  getSyncJobStateLabel,
  resolveKnowledgeCodeInput,
  SCHOOL_ERROR_CATEGORY_OPTIONS,
} from './knowledge'

describe('knowledge 与 locale-labels 配置文件读取与本地化解析', () => {
  it('正确解析经典节点与全部测试合成节点中文名称', () => {
    expect(getKnowledgeLabel('math.ok')).toBe('达标考点（对照）')
    expect(getKnowledgeLabel('math.listen')).toBe('听力理解（音频单选）')
    expect(getKnowledgeLabel('math.gap')).toBe('差距考点（薄弱短板）')
    expect(getKnowledgeLabel('physics.optics.demo')).toBe('光学与成像实验')
    expect(getKnowledgeLabel('english.zero_test')).toBe('英语零余量验证考点')
  })

  it('正确解析四科 2022 课标候选节点中文名称', () => {
    expect(getKnowledgeLabel('math_cand.num.rational')).toBe('有理数及其运算')
    expect(getKnowledgeLabel('chinese_cand.poetry.appreciation')).toBe('古代诗词意象意境与手法鉴赏')
    expect(getKnowledgeLabel('english_cand.syntax.object_clause')).toBe('宾语从句')
    expect(getKnowledgeLabel('physics_cand.energy.ohm_law')).toBe('欧姆定律及其电路综合应用')
  })

  it('未在配置文件中配置的未知知识点安全回退返回原始 ID', () => {
    expect(getKnowledgeLabel('unmapped.unknown.demo')).toBe('unmapped.unknown.demo')
    expect(getKnowledgeLabel('')).toBe('')
    expect(formatKnowledgeTitle('unknown.code')).toBe('unknown.code')
  })

  it('正确解析媒体格式、模型版本、操作员、发布状态与课标条款中文标题', () => {
    expect(LOCALE_PREFS.showTechnicalCodesByDefault).toBe(false)
    expect(getMediaTypeLabel('application/pdf')).toBe('PDF 文档')
    expect(getMediaTypeLabel('audio/mpeg')).toBe('MP3 音频')
    expect(getModelVersionLabel('v1.6-uncalibrated-rule')).toBe('V1.6 规则诊断基线（未校准）')
    expect(getModelVersionLabel('guidance-heuristic-v0.1-unvalidated')).toBe('启发式学情诊断基线 v0.1（未校准）')
    expect(getDomainLabel('num_alg')).toBe('数与代数')
    expect(getDomainLabel('geom')).toBe('图形与几何')
    expect(getDomainLabel('motion_energy')).toBe('运动、相互作用与能量')
    expect(getOperatorLabel('admin_owner')).toBe('系统管理员')
    expect(getOperatorLabel('beijing_zhongkao_expert')).toBe('北京市中考全科教研专家')
    expect(getOperatorLabel('张老师')).toBe('张老师')
    expect(getReleaseStatusLabel('active')).toBe('正式生效')
    expect(getReleaseStatusLabel('published')).toBe('已正式发布')
    expect(formatReleaseChineseName('math-v2022.1.0')).toBe('数学 2022 课标正式版 第 1.0 版')
    expect(formatClauseTitle('cs:math:2022-errata:s4:num_alg:content_req:rat_num:c01')).toBe(
      '数学课标 · 数与代数 · 内容要求（条目 C01）'
    )
    expect(
      formatClauseTitle('cs:math:2022-errata:s4:num_alg:content_req:rat_num:c01', {
        domain_title: '数与代数',
        theme_title: '数与式',
        sub_theme: '有理数',
        clause_number: '1.1',
      })
    ).toBe('数与代数 · 数与式 · 有理数（1.1）')
    expect(SCHOOL_ERROR_CATEGORY_OPTIONS).toHaveLength(6)
    expect(getSchoolErrorCategoryLabel('concept')).toBe('概念/公式不清')
    expect(getSchoolErrorCategoryLabel('calculation')).toBe('运算/粗心失误')
    expect(getSchoolErrorCategoryLabel(null)).toBe('未归类错因')
  })

  it('正确解析学科、同步任务状态、解析方式与中文知识点下拉反查', () => {
    expect(getSubjectLabel('chemistry')).toBe('化学')
    expect(getOperatorLabel('owner')).toBe('本人 / 管理员')
    expect(getSyncJobStateLabel('queued')).toBe('排队等待中')
    expect(getSyncJobStateLabel('completed')).toBe('已完成')
    expect(getParserModeLabel('deepseek_vision:deepseek-chat')).toBe('多模态智能识图')
    expect(getParserModeLabel('external_local_rules')).toBe('本地规则匹配')
    expect(getK12ScoreStatusLabel('locked_conflict')).toBe('已锁定总分冲突（保留原值）')
    expect(getStemModeLabel('pdf_local_regex')).toBe('原卷文本规则提取')

    const mathOpts = getSubjectKnowledgeOptions('math')
    expect(mathOpts.length).toBeGreaterThan(10)
    expect(mathOpts.some(o => o.code === 'math.arithmetic' && o.label === '基础算术运算')).toBe(true)
    expect(mathOpts.some(o => o.isCandidate)).toBe(false)

    // 中文名称应优先反查为当前学科正式知识点编码，编码输入则原样保留
    expect(resolveKnowledgeCodeInput('基础算术运算', 'math')).toBe('math.arithmetic')
    expect(resolveKnowledgeCodeInput('代词分类与用法', 'english')).toBe('english.grammar.pronoun')
    expect(resolveKnowledgeCodeInput('math.num.real', 'math')).toBe('math.num.real')
    expect(resolveKnowledgeCodeInput('道法综合主题', 'ethics')).toBe('道法综合主题')
  })
})
