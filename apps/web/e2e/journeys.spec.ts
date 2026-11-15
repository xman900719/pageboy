/* V2.0：J1–J9 端到端用户旅程验收（全部数据为 globalSetup 种入的虚构测试数据）。
 *
 * 覆盖核心契约：
 * - J1 成长状态总览与缺证据诚实解释、目标保存
 * - J2 智能综合练习编排、整轮提交结算与 AI 苏格拉底启发式错题引导（mock_ai + 禁直给答案）
 * - J3 知识图谱定向 → 阶段诊断未见题基线差距 → 成长状态短板定位 → 复测改善判决与免责声明
 * - J4 学校考试总分隔离边界（总分不产生考点证据）
 * - J5 管理端题库审核台（题源→附件解析→导入→审核→发布人工门禁闭环）
 * - J6/J6b 双令牌隔离与本机记住令牌安全门禁
 * - J7 知识图谱交互展示（层级/前置关系、未掌握高亮筛选、领域过滤与清单切换）
 * - J8 管理端知识点审核台（同步候选→课标审核依据草稿→批量审核→发布版本快照）
 * - J9 练习会话刷新续答（重载恢复同一未完成会话与题干，交卷后无残留）
 */
import { test, expect, type Locator, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

const ADMIN_TOKEN = 'test-admin-secret'
const STUDENT_TOKEN = 'test-student-secret'

/* ---------- helpers ---------- */

async function enterSpace(page: Page): Promise<void> {
  await page.goto('/')
  await page.getByLabel('访问令牌').fill(STUDENT_TOKEN)
  await page.getByRole('button', { name: '进入' }).click()
  await expect(page.getByRole('navigation', { name: '主要视图' })).toBeVisible()
}

async function enterAdminSpace(page: Page): Promise<void> {
  await page.goto('/admin.html')
  await page.getByLabel('访问令牌').fill(ADMIN_TOKEN)
  await page.getByRole('button', { name: '进入' }).click()
  await expect(page.getByRole('navigation', { name: '管理视图' })).toBeVisible()
}

function navTab(page: Page, label: RegExp): Locator {
  return page.getByRole('navigation', { name: '主要视图' }).getByRole('button', { name: label })
}

function adminNavTab(page: Page, label: RegExp): Locator {
  return page.getByRole('navigation', { name: '管理视图' }).getByRole('button', { name: label })
}

function questionCard(page: Page): Locator {
  return page.getByRole('region', { name: '题目' })
}

function comparisonRow(page: Page, topic: string, root: Locator): Locator {
  return root.locator('li', { has: page.locator('.comp-topic', { hasText: topic }) })
}

/** 通用作答辅助：客观单选根据 correct 选甲/乙；短答填 x=1 或错误文本；提交并处理主观自评（若遇到）。 */
async function answerCurrentCard(page: Page, correct: boolean): Promise<void> {
  const card = questionCard(page)
  await expect(card).toBeVisible()
  const radioTarget = card.getByRole('radio', { name: correct ? /甲/ : /乙/ })
  if (await radioTarget.count() > 0) {
    await radioTarget.first().click()
  } else {
    await card.locator('textarea').fill(correct ? 'x=1' : '错误回答')
  }
  await card.getByRole('button', { name: '提交答案' }).click()
  const selfBtn = card.getByRole('button', { name: '提交自评' })
  if (await selfBtn.count() > 0) {
    await selfBtn.click()
  } else {
    await expect(card.getByText(correct ? /本题得分 [1-9]/ : '本题得分 0 /')).toBeVisible()
  }
}

/** 诚实文案红线：预测/能力值只允许出现在否定式免责声明里，「提分」绝不出现。 */
async function expectHonestLanguage(page: Page): Promise<void> {
  const text = await page.evaluate(() => document.body.innerText)
  expect(text, '页面不得出现「提分」表述').not.toContain('提分')
  for (const match of text.matchAll(/预测/g)) {
    const around = text.slice(Math.max(0, (match.index ?? 0) - 10), (match.index ?? 0) + 2)
    expect(around, `「预测」只能出现在否定式免责声明里，实际上下文为「${around}」`).toMatch(/不作|不是|不预测/)
  }
  for (const match of text.matchAll(/能力值/g)) {
    const before = text.slice(Math.max(0, (match.index ?? 0) - 10), match.index ?? 0)
    expect(before, `「能力值」只能出现在否定表述里，实际上下文为「${before}能力值」`).toMatch(/不作|不是/)
  }
}

/* ---------- J1 成长状态总览与缺证据解释 ---------- */

test('J1 成长状态总览与缺证据解释：缺证据不显示 0 分，目标经 UI 保存后反映新版本', async ({ page }) => {
  await enterSpace(page)
  await navTab(page, /成长状态/).click()

  const overview = page.getByRole('region', { name: '成长状态总览' })
  await expect(overview).toBeVisible()
  await expect(overview.getByRole('img', { name: '各知识领域实测得分率雷达图' })).toBeVisible()
  await expect(overview.locator('[aria-label="分领域掌握进度条"]')).toBeVisible()

  const strengthCard = page.getByRole('region', { name: '当前优势知识点' })
  await expect(strengthCard).toContainText('当前优势 (0)')
  await expect(strengthCard).toContainText('尚未形成达到稳定阈值')

  const weaknessCard = page.getByRole('region', { name: '当前不足与薄弱短板' })
  await expect(weaknessCard).toContainText('当前不足 (0)')
  await expect(weaknessCard).toContainText('暂未发现已确认低于阈值的薄弱知识点')

  const goalSection = page.getByRole('region', { name: '学习目标与阶段验证' })
  await expect(goalSection).toContainText('目标版本 v1')
  await expect(goalSection).toContainText('每天 15 分钟')

  const validationBox = goalSection.locator('.validation')
  await expect(validationBox).toContainText('证据不足，无法比较')
  await expect(validationBox).toContainText('还没有可用于对比的独立验证记录。')
  await expect(validationBox).toContainText('每个知识点需要至少 3 道独立未见题的基线记录与 3 道复测记录，才能进行可观察对比。')

  // 缺证据状态不得把未测领域/知识点渲染成 0% 或 0 分。
  const freshText = await page.evaluate(() => document.body.innerText)
  expect(freshText).not.toMatch(/(?<!\d)0%/)
  for (const match of freshText.matchAll(/(?<!\d)0\s*分/g)) {
    const before = freshText.slice(Math.max(0, (match.index ?? 0) - 6), match.index ?? 0)
    expect(before, `「0 分」只能出现在否定式说明里，实际上下文为「${before}0 分」`).toMatch(/不显示|不是|不会|绝不|不推算/)
  }

  // 修改并保存目标版本 v2
  await goalSection.getByRole('button', { name: '修改目标' }).click()
  await expect(goalSection.locator('.goal-form')).toBeVisible()
  await goalSection.getByLabel(/科目目标分/).fill('95')
  await goalSection.getByRole('button', { name: '保存目标' }).click()
  await expect(page.getByRole('status')).toContainText('目标已保存（第 2 版）')
  await expect(goalSection).toContainText('目标版本 v2')

  await expectHonestLanguage(page)
})

/* ---------- J2 智能综合练习 + 错题 AI 苏格拉底引导 ---------- */

test('J2 智能综合练习与 AI 错题引导：整轮作答、结算错题与多轮启发式对话不泄题', async ({ page }) => {
  await enterSpace(page)

  const lobby = page.getByRole('region', { name: '智能综合练习编排' })
  await expect(lobby).toBeVisible()
  await lobby.getByRole('button', { name: '3 题' }).click()
  await lobby.getByRole('button', { name: /开始本轮智能练习/ }).click()

  const progress = page.getByRole('region', { name: '本轮练习进度' })
  await expect(progress).toBeVisible()
  await expect(progress).toContainText('已完成 0 / 3 题')
  await expect(page.locator('.question-reason-banner')).toContainText('选题依据：')

  // 第 1 题刻意答错（选 乙），触发错题记录；第 2、3 题答对（选 甲）
  await answerCurrentCard(page, false)
  await expect(questionCard(page).getByText('评分来源：已审核答案自动比对')).toBeVisible()
  await page.getByRole('button', { name: '进入下一题 →' }).click()

  await answerCurrentCard(page, true)
  await page.getByRole('button', { name: '进入下一题 →' }).click()

  await answerCurrentCard(page, true)
  await page.getByRole('button', { name: '结束本轮并查看错题讲解' }).click()

  // 结算与错题 AI 引导抽屉自动展开
  const completion = page.getByRole('region', { name: '本轮练习结算与错题讲解' })
  await expect(completion).toBeVisible()
  await expect(completion).toContainText('共作答 3 题：客观答对 2 题，待引导订正错题 1 题')

  const tutor = page.getByRole('region', { name: 'AI 错题引导讲解' })
  await expect(tutor).toBeVisible()
  await expect(tutor).toContainText('苏格拉底启发式引导 · 不直接给答案')
  const turns = tutor.locator('.tutor-turns')
  await expect(turns).toContainText('我们先不急着下结论')
  expect(await turns.innerText()).not.toContain('正确答案是 A')

  // 学生输入思考内容，触发 AI 多轮启发式回应
  await tutor.locator('#tutor-reply-input').fill('我先看清题干里的实数条件')
  await tutor.getByRole('button', { name: '发送思路' }).click()
  await expect(turns).toContainText('我先看清题干里的实数条件')
  await expect(turns).toContainText('思路很对')

  await tutor.getByRole('button', { name: '收起讲解' }).click()
  await expect(tutor).toHaveCount(0)

  // 作答溯源区域保留可读记录
  const trace = page.getByRole('region', { name: '作答溯源记录' })
  await expect(trace).toContainText('已审核答案自动比对')

  await expectHonestLanguage(page)
})

/* ---------- J3 图谱定向 → 基线差距 → 复测改善判决 ---------- */

test('J3 知识图谱定向与阶段诊断：基线错题形成短板、复测答对形成可观察改善判决', async ({ page }) => {
  await enterSpace(page)
  await navTab(page, /知识点展示/).click()

  // 通过图谱（或清单）定位到「实数与无理数概念及估算」发起阶段诊断基线测试
  const graphSection = page.getByRole('region', { name: '知识点关系图谱展示' })
  await expect(graphSection).toBeVisible()
  await graphSection.getByRole('button', { name: '切换清单视图' }).click()
  await graphSection.locator('.graph-list-fallback').getByRole('button', { name: /实数与无理数概念及估算/ }).click()

  const detail = page.getByRole('complementary', { name: '选中知识点详情' })
  await expect(detail).toContainText('实数与无理数概念及估算')
  await detail.getByRole('button', { name: '针对此知识点开始练习' }).click()

  // 自动跳回练习大厅并锁定该知识点，启动 3 题未见题基线诊断并全部答错
  const lobby = page.getByRole('region', { name: '智能综合练习编排' })
  await expect(lobby).toContainText('已锁定知识点定向突破')
  await expect(lobby).toContainText('实数与无理数概念及估算')
  await lobby.getByRole('radio', { name: /阶段诊断/ }).click()
  await expect(lobby).toContainText('不看资料、不查工具、不问他人')
  await lobby.getByRole('button', { name: '3 题' }).click()
  await lobby.getByRole('button', { name: /开始本轮未见题诊断/ }).click()

  for (let round = 1; round <= 3; round++) {
    await answerCurrentCard(page, false)
    await expect(questionCard(page).getByText('符合独立验证条件（首次见题、独立完成），已计入阶段对比。')).toBeVisible()
    if (round < 3) {
      await page.getByRole('button', { name: '进入下一题 →' }).click()
    } else {
      await page.getByRole('button', { name: '结束本轮并查看错题讲解' }).click()
    }
  }
  await expect(page.getByRole('region', { name: '本轮练习结算与错题讲解' })).toContainText('待引导订正错题 3 题')

  // 前往「成长状态」查看：该知识点立即进入「当前不足」，且支持一键跳转针对练习
  await navTab(page, /成长状态/).click()
  const weaknessCard = page.getByRole('region', { name: '当前不足与薄弱短板' })
  await expect(weaknessCard).toContainText('实数与无理数概念及估算')
  await expect(page.getByRole('region', { name: '学习目标与阶段验证' }).locator('.validation')).toContainText('证据不足，无法比较')

  const weakRow = weaknessCard.locator('li', { hasText: '实数与无理数概念及估算' })
  await weakRow.getByRole('button', { name: '针对练习' }).click()

  // 复测：3 道独立未见题全部答对（选 甲）
  await expect(lobby).toContainText('已锁定知识点定向突破')
  await lobby.getByRole('radio', { name: /阶段诊断/ }).click()
  await lobby.getByRole('button', { name: '3 题' }).click()
  await lobby.getByRole('button', { name: /开始本轮未见题诊断/ }).click()

  for (let round = 1; round <= 3; round++) {
    await answerCurrentCard(page, true)
    await expect(questionCard(page).getByText('符合独立验证条件（首次见题、独立完成），已计入阶段对比。')).toBeVisible()
    if (round < 3) {
      await page.getByRole('button', { name: '进入下一题 →' }).click()
    } else {
      await page.getByRole('button', { name: '结束本轮并查看错题讲解' }).click()
    }
  }
  await expect(page.getByRole('region', { name: '本轮练习结算与错题讲解' })).toContainText('本轮已作答的客观题全部掌握！')

  // 回到「成长状态」查看阶段对比判决：实数与数轴绝对值（math.num.real）基线 0% → 复测 100%
  await navTab(page, /成长状态/).click()
  await page.getByRole('button', { name: '刷新状态' }).click()
  const verdict = page.getByRole('region', { name: '学习目标与阶段验证' }).locator('.validation')
  await expect(verdict).toContainText('可观察对比：基线 → 复测')
  const row = comparisonRow(page, '实数与数轴绝对值', verdict)
  await expect(row).toContainText('复测高于基线')
  await expect(row).toContainText('基线 0%')
  await expect(row).toContainText('复测 100%')
  await expect(row).toContainText('基线 3 题 · 复测 3 题')
  await expect(verdict).toContainText('不是中考分数预测、不等值不同考试、不可比范围不宣称涨分')
  await expect(verdict).toContainText('小样本可观察对比，不是涨分结论')

  await expectHonestLanguage(page)
})

/* ---------- J4 校卷总分 ---------- */

test('J4 校卷总分：气泡说明可开关、三列台账协同建档并明示「总分不产生考点证据」', async ({ page }) => {
  await enterAdminSpace(page)
  await adminNavTab(page, /学校考试/).click()

  const examRegion = page.getByRole('region', { name: '学校考试总分' })

  // 校考录入说明由气泡弹窗承载：总分不产生考点证据，也不折算成知识点表现
  await examRegion.getByRole('button', { name: /校考录入说明/ }).click()
  const helpDialog = page.getByRole('dialog', { name: '校考录入说明' })
  await expect(helpDialog).toBeVisible()
  await expect(helpDialog).toContainText('总分不产生考点证据')
  await expect(helpDialog).toContainText('也不折算成知识点表现')
  await expect(helpDialog).toContainText('不提供公开下载入口')
  await helpDialog.getByRole('button', { name: '关闭说明' }).click()
  await expect(helpDialog).toBeHidden()

  // 默认落在「总分台账与建档」三列矩阵（右侧即新建校考档案），录入后直接左侧选中并在中间栏锁定展示
  await examRegion.getByLabel('考试名称').fill('虚构测试数据：学校月考')
  await examRegion.getByLabel('考试日期').fill('2026-10-20')
  await examRegion.getByLabel('获得分数').fill('85')
  await examRegion.getByLabel('考试满分').fill('100')
  await examRegion.getByRole('button', { name: '记录已核对总分' }).click()

  await expect(page.getByRole('status')).toContainText('学校考试已记录')
  await expect(page.getByRole('status')).toContainText('总分不产生考点证据')

  await expect(examRegion.locator('.exam-list')).toContainText('虚构测试数据：学校月考')
  await expect(examRegion.locator('.exam-list')).toContainText('2026-10-20')
  await expect(examRegion.locator('.exam-list')).toContainText('85 / 100')
  await expect(examRegion.locator('.exam-list')).toContainText('已核对')
  await expect(examRegion.locator('.exam-detail')).toContainText('总分已核对锁定')

  // 无逐题失分明细时，「错误分析与复盘」Tab 如实提示数据不足，并可跳转补录小题
  await examRegion.getByRole('tab', { name: /错误分析与复盘/ }).click()
  const analysisPanel = examRegion.locator('#exam-panel-analysis')
  await expect(analysisPanel).toContainText('当前仅登记了试卷总分，尚无已核对的逐题失分明细')
  await analysisPanel.getByRole('button', { name: '前往补录失分小题' }).click()

  // 在「已核对明细与补录」Tab 录入本场失分小题（带错因分类与复盘备注）
  const itemsPanel = examRegion.locator('#exam-panel-items')
  await itemsPanel.getByLabel('题号（如 第1题）').fill('第5题')
  await itemsPanel.getByLabel('所属知识点').fill('math.arithmetic')
  await itemsPanel.getByLabel('小题得分').fill('2')
  await itemsPanel.getByLabel('小题满分').fill('6')
  await itemsPanel.getByLabel('错因分类（失分题选填）').selectOption('reading')
  await itemsPanel.getByLabel('错题复盘备注').fill('漏看条件 x>0')
  await itemsPanel.getByRole('button', { name: '录入已核对小题' }).click()

  await expect(itemsPanel).toContainText('第5题')
  await expect(itemsPanel).toContainText('漏看条件 x>0')

  // 回「总分台账与建档」补充第二场更早数学月考并同样在 math.arithmetic 失分，验证跨考次顽固失分点对比
  await examRegion.getByRole('tab', { name: /总分台账与建档/ }).click()
  await examRegion.getByLabel('考试名称').fill('虚构测试数据：九月诊断月考')
  await examRegion.getByLabel('考试日期').fill('2026-09-18')
  await examRegion.getByLabel('获得分数').fill('86')
  await examRegion.getByLabel('考试满分').fill('100')
  await examRegion.getByRole('button', { name: '记录已核对总分' }).click()
  await expect(examRegion.locator('.exam-list')).toContainText('虚构测试数据：九月诊断月考')

  await examRegion.getByRole('tab', { name: /已核对明细与补录/ }).click()
  await itemsPanel.getByLabel('题号（如 第1题）').fill('第3题')
  await itemsPanel.getByLabel('所属知识点').fill('math.arithmetic')
  await itemsPanel.getByLabel('小题得分').fill('1')
  await itemsPanel.getByLabel('小题满分').fill('4')
  await itemsPanel.getByLabel('错因分类（失分题选填）').selectOption('calculation')
  await itemsPanel.getByLabel('错题复盘备注').fill('符号算错')
  await itemsPanel.getByRole('button', { name: '录入已核对小题' }).click()
  await expect(itemsPanel).toContainText('第3题')

  // 切回 2026-10-20 场次并打开「错误分析与复盘」Tab 验证三卡联动与诚实用语
  await examRegion.getByRole('button', { name: '2026-10-20 (85/100)' }).click()
  await examRegion.getByRole('tab', { name: /错误分析与复盘/ }).click()
  await expect(analysisPanel).toContainText('本场失分概览与错因分布')
  await expect(analysisPanel).toContainText('本场失分考点排行与交叉诊断')
  await expect(analysisPanel).toContainText('同科历次校考顽固失分点对比')
  await expect(analysisPanel).toContainText('本场再次失分')

  await expectHonestLanguage(page)
})

test('J4b 道法校考归档：暂存待核对、原卷上传与总分补录锁定', async ({ page }) => {
  await enterAdminSpace(page)
  await adminNavTab(page, /学校考试/).click()

  // 切换到道法科目（仅校考档案，不开放核心刷题库）
  await page.getByRole('button', { name: '道法' }).click()

  const examRegion = page.getByRole('region', { name: '学校考试总分' })
  // 在「总分台账与建档」右侧取消勾选“我已人工核对总分”，先以待核对状态归档
  await examRegion.getByLabel(/我已人工核对总分/).uncheck()
  await examRegion.getByLabel('考试名称').fill('虚构测试数据：十月道法统一练习')
  await examRegion.getByLabel('考试日期').fill('2026-10-15')
  await examRegion.getByLabel('考试满分').fill('50')
  await examRegion.getByRole('button', { name: '暂存待核对档案' }).click()

  await expect(page.getByRole('status')).toContainText('待核对学校考试档案已暂存')
  await expect(examRegion.locator('.exam-list')).toContainText('未核对')

  // 切至「原卷与草稿校对」Tab 上传私有原卷 PDF（构造规范单页 PDF，验证私有隔离且无公开下载链接）
  await examRegion.getByRole('tab', { name: /原卷与草稿校对/ }).click()
  const objs = [
    '1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n',
    '2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n',
    '3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>\nendobj\n',
  ]
  const pdfChunks = ['%PDF-1.4\n']
  const offsets: number[] = []
  let bytePos = Buffer.byteLength(pdfChunks[0])
  for (const obj of objs) {
    offsets.push(bytePos)
    pdfChunks.push(obj)
    bytePos += Buffer.byteLength(obj)
  }
  pdfChunks.push(`xref\n0 ${objs.length + 1}\n0000000000 65535 f \n`)
  for (const off of offsets) pdfChunks.push(`${String(off).padStart(10, '0')} 00000 n \n`)
  pdfChunks.push(`trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${bytePos}\n%%EOF\n`)

  await examRegion.getByLabel(/选择试卷或答题卡文件/).setInputFiles({
    name: 'mock-ethics-paper.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from(pdfChunks.join(''), 'ascii'),
  })
  await examRegion.getByRole('button', { name: '上传原卷 / 答题卡' }).click()

  await expect(page.getByRole('status')).toContainText('已加密隔离归档')
  const papersPanel = examRegion.locator('#exam-panel-papers')
  await expect(papersPanel).toContainText('mock-ethics-paper.pdf')
  await expect(papersPanel).toContainText('私有已隔离')
  await expect(papersPanel.locator('a[download]')).toHaveCount(0)

  // 切回「总分台账与建档」Tab 补录并锁定总分
  await examRegion.getByRole('tab', { name: /总分台账与建档/ }).click()
  const detailRegion = examRegion.locator('.exam-detail')
  await detailRegion.getByLabel('补充实得总分').fill('43')
  await detailRegion.getByRole('button', { name: '确认并锁定总分' }).click()

  await expect(page.getByRole('status')).toContainText('校考总分已人工核对并锁定')
  await expect(detailRegion).toContainText('总分已核对锁定')
  await expect(examRegion.locator('.exam-list')).toContainText('43 / 50')

  // 切至「已核对明细与补录」Tab：使用默认主题录入道法失分小题，再行内补充错因分类与复盘备注
  await examRegion.getByRole('tab', { name: /已核对明细与补录/ }).click()
  const ethicsItemsPanel = examRegion.locator('#exam-panel-items')
  await ethicsItemsPanel.getByRole('button', { name: '填入默认主题' }).click()
  await ethicsItemsPanel.getByLabel('题号（如 第1题）').fill('第16题')
  await ethicsItemsPanel.getByLabel('小题得分').fill('4')
  await ethicsItemsPanel.getByLabel('小题满分').fill('8')
  await ethicsItemsPanel.getByRole('button', { name: '录入已核对小题' }).click()
  await expect(ethicsItemsPanel).toContainText('第16题')

  await ethicsItemsPanel.getByRole('button', { name: '标注/修改错因' }).first().click()
  await ethicsItemsPanel.getByLabel('第16题 错因分类').selectOption('norm')
  await ethicsItemsPanel.getByLabel('第16题 错题复盘备注').fill('缺少材料分析')
  await ethicsItemsPanel.getByRole('button', { name: '保存复盘' }).click()
  await expect(ethicsItemsPanel).toContainText('缺少材料分析')

  // 切至「错误分析与复盘」Tab：道法无考点体系时进入档案复盘模式，不虚构日常练习交叉诊断
  await examRegion.getByRole('tab', { name: /错误分析与复盘/ }).click()
  const ethicsAnalysisPanel = examRegion.locator('#exam-panel-analysis')
  await expect(ethicsAnalysisPanel).toContainText('本场失分概览与错因分布')
  await expect(ethicsAnalysisPanel).toContainText('档案复盘')
  await expect(ethicsAnalysisPanel).toContainText('道法综合主题')

  await expectHonestLanguage(page)
})

function buildSyntheticTextPdf(lines: string[]): Buffer {
  const cmds = ['BT', '/F1 14 Tf', '40 740 Td']
  lines.forEach((line, idx) => {
    const escaped = line.replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)')
    if (idx > 0) cmds.push('0 -24 Td')
    cmds.push(`(${escaped}) Tj`)
  })
  cmds.push('ET')
  const stream = Buffer.from(cmds.join('\n'), 'ascii')
  const objs = [
    '1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n',
    '2 0 obj\n<< /Type /Pages /Kids [5 0 R] /Count 1 >>\nendobj\n',
    '3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n',
    `4 0 obj\n<< /Length ${stream.byteLength} >>\nstream\n${stream.toString('ascii')}\nendstream\nendobj\n`,
    '5 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /Font << /F1 3 0 R >> >> /Contents 4 0 R >>\nendobj\n',
  ]
  const chunks = ['%PDF-1.4\n']
  const offsets: number[] = []
  let pos = Buffer.byteLength(chunks[0])
  for (const obj of objs) {
    offsets.push(pos)
    chunks.push(obj)
    pos += Buffer.byteLength(obj)
  }
  chunks.push(`xref\n0 ${objs.length + 1}\n0000000000 65535 f \n`)
  for (const off of offsets) chunks.push(`${String(off).padStart(10, '0')} 00000 n \n`)
  chunks.push(`trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${pos}\n%%EOF\n`)
  return Buffer.from(chunks.join(''), 'ascii')
}

