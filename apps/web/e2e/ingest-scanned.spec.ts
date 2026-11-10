/* ST-014 J8 journey: scanned (image-only) PDF → upload → parse (pdftoppm+tesseract
 * draft with page markers) → manual per-question confirmation → review → publish →
 * practice (formula rendering from ST-013 in the same loop).
 *
 * Data: the scanned PDF is generated at runtime with Pillow (available because the
 * webServer runs the installed api package whose base deps include Pillow); it carries
 * ONLY synthetic ASCII text drawn by the test. No real papers, ever.
 *
 * Requires local parsers (poppler-utils + tesseract chi_sim/eng) on the machine running
 * the API webServer — CI installs them in both web-e2e jobs for exactly this reason.
 * Runs identically in the chromium and iPad/WebKit lanes (E2E_DEVICE=ipad). */
import { test, expect, type Page } from '@playwright/test'
import { execFileSync } from 'node:child_process'

const ADMIN_TOKEN = 'test-admin-secret'
const STUDENT_TOKEN = 'test-student-secret'
const API = process.env.ST008_API_BASE ?? 'http://127.0.0.1:18765'
const PY_CMD = process.env.PY_CMD ?? '../../.venv/bin/python'

const SOURCE_TITLE = '虚构测试数据：J8 扫描件题源'
const KID = 'math.scan'
const SCANNED_STEM = '虚构测试数据：由扫描件人工誊写——解方程 $$x^2-1=0$$。'

/** 运行时生成两页图像型 PDF（无文本层）并返回字节。 */
function buildScannedPdf(): Buffer {
  const script = [
    'from PIL import Image, ImageDraw',
    'pages = []',
    "for i in (1, 2):",
    "    img = Image.new('RGB', (600, 200), 'white')",
    "    draw = ImageDraw.Draw(img)",
    "    draw.text((30, 60), f'SYNTHETIC TEST DATA SCAN PAGE {i}', fill='black')",
    "    draw.text((30, 120), 'TRANSCRIBED BY HUMAN AFTER READING OCR DRAFT', fill='black')",
    '    pages.append(img)',
    "pages[0].save('/tmp/j8-scanned.pdf', save_all=True, append_images=pages[1:])",
    "print(open('/tmp/j8-scanned.pdf','rb').read(8))",
  ].join('\n')
  execFileSync(PY_CMD, ['-c', script], { stdio: ['ignore', 'ignore', 'inherit'] })
  const bytes = execFileSync(PY_CMD, ['-c', "import sys; sys.stdout.buffer.write(open('/tmp/j8-scanned.pdf','rb').read())"], { maxBuffer: 12 * 1024 * 1024 })
  return bytes
}

async function call<T = unknown>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: { Authorization: `Bearer ${ADMIN_TOKEN}`, ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const text = await res.text()
  if (!res.ok) throw new Error(`${method} ${path} -> HTTP ${res.status}: ${text.slice(0, 300)}`)
  return (text ? JSON.parse(text) : null) as T
}

test.beforeAll(async () => {
  // 幂等：worker 超时重启会重跑 beforeAll，按标题复用题源避免重复种子。
  const existing = await call<{ id: string; source: { title: string } }[]>('/api/admin/sources?subject=chinese')
  const reused = existing.find(item => item.source.title === SOURCE_TITLE)
  const source = reused
    ? reused.id
    : (await call<{ id: string }>('/api/admin/sources', 'POST', {
        title: SOURCE_TITLE,
        subject: 'chinese',
        rights_status: 'licensed',
        verified: true,
      })).id
  await call(`/api/admin/sources/${source}/review`, 'POST', {
    exam_year: 2026,
    source_url: 'https://example.org/synthetic-j8-scan.pdf',
    acquired_at: '2026-10-29',
    rights_status: 'licensed',
    rights_basis: '虚构测试数据：运行时合成的扫描件，人工确认无版权限制',
    applicable: true,
    applicability_note: '虚构测试数据：适用于 ST-014 摄取旅程验收',
    reviewed_by_human: true,
  })
})

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

