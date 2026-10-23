/* ST-008 F1：J1–J4 用户旅程验收（全部数据为 globalSetup 种入的虚构测试数据）。
 *
 * 选择器策略：交互用 role / accessible name / 中文文案 / 既有 aria-label，绝不新增 test-id；
 * 少量断言依赖设计器既有结构类（.stem/.reference/figure.reading/.goal-form/.exam-list/li.step）——
 * 无害的标记重构可能需要同步更新这些选择器。
 * 旅程按声明次序串行执行（config workers=1）：
 *   J1 全新库缺证据解释 → J2 复练轮换/自评/听力 → J3 基线→差距→复测判决 → J4 校卷总分。
 * J3 的确定性只依赖种子配比：math.gap 最早创建（evaluation 按 created_at 先发它）且共有
 * ≥6 道未见客观题（10 道：基线 3 + 复测 3 + 余量 4），与 J2 是否先消耗训练题无关。 */
import { test, expect, type Locator, type Page } from '@playwright/test'

const TOKEN = 'test-journey-secret'

/* ---------- helpers ---------- */

async function enterSpace(page: Page): Promise<void> {
  await page.goto('/')
  await page.getByLabel('访问令牌').fill(TOKEN)
  await page.getByRole('button', { name: '进入' }).click()
  await expect(page.getByRole('navigation', { name: '主要视图' })).toBeVisible()
}

function navTab(page: Page, label: RegExp): Locator {
  return page.getByRole('navigation', { name: '主要视图' }).getByRole('button', { name: label })
}

/** 指定知识点的计划行（匹配含该 code.kid 的 li.step）。 */
function stepRow(page: Page, kid: string, root?: Locator): Locator {
  const scope = root ?? page
  return scope.locator('li.step', { has: page.locator('code.kid', { hasText: kid }) })
}

/** 阶段对比列表里的知识点行。 */
function comparisonRow(page: Page, kid: string, root: Locator): Locator {
  return root.locator('li', { has: page.locator('code.kid', { hasText: kid }) })
}

/** 当前题目卡（aria-label="题目" 的 region）。 */
function questionCard(page: Page): Locator {
  return page.getByRole('region', { name: '题目' })
}

/** 诚实文案红线：预测/能力值只允许出现在否定式免责声明里，「提分」绝不出现。 */
async function expectHonestLanguage(page: Page): Promise<void> {
  const text = await page.evaluate(() => document.body.innerText)
  expect(text, '页面不得出现「提分」表述').not.toContain('提分')
  for (const match of text.matchAll(/预测/g)) {
    const before = text.slice(Math.max(0, match.index - 10), match.index)
    expect(before, `「预测」只能出现在否定式免责声明里，实际上下文为「${before}预测」`).toMatch(/不作|不是/)
  }
  for (const match of text.matchAll(/能力值/g)) {
    const before = text.slice(Math.max(0, match.index - 10), match.index)
    expect(before, `「能力值」只能出现在否定表述里，实际上下文为「${before}能力值」`).toMatch(/不作|不是/)
  }
}

/* ---------- J1 首页与缺证据解释 ---------- */

