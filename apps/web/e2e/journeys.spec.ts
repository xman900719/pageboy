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

/** 指定考点的计划行（匹配含该 .step-topic 的 li.step）。 */
function stepRow(page: Page, topic: string, root?: Locator): Locator {
  const scope = root ?? page
  return scope.locator('li.step', { has: page.locator('.step-topic', { hasText: topic }) })
}

/** 阶段对比列表里的考点行。 */
function comparisonRow(page: Page, topic: string, root: Locator): Locator {
  return root.locator('li', { has: page.locator('.comp-topic', { hasText: topic }) })
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

  // 全新库：每个已发布考点各有一行计划。
  for (const topic of ['基础运算与薄弱短板', '听力理解与应用', '核心知识达标模块', '代数综合与简答计算', '几何综合与主观探究']) {
    await expect(stepRow(page, topic, planRegion)).toBeVisible()
  }

  // math.gap 行：INSUFFICIENT_EVIDENCE 徽章 + 后端 reason 原文；绝不出现观察率/0 分框架。
  const gapRow = stepRow(page, '基础运算与薄弱短板', planRegion)
  await expect(gapRow).toContainText('证据不足')
  await expect(gapRow).toContainText('INSUFFICIENT_EVIDENCE')
  await expect(gapRow).toContainText('尚无足够的独立新题证据')
  await expect(gapRow).not.toContainText('观察作答率')
  await expect(stepRow(page, '核心知识达标模块', planRegion)).toContainText('尚无足够的独立新题证据')

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

test('J2 复练与轮换：轮换可见、客观判分、作答溯源', async ({ page }) => {
  await enterSpace(page)
  await navTab(page, /练习/).click()

  const practice = page.getByRole('region', { name: '练习控制' })
  await expect(practice).toBeVisible()
  await expect(practice).toContainText('复练会在全部已发布题中轮换取题')

  // 取题（不筛选 → 曝光最少且最早的 math.gap 第 1 题）→ 点正确选项 → 提交 → 得分反馈。
  await practice.getByRole('button', { name: '开始练习' }).click()
  const card = questionCard(page)
  await expect(card).toBeVisible()
  await expect(card).toContainText('专项训练')
  const firstStem = await card.locator('p.stem').innerText()
  await card.getByRole('radio', { name: /甲/ }).click()
  await card.getByRole('button', { name: '提交答案' }).click()
  await expect(card.getByText('本题得分 2 / 2')).toBeVisible()
  await expect(card.getByText('评分来源：已审核答案自动比对')).toBeVisible()
  await expect(practice.getByText('本次已练 1 题')).toBeVisible()

  // 轮换可见性：换一题后题干不同（仍为差距题池）。
  await practice.getByRole('button', { name: '换一题（轮换取题）' }).click()
  await expect(card.locator('p.stem')).not.toHaveText(firstStem)
  await expect(card).toContainText('专项训练')
  const secondStem = await card.locator('p.stem').innerText()
  expect(secondStem).not.toBe(firstStem)
  expect(secondStem).toContain('差距题')
  await card.getByRole('radio', { name: /甲/ }).click()
  await card.getByRole('button', { name: '提交答案' }).click()
  await expect(card.getByText('本题得分 2 / 2')).toBeVisible()
  await expect(practice.getByText('本次已练 2 题')).toBeVisible()

  // 作答溯源：判分来源与自评并列可溯源。
  const trace = page.getByRole('region', { name: '作答溯源记录' })
  await expect(trace).toContainText('已审核答案自动比对')

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
    await expect(card).toContainText('阶段诊断 · 未见题')
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
  const gapRow = stepRow(page, '基础运算与薄弱短板', refreshed)
  await expect(gapRow).toContainText('知识点差距')
  await expect(gapRow).toContainText('KNOWLEDGE_GAP')
  await expect(gapRow).toContainText('观察作答率')
  await expect(gapRow).toContainText('规划阈值 90%')
  await expect(stepRow(page, '核心知识达标模块', refreshed)).toContainText('尚无足够的独立新题证据')

  // 复测：再领 3 道未见题，全部答对（点「甲」）。
  for (let round = 1; round <= 3; round++) {
    await claimRegion.getByRole('button', { name: '领取未见题诊断' }).click()
    const card = questionCard(page)
    await expect(card).toBeVisible()
    await expect(card).toContainText('阶段诊断 · 未见题')
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
  const row = comparisonRow(page, '基础运算与薄弱短板', verdict)
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

/* ---------- J5 审核台：录入真题全闭环 ---------- */

test('J5 审核台：题源登记→来源人工审核→附件解析→确认导入→草稿审核→发布（人工门禁全程如实）', async ({ page }) => {
  await enterAdminSpace(page)
  await adminNavTab(page, /题库审核台/).click()

  const ledger = page.getByRole('region', { name: '题源台账' })
  const review = page.getByRole('region', { name: '来源人工审核' })
  const attachments = page.getByRole('region', { name: '附件与解析' })
  const versions = page.getByRole('region', { name: '题目草稿与发布' })

  // ① 新建题源：登记后台账出现新行并选中（新建后 chip 为「未审核」）。
  await ledger.getByLabel('题源标题').fill('虚构测试数据：J5 审核台旅程题源')
  await ledger.getByLabel('版权状态').selectOption('personal_use_reviewed')
  await ledger.getByRole('button', { name: '新建题源' }).click()
  await expect(page.getByRole('status')).toContainText('题源已登记')
  const newRow = ledger.locator('li.source-item', { hasText: 'J5 审核台旅程题源' })
  await expect(newRow).toContainText('未审核')
  await expect(review.getByRole('heading', { name: '来源人工审核' })).toBeVisible()

  // ② 来源人工审核：未勾选确认时按钮禁用（人工门禁反例）；勾选后提交，题源变已审核。
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

  // ③ 上传合成音频（运行时构造，无真实内容）：来源如实复位为「未审核」并警示。
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

  // ④ 解析（音频无转写 → 需人工录入）→ 逐题录入 → 显式勾选 → 确认导入。
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

  // ⑤ 草稿出现（含媒体附件标记）→ 人工审核通过 → 来源未审核时发布禁用并说明原因（如实门禁反例）。
  const draftRow = versions.locator('li.version-row', { hasText: 'J5 审核台听力题' })
  await expect(draftRow.locator('.badge.qstatus-draft')).toBeVisible()
  await expect(draftRow).toContainText('含媒体附件')
  await draftRow.getByRole('button', { name: '人工审核通过' }).click()
  await expect(page.getByRole('status')).toContainText('已标记为人工审核')
  await expect(draftRow.locator('.badge.qstatus-reviewed')).toBeVisible()
  await expect(draftRow.getByRole('button', { name: '发布' })).toBeDisabled()
  await expect(draftRow).toContainText('题源未通过人工审核（或版权未核实），发布暂不可用')

  // ⑥ 重新完成来源人工审核 → 发布可用 → 发布成功进入取题池。
  await review.getByRole('button', { name: '提交人工审核' }).click()
  await expect(page.getByRole('status')).toContainText('题源标记为已审核')
  await draftRow.getByRole('button', { name: '发布' }).click()
  await expect(page.getByRole('status')).toContainText('题目已发布，现在会进入练习与诊断的取题池。')
  await expect(draftRow.locator('.badge.qstatus-published')).toBeVisible()
  await expect(newRow.locator('.chip.good')).toContainText('已人工审核')

  await expectHonestLanguage(page)
})

/* ---------- J6 本机记住令牌（PWA 冷启动免输入） ---------- */

test('J6 本机记住令牌：冷启动免输入、退出即清除、失效令牌如实拦截', async ({ page }) => {
  await page.goto('/')
  // 默认不预勾选，杜绝未经用户主动授权的隐式持久化
  await expect(page.getByLabel(/在本机记住令牌/)).not.toBeChecked()

  // 用户主动勾选「在本机记住令牌」进入：令牌写入本机存储（显式选配，默认仅内存）。
  await page.getByLabel('访问令牌').fill(STUDENT_TOKEN)
  await page.getByLabel(/在本机记住令牌/).check()
  await page.getByRole('button', { name: '进入' }).click()
  await expect(page.getByRole('navigation', { name: '主要视图' })).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('shutong.student_token'))).toBe(STUDENT_TOKEN)

  // 冷启动（模拟 PWA 从主屏幕图标重开）：免输入直达首页，令牌门不出现。
  await page.reload()
  await expect(page.getByRole('navigation', { name: '主要视图' })).toBeVisible()
  await expect(page.getByLabel('访问令牌')).toHaveCount(0)
  await expect(page.getByRole('status')).toContainText('已用本机记住的令牌自动进入')
  await expect(page.getByRole('region', { name: '目标与学习计划' })).toBeVisible()

  // 退出 = 完整登出：本机存储一并清除，回到令牌门。
  await page.getByRole('button', { name: '退出' }).click()
  await expect(page.getByLabel('访问令牌')).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('shutong.student_token'))).toBeNull()
  // 登出后重回令牌门：勾选框保持默认未勾选
  await expect(page.getByLabel(/在本机记住令牌/)).not.toBeChecked()

  // 反例：本机残留失效令牌 → verify 失败即如实清除，绝不放行。
  await page.evaluate(t => localStorage.setItem('shutong.student_token', t), 'stale-token')
  await page.reload()
  await expect(page.getByLabel('访问令牌')).toBeVisible()
  await expect.poll(() => page.evaluate(() => localStorage.getItem('shutong.student_token'))).toBeNull()

  // 清除后令牌门照常可用：未主动勾选进入 → 绝不持久化到 localStorage
  await page.getByLabel('访问令牌').fill(STUDENT_TOKEN)
  await page.getByRole('button', { name: '进入' }).click()
  await expect(page.getByRole('navigation', { name: '主要视图' })).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('shutong.student_token'))).toBeNull()
})

