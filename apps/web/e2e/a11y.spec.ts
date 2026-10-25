/* ST-009 F1：三视图 WCAG 2.0/2.1 A & AA 自动化无障碍扫描（axe-core）。
 *
 * 运行纪律：完全复用 playwright.config.ts 的既有双服务（uvicorn 18765 + vite preview 4173）
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

const TOKEN = 'test-journey-secret'
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']

/* ---------- helpers ---------- */

async function enterSpace(page: Page): Promise<void> {
  await page.goto('/')
  await page.getByLabel('访问令牌').fill(TOKEN)
  await page.getByRole('button', { name: '进入' }).click()
  await expect(page.getByRole('navigation', { name: '主要视图' })).toBeVisible()
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

test('A1 首页：目标与学习计划、阶段对比摘要的 WCAG A/AA 扫描', async ({ page }) => {
  await enterSpace(page)

  // 首页即默认视图：等待计划（种子目标 v1）与阶段对比摘要真正渲染后再扫描。
  const planRegion = page.getByRole('region', { name: '目标与学习计划' })
  await expect(planRegion.getByText('目标版本 v1')).toBeVisible()
  await expect(planRegion.getByText('每天 15 分钟')).toBeVisible()
  await expect(page.getByRole('region', { name: '阶段对比摘要' })).toContainText('证据不足，无法比较')

  await scanAndReport(page, 'home')
})

test('A2 练习：训练题卡渲染后的 WCAG A/AA 扫描', async ({ page }) => {
  await enterSpace(page)
  await navTab(page, /练习/).click()

  const practice = page.getByRole('region', { name: '练习控制' })
  await expect(practice).toContainText('复练会在全部已发布题中轮换取题')

  // 取一道训练题（只曝光、不作答），确保题目卡进入可扫描 DOM。
  await practice.getByRole('button', { name: '开始练习' }).click()
  const card = page.getByRole('region', { name: '题目' })
  await expect(card).toBeVisible()
  await expect(card.locator('p.stem')).toContainText('虚构测试数据')

  await scanAndReport(page, 'practice')
})

test('A3 阶段诊断：独立验证纪律、判决与校卷总分面板的 WCAG A/AA 扫描', async ({ page }) => {
  await enterSpace(page)
  await navTab(page, /阶段诊断/).click()

  // goal 已由种子建立：诊断视图各面板完整渲染（不出现「还没有目标」提示）。
  await expect(page.getByText('独立验证纪律')).toBeVisible()
  const claimRegion = page.getByRole('region', { name: '领取未见题' })
  await expect(claimRegion).toContainText('「未见题」指你从未曝光过的题')
  await expect(page.getByRole('region', { name: '阶段对比判决' })).toContainText('证据不足，无法比较')
  await expect(page.getByRole('region', { name: '学校考试总分' })).toContainText('总分不产生考点证据')
  await expect(claimRegion.getByRole('button', { name: '领取未见题诊断' })).toBeEnabled()

  await scanAndReport(page, 'diagnosis')
})

test('A4 审核台：题源台账与人工审核工作流的 WCAG A/AA 扫描', async ({ page }) => {
  await enterSpace(page)
  await navTab(page, /审核台/).click()

  // 种子含两个已发布题源：台账非空，默认选中第一个，四个区块完整渲染后扫描。
  // 本扫描只读：不创建题源、不上传、不提交审核（state 边界与 a11y 文件头一致）。
  const ledger = page.getByRole('region', { name: '题源台账' })
  await expect(ledger.locator('li.source-item').first()).toBeVisible()
  await expect(page.getByRole('region', { name: '来源人工审核' })).toBeVisible()
  await expect(page.getByRole('region', { name: '附件与解析' })).toBeVisible()
  const versions = page.getByRole('region', { name: '题目草稿与发布' })
  await expect(versions).toBeVisible()
  // 选中题源的题目已全部发布：至少一行「已发布」徽章证明只读列表真实挂载。
  await expect(versions.locator('.badge.qstatus-published').first()).toBeVisible()

  await scanAndReport(page, 'admin')
})