test('J1 首页与缺证据解释：缺证据显示原因而非 0 分，目标经 UI 保存后反映新版本', async ({ page }) => {
  await enterSpace(page)

  const planRegion = page.getByRole('region', { name: '目标与学习计划' })
  await expect(planRegion).toBeVisible()

  // 种子已建立目标 v1：计划加载并展示目标摘要（goal_version）。
  await expect(planRegion.getByText('目标版本 v1')).toBeVisible()
  await expect(planRegion.getByText('每天 15 分钟')).toBeVisible()

  // 全新库：每个已发布知识点各有一行计划。
  for (const kid of ['math.gap', 'math.listen', 'math.ok', 'math.short', 'math.subj']) {
    await expect(stepRow(page, kid, planRegion)).toBeVisible()
  }

  // math.gap 行：INSUFFICIENT_EVIDENCE 徽章 + 后端 reason 原文；绝不出现观察率/0 分框架。
  const gapRow = stepRow(page, 'math.gap', planRegion)
  await expect(gapRow).toContainText('证据不足')
  await expect(gapRow).toContainText('INSUFFICIENT_EVIDENCE')
  await expect(gapRow).toContainText('尚无足够的独立新题证据')
  await expect(gapRow).toContainText('建议：领取未见题诊断')
  await expect(gapRow).not.toContainText('观察作答率')
  await expect(stepRow(page, 'math.ok', planRegion)).toContainText('尚无足够的独立新题证据')

  // 阶段对比摘要：CANNOT_COMPARE —— 「证据不足，无法比较」，绝无能力/涨分结论。
  const summary = page.getByRole('region', { name: '阶段对比摘要' })
  await expect(summary).toContainText('证据不足，无法比较')
  await expect(summary).toContainText('还没有可用于对比的独立验证记录。')
  await expect(summary).toContainText('每个知识点需要至少 3 道独立未见题的基线记录与 3 道复测记录，才能进行可观察对比。')

  // 缺证据绝不能呈现为 0%（90% 等带前导数字的合法百分比除外）/ 0 分。
  const freshText = await page.evaluate(() => document.body.innerText)
  expect(freshText).not.toMatch(/(?<!\d)0%/)
  for (const match of freshText.matchAll(/0\s*分/g)) {
    const before = freshText.slice(Math.max(0, (match.index ?? 0) - 6), match.index ?? 0)
    expect(before, `「0 分」只能出现在否定式说明里，实际上下文为「${before}0 分」`).toMatch(/不显示|不是|不会|绝不/)
  }

  // 目标表单经 UI 打开并保存：首页反映新目标版本。
  await planRegion.getByRole('button', { name: '修改目标' }).click()
  const goalForm = planRegion.locator('.goal-form')
  await expect(goalForm).toBeVisible()
  await planRegion.getByLabel(/科目目标分/).fill('95')
  await planRegion.getByRole('button', { name: '保存目标' }).click()
  await expect(page.getByRole('status')).toContainText('目标已保存（第 2 版）')
  await expect(planRegion.getByText('目标版本 v2')).toBeVisible()

  await expectHonestLanguage(page)
})

/* ---------- J2 复练与轮换 ---------- */