test('J4c 校考自动草稿：纯文字卷提取题号分值骨架、同屏草稿台修订丢弃与逐题确认联动错误分析', async ({ page }) => {
  await enterAdminSpace(page)
  await adminNavTab(page, /学校考试/).click()

  const examRegion = page.getByRole('region', { name: '学校考试总分' })
  await examRegion.getByLabel('考试名称').fill('虚构测试数据：十月数学自动草稿演示')
  await examRegion.getByLabel('考试日期').fill('2026-10-16')
  await examRegion.getByLabel('获得分数').fill('84')
  await examRegion.getByLabel('考试满分').fill('100')
  await examRegion.getByRole('button', { name: '记录已核对总分' }).click()
  await expect(page.getByRole('status')).toContainText('学校考试已记录')

  // 上传带可机读文本层的虚构试卷，并直接在同页右侧草稿台生成与校对草稿
  await examRegion.getByRole('tab', { name: /原卷与草稿校对/ }).click()
  const papersPanel = examRegion.locator('#exam-panel-papers')
  await papersPanel.getByLabel(/选择试卷或答题卡文件/).setInputFiles({
    name: 'mock-math-text-paper.pdf',
    mimeType: 'application/pdf',
    buffer: buildSyntheticTextPdf([
      '1. Compute quadratic equation roots',
      '2. Prove triangle congruence',
    ]),
  })
  await papersPanel.getByRole('button', { name: '上传原卷 / 答题卡' }).click()
  await expect(page.getByRole('status')).toContainText('已加密隔离归档')

  await papersPanel.getByLabel('草稿解析方式').selectOption('skeleton_only')
  await papersPanel.getByRole('button', { name: '生成待核对草稿' }).click()

  const draftDesk = papersPanel.getByRole('region', { name: '草稿校对台' })
  await expect(draftDesk).toBeVisible()
  await expect(draftDesk).toContainText('第1题')
  await expect(draftDesk).toContainText('第2题')
  await expect(draftDesk).toContainText('未确认 · 不进画像')

  // 未人工确认草稿前，「错误分析与复盘」绝不计入正式错误分析
  await examRegion.getByRole('tab', { name: /错误分析与复盘/ }).click()
  const analysisPanel = examRegion.locator('#exam-panel-analysis')
  await expect(analysisPanel).toContainText('待补充逐题失分明细')

  // 回到「原卷与草稿校对」：丢弃第2题草稿，并修改第1题实得分/满分/错因/备注后确认入账
  await examRegion.getByRole('tab', { name: /原卷与草稿校对/ }).click()
  const q2Card = draftDesk.locator('li.draft-card-item', { hasText: '第2题' })
  await q2Card.getByRole('button', { name: '丢弃草稿' }).click()
  await expect(page.getByRole('status')).toContainText('已丢弃「第2题」未确认草稿')

  const q1Card = draftDesk.locator('li.draft-card-item', { hasText: '第1题' })
  await q1Card.getByLabel('第1题 草稿实得分').fill('1.5')
  await q1Card.getByLabel('第1题 草稿满分').fill('3')
  await q1Card.getByLabel('第1题 草稿所属知识点').fill('math.num.real')
  await q1Card.getByLabel('第1题 草稿错因分类').selectOption('calculation')
  await q1Card.getByLabel('第1题 草稿复盘备注').fill('正负号移项遗漏')
  await q1Card.getByRole('button', { name: '确认入账' }).click()

  await expect(page.getByRole('status')).toContainText('已完成人工核对并正式入账')
  await expect(draftDesk.locator('li.draft-card-item')).toHaveCount(0)

  await examRegion.getByRole('tab', { name: /已核对明细与补录/ }).click()
  const itemsPanel = examRegion.locator('#exam-panel-items')
  const confirmedList = itemsPanel.getByRole('region', { name: '逐题得分与考点明细' })
  await expect(confirmedList).toContainText('第1题')
  await expect(confirmedList).toContainText('已确认')
  await expect(confirmedList).toContainText('运算/粗心失误')

  // 「错误分析与复盘」随之上报真实失分错因
  await examRegion.getByRole('tab', { name: /错误分析与复盘/ }).click()
  await expect(analysisPanel).toContainText('本场失分概览与错因分布')
  await expect(analysisPanel).toContainText('运算/粗心失误')
  await expectHonestLanguage(page)
})

