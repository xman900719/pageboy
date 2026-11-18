#!/usr/bin/env node
/**
 * k12100.com 拟人化低频浏览器辅助抓取器（仅用于已有账号的家长本机核对同步）。
 *
 * 严格防封号与合规边界：
 * 1. 默认可见 Chromium 窗口 + 持久化本地 Profile，复用登录态与 Cookie，减少重复登录风控。
 * 2. 所有输入、悬停、点击、翻看均带随机人类延迟，绝不发起并发接口扫描。
 * 3. 遇到 401/403/429、滑块/验证码、扫码或异常校验时立刻熔断并交还用户人工处理，绝不自动绕过或重试。
 * 4. 不向标准输出/快照文件写入姓名、考号、密码或授权令牌等敏感字段。
 */

import crypto from 'node:crypto'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import {
  extractExamIdentityFields,
  extractOwnRankFields,
  extractStudentIdentityRefs,
  withoutIdentityConflicts,
  withoutRankConflicts,
} from './k12100_rank_fields.mjs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = path.resolve(__dirname, '..')
const PLAYWRIGHT_CORE = path.join(REPO_ROOT, 'apps', 'web', 'node_modules', 'playwright-core', 'index.mjs')

const TARGET_LOGIN_URL = 'https://www.k12100.com/#/login'
const TARGET_REPORT_LIST_URL = 'https://www.k12100.com/studenting/#/jointStudentAnalysisReport/list'
const MAX_CARD_IMAGE_BYTES = 5 * 1024 * 1024
const MAX_REPORT_PDF_BYTES = 35 * 1024 * 1024

const SENSITIVE_KEY_RE =
  /^(student_?name|real_?name|user_?name|nick_?name|xm|student_?id|xuehao|exam_?no|kaohao|seat_?no|class_?name|school_?name|phone|mobile|tel|id_?card|password|pwd|token|access_?token|refresh_?token|cookie|姓名|学生姓名|学号|考号|座位号|班级|学校|手机号|身份证|studName|studentName|stuName|className|schoolName|studId|studentId|stuCode|studentNo|studentCode|classIdCode|schoolId|schoolRank|classRank|examRank|regionRank|examRankRate|schoolRankRate|groupClassRanks|examNum|actualExamNum|subjectLeader|createdBy)$/i

const CHALLENGE_KEYWORDS = ['滑块', '滑动验证', '人机验证', '安全验证', '行为验证', '图形验证码', '操作过于频繁', '访问受限', '账号异常']

function resolveDefaultK12100Dir() {
  const override = (process.env.SHUTONG_K12100_CONFIG_DIR || '').trim()
  if (override) return path.resolve(override)
  const pageboyHome = (process.env.PAGEBOY_HOME || '/media/xc/backup_ext4/pageboy-home').trim()
  const rawEnv = (process.env.SHUTONG_ENV || 'development').trim().toLowerCase()
  const envDir = rawEnv === 'prod' || rawEnv === 'production' ? 'production' : 'development'
  return path.join(pageboyHome, envDir, 'k12100')
}

function parseArgs(argv) {
  const defaultK12Dir = resolveDefaultK12100Dir()
  const args = {
    mode: 'probe',
    profileDir: path.join(defaultK12Dir, 'k12100-browser-profile'),
    probeDir: path.join(defaultK12Dir, 'probe_snapshot'),
    output: '',
    examKeyword: '',
    maxExams: 2,
    waitSeconds: 180,
    probeBrowseSeconds: 20,
    fetchCardImages: false,
    headless: false,
    probeTarget: '',
    skipFile: '',
    downloadDir: '',
  }
  for (let i = 0; i < argv.length; i += 1) {
    const key = argv[i]
    const val = argv[i + 1]
    if (key === '--mode' && val) {
      args.mode = val
      i += 1
    } else if (key === '--profile-dir' && val) {
      args.profileDir = val
      i += 1
    } else if (key === '--probe-dir' && val) {
      args.probeDir = val
      i += 1
    } else if ((key === '--output' || key === '--out') && val) {
      args.output = val
      i += 1
    } else if (key === '--exam-keyword' && val !== undefined) {
      args.examKeyword = String(val).trim()
      i += 1
    } else if (key === '--max-exams' && val) {
      const n = Number(val)
      args.maxExams = Number.isFinite(n) ? Math.max(1, Math.min(3, Math.floor(n))) : 2
      i += 1
    } else if (key === '--wait-seconds' && val) {
      const n = Number(val)
      args.waitSeconds = Number.isFinite(n) ? Math.max(15, Math.min(600, Math.floor(n))) : 180
      i += 1
    } else if (key === '--probe-browse-seconds' && val) {
      const n = Number(val)
      args.probeBrowseSeconds = Number.isFinite(n) ? Math.max(0, Math.min(300, Math.floor(n))) : 20
      i += 1
    } else if (key === '--probe-target' && val) {
      args.probeTarget = String(val).trim()
      i += 1
    } else if (key === '--skip-file' && val) {
      args.skipFile = String(val).trim()
      i += 1
    } else if (key === '--download-dir' && val) {
      args.downloadDir = String(val).trim()
      i += 1
    } else if (key === '--fetch-card-images') {
      args.fetchCardImages = true
    } else if (key === '--headless') {
      args.headless = true
    } else if (key === '--headed') {
      args.headless = false
    }
  }
  return args
}

function randInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

async function humanPause(minMs = 1800, maxMs = 3600) {
  await sleep(randInt(minMs, maxMs))
}

async function humanType(page, locator, text) {
  await locator.waitFor({ state: 'visible', timeout: 8000 })
  await locator.scrollIntoViewIfNeeded()
  await sleep(randInt(180, 420))
  await locator.click({ delay: randInt(50, 120) })
  await sleep(randInt(120, 280))
  await locator.fill('')
  await sleep(randInt(100, 220))
  await page.keyboard.type(text, { delay: randInt(90, 180) })
}

async function humanClick(locator) {
  await locator.waitFor({ state: 'visible', timeout: 8000 })
  await locator.scrollIntoViewIfNeeded()
  await sleep(randInt(180, 420))
  await locator.hover()
  await sleep(randInt(220, 520))
  await locator.click({ delay: randInt(40, 110) })
}

function sanitizeValue(value, depth = 0) {
  if (depth > 10) return '[TRUNCATED]'
  if (value === null || value === undefined) return value
  if (Array.isArray(value)) {
    return value.slice(0, 200).map(item => sanitizeValue(item, depth + 1))
  }
  if (typeof value === 'object') {
    const clean = {}
    for (const [k, v] of Object.entries(value)) {
      if (SENSITIVE_KEY_RE.test(String(k).trim())) {
        continue
      }
      clean[k] = sanitizeValue(v, depth + 1)
    }
    return clean
  }
  return value
}

async function detectPageChallenge(page) {
  try {
    const bodyText = await page.evaluate(() => (document.body?.innerText || '').slice(0, 2000))
    for (const kw of CHALLENGE_KEYWORDS) {
      if (bodyText.includes(kw)) {
        return `检测到风控或人机校验提示（关键词：${kw}）`
      }
    }
    const hasCaptchaInput = await page.locator('input[placeholder*="验证码"]').count()
    if (hasCaptchaInput > 0) {
      return '检测到图形/短信验证码输入框'
    }
  } catch {
    return ''
  }
  return ''
}

