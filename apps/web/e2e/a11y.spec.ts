/* ST-009 F1：三视图 WCAG 2.0/2.1 A & AA 自动化无障碍扫描（axe-core）。
 *
 * 运行纪律：完全复用 playwright.config.ts 的既有双服务（uvicorn 18765 + Vite dev 5173）
 * 与 globalSetup 种子，不新增任何服务或配置。
 *
 * 状态边界（本文件按字母序先于 journeys.spec.ts 串行执行，workers=1）：
 * - 练习视图取一道训练题（只曝光、不作答）。种子下 J2 随后取差距题 2/3、J3 仍有
 *   7 道 math.gap 未见题（基线 3 + 复测 3 + 余量 1），J1–J4 断言全部不受影响。
 * - 诊断视图只做静态加载扫描，绝不「领取未见题」：领取并作答会写入基线记录，
 *   令 J3 的「基线 0% / 基线 3 题」断言失效。goal 已由种子建立（v1），
 *   诊断视图各面板可完整渲染（无 GOAL_REQUIRED 提示）。
 *
 * 门禁策略：critical / serious 违规即失败；minor / moderate 只报告不失败——
 * 保持门禁有效的同时避免脆性零容忍。
 */
import { test, expect, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

const ADMIN_TOKEN = 'test-admin-secret'
const STUDENT_TOKEN = 'test-student-secret'
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']

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

function navTab(page: Page, label: RegExp) {
  return page.getByRole('navigation', { name: '主要视图' }).getByRole('button', { name: label })
}

/** axe failureSummary 形如 "Fix any of the following:\n  <具体原因>."，取首个具体原因行。 */
function firstDetail(node: { failureSummary?: string }): string {
  const detail = node.failureSummary?.split('\n').find(line => line.trim() !== '' && !line.startsWith('Fix'))
  return (detail ?? '').trim().slice(0, 200)
}

/** 等入场动画（rise 0.35s，含 .view/.card）结束再测量：WCAG 1.4.3 对比度针对静止状态，
 *  半透明渐入过程中按混合色计算会产出虚假比值（如 --primary 按钮在 80% 不透明度下被误报）。 */
async function settleAnimations(page: Page): Promise<void> {
  await page.evaluate(() =>
    Promise.allSettled(Array.from(document.getAnimations()).map(animation => animation.finished)),
  )
}

/** 扫描当前页面：打印结构化报告（规则 / 影响 / 节点数 / 选择器片段 / 具体原因），
 *  仅当存在 critical / serious 违规时失败；minor / moderate 只报告。
 *  另附 incomplete（axe 无法自动判定的项，如渐变背景）作人工复核清单，不参与门禁。 */
async function scanAndReport(page: Page, view: string): Promise<void> {
  await settleAnimations(page)
  const results = await new AxeBuilder({ page }).withTags(TAGS).analyze()

  const lines: string[] = [`[a11y] ${view}：${results.violations.length} 条违规规则（wcag2a/2aa/21a/21aa）`]
  for (const violation of results.violations) {
    lines.push(
      `[a11y] ${view} | rule=${violation.id} | impact=${violation.impact ?? 'unknown'} | nodes=${violation.nodes.length} | ${violation.help}`,
    )
    for (const node of violation.nodes) {
      lines.push(`[a11y]   target=${JSON.stringify(node.target)} | html=${node.html.slice(0, 120)}`)
      const detail = firstDetail(node)
      if (detail) lines.push(`[a11y]   detail=${detail}`)
    }
  }
  if (results.incomplete.length > 0) {
    lines.push(`[a11y] ${view}：另 ${results.incomplete.length} 条待人工复核（incomplete，不计入门禁）`)
    for (const inc of results.incomplete) {
      lines.push(`[a11y] ${view} | incomplete=${inc.id} | nodes=${inc.nodes.length} | ${inc.help}`)
    }
  }
  console.log(lines.join('\n'))

  const blocking = results.violations.filter(v => v.impact === 'critical' || v.impact === 'serious')
  expect(
    blocking.map(v => `${v.id}(${v.impact}, ${v.nodes.length} 节点)`),
    `[a11y] ${view}：不允许出现 critical/serious 违规。完整发现：\n${lines.join('\n')}`,
  ).toEqual([])
}

/* ---------- 每视图一测 ---------- */

test('A1 练习：智能练习大厅与题目卡 WCAG A/AA 扫描', async ({ page }) => {
  await enterSpace(page)

  // 练习即默认视图：开始一轮 3 题练习后扫描题卡与会话条
  const lobby = page.getByRole('region', { name: '智能综合练习编排' })
  await expect(lobby).toBeVisible()
  await lobby.getByRole('button', { name: '3 题' }).click()
  await lobby.getByRole('button', { name: /开始本轮智能练习/ }).click()

  const card = page.getByRole('region', { name: '题目' })
  await expect(card).toBeVisible()
  await expect(card.locator('p.stem')).toContainText('虚构测试数据')

  await scanAndReport(page, 'practice')
})

test('A2 成长状态：优势不足与阶段验证面板 WCAG A/AA 扫描', async ({ page }) => {
  await enterSpace(page)
  await navTab(page, /成长状态/).click()

  await expect(page.getByRole('region', { name: '成长状态总览' })).toBeVisible()
  await expect(page.getByRole('region', { name: '学习目标与阶段验证' })).toContainText('目标版本 v1')
  await expect(page.getByRole('region', { name: '学习目标与阶段验证' })).toContainText('证据不足，无法比较')

  await scanAndReport(page, 'growth')
})

test('A3 知识点展示：图谱画布与节点详情 WCAG A/AA 扫描', async ({ page }) => {
  await enterSpace(page)
  await navTab(page, /知识点展示/).click()

  await expect(page.getByRole('region', { name: '知识点关系图谱展示' })).toBeVisible()
  await expect(page.getByRole('complementary', { name: '选中知识点详情' })).toBeVisible()

  await scanAndReport(page, 'knowledge')
})

test('A4 审核台：题源台账与人工审核工作流的 WCAG A/AA 扫描', async ({ page }) => {
  await enterAdminSpace(page)

  // 种子含两个已发布题源：默认落在第一阶段第 1 步「题源台账」（单卡聚焦），逐步推进并扫描各阶段工作台。
  // 本扫描只读：不创建题源、不上传、不提交审核（state 边界与 a11y 文件头一致）。
  const ledger = page.getByRole('region', { name: '题源台账' })
  await expect(ledger.locator('li.source-item').first()).toBeVisible()
  await expect(page.locator('#ledger-panel-sources .step-stage-body section.card')).toHaveCount(1)
  await scanAndReport(page, 'admin-sources')

  // 逐步推进至第 3 步「来源人工审核」（仍只呈现 1 张卡片）
  await ledger.getByRole('button', { name: /下一步：题源概览与顺序核查/ }).click()
  await page.getByRole('button', { name: /下一步：来源人工审核/ }).click()
  await expect(page.getByRole('region', { name: '来源人工审核' })).toBeVisible()
  await expect(page.locator('#ledger-panel-sources .step-stage-body section.card')).toHaveCount(1)
  await scanAndReport(page, 'admin-sources-review')

  await page.getByRole('tab', { name: /附件解析与录入/ }).click()
  await expect(page.getByRole('region', { name: '附件与解析' })).toBeVisible()
  await scanAndReport(page, 'admin-attachments')

  await page.getByRole('tab', { name: /题目审核与发布/ }).click()
  const versions = page.getByRole('region', { name: '题目草稿与发布' })
  await expect(versions).toBeVisible()
  // 选中题源的题目已全部发布：自动聚焦第 2 步「已发布入池题目（只读）」，至少一行「已发布」徽章。
  await expect(versions.locator('.badge.qstatus-published').first()).toBeVisible()
  await scanAndReport(page, 'admin-versions')
})