/* ---------- J5 审核台：录入真题全闭环 ---------- */

test('J5 审核台：题源登记→来源人工审核→附件解析→确认导入→草稿审核→发布（人工门禁全程如实）', async ({ page }) => {
  await enterAdminSpace(page)
  await adminNavTab(page, /题库与体检/).click()

  const ledger = page.getByRole('region', { name: '题源台账' })
  const review = page.getByRole('region', { name: '来源人工审核' })

  await ledger.getByLabel('题源标题').fill('虚构测试数据：J5 审核台旅程题源')
  await ledger.getByLabel('版权状态').selectOption('personal_use_reviewed')
  await ledger.getByRole('button', { name: '新建题源' }).click()
  await expect(page.getByRole('status')).toContainText('题源已登记')
  const newRow = ledger.locator('li.source-item', { hasText: 'J5 审核台旅程题源' })
  await expect(newRow).toContainText('未审核')
  await expect(review.getByRole('heading', { name: '来源人工审核' })).toBeVisible()

  await review.getByLabel('考试年份（1990–2100）').fill('2026')
  await review.getByLabel('来源链接（必须 https）').fill('https://example.org/synthetic-j5.mp3')
  await review.getByLabel('获取日期').fill('2026-10-26')
  await review.getByLabel('版权状态').selectOption('personal_use_reviewed')
  await review.getByLabel('版权依据（1–2000 字，必填）').fill('虚构测试数据：合成音频，人工确认无版权限制')
  await review.getByLabel('适用性说明（1–2000 字，必填）').fill('虚构测试数据：适用于 J5 审核台旅程验收')
  await expect(review.getByRole('button', { name: '提交人工审核' })).toBeDisabled()
  await review.getByLabel(/我已人工核查来源与版权/).check()
  await review.getByRole('button', { name: '提交人工审核' }).click()
  await expect(page.getByRole('status')).toContainText('题源标记为已审核')
  await expect(newRow.locator('.chip.good')).toContainText('已人工审核')

  // 切入「附件解析与录入」子 Tab 完成附件上传、解析与逐题人工导入
  await page.getByRole('tab', { name: /附件解析与录入/ }).click()
  const attachments = page.getByRole('region', { name: '附件与解析' })
  await expect(attachments).toBeVisible()

  const mp3 = Buffer.alloc(507)
  mp3.set(Buffer.from('ID3'), 0)
  mp3[3] = 0x03
  await attachments.getByLabel(/选择原始附件/).setInputFiles({
    name: '虚构测试数据-j5.mp3',
    mimeType: 'audio/mpeg',
    buffer: mp3,
  })
  await attachments.getByRole('button', { name: '上传附件' }).click()
  await expect(page.getByRole('status')).toContainText('附件已上传')
  await expect(page.getByRole('status')).toContainText('题源回到「未审核」状态')

  await attachments.getByRole('button', { name: '解析' }).click()
  await expect(page.getByRole('status')).toContainText('请逐题人工录入')
  await attachments.getByRole('button', { name: '逐题录入并确认导入' }).click()
  const entryForm = attachments.locator('.confirm-import')
  await entryForm.getByLabel('题干').fill('虚构测试数据：J5 审核台听力题——听录音选出提到的词。')
  await entryForm.getByLabel('选项 A 内容').fill('甲')
  await entryForm.getByLabel('选项 B 内容').fill('乙')
  await entryForm.getByLabel('正确选项').selectOption({ label: 'A · 甲' })
  await entryForm.getByLabel('所属知识点（至少 1 个，可直接输入名称或逗号分隔）').fill('math.listen')
  await entryForm.getByRole('button', { name: '加入待导入列表' }).click()
  await expect(entryForm.getByText('已录入 1 题')).toBeVisible()
  await expect(entryForm.getByRole('button', { name: '确认导入 1 题' })).toBeDisabled()
  await entryForm.getByLabel(/我已逐题人工核对/).check()
  await entryForm.getByRole('button', { name: '确认导入 1 题' }).click()
  await expect(page.getByRole('status')).toContainText('已确认导入 1 题，草稿待人工审核')
  await expect(attachments.getByText('已导入 1 题，等待逐题人工审核。')).toBeVisible()

  // 切入「题目审核与发布」子 Tab 完成人工审核；题源未重审时发布应受门禁阻断
  await page.getByRole('tab', { name: /题目审核与发布/ }).click()
  const versions = page.getByRole('region', { name: '题目草稿与发布' })
  const draftRow = versions.locator('li.version-row', { hasText: 'J5 审核台听力题' })
  await expect(draftRow.locator('.badge.qstatus-draft')).toBeVisible()
  await expect(draftRow).toContainText('含媒体附件')
  await draftRow.getByRole('button', { name: '人工审核通过' }).click()
  await expect(page.getByRole('status')).toContainText('已标记为人工审核')
  await expect(draftRow.locator('.badge.qstatus-reviewed')).toBeVisible()
  await expect(draftRow.getByRole('button', { name: '发布' })).toBeDisabled()
  await expect(draftRow).toContainText('题源未通过人工审核（或版权未核实），发布暂不可用')

  // 回到「题源与来源审核」确认题源回到待审核并重新核验提交，再切回「题目审核与发布」执行正式发布
  await page.getByRole('tab', { name: /题源与来源审核/ }).click()
  await expect(newRow.locator('.chip.wait')).toContainText('未审核')
  await expect(page.locator('#ledger-panel-sources')).not.toContainText('owner')
  await expect(page.locator('#ledger-panel-sources')).not.toContainText('SHA256')
  await review.getByLabel(/我已人工核查来源与版权/).check()
  await review.getByRole('button', { name: '提交人工审核' }).click()
  await expect(page.getByRole('status')).toContainText('题源标记为已审核')

  await page.getByRole('tab', { name: /题目审核与发布/ }).click()
  await draftRow.getByRole('button', { name: '发布' }).click()
  await expect(page.getByRole('status')).toContainText('题目已发布，现在会进入练习与诊断的取题池。')
  await expect(draftRow.locator('.badge.qstatus-published')).toBeVisible()

  await expectHonestLanguage(page)
})