function isLoginUrl(url) {
  return String(url || '').includes('#/login')
}

async function ensureLoggedIn(page, { username, password, waitSeconds, headless, state }) {
  await page.goto(TARGET_LOGIN_URL, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await humanPause(1800, 3200)

  if (state.circuitBreaker) {
    return { loggedIn: false, reason: state.circuitBreaker }
  }

  const accountInput = page.locator('input[placeholder="请输入账号"]').first()
  const alreadySignedIn = !isLoginUrl(page.url()) && (await accountInput.count()) === 0
  if (alreadySignedIn) {
    return { loggedIn: true, reason: 'reuse_persistent_profile' }
  }

  // 若配置了学生账号密码且无验证码遮挡，则执行拟人化慢速输入并轻点登录
  const challengeBeforeLogin = await detectPageChallenge(page)
  if (headless && challengeBeforeLogin) {
    state.circuitBreaker = challengeBeforeLogin
    return { loggedIn: false, reason: challengeBeforeLogin }
  }
  if (!challengeBeforeLogin && username && password && (await accountInput.count()) > 0) {
    const studentTab = page.getByText('学生', { exact: true }).first()
    if ((await studentTab.count()) > 0) {
      try {
        await humanClick(studentTab)
        await humanPause(500, 1000)
      } catch {
        // 默认可能已选中对应端，继续后续输入
      }
    }
    await humanType(page, accountInput, username)
    await humanPause(450, 900)
    const pwdInput = page.locator('input[placeholder="请输入密码"]').first()
    await humanType(page, pwdInput, password)
    await humanPause(650, 1300)

    const loginBtn = page.locator('button:has-text("登 录"), button:has-text("登录")').first()
    if ((await loginBtn.count()) > 0) {
      await humanClick(loginBtn)
    }
  } else if (challengeBeforeLogin) {
    console.error(`[书童同步] ${challengeBeforeLogin}，请直接在可见浏览器窗口中人工完成验证与登录。`)
  } else {
    console.error('[书童同步] 请在可见浏览器窗口中确认并完成登录。')
  }

  // 等待用户完成可能的手动验证/登录跳转，绝不并发刷接口或强行重试；无头模式下遇到验证立即熔断
  const deadline = Date.now() + waitSeconds * 1000
  while (Date.now() < deadline) {
    if (state.circuitBreaker) {
      return { loggedIn: false, reason: state.circuitBreaker }
    }
    if (headless) {
      const midChallenge = await detectPageChallenge(page)
      if (midChallenge) {
        state.circuitBreaker = `${midChallenge}（无头模式不支持交互，请勾选显示可见窗口）`
        return { loggedIn: false, reason: state.circuitBreaker }
      }
    }
    if (!isLoginUrl(page.url())) {
      const checkInput = await accountInput.count()
      if (checkInput === 0) {
        await humanPause(1600, 2800)
        return { loggedIn: true, reason: 'interactive_or_credential_login' }
      }
    }
    await sleep(1500)
  }
  return { loggedIn: false, reason: `等待登录超时（${waitSeconds}s）` }
}

function collectCandidateExamArrays(node, out = []) {
  if (!node || typeof node !== 'object') return out
  if (Array.isArray(node)) {
    if (
      node.length > 0 &&
      node.every(el => el && typeof el === 'object') &&
      node.some(el => 'examName' in el || 'paperName' in el || 'title' in el || 'subjectName' in el || 'questionList' in el)
    ) {
      out.push(node)
    }
    for (const item of node) collectCandidateExamArrays(item, out)
    return out
  }
  for (const val of Object.values(node)) {
    collectCandidateExamArrays(val, out)
  }
  return out
}

function normalizeScrapedExams(xhrPayloads, domSnapshot, maxExams) {
  const exams = []
  for (const packet of xhrPayloads) {
    const arrays = collectCandidateExamArrays(packet.data)
    for (const arr of arrays) {
      for (const raw of arr) {
        const title = String(raw.examName || raw.paperName || raw.title || raw.name || '').trim()
        if (!title || exams.some(e => e.title === title)) continue
        const itemsRaw = Array.isArray(raw.questionList || raw.questions || raw.items || raw.scoreDetails)
          ? raw.questionList || raw.questions || raw.items || raw.scoreDetails
          : []
        const items = itemsRaw
          .filter(q => q && typeof q === 'object')
          .slice(0, 100)
          .map((q, idx) => ({
            question_label: String(q.questionNo || q.questionNum || q.label || q.question_label || `第${idx + 1}题`),
            earned_points: Number(q.studentScore ?? q.score ?? q.earnedPoints ?? q.earned_points ?? 0),
            max_points: Number(q.fullScore ?? q.totalScore ?? q.maxPoints ?? q.max_points ?? 2),
            stem_text: q.stem || q.content || q.questionContent || null,
            wrong_reason: q.wrongReason || q.errorReason || q.analysis || null,
          }))
        exams.push({
          external_id: String(raw.examId || raw.id || raw.paperId || title),
          title,
          subject_hint: String(raw.subjectName || raw.subject || raw.courseName || 'math'),
          exam_date: String(raw.examDate || raw.examTime || raw.createTime || '').slice(0, 10),
          earned_points: Number(raw.studentScore ?? raw.score ?? raw.totalScore ?? 0),
          max_points: Number(raw.fullScore ?? raw.paperScore ?? raw.maxPoints ?? 100),
          items,
        })
        if (exams.length >= maxExams) return exams
      }
    }
  }
  // 回退读取表格行文本摘要，供无 XHR 匹配时识别并触发 probe 提示
  void domSnapshot
  return exams.slice(0, maxExams)
}

function isAllowedCardUrl(rawUrl) {
  try {
    const parsed = new URL(String(rawUrl || '').trim())
    if (parsed.protocol !== 'https:') return false
    const host = parsed.hostname.toLowerCase()
    return host === 'k12100.com' || host.endsWith('.k12100.com') || host.endsWith('.aliyuncs.com')
  } catch {
    return false
  }
}

async function fetchValidatedCardImages(imgUrlList, subjectName) {
  const images = []
  const urls = Array.isArray(imgUrlList) ? imgUrlList.slice(0, 12) : []
  for (let i = 0; i < urls.length; i += 1) {
    const url = urls[i]
    if (!isAllowedCardUrl(url)) continue
    try {
      const resp = await fetch(url, { signal: AbortSignal.timeout(15000) })
      if (!resp.ok) continue
      const arrBuf = await resp.arrayBuffer()
      if (arrBuf.byteLength > MAX_CARD_IMAGE_BYTES || arrBuf.byteLength < 3) continue
      const bytes = Buffer.from(arrBuf)
      if (bytes[0] !== 0xff || bytes[1] !== 0xd8 || bytes[2] !== 0xff) continue
      images.push({
        filename: `${subjectName || '校考'}答_第${i + 1}页.jpg`,
        media_type: 'image/jpeg',
        data_base64: bytes.toString('base64'),
      })
    } catch {
      // 单页下载超时时保留 URL 元数据供后端安全回退，不中断其余学科采集
    }
  }
  return images
}

async function collectExamPackets(page, state, args) {
  state.collectBucket = []
  await page.goto(TARGET_REPORT_LIST_URL, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await page.locator('.list_item').first().waitFor({ state: 'visible', timeout: 25000 })
  await humanPause(1600, 2600)

  if (isLoginUrl(page.url())) {
    return { status: 'login_required', reason: '跳转报告列表后会话失效，需重新登录', exams: [] }
  }
  const ch0 = await detectPageChallenge(page)
  if (ch0 || state.circuitBreaker) {
    return { status: 'circuit_breaker', reason: state.circuitBreaker || ch0, exams: [] }
  }

  const examListEntry = [...state.collectBucket].reverse().find(b => b.endpoint === 'queryStudentExamDataList')
  const examDataList = examListEntry?.data?.data?.examData || []

  let targetLocator = page.locator('.list_item')
  if (args.examKeyword) {
    targetLocator = targetLocator.filter({ hasText: args.examKeyword })
  }
  const matchedCardsCount = await targetLocator.count()
  const processLimit = Math.min(matchedCardsCount, clampMaxExams(args.maxExams))
  if (processLimit === 0) {
    return {
      status: 'collected',
      reason: args.examKeyword
        ? `成绩列表未找到包含关键词「${args.examKeyword}」的考试记录`
        : '成绩列表中暂无可采集的考试记录',
      exams: [],
    }
  }

  const collectedExams = []
  for (let cardIdx = 0; cardIdx < processLimit; cardIdx += 1) {
    if (state.circuitBreaker) break
    if (cardIdx > 0) {
      state.collectBucket = []
      await page.goto(TARGET_REPORT_LIST_URL, { waitUntil: 'domcontentloaded', timeout: 30000 })
      await page.locator('.list_item').first().waitFor({ state: 'visible', timeout: 25000 })
      await humanPause(1800, 3000)
    }

    const card = targetLocator.nth(cardIdx)
    await card.scrollIntoViewIfNeeded()
    const cardText = await card.innerText().catch(() => '')
    const lines = cardText
      .split('\n')
      .map(s => s.trim())
      .filter(Boolean)
    const fallbackTitle = lines[0] || `k12100 校考 #${cardIdx + 1}`
    const matchedMeta =
      examDataList.find(item => {
        const name = String(item?.examName || '').trim()
        return name && (cardText.includes(name) || (!args.examKeyword && cardIdx === 0))
      }) || {}

    const examName = String(matchedMeta.examName || fallbackTitle).trim()
    const dateMatch = cardText.match(/\b(20\d{2}[-/.]\d{1,2}[-/.]\d{1,2})\b/)
    const examDateRaw = String(matchedMeta.examDate || matchedMeta.examTime || (dateMatch ? dateMatch[1] : '')).slice(0, 10)
    // 不得用抓取当天伪造平台考试日期；缺失时留空，由后端阻断自动建档。
    const examDate = examDateRaw.replace(/[/.]/g, '-') || ''

    const totalCourses = await card.locator('.course_img').count()
    const subjectsCollected = []
    for (let idx = 0; idx < totalCourses; idx += 1) {
      if (state.circuitBreaker) break
      if (idx > 0) {
        await page.goto(TARGET_REPORT_LIST_URL, { waitUntil: 'domcontentloaded', timeout: 30000 })
        await page.locator('.list_item').first().waitFor({ state: 'visible', timeout: 20000 })
        await humanPause(1800, 3000)
      }
      state.collectBucket = []
      const cover = card.locator('.course_img').nth(idx)
      await cover.scrollIntoViewIfNeeded()
      await sleep(randInt(280, 620))
      await cover.hover()
      await sleep(randInt(280, 560))
      await cover.click({ delay: randInt(50, 110) })

      const deadline = Date.now() + 14000
      while (Date.now() < deadline && !state.circuitBreaker) {
        const hasMain = state.collectBucket.some(b => b.endpoint === 'queryOneSubjectData')
        const hasSmall = state.collectBucket.some(b => b.endpoint === 'queryOneSubjectSmallQuestionData')
        const hasCard = state.collectBucket.some(b => b.endpoint === 'findStudentCard')
        if (hasMain && hasSmall && hasCard) break
        await sleep(350)
      }
      await humanPause(1400, 2400)

      const ch = await detectPageChallenge(page)
      if (ch || state.circuitBreaker) {
        return {
          status: 'circuit_breaker',
          reason: state.circuitBreaker || ch,
          exams: collectedExams,
        }
      }

      const byName = {}
      const ownRankFields = {}
      const studentIdentityRefs = new Set()
      for (const rec of state.collectBucket) {
        byName[rec.endpoint] = rec.data?.data ?? rec.data
        for (const ref of rec.studentIdentityRefs || []) studentIdentityRefs.add(ref)
        if (rec.ownRankFields) {
          for (const [key, value] of Object.entries(rec.ownRankFields)) {
            if (String(key).endsWith('__conflict')) {
              ownRankFields[key] = true
              delete ownRankFields[key.slice(0, -'__conflict'.length)]
              continue
            }
            const conflictKey = `${key}__conflict`
            if (ownRankFields[conflictKey]) continue
            if (ownRankFields[key] !== undefined && String(ownRankFields[key]) !== String(value)) {
              ownRankFields[conflictKey] = true
              delete ownRankFields[key]
              continue
            }
            ownRankFields[key] = value
          }
        }
      }
      const ownIdentityFields = {}
      for (const rec of state.collectBucket) {
        if (!rec.examIdentityFields) continue
        for (const [key, value] of Object.entries(rec.examIdentityFields)) {
          if (key.endsWith('__conflict')) {
            ownIdentityFields[key] = true
            delete ownIdentityFields[key.slice(0, -'__conflict'.length)]
            continue
          }
          const conflictKey = `${key}__conflict`
          if (ownIdentityFields[conflictKey]) continue
          if (ownIdentityFields[key] !== undefined && String(ownIdentityFields[key]) !== String(value)) {
            ownIdentityFields[conflictKey] = true
            delete ownIdentityFields[key]
            continue
          }
          ownIdentityFields[key] = value
        }
      }
      const rankOwnership = studentIdentityRefs.size === 1 ? 'verified' : studentIdentityRefs.size > 1 ? 'conflict' : 'unverified'
      const rankOwnershipBasis = studentIdentityRefs.size === 1
        ? 'single_student_ref_authenticated_subject_response'
        : studentIdentityRefs.size > 1
          ? 'conflicting_student_refs'
          : 'missing_student_ref'
      const subjInfo = { ...(byName.queryOneSubjectData || {}), ...withoutRankConflicts(ownRankFields) }
      const smallInfo = byName.queryOneSubjectSmallQuestionData || {}
      const cardInfo = byName.findStudentCard || {}
      const smallQuestions = Array.isArray(smallInfo.tableData) ? smallInfo.tableData : []
      if (!subjInfo.subjectName || smallQuestions.length === 0) {
        // 跳过全科总报告等非单科细目入口
        continue
      }

      const imgUrlList = Array.isArray(subjInfo.imgUrlList) ? subjInfo.imgUrlList : []
      const cardImages = args.fetchCardImages
        ? await fetchValidatedCardImages(imgUrlList, subjInfo.subjectName)
        : []

      subjectsCollected.push({
        ...withoutRankConflicts(ownRankFields),
        ...withoutIdentityConflicts(ownIdentityFields),
        rank_ownership: rankOwnership,
        rank_ownership_basis: rankOwnershipBasis,
        course_index: idx,
        subjectName: subjInfo.subjectName,
        subjectCode: subjInfo.subjectCode ?? null,
        score: subjInfo.score ?? null,
        fullScore: subjInfo.fullScore ?? null,
        scoreRate: subjInfo.scoreRate ?? null,
        imgUrlList,
        card_images: cardImages,
        smallQuestions,
        cardPages: cardInfo.pageVOS || [],
      })
    }

    collectedExams.push({
      examName,
      examDate,
      totalCourses,
      subjects: subjectsCollected,
    })
  }

  return {
    status: state.circuitBreaker ? 'circuit_breaker' : 'collected',
    captured_at: new Date().toISOString(),
    reason: state.circuitBreaker || `已温和采集 ${collectedExams.length} 场校考全科脱敏快照`,
    exams: collectedExams,
  }
}

async function probeTotalReport(page, context, state, args) {
  state.collectBucket = []
  const responseMeta = []
  const popupPages = []
  const downloads = []

  const attachPageWatchers = targetPage => {
    targetPage.on('download', async dl => {
      const entry = {
        suggestedFilename: dl.suggestedFilename(),
        url: dl.url().split('?')[0],
        savedPath: null,
        byteSize: 0,
        isPdf: false,
      }
      try {
        fs.mkdirSync(args.probeDir, { recursive: true, mode: 0o700 })
        const dest = path.join(args.probeDir, 'probe_downloaded_report.bin')
        await dl.saveAs(dest)
        fs.chmodSync(dest, 0o600)
        const stat = fs.statSync(dest)
        const head = Buffer.alloc(8)
        const fd = fs.openSync(dest, 'r')
        fs.readSync(fd, head, 0, 8, 0)
        fs.closeSync(fd)
        entry.savedPath = dest
        entry.byteSize = stat.size
        entry.isPdf = head.subarray(0, 5).toString('latin1') === '%PDF-'
      } catch (err) {
        entry.error = err?.message || String(err)
      }
      downloads.push(entry)
    })
  }
  attachPageWatchers(page)
  context.on('page', newPage => {
    popupPages.push({ url: newPage.url() })
    attachPageWatchers(newPage)
    newPage.on('response', resp => {
      const url = resp.url()
      if (!url.includes('k12100.com')) return
      responseMeta.push({
        source: 'popup',
        url: url.split('?')[0],
        status: resp.status(),
        contentType: resp.headers()['content-type'] || '',
        contentDisposition: resp.headers()['content-disposition'] || '',
      })
    })
  })
  page.on('response', resp => {
    const url = resp.url()
    if (!url.includes('k12100.com')) return
    const ct = resp.headers()['content-type'] || ''
    const cd = resp.headers()['content-disposition'] || ''
    if (!ct.includes('json') || cd) {
      responseMeta.push({
        source: 'main',
        url: url.split('?')[0],
        status: resp.status(),
        contentType: ct,
        contentDisposition: cd,
      })
    }
  })

  await page.goto(TARGET_REPORT_LIST_URL, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await page.locator('.list_item').first().waitFor({ state: 'visible', timeout: 25000 })
  await humanPause(1800, 2800)

  const homeCardSummary = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('.list_item'))
      .slice(0, 5)
      .map((card, idx) => ({
        index: idx,
        lines: (card.innerText || '')
          .split('\n')
          .map(s => s.trim())
          .filter(Boolean)
          .slice(0, 12),
        courses: Array.from(card.querySelectorAll('.course_img, [class*="course"], button, a')).map(el => ({
          tag: el.tagName,
          className: el.className,
          text: (el.textContent || '').trim(),
          alt: el.getAttribute('alt') || '',
          title: el.getAttribute('title') || '',
          src: (el.getAttribute('src') || '').split('/').pop(),
        })),
      }))
  })

  const homeXhrs = state.xhrRecords
    .filter(r => /exam|list|report|student/i.test(r.url))
    .map(r => ({ endpoint: r.url.split('/').pop(), url: r.url, data: r.data }))

  // 点开第一场下的「总分」入口
  state.collectBucket = []
  const firstCard = page.locator('.list_item').first()
  let clickedEntry = null
  const totalCandidates = [
    firstCard.locator('.course_img').filter({ hasText: '总分' }),
    firstCard.locator('.course_img[alt*="总分"], .course_img[title*="总分"]'),
    firstCard.locator('text=总分'),
  ]
  for (const loc of totalCandidates) {
    if ((await loc.count()) > 0) {
      const target = loc.first()
      clickedEntry = await target.evaluate(el => ({
        tag: el.tagName,
        className: el.className,
        text: (el.textContent || '').trim(),
        alt: el.getAttribute('alt') || '',
      }))
      await humanClick(target)
      break
    }
  }
  if (!clickedEntry && (await firstCard.locator('.course_img').count()) > 0) {
    const firstCourse = firstCard.locator('.course_img').first()
    clickedEntry = await firstCourse.evaluate(el => ({
      fallbackFirstCourse: true,
      tag: el.tagName,
      className: el.className,
      text: (el.textContent || '').trim(),
    }))
    await humanClick(firstCourse)
  }

  await humanPause(3500, 5000)
  const activePage = context.pages()[context.pages().length - 1] || page
  await activePage.waitForLoadState('domcontentloaded').catch(() => {})
  await humanPause(1500, 2200)

  const detailDom = await activePage.evaluate(() => ({
    url: location.href,
    title: document.title,
    buttonsAndLinks: Array.from(document.querySelectorAll('a, button, [role="button"], .el-button, span, div'))
      .filter(el => {
        const t = (el.textContent || '').trim()
        return t.length > 0 && t.length <= 30 && /下载|导出|报告|PDF|打印|总分|成绩/i.test(t)
      })
      .slice(0, 40)
      .map(el => ({
        tag: el.tagName,
        className: String(el.className || '').slice(0, 80),
        text: (el.textContent || '').trim(),
        href: el.getAttribute('href') || '',
      })),
    iframes: Array.from(document.querySelectorAll('iframe, embed, object')).map(el => ({
      tag: el.tagName,
      src: (el.getAttribute('src') || el.getAttribute('data') || '').slice(0, 120),
    })),
  }))

  const detailXhrsBeforeDownload = state.collectBucket.map(b => ({ endpoint: b.endpoint, url: b.url, data: b.data }))

  // 点「报告打印」按钮，观察跳转/弹窗/下载按钮与 XHR
  state.collectBucket = []
  let printClickInfo = null
  const printBtn = activePage.locator('button:has-text("报告打印"), .mm_btn:has-text("报告打印")').first()
  if ((await printBtn.count()) > 0) {
    printClickInfo = await printBtn.evaluate(el => ({
      tag: el.tagName,
      className: String(el.className || ''),
      text: (el.textContent || '').trim(),
    }))
    await humanClick(printBtn)
    await humanPause(3500, 5000)
  }

  const afterPrintPage = context.pages()[context.pages().length - 1] || activePage
  await afterPrintPage.waitForLoadState('domcontentloaded').catch(() => {})
  const printDom = await afterPrintPage.evaluate(() => ({
    url: location.href,
    textPreview: (document.body?.innerText || '').slice(0, 1000),
    buttonsAndLinks: Array.from(document.querySelectorAll('a, button, [role="button"], .el-button, input[type="checkbox"], label'))
      .map(el => ({
        tag: el.tagName,
        className: String(el.className || '').slice(0, 80),
        text: (el.textContent || '').trim().slice(0, 60),
        href: el.getAttribute('href') || '',
      }))
      .filter(item => item.text)
      .slice(0, 60),
  }))
  const printXhrs = state.collectBucket.map(b => ({ endpoint: b.endpoint, url: b.url, data: b.data }))

  // 若出现下载/生成PDF/导出报告按钮，轻点一次并等待下载或 XHR（最多 25 秒）
  state.collectBucket = []
  let downloadClickInfo = null
  const dlLocators = [
    afterPrintPage.locator('button:has-text("下载"), button:has-text("生成"), button:has-text("导出报告"), button:has-text("打印"), a:has-text("下载")'),
  ]
  for (const loc of dlLocators) {
    const count = await loc.count()
    for (let i = 0; i < count; i += 1) {
      const btn = loc.nth(i)
      const txt = ((await btn.textContent().catch(() => '')) || '').trim()
      if (txt === '报告打印') continue
      const visible = await btn.isVisible().catch(() => false)
      if (!visible) continue
      downloadClickInfo = {
        text: txt,
        className: await btn.getAttribute('class').catch(() => ''),
      }
      await humanClick(btn)
      const waitEnd = Date.now() + 25000
      while (Date.now() < waitEnd && downloads.length === 0 && !state.circuitBreaker) {
        await sleep(800)
      }
      break
    }
    if (downloadClickInfo) break
  }

  fs.mkdirSync(args.probeDir, { recursive: true, mode: 0o700 })
  const outPath = path.join(args.probeDir, 'total_report_probe.json')
  const payload = {
    status: state.circuitBreaker ? 'circuit_breaker' : 'probed',
    reason: state.circuitBreaker || 'ok',
    captured_at: new Date().toISOString(),
    home_cards_count: homeCardSummary.length,
    home_cards: homeCardSummary,
    home_xhrs: homeXhrs,
    clicked_entry: clickedEntry,
    detail_dom: detailDom,
    detail_xhrs_before_download: detailXhrsBeforeDownload,
    print_click: printClickInfo,
    print_dom: printDom,
    print_xhrs: printXhrs,
    download_click: downloadClickInfo,
    download_xhrs: state.collectBucket.map(b => ({ endpoint: b.endpoint, url: b.url, data: b.data })),
    non_json_responses: responseMeta,
    popups: popupPages,
    downloads,
  }
  fs.writeFileSync(outPath, JSON.stringify(payload, null, 2), { mode: 0o600 })
  return { ...payload, probe_file: outPath }
}

