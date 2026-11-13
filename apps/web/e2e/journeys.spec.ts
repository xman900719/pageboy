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

test('J4 校卷总分：录入成功、明示「总分不产生考点证据」并列出条目', async ({ page }) => {
  await enterAdminSpace(page)
  await adminNavTab(page, /学校考试/).click()

  const examRegion = page.getByRole('region', { name: '学校考试总分' })
  await expect(examRegion).toContainText('总分不产生考点证据')
  await expect(examRegion).toContainText('也不折算成知识点表现')

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

  await expectHonestLanguage(page)
})

/* ---------- J5 审核台：录入真题全闭环 ---------- */

test('J5 审核台：题源登记→来源人工审核→附件解析→确认导入→草稿审核→发布（人工门禁全程如实）', async ({ page }) => {
  await enterAdminSpace(page)
  await adminNavTab(page, /题库审核台/).click()

  const ledger = page.getByRole('region', { name: '题源台账' })
  const review = page.getByRole('region', { name: '来源人工审核' })
  const attachments = page.getByRole('region', { name: '附件与解析' })
  const versions = page.getByRole('region', { name: '题目草稿与发布' })

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
  await expect(newRow.locator('.chip.wait')).toContainText('未审核')

  await attachments.getByRole('button', { name: '解析' }).click()
  await expect(page.getByRole('status')).toContainText('请逐题人工录入')
  await attachments.getByRole('button', { name: '逐题录入并确认导入' }).click()
  const entryForm = attachments.locator('.confirm-import')
  await entryForm.getByLabel('题干').fill('虚构测试数据：J5 审核台听力题——听录音选出提到的词。')
  await entryForm.getByLabel('选项 A 内容').fill('甲')
  await entryForm.getByLabel('选项 B 内容').fill('乙')
  await entryForm.getByLabel('正确选项').selectOption({ label: 'A · 甲' })
  await entryForm.getByLabel('知识点 ID（至少 1 个，逗号或空格分隔）').fill('math.listen')
  await entryForm.getByRole('button', { name: '加入待导入列表' }).click()
  await expect(entryForm.getByText('已录入 1 题')).toBeVisible()
  await expect(entryForm.getByRole('button', { name: '确认导入 1 题' })).toBeDisabled()
  await entryForm.getByLabel(/我已逐题人工核对/).check()
  await entryForm.getByRole('button', { name: '确认导入 1 题' }).click()
  await expect(page.getByRole('status')).toContainText('已确认导入 1 题，草稿待人工审核')
  await expect(attachments.getByText('已导入 1 题，等待在下方逐题人工审核。')).toBeVisible()

  const draftRow = versions.locator('li.version-row', { hasText: 'J5 审核台听力题' })
  await expect(draftRow.locator('.badge.qstatus-draft')).toBeVisible()
  await expect(draftRow).toContainText('含媒体附件')
  await draftRow.getByRole('button', { name: '人工审核通过' }).click()
  await expect(page.getByRole('status')).toContainText('已标记为人工审核')
  await expect(draftRow.locator('.badge.qstatus-reviewed')).toBeVisible()
  await expect(draftRow.getByRole('button', { name: '发布' })).toBeDisabled()
  await expect(draftRow).toContainText('题源未通过人工审核（或版权未核实），发布暂不可用')

  await review.getByRole('button', { name: '提交人工审核' }).click()
  await expect(page.getByRole('status')).toContainText('题源标记为已审核')
  await draftRow.getByRole('button', { name: '发布' }).click()
  await expect(page.getByRole('status')).toContainText('题目已发布，现在会进入练习与诊断的取题池。')
  await expect(draftRow.locator('.badge.qstatus-published')).toBeVisible()
  await expect(newRow.locator('.chip.good')).toContainText('已人工审核')

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

/* ---------- J8 管理端知识点审核台：同步→课标草稿→批量审核→发布 ---------- */

test('J8 管理端知识点审核台：同步候选→按课标生成审核依据草稿→批量审核→发布版本快照', async ({ page }) => {
  await enterAdminSpace(page)
  await adminNavTab(page, /知识点审核台/).click()

  await expect(page.getByText('数学权威知识点库审核工作台')).toBeVisible()
  await page.getByRole('button', { name: '同步候选入库 (待审)' }).click()
  await expect(page.locator('.status-banner')).toContainText('待审核: 48')

  await page.getByLabel('审核人 ID (必填):').fill('owner_e2e_reviewer')
  await page.getByRole('button', { name: '按课标生成审核依据草稿' }).click()
  await expect(page.getByLabel('审核依据与意见 (必填):')).not.toHaveValue('')

  await page.getByRole('button', { name: /按课标批量审核待审 \(48\)/ }).click()
  await expect(page.locator('.status-banner')).toContainText('待审核: 0')
  await expect(page.locator('.status-banner')).toContainText('已通过: 48')

  await page.getByRole('button', { name: /版本发布与快照/ }).click()
  await page.getByRole('button', { name: '发布正式版本快照' }).click()
  await expect(page.locator('.releases-list')).toContainText('math-v2022.1.0')
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
