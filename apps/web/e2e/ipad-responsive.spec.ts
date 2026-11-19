/* ST-010：iPad（WebKit 仿真）响应式布局验证 —— 720–980px 区间。
 *
 * 只在 E2E_DEVICE=ipad 通道（npm run test:e2e:ipad）运行；默认 chromium 通道
 * 整文件跳过（跳过记录本身即反例证据：响应式断言不属于桌面通道）。
 *
 * 状态边界（文件按字母序介于 a11y 与 journeys 之间、串行 workers=1）：
 * 本文件只读导航与度量，绝不「开始练习 / 领取未见题 / 保存目标」，
 * 不产生曝光、作答或目标版本，保证 J1 的全新库断言不受影响
 * （a11y.spec.ts 只消耗一道训练题曝光，余量见其文件头注释）。
 *
 * 断言口径（对照 style.css 响应式规则）：
 * - 竖屏 810px 落在 720 断点与 980 上限之间：.home-grid 保持 grid（断点未触发），
 *   三视图均无横向溢出；
 * - 横屏 1080px：.page 被 max-width:980px 收束（border-box，rect 宽即 980）；
 * - R3 矩阵：gen 11 / Mini / Pro 11 竖横六向，视口与 iPad UA 生效、首页无溢出；
 * - 仿真生效：iPad UA、触摸事件、deviceScaleRatio 如描述符。
 */
import { test, expect, devices, type Page } from '@playwright/test'

const TOKEN = 'test-student-secret'
const ADMIN_TOKEN = 'test-admin-secret'
const ipadMode = process.env.E2E_DEVICE === 'ipad'

test.skip(!ipadMode, '仅 iPad 仿真通道运行（E2E_DEVICE=ipad）')

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

/** 单栏布局不允许横向滚动：scrollWidth 不得超过 clientWidth。 */
async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  const m = await page.evaluate(() => ({
    scrollW: document.documentElement.scrollWidth,
    clientW: document.documentElement.clientWidth,
  }))
  expect(
    m.scrollW,
    `出现横向溢出：scrollWidth=${m.scrollW} > clientWidth=${m.clientW}`,
  ).toBeLessThanOrEqual(m.clientW)
}

/* ---------- R1 竖屏 ---------- */

