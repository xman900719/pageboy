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
  await expect(tutor).toContainText('我的书童')
  const turns = tutor.locator('.tutor-turns')
  await expect(turns).toContainText('我们先不急着下结论')
  expect(await turns.innerText()).not.toContain('正确答案是 A')

  // 学生输入思考内容，触发 AI 多轮启发式回应
  await tutor.locator('#tutor-reply-input').fill('我先看清题干里的实数条件')
  await tutor.getByRole('button', { name: '发送' }).click()
  await expect(turns).toContainText('我先看清题干里的实数条件')
  await expect(turns).toContainText('思路很对')

  await tutor.getByRole('button', { name: '收起' }).click()
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

  // 默认落在第一阶段第 1 步（无校考时自动进入建档模式，且第 2 步「上传原卷」严防跳步锁定；获得分数默认等于考试满分）
  await expect(examRegion.getByLabel('考试名称')).toBeVisible()
  await expect(examRegion.locator('#exam-panel-scores .step-stage-body section.card')).toHaveCount(1)
  const uploadPill = examRegion.getByRole('button', { name: /2\. 上传原卷/ })
  await expect(uploadPill).toHaveAttribute('aria-disabled', 'true')
  await uploadPill.click({ force: true })
  await expect(examRegion.locator('.gate-alert-banner')).toContainText('不可跳步至')

  await examRegion.getByLabel('考试名称').fill('虚构测试数据：学校月考')
  await examRegion.getByLabel('考试日期').fill('2026-10')
  await examRegion.getByRole('button', { name: '提交考试信息并建档' }).click()

  await expect(page.getByRole('status')).toContainText('全科校考档案已创建')
  await expect(page.getByRole('status')).toContainText('总分不产生考点证据')

  // 录入后自动推进到第 2 步「上传原卷」，此时仅展示单卡，回第 1 步可见台账列表与「提交考试信息」按钮
  await expect(examRegion.getByRole('heading', { name: '上传原卷' })).toBeVisible()
  await expect(examRegion.locator('.exam-list')).toHaveCount(0)
  await examRegion.locator('ol.step-pill-bar').getByRole('button', { name: /选定或新建校考档案/ }).click()
  await expect(examRegion.locator('.exam-list')).toContainText('虚构测试数据：学校月考')
  await expect(examRegion.locator('.exam-list')).toContainText('2026-10')
  await expect(examRegion.locator('.exam-list')).toContainText('100 / 100')
  await expect(examRegion.locator('.exam-list')).toContainText('未核对')
  await expect(examRegion.locator('.exam-list')).toContainText('提交考试信息')

  // 无逐题失分明细时，「错误分析与复盘」Tab 如实提示数据不足，并可跳转补录小题
  await examRegion.getByRole('tab', { name: /错误分析与复盘/ }).click()
  const analysisPanel = examRegion.locator('#exam-panel-analysis')
  await expect(analysisPanel).toContainText('当前档案尚无已核对总分与逐题明细，暂不足以生成错误分析')
  await analysisPanel.getByRole('button', { name: '前往补录失分小题' }).click()

  // 在「已核对明细与补录」第 2 步录入本场失分小题（错因与复盘由学生端完成）
  const itemsPanel = examRegion.locator('#exam-panel-items')
  await itemsPanel.getByLabel('题号（如 第1题）').fill('第5题')
  await itemsPanel.getByLabel('所属知识点').fill('math.arithmetic')
  await itemsPanel.getByLabel('小题得分').fill('2')
  await itemsPanel.getByLabel('小题满分').fill('6')
  await itemsPanel.getByRole('button', { name: '录入已核对小题' }).click()

  await expect(itemsPanel).toContainText('第5题')
  await expect(itemsPanel).toContainText('待学生复盘')

  // 回「总分台账与建档」第 1 步切换建档模式，补充第二场更早数学月考，验证跨考次顽固失分点对比
  await examRegion.getByRole('tab', { name: /总分台账与建档/ }).click()
  await examRegion.getByRole('button', { name: '＋ 新建 / 暂存档案' }).click()
  await examRegion.getByLabel('考试名称').fill('虚构测试数据：九月诊断月考')
  await examRegion.getByLabel('考试日期').fill('2026-09')
  await examRegion.getByRole('button', { name: '提交考试信息并建档' }).click()
  await expect(examRegion.getByRole('heading', { name: '上传原卷' })).toBeVisible()
  await examRegion.locator('ol.step-pill-bar').getByRole('button', { name: /选定或新建校考档案/ }).click()
  await expect(examRegion.locator('.exam-list')).toContainText('虚构测试数据：九月诊断月考')

  await examRegion.getByRole('tab', { name: /已核对明细与补录/ }).click()
  await itemsPanel.locator('ol.step-pill-bar').getByRole('button', { name: /人工补录已核对小题/ }).click()
  await itemsPanel.getByLabel('题号（如 第1题）').fill('第3题')
  await itemsPanel.getByLabel('所属知识点').fill('math.arithmetic')
  await itemsPanel.getByLabel('小题得分').fill('1')
  await itemsPanel.getByLabel('小题满分').fill('4')
  await itemsPanel.getByRole('button', { name: '录入已核对小题' }).click()
  await expect(itemsPanel).toContainText('第3题')

  // 切回 2026-10 场次并打开「错误分析与复盘」Tab，按 1→2→3 单卡步骤验证三段分析与诚实用语
  await examRegion.getByRole('button', { name: '2026-10 (100/100)' }).click()
  await examRegion.getByRole('tab', { name: /错误分析与复盘/ }).click()
  await expect(analysisPanel).toContainText('本场失分概览与错因分布')
  await expect(analysisPanel.locator('.step-stage-body section.card')).toHaveCount(1)
  await analysisPanel.locator('ol.step-pill-bar').getByRole('button', { name: /失分考点排行与交叉诊断/ }).click()
  await expect(analysisPanel).toContainText('本场失分考点排行与交叉诊断')
  await analysisPanel.locator('ol.step-pill-bar').getByRole('button', { name: /同科历次顽固失分点对比/ }).click()
  await expect(analysisPanel).toContainText('同科历次校考顽固失分点对比')
  await expect(analysisPanel).toContainText('本场再次失分')

  await expectHonestLanguage(page)
})

test('J4d 已录校考台账：单项删除需二次确认，仅删除当前场次', async ({ page }) => {
  await enterAdminSpace(page)
  await adminNavTab(page, /学校考试/).click()
  const examRegion = page.getByRole('region', { name: '学校考试总分' })
  const title = '虚构测试数据：待删除月考'
  const keepTitle = '虚构测试数据：保留对照月考'

  await examRegion.getByRole('button', { name: '＋ 新建 / 暂存档案' }).click()
  await examRegion.getByLabel('考试名称').fill(title)
  await examRegion.getByLabel('考试日期').fill('2026-08')
  await examRegion.getByRole('button', { name: '提交考试信息并建档' }).click()
  await expect(examRegion.getByRole('heading', { name: '上传原卷' })).toBeVisible()

  await examRegion.locator('ol.step-pill-bar').getByRole('button', { name: /选定或新建校考档案/ }).click()
  await examRegion.getByRole('button', { name: '＋ 新建 / 暂存档案' }).click()
  await examRegion.getByLabel('考试名称').fill(keepTitle)
  await examRegion.getByLabel('考试日期').fill('2026-07')
  await examRegion.getByRole('button', { name: '提交考试信息并建档' }).click()
  await expect(examRegion.getByRole('heading', { name: '上传原卷' })).toBeVisible()
  await examRegion.locator('ol.step-pill-bar').getByRole('button', { name: /选定或新建校考档案/ }).click()
  await expect(examRegion.locator('.exam-item', { hasText: title })).toHaveCount(1)
  await expect(examRegion.locator('.exam-item', { hasText: keepTitle })).toHaveCount(1)

  await examRegion.getByRole('button', { name: `删除 ${title}` }).click()
  await expect(examRegion.locator('.exam-list')).toContainText('删除本场？')
  await examRegion.getByRole('button', { name: `确认删除 ${title}` }).click()

  await expect(page.getByRole('status')).toContainText('已删除该场校考')
  await expect(examRegion.locator('.exam-item', { hasText: title })).toHaveCount(0)
  await expect(examRegion.locator('.exam-item', { hasText: keepTitle })).toHaveCount(1)
  await expectHonestLanguage(page)
})