function readSkipPayload(skipFile) {
  if (!skipFile || !fs.existsSync(skipFile)) return { skipSet: new Set(), completeIdentities: [] }
  try {
    const raw = JSON.parse(fs.readFileSync(skipFile, 'utf-8'))
    const ids = Array.isArray(raw?.external_exam_ids) ? raw.external_exam_ids : []
    const identities = Array.isArray(raw?.complete_identities) ? raw.complete_identities : []
    return {
      skipSet: new Set(ids.map(v => String(v || '').trim()).filter(Boolean)),
      completeIdentities: identities.filter(item => item && typeof item === 'object'),
    }
  } catch {
    return { skipSet: new Set(), completeIdentities: [] }
  }
}

function normGradeShort(raw) {
  const text = String(raw || '').trim()
  if (!text) return ''
  return { 初三: '9', 九年级: '9', 初二: '8', 八年级: '8', 初一: '7', 七年级: '7' }[text] || text
}

function normAcademicYear(raw) {
  const text = String(raw || '').trim()
  if (!text) return ''
  const full = text.match(/(20\d{2})\s*[-—~]\s*(20\d{2})/)
  if (full) return `${full[1]}-${full[2]}`
  const short = text.match(/(\d{2})\s*[-—~]\s*(\d{2})/)
  if (short && Number(short[2]) === Number(short[1]) + 1) return `20${short[1]}-20${short[2]}`
  return text
}

