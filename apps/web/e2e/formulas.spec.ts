/* ST-013 题干富文本与公式渲染 e2e（chromium 与 iPad/WebKit 双引擎同一套断言）。
 *
 * 数据：全部为「虚构测试数据」，经管理 API 现场种入（镜像 global-setup / journeys J5 的
 * 新建题源 → 来源人工审核 → 逐题录入 → 人工审核 → 发布 流程）；不依赖 global-setup，
 * 使用独立知识点 math.formula*，绝不影响既有旅程的取题/曝光纪律。
 *
 * 选择器只用 role / 文案 / 既有结构类（.stem/.reading/.options/.reference/.version-stem），
 * 不新增 test-id。断言口径：
 *   - 公式 → KaTeX 渲染出 .katex，且无 .katex-error（非法 LaTeX 会回退为错误样式）；
 *   - 分隔符消失：题干/材料/参考答案文本中不再出现字面 `$`（更别提 `$\frac`）；
 *   - 文本段仍安全转义：选项里的 `<b>` 只作为字面文本出现，绝不生成 HTML 元素。 */
import { test, expect, type Page } from '@playwright/test'

const ADMIN_TOKEN = 'test-admin-secret'
const STUDENT_TOKEN = 'test-student-secret'
const API = process.env.ST008_API_BASE ?? 'http://127.0.0.1:18765'

const SOURCE_TITLE = '虚构测试数据：ST-013 公式渲染题源'
const CHOICE_KID = 'math.formula'
const SUBJ_KID = 'math.formula.subj'

const ROOT_FORMULA = '$$x=\\frac{-b\\pm\\sqrt{b^2-4ac}}{2a}$$'
const CHOICE_STEM = `虚构测试数据：解方程 ${ROOT_FORMULA} 的根。`
const GROUP_CONTEXT = '虚构测试数据：已知 $a+b$ 为正整数，且 $a-b=1$。'
const OPTION_A = `A. $x=\\frac{-b\\pm\\sqrt{b^2-4ac}}{2a}$`
const OPTION_B = 'B. <b>不是公式</b>'
const CHOICE_ANSWER = 'A'
const SUBJ_STEM = '虚构测试数据：写出求根公式的推导过程。'
const SUBJ_REFERENCE = `虚构测试数据：由配方法可得 ${ROOT_FORMULA}。`

/* ---------- admin API seeding ---------- */