test('J4b 道法校考归档：暂存待核对、原卷上传与总分补录锁定', async ({ page }) => {
  await enterAdminSpace(page)
  await adminNavTab(page, /学校考试/).click()

  // 切换到道法科目（仅校考档案，不开放核心刷题库）
  await page.getByRole('button', { name: '道法' }).click()

  const examRegion = page.getByRole('region', { name: '学校考试总分' })
  // 新建档案不分科目、面向全科；若已有全科档案，点击「＋ 新建 / 暂存档案」进入建档表单，总分待后续核对
  const createModeBtn = examRegion.getByRole('button', { name: '＋ 新建 / 暂存档案' })
  if (await createModeBtn.isVisible()) {
    await createModeBtn.click()
  }
  await expect(examRegion.getByLabel('考试名称')).toBeVisible()
  await examRegion.getByLabel('考试名称').fill('虚构测试数据：十月道法统一练习')
  await examRegion.getByLabel('考试日期').fill('2026-10')
  await examRegion.getByRole('button', { name: '提交考试信息并建档' }).click()

  await expect(page.getByRole('status')).toContainText('全科校考档案已创建')
  await examRegion.locator('ol.step-pill-bar').getByRole('button', { name: /选定或新建校考档案/ }).click()
  const ethicsRow = examRegion.locator('.exam-item', { hasText: '虚构测试数据：十月道法统一练习' })
  await expect(ethicsRow).toHaveCount(1)
  await expect(ethicsRow).toContainText('全科')
  await expect(ethicsRow).toContainText('未核对')

  // 切至第二阶段「原卷提取与明细核对」Tab：未上传原卷且无待核对明细时，第 2 步「逐题明细核对台」应呈锁定拦截态
  await examRegion.getByRole('tab', { name: /原卷提取与明细核对/ }).click()
  const draftStepPill = examRegion.getByRole('button', { name: /逐题明细核对台/ })
  await expect(draftStepPill).toHaveAttribute('aria-disabled', 'true')
  await draftStepPill.click({ force: true })
  await expect(examRegion.locator('.gate-alert-banner')).toContainText('不可跳步至')

  // 回到第一阶段第 2 步「上传原卷」完成隔离上传（存放于 exam-paper 目录）
  await examRegion.getByRole('tab', { name: /总分台账与建档/ }).click()
  await examRegion.locator('ol.step-pill-bar').getByRole('button', { name: /2\. 上传原卷/ }).click()

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

  const scoresPanel = examRegion.locator('#exam-panel-scores')
  await scoresPanel.getByLabel(/选择原卷文件/).setInputFiles({
    name: 'mock-ethics-paper.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from(pdfChunks.join(''), 'ascii'),
  })
  await scoresPanel.getByRole('button', { name: '上传原卷', exact: true }).click()

  await expect(page.getByRole('status')).toContainText('已存入档案 exam-paper 目录')
  await expect(scoresPanel).toContainText('mock-ethics-paper.pdf')
  await expect(scoresPanel).toContainText('exam-paper')
  await expect(scoresPanel.locator('a[download]')).toHaveCount(0)

  // 推进至第 3 步「全科校考同步」，确认可见同步中心后回第 1 步确认台账
  await scoresPanel.getByRole('button', { name: /下一步：3\. 全科校考同步/ }).click()
  await expect(scoresPanel.getByRole('region', { name: '全科校考同步中心' })).toBeVisible()
  await examRegion.locator('ol.step-pill-bar').getByRole('button', { name: /选定或新建校考档案/ }).click()
  await expect(ethicsRow).toContainText('100 / 100')
  await expect(ethicsRow).toContainText('未核对')

  // 切至「已核对明细与补录」第 2 步录入道法失分小题（确认后进入学生端待复盘）
  await examRegion.getByRole('tab', { name: /已核对明细与补录/ }).click()
  const ethicsItemsPanel = examRegion.locator('#exam-panel-items')
  await ethicsItemsPanel.locator('ol.step-pill-bar').getByRole('button', { name: /人工补录已核对小题/ }).click()
  await ethicsItemsPanel.getByRole('button', { name: '填入默认主题' }).click()
  await ethicsItemsPanel.getByLabel('题号（如 第1题）').fill('第16题')
  await ethicsItemsPanel.getByLabel('小题得分').fill('4')
  await ethicsItemsPanel.getByLabel('小题满分').fill('8')
  await ethicsItemsPanel.getByRole('button', { name: '录入已核对小题' }).click()
  await expect(ethicsItemsPanel).toContainText('第16题')
  await expect(ethicsItemsPanel).toContainText('待学生复盘')

  // 切至「错误分析与复盘」Tab：第 1 步看概览，第 2 步看道法档案复盘模式
  await examRegion.getByRole('tab', { name: /错误分析与复盘/ }).click()
  const ethicsAnalysisPanel = examRegion.locator('#exam-panel-analysis')
  await expect(ethicsAnalysisPanel).toContainText('本场失分概览与错因分布')
  await ethicsAnalysisPanel.locator('ol.step-pill-bar').getByRole('button', { name: /失分考点排行与交叉诊断/ }).click()
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

test('J4c 校考待核对明细：纯文字卷提取、题号自然排序、分数只读、满分隐藏错因与分段批量确认', async ({ page }) => {
  await enterAdminSpace(page)
  await adminNavTab(page, /学校考试/).click()

  const examRegion = page.getByRole('region', { name: '学校考试总分' })
  await examRegion.getByRole('button', { name: '＋ 新建 / 暂存档案' }).click()
  await examRegion.getByLabel('考试名称').fill('虚构测试数据：十月数学待核明细演示')
  await examRegion.getByLabel('考试日期').fill('2026-10')
  await examRegion.getByRole('button', { name: '提交考试信息并建档' }).click()
  await expect(page.getByRole('status')).toContainText('全科校考档案已创建')

  // 第一阶段第 2 步上传原卷，再推进至第 3 步并进入第二阶段提取与核对
  const scoresPanel = examRegion.locator('#exam-panel-scores')
  await expect(scoresPanel.getByRole('button', { name: '查看错误分析' })).toHaveCount(0)
  await scoresPanel.getByLabel(/选择原卷文件/).setInputFiles({
    name: 'mock-math-text-paper.pdf',
    mimeType: 'application/pdf',
    buffer: buildSyntheticTextPdf([
      '1. Compute quadratic equation roots',
      '2. Prove triangle congruence',
    ]),
  })
  await scoresPanel.getByRole('button', { name: '上传原卷', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('已存入档案 exam-paper 目录')

  await scoresPanel.getByRole('button', { name: /下一步：3\. 全科校考同步/ }).click()
  await scoresPanel.getByRole('button', { name: /^核对入档/ }).click()
  await scoresPanel.getByRole('button', { name: /下一步：进入第二阶段 · 明细提取与核对/ }).click()
  const papersPanel = examRegion.locator('#exam-panel-papers')
  await papersPanel.getByLabel('待核对明细提取方式').selectOption('skeleton_only')
  await papersPanel.getByRole('button', { name: '生成待核对明细' }).click()

  const draftDesk = papersPanel.getByRole('region', { name: '逐题明细核对台' })
  await expect(draftDesk).toBeVisible()
  await expect(draftDesk).toContainText('第1题')
  await expect(draftDesk).toContainText('第2题')
  await expect(draftDesk).toContainText('未确认 · 不进画像')

  // 未人工确认待核对明细前，「错误分析与复盘」绝不计入正式错误分析
  await examRegion.getByRole('tab', { name: /错误分析与复盘/ }).click()
  const analysisPanel = examRegion.locator('#exam-panel-analysis')
  await expect(analysisPanel).toContainText('待补充逐题失分明细')

  // 回到「原卷提取与明细核对」（仍停留在核对台）：移除第2题，第1题分数只读不可编辑，填写考点后确认入账
  await examRegion.getByRole('tab', { name: /原卷提取与明细核对/ }).click()
  const q2Card = draftDesk.locator('li.draft-card-item', { hasText: '第2题' })
  await q2Card.getByRole('button', { name: '移除待核项' }).click()
  await expect(page.getByRole('status')).toContainText('已移除「第2题」待核对明细')

  const q1Card = draftDesk.locator('li.draft-card-item', { hasText: '第1题' })
  await expect(q1Card.locator('input[type="number"]')).toHaveCount(0)
  await expect(q1Card).toContainText('实得 0 / 满分 2 分')
  await expect(q1Card.locator('.draft-basis-tag').first()).toBeVisible()
  await expect(q1Card.locator('.candidate-chip-btn')).toHaveCount(3)
  const q1Input = q1Card.getByLabel('第1题 所属知识点')
  await expect(q1Input).not.toHaveValue('')
  await expect(q1Input).not.toHaveValue('unmapped')
  await expect(q1Input).toHaveClass(/input-auto-linked/)
  const firstVal = await q1Input.inputValue()
  await q1Card.locator('.candidate-chip-btn').nth(1).click()
  await expect(q1Card.locator('.candidate-chip-btn').nth(1)).toHaveClass(/active/)
  const secondVal = await q1Input.inputValue()
  expect(secondVal).not.toBe(firstVal)

  await q1Input.fill('math.num.real')
  await expect(q1Card.getByLabel('第1题 错因分类')).toHaveCount(0)
  await expect(q1Card.getByLabel('第1题 复盘备注')).toHaveCount(0)
  await q1Card.getByRole('button', { name: '确认入账' }).click()

  await expect(page.getByRole('status')).toContainText('已完成人工核对并正式入账')
  await expect(draftDesk.locator('li.draft-card-item')).toHaveCount(0)

  // 补充乱序 + 满分题 + 失分题待核对明细（纯数字题号 10、2、3），验证自然排序、满分隐藏错因与分段批量确认
  const examsRes = await page.request.get('/api/school-exams?subject=math', {
    headers: { Authorization: `Bearer ${ADMIN_TOKEN}` },
  })
  const examsList = (await examsRes.json()) as Array<{ id: string; title: string }>
  const targetExam = examsList.find(e => e.title.includes('十月数学待核明细演示'))!
  const seedDraftsRes = await page.request.post(`/api/school-exams/${targetExam.id}/items`, {
    headers: { Authorization: `Bearer ${ADMIN_TOKEN}` },
    data: {
      items: [
        { question_label: '10', knowledge_id: 'unmapped', earned_points: 1, max_points: 2, scoring_origin: 'ocr_draft' },
        { question_label: '3', knowledge_id: 'unmapped', earned_points: 2, max_points: 2, scoring_origin: 'ocr_draft' },
        { question_label: '2', knowledge_id: 'unmapped', earned_points: 0, max_points: 2, scoring_origin: 'ocr_draft' },
      ],
    },
  })
  expect(seedDraftsRes.status()).toBe(201)

  await examRegion.getByRole('button', { name: '刷新' }).click()
  await expect(draftDesk.locator('li.draft-card-item')).toHaveCount(3)

  // 1) 严格按 2 -> 3 -> 10 自然序展示（不再是 10 排在 2 前面）
  const orderedHeadings = await draftDesk.locator('li.draft-card-item .draft-card-head b').allInnerTexts()
  expect(orderedHeadings).toEqual(['第 2 题', '第 3 题', '第 10 题'])

  // 2) 所有分数只读 + 满分题（第 3 题）无需复盘 + 消除 unmapped 预填
  const card3 = draftDesk.locator('li.draft-card-item', { hasText: '第 3 题' })
  await expect(card3).toContainText('✓ 作答正确')
  await expect(card3.locator('input[type="number"]')).toHaveCount(0)
  await expect(card3.getByLabel('第 3 题 错因分类')).toHaveCount(0)
  await expect(card3.getByLabel('第 3 题 复盘备注')).toHaveCount(0)
  await expect(card3.getByLabel('第 3 题 所属知识点')).toHaveValue('')

  // 3) 失分题（第 2 题）仅填知识点，确认后推送学生端完成复盘；用「同上题」一键填入第 3 题，并测试状态筛选与分段批量确认
  const card2 = draftDesk.locator('li.draft-card-item', { hasText: '第 2 题' })
  await card2.getByLabel('第 2 题 所属知识点').fill('math.num.real')
  await card3.getByRole('button', { name: '同上题' }).click()
  await expect(card3.getByLabel('第 3 题 所属知识点')).not.toHaveValue('')

  await draftDesk.getByRole('button', { name: /待补考点 \(1\)/ }).click()
  await expect(draftDesk.locator('li.draft-card-item')).toHaveCount(1)
  await expect(draftDesk.locator('li.draft-card-item')).toContainText('第 10 题')
  await draftDesk.getByRole('button', { name: /全部 \(3\)/ }).click()

  await draftDesk.getByRole('button', { name: /先确认已就绪项 \(2 题\)/ }).click()
  await expect(page.getByRole('status')).toContainText('已先确认 2 条已就绪待核对明细')
  await expect(draftDesk.locator('li.draft-card-item')).toHaveCount(1)

  const card10 = draftDesk.locator('li.draft-card-item', { hasText: '第 10 题' })
  await draftDesk.getByRole('button', { name: '智能补全关联' }).click()
  await expect(card10.locator('.candidate-chip-btn')).toHaveCount(3)
  await expect(card10.locator('.draft-basis-tag').first()).toBeVisible()
  await expect(card10.getByLabel('第 10 题 所属知识点')).not.toHaveValue('')
  await expect(card10.getByLabel('第 10 题 所属知识点')).toHaveClass(/input-auto-linked/)
  await card10.getByLabel('第 10 题 所属知识点').fill('math.num.real')
  await draftDesk.getByRole('button', { name: '批量确认本页待核明细' }).click()
  await expect(draftDesk.locator('li.draft-card-item')).toHaveCount(0)

  const noOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
  expect(noOverflow).toBe(true)

  await examRegion.getByRole('tab', { name: /已核对明细与补录/ }).click()
  const itemsPanel = examRegion.locator('#exam-panel-items')
  const confirmedList = itemsPanel.getByRole('region', { name: '逐题得分与考点明细' })
  await expect(confirmedList).toContainText('第1题')
  await expect(confirmedList).toContainText('第 10 题')
  await expect(confirmedList).toContainText('已确认')
  await expect(confirmedList).toContainText('待学生复盘')

  // 切换至学生端「校考复盘」：先看台账目录，确认不展示「日常练习错题回顾」，再钻取进入单场三步引导复盘
  await enterSpace(page)
  await navTab(page, /校考复盘/).click()
  const reflectionRegion = page.getByRole('region', { name: '校考复盘工作台' })
  await expect(reflectionRegion).toBeVisible()
  await expect(reflectionRegion.locator('h2')).toHaveText('校考复盘')
  await expect(reflectionRegion).not.toContainText('防敷衍')
  await expect(reflectionRegion).not.toContainText('系统会拦截敷衍套话')
  await expect(page.locator('main')).not.toContainText('日常练习错题回顾')
  const examTile = reflectionRegion.locator('article.reflection-exam-tile', { hasText: '十月数学待核明细演示' })
  await expect(examTile).toBeVisible()
  await examTile.getByRole('button', { name: /进入本场复盘/ }).click()
  await expect(reflectionRegion.getByRole('button', { name: /返回校考台账/ })).toBeVisible()
  await expect(reflectionRegion.getByRole('tablist', { name: '错题切换' })).toBeVisible()
  await expect(reflectionRegion.locator('li.reflection-card')).toHaveCount(1)
  const q1ReflectionCard = reflectionRegion.locator('li.reflection-card', { hasText: '第1题' }).first()
  await expect(q1ReflectionCard).toBeVisible()
  // 第 1 步：回到考场
  await q1ReflectionCard.getByRole('button', { name: /一看就有思路/ }).click()
  // 第 2 步：找到那一步（先测套话与仅点句式起头不补全被追问）
  await q1ReflectionCard.getByRole('button', { name: /运算\/粗心失误/ }).click()
  await q1ReflectionCard.getByLabel('第1题 当时卡在哪一步').fill('太粗心了没看清看错了')
  await q1ReflectionCard.getByRole('button', { name: /下一步：写给下次的自己/ }).click()
  await q1ReflectionCard.getByLabel('第1题 给下次的提醒').fill('下次一定注意认真审题')
  await q1ReflectionCard.getByRole('button', { name: '收好提醒卡 ✓' }).click()
  await expect(q1ReflectionCard.locator('.reflection-reject-alert')).toContainText('粗心')

  // 仅点句式起头不补全也会被追问
  await q1ReflectionCard.getByRole('button', { name: /② 找到那一步/ }).click()
  await q1ReflectionCard.getByLabel('第1题 当时卡在哪一步').fill('')
  await q1ReflectionCard.getByRole('button', { name: /在「」这一步/ }).click()
  await q1ReflectionCard.getByRole('button', { name: /下一步：写给下次的自己/ }).click()
  await q1ReflectionCard.getByLabel('第1题 给下次的提醒').fill('')
  await q1ReflectionCard.getByRole('button', { name: /如果再看到「」/ }).click()
  await q1ReflectionCard.getByRole('button', { name: '收好提醒卡 ✓' }).click()
  await expect(q1ReflectionCard.locator('.reflection-reject-alert')).toContainText('具体')

  // 填写具体复盘后成功收好提醒卡
  await q1ReflectionCard.getByRole('button', { name: /② 找到那一步/ }).click()
  await q1ReflectionCard.getByLabel('第1题 当时卡在哪一步').fill('去分母移项时常数项正负号抄反导致判别式计算错误')
  await q1ReflectionCard.getByRole('button', { name: /下一步：写给下次的自己/ }).click()
  await q1ReflectionCard.getByLabel('第1题 给下次的提醒').fill('每次移项后立刻代回原等式核对正负号再继续求解')
  await q1ReflectionCard.getByRole('button', { name: '收好提醒卡 ✓' }).click()
  await expect(page.getByRole('status')).toContainText('提醒卡已收好')
  await reflectionRegion.getByRole('button', { name: /返回校考台账/ }).click()
  await expect(reflectionRegion.locator('article.reflection-exam-tile', { hasText: '十月数学待核明细演示' })).toBeVisible()

  // 回到管理端：第四阶段「错误分析与复盘」集中查看学生复盘、确认失分题干与退回重写闭环
  await enterAdminSpace(page)
  await adminNavTab(page, /学校考试/).click()
  const adminExamRegion = page.getByRole('region', { name: '学校考试总分' })
  await adminExamRegion.locator('button.exam-pick', { hasText: '十月数学待核明细演示' }).click()
  await adminExamRegion.getByRole('tab', { name: /错误分析与复盘/ }).click()
  const adminAnalysisPanel = adminExamRegion.locator('#exam-panel-analysis')
  await expect(adminAnalysisPanel).toContainText('本场失分概览与错因分布')
  await expect(adminAnalysisPanel).toContainText('运算/粗心失误')

  // 进入第 4 步「失分题干与学生复盘」：编辑并确认第 1 题题干（含公式）与作答，并验证退回重写
  await adminAnalysisPanel.getByRole('button', { name: /4\. 失分题干与学生复盘/ }).click()
  const q1AdminRow = adminAnalysisPanel.locator('li.attachment-row', { hasText: '第1题' }).first()
  await expect(q1AdminRow).toContainText('学生已复盘')
  await expect(q1AdminRow).toContainText('去分母移项时常数项正负号抄反')
  await q1AdminRow.getByRole('button', { name: /编辑 \/ 确认原题与作答/ }).click()
  await q1AdminRow.getByLabel('第1题 原题题干').fill('解方程 $x^2 - 4 = 0$')
  await q1AdminRow.getByLabel('第1题 学生当时作答').fill('x = 2')
  await q1AdminRow.getByRole('button', { name: '确认题干' }).click()
  await expect(q1AdminRow).toContainText('题干已确认')

  await q1AdminRow.getByRole('button', { name: '退回重写' }).click()
  await q1AdminRow.getByLabel('第1题 退回重写原因').fill('请补充说明判别式具体算成了多少')
  await q1AdminRow.getByRole('button', { name: '确认退回重写' }).click()
  await expect(q1AdminRow).toContainText('已退回重写')
  await expectHonestLanguage(page)

  // 切回学生端确认：已确认题干显示 KaTeX 公式与「我当时的作答」，家长留言可见
  await enterSpace(page)
  await navTab(page, /校考复盘/).click()
  const stuExamTile = page.getByRole('region', { name: '校考复盘工作台' }).locator('article.reflection-exam-tile', {
    hasText: '十月数学待核明细演示',
  })
  await stuExamTile.getByRole('button', { name: /进入本场复盘/ }).click()
  const q1StuCard = page.locator('li.reflection-card', { hasText: '第1题' }).first()
  await expect(q1StuCard).toContainText('家长想和你再聊聊这题')
  await expect(q1StuCard).toContainText('家长留言：请补充说明判别式具体算成了多少')
  await expect(q1StuCard.locator('.reflection-stem-box .katex')).toBeVisible()
  await expect(q1StuCard.locator('.reflection-stem-box')).toContainText('x = 2')

  // ST-023：校考复盘「书童陪你想」对话 → 2轮后整理草稿回填三步卡 → 收好提醒卡 → 管理端只读回溯
  await q1StuCard.getByRole('button', { name: /书童陪你想/ }).click()
  const coachPanel = q1StuCard.getByRole('region', { name: '第1题 书童陪你想' })
  await expect(coachPanel).toBeVisible()
  await expect(coachPanel.locator('.msg-row.ai')).toHaveCount(1)

  await coachPanel.getByLabel('第1题 给书童发消息').fill('我去分母移项的时候把负号弄反了')
  await coachPanel.getByRole('button', { name: '发送' }).click()
  await expect(coachPanel.locator('.msg-row.stu')).toHaveCount(1)
  await expect(coachPanel).toContainText('1/2')

  await coachPanel.getByLabel('第1题 给书童发消息').fill('下次移项我先圈出负号再代回原式验算')
  await coachPanel.getByRole('button', { name: '发送' }).click()
  await expect(coachPanel.locator('.msg-row.stu')).toHaveCount(2)

  await coachPanel.getByRole('button', { name: /把刚才聊明白的整理成提醒卡草稿/ }).click()
  await expect(q1StuCard.locator('.reflection-coach-hint')).toContainText('书童按你刚才聊的内容起草了草稿')
  await expect(q1StuCard.getByLabel('第1题 给下次的提醒')).toHaveValue(/代回原式验算/)
  await q1StuCard.getByRole('button', { name: '收好提醒卡 ✓' }).click()
  await expect(page.getByRole('status')).toContainText('提醒卡已收好')

  // 切回管理端第四阶段第 4 步：折叠展开只读查看学生与书童对话过程
  await enterAdminSpace(page)
  await adminNavTab(page, /学校考试/).click()
  const adminExamRegion2 = page.getByRole('region', { name: '学校考试总分' })
  await adminExamRegion2.locator('button.exam-pick', { hasText: '十月数学待核明细演示' }).click()
  await adminExamRegion2.getByRole('tab', { name: /错误分析与复盘/ }).click()
  const adminAnalysisPanel2 = adminExamRegion2.locator('#exam-panel-analysis')
  await adminAnalysisPanel2.getByRole('button', { name: /4\. 失分题干与学生复盘/ }).click()
  const q1AdminRow2 = adminAnalysisPanel2.locator('li.attachment-row', { hasText: '第1题' }).first()
  await q1AdminRow2.getByRole('button', { name: /查看书童对话过程/ }).click()
  await expect(q1AdminRow2.locator('.admin-coach-readonly')).toContainText('把负号弄反了')
})

/* ---------- J5 审核台：录入真题全闭环 ---------- */

test('J5 审核台：题源登记→来源人工审核→附件解析→确认导入→草稿审核→发布（人工门禁全程如实）', async ({ page }) => {
  await enterAdminSpace(page)
  await adminNavTab(page, /^题库/).click()

  const sourcesPanel = page.locator('#ledger-panel-sources')
  await expect(sourcesPanel.locator('.step-stage-body section.card')).toHaveCount(1)

  // 第 1 步切换到新建题源模式登记题源
  const ledger = page.getByRole('region', { name: '题源台账' })
  await ledger.getByRole('button', { name: '＋ 登记新题源' }).click()
  await ledger.getByLabel('题源标题').fill('虚构测试数据：J5 审核台旅程题源')
  await ledger.getByLabel('版权状态').selectOption('personal_use_reviewed')
  await ledger.getByRole('button', { name: '新建题源' }).click()
  await expect(page.getByRole('status')).toContainText('题源已登记')

  // 回第 1 步台账确认新题源处于未审核状态，再进入第 3 步「来源人工审核」
  await sourcesPanel.getByRole('button', { name: /选定或新建题源/ }).click()
  const newRow = ledger.locator('li.source-item', { hasText: 'J5 审核台旅程题源' })
  await expect(newRow).toContainText('未审核')

  await sourcesPanel.getByRole('button', { name: /来源人工审核/ }).click()
  const review = page.getByRole('region', { name: '来源人工审核' })
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

  await sourcesPanel.getByRole('button', { name: /选定或新建题源/ }).click()
  await expect(newRow.locator('.chip.good')).toContainText('已人工审核')

  // 切入「附件解析与录入」：未上传附件前第 2 步「逐题人工录入工作台」必须严格锁定阻断跳步
  await page.getByRole('tab', { name: /附件解析与录入/ }).click()
  const attachments = page.getByRole('region', { name: '附件与解析' })
  await expect(attachments).toBeVisible()
  const importStepPill = attachments.getByRole('button', { name: /逐题人工录入工作台/ })
  await expect(importStepPill).toHaveAttribute('aria-disabled', 'true')
  await importStepPill.click({ force: true })
  await expect(attachments.locator('.gate-alert-banner')).toContainText('不可跳步至')

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

  await attachments.getByRole('button', { name: '解析', exact: true }).click()
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
  await sourcesPanel.getByRole('button', { name: /选定或新建题源/ }).click()
  await expect(newRow.locator('.chip.wait')).toContainText('未审核')
  await expect(sourcesPanel).not.toContainText('owner')
  await expect(sourcesPanel).not.toContainText('SHA256')
  await sourcesPanel.getByRole('button', { name: /来源人工审核/ }).click()
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

test('J7 知识图谱交互展示：Vue Flow 关系图谱、脉络聚焦、领域筛选、选学排除与未掌握高亮', async ({ page }) => {
  await enterSpace(page)
  await navTab(page, /知识点展示/).click()

  const section = page.getByRole('region', { name: '知识点关系图谱展示' })
  await expect(section).toBeVisible()
  const graphGroup = page.getByRole('group', { name: '知识点层级与前置关联图谱' })
  await expect(graphGroup).toBeVisible()
  await expect(graphGroup.locator('.vue-flow')).toBeVisible()
  await expect(graphGroup.locator('.vue-flow__node-knowledgeLeaf').first()).toBeVisible()
  const fullLeafCount = await graphGroup.locator('.vue-flow__node-knowledgeLeaf').count()
  expect(fullLeafCount).toBeGreaterThan(10)

  // 不含选学（*）节点（三元一次方程组解法、切线长定理均标记 is_elective=true）
  const allText = await section.innerText()
  expect(allText).toContain('已自动排除选学*内容')
  expect(allText).not.toContain('三元一次方程组')
  // 图谱展示全面中文化：不得泄露内部领域英文编码
  for (const rawDomain of ['num_alg', 'geom', 'stat_prob', 'comp_prac']) {
    expect(allText).not.toContain(rawDomain)
  }

  // 领域过滤、仅高亮未掌握切换及图谱节点点选
  await section.locator('.domain-filter-strip').getByRole('button', { name: '数与代数', exact: true }).click()
  const filteredLeafCount = await graphGroup.locator('.vue-flow__node-knowledgeLeaf').count()
  expect(filteredLeafCount).toBeLessThan(fullLeafCount)
  await section.getByRole('button', { name: '仅高亮未掌握' }).click()
  await section.getByRole('button', { name: '仅高亮未掌握' }).click()
  await section.getByRole('button', { name: /全部领域/ }).click()

  await graphGroup.getByRole('button', { name: /有理数及其运算/ }).click()
  const detail = page.getByRole('complementary', { name: '选中知识点详情' })
  await expect(detail).toContainText('有理数及其运算')
  await expect(detail).toContainText('有效独立样本')

  // 「仅看选中脉络」子图过滤与恢复、缩放与全览控制
  await graphGroup.getByRole('button', { name: '🕸️ 仅看选中脉络' }).click()
  const lineageLeafCount = await graphGroup.locator('.vue-flow__node-knowledgeLeaf').count()
  expect(lineageLeafCount).toBeGreaterThan(1)
  expect(lineageLeafCount).toBeLessThan(fullLeafCount)
  await graphGroup.getByRole('button', { name: /退出脉络子图/ }).click()
  expect(await graphGroup.locator('.vue-flow__node-knowledgeLeaf').count()).toBe(fullLeafCount)

  await graphGroup.getByRole('button', { name: '放大图谱' }).click()
  await graphGroup.getByRole('button', { name: '缩小图谱' }).click()
  await graphGroup.getByRole('button', { name: '⛶ 自适应全览' }).click()

  await expectHonestLanguage(page)
})

/* ---------- J8 管理端知识点审核：同步→课标草稿→批量审核→发布 ---------- */

test('J8 管理端知识点审核：同步候选→按课标生成审核依据草稿→批量审核→发布版本快照', async ({ page }) => {
  await enterAdminSpace(page)
  await adminNavTab(page, /^知识点库/).click()

  await expect(page.getByText('数学权威知识点库审核工作台')).toBeVisible()
  // 默认隐藏英文技术编码与 MOE 标准代码
  await expect(page.locator('.knowledge-workbench')).not.toContainText('MOE-2022-')

  // 等首屏候选与课标条款加载均完成后再触发同步，避免与 mount 期的 loadCandidates 竞态。
  await expect(page.locator('.status-banner')).toContainText('待审核: 48')
  await expect(page.locator('.status-banner')).toContainText('课标条款:')

  // 未同步入库前（候选尚无 DB id），第 3 步「提交专家审核决定」应呈锁定拦截态
  const auditStepPill = page.getByRole('button', { name: /提交专家审核决定/ })
  await expect(auditStepPill).toHaveAttribute('aria-disabled', 'true')
  await auditStepPill.click({ force: true })
  await expect(page.locator('.gate-alert-banner')).toContainText('不可跳步至')

  const seedDone = page.waitForResponse(
    res => res.url().includes('/api/admin/knowledge/candidates/seed') && res.request().method() === 'POST',
  )
  await page.getByRole('button', { name: '同步候选入库 (待审)' }).click()
  expect((await seedDone).status()).toBe(201)
  // 按钮恢复为「同步候选入库 (待审)」且可用，表示 seed 后的 await loadCandidates() 已落库更新 id。
  await expect(page.getByRole('button', { name: '同步候选入库 (待审)' })).toBeEnabled({ timeout: 15_000 })
  await expect(page.locator('.status-banner')).toContainText('待审核: 48')

  // 按 1 → 2 → 3 单卡步进：查看第 2 步课标溯源并用一键按钮带草稿进入第 3 步
  await expect(page.locator('#kr-panel-review .step-stage-body section.card')).toHaveCount(1)
  await page.getByRole('button', { name: /下一步：核对课标溯源与兼容/ }).click()
  await expect(page.getByRole('region', { name: '课标溯源条款与旧考点兼容' })).toBeVisible()
  await page.getByRole('button', { name: /按课标生成依据草稿并进入第 3 步/ }).click()

  await expect(page.getByLabel('审核依据与意见 (必填):')).not.toHaveValue('')
  await page.getByLabel('审核人实名标识 (必填):').fill('owner_e2e_reviewer')
  await page.getByRole('button', { name: '按课标生成审核依据草稿' }).click()
  await expect(page.getByLabel('审核依据与意见 (必填):')).not.toHaveValue('')

  await page.getByRole('button', { name: /按课标批量审核待审 \(48\)/ }).click()
  await expect(page.locator('.status-banner')).toContainText('待审核: 0', { timeout: 15_000 })
  await expect(page.locator('.status-banner')).toContainText('已通过: 48', { timeout: 15_000 })

  await page.getByRole('tab', { name: /版本发布与快照/ }).click()
  await page.getByRole('button', { name: '发布正式版本快照', exact: true }).click()
  // 发布成功后自动推进到第 2 步「历史发布版本快照」
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


test('J10 全科校考同步中心：四步发现、冲突人工匹配、私有入档、本人排名与总分核对', async ({ page }) => {
  const consoleErrors: string[] = []
  const pageErrors: string[] = []
  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text())
  })
  page.on('pageerror', err => pageErrors.push(String(err)))

  const created = await page.request.post('/api/school-exams', {
    headers: { Authorization: `Bearer ${ADMIN_TOKEN}` },
    data: {
      subject: 'math',
      title: '虚构测试数据 · 九上10月月考 UI 核对',
      exam_date: '2025-10-12',
      earned_points: 88,
      max_points: 100,
      confirmed_by_user: false,
      school_name: '虚构测试数据实验学校',
      grade: '九年级',
      exam_type: 'monthly',
      academic_year: '2025-2026',
      term: 'first',
      series_title: '2025—2026学年第一学期 九年级10月月考',
    },
  })
  expect(created.status()).toBe(201)
  const examId = ((await created.json()) as { id: string }).id

  let paperStatus = 'needs_review'
  let paperMatchState = 'CONFLICT'
  let rankConfirmed = false
  let scanned = false
  const basePaper = {
    id: 'paper-e2e-1',
    filename: '虚构测试数据_九年级数学月考试卷.docx',
    sha256: 'b'.repeat(64),
    media_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    byte_size: 20480,
    source_kind: 'local_scan',
    source_name: 'inbox',
    source_ref: 'inbox/虚构测试数据_九年级数学月考试卷.docx',
    header: {
      subject: 'math',
      academic_year: '2025-2026',
      grade: '9',
      exam_type: 'monthly',
      exam_type_label: '月考',
      exam_date: '2025-10-12',
      confidence: 'high',
      complete: true,
      fields: {
        academic_year: { status: 'found', value: '2025-2026', evidence: '2025—2026学年度' },
        grade: { status: 'found', value: '9', evidence: '九年级10月月考' },
        exam_type: { status: 'found', value: 'monthly', evidence: '10月月考' },
        subject: { status: 'found', value: 'math', evidence: '文件名：九年级数学月考试卷.docx' },
        exam_date: { status: 'found', value: '2025-10-12', evidence: '考试时间：2025年10月12日' },
      },
      text_excerpt: '2025—2026学年度九年级10月月考\n数学\n2025.10.12\n姓名：[已脱敏]',
      warnings: [],
    },
    candidates: [
      {
        exam_id: examId,
        title: '虚构测试数据 · 九上10月月考 UI 核对',
        exam_date: '2025-11-15',
        score: 9,
        exact: false,
        comparisons: [
          { field: 'subject', label: '学科', expected: 'math', actual: 'math', state: 'match' },
          { field: 'academic_year', label: '学年度', expected: '2025-2026', actual: '2025-2026', state: 'match' },
          { field: 'grade', label: '年级', expected: '9', actual: '9', state: 'match' },
          { field: 'exam_type', label: '考试类型', expected: '月考', actual: '月考', state: 'match' },
          { field: 'exam_date', label: '考试日期', expected: '2025-10', actual: '2025-11', state: 'conflict' },
        ],
        conflicts: ['exam_date'],
        missing: [],
      },
    ],
    school_exam_id: null,
    exam: null,
    error_code: null,
    imported_at: null,
    created_at: '2026-11-15T00:00:00Z',
    updated_at: '2026-11-15T00:00:00Z',
  }
  const source = {
    environment: 'development',
    directory: '/tmp/pageboy-test-home/development/school-exams/inbox',
    directory_display: '$PAGEBOY_HOME/development/school-exams/inbox',
    real_source_configured: false,
    source_kind: 'local_inbox',
    ready: true,
    source_code: 'SOURCE_NOT_CONFIGURED',
    message: '未配置真实授权学校试卷来源；可扫描收件箱中已有文件，但不会伪造远程下载。',
    supported_formats: ['PDF', 'DOCX', 'PNG', 'JPG/JPEG'],
    max_file_bytes: 36700160,
  }
  const centerPayload = () => ({
    source,
    latest_scan: scanned
      ? {
          id: 'scan-e2e-1',
          status: 'completed',
          discovered_count: 1,
          imported_count: 0,
          duplicate_count: 0,
          invalid_count: 0,
          needs_review_count: paperStatus === 'imported' ? 0 : 1,
          error_count: 0,
          errors: [],
          started_at: '2026-11-15T00:00:00Z',
          finished_at: '2026-11-15T00:00:02Z',
        }
      : null,
    counts: {
      total: scanned ? 1 : 0,
      needs_review: scanned && paperStatus === 'needs_review' ? 1 : 0,
      matched: paperStatus === 'matched' ? 1 : 0,
      imported: paperStatus === 'imported' ? 1 : 0,
      rejected: 0,
    },
    papers: scanned
      ? [
          {
            ...basePaper,
            status: paperStatus,
            match_state: paperMatchState,
            school_exam_id: paperStatus === 'needs_review' ? null : examId,
            exam: paperStatus === 'needs_review'
              ? null
              : {
                  id: examId,
                  title: '虚构测试数据 · 九上10月月考 UI 核对',
                  subject: 'math',
                  exam_date: '2025-10-12',
                  confirmed_by_user: false,
                },
          },
        ]
      : [],
  })

  await page.route('**/api/school-exams/sync-center*', route =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(centerPayload()) }),
  )
  await page.route('**/api/school-exams/pipeline/scan', route => {
    scanned = true
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        run: {
          id: 'scan-e2e-1',
          status: 'completed',
          discovered_count: 1,
          imported_count: 0,
          duplicate_count: 0,
          invalid_count: 0,
          needs_review_count: 1,
          error_count: 0,
          errors: [],
          started_at: '2026-11-15T00:00:00Z',
          finished_at: '2026-11-15T00:00:02Z',
        },
        papers: centerPayload().papers,
        source,
      }),
    })
  })
  await page.route('**/api/school-exams/pipeline/papers/paper-e2e-1/match', async route => {
    const body = route.request().postDataJSON() as { exam_id?: string; confirmed_by_human?: boolean }
    if (body.exam_id === examId && body.confirmed_by_human === true) {
      paperStatus = 'matched'
      paperMatchState = 'MANUAL_CONFIRMED'
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        paper: centerPayload().papers[0],
        match: {
          state: paperMatchState,
          confidence: 'high',
          best_exam_id: examId,
          candidates: basePaper.candidates,
          reasons: ['管理员已人工确认'],
          missing_fields: [],
        },
      }),
    })
  })
  await page.route('**/api/school-exams/pipeline/papers/paper-e2e-1/import', route => {
    paperStatus = 'imported'
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        already_imported: false,
        paper: centerPayload().papers[0],
        attachment_created: true,
        attachment: {
          id: 'att-e2e-1',
          filename: basePaper.filename,
          media_type: basePaper.media_type,
          sha256: basePaper.sha256,
          byte_size: basePaper.byte_size,
          created_at: '2026-11-15T00:00:03Z',
        },
        metadata_updates: [],
      }),
    })
  })
  await page.route(`**/api/school-exams/${examId}/ranks`, route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        exam_id: examId,
        ranks: [
          {
            id: 'rank-e2e-1',
            subject_scope: 'math',
            scope: 'class',
            rank_value: 5,
            participant_count: 320,
            percentile: 0.96,
            source_name: 'k12100',
            source_field: 'classrank',
            ownership_status: 'verified',
            ownership_basis: 'single_student_ref_authenticated_subject_response',
            review_status: rankConfirmed ? 'confirmed' : 'pending',
            captured_at: '2026-11-15T00:00:04Z',
            history_count: 1,
          },
        ],
        missing_scopes: ['grade', 'school', 'region'],
        disclaimer: '本人排名仅为平台来源快照，不进入知识点能力画像，也不预测中考成绩。',
      }),
    }),
  )
  await page.route(`**/api/school-exams/${examId}/ranks/rank-e2e-1/confirm`, route => {
    rankConfirmed = true
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 'rank-e2e-1',
        scope: 'class',
        rank_value: 5,
        participant_count: 320,
        review_status: 'confirmed',
      }),
    })
  })
  await page.route('**/api/school-exams/k12100-sync/status', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        environment: 'development',
        mode: 'host_direct',
        can_run_local: true,
        is_isolated: false,
        browser_ready: true,
        node_available: true,
        playwright_available: true,
        unavailable_code: null,
        unavailable_reason: null,
        credentials: {
          status: 'ready',
          username_masked: '139****1111',
          deepseek_configured: true,
          deepseek_masked: 'sk-****',
          message: '已就绪',
        },
        deepseek_configured: true,
        active_job_id: null,
        latest_job: null,
        recommended_cli_command: 'uv run python scripts/k12100_sync.py collect --env development',
      }),
    }),
  )

  await enterAdminSpace(page)
  await adminNavTab(page, /学校考试/).click()
  const targetRow = page.getByRole('region', { name: '学校考试总分' })
    .locator('.exam-item', { hasText: '虚构测试数据 · 九上10月月考 UI 核对' })
  await expect(targetRow).toHaveCount(1)
  await targetRow.getByRole('button', { name: '提交考试信息', exact: true }).click()
  await expect(page.getByRole('heading', { name: '上传原卷' })).toBeVisible()
  await page.locator('ol.step-pill-bar').getByRole('button', { name: /3\. 全科校考同步/ }).click()
  const sync = page.getByRole('region', { name: '全科校考同步中心' })
  await expect(sync).toBeVisible()
  await expect(sync).toContainText('还没有发现试卷')

  // 第一步：扫描原卷目录，列出真实文件索引与卷头摘要
  await sync.getByRole('button', { name: '扫描私有收件箱' }).click()
  await expect(sync).toContainText('虚构测试数据_九年级数学月考试卷.docx')
  await expect(sync).toContainText('身份字段冲突')

  // 直接进入「核对入档」：档案与排名均来自真实管理端接口
  await sync.getByRole('button', { name: /核对入档/ }).click()
  await expect(sync).toContainText('核对入档')
  await expect(sync).toContainText('虚构测试数据 · 九上10月月考 UI 核对')
  await expect(sync).toContainText('总分待核对')
  await expect(sync).toContainText('第 5 名 / 320 人')
  await expect(sync).toContainText('待确认来源')
  await expect(sync).toContainText('本人归属已验证')

  // 人工排名确认与总分锁定均要求显式勾选/提交
  await sync.getByRole('button', { name: '确认排名来源' }).click()
  await expect(sync).toContainText('已人工确认')
  await sync.getByLabel('实得总分').fill('88')
  await expect(sync.getByRole('button', { name: '确认并锁定总分' })).toBeDisabled()
  await sync.getByLabel(/我已对照成绩单人工核对/).check()
  await sync.getByRole('button', { name: '确认并锁定总分' }).click()
  await expect(sync).toContainText('总分已核对')
  await expect(sync).toContainText('总分已人工锁定')

  await page.evaluate(() => Promise.allSettled(Array.from(document.getAnimations()).map(animation => animation.finished)))
  const axeSync = await new AxeBuilder({ page })
    .include('.exam-sync-center')
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze()
  expect(axeSync.violations.filter(violation => violation.impact === 'critical' || violation.impact === 'serious')).toEqual([])

  // 键盘可操作性：Tab 顺序中的步骤按钮可由 Enter 激活并回写 aria-current。
  const syncStep = sync.getByRole('button', { name: /k12100 报告同步/ })
  await syncStep.focus()
  await syncStep.press('Enter')
  await expect(syncStep).toHaveAttribute('aria-current', 'step')

  await expectHonestLanguage(page)
  expect(pageErrors).toEqual([])
  expect(consoleErrors).toEqual([])
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})

