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
 * - 仿真生效：iPad UA、触摸事件、deviceScaleRatio 如描述符。
 */
import { test, expect, devices, type Page } from '@playwright/test'

const TOKEN = 'test-journey-secret'
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

test('R1 竖屏 810×1080：三视图无横向溢出，720 断点未触发，触摸与 iPad UA 生效', async ({ page }) => {
  await enterSpace(page)

  // 仿真生效：iPad UA、触摸事件、810px 视口（720 < 810 < 980）。
  expect(await page.evaluate(() => navigator.userAgent)).toContain('iPad')
  expect(await page.evaluate(() => 'ontouchstart' in window)).toBe(true)
  expect(await page.evaluate(() => innerWidth)).toBe(810)

  // 首页（默认视图）：810px 下 .home-grid 仍为双列 grid——720 断点不得触发。
  const homeGridDisplay = await page.evaluate(() => getComputedStyle(document.querySelector('.home-grid')!).display)
  expect(homeGridDisplay, '810px 应保持桌面双列布局（720 断点未触发）').toBe('grid')
  await expectNoHorizontalOverflow(page)

  // 练习视图：控制区渲染即度量，不开始练习（不产生曝光）。
  await navTab(page, /练习/).click()
  await expect(page.getByRole('region', { name: '练习控制' })).toBeVisible()
  await expectNoHorizontalOverflow(page)

  // 阶段诊断视图：仅静态加载（绝不领取未见题，避免写入基线记录）。
  await navTab(page, /阶段诊断/).click()
  await expect(page.getByText('独立验证纪律')).toBeVisible()
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