test('J6b 凭据门禁安全整改：废弃旧键清理、未主动勾选不持久化、管理端隐藏记住选项', async ({ page }) => {
  // 1. 学生端：注入废弃的旧版全局凭据 shutong.token，访问后自动清理
  await page.goto('/')
  await page.evaluate(() => localStorage.setItem('shutong.token', 'legacy-admin-token'))
  await page.reload()
  await expect(page.getByLabel('访问令牌')).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('shutong.token'))).toBeNull()

  // 2. 学生端默认不预勾选，不勾选直接进入不持久化
  await expect(page.getByLabel(/在本机记住令牌/)).not.toBeChecked()
  await page.getByLabel('访问令牌').fill(STUDENT_TOKEN)
  await page.getByRole('button', { name: '进入' }).click()
  await expect(page.getByRole('navigation', { name: '主要视图' })).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('shutong.student_token'))).toBeNull()
  await page.getByRole('button', { name: '退出' }).click()
  await expect(page.getByLabel('访问令牌')).toBeVisible()

  // 3. 管理端：隐藏「在本机记住令牌」选项，显示仅内存安全说明
  await page.goto('/admin.html')
  await page.evaluate(() => localStorage.setItem('shutong.token', 'legacy-admin-token'))
  await page.reload()
  expect(await page.evaluate(() => localStorage.getItem('shutong.token'))).toBeNull()
  await expect(page.getByLabel(/在本机记住令牌/)).toHaveCount(0)
  await expect(page.getByText('管理凭据安全策略：仅在当前页面内存持有，不支持本机持久化记住。')).toBeVisible()

  // 4. 管理端正常登录与退出，管理凭据全生命周期零 localStorage 残留
  await page.getByLabel('访问令牌').fill(ADMIN_TOKEN)
  await page.getByRole('button', { name: '进入' }).click()
  await expect(page.getByRole('navigation', { name: '管理视图' })).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('shutong.admin_token'))).toBeNull()
  expect(await page.evaluate(() => localStorage.getItem('shutong.token'))).toBeNull()

  await page.getByRole('button', { name: '退出' }).click()
  await expect(page.getByLabel('访问令牌')).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('shutong.admin_token'))).toBeNull()
})