test('J10b 校考采集失败：429 风控立即停止且不以“完成”掩盖', async ({ page }) => {
  const created = await page.request.post('/api/school-exams', {
    headers: { Authorization: `Bearer ${ADMIN_TOKEN}` },
    data: {
      subject: 'math',
      title: '虚构测试数据 · 采集失败 UI',
      exam_date: '2025-10-23',
      earned_points: 0,
      max_points: 100,
      confirmed_by_user: false,
    },
  })
  expect(created.status()).toBe(201)
  const examId = ((await created.json()) as { id: string }).id

  await page.route('**/api/school-exams/sync-center*', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        source: {
          environment: 'development',
          directory: '/tmp/pageboy-test-home/development/school-exams/inbox',
          directory_display: '$PAGEBOY_HOME/development/school-exams/inbox',
          real_source_configured: false,
          source_kind: 'local_inbox',
          ready: true,
          source_code: 'SOURCE_NOT_CONFIGURED',
          message: '未配置真实授权学校试卷来源。',
          supported_formats: ['PDF'],
          max_file_bytes: 36700160,
        },
        latest_scan: null,
        counts: { total: 1, needs_review: 0, matched: 1, imported: 1, rejected: 0 },
        papers: [
          {
            id: 'paper-e2e-fail',
            filename: '虚构测试数据_失败状态.docx',
            sha256: 'c'.repeat(64),
            media_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            byte_size: 2048,
            source_kind: 'local_scan',
            source_name: 'inbox',
            source_ref: 'inbox/虚构测试数据_失败状态.docx',
            header: {
              subject: 'math',
              academic_year: '2025-2026',
              grade: '9',
              exam_type: 'monthly',
              exam_type_label: '月考',
              exam_date: '2025-10-23',
              confidence: 'high',
              complete: true,
              fields: {},
              text_excerpt: '虚构测试数据',
              warnings: [],
            },
            status: 'imported',
            match_state: 'EXACT_MATCH',
            candidates: [],
            school_exam_id: examId,
            exam: {
              id: examId,
              title: '虚构测试数据 · 采集失败 UI',
              subject: 'math',
              exam_date: '2025-10-23',
              confirmed_by_user: false,
            },
            error_code: null,
            imported_at: '2026-11-15T00:00:00Z',
            created_at: '2026-11-15T00:00:00Z',
            updated_at: '2026-11-15T00:00:00Z',
          },
        ],
      }),
    }),
  )
  await page.route('**/api/school-exams/k12100-sync/status', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        environment: 'development',
        mode: 'host_direct',
        can_run_local: true,
        is_isolated: false,
        browser_ready: true,
        node_available: true,
        playwright_available: true,
        unavailable_code: null,
        unavailable_reason: null,
        credentials: { status: 'ready', username_masked: '139****1111', deepseek_configured: false, deepseek_masked: null, message: '已就绪' },
        deepseek_configured: false,
        active_job_id: null,
        latest_job: null,
        recommended_cli_command: 'uv run python scripts/k12100_sync.py collect --env development',
      }),
    }),
  )
  let reportJobCalled = false
  await page.route('**/api/school-exams/k12100-sync/report-jobs', route => {
    reportJobCalled = true
    return route.fulfill({
      status: 202,
      contentType: 'application/json',
      body: JSON.stringify({
        job_id: 'job-e2e-429',
        kind: 'report',
        state: 'queued',
        stage_message: '任务已入队。',
        created_at: '2026-11-15T00:00:00Z',
        updated_at: '2026-11-15T00:00:00Z',
        exam_keyword: null,
        confirm_total_scores: false,
        error_code: null,
        error_message: null,
        result: null,
        report_result: null,
      }),
    })
  })
  await page.route('**/api/school-exams/k12100-sync/jobs/job-e2e-429', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        job_id: 'job-e2e-429',
        kind: 'report',
        state: 'failed',
        stage_message: '检测到 HTTP 429，已立即熔断止损。',
        created_at: '2026-11-15T00:00:00Z',
        updated_at: '2026-11-15T00:00:01Z',
        exam_keyword: null,
        confirm_total_scores: false,
        error_code: 'K12100_CIRCUIT_BREAKER',
        error_message: '检测到 HTTP 429，已立即熔断止损。',
        result: null,
        report_result: null,
      }),
    }),
  )
  // 排名与详情使用真实档案；只读排行接口返回缺失，避免伪造排名。
  await page.route(`**/api/school-exams/${examId}/ranks`, route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        exam_id: examId,
        ranks: [],
        missing_scopes: ['class', 'grade', 'school', 'region'],
        disclaimer: '本人排名仅为平台来源快照，不进入知识点能力画像，也不预测中考成绩。',
      }),
    }),
  )

  await enterAdminSpace(page)
  await adminNavTab(page, /学校考试/).click()
  const enterBtn = page.getByRole('button', { name: '提交考试信息' }).first()
  const titleInput = page.getByLabel('考试名称')
  await expect(enterBtn.or(titleInput)).toBeVisible()
  if (await enterBtn.isVisible()) {
    await enterBtn.click()
  } else {
    await titleInput.fill('同步入口占位校考（虚构测试数据）')
    await page.getByRole('button', { name: /提交考试信息并建档|暂存全科档案/ }).click()
  }
  await page.getByRole('button', { name: /3\. 全科校考同步/ }).click()
  const sync = page.getByRole('region', { name: '全科校考同步中心' })
  await expect(sync).toBeVisible()
  await sync.getByRole('button', { name: /^k12100 报告同步/ }).click()
  await expect(sync.getByRole('button', { name: '从 k12100 下载总分报告并同步' })).toBeEnabled()
  await sync.getByRole('button', { name: '从 k12100 下载总分报告并同步' }).click()
  await expect(sync).toContainText('检测到 HTTP 429，已立即熔断止损', { timeout: 8000 })
  expect(reportJobCalled).toBe(true)
  await expect(sync).not.toContainText('报告同步完成')
  await expect(sync).toContainText('已停止')
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})

