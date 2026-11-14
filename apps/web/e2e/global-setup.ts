/* ST-008 F1：旅程种子（全部虚构测试数据）。webServers 就绪后运行。
 *
 * 题量按 test_math_vertical.py 的曝光纪律反推（evaluation 只发未见题、training
 * 按（最少曝光优先）轮换会消耗新题）：
 * - math.gap 10 道单选：J2 复练消耗 2 道 + J3 基线 3 道 + 复测 3 道 + 余量 2 道；
 * - math.ok 4 道单选（其中 2 道共享阅读材料 group_context）；
 * - math.short 1 道短答（答案 'x=1' 需在归一化比对下存活）；
 * - math.subj 1 道主观（correct_answer 即参考答案文本）；
 * - math.listen 1 道听力单选（合成 mp3 附件，经 upload→parse→confirm-import 导入）。
 *
 * 门禁注意：来源一旦带附件，该来源的题必须走 confirm-import 才能发布
 * （require_import_integrity），所以听力题放在独立题源 B；上传会令 source.verified
 * 复位，故附件导入后须重走来源审核再发布（镜像 test_media_question.py）。 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import type { FullConfig } from '@playwright/test'

// 端口 18765 与 playwright.config.ts 保持一致（8000 被无关常驻服务占用）。
const API = process.env.ST008_API_BASE ?? 'http://127.0.0.1:18765'
const ADMIN_TOKEN = 'test-admin-secret'
const STUDENT_TOKEN = 'test-student-secret'

async function call<T = any>(path: string, method = 'GET', body?: unknown, token = ADMIN_TOKEN): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const text = await res.text()
  if (!res.ok) throw new Error(`${method} ${path} -> HTTP ${res.status}: ${text.slice(0, 300)}`)
  return (text ? JSON.parse(text) : null) as T
}

async function waitForApi(): Promise<void> {
  const problems: string[] = []
  for (let i = 0; i < 60; i++) {
    try {
      const res = await fetch(`${API}/health/live`)
      if (res.ok) return
      problems.push(`HTTP ${res.status}: ${(await res.text()).slice(0, 120)}`)
    } catch (error) {
      problems.push(String(error).slice(0, 160))
    }
    await new Promise(resolve => setTimeout(resolve, 500))
  }
  throw new Error(`API 未在 30 秒内就绪。诊断：${JSON.stringify(problems.slice(0, 3))}；末次：${JSON.stringify(problems.slice(-2))}`)
}

function reviewPayload(rightsBasis: string, note: string) {
  return {
    exam_year: 2026,
    source_url: 'https://example.org/synthetic-st008.pdf',
    acquired_at: '2026-10-18',
    rights_status: 'licensed',
    rights_basis: rightsBasis,
    applicable: true,
    applicability_note: note,
    reviewed_by_human: true,
  }
}

async function publishQuestion(sourceId: string, question: Record<string, unknown>): Promise<string> {
  const created = await call<{ id: string }>('/api/admin/questions', 'POST', { source_document_id: sourceId, ...question })
  await call(`/api/admin/questions/${created.id}/review`, 'POST')
  await call(`/api/admin/questions/${created.id}/publish`, 'POST')
  return created.id
}

// 确保无私有课标 PDF 的 CI 环境同样具备合成课标标记文件（与 conftest.py 协议一致，不覆盖真实大文件）。
function ensureSyntheticCurriculumStandards(): void {
  const currentDir = path.dirname(fileURLToPath(import.meta.url))
  const repoRoot = path.resolve(currentDir, '..', '..', '..')
  const pdfDir = path.join(repoRoot, 'private-data', 'curriculum_standards')
  const sourcesPath = path.join(repoRoot, 'contracts', 'curriculum_sources.json')
  if (!fs.existsSync(sourcesPath)) return

  const localNameMap: Record<string, string> = {
    chinese: '义务教育语文课程标准（2022年版）.pdf',
    math: '义务教育数学课程标准（2022年版）（以此为准2022年5月9日）.pdf',
    english: '义务教育英语课程标准（2022年版）.pdf',
    physics: '义务教育物理课程标准（2022年版）.pdf',
  }

  const sources = JSON.parse(fs.readFileSync(sourcesPath, 'utf-8')) as Array<{
    subject?: string
    file_sha256?: string
    byte_size?: number
  }>
  fs.mkdirSync(pdfDir, { recursive: true })
  for (const s of sources) {
    const fname = s.subject ? localNameMap[s.subject] : undefined
    if (!fname) continue
    const fpath = path.join(pdfDir, fname)
    if (!fs.existsSync(fpath) || fs.statSync(fpath).size < 1024) {
      fs.writeFileSync(
        fpath,
        `%PAGEBOY_SYNTHETIC_STANDARD:${s.file_sha256}:${s.byte_size}\n`,
        'utf-8',
      )
    }
  }
}

async function seed(): Promise<void> {
  ensureSyntheticCurriculumStandards()
  await waitForApi()

  // 题源 A：数学主题源（人工审核 + licensed）。
  const sourceA = (await call<{ id: string }>('/api/admin/sources', 'POST', {
    title: '虚构测试数据：ST-008 旅程数学题源',
    subject: 'math',
    rights_status: 'licensed',
    verified: true,
  })).id
  await call(`/api/admin/sources/${sourceA}/review`, 'POST', reviewPayload(
    '虚构测试数据：合成题，人工确认无版权限制',
    '虚构测试数据：适用于 ST-008 旅程验收',
  ))

  const choice = (stem: string, extra: Record<string, unknown> = {}) => ({
    stem,
    kind: 'single_choice',
    options: ['A. 甲', 'B. 乙'],
    correct_answer: 'A',
    max_points: 2,
    ...extra,
  })

  // 1) math.gap ×10：先建（created_at 最早），保证 evaluation 依次先发差距题。
  for (let i = 1; i <= 10; i++) {
    await publishQuestion(sourceA, choice(`虚构测试数据：差距题 ${i}。`, { knowledge_ids: ['math.gap'] }))
  }
  // 1b) 映射至新课标节点 math_cand.num.real / math_cand.num.rational 的 12 道练习题，供知识图谱、阶段诊断与定向练习验证。
  for (let i = 1; i <= 12; i++) {
    await publishQuestion(sourceA, choice(`虚构测试数据：实数与有理数综合题 ${i}。`, { knowledge_ids: ['math.num.real'] }))
  }
  // 2) math.ok ×4：前两题共享阅读材料。
  const groupContext = '虚构测试数据：阅读材料文本——两道题共享这一段材料。'
  for (const stem of ['虚构测试数据：对照阅读题 1。', '虚构测试数据：对照阅读题 2。']) {
    await publishQuestion(sourceA, choice(stem, { knowledge_ids: ['math.ok'], group_context: groupContext }))
  }
  for (const stem of ['虚构测试数据：对照题 3。', '虚构测试数据：对照题 4。']) {
    await publishQuestion(sourceA, choice(stem, { knowledge_ids: ['math.ok'] }))
  }
  // 3) 短答 ×1（短答归一化比对：'x=1'）。
  await publishQuestion(sourceA, {
    stem: '虚构测试数据：解方程 2x=2，求 x。',
    kind: 'short_answer',
    correct_answer: 'x=1',
    knowledge_ids: ['math.short'],
    max_points: 3,
  })
  // 4) 主观 ×1（correct_answer 即参考答案文本）。
  await publishQuestion(sourceA, {
    stem: '虚构测试数据：论述复练与阶段诊断的区别。',
    kind: 'subjective',
    correct_answer: '虚构测试数据：参考解答——复练面向已见题巩固；阶段诊断用从未见过的题独立验证。',
    knowledge_ids: ['math.subj'],
    max_points: 6,
  })

  // 5) 听力题 ×1：题源 B + 合成 mp3（ID3 魔数 + 零填充，无真实音频内容）。
  const sourceB = (await call<{ id: string }>('/api/admin/sources', 'POST', {
    title: '虚构测试数据：ST-008 旅程听力题源',
    subject: 'math',
    rights_status: 'licensed',
    verified: true,
  })).id
  const mp3 = new Uint8Array(507) // b'ID3' + b'\x03\x00\x00\x00' + 500 个零字节：运行时合成的虚构音频。
  mp3.set(Buffer.from('ID3'), 0)
  mp3[3] = 0x03
  const uploadRes = await fetch(`${API}/api/admin/sources/${sourceB}/attachments?filename=${encodeURIComponent('虚构测试数据-听力.mp3')}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${ADMIN_TOKEN}`, 'Content-Type': 'audio/mpeg' },
    body: mp3,
  })
  if (!uploadRes.ok) throw new Error(`upload -> HTTP ${uploadRes.status}: ${(await uploadRes.text()).slice(0, 300)}`)
  const attachmentId = ((await uploadRes.json()) as { id: string }).id

  await call(`/api/admin/attachments/${attachmentId}/parse`, 'POST')
  const confirmed = await call<{ question_version_ids: string[] }>(`/api/admin/attachments/${attachmentId}/confirm`, 'POST', {
    confirmed_by_human: true,
    questions: [{
      source_document_id: sourceB,
      stem: '虚构测试数据：听力题——听录音选出提到的词。',
      kind: 'single_choice',
      options: ['A. 甲', 'B. 乙'],
      correct_answer: 'A',
      knowledge_ids: ['math.listen'],
      max_points: 2,
      media_attachment_id: attachmentId,
    }],
  })
  // 上传会令 source.verified 复位：重走来源审核，再审核并发布听力题。
  await call(`/api/admin/sources/${sourceB}/review`, 'POST', reviewPayload(
    '虚构测试数据：合成音频，人工确认无版权限制',
    '虚构测试数据：适用于 ST-008 听力旅程验收',
  ))
  const listeningVersion = confirmed.question_version_ids[0]
  await call(`/api/admin/questions/${listeningVersion}/review`, 'POST')
  await call(`/api/admin/questions/${listeningVersion}/publish`, 'POST')

  // 6) 目标：计划/诊断依赖目标存在（GOAL_REQUIRED），v1 由种子建立，J1 再经 UI 保存 v2。
  await call('/api/goals', 'POST', { subject: 'math', target_points: 90, max_points: 100, minutes_per_day: 15 }, STUDENT_TOKEN)
}

export default async function globalSetup(_config: FullConfig): Promise<void> {
  await seed()
}