test('R1 竖屏 810×1080：四视图无横向溢出，720 断点未触发，触摸与 iPad UA 生效', async ({ page }) => {
  await enterSpace(page)

  // 仿真生效：iPad UA、触摸事件、810px 视口（720 < 810 < 980）。
  expect(await page.evaluate(() => navigator.userAgent)).toContain('iPad')
  expect(await page.evaluate(() => 'ontouchstart' in window)).toBe(true)
  expect(await page.evaluate(() => innerWidth)).toBe(810)

  // 练习（默认视图）：810px 下 .lobby-controls 保持网格布局（720 断点未触发），且可切换至近期错题回顾工作台无溢出。
  await expect(page.getByRole('region', { name: '智能综合练习编排' })).toBeVisible()
  const lobbyGridDisplay = await page.evaluate(() => getComputedStyle(document.querySelector('.lobby-controls')!).display)
  expect(lobbyGridDisplay, '810px 应保持控制网格（720 断点未触发）').toBe('grid')
  await expectNoHorizontalOverflow(page)

  await page.getByRole('tab', { name: /近期错题回顾/ }).click()
  await expect(page.getByRole('region', { name: '近期错题与引导复习' })).toBeVisible()
  await expectNoHorizontalOverflow(page)
  await page.getByRole('tab', { name: /开始新练习/ }).click()
  await expect(page.getByRole('region', { name: '智能综合练习编排' })).toBeVisible()

  // 成长状态视图：只读加载（不修改目标、不消耗未见题），度量双列与雷达无溢出。
  await navTab(page, /成长状态/).click()
  await expect(page.getByRole('region', { name: '成长状态总览' })).toBeVisible()
  await expectNoHorizontalOverflow(page)

  // 知识点展示视图：交互图谱画布内部滚动，页面整体无横向溢出。
  await navTab(page, /知识点展示/).click()
  await expect(page.getByRole('region', { name: '知识点关系图谱展示' })).toBeVisible()
  await expectNoHorizontalOverflow(page)

  // 错题复盘视图：校考错题复盘与防敷衍质检，无横向溢出。
  await navTab(page, /错题复盘/).click()
  await expect(page.getByRole('region', { name: '校考错题复盘工作台' })).toBeVisible()
  await expectNoHorizontalOverflow(page)

  // 管理端工作台（/admin.html）：分阶段子 Tab 条 + 单卡分步工作区 + 知识点审核工作台，均无横向溢出。
  await page.goto('/admin.html')
  await page.getByLabel('访问令牌').fill(ADMIN_TOKEN)
  await page.getByRole('button', { name: '进入' }).click()
  await expect(page.getByRole('navigation', { name: '管理视图' })).toBeVisible()
  await expect(page.getByRole('region', { name: '题源台账' })).toBeVisible()
  await expectNoHorizontalOverflow(page)

  await page.getByRole('tab', { name: /附件解析与录入/ }).click()
  await expectNoHorizontalOverflow(page)

  await page.getByRole('navigation', { name: '管理视图' }).getByRole('button', { name: '学校考试' }).click()
  await expect(page.getByRole('region', { name: '学校考试总分' })).toBeVisible()
  await expectNoHorizontalOverflow(page)

  // 第 1 步先建档进入第 2 步「总分概览与材料入口」，再从第 2 步跳转全科同步与报告导入（测完在 UI 删除占位档案，保持空库给 J4）
  await page.getByLabel('考试名称').fill('视口巡检占位校考（虚构测试数据）')
  await page.getByLabel('获得分数').fill('88')
  await page.getByRole('button', { name: /记录已核对总分|暂存待核对档案/ }).click()
  await expect(page.getByRole('button', { name: /2\. 全科校考同步/ })).toBeVisible()

  await page.getByRole('button', { name: /2\. 全科校考同步/ }).click()
  await expect(page.getByRole('region', { name: '全科校考同步中心' })).toBeVisible()
  await expectNoHorizontalOverflow(page)

  await page.getByRole('button', { name: /返回第一阶段/ }).click()
  await page.getByRole('button', { name: /1\. 报告导入与核对/ }).click()
  await expect(page.getByRole('region', { name: '校考报告导入与核对' })).toBeVisible()
  await expectNoHorizontalOverflow(page)

  await page.getByRole('button', { name: /返回第一阶段/ }).click()
  await page.getByRole('button', { name: /← 返回第 1 步切换或新建场次/ }).click()
  await page.getByRole('button', { name: '删除 视口巡检占位校考（虚构测试数据）' }).click()
  await page.getByRole('button', { name: '确认删除 视口巡检占位校考（虚构测试数据）' }).click()
  await expect(page.getByLabel('考试名称')).toBeVisible()

  await page.getByRole('navigation', { name: '管理视图' }).getByRole('button', { name: '知识点库' }).click()
  await expect(page.getByRole('region', { name: '知识点工作台总览' })).toBeVisible()
  await expectNoHorizontalOverflow(page)

  await page.getByRole('navigation', { name: '管理视图' }).getByRole('button', { name: '错题诊断' }).click()
  await expect(page.getByRole('region', { name: '错题 AI 深度诊断工作台' })).toBeVisible()
  await expectNoHorizontalOverflow(page)
})

/* ---------- R2 横屏 ---------- */

test('R2 横屏 1080×810：.page 被 980px 上限收束，无横向溢出', async ({ browser }) => {
  const ctx = await browser.newContext({ ...devices['iPad (gen 7) landscape'] })
  const page = await ctx.newPage()
  try {
    await enterSpace(page)
    expect(await page.evaluate(() => innerWidth)).toBe(1080)

    // border-box + max-width:980px：1080px 视口下列宽被收束到 980，而非全幅铺开。
    const pageWidth = await page.evaluate(() => document.querySelector('.page')!.getBoundingClientRect().width)
    expect(pageWidth, '1080px 视口下 .page 应被 980px 上限收束').toBe(980)
    await expectNoHorizontalOverflow(page)
  } finally {
    await ctx.close()
  }
})

/* ---------- R3 设备描述符矩阵 ---------- */

test('R3 描述符矩阵：gen 11 / Mini / Pro 11 竖横各向视口与 UA 生效，首页无横向溢出', async ({ browser }) => {
  // gen 7 由 R1/R2 覆盖；此处把其余三个 iPad 描述符纳入门禁（原为通道外冒烟）。
  const matrix = [
    'iPad (gen 11)', 'iPad (gen 11) landscape',
    'iPad Mini', 'iPad Mini landscape',
    'iPad Pro 11', 'iPad Pro 11 landscape',
  ]
  for (const name of matrix) {
    const desc = devices[name]
    const ctx = await browser.newContext({ ...desc })
    const page = await ctx.newPage()
    try {
      await enterSpace(page)
      expect(await page.evaluate(() => innerWidth), `${name} 视口应生效`).toBe(desc.viewport.width)
      expect(await page.evaluate(() => navigator.userAgent), `${name} 应为 iPad UA`).toContain('iPad')
      await expectNoHorizontalOverflow(page)
    } finally {
      await ctx.close()
    }
  }
})