test('J10d k12100 总分报告一键同步：无前置匹配直达、跳过已同步场次、新建与锁分冲突清晰呈现', async ({ page }) => {
  const created = await page.request.post('/api/school-exams', {
    headers: { Authorization: `Bearer ${ADMIN_TOKEN}` },
    data: {
      subject: 'math',
      title: '虚构测试数据 · 报告同步核对',
      exam_date: '2026-10-10',
      earned_points: 88,
      max_points: 100,
      confirmed_by_user: false,
      grade: '9',
      exam_type: 'unified_practice',
      academic_year: '2026-2027',
    },
  })
  expect(created.status()).toBe(201)
  const examId = ((await created.json()) as { id: string }).id

  await page.route('**/api/school-exams/sync-center*', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        source: {
          environment: 'development',
          directory: '/tmp/pageboy-test-home/development/school-exams/inbox',
          directory_display: '$PAGEBOY_HOME/development/school-exams/inbox',
          real_source_configured: false,
          source_kind: 'local_inbox',
          ready: true,
          source_code: 'SOURCE_NOT_CONFIGURED',
          message: '未配置真实授权学校试卷来源。',
          supported_formats: ['PDF'],
          max_file_bytes: 36700160,
        },
        latest_scan: null,
        counts: { total: 0, needs_review: 0, matched: 0, imported: 0, rejected: 0 },
        papers: [],
      }),
    }),
  )
  await page.route('**/api/school-exams/k12100-sync/status', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        environment: 'development',
        mode: 'host_direct',
        can_run_local: true,
        is_isolated: false,
        browser_ready: true,
        node_available: true,
        playwright_available: true,
        unavailable_code: null,
        unavailable_reason: null,
        credentials: { status: 'ready', username_masked: '25****86', deepseek_configured: true, deepseek_masked: 'sk-****', message: '已就绪' },
        deepseek_configured: true,
        active_job_id: null,
        latest_job: null,
        recommended_cli_command: 'uv run python scripts/k12100_sync.py collect --env development',
      }),
    }),
  )
  await page.route('**/api/school-exams/k12100-sync/report-jobs', route =>
    route.fulfill({
      status: 202,
      contentType: 'application/json',
      body: JSON.stringify({
        job_id: 'job-e2e-report-ok',
        kind: 'report',
        state: 'queued',
        stage_message: '任务已创建，准备下载「总分」报告…',
        created_at: '2026-11-18T00:00:00Z',
        updated_at: '2026-11-18T00:00:00Z',
        exam_keyword: null,
        confirm_total_scores: false,
        error_code: null,
        error_message: null,
        result: null,
        report_result: null,
      }),
    }),
  )
  await page.route('**/api/school-exams/k12100-sync/jobs/job-e2e-report-ok', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        job_id: 'job-e2e-report-ok',
        kind: 'report',
        state: 'completed',
        stage_message: '报告同步完成：下载 1 份，新建 1 科、更新 0 科、补全 0 科，新增草稿 3 题。',
        created_at: '2026-11-18T00:00:00Z',
        updated_at: '2026-11-18T00:00:03Z',
        exam_keyword: null,
        confirm_total_scores: false,
        error_code: null,
        error_message: null,
        result: null,
        report_result: {
          home_exams: [
            {
              external_exam_id: 'E-PREV',
              exam_name: '虚构测试数据 九年级上期中',
              exam_date: '2026-11-12',
              grade: '九年级',
              academic_year: '2026-2027',
              exam_type: '期中',
              already_synced: true,
            },
            {
              external_exam_id: 'E-NEW',
              exam_name: '虚构测试数据 统一练习一',
              exam_date: '2026-10-10',
              grade: '九年级',
              academic_year: '2026-2027',
              exam_type: '月考',
              already_synced: false,
            },
          ],
          reports: [],
          subject_actions: [
            {
              subject: 'math',
              subject_label: '数学',
              action: 'created',
              exam_id: examId,
              exam_title: '虚构测试数据 · 报告同步核对',
              exam_date: '2026-10-10',
              earned_points: 88,
              max_points: 100,
              confirmed_by_user: false,
              filled_fields: ['exam_date', 'grade'],
              conflict_fields: [],
              message: '已按 k12100 首页日期与报告身份新建待核对档案。',
              report_id: 'rep-1',
              report_title: '虚构测试数据 统一练习一',
              external_exam_id: 'E-NEW',
              report_exam_date: '2026-10-10',
              academic_year: '2026-2027',
              grade: '9',
              exam_type: '统一练习一',
            },
            {
              subject: 'english',
              subject_label: '英语',
              action: 'locked_conflict',
              exam_id: examId,
              exam_title: '虚构测试数据 · 英语锁定',
              exam_date: '2026-10-10',
              earned_points: 92,
              max_points: 100,
              confirmed_by_user: true,
              filled_fields: [],
              conflict_fields: [],
              message: '已人工锁定总分 92/100，与报告 85/100 不同；按锁分红线保留原值。',
              report_id: 'rep-1',
              report_title: '虚构测试数据 统一练习一',
              external_exam_id: 'E-NEW',
              report_exam_date: '2026-10-10',
              academic_year: '2026-2027',
              grade: '9',
              exam_type: '统一练习一',
            },
          ],
          totals: {
            home_exams: 2,
            skipped_existing: 1,
            downloaded: 1,
            reports_registered: 1,
            created_exams: 1,
            updated_exams: 0,
            filled_exams: 0,
            unchanged_exams: 0,
            locked_conflicts: 1,
            identity_conflicts: 0,
            awaiting_exam_date: 0,
            ambiguous_exams: 0,
            drafts_created: 3,
            drafts_updated: 0,
            auto_mapped: 1,
            cards_created: 2,
            cards_synced: 2,
            failures: 0,
          },
          failures: [],
          knowledge_evidence_created: 0,
        },
      }),
    }),
  )
  await page.route(`**/api/school-exams/${examId}/ranks`, route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        exam_id: examId,
        ranks: [],
        missing_scopes: ['class', 'grade', 'school', 'region'],
        disclaimer: '本人排名仅为平台来源快照，不进入知识点能力画像，也不预测中考成绩。',
      }),
    }),
  )

  await enterAdminSpace(page)
  await adminNavTab(page, /学校考试/).click()
  const enterBtn = page.getByRole('button', { name: '提交考试信息' }).first()
  const titleInput = page.getByLabel('考试名称')
  await expect(enterBtn.or(titleInput)).toBeVisible()
  if (await enterBtn.isVisible()) {
    await enterBtn.click()
  } else {
    await titleInput.fill('同步入口占位校考（虚构测试数据）')
    await page.getByRole('button', { name: /提交考试信息并建档|暂存全科档案/ }).click()
  }
  await page.getByRole('button', { name: /3\. 全科校考同步/ }).click()
  const sync = page.getByRole('region', { name: '全科校考同步中心' })
  await expect(sync).toBeVisible()
  // 无需先在第 1/2 步选试卷，第 3 步应可直接点击
  await sync.getByRole('button', { name: /^k12100 报告同步/ }).click()
  await sync.getByRole('button', { name: '从 k12100 下载总分报告并同步' }).click()
  await expect(sync).toContainText('本次报告同步结果', { timeout: 8000 })
  await expect(sync).toContainText('已同步跳过')
  await expect(sync).toContainText('新建待核对')
  await expect(sync).toContainText('锁分冲突')

  const noOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
  expect(noOverflow).toBe(true)

  await page.evaluate(() =>
    Promise.allSettled(Array.from(document.getAnimations()).map(animation => animation.finished)),
  )
  const axe = await new AxeBuilder({ page })
    .include('.exam-sync-center')
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze()
  expect(axe.violations).toEqual([])

  await sync.getByRole('button', { name: '核对总分 →' }).first().click()
  await expect(sync).toContainText('虚构测试数据 · 报告同步核对')
  await expect(sync).toContainText('总分待核对')
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})


