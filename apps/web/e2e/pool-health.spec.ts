/* ST-015 题库体检 e2e（chromium 与 iPad/WebKit 双引擎同一套断言）。
 *
 * 数据：复用 global-setup 的虚构测试数据（math 已发布题含 math.gap/math.ok/math.short/
 * math.subj/math.listen 五个知识点）。J1–J6 会消耗部分曝光，故只断言形状与集合，
 * 不断言精确计数（计数由后端 test_pool_health.py 单测锁定）。
 * 选择器只用 role / aria-label / 既有结构类（code.kid / .comparison），不新增 test-id。 */
import { test, expect, type Page } from '@playwright/test'
import { getKnowledgeLabel } from '../src/config/knowledge'

const TOKEN = 'test-admin-secret'

async function enterAdminSpace(page: Page): Promise<void> {
  await page.goto('/admin.html')
  await page.getByLabel('访问令牌').fill(TOKEN)
  await page.getByRole('button', { name: '进入' }).click()
  await expect(page.getByRole('navigation', { name: '管理视图' })).toBeVisible()
}

/** 诚实文案红线（与 journeys.spec.ts 同一口径）：禁「提分」；「预测」只允许否定式上下文。 */
async function expectHonestLanguage(page: Page): Promise<void> {
  const text = await page.evaluate(() => document.body.innerText)
  expect(text, '页面不得出现「提分」表述').not.toContain('提分')
  for (const match of text.matchAll(/预测/g)) {
    const before = text.slice(Math.max(0, match.index - 10), match.index)
    expect(before, `「预测」只能出现在否定式免责声明里，实际上下文为「${before}预测」`).toMatch(/不作|不是/)
  }
}

test('J7 题库体检：计数口径如实呈现、知识点行齐全、免责声明在位', async ({ page }) => {
  await enterAdminSpace(page)
  await page.getByRole('navigation', { name: '管理视图' }).getByRole('button', { name: /题库体检/ }).click()

  const card = page.getByRole('region', { name: '题库体检' })
  await expect(card).toBeVisible()

  // 总量行：三个合理计数（文案锚点，不断言数值——随 J1–J6 消耗而变化）。
  await expect(card).toContainText('已发布')
  await expect(card).toContainText('未见题余量')
  await expect(card).toContainText('已曝光')

  // 知识点行：global-setup 的五个数学知识点各有一行（code.kid 既有约定，兼容本地化标签）。
  for (const kid of ['math.gap', 'math.listen', 'math.ok', 'math.short', 'math.subj']) {
    const label = getKnowledgeLabel(kid)
    await expect(card.locator('li', { has: page.locator('code.kid', { hasText: new RegExp(`${label}|${kid}`) }) })).toBeVisible()
  }

  // 后端免责声明原文在位（.muted .tiny）：不构成分数或能力结论。
  await expect(card.locator('.muted.tiny')).toContainText('不构成分数或能力结论')

  await expectHonestLanguage(page)
})

test('J7b 题库体检：零余量知识点如实显示「暂无未见题余量」，不伪造 0 分语义', async ({ page }) => {
  // 在暂未种题的 english 学科创建 1 道已发布题并作为学生曝光 1 次，使该知识点确定达到未见题余量 0。
  const apiBase = 'http://127.0.0.1:18765'
  const adminHeaders = { Authorization: `Bearer ${TOKEN}`, 'Content-Type': 'application/json' }
  const srcRes = await page.request.post(`${apiBase}/api/admin/sources`, {
    headers: adminHeaders,
    data: { title: '虚构测试数据：零余量校验题源', subject: 'english', rights_status: 'licensed', verified: true },
  })
  const srcId = (await srcRes.json()).id as string
  await page.request.post(`${apiBase}/api/admin/sources/${srcId}/review`, {
    headers: adminHeaders,
    data: {
      exam_year: 2026,
      source_url: 'https://example.org/zero-pool.pdf',
      acquired_at: '2026-10-20',
      rights_status: 'licensed',
      rights_basis: '虚构测试数据：合成校验用题',
      applicable: true,
      applicability_note: '虚构测试数据：零余量校验',
      reviewed_by_human: true,
    },
  })
  const qRes = await page.request.post(`${apiBase}/api/admin/questions`, {
    headers: adminHeaders,
    data: {
      source_document_id: srcId,
      stem: '虚构测试数据：英语零余量校验唯一题。',
      kind: 'single_choice',
      options: ['A. Yes', 'B. No'],
      correct_answer: 'A',
      knowledge_ids: ['english.zero_test'],
      max_points: 2,
    },
  })
  const qid = (await qRes.json()).id as string
  await page.request.post(`${apiBase}/api/admin/questions/${qid}/review`, { headers: adminHeaders })
  await page.request.post(`${apiBase}/api/admin/questions/${qid}/publish`, { headers: adminHeaders })
  const expRes = await page.request.get(`${apiBase}/api/practice/next?subject=english&purpose=evaluation`, {
    headers: { Authorization: 'Bearer test-student-secret' },
  })
  expect(expRes.ok()).toBe(true)

  await enterAdminSpace(page)
  await page.getByRole('navigation', { name: '管理视图' }).getByRole('button', { name: /题库体检/ }).click()
  await page.getByRole('group', { name: '科目' }).getByRole('button', { name: '英语' }).click()

  const card = page.getByRole('region', { name: '题库体检' })
  await expect(card).toBeVisible()

  // 零余量行必须出现「暂无未见题余量」提示，且页面不得出现「0 分」表述（缺证据不渲染为 0 分）。
  await expect(card.getByText('暂无未见题余量').first()).toBeVisible()
  const text = await page.evaluate(() => document.body.innerText)
  for (const match of text.matchAll(/0\s*分/g)) {
    const before = text.slice(Math.max(0, (match.index ?? 0) - 6), match.index ?? 0)
    expect(before, `「0 分」只能出现在否定式说明里，实际上下文为「${before}0 分」`).toMatch(/不显示|不是|不会|绝不/)
  }

  await expectHonestLanguage(page)
})