test('J8 扫描件摄取：图像型 PDF 上传→OCR 解析草稿→人工确认导入→审核发布→练习渲染公式', async ({ page }) => {
  await enterAdminSpace(page)
  // 切换至语文科目（专属于 J8 扫描件摄取与题库，避免污染数学纵向闭环）
  await page.getByRole('group', { name: '科目' }).getByRole('button', { name: '语文' }).click()

  const ledger = page.getByRole('region', { name: '题源台账' })
  const review = page.getByRole('region', { name: '来源人工审核' })
  const attachments = page.getByRole('region', { name: '附件与解析' })
  const versions = page.getByRole('region', { name: '题目草稿与发布' })

  // ① 选中 beforeAll 建好的题源（已人工审核）。
  await ledger.getByRole('button', { name: new RegExp(SOURCE_TITLE) }).click()
  await expect(ledger.locator('li.source-item', { hasText: 'J8 扫描件题源' })).toContainText('已人工审核')

  // ② 上传运行时生成的图像型 PDF（无文本层）。
  const scanned = buildScannedPdf()
  expect(scanned.subarray(0, 5).toString()).toBe('%PDF-')
  await attachments.getByLabel(/选择原始附件/).setInputFiles({
    name: '虚构测试数据-j8-scan.pdf',
    mimeType: 'application/pdf',
    buffer: scanned,
  })
  await attachments.getByRole('button', { name: '上传附件' }).click()
  await expect(page.getByRole('status')).toContainText('附件已上传')

  // ③ 解析：pdftoppm→tesseract 逐页 OCR 草稿（上传使题源复位为未审核，如实）。
  await attachments.getByRole('button', { name: '解析' }).click()
  await expect(page.getByRole('status')).toContainText('解析完成', { timeout: 60_000 })
  const row = attachments.locator('li.attachment-row', { hasText: 'j8-scan.pdf' })
  await expect(row.locator('.chip.mid')).toContainText('已解析')
  await expect(row.locator('.parsed-text blockquote')).toContainText('第 1 页（OCR 草稿）')
  await expect(row.locator('.parsed-text blockquote')).toContainText('SCAN PAGE 1')
  await expect(row.locator('.parsed-text blockquote')).toContainText('SCAN PAGE 2')
  await expect(row.locator('.parsed-text blockquote')).toContainText('OCR 草稿') // 页码标记如实存在

  // ④ OCR 只是草稿：逐题人工录入（题干含公式，ST-013 渲染面）+ 显式人工核对 → 确认导入。
  await attachments.getByRole('button', { name: '逐题录入并确认导入' }).click()
  const entryForm = attachments.locator('.confirm-import')
  await entryForm.getByLabel('题干').fill(SCANNED_STEM)
  await entryForm.getByLabel('选项 A 内容').fill('1')
  await entryForm.getByLabel('选项 B 内容').fill('-1')
  await entryForm.getByLabel('正确选项').selectOption({ label: 'A · 1' })
  await entryForm.getByLabel('知识点 ID（至少 1 个，逗号或空格分隔）').fill(KID)
  await entryForm.getByRole('button', { name: '加入待导入列表' }).click()
  await expect(entryForm.getByText('已录入 1 题')).toBeVisible()
  await entryForm.getByLabel(/我已逐题人工核对/).check()
  await entryForm.getByRole('button', { name: '确认导入 1 题' }).click()
  await expect(page.getByRole('status')).toContainText('已确认导入 1 题，草稿待人工审核')

  // ⑤ 草稿人工审核通过；来源因上传复位 → 重新来源人工审核后才可发布（门禁如实）。
  const draftRow = versions.locator('li.version-row', { hasText: '由扫描件人工誊写' })
  await expect(draftRow.locator('.badge.qstatus-draft')).toBeVisible()
  await draftRow.getByRole('button', { name: '人工审核通过' }).click()
  await expect(page.getByRole('status')).toContainText('已标记为人工审核')
  await expect(draftRow.getByRole('button', { name: '发布' })).toBeDisabled()
  // 上传把题源复位为未审核：人工核查勾选框按会话重置（默认未勾选），须显式重新勾选后提交。
  await review.getByLabel(/我已人工核查来源与版权/).check()
  await review.getByRole('button', { name: '提交人工审核' }).click()
  await expect(page.getByRole('status')).toContainText('题源标记为已审核')
  await draftRow.getByRole('button', { name: '发布' }).click()
  await expect(page.getByRole('status')).toContainText('题目已发布')

  // ⑥ 进入学生练习区按语文科目取题：扫描件誊写的题干公式渲染为 KaTeX（ST-013 链路复用）。
  await enterSpace(page)
  await page.getByRole('group', { name: '科目' }).getByRole('button', { name: '语文' }).click()
  await page.getByRole('navigation', { name: '主要视图' }).getByRole('button', { name: /练习/ }).click()
  const practice = page.getByRole('region', { name: '练习控制' })
  await practice.getByRole('button', { name: '开始练习' }).click()
  const card = page.getByRole('region', { name: '题目' })
  await expect(card).toBeVisible()
  await expect(card.locator('p.stem .katex')).toHaveCount(1)
  await expect(card.locator('p.stem .katex-error')).toHaveCount(0)
  await expect(card.locator('p.stem')).not.toContainText('$')
  await card.getByRole('radio', { name: /^A/ }).click() // 正确答案为 A（选项文本可能互为子串，用前缀锚定）
  await card.getByRole('button', { name: '提交答案' }).click()
  await expect(card.getByText('本题得分 3 / 3')).toBeVisible() // 录入表单默认满分 3
})