test('J10e k12100 中断后二次跳过重跑：前期同步内容持续显示且支持跨学科跳转', async ({ page }) => {
  const mathRes = await page.request.post('/api/school-exams', {
    headers: { Authorization: `Bearer ${ADMIN_TOKEN}` },
    data: {
      subject: 'math',
      title: '虚构测试数据 · 九年级上期中',
      exam_date: '2026-11-12',
      earned_points: 88,
      max_points: 100,
      confirmed_by_user: false,
      grade: '9',
      exam_type: 'midterm',
      academic_year: '2026-2027',
    },
  })
  expect(mathRes.status()).toBe(201)
  const mathExamId = ((await mathRes.json()) as { id: string }).id

  const chiRes = await page.request.post('/api/school-exams', {
    headers: { Authorization: `Bearer ${ADMIN_TOKEN}` },
    data: {
      subject: 'chinese',
      title: '虚构测试数据 · 九年级上期中（语文）',
      exam_date: '2026-11-12',
      earned_points: 91,
      max_points: 120,
      confirmed_by_user: false,
      grade: '9',
      exam_type: 'midterm',
      academic_year: '2026-2027',
    },
  })
  expect(chiRes.status()).toBe(201)
  const chiExamId = ((await chiRes.json()) as { id: string }).id

  await page.route(`**/api/school-exams/${mathExamId}/ranks`, route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        exam_id: mathExamId,
        class_highest: 98,
        grade_highest: 100,
        ranks: [
          {
            id: 'rk-e2e-cls',
            subject_scope: 'math',
            scope: 'class',
            rank_value: 5,
            participant_count: null,
            percentile: null,
            highest_score: 98,
            source_name: 'k12100',
            source_field: 'report.math.class_rank',
            ownership_status: 'verified',
            ownership_basis: 'k12100_total_report_pdf',
            review_status: 'pending',
            captured_at: '2026-11-18T00:00:00Z',
            history_count: 1,
          },
          {
            id: 'rk-e2e-grd',
            subject_scope: 'math',
            scope: 'grade',
            rank_value: 42,
            participant_count: 680,
            percentile: null,
            highest_score: 100,
            source_name: 'k12100',
            source_field: 'report.math.grade_rank',
            ownership_status: 'verified',
            ownership_basis: 'k12100_total_report_pdf',
            review_status: 'pending',
            captured_at: '2026-11-18T00:00:00Z',
            history_count: 1,
          },
        ],
        total_ranks: [],
        report_total: {
          report_total_score: 179,
          report_total_max: 220,
          total_class_rank: 8,
          total_grade_rank: 120,
          total_participants: 680,
          total_class_highest: 205,
          total_grade_highest: 216,
        },
        missing_scopes: ['school', 'region'],
        disclaimer: '本人排名仅为平台来源快照，不进入知识点能力画像，也不预测中考成绩。',
      }),
    }),
  )

  await page.route('**/api/school-exams/sync-center*', async route => {
    const [mathStateRes, chiStateRes] = await Promise.all([
      page.request.get(`/api/school-exams/${mathExamId}`, { headers: { Authorization: `Bearer ${ADMIN_TOKEN}` } }),
      page.request.get(`/api/school-exams/${chiExamId}`, { headers: { Authorization: `Bearer ${ADMIN_TOKEN}` } }),
    ])
    const mathState = (await mathStateRes.json()) as { confirmed_by_user: boolean; earned_points: number }
    const chiState = (await chiStateRes.json()) as { confirmed_by_user: boolean; earned_points: number }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        source: {
          environment: 'development',
          directory: '/tmp/pageboy-test-home/development/school-exams/inbox',
          directory_display: '$PAGEBOY_HOME/development/school-exams/inbox',
          real_source_configured: false,
          source_kind: 'local_inbox',
          ready: true,
          source_code: 'SOURCE_NOT_CONFIGURED',
          message: '未配置真实授权学校试卷来源。',
          supported_formats: ['PDF'],
          max_file_bytes: 36700160,
        },
        latest_scan: null,
        counts: { total: 0, needs_review: 0, matched: 0, imported: 0, rejected: 0 },
        papers: [],
        synced_reports: [
          {
            id: 'rep-persisted-1',
            title: '虚构测试数据 · 九年级上期中分析报告册',
            external_exam_id: 'E-PERSIST-1',
            exam_date: '2026-11-12',
            academic_year: '2026-2027',
            grade: '9',
            exam_type: 'midterm',
            status: 'matched',
            match_state: 'MATCHED',
            report_total_score: 179,
            report_total_max: 220,
            total_class_rank: 8,
            total_grade_rank: 120,
            total_participants: 680,
            total_class_highest: 205,
            total_grade_highest: 216,
            pages: 12,
            updated_at: '2026-11-18T00:00:00Z',
            completeness: { complete: true, missing: [] },
            exams: [
              {
                exam_id: mathExamId,
                subject: 'math',
                subject_label: '数学',
                exam_title: '虚构测试数据 · 九年级上期中',
                exam_date: '2026-11-12',
                earned_points: mathState.earned_points,
                max_points: 100,
                confirmed_by_user: mathState.confirmed_by_user,
                draft_count: 14,
                confirmed_item_count: 0,
                attachment_count: 2,
                class_rank: 5,
                grade_rank: 42,
                participants: 680,
                class_highest: 98,
                grade_highest: 100,
                rank_synced_count: 2,
              },
              {
                exam_id: chiExamId,
                subject: 'chinese',
                subject_label: '语文',
                exam_title: '虚构测试数据 · 九年级上期中（语文）',
                exam_date: '2026-11-12',
                earned_points: chiState.earned_points,
                max_points: 120,
                confirmed_by_user: chiState.confirmed_by_user,
                draft_count: 0,
                confirmed_item_count: 18,
                attachment_count: 2,
                class_rank: 7,
                grade_rank: 85,
                participants: 680,
                class_highest: 108,
                grade_highest: 115,
                rank_synced_count: 2,
              },
            ],
            unlinked_subjects: [],
          },
        ],
        sync_readiness: {
          total_reports: 1,
          complete_reports: 1,
          incomplete_reports: 0,
          all_complete: true,
        },
      }),
    })
  })
  await page.route('**/api/school-exams/k12100-sync/status', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        environment: 'development',
        mode: 'host_direct',
        can_run_local: true,
        is_isolated: false,
        browser_ready: true,
        node_available: true,
        playwright_available: true,
        unavailable_code: null,
        unavailable_reason: null,
        credentials: { status: 'ready', username_masked: '25****86', deepseek_configured: true, deepseek_masked: 'sk-****', message: '已就绪' },
        deepseek_configured: true,
        active_job_id: null,
        latest_job: {
          job_id: 'job-e2e-failed-before',
          kind: 'report',
          state: 'failed',
          stage_message: '上次抓取中途退出',
          created_at: '2026-11-18T00:00:00Z',
          updated_at: '2026-11-18T00:00:00Z',
          exam_keyword: null,
          confirm_total_scores: false,
          error_code: 'K12100_BROWSER_FAILED',
          error_message: '浏览器下载分析报告中断，可重新点击同步继续下载剩余场次。',
          result: null,
          report_result: null,
        },
        recommended_cli_command: 'uv run python scripts/k12100_sync.py collect --env development',
      }),
    }),
  )
  await page.route('**/api/school-exams/k12100-sync/report-jobs', route =>
    route.fulfill({
      status: 202,
      contentType: 'application/json',
      body: JSON.stringify({
        job_id: 'job-e2e-skip-all',
        kind: 'report',
        state: 'queued',
        stage_message: '任务已创建，准备检查首页已同步场次…',
        created_at: '2026-11-18T00:01:00Z',
        updated_at: '2026-11-18T00:01:00Z',
        exam_keyword: null,
        confirm_total_scores: false,
        error_code: null,
        error_message: null,
        result: null,
        report_result: null,
      }),
    }),
  )
  await page.route('**/api/school-exams/k12100-sync/jobs/job-e2e-skip-all', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        job_id: 'job-e2e-skip-all',
        kind: 'report',
        state: 'completed',
        stage_message: '首页共 1 场考试，全部已有同步报告，本次无需重复下载。',
        created_at: '2026-11-18T00:01:00Z',
        updated_at: '2026-11-18T00:01:03Z',
        exam_keyword: null,
        confirm_total_scores: false,
        error_code: null,
        error_message: null,
        result: null,
        report_result: {
          home_exams: [
            {
              external_exam_id: 'E-PERSIST-1',
              exam_name: '虚构测试数据 · 九年级上期中',
              exam_date: '2026-11-12',
              grade: '九年级',
              academic_year: '2026-2027',
              exam_type: '期中',
              already_synced: true,
            },
          ],
          reports: [],
          subject_actions: [],
          totals: {
            home_exams: 1,
            skipped_existing: 1,
            downloaded: 0,
            reports_registered: 0,
            created_exams: 0,
            updated_exams: 0,
            filled_exams: 0,
            unchanged_exams: 0,
            locked_conflicts: 0,
            identity_conflicts: 0,
            awaiting_exam_date: 0,
            ambiguous_exams: 0,
            drafts_created: 0,
            drafts_updated: 0,
            auto_mapped: 0,
            cards_created: 0,
            cards_synced: 0,
            failures: 0,
          },
          failures: [],
          knowledge_evidence_created: 0,
        },
      }),
    }),
  )

  await enterAdminSpace(page)
  await adminNavTab(page, /学校考试/).click()
  const enterBtn = page.getByRole('button', { name: '提交考试信息' }).first()
  const titleInput = page.getByLabel('考试名称')
  await expect(enterBtn.or(titleInput)).toBeVisible()
  if (await enterBtn.isVisible()) {
    await enterBtn.click()
  } else {
    await titleInput.fill('同步入口占位校考（虚构测试数据）')
    await page.getByRole('button', { name: /提交考试信息并建档|暂存全科档案/ }).click()
  }
  await page.getByRole('button', { name: /3\. 全科校考同步/ }).click()
  const sync = page.getByRole('region', { name: '全科校考同步中心' })
  await expect(sync).toBeVisible()
  await sync.getByRole('button', { name: /^k12100 报告同步/ }).click()

  // 前期同步数据在任务曾经失败时仍从数据库持久展示，并展示同步前完整性预检与全科/各科排名+最高分
  await expect(sync).toContainText('已全部完整同步')
  const persistedPanel = sync.getByLabel('已同步的 k12100 报告与档案')
  await expect(persistedPanel).toContainText('虚构测试数据 · 九年级上期中分析报告册')
  await expect(persistedPanel).toContainText('总分班最高：205')
  await expect(persistedPanel).toContainText('总分年最高：216')
  await expect(persistedPanel).toContainText('班排 #5 · 年排 #42 · 班最高 98 · 年最高 100')
  await expect(persistedPanel).toContainText('数学')
  await expect(persistedPanel).toContainText('语文')

  // 二次点击同步且全部跳过（downloaded=0）后，前期同步数据继续保留
  await sync.getByRole('button', { name: '从 k12100 下载总分报告并同步' }).click()
  await expect(sync).toContainText('均已有同步报告并自动跳过下载', { timeout: 8000 })
  await expect(persistedPanel).toContainText('虚构测试数据 · 九年级上期中分析报告册')
  await expect(persistedPanel).toContainText('待核对 14 / 已确认 0 题 · 附件 2 份')

  // 确认数学总分后，仅数学更新（不连带确认语文）
  await persistedPanel.getByRole('button', { name: '核对总分 →' }).first().click()
  await sync.getByLabel('我已对照成绩单人工核对').check()
  await sync.getByRole('button', { name: '确认并锁定总分' }).click()
  await expect(sync).toContainText('总分已人工锁定', { timeout: 8000 })
  await sync.getByRole('button', { name: /^k12100 报告同步/ }).click()
  await expect(persistedPanel.locator('.exam-sync-persisted-subject').nth(0)).toContainText('已核对')
  await expect(persistedPanel.locator('.exam-sync-persisted-subject').nth(1)).toContainText('待核对')

  const noOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
  expect(noOverflow).toBe(true)

  await page.evaluate(() =>
    Promise.allSettled(Array.from(document.getAnimations()).map(animation => animation.finished)),
  )
  const axe = await new AxeBuilder({ page })
    .include('.exam-sync-center')
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze()
  expect(axe.violations).toEqual([])

  // 从数学视角跨科点击语文“打开档案”，应自动切换顶部学科并打开该语文档案
  await persistedPanel.getByRole('button', { name: '打开档案' }).nth(1).click()
  await expect(page.getByText('虚构测试数据 · 九年级上期中（语文）').first()).toBeVisible({ timeout: 8000 })
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})


