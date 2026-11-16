/* ST-EXAM-AUTOSYNC-01：Review 包界面证据截图（仅在 EXAM_SYNC_VISUALS=1 时运行）。
 *
 * 全部使用虚构数据与 API mock；不读取真实县/校/学生、私有附件或凭据。
 * 桌面通道：npx playwright test e2e/exam-sync-visual.spec.ts
 * iPad WebKit：E2E_DEVICE=ipad npx playwright test e2e/exam-sync-visual.spec.ts
 */
import { test, expect, devices, type APIRequestContext, type Browser, type BrowserContextOptions, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import fs from 'node:fs'
import path from 'node:path'

const ADMIN_TOKEN = 'test-admin-secret'
const enabled = process.env.EXAM_SYNC_VISUALS === '1'
const ipadMode = process.env.E2E_DEVICE === 'ipad'
const outputDir = process.env.EXAM_SYNC_VISUAL_DIR ?? '/tmp/exam-sync-visuals'
const AUTH = { Authorization: `Bearer ${ADMIN_TOKEN}` }

test.skip(!enabled, '仅在 EXAM_SYNC_VISUALS=1 时生成界面证据')

interface VisualState {
  status: 'needs_review' | 'imported'
  jobState: 'completed' | 'failed' | null
  totalConfirmed: boolean
  examId: string
}

const source = {
  environment: 'development',
  directory: '/tmp/pageboy-visual-home/development/school-exams/inbox',
  directory_display: '$PAGEBOY_HOME/development/school-exams/inbox',
  real_source_configured: false,
  source_kind: 'local_inbox',
  ready: true,
  source_code: 'SOURCE_NOT_CONFIGURED',
  message: '未配置真实授权学校试卷来源；可扫描收件箱中已有文件，但不会伪造远程下载。',
  supported_formats: ['PDF', 'DOCX', 'PNG', 'JPG/JPEG'],
  max_file_bytes: 36700160,
}

function paperPayload(state: VisualState) {
  const imported = state.status === 'imported'
  return {
    id: 'visual-paper-1',
    filename: '虚构测试数据_九年级数学月考试卷.docx',
    sha256: 'd'.repeat(64),
    media_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    byte_size: 20480,
    source_kind: 'local_scan',
    source_name: 'inbox',
    source_ref: 'inbox/虚构测试数据_九年级数学月考试卷.docx',
    header: {
      subject: 'math',
      academic_year: '2025-2026',
      grade: '9',
      exam_type: 'monthly',
      exam_type_label: '月考',
      exam_date: '2025-10-12',
      confidence: 'high',
      complete: true,
      fields: {
        academic_year: { status: 'found', value: '2025-2026', evidence: '2025—2026学年度' },
        grade: { status: 'found', value: '9', evidence: '九年级10月月考' },
        exam_type: { status: 'found', value: 'monthly', evidence: '10月月考' },
        subject: { status: 'found', value: 'math', evidence: '文件名：九年级数学月考试卷.docx' },
        exam_date: { status: 'found', value: '2025-10-12', evidence: '考试时间：2025年10月12日' },
      },
      text_excerpt: '2025—2026学年度九年级10月月考\n数学\n2025.10.12\n姓名：[已脱敏] 学号：[已脱敏]',
      warnings: [],
    },
    candidates: [
      {
        exam_id: state.examId,
        title: '虚构测试数据 · 九上10月月考 UI 核对',
        exam_date: '2025-11-15',
        score: 9,
        exact: false,
        comparisons: [
          { field: 'subject', label: '学科', expected: 'math', actual: 'math', state: 'match' },
          { field: 'academic_year', label: '学年度', expected: '2025-2026', actual: '2025-2026', state: 'match' },
          { field: 'grade', label: '年级', expected: '9', actual: '9', state: 'match' },
          { field: 'exam_type', label: '考试类型', expected: '月考', actual: '月考', state: 'match' },
          { field: 'exam_date', label: '考试日期', expected: '2025-10', actual: '2025-11', state: 'conflict' },
        ],
        conflicts: ['exam_date'],
        missing: [],
      },
    ],
    status: imported ? 'imported' : 'needs_review',
    match_state: imported ? 'MANUAL_CONFIRMED' : 'CONFLICT',
    school_exam_id: imported ? state.examId : null,
    exam: imported
      ? {
          id: state.examId,
          title: '虚构测试数据 · 九上10月月考 UI 核对',
          subject: 'math',
          exam_date: '2025-10-12',
          confirmed_by_user: state.totalConfirmed,
        }
      : null,
    error_code: null,
    imported_at: imported ? '2026-11-15T00:00:03Z' : null,
    created_at: '2026-11-15T00:00:00Z',
    updated_at: '2026-11-15T00:00:00Z',
  }
}

async function stabilize(page: Page): Promise<void> {
  const closeNotice = page.getByRole('button', { name: '关闭提示' })
  if (await closeNotice.count()) {
    await closeNotice.first().click()
  }
  await page.evaluate(() => Promise.allSettled(Array.from(document.getAnimations()).map(animation => animation.finished)))
  await page.waitForTimeout(80)
}

async function setupVisualPage(browser: Browser, contextOptions: BrowserContextOptions, state: VisualState): Promise<Page> {
  const context = await browser.newContext(contextOptions)
  const page = await context.newPage()
  await page.route('**/api/school-exams/sync-center', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        source,
        latest_scan: {
          id: 'visual-scan-1',
          status: 'completed',
          discovered_count: 1,
          imported_count: state.status === 'imported' ? 1 : 0,
          duplicate_count: 0,
          invalid_count: 0,
          needs_review_count: state.status === 'needs_review' ? 1 : 0,
          error_count: 0,
          errors: [],
          started_at: '2026-11-15T00:00:00Z',
          finished_at: '2026-11-15T00:00:02Z',
        },
        counts: {
          total: 1,
          needs_review: state.status === 'needs_review' ? 1 : 0,
          matched: state.status === 'imported' ? 1 : 0,
          imported: state.status === 'imported' ? 1 : 0,
          rejected: 0,
        },
        papers: [paperPayload(state)],
      }),
    }),
  )
  const job = state.jobState
    ? {
        job_id: state.jobState === 'failed' ? 'visual-job-failed' : 'visual-job-done',
        state: state.jobState,
        stage_message:
          state.jobState === 'failed'
            ? '检测到 HTTP 429，已立即熔断止损。'
            : '采集任务结束：逐题信息已作为待核对草稿保存。',
        created_at: '2026-11-15T00:00:00Z',
        updated_at: '2026-11-15T00:00:05Z',
        exam_keyword: '2025—2026学年第一学期 九年级10月月考',
        confirm_total_scores: false,
        error_code: state.jobState === 'failed' ? 'K12100_CIRCUIT_BREAKER' : null,
        error_message: state.jobState === 'failed' ? '检测到 HTTP 429，已立即熔断止损。' : null,
        result:
          state.jobState === 'completed'
            ? {
                source_exam_title: '2025—2026学年第一学期 九年级10月月考',
                source_exam_date: '2025-10-12',
                subjects: [
                  {
                    subject: 'math',
                    subject_label: '数学',
                    exam_id: state.examId,
                    exam_title: '虚构测试数据 · 九上10月月考 UI 核对',
                    exam_date: '2025-10-12',
                    earned_points: 88,
                    max_points: 100,
                    confirmed_by_user: false,
                    score_status: 'updated_unconfirmed',
                    stem_mode: 'pdf_local_regex',
                    parser_mode_used: 'local_rules',
                    attachments_uploaded: 1,
                    drafts_created: 3,
                    skipped_labels: [],
                    warning: null,
                    match_state: 'EXACT_MATCH',
                    ranks_created: 2,
                    rank_issues: [],
                  },
                ],
                totals: {
                  subjects_processed: 1,
                  subjects_blocked: 0,
                  created_exams: 0,
                  confirmed_now: 0,
                  locked_conflicts: 0,
                  attachments_uploaded: 1,
                  drafts_created: 3,
                  ranks_created: 2,
                },
                knowledge_evidence_created: 0,
              }
            : null,
      }
    : null
  await page.route('**/api/school-exams/k12100-sync/status', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        environment: 'development',
        mode: 'host_direct',
        can_run_local: true,
        is_isolated: false,
        browser_ready: true,
        node_available: true,
        playwright_available: true,
        unavailable_code: null,
        unavailable_reason: null,
        credentials: {
          status: 'ready',
          username_masked: '139****1111',
          deepseek_configured: true,
          deepseek_masked: 'sk-****',
          message: '已就绪',
        },
        deepseek_configured: true,
        active_job_id: job && (job.state === 'queued' || job.state === 'collecting' || job.state === 'backfilling') ? job.job_id : null,
        latest_job: job,
        recommended_cli_command: 'uv run python scripts/k12100_sync.py collect --env development',
      }),
    }),
  )
  await page.route(`**/api/school-exams/${state.examId}/ranks`, route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        exam_id: state.examId,
        ranks: [
          {
            id: 'visual-rank-class',
            subject_scope: 'math',
            scope: 'class',
            rank_value: 5,
            participant_count: 320,
            percentile: 0.96,
            source_name: 'k12100',
            source_field: 'classrank',
            ownership_status: 'verified',
            ownership_basis: 'single_student_ref_authenticated_subject_response',
            review_status: 'pending',
            captured_at: '2026-11-15T00:00:04Z',
            history_count: 1,
          },
          {
            id: 'visual-rank-school',
            subject_scope: 'math',
            scope: 'school',
            rank_value: 18,
            participant_count: 320,
            percentile: null,
            source_name: 'k12100',
            source_field: 'schoolrank',
            ownership_status: 'verified',
            ownership_basis: 'single_student_ref_authenticated_subject_response',
            review_status: 'pending',
            captured_at: '2026-11-15T00:00:04Z',
            history_count: 1,
          },
        ],
        missing_scopes: ['grade', 'region'],
        disclaimer: '本人排名仅为平台来源快照，不进入知识点能力画像，也不预测中考成绩。',
      }),
    }),
  )

  await page.goto('/admin.html')
  await page.getByLabel('访问令牌').fill(ADMIN_TOKEN)
  await page.getByRole('button', { name: '进入' }).click()
  await expect(page.getByRole('navigation', { name: '管理视图' })).toBeVisible()
  await page.getByRole('navigation', { name: '管理视图' }).getByRole('button', { name: '学校考试' }).click()
  await page.getByRole('tab', { name: /全科校考同步/ }).click()
  await expect(page.getByRole('region', { name: '全科校考同步中心' })).toBeVisible()
  await stabilize(page)
  return page
}