/* ---------- J6 / J6b 双令牌隔离与本机记住令牌 ---------- */

test('J6 本机记住令牌：冷启动免输入、退出即清除、失效令牌如实拦截', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByLabel(/在本机记住令牌/)).not.toBeChecked()

  await page.getByLabel('访问令牌').fill(STUDENT_TOKEN)
  await page.getByLabel(/在本机记住令牌/).check()
  await page.getByRole('button', { name: '进入' }).click()
  await expect(page.getByRole('navigation', { name: '主要视图' })).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('shutong.student_token'))).toBe(STUDENT_TOKEN)

  await page.reload()
  await expect(page.getByRole('navigation', { name: '主要视图' })).toBeVisible()
  await expect(page.getByLabel('访问令牌')).toHaveCount(0)
  await expect(page.getByRole('status')).toContainText('已用本机记住的令牌自动进入')
  await expect(page.getByRole('region', { name: '智能综合练习编排' })).toBeVisible()

  await page.getByRole('button', { name: '退出' }).click()
  await expect(page.getByLabel('访问令牌')).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('shutong.student_token'))).toBeNull()
  await expect(page.getByLabel(/在本机记住令牌/)).not.toBeChecked()

  await page.evaluate(t => localStorage.setItem('shutong.student_token', t), 'stale-token')
  await page.reload()
  await expect(page.getByLabel('访问令牌')).toBeVisible()
  await expect.poll(() => page.evaluate(() => localStorage.getItem('shutong.student_token'))).toBeNull()

  await page.getByLabel('访问令牌').fill(STUDENT_TOKEN)
  await page.getByRole('button', { name: '进入' }).click()
  await expect(page.getByRole('navigation', { name: '主要视图' })).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('shutong.student_token'))).toBeNull()
})