test('J10c 离线采集包回退：本机不可用、默认待核对与锁定总分冲突提示', async ({ page }) => {
  const created = await page.request.post('/api/school-exams', {
    headers: { Authorization: `Bearer ${ADMIN_TOKEN}` },
    data: {
      subject: 'math',
      title: '虚构测试数据 · 离线回退锁定冲突 UI',
      exam_date: '2025-10-30',
      earned_points: 88,
      max_points: 100,
      confirmed_by_user: true,
      school_name: '虚构测试数据实验学校',
      grade: '九年级',
      exam_type: 'midterm',
      academic_year: '2025-2026',
      term: 'first',
      series_title: '虚构测试数据 期中考试',
    },
  })
  expect(created.status()).toBe(201)
  const examId = ((await created.json()) as { id: string }).id
  let bundleBody: Record<string, unknown> | null = null

  await page.route('**/api/school-exams/sync-center*', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        source: {
          environment: 'development',
          directory: '/tmp/pageboy-test-home/development/school-exams/inbox',
          directory_display: '$PAGEBOY_HOME/development/school-exams/inbox',
          real_source_configured: false,
          source_kind: 'local_inbox',
          ready: true,
          source_code: 'SOURCE_NOT_CONFIGURED',
          message: '未配置真实授权学校试卷来源。',
          supported_formats: ['PDF', 'DOCX', 'PNG', 'JPG/JPEG'],
          max_file_bytes: 36700160,
        },
        latest_scan: null,
        counts: { total: 1, needs_review: 0, matched: 0, imported: 1, rejected: 0 },
        papers: [
          {
            id: 'paper-offline-1',
            filename: '虚构测试数据_离线回退.docx',
            sha256: 'e'.repeat(64),
            media_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            byte_size: 4096,
            source_kind: 'local_scan',
            source_name: 'inbox',
            source_ref: 'inbox/虚构测试数据_离线回退.docx',
            header: {
              subject: 'math',
              academic_year: '2025-2026',
              grade: '9',
              exam_type: 'midterm',
              exam_type_label: '期中',
              exam_date: '2025-10-30',
              confidence: 'high',
              complete: true,
              fields: {},
              text_excerpt: '虚构测试数据',
              warnings: [],
            },
            status: 'imported',
            match_state: 'EXACT_MATCH',
            candidates: [],
            school_exam_id: examId,
            exam: {
              id: examId,
              title: '虚构测试数据 · 离线回退锁定冲突 UI',
              subject: 'math',
              exam_date: '2025-10-30',
              confirmed_by_user: true,
            },
            error_code: null,
            imported_at: '2026-11-15T00:00:00Z',
            created_at: '2026-11-15T00:00:00Z',
            updated_at: '2026-11-15T00:00:00Z',
          },
        ],
      }),
    }),
  )
  await page.route('**/api/school-exams/k12100-sync/status', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        environment: 'development',
        mode: 'isolated_import_only',
        can_run_local: false,
        is_isolated: true,
        browser_ready: false,
        node_available: false,
        playwright_available: false,
        unavailable_code: 'K12100_LOCAL_RUNNER_UNAVAILABLE',
        unavailable_reason: '当前后端运行在安全隔离容器内，请使用离线采集包。',
        credentials: {
          status: 'missing',
          username_masked: null,
          deepseek_configured: false,
          deepseek_masked: null,
          message: '隔离环境不读取凭据',
        },
        deepseek_configured: false,
        active_job_id: null,
        latest_job: null,
        recommended_cli_command: 'uv run python scripts/k12100_sync.py collect --env development',
      }),
    }),
  )
  await page.route(`**/api/school-exams/${examId}/ranks`, route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        exam_id: examId,
        ranks: [],
        missing_scopes: ['class', 'grade', 'school', 'region'],
        disclaimer: '本人排名仅为平台来源快照，不进入知识点能力画像，也不预测中考成绩。',
      }),
    }),
  )
  await page.route('**/api/school-exams/k12100-sync/import-bundle', async route => {
    bundleBody = route.request().postDataJSON() as Record<string, unknown>
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        source_exam_title: '虚构测试数据 期中考试',
        source_exam_date: '2025-10-30',
        subjects: [
          {
            subject: 'math',
            subject_label: '数学',
            exam_id: examId,
            exam_title: '虚构测试数据 · 离线回退锁定冲突 UI',
            exam_date: '2025-10-30',
            earned_points: 72,
            max_points: 100,
            confirmed_by_user: true,
            score_status: 'locked_conflict',
            stem_mode: 'pdf_local_regex',
            parser_mode_used: 'local_rules',
            attachments_uploaded: 0,
            drafts_created: 1,
            skipped_labels: [],
            warning: '库中已人工锁定总分 88/100 分，与平台候选 72/100 分不同；按锁分红线保留原值未覆写。',
            match_state: 'EXACT_MATCH',
            ranks_created: 0,
            rank_issues: [{ scope: 'class', code: 'RANK_VALUE_INVALID' }],
          },
        ],
        totals: {
          subjects_processed: 1,
          subjects_blocked: 0,
          created_exams: 0,
          confirmed_now: 0,
          locked_conflicts: 1,
          attachments_uploaded: 0,
          drafts_created: 1,
          ranks_created: 0,
        },
        knowledge_evidence_created: 0,
      }),
    })
  })

  await enterAdminSpace(page)
  await adminNavTab(page, /学校考试/).click()
  const enterBtn = page.getByRole('button', { name: '提交考试信息' }).first()
  const titleInput = page.getByLabel('考试名称')
  await expect(enterBtn.or(titleInput)).toBeVisible()
  if (await enterBtn.isVisible()) {
    await enterBtn.click()
  } else {
    await titleInput.fill('同步入口占位校考（虚构测试数据）')
    await page.getByRole('button', { name: /提交考试信息并建档|暂存全科档案/ }).click()
  }
  await page.getByRole('button', { name: /3\. 全科校考同步/ }).click()
  const sync = page.getByRole('region', { name: '全科校考同步中心' })
  await expect(sync).toBeVisible()
  await expect(sync).toContainText('虚构测试数据_离线回退.docx')
  await sync.getByRole('button', { name: /^k12100 报告同步/ }).click()
  await expect(sync).toContainText('本机直连不可用')
  await sync.getByRole('button', { name: '高级设置与离线包' }).click()
  await sync.locator('input[type="file"]').setInputFiles({
    name: 'mock_k12100_offline_bundle.json',
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify({
      exams: [
        {
          examName: '虚构测试数据 期中考试',
          examDate: '2025-10-30',
          subjects: [{ subjectName: '数学', score: 72, fullScore: 100, smallQuestions: [] }],
        },
      ],
    }), 'utf-8'),
  })
  await expect(sync).toContainText('库中已人工锁定总分 88/100 分')
  await expect(sync).toContainText('保留原值未覆写')
  expect(bundleBody).not.toBeNull()
  expect(bundleBody?.confirm_total_scores).toBe(false)
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})