function normExamTypeAndSeq(rawType, examName) {
  const joined = `${String(rawType || '').trim()} ${String(examName || '').trim()}`
  if (/统一练习/.test(joined)) {
    const seqMap = { 一: 1, 1: 1, 二: 2, 2: 2, 三: 3, 3: 3 }
    const m = joined.match(/统一练习\s*([一二三123])/)
    return { examType: 'unified_practice', examSequence: m ? (seqMap[m[1]] ?? null) : null }
  }
  if (/期中/.test(joined)) return { examType: 'midterm', examSequence: null }
  if (/期末/.test(joined)) return { examType: 'final', examSequence: null }
  if (/月考/.test(joined)) return { examType: 'monthly', examSequence: null }
  return { examType: '', examSequence: null }
}

function findMatchingCompleteIdentity(homeExam, completeIdentities) {
  const year = normAcademicYear(homeExam.academic_year) || normAcademicYear(homeExam.exam_name)
  const grade = normGradeShort(homeExam.grade) || normGradeShort((homeExam.exam_name || '').match(/初[一二三]|[七八九]年级/)?.[0] || '')
  const { examType, examSequence } = normExamTypeAndSeq(homeExam.exam_type, homeExam.exam_name)
  const homeYm = String(homeExam.exam_date || '').slice(0, 7)
  if (!year || !grade || !examType) return null
  return (
    completeIdentities.find(entry => {
      if (entry.academic_year !== year || entry.grade !== grade || entry.exam_type !== examType) return false
      if (examType === 'unified_practice' || entry.exam_sequence != null || examSequence != null) {
        if ((entry.exam_sequence ?? null) !== (examSequence ?? null)) return false
      }
      if (entry.exam_date_ym && homeYm && entry.exam_date_ym !== homeYm) return false
      return true
    }) || null
  )
}