/* ---------- J9 会话续答（ST-018）：刷新/重开不空烧未见题 ---------- */

test('J9 会话续答：领取未见题后刷新恢复同一曝光，作答完成后刷新无残留', async ({ page }) => {
  await enterSpace(page)
  await navTab(page, /阶段诊断/).click()

  const claimRegion = page.getByRole('region', { name: '领取未见题' })
  // 初访不应出现续答提示（此前 J1–J6 已把全部未作答曝光消耗完）。
  await expect(page.getByText('已恢复上次未完成作答的题目')).toHaveCount(0)

  // 领取一道未见题（math.gap 在 J3 消耗后仍余未见题）。
  await claimRegion.getByRole('button', { name: '领取未见题诊断' }).click()
  const card = questionCard(page)
  await expect(card).toBeVisible()
  await expect(card).toContainText('阶段诊断 · 未见题')
  const claimedStem = await card.locator('p.stem').innerText()

  // 刷新（令牌仅内存 → 重新输入）后进入诊断页：同一曝光被恢复，题干一致，且明示续答。
  await page.reload()
  await page.getByLabel('访问令牌').fill(STUDENT_TOKEN)
  await page.getByRole('button', { name: '进入' }).click()
  await navTab(page, /阶段诊断/).click()
  await expect(page.getByText('已恢复上次未完成作答的题目')).toBeVisible()
  await expect(card.locator('p.stem')).toHaveText(claimedStem)
  await expect(card).toContainText('阶段诊断 · 未见题')
  // 已持有曝光时按钮切换为「已领取」态（不可重复领取），证明没有双烧未见题。
  await expect(claimRegion.getByRole('button', { name: '已领取，请在本页作答' })).toBeDisabled()
  await expect(claimRegion.getByRole('button', { name: '领取未见题诊断' })).toHaveCount(0)

  // 续答的题正常走判分链（甲为正确选项）。
  await card.getByRole('radio', { name: /甲/ }).click()
  await card.getByRole('button', { name: '提交答案' }).click()
  await expect(card.getByText('本题得分 2 / 2')).toBeVisible()
  await card.getByRole('button', { name: '完成本题' }).click()
  await expect(card).toHaveCount(0)

  // 完成后再刷新：无待续会话，可再次领取（未作答曝光不残留、不见题不双烧）。
  await page.reload()
  await page.getByLabel('访问令牌').fill(STUDENT_TOKEN)
  await page.getByRole('button', { name: '进入' }).click()
  await navTab(page, /阶段诊断/).click()
  await expect(page.getByText('已恢复上次未完成作答的题目')).toHaveCount(0)
  await expect(claimRegion.getByRole('button', { name: '领取未见题诊断' })).toBeEnabled()

  await expectHonestLanguage(page)
})