test('J6b 凭据门禁安全整改：废弃旧键清理、未主动勾选不持久化、管理端隐藏记住选项', async ({ page }) => {
  await page.goto('/')
  await page.evaluate(() => localStorage.setItem('shutong.token', 'legacy-admin-token'))
  await page.reload()
  await expect(page.getByLabel('访问令牌')).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('shutong.token'))).toBeNull()

  await expect(page.getByLabel(/在本机记住令牌/)).not.toBeChecked()
  await page.getByLabel('访问令牌').fill(STUDENT_TOKEN)
  await page.getByRole('button', { name: '进入' }).click()
  await expect(page.getByRole('navigation', { name: '主要视图' })).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('shutong.student_token'))).toBeNull()
  await page.getByRole('button', { name: '退出' }).click()
  await expect(page.getByLabel('访问令牌')).toBeVisible()

  await page.goto('/admin.html')
  await page.evaluate(() => localStorage.setItem('shutong.token', 'legacy-admin-token'))
  await page.reload()
  expect(await page.evaluate(() => localStorage.getItem('shutong.token'))).toBeNull()
  await expect(page.getByLabel(/在本机记住令牌/)).toHaveCount(0)
  await expect(page.getByText('管理凭据安全策略：仅在当前页面内存持有，不支持本机持久化记住。')).toBeVisible()

  await page.getByLabel('访问令牌').fill(ADMIN_TOKEN)
  await page.getByRole('button', { name: '进入' }).click()
  await expect(page.getByRole('navigation', { name: '管理视图' })).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('shutong.admin_token'))).toBeNull()
  expect(await page.evaluate(() => localStorage.getItem('shutong.token'))).toBeNull()

  await page.getByRole('button', { name: '退出' }).click()
  await expect(page.getByLabel('访问令牌')).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('shutong.admin_token'))).toBeNull()
})