function normalizeHomeDateText(raw) {
  const text = String(raw || '').trim()
  if (!text) return ''
  const full = text.match(/(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})/)
  if (full) {
    return `${full[1]}-${String(Number(full[2])).padStart(2, '0')}-${String(Number(full[3])).padStart(2, '0')}`
  }
  const month = text.match(/(20\d{2})[-/.年](\d{1,2})(?!\d)/)
  if (month) {
    return `${month[1]}-${String(Number(month[2])).padStart(2, '0')}`
  }
  return ''
}

function extractHomeExams(xhrRecords, cardDomList) {
  const listRecord = [...xhrRecords].reverse().find(r => String(r.url || '').endsWith('/queryStudentExamDataList'))
  const payload = listRecord?.data?.data || {}
  const examTypeMap = new Map()
  for (const item of Array.isArray(payload.examTypeData) ? payload.examTypeData : []) {
    if (item && item.examType !== undefined && item.examName) {
      examTypeMap.set(String(item.examType), String(item.examName).trim())
    }
  }
  const rawList = Array.isArray(payload.examData) ? payload.examData : []
  if (rawList.length > 0) {
    return rawList.map((entry, idx) => {
      const ex = entry?.examData && typeof entry.examData === 'object' ? entry.examData : entry || {}
      const subjects = Array.isArray(ex.examSubjectVoList) ? ex.examSubjectVoList : []
      const totalIdx = subjects.findIndex(s => Number(s?.isTotal) === 1 || String(s?.subjectName || '').trim() === '总分')
      const domFallback = cardDomList[idx] || {}
      const domText = (domFallback.lines || []).join(' ')
      const domDateMatch = domText.match(/考试时间[:：]?\s*([^\s]+)/)
      const domGradeMatch = domText.match(/年级[:：]?\s*([^\s]+)/)
      const examDate = normalizeHomeDateText(ex.examDate || ex.examTime || (domDateMatch ? domDateMatch[1] : '') || domText)
      return {
        card_index: idx,
        external_exam_id: String(ex._id || ex.examId || ex.id || '').trim(),
        exam_name: String(ex.examName || domFallback.lines?.[1] || domFallback.lines?.[0] || '').trim(),
        exam_date: examDate,
        grade: String(ex.gradeName || ex.gradeCode || (domGradeMatch ? domGradeMatch[1] : '') || '').trim(),
        academic_year: String(ex.schoolYearCode || ex.academicYear || '').trim(),
        exam_type: examTypeMap.get(String(ex.examType ?? '')) || String(domFallback.lines?.[0] || '').trim(),
        total_course_index: totalIdx >= 0 ? totalIdx : 0,
      }
    })
  }
  return cardDomList.map((card, idx) => {
    const lines = card.lines || []
    const joined = lines.join(' ')
    const dateMatch = joined.match(/考试时间[:：]?\s*([^\s]+)/)
    const gradeMatch = joined.match(/年级[:：]?\s*([^\s]+)/)
    const yearMatch = joined.match(/(20\d{2})\s*[-—]\s*(20\d{2})|(\d{2})\s*[-—]\s*(\d{2})学年/)
    let academicYear = ''
    if (yearMatch) {
      academicYear = yearMatch[1] ? `${yearMatch[1]}-${yearMatch[2]}` : `20${yearMatch[3]}-20${yearMatch[4]}`
    }
    return {
      card_index: idx,
      external_exam_id: '',
      exam_name: lines.find(l => l.includes('考试') || l.includes('练习') || l.includes('学年')) || lines[0] || '',
      exam_date: normalizeHomeDateText(dateMatch ? dateMatch[1] : joined),
      grade: gradeMatch ? gradeMatch[1] : '',
      academic_year: academicYear,
      exam_type: lines[0] || '',
      total_course_index: 0,
    }
  })
}