test('J2 复练与轮换：轮换可见、客观判分、主观自评链与听力音频', async ({ page }) => {
  await enterSpace(page)
  await navTab(page, /练习/).click()

  const practice = page.getByRole('region', { name: '练习控制' })
  await expect(practice).toBeVisible()
  await expect(practice).toContainText('复练会在全部已发布题中轮换取题')

  // 取题（不筛选 → 曝光最少且最早的 math.gap 第 1 题）→ 点正确选项 → 提交 → 得分反馈。
  await practice.getByRole('button', { name: '开始练习' }).click()
  let card = questionCard(page)
  await expect(card).toBeVisible()
  await expect(card).toContainText('专项训练 · math.gap')
  const firstStem = await card.locator('p.stem').innerText()
  await card.getByRole('radio', { name: /甲/ }).click()
  await card.getByRole('button', { name: '提交答案' }).click()
  await expect(card.getByText('本题得分 2 / 2')).toBeVisible()
  await expect(card.getByText('评分来源：已审核答案自动比对')).toBeVisible()
  await expect(practice.getByText('本次已练 1 题')).toBeVisible()

  // 轮换可见性：换一题后题干不同（仍为差距题池）。innerText 无自动等待，
  // 须先用否定断言等新题挂载，避免读到旧卡内容。
  await practice.getByRole('button', { name: '换一题（轮换取题）' }).click()
  await expect(card.locator('p.stem')).not.toHaveText(firstStem)
  await expect(card).toContainText('专项训练 · math.gap')
  const secondStem = await card.locator('p.stem').innerText()
  expect(secondStem).not.toBe(firstStem)
  expect(secondStem).toContain('差距题')

  // 知识点筛选 → math.ok：共享阅读材料（group_context）以「阅读材料」区块展示。
  await practice.getByLabel('按知识点').selectOption('math.ok')
  await practice.getByRole('button', { name: '换一题（轮换取题）' }).click()
  card = questionCard(page)
  await expect(card.locator('figure.reading')).toBeVisible()
  await expect(card.locator('figure.reading figcaption')).toHaveText('阅读材料')
  await expect(card.locator('figure.reading blockquote')).toContainText('虚构测试数据：阅读材料文本')
  await expect(card.locator('p.stem')).toContainText('对照阅读题 1')

  // 知识点筛选 → math.short：短答按已审核答案归一化比对得分。
  await practice.getByLabel('按知识点').selectOption('math.short')
  await practice.getByRole('button', { name: '换一题（轮换取题）' }).click()
  card = questionCard(page)
  await expect(card).toContainText('短答题')
  await card.getByLabel('答案').fill('x=1')
  await card.getByRole('button', { name: '提交答案' }).click()
  await expect(card.getByText('本题得分 3 / 3')).toBeVisible()
  await expect(card.getByText('评分来源：已审核答案自动比对')).toBeVisible()

  // 知识点筛选 → math.subj：主观题链（作答 → 参考答案 → 自评 → 已记录，输入消失）。
  await practice.getByLabel('按知识点').selectOption('math.subj')
  await practice.getByRole('button', { name: '换一题（轮换取题）' }).click()
  card = questionCard(page)
  await expect(card).toContainText('主观题')
  await card.getByLabel('解答').fill('虚构测试数据：复练是已见题的巩固，阶段诊断是未见题的独立验证。')
  await card.getByRole('button', { name: '提交答案' }).click()
  await expect(card.getByText('暂未评分，等待自评')).toBeVisible()
  await expect(card.getByText('评分来源：主观题未自动评分')).toBeVisible()
  await expect(card.locator('.reference')).toBeVisible()
  await expect(card.locator('.reference')).toContainText('虚构测试数据：参考解答')
  await card.getByLabel(/对照参考答案，给自己评分/).fill('5')
  await card.getByRole('button', { name: '提交自评' }).click()
  await expect(card.getByText(/自评已记录：5 \/ 6/)).toBeVisible()
  await expect(card.getByText('只可提交一次、不能修改')).toBeVisible()
  await expect(card.getByLabel(/对照参考答案，给自己评分/)).toHaveCount(0)
  await expect(practice.getByText('本次已练 3 题')).toBeVisible()

  // 知识点筛选 → math.listen：听力题渲染音频控件。
  await practice.getByLabel('按知识点').selectOption('math.listen')
  await practice.getByRole('button', { name: '换一题（轮换取题）' }).click()
  card = questionCard(page)
  await expect(card.getByText('听力材料')).toBeVisible()
  await expect(card.locator('audio')).toHaveCount(1)
  await expect(card.locator('audio')).toBeVisible()

  // 作答溯源：判分来源与自评并列可溯源。
  const trace = page.getByRole('region', { name: '作答溯源记录' })
  await expect(trace).toContainText('已审核答案自动比对')
  await expect(trace).toContainText('主观题未自动评分')
  await expect(trace).toContainText('自评 5 / 6')

  await expectHonestLanguage(page)
})

/* ---------- J3 阶段诊断 ---------- */