/* ---------- J7 知识图谱交互展示与选学过滤 ---------- */

test('J7 知识图谱交互展示：SVG 关系图谱、领域筛选、选学排除与未掌握高亮', async ({ page }) => {
  await enterSpace(page)
  await navTab(page, /知识点展示/).click()

  const section = page.getByRole('region', { name: '知识点关系图谱展示' })
  await expect(section).toBeVisible()
  const svg = page.getByRole('group', { name: '知识点层级与前置关联图谱' })
  await expect(svg).toBeVisible()

  // 不含选学（*）节点（三元一次方程组解法、切线长定理均标记 is_elective=true）
  const allText = await section.innerText()
  expect(allText).toContain('已自动排除选学*内容')
  expect(allText).not.toContain('三元一次方程组')
  // 方案三跨章桥梁矩阵与图谱展示全面中文化：不得泄露内部领域英文编码
  for (const rawDomain of ['num_alg', 'geom', 'stat_prob', 'comp_prac']) {
    expect(allText).not.toContain(rawDomain)
  }

  // 领域过滤、仅高亮未掌握切换及图谱节点点选
  await section.locator('.domain-filter-strip').getByRole('button', { name: '数与代数', exact: true }).click()
  await section.getByRole('button', { name: '仅高亮未掌握' }).click()
  await section.getByRole('button', { name: '仅高亮未掌握' }).click()
  await section.getByRole('button', { name: /全部领域/ }).click()

  await svg.getByRole('button', { name: /有理数及其运算/ }).click()
  const detail = page.getByRole('complementary', { name: '选中知识点详情' })
  await expect(detail).toContainText('有理数及其运算')
  await expect(detail).toContainText('有效独立样本')

  await expectHonestLanguage(page)
})