async function ensureOnReportList(page) {
  if (!String(page.url() || '').includes('/jointStudentAnalysisReport/list')) {
    await page.goto(TARGET_REPORT_LIST_URL, { waitUntil: 'domcontentloaded', timeout: 30000 })
  }
  await page.locator('.list_item').first().waitFor({ state: 'visible', timeout: 25000 })
  await humanPause(1600, 2600)
}

async function downloadTotalReports(page, context, state, args) {
  const { skipSet, completeIdentities } = readSkipPayload(args.skipFile)
  const downloadDir = args.downloadDir || path.join(resolveDefaultK12100Dir(), 'tmp_reports')
  fs.mkdirSync(downloadDir, { recursive: true, mode: 0o700 })
  try {
    fs.chmodSync(downloadDir, 0o700)
  } catch {
    // 忽略不支持 chmod 的文件系统
  }

  await ensureOnReportList(page)
  if (isLoginUrl(page.url())) {
    return { status: 'login_required', reason: '会话已失效，需重新登录', home_exams: [], downloads: [], failures: [] }
  }
  const ch0 = await detectPageChallenge(page)
  if (ch0 || state.circuitBreaker) {
    return { status: 'circuit_breaker', reason: state.circuitBreaker || ch0, home_exams: [], downloads: [], failures: [] }
  }

  // 等待首页列表 XHR 落桶（首次跳转时可能与登录重定向并发）
  const xhrDeadline = Date.now() + 6000
  while (Date.now() < xhrDeadline) {
    if (state.xhrRecords.some(r => String(r.url || '').endsWith('/queryStudentExamDataList'))) break
    await sleep(300)
  }

  const cardDomList = await page.evaluate(() =>
    Array.from(document.querySelectorAll('.list_item')).map(card => ({
      lines: (card.innerText || '')
        .split('\n')
        .map(s => s.trim())
        .filter(Boolean)
        .slice(0, 12),
    })),
  )

  const homeExamsRaw = extractHomeExams(state.xhrRecords, cardDomList)
  const homeExams = homeExamsRaw.map(item => {
    const matchedById = Boolean(item.external_exam_id && skipSet.has(item.external_exam_id))
    const matchedIdentity = matchedById ? null : findMatchingCompleteIdentity(item, completeIdentities)
    return {
      ...item,
      already_synced: Boolean(matchedById || matchedIdentity),
      matched_report_id: matchedIdentity?.report_id || null,
    }
  })
  if (homeExams.length === 0) {
    return {
      status: 'collected',
      reason: 'K12100_NO_EXAMS',
      home_exams: [],
      downloads: [],
      failures: [],
    }
  }

  const targets = homeExams.filter(item => !item.already_synced).slice(0, clampMaxExams(args.maxExams))
  if (targets.length === 0) {
    return {
      status: 'collected',
      captured_at: new Date().toISOString(),
      reason: `首页共 ${homeExams.length} 场，全部已有完整同步记录，未进入详情页或触发任何下载`,
      home_exams: homeExams,
      downloads: [],
      failures: [],
    }
  }
  const downloads = []
  const failures = []
  let lastStatus = 'collecting'
  let lastReason = `首页共 ${homeExams.length} 场，准备下载 ${targets.length} 场`
  let finalWritten = false

  function flushProgress(status, reason) {
    lastStatus = status
    if (reason) lastReason = reason
    if (!args.output) return
    const payload = {
      status,
      captured_at: new Date().toISOString(),
      reason: reason || '',
      home_exams: homeExams,
      downloads,
      failures,
    }
    const tmpOut = `${args.output}.tmp`
    try {
      fs.writeFileSync(tmpOut, JSON.stringify(payload, null, 2), { mode: 0o600 })
      try {
        fs.chmodSync(tmpOut, 0o600)
      } catch {
        // 忽略不支持 chmod 的文件系统
      }
      fs.renameSync(tmpOut, args.output)
    } catch {
      try {
        fs.writeFileSync(args.output, JSON.stringify(payload, null, 2), { mode: 0o600 })
      } catch {
        // 忽略局部写盘异常
      }
    }
  }

  flushProgress('collecting', lastReason)

  try {
    for (let i = 0; i < targets.length; i += 1) {
      const target = targets[i]
      if (state.circuitBreaker) break
      if (i > 0) {
        await ensureOnReportList(page)
        if (isLoginUrl(page.url())) {
          finalWritten = true
          return { status: 'login_required', reason: '翻页回列表时会话失效', home_exams: homeExams, downloads, failures }
        }
        const ch = await detectPageChallenge(page)
        if (ch || state.circuitBreaker) {
          finalWritten = true
          return { status: 'circuit_breaker', reason: state.circuitBreaker || ch, home_exams: homeExams, downloads, failures }
        }
      }

      let card = page.locator('.list_item').nth(target.card_index)
      if (target.exam_name) {
        const byName = page.locator('.list_item').filter({ hasText: target.exam_name })
        if ((await byName.count()) === 1) {
          card = byName.first()
        } else if ((await byName.count()) > 1 && target.exam_date) {
          const byDate = byName.filter({ hasText: target.exam_date })
          if ((await byDate.count()) >= 1) card = byDate.first()
        }
      }

      const coursesCount = await card.locator('.course_img').count()
      if (coursesCount === 0) {
        failures.push({
          external_exam_id: target.external_exam_id,
          exam_name: target.exam_name,
          code: 'K12100_TOTAL_ENTRY_MISSING',
          reason: '未找到场次下的总分入口',
        })
        flushProgress('collecting', `已下载 ${downloads.length} 份（${target.exam_name || '场次'}缺少总分入口）`)
        continue
      }
      const courseIdx = target.total_course_index >= 0 && target.total_course_index < coursesCount ? target.total_course_index : 0
      await humanClick(card.locator('.course_img').nth(courseIdx))
      await humanPause(2000, 3200)

      const detailPage = context.pages()[context.pages().length - 1] || page
      await detailPage.waitForLoadState('domcontentloaded').catch(() => {})
      const totalTab = detailPage.locator('.tag_item').filter({ hasText: '总分' }).first()
      if ((await totalTab.count()) > 0) {
        const cls = (await totalTab.getAttribute('class').catch(() => '')) || ''
        if (!cls.includes('active')) {
          await humanClick(totalTab)
          await humanPause(1400, 2200)
        }
      }

      const printBtn = detailPage.locator('button.mm_btn:has-text("报告打印"), button:has-text("报告打印")').first()
      try {
        await printBtn.waitFor({ state: 'visible', timeout: 20000 })
      } catch {
        failures.push({
          external_exam_id: target.external_exam_id,
          exam_name: target.exam_name,
          code: 'K12100_REPORT_PRINT_MISSING',
          reason: '总分页面未出现“报告打印”按钮',
        })
        flushProgress('collecting', `已下载 ${downloads.length} 份（${target.exam_name || '场次'}缺少报告打印按钮）`)
        continue
      }

      state.collectBucket = []
      await humanClick(printBtn)
      await humanPause(2500, 4000)

      const printPage = context.pages()[context.pages().length - 1] || detailPage
      await printPage.locator('.el-loading-mask').waitFor({ state: 'hidden', timeout: 25000 }).catch(() => {})
      const dlBtn = printPage.locator('button.download_btn, button:has-text("下载PDF")').first()
      try {
        await dlBtn.waitFor({ state: 'visible', timeout: 25000 })
      } catch {
        failures.push({
          external_exam_id: target.external_exam_id,
          exam_name: target.exam_name,
          code: 'K12100_DOWNLOAD_BUTTON_MISSING',
          reason: '报告打印页未出现“下载PDF”按钮',
        })
        flushProgress('collecting', `已下载 ${downloads.length} 份（${target.exam_name || '场次'}缺少下载PDF按钮）`)
        continue
      }
      await humanPause(1200, 2200)

      const chBeforeDl = await detectPageChallenge(printPage)
      if (chBeforeDl || state.circuitBreaker) {
        finalWritten = true
        return {
          status: 'circuit_breaker',
          reason: state.circuitBreaker || chBeforeDl,
          home_exams: homeExams,
          downloads,
          failures,
        }
      }

      try {
        const [download] = await Promise.all([
          printPage.waitForEvent('download', { timeout: 60000 }),
          humanClick(dlBtn),
        ])
        const destPath = path.join(downloadDir, `report_${i}_${target.external_exam_id || 'exam'}.pdf`)
        await download.saveAs(destPath)
        fs.chmodSync(destPath, 0o600)
        const stat = fs.statSync(destPath)
        const bytes = fs.readFileSync(destPath)
        const isPdf = stat.size > 0 && stat.size <= MAX_REPORT_PDF_BYTES && bytes.subarray(0, 5).toString('latin1') === '%PDF-'
        if (!isPdf) {
          fs.unlinkSync(destPath)
          failures.push({
            external_exam_id: target.external_exam_id,
            exam_name: target.exam_name,
            code: 'K12100_REPORT_NOT_PDF',
            reason: `下载结果不是合法 PDF 或超出 ${MAX_REPORT_PDF_BYTES} 字节限制`,
          })
          flushProgress('collecting', `已下载 ${downloads.length} 份（${target.exam_name || '场次'}校验失败）`)
          continue
        }
        const digest = crypto.createHash('sha256').update(bytes).digest('hex')
        const safeName = `${(target.exam_name || '校考').replace(/[/\\:*?"<>|]+/g, '_')}_分析报告册.pdf`
        downloads.push({
          external_exam_id: target.external_exam_id,
          exam_name: target.exam_name,
          exam_date: target.exam_date,
          grade: target.grade,
          academic_year: target.academic_year,
          exam_type: target.exam_type,
          file: destPath,
          suggested_filename: safeName,
          byte_size: stat.size,
          sha256: digest,
        })
        flushProgress('collecting', `已下载 ${downloads.length}/${targets.length} 份分析报告`)
      } catch (err) {
        failures.push({
          external_exam_id: target.external_exam_id,
          exam_name: target.exam_name,
          code: 'K12100_REPORT_DOWNLOAD_FAILED',
          reason: err?.message || '下载报告超时或失败',
        })
        flushProgress('collecting', `已下载 ${downloads.length} 份（${target.exam_name || '场次'}下载失败）`)
      }
    }

    finalWritten = true
    return {
      status: state.circuitBreaker ? 'circuit_breaker' : 'collected',
      captured_at: new Date().toISOString(),
      reason: state.circuitBreaker || `首页共 ${homeExams.length} 场，本次处理 ${targets.length} 场，成功下载 ${downloads.length} 份报告`,
      home_exams: homeExams,
      downloads,
      failures,
    }
  } catch (err) {
    lastStatus = 'interrupted'
    lastReason = err?.message || '浏览器下载过程中断'
    throw err
  } finally {
    if (!finalWritten && args.output && (homeExams.length > 0 || downloads.length > 0 || failures.length > 0)) {
      flushProgress(lastStatus, lastReason)
    }
  }
}