/* ---------- J10 方案 A 错题工作台 + 管理端 AI 错因三选一 + Level 2 闭环 ---------- */

test('J10 学生端方案 A 错题工作台与管理端 AI 错因诊断三选一闭环', async ({ page }) => {
  // 1. 学生端练习页方案 2 错题卡显示错答与正解具体内容、统一称呼「我的书童」并回放 J2 对话
  await enterSpace(page)
  await expect(page.getByRole('region', { name: '智能综合练习编排' })).toBeVisible()
  await page.getByRole('tab', { name: /近期错题回顾/ }).click()
  const reviewRegion = page.getByRole('region', { name: '近期错题与引导复习' })
  await expect(reviewRegion).toBeVisible()
  await expect(reviewRegion).toContainText('错答：乙')
  await expect(reviewRegion).toContainText('正解：甲')
  // J3 错题在最前已被默认选中，点击另一条「继续对话」即打开 J2 保留多轮思考的错题
  await reviewRegion.getByRole('button', { name: /继续对话/ }).first().click()
  await expect(reviewRegion).toContainText('我先看清题干里的实数条件')

  // 2. 管理端「错题诊断」方案 A（汇总信息卡 + 三步锁步流）：选错题 -> 对话回放与 AI 剖析 -> 3 列方案选定
  await enterAdminSpace(page)
  await adminNavTab(page, /错题诊断/).click()
  const diag = page.getByRole('region', { name: '错题 AI 深度诊断工作台' })
  await expect(diag).toBeVisible()
  await expect(diag.getByRole('region', { name: '错题诊断工作台总览' })).toBeVisible()

  await diag.getByRole('button', { name: /对话 3 轮/ }).click()
  await expect(diag).toContainText('我先看清题干里的实数条件')

  await diag.getByRole('button', { name: 'AI 分析真正错因' }).click()
  await expect(diag).toContainText('学生在审题阶段忽略了题干的限定条件')
  await diag.getByRole('button', { name: /下一步：从 3 个解决对策中拍板/ }).click()

  await diag.getByRole('radio', { name: /选项逐项反代检验训练/ }).click()
  await diag.getByPlaceholder(/今晚先用红笔/).fill('先代回原题干验证一遍再提交')
  await diag.getByRole('button', { name: /确认采用此方案/ }).click()
  await expect(diag).toContainText('当前已采纳：选项逐项反代检验训练')

  // 3. 学生端重新进入「近期错题回顾」工作台，看到 Level 2 改进对策并可一键跳转定向练一轮
  await enterSpace(page)
  await page.getByRole('tab', { name: /近期错题回顾/ }).click()
  const reviewRegionAfter = page.getByRole('region', { name: '近期错题与引导复习' })
  await reviewRegionAfter.getByRole('button', { name: /继续对话/ }).first().click()
  const adoptedBox = page.getByLabel('家长或老师选定的改进对策')
  await expect(adoptedBox).toBeVisible()
  await expect(adoptedBox).toContainText('选项逐项反代检验训练')
  await expect(adoptedBox).toContainText('先代回原题干验证一遍再提交')

  await adoptedBox.getByRole('button', { name: /练一轮/ }).click()
  await expect(page.getByRole('region', { name: '智能综合练习编排' })).toBeVisible()
  await expect(page.getByRole('region', { name: '智能综合练习编排' })).toContainText('已锁定知识点定向突破')
})