/* ---------- J8 管理端知识点审核：同步→课标草稿→批量审核→发布 ---------- */

test('J8 管理端知识点审核：同步候选→按课标生成审核依据草稿→批量审核→发布版本快照', async ({ page }) => {
  await enterAdminSpace(page)
  await adminNavTab(page, /知识点审核/).click()

  await expect(page.getByText('数学权威知识点库审核工作台')).toBeVisible()
  // 默认隐藏英文技术编码与 MOE 标准代码
  await expect(page.locator('.knowledge-workbench')).not.toContainText('MOE-2022-')

  await page.getByRole('button', { name: '同步候选入库 (待审)' }).click()
  await expect(page.locator('.status-banner')).toContainText('待审核: 48')

  await page.getByLabel('审核人实名标识 (必填):').fill('owner_e2e_reviewer')
  await page.getByRole('button', { name: '按课标生成审核依据草稿' }).click()
  await expect(page.getByLabel('审核依据与意见 (必填):')).not.toHaveValue('')

  await page.getByRole('button', { name: /按课标批量审核待审 \(48\)/ }).click()
  await expect(page.locator('.status-banner')).toContainText('待审核: 0', { timeout: 15_000 })
  await expect(page.locator('.status-banner')).toContainText('已通过: 48', { timeout: 15_000 })

  await page.getByRole('tab', { name: /版本发布与快照/ }).click()
  await page.getByRole('button', { name: '发布正式版本快照' }).click()
  const releasesList = page.locator('.releases-list')
  await expect(releasesList).toContainText('数学 2022 课标正式版')
  // 默认不显示原始英文版本号，开启「显示技术编码」后方可展示
  await expect(releasesList).not.toContainText('math-v2022.1.0')
  await page.getByRole('button', { name: '显示技术编码' }).click()
  await expect(releasesList).toContainText('math-v2022.1.0')
})

/* ---------- J9 会话续答（刷新不空烧未见题） ---------- */

test('J9 会话续答：未完成练习刷新后自动恢复同一会话与题干，交卷后无残留', async ({ page }) => {
  await enterSpace(page)

  const lobby = page.getByRole('region', { name: '智能综合练习编排' })
  await lobby.getByRole('radio', { name: /阶段诊断/ }).click()
  await lobby.getByRole('button', { name: '3 题' }).click()
  await lobby.getByRole('button', { name: /开始本轮未见题诊断/ }).click()

  const card = questionCard(page)
  await expect(card).toBeVisible()
  const firstStem = await card.locator('p.stem').innerText()

  // 刷新页面并重新登录后，自动恢复到同一场未完成会话与同一第 1 题题干
  await page.reload()
  await page.getByLabel('访问令牌').fill(STUDENT_TOKEN)
  await page.getByRole('button', { name: '进入' }).click()

  await expect(page.getByRole('status')).toContainText('已恢复上次未完成的练习会话')
  await expect(page.getByRole('region', { name: '本轮练习进度' })).toContainText('已完成 0 / 3 题')
  await expect(questionCard(page).locator('p.stem')).toHaveText(firstStem)

  // 作答并提前交卷
  await answerCurrentCard(page, true)
  await page.getByRole('button', { name: '提前交卷看错题' }).click()
  await expect(page.getByRole('region', { name: '本轮练习结算与错题讲解' })).toBeVisible()

  // 交卷后再次刷新，不残留待续会话，干净回到练习大厅
  await page.reload()
  await page.getByLabel('访问令牌').fill(STUDENT_TOKEN)
  await page.getByRole('button', { name: '进入' }).click()
  await expect(page.getByRole('status')).not.toContainText('已恢复上次未完成的练习会话')
  await expect(page.getByRole('region', { name: '智能综合练习编排' })).toBeVisible()

  await expectHonestLanguage(page)
})