function clampMaxExams(val) {
  return Math.max(1, Math.min(3, Math.floor(Number(val) || 1)))
}

async function main() {
  const args = parseArgs(process.argv.slice(2))
  const { chromium } = await import(pathToFileURL(PLAYWRIGHT_CORE).href)

  fs.mkdirSync(args.profileDir, { recursive: true, mode: 0o700 })
  try {
    fs.chmodSync(args.profileDir, 0o700)
  } catch {
    // 忽略不支持 chmod 的文件系统
  }

  const state = {
    circuitBreaker: '',
    xhrRecords: [],
    collectBucket: [],
  }

  const context = await chromium.launchPersistentContext(args.profileDir, {
    headless: args.headless,
    viewport: { width: 1280, height: 860 },
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
  })

  try {
    const page = context.pages()[0] || (await context.newPage())
    page.on('response', async resp => {
      const url = resp.url()
      if (!url.includes('k12100.com')) return
      const status = resp.status()
      if (status === 401 || status === 403 || status === 429) {
        state.circuitBreaker = `上游返回 HTTP ${status}（${url.split('?')[0]}），已立即熔断止损`
        return
      }
      const ctype = (resp.headers()['content-type'] || '').toLowerCase()
      if (!ctype.includes('json')) return
      try {
        const json = await resp.json()
        const ownRankFields = extractOwnRankFields(json)
        const examIdentityFields = extractExamIdentityFields(json)
        const studentIdentityRefs = [...extractStudentIdentityRefs(json)]
        const cleanJson = sanitizeValue(json)
        const baseUrl = url.split('?')[0]
        state.xhrRecords.push({
          url: baseUrl,
          status,
          captured_at: new Date().toISOString(),
          data: cleanJson,
        })
        if (Array.isArray(state.collectBucket)) {
          state.collectBucket.push({
            endpoint: baseUrl.split('/').pop(),
            url: baseUrl,
            data: cleanJson,
            ownRankFields,
            examIdentityFields,
            studentIdentityRefs,
          })
        }
      } catch {
        // 非法或空响应体静默忽略
      }
    })

    const loginRes = await ensureLoggedIn(page, {
      username: process.env.K12100_USERNAME || '',
      password: process.env.K12100_PASSWORD || '',
      waitSeconds: args.waitSeconds,
      headless: args.headless,
      state,
    })

    if (!loginRes.loggedIn) {
      const result = {
        status: state.circuitBreaker ? 'circuit_breaker' : 'login_incomplete',
        reason: loginRes.reason,
        url: page.url(),
        exams: [],
      }
      if (args.output) fs.writeFileSync(args.output, JSON.stringify(result, null, 2), { mode: 0o600 })
      else process.stdout.write(JSON.stringify(result, null, 2) + '\n')
      process.exitCode = state.circuitBreaker ? 3 : 2
      return
    }

    if (args.mode === 'collect') {
      const result = await collectExamPackets(page, state, args)
      if (args.output) fs.writeFileSync(args.output, JSON.stringify(result, null, 2), { mode: 0o600 })
      else process.stdout.write(JSON.stringify(result, null, 2) + '\n')
      if (result.status === 'login_required') process.exitCode = 2
      else if (result.status === 'circuit_breaker') process.exitCode = 3
      return
    }

    if (args.mode === 'reports') {
      const result = await downloadTotalReports(page, context, state, args)
      if (args.output) fs.writeFileSync(args.output, JSON.stringify(result, null, 2), { mode: 0o600 })
      else process.stdout.write(JSON.stringify(result, null, 2) + '\n')
      if (result.status === 'login_required') process.exitCode = 2
      else if (result.status === 'circuit_breaker') process.exitCode = 3
      return
    }

    if (args.mode === 'probe') {
      if (args.probeTarget === 'total-report') {
        const result = await probeTotalReport(page, context, state, args)
        if (args.output) fs.writeFileSync(args.output, JSON.stringify(result, null, 2), { mode: 0o600 })
        else process.stdout.write(JSON.stringify(result, null, 2) + '\n')
        if (result.status === 'circuit_breaker') process.exitCode = 3
        return
      }
      if (args.probeBrowseSeconds > 0) {
        console.error(
          `[书童探测] 登录成功！请在接下来 ${args.probeBrowseSeconds} 秒内像平时一样手工点开 1~2 场考试成绩与错题详情页面，系统仅静默记录脱敏后的结构快照…`
        )
        const waitEnd = Date.now() + args.probeBrowseSeconds * 1000
        while (Date.now() < waitEnd && !state.circuitBreaker) {
          await sleep(1000)
        }
      }
      const domSnapshot = await page.evaluate(() => ({
        title: document.title,
        url: location.href,
        links: Array.from(document.querySelectorAll('a, button, .el-menu-item, .el-submenu__title'))
          .map(el => (el.textContent || '').trim())
          .filter(Boolean)
          .slice(0, 80),
        tables: Array.from(document.querySelectorAll('table')).map(tbl =>
          Array.from(tbl.querySelectorAll('tr'))
            .slice(0, 15)
            .map(tr => Array.from(tr.querySelectorAll('th,td')).map(td => (td.textContent || '').trim()))
        ),
      }))
      fs.mkdirSync(args.probeDir, { recursive: true, mode: 0o700 })
      const summaryFile = path.join(args.probeDir, 'probe_summary.json')
      const xhrFile = path.join(args.probeDir, 'xhr_shapes.json')
      const summary = {
        status: state.circuitBreaker ? 'circuit_breaker' : 'probed',
        reason: state.circuitBreaker || 'ok',
        captured_at: new Date().toISOString(),
        dom_snapshot: domSnapshot,
        xhr_count: state.xhrRecords.length,
        xhr_endpoints: [...new Set(state.xhrRecords.map(r => r.url))],
      }
      fs.writeFileSync(summaryFile, JSON.stringify(summary, null, 2), { mode: 0o600 })
      fs.writeFileSync(xhrFile, JSON.stringify(state.xhrRecords, null, 2), { mode: 0o600 })
      const out = { ...summary, summary_file: summaryFile, xhr_file: xhrFile }
      if (args.output) fs.writeFileSync(args.output, JSON.stringify(out, null, 2), { mode: 0o600 })
      else process.stdout.write(JSON.stringify(out, null, 2) + '\n')
      return
    }

    // sync 模式：温和翻看页面 1~2 次，严格不超过 maxExams 场，无并发请求
    await humanPause(1800, 3400)
    await page.evaluate(() => window.scrollBy(0, 320))
    await humanPause(1600, 2800)

    const challengeAfterNav = await detectPageChallenge(page)
    if (challengeAfterNav || state.circuitBreaker) {
      const result = {
        status: 'circuit_breaker',
        reason: state.circuitBreaker || challengeAfterNav,
        url: page.url(),
        exams: [],
      }
      if (args.output) fs.writeFileSync(args.output, JSON.stringify(result, null, 2), { mode: 0o600 })
      else process.stdout.write(JSON.stringify(result, null, 2) + '\n')
      process.exitCode = 3
      return
    }

    const domSnapshot = await page.evaluate(() => ({
      url: location.href,
      text_preview: (document.body?.innerText || '').slice(0, 1200),
    }))
    const exams = normalizeScrapedExams(state.xhrRecords, domSnapshot, args.maxExams)
    const status = exams.length > 0 ? 'synced_raw' : 'needs_probe'
    const result = {
      status,
      reason:
        exams.length > 0
          ? `被动捕获并抽取 ${exams.length} 场校考记录`
          : '当前首页与被动 XHR 未匹配到结构化成绩列表，请先运行 probe 子命令点开成绩页记录结构',
      url: page.url(),
      xhr_count: state.xhrRecords.length,
      exams,
    }
    if (args.output) fs.writeFileSync(args.output, JSON.stringify(result, null, 2), { mode: 0o600 })
    else process.stdout.write(JSON.stringify(result, null, 2) + '\n')
  } finally {
    await context.close()
  }
}

main().catch(err => {
  console.error('[书童抓取异常]', err?.message || String(err))
  process.exit(1)
})