/* ---------- J11 知识点双游戏（知识合成工坊 & 迷雾科技树探险）与管理端基础管控联动 ---------- */

test('J11 知识点双游戏闯关体验与管理端启停/护盾/进度重置联动', async ({ page }) => {
  await enterSpace(page)
  await navTab(page, /知识点展示/).click()

  const section = page.getByRole('region', { name: '知识点关系图谱展示' })
  await expect(section).toBeVisible()

  // 1. 游戏一：知识合成工坊（点击干扰卡扣护盾，点击 3 张合法卡牌完成合成爆卡）
  await section.getByRole('button', { name: /知识合成工坊/ }).click()
  const alchemyStage = page.getByRole('region', { name: '知识合成工坊操作舞台' })
  await expect(alchemyStage).toBeVisible()
  expect(await alchemyStage.innerText()).not.toContain('math_cand.')

  await alchemyStage.locator('button.clean-card.trap-card').click()
  await expect(section.locator('.game-inline-feedback.warn')).toContainText('误触干扰陷阱')

  const validCards = alchemyStage.locator('button.clean-card:not(.trap-card)')
  const cardCount = await validCards.count()
  for (let i = 0; i < cardCount; i += 1) {
    const btn = validCards.nth(i)
    if (await btn.isEnabled()) {
      await btn.click()
    }
  }
  await expect(alchemyStage.locator('.ssr-reveal-stage')).toContainText('完美合成')
  await expect(alchemyStage.getByRole('button', { name: /趁热做专项练习巩固/ })).toBeVisible()

  // 2. 游戏二：迷雾科技树探险（三连斩破甲清零 BOSS 1000 HP 护甲并掉落避坑秘籍宝箱）
  await section.getByRole('button', { name: /迷雾科技树探险/ }).click()
  const expStage = page.getByRole('region', { name: '迷雾科技树探险棋盘' })
  await expect(expStage).toBeVisible()
  await expect(expStage).toContainText('1000 / 1000')

  for (let slash = 1; slash <= 3; slash += 1) {
    const prevProgress = await expStage.locator('.slash-progress-tag').innerText()
    const opts = expStage.locator('button.airy-opt-btn')
    const optCount = await opts.count()
    for (let j = 0; j < optCount; j += 1) {
      await opts.nth(j).click()
      if ((await expStage.locator('.ssr-reveal-stage').count()) > 0) break
      const curProgress = await expStage.locator('.slash-progress-tag').innerText()
      if (curProgress !== prevProgress) break
    }
  }
  await expect(expStage.locator('.ssr-reveal-stage')).toContainText('护甲已清零')
  await expect(expStage).toContainText('0 / 1000')

  // 3. 管理端：进入「知识点库 -> 闯关游戏管控」，停用合成工坊并将护盾改为 2 颗
  await enterAdminSpace(page)
  await adminNavTab(page, /^知识点库/).click()
  await page.getByRole('tab', { name: /闯关游戏管控/ }).click()
  const ctrl = page.getByRole('region', { name: '闯关游戏基础管控' })
  await expect(ctrl).toBeVisible()

  const toggleAlchemyBtn = ctrl.locator('.control-row', { hasText: '知识合成工坊' }).locator('button.toggle-pill')
  await expect(toggleAlchemyBtn).toContainText('已开启')
  const putPromise1 = page.waitForResponse(
    res => res.url().includes('/api/admin/knowledge/game-config/math') && res.request().method() === 'PUT',
  )
  await toggleAlchemyBtn.click()
  expect((await putPromise1).status()).toBe(200)
  await expect(toggleAlchemyBtn).toContainText('已停用')

  const putPromise2 = page.waitForResponse(
    res => res.url().includes('/api/admin/knowledge/game-config/math') && res.request().method() === 'PUT',
  )
  await ctrl.getByLabel(/每局初始护盾生命数/).selectOption('2')
  expect((await putPromise2).status()).toBe(200)

  // 4. 切回学生端验证：知识合成工坊已隐藏，迷雾探险显示 2 颗护盾
  await enterSpace(page)
  await navTab(page, /知识点展示/).click()
  await expect(page.getByRole('button', { name: /知识合成工坊/ })).toHaveCount(0)
  await page.getByRole('button', { name: /迷雾科技树探险/ }).click()
  await expect(page.getByLabel('当前剩余护盾 2 颗')).toBeVisible()

  // 5. 管理端恢复默认设置并测试重置游戏进度
  await enterAdminSpace(page)
  await adminNavTab(page, /^知识点库/).click()
  await page.getByRole('tab', { name: /闯关游戏管控/ }).click()
  const ctrlRestore = page.getByRole('region', { name: '闯关游戏基础管控' })
  await ctrlRestore.locator('.control-row', { hasText: '知识合成工坊' }).locator('button.toggle-pill').click()
  await ctrlRestore.getByLabel(/每局初始护盾生命数/).selectOption('3')
  const resetPromise = page.waitForResponse(
    res => res.url().includes('/api/admin/knowledge/game-config/math') && res.request().method() === 'PUT',
  )
  await ctrlRestore.getByRole('button', { name: /重置本学科游戏进度/ }).click()
  expect((await resetPromise).status()).toBe(200)
  await expect(ctrlRestore).toContainText('第 1 版')
})

/* ---------- J12 学校考试第三、四阶段右上角科目联动且移除详情页内部科目 Tab ---------- */

test('J12 学校考试第三/四阶段右上角科目切换直接联动内容且无详情页内科目Tab', async ({ page }) => {
  await enterAdminSpace(page)
  const createRes = await page.request.post('/api/school-exams', {
    headers: { Authorization: `Bearer ${ADMIN_TOKEN}` },
    data: {
      subject: 'all',
      title: '全科联动验收考（虚构测试数据）',
      exam_date: '2026-10-15',
      earned_points: 150,
      max_points: 200,
      confirmed_by_user: false,
    },
  })
  expect(createRes.status()).toBe(201)
  const examId = (await createRes.json()).id as string

  const addItemsRes = await page.request.post(`/api/school-exams/${examId}/items`, {
    headers: { Authorization: `Bearer ${ADMIN_TOKEN}` },
    data: {
      items: [
        {
          question_label: '数学·第1题',
          knowledge_id: 'math_cand.num.rational',
          earned_points: 1,
          max_points: 2,
          scoring_origin: 'manual_entry',
          error_category: 'calculation',
        },
        {
          question_label: '语文·第1题',
          knowledge_id: 'chinese_cand.base.contextual_expression',
          earned_points: 0,
          max_points: 2,
          scoring_origin: 'manual_entry',
          error_category: 'reading',
        },
        {
          question_label: '语文·第2题',
          knowledge_id: 'chinese_cand.poetry.appreciation',
          earned_points: 2,
          max_points: 2,
          scoring_origin: 'manual_entry',
        },
      ],
    },
  })
  expect(addItemsRes.status()).toBe(201)

  await adminNavTab(page, /学校考试/).click()
  const examRegion = page.getByRole('region', { name: '学校考试总分' })
  await examRegion.locator('.exam-pick', { hasText: '全科联动验收考' }).click()

  // 进入第三阶段「已核对明细与补录」
  await examRegion.getByRole('tab', { name: /已核对明细与补录/ }).click()
  await expect(examRegion.locator('.exam-sync-subject-tabs')).toHaveCount(0)
  await expect(examRegion).toContainText('已核对逐题得分与考点明细（1）')
  await expect(examRegion).toContainText('第1题')
  await expect(examRegion).not.toContainText('语文·第2题')

  // 点击界面右上方「语文」，保持在第三阶段并显示语文的 2 道明细
  const topSubjects = page.getByRole('group', { name: '科目' })
  await topSubjects.getByRole('button', { name: '语文' }).click()
  await expect(examRegion.getByRole('tab', { name: /已核对明细与补录/ })).toHaveAttribute('aria-selected', 'true')
  await expect(examRegion.locator('.exam-sync-subject-tabs')).toHaveCount(0)
  await expect(examRegion).toContainText('已核对逐题得分与考点明细（2）')
  await expect(examRegion).toContainText('第2题')

  // 进入第四阶段「错误分析与复盘」
  await examRegion.getByRole('tab', { name: /错误分析与复盘/ }).click()
  await expect(examRegion.locator('.exam-sync-subject-tabs')).toHaveCount(0)
  await expect(examRegion).toContainText('1 / 2 题')

  // 点击界面右上方「数学」，保持在第四阶段并切换为数学分析（1 / 1 题）
  await topSubjects.getByRole('button', { name: '数学' }).click()
  await expect(examRegion.getByRole('tab', { name: /错误分析与复盘/ })).toHaveAttribute('aria-selected', 'true')
  await expect(examRegion.locator('.exam-sync-subject-tabs')).toHaveCount(0)
  await expect(examRegion).toContainText('1 / 1 题')

  // 清理测试档案
  const delRes = await page.request.delete(`/api/school-exams/${examId}?confirm=true`, {
    headers: { Authorization: `Bearer ${ADMIN_TOKEN}` },
  })
  expect(delRes.status()).toBe(200)
})