test('J10 全科校考同步：脱敏采集包导入、跨科草稿跳转校对、全中文化态与宿主后台任务轮询', async ({ page }) => {
  const consoleErrors: string[] = []
  const pageErrors: string[] = []
  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text())
  })
  page.on('pageerror', err => pageErrors.push(String(err)))

  await enterAdminSpace(page)
  await adminNavTab(page, /学校考试/).click()
  await expect(page.getByRole('region', { name: '学校考试总分' })).toBeVisible()

  // 切至「全科校考同步」子 Tab：应加载运行态、展示复制命令参考并通过 WCAG AA 无障碍抽检
  await page.getByRole('tab', { name: /全科校考同步/ }).click()
  const drawer = page.getByRole('region', { name: '从全科校考平台补全各科校考信息' })
  await expect(drawer).toBeVisible()
  await expect(drawer).toContainText('k12100_sync.py collect')
  // 等 .card 入场渐入动画完成后再测量静态 WCAG 对比度
  await page.evaluate(() => Promise.allSettled(Array.from(document.getAnimations()).map(a => a.finished)))
  const axeDrawer = await new AxeBuilder({ page })
    .include('#k12100-backfill-drawer')
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze()
  expect(axeDrawer.violations.filter(v => v.impact === 'critical' || v.impact === 'serious')).toEqual([])

  // 真实全栈端到端：上传含 2 科（数学 + 英语含真实合法 JPEG 答题卡与个人信息诱饵字段）的脱敏采集包
  const tinyJpegBase64 =
    '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAAQABADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD3SiiirIP/2Q=='
  const bundlePayload = {
    examName: '虚构测试数据 · 全科自动补全',
    examDate: '2026-10-18',
    studName: '王五',
    schoolRank: 1,
    exams: [
      {
        examName: '虚构测试数据 · 全科自动补全',
        examDate: '2026-10-18',
        studName: '王五',
        subjects: [
          {
            subjectName: '数学',
            score: 91,
            fullScore: 100,
            smallQuestions: [
              { questionName: '1', score: 2, fullScore: 2 },
              { questionName: '2', score: 0, fullScore: 2 },
            ],
            card_images: [],
          },
          {
            subjectName: '英语',
            score: 88,
            fullScore: 100,
            smallQuestions: [
              { questionName: '1', score: 2, fullScore: 2 },
              { questionName: '21', score: 1, fullScore: 2 },
            ],
            card_images: [{ filename: 'english_card_1.jpg', data_base64: tinyJpegBase64 }],
          },
        ],
      },
    ],
  }
  await drawer.locator('input[type="file"]').setInputFiles({
    name: 'mock_k12100_bundle.json',
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(bundlePayload), 'utf-8'),
  })

  await expect(drawer).toContainText('最近同步结果：虚构测试数据 · 全科自动补全')
  await expect(drawer).toContainText('处理 2 科')
  await expect(drawer).toContainText('新上传 1 份')
  await expect(drawer).toContainText('待核对草稿 4 题')
  await expect(drawer).toContainText('数学')
  await expect(drawer).toContainText('英语')
  await expect(drawer).not.toContainText('王五')
  await expect(drawer).not.toContainText('external_local_rules')
  await expect(drawer).not.toContainText('created_and_confirmed')

  // 点击英语行的「去校对草稿」→ 自动切换管理端当前科目为英语并定位到「原卷与草稿校对」草稿校对台
  const englishRow = drawer.locator('tbody tr', { hasText: '英语' })
  await englishRow.getByRole('button', { name: '去校对草稿' }).click()

  const draftBench = page.getByRole('region', { name: '草稿校对台' })
  await expect(draftBench).toBeVisible()
  await expect(draftBench).toContainText('待核对 2 题')
  await expect(draftBench).toContainText('未确认 · 不进画像')
  await expect(page.getByRole('group', { name: '科目' }).getByRole('button', { name: '英语' })).toHaveClass(
    /\bselected\b/,
  )

  // 验证宿主机直连模式（Mock /status + /jobs + /jobs/:id）启动与进度轮询完成态及全中文化展示
  await page.route('**/api/school-exams/k12100-sync/status', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        can_run_local: true,
        is_isolated_runtime: false,
        unavailable_reason: null,
        credentials: { env_exists: true, env_mode_ok: true, username_masked: '139****1111', configured: true },
        deepseek_configured: true,
        has_browser_state: true,
        recommended_cli_command: 'uv run python scripts/k12100_sync.py collect --config-dir ~/.config/shutong',
        latest_job: null,
      }),
    }),
  )
  await page.route('**/api/school-exams/k12100-sync/jobs', async route => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({
          job_id: 'job-e2e-mock-1',
          state: 'queued',
          stage: 'queued',
          stage_message: '任务已入队，准备启动宿主机安全同步。',
          created_at: '2026-11-15T00:00:00Z',
          updated_at: '2026-11-15T00:00:00Z',
          error_code: null,
          error_message: null,
          result: null,
        }),
      })
      return
    }
    await route.continue()
  })
  await page.route('**/api/school-exams/k12100-sync/jobs/job-e2e-mock-1', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        job_id: 'job-e2e-mock-1',
        state: 'completed',
        stage: 'completed',
        stage_message: '已完成全科采集与入库。',
        created_at: '2026-11-15T00:00:00Z',
        updated_at: '2026-11-15T00:00:02Z',
        error_code: null,
        error_message: null,
        result: {
          source_exam_title: '虚构测试数据 · 宿主机异步采集',
          source_exam_date: '2026-10-19',
          subjects: [
            {
              subject: 'physics',
              subject_label: '物理',
              exam_id: 'exam-e2e-phy-1',
              exam_title: '虚构测试数据 · 物理',
              exam_date: '2026-10-19',
              earned_points: 65,
              max_points: 70,
              confirmed_by_user: true,
              score_status: 'created_and_confirmed',
              stem_mode: 'pdf_local_regex',
              parser_mode_used: 'external_local_rules',
              attachments_uploaded: 1,
              drafts_created: 3,
              skipped_labels: [],
              warning: null,
            },
          ],
          totals: {
            subjects_processed: 1,
            created_exams: 1,
            confirmed_now: 1,
            locked_conflicts: 0,
            attachments_uploaded: 1,
            drafts_created: 3,
          },
          knowledge_evidence_created: 0,
        },
      }),
    }),
  )

  await page.getByRole('tab', { name: /全科校考同步/ }).click()
  const hostDrawer = page.getByRole('region', { name: '从全科校考平台补全各科校考信息' })
  await hostDrawer.getByRole('button', { name: '刷新状态' }).click()
  await expect(hostDrawer).toContainText('本机环境已就绪')
  await expect(hostDrawer).toContainText('139****1111')
  await hostDrawer.getByRole('button', { name: '手动启动全科校考同步' }).click()
  await expect(hostDrawer).toContainText('任务进度 · 已完成')
  await expect(hostDrawer).toContainText('最近同步结果：虚构测试数据 · 宿主机异步采集')
  await expect(hostDrawer).toContainText('物理')
  await expect(hostDrawer).toContainText('本地规则匹配')
  await expect(hostDrawer).not.toContainText('queued')
  await expect(hostDrawer).not.toContainText('completed')
  await expect(hostDrawer).not.toContainText('external_local_rules')
  await expect(hostDrawer).not.toContainText('pdf_local_regex')

  await page.unrouteAll({ behavior: 'ignoreErrors' })
  await expectHonestLanguage(page)
  expect(pageErrors).toEqual([])
  expect(consoleErrors).toEqual([])
})