async function call<T = unknown>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${ADMIN_TOKEN}`,
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const text = await res.text()
  if (!res.ok) throw new Error(`${method} ${path} -> HTTP ${res.status}: ${text.slice(0, 300)}`)
  return (text ? JSON.parse(text) : null) as T
}

async function seed(): Promise<void> {
  // 幂等：Playwright 在用例超时后会重启 worker 并重跑 beforeAll（2026-10-29 实证），
  // 按标题复用已存在的题源，避免重复种子把台账选择器挤成 strict 冲突。
  const existing = await call<{ id: string; source: { title: string } }[]>('/api/admin/sources?subject=physics')
  const reused = existing.find(item => item.source.title === SOURCE_TITLE)
  const source = reused
    ? reused.id
    : (
        await call<{ id: string }>('/api/admin/sources', 'POST', {
          title: SOURCE_TITLE,
          subject: 'physics',
          rights_status: 'licensed',
          verified: true,
        })
      ).id
  await call(`/api/admin/sources/${source}/review`, 'POST', {
    exam_year: 2026,
    source_url: 'https://example.org/synthetic-st013.pdf',
    acquired_at: '2026-10-28',
    rights_status: 'licensed',
    rights_basis: '虚构测试数据：合成题，人工确认无版权限制',
    applicable: true,
    applicability_note: '虚构测试数据：适用于 ST-013 公式渲染验收',
    reviewed_by_human: true,
  })

  const publish = async (question: Record<string, unknown>): Promise<void> => {
    const created = await call<{ id: string }>('/api/admin/questions', 'POST', {
      source_document_id: source,
      ...question,
    })
    await call(`/api/admin/questions/${created.id}/review`, 'POST')
    await call(`/api/admin/questions/${created.id}/publish`, 'POST')
  }

  await publish({
    stem: CHOICE_STEM,
    kind: 'single_choice',
    options: [OPTION_A, OPTION_B],
    correct_answer: CHOICE_ANSWER,
    knowledge_ids: [CHOICE_KID],
    max_points: 2,
    group_context: GROUP_CONTEXT,
  })
  await publish({
    stem: SUBJ_STEM,
    kind: 'subjective',
    correct_answer: SUBJ_REFERENCE,
    knowledge_ids: [SUBJ_KID],
    max_points: 4,
  })
}

test.beforeAll(async () => {
  await seed()
})

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

function questionCard(page: Page) {
  return page.getByRole('region', { name: '题目' })
}

async function openPracticeItem(page: Page) {
  await enterSpace(page)
  // 切换至物理科目（该科目专属于 ST-013 公式渲染题目，避免依赖学生端内部知识点参数筛选）
  await page.getByRole('group', { name: '科目' }).getByRole('button', { name: '物理' }).click()
  await page.getByRole('navigation', { name: '主要视图' }).getByRole('button', { name: /练习/ }).click()
  const lobby = page.getByRole('region', { name: '智能综合练习编排' })
  await lobby.getByRole('button', { name: /开始本轮智能练习/ }).click()
  const card = questionCard(page)
  await expect(card).toBeVisible()
  return card
}

/* ---------- 客观题：题干 / 阅读材料 / 选项 ---------- */

test('客观题：题干与材料公式渲染、选项公式与文本转义、KaTeX 交付判分', async ({ page }) => {
  const card = await openPracticeItem(page)

  // 题干：display 公式渲染为 KaTeX（无错误），分隔符与 LaTeX 源不再作为字面文本出现。
  await expect(card.locator('p.stem .katex')).toHaveCount(1)
  await expect(card.locator('p.stem .katex-error')).toHaveCount(0)
  await expect(card.locator('p.stem')).toContainText('虚构测试数据：解方程')
  await expect(card.locator('p.stem')).not.toContainText('$')
  await expect(card.locator('p.stem')).not.toContainText('$\\frac')

  // 阅读材料：两处行内公式各渲染一个 KaTeX，`$` 分隔符消失。
  await expect(card.locator('figure.reading .katex')).toHaveCount(2)
  await expect(card.locator('figure.reading .katex-error')).toHaveCount(0)
  await expect(card.locator('figure.reading blockquote')).not.toContainText('$')

  // 选项：A 含公式 → KaTeX；B 的 `<b>` 只作为字面文本，绝不生成 HTML 元素。
  const options = card.locator('.options .option')
  await expect(options).toHaveCount(2)
  await expect(options.nth(0).locator('.katex')).toHaveCount(1)
  await expect(options.nth(0).locator('.katex-error')).toHaveCount(0)
  await expect(options.nth(1).locator('b')).toHaveCount(0)
  await expect(options.nth(1)).toContainText('<b>不是公式</b>')

  // 卡片整体确有 KaTeX 节点（count > 0）。
  expect(await card.locator('.katex').count()).toBeGreaterThan(0)

  // 作答仍走既有客观判分链。
  await options.nth(0).click()
  await card.getByRole('button', { name: '提交答案' }).click()
  await expect(card.getByText('本题得分 2 / 2')).toBeVisible()
  await expect(card.getByText('评分来源：已审核答案自动比对')).toBeVisible()
})

/* ---------- 主观题：参考答案 ---------- */

test('主观题：参考答案公式渲染（自评链照常）', async ({ page }) => {
  const card = await openPracticeItem(page)
  await expect(card).toContainText('主观题')

  await card.getByLabel('解答').fill('虚构测试数据：用配方法推导。')
  await card.getByRole('button', { name: '提交答案' }).click()
  await expect(card.getByText('暂未评分，等待自评')).toBeVisible()

  const reference = card.locator('.reference')
  await expect(reference.locator('.katex')).toHaveCount(1)
  await expect(reference.locator('.katex-error')).toHaveCount(0)
  await expect(reference).toContainText('虚构测试数据：由配方法可得')
  await expect(reference).not.toContainText('$')
})

/* ---------- 审核台：草稿列表公式预览 ---------- */

test('审核台：题目草稿列表的公式预览同样安全渲染', async ({ page }) => {
  await enterAdminSpace(page)
  await page.getByRole('group', { name: '科目' }).getByRole('button', { name: '物理' }).click()

  const ledger = page.getByRole('region', { name: '题源台账' })
  await ledger.getByRole('button', { name: /ST-013 公式渲染题源/ }).click()

  await page.getByRole('tab', { name: /题目审核与发布/ }).click()
  const versions = page.getByRole('region', { name: '题目草稿与发布' })
  const choiceRow = versions.locator('li.version-row', { hasText: '解方程' }).first()
  await expect(choiceRow.locator('.version-stem .katex')).toHaveCount(1)
  await expect(choiceRow.locator('.version-stem .katex-error')).toHaveCount(0)
  await expect(choiceRow.locator('.version-stem')).not.toContainText('$')
})