async function createVisualExam(request: APIRequestContext): Promise<string> {
  const response = await request.post('/api/school-exams', {
    headers: AUTH,
    data: {
      subject: 'math',
      title: '虚构测试数据 · 九上10月月考 UI 核对',
      exam_date: '2025-10-12',
      earned_points: 88,
      max_points: 100,
      confirmed_by_user: false,
      school_name: '虚构测试数据实验学校',
      grade: '九年级',
      exam_type: 'monthly',
      academic_year: '2025-2026',
      term: 'first',
      series_title: '2025—2026学年第一学期 九年级10月月考',
    },
  })
  expect(response.status()).toBe(201)
  return ((await response.json()) as { id: string }).id
}

test('V1 桌面：冲突、429 停止与核对入档界面证据', async ({ browser, request }) => {
  test.skip(ipadMode, '桌面证据只在 Chromium 通道生成')
  fs.mkdirSync(outputDir, { recursive: true })
  const examId = await createVisualExam(request)

  const conflict = await setupVisualPage(browser, { viewport: { width: 1280, height: 1000 } }, {
    status: 'needs_review',
    jobState: null,
    totalConfirmed: false,
    examId,
  })
  await conflict.getByRole('button', { name: /虚构测试数据_九年级数学月考试卷.docx/ }).click()
  await expect(conflict.getByRole('region', { name: '全科校考同步中心' })).toContainText('身份字段冲突')
  await stabilize(conflict)
  await conflict.screenshot({ path: path.join(outputDir, 'sync-center-desktop-conflict.png'), fullPage: true })

  const axe = await new AxeBuilder({ page: conflict })
    .include('#exam-panel-sync')
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze()
  fs.writeFileSync(
    path.join(outputDir, 'a11y-exam-sync.txt'),
    [
      `violations=${axe.violations.length}`,
      `blocking=${axe.violations.filter(v => v.impact === 'critical' || v.impact === 'serious').length}`,
      ...axe.violations.flatMap(v => [
        `${v.id} | ${v.impact} | nodes=${v.nodes.length} | ${v.help}`,
        ...v.nodes.map(node => `  target=${JSON.stringify(node.target)} html=${node.html.slice(0, 160)} detail=${(node.failureSummary ?? '').split('\n').slice(-1)[0]?.slice(0, 160)}`),
      ]),
    ].join('\n') + '\n',
    'utf-8',
  )

  const failed = await setupVisualPage(browser, { viewport: { width: 1280, height: 1000 } }, {
    status: 'imported',
    jobState: 'failed',
    totalConfirmed: false,
    examId,
  })
  await failed.getByRole('button', { name: /获取信息/ }).click()
  await expect(failed.getByRole('region', { name: '全科校考同步中心' })).toContainText('429')
  await stabilize(failed)
  await failed.screenshot({ path: path.join(outputDir, 'sync-center-desktop-stop.png'), fullPage: true })

  const review = await setupVisualPage(browser, { viewport: { width: 1280, height: 1000 } }, {
    status: 'imported',
    jobState: 'completed',
    totalConfirmed: false,
    examId,
  })
  await review.getByRole('button', { name: /^核对入档/ }).click()
  await expect(review.getByRole('region', { name: '全科校考同步中心' })).toContainText('第 5 名 / 320 人')
  await stabilize(review)
  await review.screenshot({ path: path.join(outputDir, 'sync-center-desktop-review.png'), fullPage: true })
  await conflict.context().close()
  await failed.context().close()
  await review.context().close()
})

test('V2 iPad：竖屏与横屏界面证据', async ({ browser, request }) => {
  test.skip(!ipadMode, 'iPad 证据只在 WebKit iPad 通道生成')
  fs.mkdirSync(outputDir, { recursive: true })
  const examId = await createVisualExam(request)
  for (const [name, descriptor] of [
    ['portrait', devices['iPad (gen 7)']],
    ['landscape', devices['iPad (gen 7) landscape']],
  ] as const) {
    const visual = await setupVisualPage(browser, { ...descriptor }, {
      status: 'needs_review',
      jobState: null,
      totalConfirmed: false,
      examId,
    })
    await visual.getByRole('button', { name: /虚构测试数据_九年级数学月考试卷.docx/ }).click()
    await stabilize(visual)
    await visual.screenshot({ path: path.join(outputDir, `sync-center-ipad-${name}.png`), fullPage: true })
    await visual.context().close()
  }
})