test('J3 阶段诊断：独立验证纪律、基线→差距、复测判决与免责声明', async ({ page }) => {
  await enterSpace(page)
  await navTab(page, /阶段诊断/).click()

  // 独立验证纪律明示。
  await expect(page.getByText('独立验证纪律')).toBeVisible()
  await expect(page.getByText('不看资料、不查工具、不问他人')).toBeVisible()

  const claimRegion = page.getByRole('region', { name: '领取未见题' })
  await expect(claimRegion).toContainText('「未见题」指你从未曝光过的题')

  // 领取未见题 → 答错（正确为「甲」，点「乙」）×3：evaluation 依次发出 math.gap 未见过题。
  for (let round = 1; round <= 3; round++) {
    await claimRegion.getByRole('button', { name: '领取未见题诊断' }).click()
    const card = questionCard(page)
    await expect(card).toBeVisible()
    await expect(card).toContainText('阶段诊断 · 未见题 · math.gap')
    await card.getByRole('radio', { name: /乙/ }).click()
    await card.getByRole('button', { name: '提交答案' }).click()
    await expect(card.getByText('本题得分 0 / 2')).toBeVisible()
    await expect(card.getByText('符合独立验证条件（首次见题、独立完成），已计入阶段对比。')).toBeVisible()
    const refreshed = page.getByRole('region', { name: '计划刷新结果' })
    await expect(refreshed).toBeVisible()
    await card.getByRole('button', { name: '完成本题' }).click()
    await expect(card).toHaveCount(0)
  }

  // 刷新后的计划：math.gap 变为 KNOWLEDGE_GAP（知识点差距）并展示观察率文本；
  // 证据仍不足的知识点（math.ok）继续显示 INSUFFICIENT_EVIDENCE 原因。
  const refreshed = page.getByRole('region', { name: '计划刷新结果' })
  await expect(refreshed).toContainText('证据不足 → 知识点差距')
  const gapRow = stepRow(page, 'math.gap', refreshed)
  await expect(gapRow).toContainText('知识点差距')
  await expect(gapRow).toContainText('KNOWLEDGE_GAP')
  await expect(gapRow).toContainText('观察作答率')
  await expect(gapRow).toContainText('规划阈值 90%')
  await expect(stepRow(page, 'math.ok', refreshed)).toContainText('尚无足够的独立新题证据')

  // 复测：再领 3 道未见题，全部答对（点「甲」）。
  for (let round = 1; round <= 3; round++) {
    await claimRegion.getByRole('button', { name: '领取未见题诊断' }).click()
    const card = questionCard(page)
    await expect(card).toBeVisible()
    await expect(card).toContainText('阶段诊断 · 未见题 · math.gap')
    await card.getByRole('radio', { name: /甲/ }).click()
    await card.getByRole('button', { name: '提交答案' }).click()
    await expect(card.getByText('本题得分 2 / 2')).toBeVisible()
    await expect(card.getByText('符合独立验证条件（首次见题、独立完成），已计入阶段对比。')).toBeVisible()
    await card.getByRole('button', { name: '完成本题' }).click()
    await expect(card).toHaveCount(0)
  }

  // 阶段对比判决：可观察对比 + 每知识点 improved 判决 + 强制免责声明。
  const verdict = page.getByRole('region', { name: '阶段对比判决' })
  await verdict.getByRole('button', { name: '刷新' }).click()
  await expect(verdict).toContainText('可观察对比：基线 → 复测')
  const row = comparisonRow(page, 'math.gap', verdict)
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
  await enterSpace(page)
  await navTab(page, /阶段诊断/).click()

  const examRegion = page.getByRole('region', { name: '学校考试总分' })
  await expect(examRegion).toContainText('总分不产生考点证据')
  await expect(examRegion).toContainText('也不折算成知识点表现')

  // 录入一个 earned < max 的学校总分（经 UI 表单）。
  await examRegion.getByLabel('考试名称').fill('虚构测试数据：学校月考')
  await examRegion.getByLabel('考试日期').fill('2026-10-20')
  await examRegion.getByLabel('获得分数').fill('85')
  await examRegion.getByLabel('考试满分').fill('100')
  await examRegion.getByRole('button', { name: '记录已核对总分' }).click()

  await expect(page.getByRole('status')).toContainText('学校考试已记录')
  await expect(page.getByRole('status')).toContainText('总分不产生考点证据')

  // 总分列表展示刚录入的条目。
  await expect(examRegion.locator('.exam-list')).toContainText('虚构测试数据：学校月考')
  await expect(examRegion.locator('.exam-list')).toContainText('2026-10-20')
  await expect(examRegion.locator('.exam-list')).toContainText('85 / 100')
  await expect(examRegion.locator('.exam-list')).toContainText('已核对')

  await expectHonestLanguage(page)
})
