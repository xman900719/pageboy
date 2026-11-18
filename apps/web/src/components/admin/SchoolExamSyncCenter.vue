<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  ApiError,
  describeError,
  type ApiClient,
  type K12100BackfillResult,
  type K12100ReportJobResult,
  type K12100RuntimeStatus,
  type K12100SyncedReportSummary,
  type K12100SyncJob,
  type K12100SyncReadiness,
  type SchoolExamDetail,
  type SchoolExamPaper,
  type SchoolExamRanksPayload,
  type SchoolExamScanRun,
  type SchoolExamSyncCenter,
  type SchoolPaperFieldComparison,
  type SchoolPaperMatchCandidate,
  type SchoolSubject,
} from '../../api'
import { fmtBytes, fmtPoints, shortTime } from '../../copy'
import {
  deriveReviewCoverage,
  formatPaperExamIdentity,
  formatPaperSubject,
  formatRankValue,
  getMatchMeta,
  getPaperNextStep,
  getReportActionMeta,
  RANK_SCOPE_LABELS,
  summarizeReportJob,
  type SyncStep,
} from '../../examSync'
import HelpBubble from '../HelpBubble.vue'
import type { NoticeTone } from '../Notice.vue'
import StepFlowWorkspace from './StepFlowWorkspace.vue'
import type { StepDefinition, StepFlowContext } from './stepFlow'

type Notify = (text: string, tone?: NoticeTone) => void
type OpenTab = 'scores' | 'papers' | 'items' | 'analysis'

const props = defineProps<{
  client: ApiClient
  subject: SchoolSubject
  notify: Notify
  selectedExamId?: string | null
}>()

const emit = defineEmits<{
  (e: 'open-exam', examId: string, tab: OpenTab): void
  (e: 'papers-imported', examId: string): void
}>()

const PAPER_STATUS_META: Record<string, { label: string; tone: string }> = {
  needs_review: { label: '待核对', tone: 'wait' },
  matched: { label: '已匹配', tone: 'mid' },
  imported: { label: '已入档', tone: 'good' },
  rejected: { label: '已忽略', tone: 'subtle' },
}

const EXAM_TYPE_LABELS: Record<string, string> = {
  monthly: '月考',
  midterm: '期中',
  final: '期末',
  unified_practice: '统一练习',
  other: '其他',
}
function fmtExamMonth(value?: string | null): string {
  const text = String(value || '').trim()
  return /^\d{4}-\d{2}/.test(text) ? text.slice(0, 7) : (text || '')
}

const CONFIDENCE_LABELS: Record<string, string> = { high: '高置信', medium: '中等置信', low: '低置信' }
const FIELD_STATUS_LABELS: Record<string, string> = { found: '已识别', missing: '缺失', ambiguous: '冲突' }
const FIELD_LABELS: Record<string, string> = {
  academic_year: '学年度',
  grade: '年级',
  exam_type: '考试类型',
  subject: '学科',
  exam_date: '考试日期',
}
const SOURCE_KIND_LABELS: Record<string, string> = {
  manual: '手工建档',
  k12100: '平台同步',
  local_scan: '本地扫描',
  import: '离线导入',
}
const CORE_COMPARISON_FIELDS = new Set(['subject', 'academic_year', 'grade', 'exam_type', 'exam_date'])
const SUBJECT_LABELS: Record<string, string> = {
  math: '数学',
  chinese: '语文',
  english: '英语',
  physics: '物理',
  ethics: '道德与法治',
}
const COMPARISON_LABELS: Record<string, string> = {
  match: '一致',
  conflict: '冲突',
  different: '名称不同',
  missing: '缺失',
}

const center = ref<SchoolExamSyncCenter | null>(null)
const loading = ref(false)
const loadError = ref('')
const activeStep = ref<SyncStep>(1)
const selectedPaperId = ref<string | null>(null)
const candidateExamId = ref('')
const manualConfirmChecked = ref(false)
const scanning = ref(false)
const acquiring = ref(false)
const matching = ref(false)
const importing = ref(false)
const rejecting = ref(false)
const actionNotice = ref('')
const actionTone = ref<'info' | 'caution' | 'error'>('info')

const runtime = ref<K12100RuntimeStatus | null>(null)
const job = ref<K12100SyncJob | null>(null)
const lastResult = ref<K12100BackfillResult | null>(null)
const lastReportResult = ref<K12100ReportJobResult | null>(null)
const collectionError = ref('')
const startingJob = ref(false)
const focusedExamId = ref<string | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null

const reviewDetail = ref<SchoolExamDetail | null>(null)
const reviewRanks = ref<SchoolExamRanksPayload | null>(null)
const reviewLoading = ref(false)
const confirmTotalInput = ref<number | ''>('')
const confirmTotalAcknowledged = ref(false)
const confirmingTotal = ref(false)
const confirmingRankId = ref<string | null>(null)
const reviewError = ref('')

const advancedOpen = ref(false)
const showBrowser = ref(true)
const bundleInputRef = ref<HTMLInputElement | null>(null)
const importingBundle = ref(false)

function fmtGradeLabel(grade: string | null | undefined): string {
  const raw = String(grade || '').trim()
  if (!raw) return ''
  return raw.endsWith('年级') ? raw : `${raw}年级`
}
const bundleError = ref('')

const papers = computed(() => center.value?.papers ?? [])
const selectedPaper = computed(
  () => papers.value.find(paper => paper.id === selectedPaperId.value) ?? null,
)
const matchedPaperCount = computed(
  () => papers.value.filter(paper => paper.status === 'matched' || paper.status === 'imported').length,
)
const isJobActive = computed(
  () => job.value?.state === 'queued' || job.value?.state === 'collecting' || job.value?.state === 'backfilling',
)
const currentExamId = computed(() => focusedExamId.value ?? selectedPaper.value?.school_exam_id ?? props.selectedExamId ?? null)
const currentExamTitle = computed(
  () => reviewDetail.value?.title ?? selectedPaper.value?.exam?.title ?? '尚未关联考试档案',
)
const currentResultRow = computed(() => {
  const result = lastResult.value
  if (!result) return null
  return result.subjects.find(row => row.exam_id === currentExamId.value) ?? result.subjects[0] ?? null
})
const reportSummary = computed(() => summarizeReportJob(lastReportResult.value))
const syncedReports = computed<K12100SyncedReportSummary[]>(() => center.value?.synced_reports ?? [])
const syncReadiness = computed<K12100SyncReadiness | null>(() => center.value?.sync_readiness ?? null)
const hydratingLocal = ref(false)
const selectedCandidates = computed<SchoolPaperMatchCandidate[]>(() => selectedPaper.value?.candidates ?? [])
const reviewCoverage = computed(() => deriveReviewCoverage(reviewDetail.value, reviewRanks.value))

const activeStepStr = computed({
  get: () => String(activeStep.value),
  set: (val: string) => {
    const num = Number(val) as SyncStep
    if (num >= 1 && num <= 4) {
      goStep(num)
    }
  },
})

const syncContext = computed<StepFlowContext | null>(() => {
  if (!selectedPaper.value) return null
  const meta = getPaperStatusMeta(selectedPaper.value.status)
  return {
    eyebrow: '当前试卷',
    title: selectedPaper.value.filename,
    statusText: `${formatPaperSubject(selectedPaper.value)} · ${meta.label}`,
    statusTone: meta.tone === 'good' ? 'good' : meta.tone === 'mid' ? 'mid' : 'wait',
  }
})

const syncSteps = computed<StepDefinition[]>(() => {
  const paper = selectedPaper.value
  return [
    {
      id: '1',
      title: '发现试卷',
      subtitle: '扫描收件箱并选定试卷',
      badge: center.value ? `${papers.value.length} 份` : '待加载',
      done: paper !== null,
      prereqMet: true,
    },
    {
      id: '2',
      title: '匹配考试',
      subtitle: '联合身份字段，人工消歧',
      badge: center.value ? `${matchedPaperCount.value} 已匹配` : '待加载',
      done: Boolean(paper && ['matched', 'imported'].includes(paper.status)),
      prereqMet: paper !== null,
      lockReason: '请先在第 1 步扫描私有收件箱并选定一份试卷。',
    },
    {
      id: '3',
      title: 'k12100 报告同步',
      subtitle: '一键下载总分报告并补全档案',
      badge: job.value
        ? getJobStateLabel(job.value.state)
        : syncedReports.value.length > 0
          ? `已同步 ${syncedReports.value.length} 场`
          : '未开始',
      done: job.value?.state === 'completed' || syncedReports.value.length > 0,
      prereqMet: true,
    },
    {
      id: '4',
      title: '核对入档',
      subtitle: '人工锁定总分与本人排名',
      badge: reviewDetail.value ? (reviewDetail.value.confirmed_by_user ? '总分已核对' : '待核对') : '待入档',
      badgeTone: reviewDetail.value?.confirmed_by_user ? 'good' : 'wait',
      done: Boolean(reviewDetail.value?.confirmed_by_user),
      prereqMet: Boolean(currentExamId.value),
      lockReason: '请先关联试卷或从第 3 步报告结果选择一场考试后再核对入档。',
    },
  ]
})

const cliCommand = computed(() => {
  const environment = center.value?.source.environment ?? 'development'
  return `uv run python scripts/school_exam_pipeline.py run --env ${environment}`
})

const sourceTone = computed(() => {
  if (!center.value?.source.ready) return 'bad'
  return center.value.source.real_source_configured ? 'good' : 'wait'
})

const sourceStatusText = computed(() => {
  const source = center.value?.source
  if (!source) return '正在读取卷源状态…'
  if (!source.ready) return '私有收件箱不可用'
  return source.real_source_configured ? '真实授权卷源已就绪' : '仅本地收件箱 · 未配置真实卷源'
})

function setNotice(text: string, tone: 'info' | 'caution' | 'error' = 'info') {
  actionNotice.value = text
  actionTone.value = tone
}

function getPaperStatusMeta(status: string) {
  return PAPER_STATUS_META[status] ?? { label: status, tone: 'subtle' }
}

function getJobStateLabel(state: string | null | undefined): string {
  return {
    queued: '排队中',
    collecting: '采集中',
    backfilling: '整理中',
    completed: '已完成',
    failed: '已停止',
  }[state ?? ''] ?? '未开始'
}

function visibleComparisons(candidate: SchoolPaperMatchCandidate) {
  return (candidate.comparisons ?? []).filter(
    comparison => CORE_COMPARISON_FIELDS.has(comparison.field) || comparison.state === 'conflict',
  )
}

function comparisonValue(comparison: SchoolPaperFieldComparison, value: string | null): string {
  if (!value) return '缺失'
  if (comparison.field === 'subject') return SUBJECT_LABELS[value] || value
  return value
}

function comparisonClass(state: string): string {
  return state === 'match' ? 'good' : state === 'conflict' ? 'bad' : state === 'missing' ? 'subtle' : 'wait'
}

function openTab(tab: OpenTab) {
  if (currentExamId.value) emit('open-exam', currentExamId.value, tab)
}

async function loadCenter(preferPaperId?: string) {
  loading.value = true
  loadError.value = ''
  try {
    const data = await props.client.schoolExamSyncCenter()
    center.value = data
    const preferred = preferPaperId && data.papers.some(paper => paper.id === preferPaperId)
      ? preferPaperId
      : selectedPaperId.value && data.papers.some(paper => paper.id === selectedPaperId.value)
        ? selectedPaperId.value
        : (data.papers[0]?.id ?? null)
    selectedPaperId.value = preferred
    syncCandidateSelection()
  } catch (error) {
    center.value = null
    loadError.value = describeError(error)
  } finally {
    loading.value = false
  }
}

function syncCandidateSelection() {
  const paper = selectedPaper.value
  if (!paper) {
    candidateExamId.value = ''
    return
  }
  const known = paper.candidates.some(candidate => candidate.exam_id === candidateExamId.value)
  if (!known) {
    candidateExamId.value = paper.school_exam_id ?? paper.candidates[0]?.exam_id ?? ''
  }
  manualConfirmChecked.value = false
}

function selectPaper(paper: SchoolExamPaper) {
  selectedPaperId.value = paper.id
  syncCandidateSelection()
  activeStep.value = getPaperNextStep(paper)
  if (paper.status === 'imported') {
    void loadReview(paper.school_exam_id ?? currentExamId.value)
  }
}

function goStep(step: SyncStep) {
  activeStep.value = step
  if (step === 4) void loadReview(currentExamId.value)
}

async function scanInbox() {
  scanning.value = true
  actionNotice.value = ''
  try {
    const result = await props.client.scanSchoolExamPapers()
    await loadCenter()
    const run: SchoolExamScanRun = result.run
    const tone = run.error_count > 0 || run.invalid_count > 0 ? 'caution' : 'info'
    setNotice(
      `扫描完成：发现 ${run.discovered_count} 份，去重 ${run.duplicate_count} 份，待核对 ${run.needs_review_count} 份，跳过 ${run.invalid_count} 份。`,
      tone,
    )
    props.notify(
      run.error_count > 0
        ? `扫描完成，但有 ${run.error_count} 个文件/路径被安全策略跳过，请查看扫描记录。`
        : `扫描完成：发现 ${run.discovered_count} 份试卷。`,
      run.error_count > 0 ? 'caution' : 'success',
    )
  } catch (error) {
    setNotice(describeError(error), 'error')
    props.notify(describeError(error), 'error')
  } finally {
    scanning.value = false
  }
}

async function tryAcquire() {
  acquiring.value = true
  actionNotice.value = ''
  try {
    const result = await props.client.acquireSchoolExamPapers()
    await loadCenter()
    setNotice(`授权来源取得 ${result.acquired_count} 份试卷，已重新扫描登记。`)
    props.notify('授权卷源获取完成。', 'success')
  } catch (error) {
    const code = error instanceof ApiError ? error.code : ''
    const message = code === 'SOURCE_NOT_CONFIGURED'
      ? '未配置真实授权学校试卷来源；本地扫描仍可用，系统不会伪造远程下载。'
      : describeError(error)
    setNotice(message, 'caution')
    props.notify(message, 'caution')
  } finally {
    acquiring.value = false
  }
}

async function runMatch(manual: boolean) {
  const paper = selectedPaper.value
  if (!paper) return
  if (manual && !manualConfirmChecked.value) {
    setNotice('人工匹配前必须勾选“我已对照卷头与候选考试”。', 'caution')
    return
  }
  if (manual && !candidateExamId.value) {
    setNotice('请先选择一个候选考试。', 'caution')
    return
  }
  matching.value = true
  actionNotice.value = ''
  try {
    const result = await props.client.matchSchoolExamPaper(
      paper.id,
      manual ? { examId: candidateExamId.value, confirmedByHuman: true } : {},
    )
    await loadCenter(paper.id)
    setNotice(
      manual
        ? '已记录人工匹配；请继续导入原卷，再核对成绩与草稿。'
        : result.match
          ? `匹配结果：${getMatchMeta(result.match.state).label}。`
          : '已重新执行匹配。',
      result.paper.status === 'matched' ? 'info' : 'caution',
    )
    if (result.paper.status === 'matched') {
      manualConfirmChecked.value = false
    }
  } catch (error) {
    setNotice(describeError(error), 'error')
    props.notify(describeError(error), 'error')
  } finally {
    matching.value = false
  }
}

async function importPaper() {
  const paper = selectedPaper.value
  if (!paper) return
  importing.value = true
  actionNotice.value = ''
  try {
    const result = await props.client.importSchoolExamPaper(paper.id)
    await loadCenter(paper.id)
    emit('papers-imported', result.paper.school_exam_id ?? currentExamId.value ?? '')
    if (result.paper.school_exam_id) {
      await loadReview(result.paper.school_exam_id)
      activeStep.value = 4
    }
    setNotice(
      result.already_imported
        ? '该试卷此前已入私有档案，无重复附件。'
        : `原卷已入私有档案${result.attachment_created ? '' : '（哈希已存在，未重复保存）'}。`,
    )
    props.notify('校考试卷已入私有档案。', 'success')
  } catch (error) {
    setNotice(describeError(error), 'error')
    props.notify(describeError(error), 'error')
  } finally {
    importing.value = false
  }
}

async function rejectPaper() {
  const paper = selectedPaper.value
  if (!paper) return
  rejecting.value = true
  try {
    await props.client.rejectSchoolExamPaper(paper.id)
    await loadCenter(paper.id)
    setNotice('已人工忽略该试卷；原始文件仍保留在私有收件箱，未删除。')
  } catch (error) {
    setNotice(describeError(error), 'error')
  } finally {
    rejecting.value = false
  }
}

async function loadRuntime() {
  try {
    runtime.value = await props.client.k12100SyncStatus()
    if (runtime.value.latest_job) {
      job.value = runtime.value.latest_job
      if (runtime.value.latest_job.result) lastResult.value = runtime.value.latest_job.result
      if (runtime.value.latest_job.report_result) lastReportResult.value = runtime.value.latest_job.report_result
      if (runtime.value.active_job_id) startPolling(runtime.value.latest_job.job_id)
    }
  } catch (error) {
    collectionError.value = describeError(error)
  }
}

function stopPolling() {
  if (pollTimer !== null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function startPolling(jobId: string) {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      const latest = await props.client.k12100SyncJob(jobId)
      job.value = latest
      if (latest.state === 'completed') {
        stopPolling()
        if (latest.report_result) {
          lastReportResult.value = latest.report_result
          const summary = summarizeReportJob(latest.report_result)
          const firstExam = latest.report_result.subject_actions.find(row => row.exam_id)?.exam_id ?? ''
          if (firstExam && !focusedExamId.value) focusedExamId.value = firstExam
          await loadCenter(selectedPaperId.value ?? undefined)
          if (firstExam) emit('papers-imported', firstExam)
          if (currentExamId.value) await loadReview(currentExamId.value)
          const message = latest.stage_message || (summary.hasIssues ? '报告同步完成，请查看冲突或待补项。' : '报告同步完成。')
          collectionError.value = ''
          props.notify(message, summary.hasIssues ? 'caution' : 'success')
          return
        }
        lastResult.value = latest.result
        const blocked = latest.result?.totals.subjects_blocked ?? 0
        const message = blocked > 0
          ? `采集完成，但有 ${blocked} 科因身份未唯一匹配而停止入账，请人工处理。`
          : '采集任务结束：逐题信息已作为待核对草稿保存。'
        collectionError.value = blocked > 0 ? message : ''
        props.notify(message, blocked > 0 ? 'caution' : 'success')
        await loadReview(currentExamId.value)
      } else if (latest.state === 'failed') {
        stopPolling()
        if (latest.report_result) {
          lastReportResult.value = latest.report_result
        }
        await loadCenter(selectedPaperId.value ?? undefined)
        emit('papers-imported', '')
        collectionError.value = latest.error_message || latest.stage_message || '同步已停止。'
        props.notify(collectionError.value, 'error')
      }
    } catch (error) {
      stopPolling()
      collectionError.value = describeError(error)
    }
  }, 1500)
}

async function startReportSync() {
  startingJob.value = true
  collectionError.value = ''
  try {
    const created = await props.client.startK12100ReportJob({
      maxExams: 3,
      headless: !showBrowser.value,
    })
    job.value = created
    startPolling(created.job_id)
    props.notify('已启动 k12100 总分报告同步（自动跳过已有报告，单次最多 3 场串行）。', 'info')
  } catch (error) {
    collectionError.value = describeError(error)
    props.notify(collectionError.value, 'error')
    await loadRuntime()
  } finally {
    startingJob.value = false
  }
}

function inspectReportExam(examId: string) {
  if (!examId) return
  focusedExamId.value = examId
  activeStep.value = 4
  void loadReview(examId)
}

async function loadReview(examId: string | null) {
  if (!examId) {
    reviewDetail.value = null
    reviewRanks.value = null
    return
  }
  reviewLoading.value = true
  reviewError.value = ''
  try {
    const [detail, ranks] = await Promise.all([
      props.client.schoolExamDetail(examId),
      props.client.schoolExamRanks(examId),
    ])
    reviewDetail.value = detail
    reviewRanks.value = ranks
    confirmTotalInput.value = detail.confirmed_by_user ? detail.earned_points : detail.earned_points || ''
    confirmTotalAcknowledged.value = false
  } catch (error) {
    reviewDetail.value = null
    reviewRanks.value = null
    reviewError.value = describeError(error)
  } finally {
    reviewLoading.value = false
  }
}

async function confirmTotal() {
  const detail = reviewDetail.value
  if (!detail || confirmTotalInput.value === '') return
  if (!confirmTotalAcknowledged.value) {
    reviewError.value = '请先勾选“我已对照成绩单人工核对”。'
    return
  }
  confirmingTotal.value = true
  reviewError.value = ''
  try {
    await props.client.confirmSchoolExam(detail.id, Number(confirmTotalInput.value))
    props.notify('该科总分已人工核对并锁定；其余学科保持各自独立核对状态。', 'success')
    focusedExamId.value = detail.id
    await Promise.all([
      loadReview(detail.id),
      loadCenter(selectedPaperId.value ?? undefined),
    ])
    emit('papers-imported', detail.id)
  } catch (error) {
    reviewError.value = describeError(error)
  } finally {
    confirmingTotal.value = false
  }
}

async function hydrateLocalReports() {
  hydratingLocal.value = true
  collectionError.value = ''
  try {
    const res = await props.client.hydrateK12100LocalReports()
    await loadCenter(selectedPaperId.value ?? undefined)
    if (reviewDetail.value?.id) {
      await loadReview(reviewDetail.value.id)
    }
    props.notify(
      `本地补全完成：合并重复 ${res.deduped_reports} 份、同步排名 ${res.ranks_synced} 条、补切答题卡 ${res.cards_synced} 页（零联网重下）。`,
      'success',
    )
  } catch (error) {
    collectionError.value = describeError(error)
    props.notify(collectionError.value, 'error')
  } finally {
    hydratingLocal.value = false
  }
}

async function confirmRank(rankId: string) {
  const detail = reviewDetail.value
  if (!detail) return
  confirmingRankId.value = rankId
  reviewError.value = ''
  try {
    await props.client.confirmSchoolExamRank(detail.id, rankId)
    await loadReview(detail.id)
    props.notify('本人排名来源已人工确认；排名仍不进入能力画像。', 'success')
  } catch (error) {
    reviewError.value = describeError(error)
  } finally {
    confirmingRankId.value = null
  }
}

function triggerBundlePicker() {
  bundleInputRef.value?.click()
}

async function handleBundleFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (file.size > 15 * 1024 * 1024) {
    bundleError.value = '采集包超过 15 MiB 上限。'
    return
  }
  importingBundle.value = true
  bundleError.value = ''
  try {
    const parsed = JSON.parse(await file.text()) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error('采集包根节点必须是 JSON 对象。')
    }
    const result = await props.client.importK12100Bundle(parsed as Record<string, unknown>, {
      maxExams: 1,
      confirmTotalScores: false,
      extractExistingPdfs: true,
      uploadMissingCards: true,
      replaceUnconfirmedDrafts: true,
      useAi: true,
    })
    lastResult.value = result
    const blocked = result.totals.subjects_blocked ?? 0
    props.notify(
      blocked > 0
        ? `采集包已处理，${blocked} 科因身份未唯一匹配暂停入账。`
        : `采集包已处理 ${result.totals.subjects_processed} 科；总分默认待核对。`,
      blocked > 0 ? 'caution' : 'success',
    )
    await loadReview(currentExamId.value)
  } catch (error) {
    bundleError.value = error instanceof SyntaxError ? 'JSON 格式损坏，无法解析。' : describeError(error)
  } finally {
    importingBundle.value = false
  }
}

async function copyCliCommand() {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(cliCommand.value)
      props.notify('已复制本地流水线命令。', 'success')
      return
    }
  } catch {
    // 剪贴板权限受限时降级为文本提示
  }
  props.notify(`请手动复制命令：${cliCommand.value}`, 'info')
}

watch(
  () => props.client,
  () => {
    stopPolling()
    void loadCenter()
    void loadRuntime()
  },
  { immediate: true },
)

watch(
  () => props.selectedExamId,
  examId => {
    if (examId && !focusedExamId.value) void loadReview(examId)
  },
)

onBeforeUnmount(() => {
  stopPolling()
})
</script>

<template>
  <section class="exam-sync-center" aria-label="全科校考同步中心">
    <header class="exam-sync-topbar stage-wrap">
      <div class="exam-sync-env">
        <span class="chip good">{{ center?.source.environment || 'development' }} 环境</span>
        <span class="muted tiny">{{ sourceStatusText }}</span>
      </div>
      <div class="exam-sync-dir" :title="center?.source.directory || ''">
        <span class="muted tiny">私有收件箱</span>
        <code>{{ center?.source.directory_display || '$PAGEBOY_HOME/development/school-exams/inbox' }}</code>
      </div>
      <div class="exam-sync-top-actions">
        <span :class="['chip', isJobActive ? 'wait' : job?.state === 'failed' ? 'bad' : 'subtle']">
          {{ isJobActive ? `采集中 · ${getJobStateLabel(job?.state)}` : job ? `采集${getJobStateLabel(job.state)}` : '未启动采集' }}
        </span>
        <button type="button" class="ghost small" :disabled="loading" @click="loadCenter(selectedPaperId ?? undefined)">
          {{ loading ? '刷新中…' : '刷新同步中心' }}
        </button>
      </div>
    </header>

    <p v-if="loadError" class="exam-sync-banner bad stage-wrap" role="alert">{{ loadError }}</p>
    <p v-if="actionNotice" :class="['exam-sync-banner', actionTone, 'stage-wrap']" role="status">{{ actionNotice }}</p>

    <StepFlowWorkspace
      v-model="activeStepStr"
      :steps="syncSteps"
      :context="syncContext"
      steps-aria-label="校考同步四步工作流"
    >
      <!-- 第一步：发现试卷（合并为单一卡片） -->
      <template #step-1>
        <article class="card" aria-label="第一步：发现试卷">
          <div class="card-head">
            <div>
              <h3>第一步 · 试卷发现与收件箱列表</h3>
              <p class="card-sub">本地扫描不会伪造远程下载；任何文件都不会自动进入公共题库。</p>
            </div>
            <div class="card-head-tools">
              <span :class="['chip', sourceTone]">{{ sourceStatusText }}</span>
              <span class="chip subtle">待核对 {{ center?.counts.needs_review ?? 0 }} · 已匹配 {{ center?.counts.matched ?? 0 }} · 已入档 {{ center?.counts.imported ?? 0 }}</span>
            </div>
          </div>

          <dl class="exam-sync-facts">
            <div>
              <dt>当前目录</dt>
              <dd><code>{{ center?.source.directory_display || '—' }}</code></dd>
            </div>
            <div>
              <dt>格式与大小</dt>
              <dd>{{ center?.source.supported_formats.join(' / ') || 'PDF / DOCX / PNG / JPG' }} · 单份 ≤ {{ fmtBytes(center?.source.max_file_bytes ?? 35 * 1024 * 1024) }}</dd>
            </div>
            <div>
              <dt>最近扫描</dt>
              <dd>{{ center?.latest_scan ? shortTime(center.latest_scan.finished_at || center.latest_scan.started_at) : '尚未扫描' }}</dd>
            </div>
            <div>
              <dt>扫描审计</dt>
              <dd v-if="center?.latest_scan">
                发现 {{ center.latest_scan.discovered_count }} · 去重 {{ center.latest_scan.duplicate_count }} · 跳过 {{ center.latest_scan.invalid_count }} · 安全错误 {{ center.latest_scan.error_count }}
              </dd>
              <dd v-else>扫描后生成可复核记录</dd>
            </div>
          </dl>

          <div class="exam-sync-action-row" style="margin-bottom: 12px;">
            <button type="button" class="primary" :disabled="scanning" @click="scanInbox">
              {{ scanning ? '正在扫描…' : '扫描私有收件箱' }}
            </button>
            <button
              type="button"
              class="ghost"
              :disabled="acquiring || !center?.source.real_source_configured"
              :title="center?.source.real_source_configured ? '调用已授权来源适配器' : '未配置真实授权来源，不能伪造下载'"
              @click="tryAcquire"
            >
              {{ acquiring ? '获取中…' : '通过授权来源获取' }}
            </button>
            <HelpBubble compact title="为什么显示来源未配置" label="来源说明">
              <p>系统只登记仓库中已审核的合法来源适配器。当前没有学校月考/期中/期末真实卷源与授权方式，因此不会猜测 URL、不会抓取第三方试卷。</p>
              <p>你仍可把合法取得的文件放入私有收件箱后扫描；原始文件不会被删除或改名。</p>
            </HelpBubble>
          </div>

          <p v-if="center && !center.source.real_source_configured" class="exam-sync-blocked" role="note" style="margin-bottom: 12px;">
            <b>SOURCE_NOT_CONFIGURED</b>：{{ center.source.message }}
          </p>

          <details v-if="center?.latest_scan?.errors.length" class="exam-sync-details" style="margin-bottom: 12px;">
            <summary>查看最近扫描被跳过的文件</summary>
            <ul class="exam-sync-error-list" tabindex="0">
              <li v-for="(err, idx) in center.latest_scan.errors" :key="`${err.code}-${idx}`">
                <code>{{ err.path || '（目录）' }}</code><span>{{ err.code }}</span>
              </li>
            </ul>
          </details>

          <h4 class="sub-head" style="margin: 12px 0 8px;">已发现试卷 ({{ papers.length }})</h4>
          <div v-if="loading" class="exam-sync-empty">正在读取私有收件箱…</div>
          <div v-else-if="papers.length === 0" class="exam-sync-empty">
            <b>还没有发现试卷</b>
            <p>把 PDF / DOCX / PNG / JPG 放入私有收件箱，或使用命令行 `--source-dir` 导入。单次最多处理 200 份，符号链接会被拒绝。</p>
          </div>
          <ul v-else class="exam-paper-list" tabindex="0" aria-label="已发现校考试卷列表">
            <li v-for="paper in papers" :key="paper.id">
              <button
                type="button"
                class="exam-paper-row"
                :class="{ selected: selectedPaperId === paper.id }"
                :aria-pressed="selectedPaperId === paper.id"
                @click="selectPaper(paper)"
              >
                <span class="exam-paper-icon" aria-hidden="true">{{ paper.media_type.includes('pdf') ? 'PDF' : paper.media_type.includes('word') ? 'DOC' : 'IMG' }}</span>
                <span class="exam-paper-main">
                  <b>{{ paper.filename }}</b>
                  <small>
                    {{ formatPaperSubject(paper) }}
                    · {{ formatPaperExamIdentity(paper) }}
                    · {{ fmtBytes(paper.byte_size) }}
                  </small>
                  <small class="exam-paper-source">{{ paper.source_ref }}</small>
                </span>
                <span class="exam-paper-status">
                  <span :class="['chip', getMatchMeta(paper.match_state).tone]">{{ getMatchMeta(paper.match_state).label }}</span>
                  <span :class="['chip', getPaperStatusMeta(paper.status).tone]">{{ getPaperStatusMeta(paper.status).label }}</span>
                </span>
              </button>
            </li>
          </ul>
        </article>
      </template>

      <!-- 第二步：匹配考试（单一焦点卡内分节呈递） -->
      <template #step-2>
        <article v-if="selectedPaper" class="card" aria-label="第二步：匹配考试">
          <div class="card-head">
            <div>
              <h3>第二步 · 卷头识别与候选考试匹配</h3>
              <p class="card-sub">{{ selectedPaper.filename }}</p>
            </div>
            <div class="card-head-tools">
              <span :class="['chip', selectedPaper.header.complete ? 'good' : 'wait']">
                {{ CONFIDENCE_LABELS[selectedPaper.header.confidence || ''] || '待识别' }}
              </span>
              <span :class="['chip', getMatchMeta(selectedPaper.match_state).tone]">
                {{ getMatchMeta(selectedPaper.match_state).label }}
              </span>
            </div>
          </div>

          <h4 class="sub-head" style="margin-top: 4px;">卷头识别依据</h4>
          <dl class="exam-sync-identity">
            <div><dt>学年度</dt><dd>{{ selectedPaper.header.academic_year || '缺失' }}</dd></div>
            <div><dt>年级</dt><dd>{{ selectedPaper.header.grade || '缺失' }}</dd></div>
            <div><dt>考试类型</dt><dd>{{ selectedPaper.header.exam_type_label || EXAM_TYPE_LABELS[selectedPaper.header.exam_type || ''] || '缺失' }}</dd></div>
            <div><dt>学科</dt><dd>{{ formatPaperSubject(selectedPaper) === '学科待识别' ? '缺失' : formatPaperSubject(selectedPaper) }}</dd></div>
            <div><dt>考试日期</dt><dd>{{ fmtExamMonth(selectedPaper.header.exam_date) || '缺失' }}</dd></div>
          </dl>

          <details class="exam-sync-details" style="margin-bottom: 12px;">
            <summary>查看五字段证据与脱敏卷头摘录</summary>
            <ul class="exam-sync-fields" tabindex="0" aria-label="卷头字段识别状态">
              <li v-for="(field, key) in selectedPaper.header.fields" :key="key">
                <span>{{ FIELD_LABELS[key] || key }}</span>
                <span :class="['chip', field.status === 'found' ? 'good' : field.status === 'ambiguous' ? 'bad' : 'subtle']">
                  {{ FIELD_STATUS_LABELS[field.status] || field.status }}
                </span>
                <small>{{ field.evidence || '无识别依据' }}</small>
              </li>
            </ul>
            <pre class="exam-sync-excerpt" tabindex="0">{{ selectedPaper.header.text_excerpt || '未提取到文字层。' }}</pre>
          </details>

          <p v-if="selectedPaper.header.warnings.length" class="exam-sync-blocked" role="note" style="margin-bottom: 12px;">
            {{ selectedPaper.header.warnings.join('；') }}
          </p>

          <h4 class="sub-head" style="margin-top: 12px;">候选考试与字段差异</h4>
          <p class="muted tiny" style="margin-top: 0;">只有五项核心字段共同成立且候选唯一，或人工确认消歧后才可导入并进入采集。</p>

          <div v-if="selectedCandidates.length === 0" class="exam-sync-empty">
            <b>没有可比较的候选</b>
            <p>先在“总分台账与建档”新建对应考试档案，再回来人工选择。</p>
            <button type="button" class="ghost" @click="emit('open-exam', '', 'scores')">前往新建考试档案</button>
          </div>
          <ul v-else class="exam-sync-candidates" tabindex="0" aria-label="k12100 候选考试列表">
            <li v-for="candidate in selectedCandidates" :key="candidate.exam_id" class="exam-sync-candidate">
              <label class="exam-sync-candidate-head">
                <input
                  v-model="candidateExamId"
                  type="radio"
                  :value="candidate.exam_id"
                  :disabled="selectedPaper.status === 'imported'"
                />
                <span>
                  <b>{{ candidate.title || '未命名考试' }}</b>
                  <small>{{ fmtExamMonth(candidate.exam_date) || '日期缺失' }} · {{ candidate.manual ? '人工候选' : `匹配分 ${candidate.score ?? 0}` }}</small>
                </span>
                <span v-if="candidate.exact && !candidate.conflicts?.length" class="chip good">精确</span>
              </label>
              <ul v-if="visibleComparisons(candidate).length" class="exam-sync-compare">
                <li v-for="cmp in visibleComparisons(candidate)" :key="`${candidate.exam_id}-${cmp.field}`">
                  <span>{{ cmp.label }}</span>
                  <span class="exam-sync-compare-values">
                    <em>{{ comparisonValue(cmp, cmp.expected) }}</em>
                    <span aria-hidden="true">↔</span>
                    <em>{{ comparisonValue(cmp, cmp.actual) }}</em>
                  </span>
                  <span :class="['chip', comparisonClass(cmp.state)]">{{ COMPARISON_LABELS[cmp.state] || cmp.state }}</span>
                </li>
              </ul>
              <p v-if="candidate.conflicts?.length" class="muted tiny">
                冲突字段：{{ candidate.conflicts.map(field => FIELD_LABELS[field] || field).join('、') }}
              </p>
            </li>
          </ul>

          <div v-if="selectedCandidates.length" class="exam-sync-confirm-box">
            <label class="exam-sync-check">
              <input v-model="manualConfirmChecked" type="checkbox" :disabled="selectedPaper.status === 'imported'" />
              <span>我已对照卷头与候选考试，人工确认这是同一场考试。</span>
            </label>
            <div class="exam-sync-action-row">
              <button
                type="button"
                class="primary"
                :disabled="matching || manualConfirmChecked === false || selectedPaper.status === 'imported'"
                @click="runMatch(true)"
              >
                {{ matching ? '保存中…' : '确认匹配所选考试' }}
              </button>
              <button type="button" class="ghost" :disabled="matching" @click="runMatch(false)">
                {{ matching ? '匹配中…' : '重新执行自动匹配' }}
              </button>
              <button
                type="button"
                class="ghost"
                :disabled="rejecting || selectedPaper.status === 'imported'"
                @click="rejectPaper"
              >
                {{ rejecting ? '处理中…' : '人工忽略此试卷' }}
              </button>
            </div>
          </div>

          <div v-if="selectedPaper.status === 'matched'" class="exam-sync-next-card">
            <p><b>匹配已完成。</b>下一步把原卷纳入该考试私有附件，再启动信息采集。</p>
            <div class="exam-sync-action-row">
              <button type="button" class="primary" :disabled="importing" @click="importPaper">
                {{ importing ? '入档中…' : '将原卷导入该考试' }}
              </button>
              <button type="button" class="ghost" @click="goStep(3)">先查看采集范围</button>
            </div>
          </div>
        </article>
      </template>

      <!-- 第三步：k12100 报告同步（自动下载总分报告、新建/更新/补全考试档案） -->
      <template #step-3>
        <article class="card" aria-label="第三步：k12100 报告同步">
          <div class="card-head">
            <div>
              <h3>第三步 · 从 k12100 下载总分报告并同步</h3>
              <p class="card-sub">考试时间取自 k12100 首页，学年 / 年级 / 考试类型 / 学科取自下载的总分分析报告与首页元数据；自动跳过已有报告的场次。</p>
            </div>
            <div class="card-head-tools">
              <span :class="['chip', job?.state === 'failed' ? 'bad' : job?.state === 'completed' ? 'good' : isJobActive ? 'wait' : 'subtle']">
                {{ job ? getJobStateLabel(job.state) : '未启动' }}
              </span>
            </div>
          </div>

          <div class="exam-sync-scope-grid">
            <div><b>考试档案</b><span>首页考试时间 + 报告学年度 / 年级 / 类型 / 学科；缺失自动新建或补全</span></div>
            <div><b>成绩更新</b><span>更新未锁定档案总分（保持待核对）；已锁分冲突只提示不覆盖</span></div>
            <div><b>逐题与答案</b><span>新建或更新未确认 ocr_draft 得分；保护已确认小题</span></div>
            <div><b>答题卡附件</b><span>从报告册切分并同步各科答题卡至私有附件存储</span></div>
          </div>

          <div class="exam-sync-safety" role="note" style="margin-bottom: 10px;">
            <b>低频与核对红线</b>
            <ul>
              <li>单账号、单会话、串行；每次最多下载 3 场未同步场次，遇验证码或 401/403/429 立即熔断停止。</li>
              <li>新建或更新的总分与逐题草稿均保持待人工核对，绝不直接写入能力画像。</li>
            </ul>
          </div>

          <p v-if="runtime && !runtime.can_run_local" class="exam-sync-blocked" role="note">
            本机直连不可用：{{ runtime.unavailable_reason || '当前环境无法启动宿主机浏览器' }}。可使用下方离线采集包或「报告导入与核对」本地扫描。
          </p>
          <p v-else-if="runtime" class="muted tiny">
            账号 {{ runtime.credentials.username_masked || '未配置' }} · 环境 {{ runtime.environment }}
          </p>

          <label class="exam-sync-check" style="margin-top: 8px;">
            <input v-model="showBrowser" type="checkbox" />
            <span>显示宿主机浏览器窗口（首次登录/遇到人机校验时人工处理）</span>
          </label>

          <div v-if="syncReadiness && syncReadiness.total_reports > 0" class="exam-sync-readiness" role="note">
            <div class="exam-sync-report-row-head">
              <b>
                {{
                  syncReadiness.all_complete
                    ? `同步前完整性预检：库内 ${syncReadiness.total_reports} 场考试已全部完整同步`
                    : `同步前完整性预检：${syncReadiness.complete_reports} 场完整，${syncReadiness.incomplete_reports} 场尚缺排名/最高分或字段`
                }}
              </b>
              <span :class="['chip', syncReadiness.all_complete ? 'good' : 'wait']">
                {{ syncReadiness.all_complete ? '已完整同步 · 免重下' : '可先本地补全' }}
              </span>
            </div>
            <p class="muted tiny" style="margin: 4px 0 0;">
              {{
                syncReadiness.all_complete
                  ? '各场次均已具备日期、全科成绩、逐题草稿、答题卡及班/年排名与最高分；点击下方按钮仅检查 k12100 首页是否有新增场次，已完整场次不会重复下载。'
                  : '建议先点右侧按钮从本地已存 PDF 直接补全排名与最高分，无需重新登录或重复下载。'
              }}
            </p>
          </div>

          <div class="exam-sync-action-row" style="margin-bottom: 12px;">
            <button
              type="button"
              class="primary"
              :disabled="startingJob || isJobActive || !runtime?.can_run_local"
              @click="startReportSync"
            >
              {{ startingJob ? '正在启动…' : isJobActive ? '报告下载与同步中…' : '从 k12100 下载总分报告并同步' }}
            </button>
            <button
              v-if="syncReadiness && (syncReadiness.incomplete_reports > 0 || syncReadiness.total_reports > 0)"
              type="button"
              class="ghost"
              :disabled="hydratingLocal || isJobActive"
              @click="hydrateLocalReports"
            >
              {{ hydratingLocal ? '补全中…' : '本地核对并补全排名/最高分' }}
            </button>
            <button type="button" class="ghost" @click="loadRuntime">刷新环境状态</button>
            <button type="button" class="ghost small" @click="advancedOpen = !advancedOpen">
              {{ advancedOpen ? '收起高级设置' : '高级设置与离线包' }}
            </button>
          </div>

          <div v-if="job" class="exam-sync-progress" aria-live="polite" style="margin-bottom: 10px;">
            <div class="exam-sync-progress-head">
              <b>{{ job.stage_message }}</b>
              <span class="muted tiny">{{ shortTime(job.updated_at) }}</span>
            </div>
            <dl class="exam-sync-facts compact">
              <div><dt>任务状态</dt><dd>{{ getJobStateLabel(job.state) }}</dd></div>
              <div><dt>总分确认</dt><dd>默认待人工核对</dd></div>
              <div><dt>失败原因</dt><dd>{{ job.error_message || '无' }}</dd></div>
            </dl>
          </div>

          <div v-if="lastReportResult" class="exam-sync-result">
            <h4>本次报告同步结果</h4>
            <div class="exam-sync-mini-stats">
              <div><b>{{ reportSummary.homeExams }}</b><span>首页场次（跳过 {{ reportSummary.skippedExisting }}）</span></div>
              <div><b>{{ reportSummary.created }} / {{ reportSummary.updated + reportSummary.filled }}</b><span>新建科次 / 更新补全</span></div>
              <div><b>{{ reportSummary.draftsChanged }} 题</b><span>草稿变更（切图 {{ reportSummary.cardsSynced }} 页）</span></div>
            </div>

            <div v-if="lastReportResult.home_exams.length" class="exam-sync-home-list">
              <span
                v-for="hx in lastReportResult.home_exams"
                :key="hx.external_exam_id || hx.exam_name"
                :class="['chip', hx.already_synced ? 'subtle' : 'mid']"
              >
                {{ hx.exam_name }}（{{ hx.exam_date || '无日期' }}）· {{ hx.already_synced ? '已同步跳过' : '本次处理' }}
              </span>
            </div>

            <ul v-if="lastReportResult.subject_actions.length" class="exam-sync-report-actions" tabindex="0" aria-label="报告同步学科结果列表">
              <li v-for="(row, idx) in lastReportResult.subject_actions" :key="`${row.report_id}-${row.subject}-${idx}`">
                <div class="exam-sync-report-row-head">
                  <b>{{ row.subject_label }} · {{ row.report_title }}</b>
                  <span :class="['chip', getReportActionMeta(row.action).tone]">{{ getReportActionMeta(row.action).label }}</span>
                </div>
                <div class="exam-sync-report-row-meta">
                  <span>时间：{{ row.report_exam_date || row.exam_date || '缺失' }}</span>
                  <span v-if="row.academic_year">学年：{{ row.academic_year }}</span>
                  <span v-if="row.grade">年级：{{ row.grade }}年级</span>
                  <span v-if="row.earned_points !== null && row.max_points !== null">
                    成绩：{{ fmtPoints(row.earned_points) }} / {{ fmtPoints(row.max_points) }}
                  </span>
                </div>
                <p class="muted tiny" style="margin: 3px 0 0;">{{ row.message }}</p>
                <div class="exam-sync-action-row" style="margin-top: 6px;">
                  <button
                    v-if="row.exam_id"
                    type="button"
                    class="ghost small"
                    @click="inspectReportExam(row.exam_id)"
                  >
                    核对总分 →
                  </button>
                  <button
                    v-if="row.exam_id"
                    type="button"
                    class="ghost small"
                    @click="emit('open-exam', row.exam_id, 'scores')"
                  >
                    打开档案
                  </button>
                  <button
                    v-else-if="row.action === 'awaiting_exam_date'"
                    type="button"
                    class="ghost small"
                    @click="emit('open-exam', '', 'scores')"
                  >
                    去手工建档
                  </button>
                </div>
              </li>
            </ul>

            <ul v-if="lastReportResult.failures.length" class="exam-sync-error-list" style="margin-top: 8px;">
              <li v-for="(err, idx) in lastReportResult.failures" :key="`${err.code}-${idx}`">
                <span>{{ err.exam_name || err.external_exam_id || '报告下载' }}：{{ err.reason }}</span>
                <code>{{ err.code }}</code>
              </li>
            </ul>

            <p
              v-if="lastReportResult.subject_actions.length === 0 && lastReportResult.totals.skipped_existing > 0 && lastReportResult.failures.length === 0"
              class="muted tiny"
              style="margin: 8px 0 0;"
            >
              首页 {{ lastReportResult.totals.home_exams }} 场均已有同步报告并自动跳过下载；前期同步的完整场次与各科状态见下方「已同步的 k12100 报告与档案」。
            </p>
          </div>

          <div v-if="syncedReports.length" class="exam-sync-result" aria-label="已同步的 k12100 报告与档案">
            <h4>已同步的 k12100 报告与档案（共 {{ syncedReports.length }} 场 · 库中实时）</h4>
            <ul class="exam-sync-persisted-list" tabindex="0">
              <li v-for="rep in syncedReports" :key="rep.id">
                <div class="exam-sync-report-row-head">
                  <b>{{ rep.title || rep.external_exam_id || '校考分析报告' }}</b>
                  <div style="display: flex; gap: 6px; flex-wrap: wrap;">
                    <span
                      v-if="rep.completeness"
                      :class="['chip', rep.completeness.complete ? 'good' : 'wait']"
                    >
                      {{
                        rep.completeness.complete
                          ? '信息完整'
                          : `缺：${rep.completeness.missing.slice(0, 3).join('、')}${rep.completeness.missing.length > 3 ? ` 等 ${rep.completeness.missing.length} 项` : ''}`
                      }}
                    </span>
                    <span :class="['chip', rep.match_state === 'MATCHED' || rep.match_state === 'EXACT_MATCH' ? 'good' : 'wait']">
                      {{ getMatchMeta(rep.match_state).label }}
                    </span>
                  </div>
                </div>
                <div class="exam-sync-report-row-meta">
                  <span>时间：{{ rep.exam_date || '待补全' }}</span>
                  <span v-if="rep.academic_year">学年：{{ rep.academic_year }}</span>
                  <span v-if="rep.grade">年级：{{ fmtGradeLabel(rep.grade) }}</span>
                  <span v-if="rep.exam_type">类型：{{ EXAM_TYPE_LABELS[rep.exam_type] || rep.exam_type }}</span>
                  <span v-if="rep.report_total_score !== null && rep.report_total_max !== null">
                    报告总分：{{ fmtPoints(rep.report_total_score) }} / {{ fmtPoints(rep.report_total_max) }}
                  </span>
                  <span v-if="rep.total_class_rank">总分班排：#{{ rep.total_class_rank }}</span>
                  <span v-if="rep.total_grade_rank">
                    总分年排：#{{ rep.total_grade_rank }}{{ rep.total_participants ? ` / ${rep.total_participants}人` : '' }}
                  </span>
                  <span v-if="rep.total_class_highest !== null && rep.total_class_highest !== undefined">
                    总分班最高：{{ fmtPoints(rep.total_class_highest) }}
                  </span>
                  <span v-if="rep.total_grade_highest !== null && rep.total_grade_highest !== undefined">
                    总分年最高：{{ fmtPoints(rep.total_grade_highest) }}
                  </span>
                  <span>共 {{ rep.pages }} 页</span>
                </div>

                <div v-if="rep.exams.length" class="exam-sync-persisted-subjects">
                  <div v-for="ex in rep.exams" :key="ex.exam_id" class="exam-sync-persisted-subject">
                    <div class="exam-sync-persisted-subject-main">
                      <b>{{ ex.subject_label }}</b>
                      <span>{{ fmtPoints(ex.earned_points) }} / {{ fmtPoints(ex.max_points) }}</span>
                      <span :class="['chip', ex.confirmed_by_user ? 'good' : 'wait']">
                        {{ ex.confirmed_by_user ? '已核对' : '待核对' }}
                      </span>
                    </div>
                    <small class="muted tiny">
                      班排 {{ ex.class_rank ? `#${ex.class_rank}` : '—' }} · 年排 {{ ex.grade_rank ? `#${ex.grade_rank}` : '—' }} · 班最高 {{ ex.class_highest !== null && ex.class_highest !== undefined ? fmtPoints(ex.class_highest) : '—' }} · 年最高 {{ ex.grade_highest !== null && ex.grade_highest !== undefined ? fmtPoints(ex.grade_highest) : '—' }}
                    </small>
                    <small class="muted tiny">
                      草稿 {{ ex.draft_count }} / 已确认 {{ ex.confirmed_item_count }} 题 · 附件 {{ ex.attachment_count }} 份
                    </small>
                    <div class="exam-sync-action-row" style="margin-top: 4px;">
                      <button
                        type="button"
                        class="ghost small"
                        @click="inspectReportExam(ex.exam_id)"
                      >
                        {{ ex.confirmed_by_user ? '查看核对 →' : '核对总分 →' }}
                      </button>
                      <button
                        type="button"
                        class="ghost small"
                        @click="emit('open-exam', ex.exam_id, 'scores')"
                      >
                        打开档案
                      </button>
                    </div>
                  </div>
                </div>

                <p v-if="rep.unlinked_subjects.length" class="muted tiny" style="margin: 6px 0 0;">
                  尚有 {{ rep.unlinked_subjects.map(item => item.subject_label).join('、') }} 未建档（如缺考试日期需手工建档）。
                  <button
                    type="button"
                    class="ghost small"
                    style="margin-left: 6px;"
                    @click="emit('open-exam', '', 'scores')"
                  >
                    去手工建档
                  </button>
                </p>
              </li>
            </ul>
          </div>

          <div v-if="currentResultRow" class="exam-sync-result">
            <h4>{{ currentResultRow.match_state ? getMatchMeta(currentResultRow.match_state).label : '离线采集包结果' }}</h4>
            <dl class="exam-sync-facts">
              <div><dt>科目</dt><dd>{{ currentResultRow.subject_label || formatPaperSubject(selectedPaper) }}</dd></div>
              <div><dt>总分</dt><dd>{{ fmtPoints(currentResultRow.earned_points) }} / {{ fmtPoints(currentResultRow.max_points) }} · {{ currentResultRow.confirmed_by_user ? '已核对' : '待核对' }}</dd></div>
              <div><dt>答题卡</dt><dd>新上传 {{ currentResultRow.attachments_uploaded }} 份</dd></div>
              <div><dt>逐题草稿</dt><dd>{{ currentResultRow.drafts_created }} 题待人工确认</dd></div>
            </dl>
            <p v-if="currentResultRow.warning" class="exam-sync-banner caution">{{ currentResultRow.warning }}</p>
          </div>

          <p v-if="collectionError" class="exam-sync-banner bad" role="alert">{{ collectionError }}</p>

          <!-- 内联折叠：高级设置与离线回退 -->
          <div v-if="advancedOpen" class="exam-sync-advanced" style="margin-top: 14px; padding-top: 12px; border-top: 1px dashed var(--line);">
            <h4 class="sub-head" style="margin-top: 0;">高级设置与离线回退</h4>
            <div class="exam-sync-cli">
              <span class="muted tiny">本地单次执行</span>
              <code>{{ cliCommand }}</code>
              <button type="button" class="ghost small" @click="copyCliCommand">复制命令</button>
            </div>
            <div class="exam-sync-bundle">
              <div>
                <b>离线采集包导入</b>
                <p class="muted tiny">合法导出的脱敏 JSON；服务端二次 PII 清洗并强制草稿门禁。</p>
              </div>
              <input
                ref="bundleInputRef"
                type="file"
                accept="application/json,.json"
                class="sr-only-input"
                aria-label="选择脱敏校考采集包"
                @change="handleBundleFile"
              />
              <button type="button" class="ghost" :disabled="importingBundle" @click="triggerBundlePicker">
                {{ importingBundle ? '导入中…' : '选择离线采集包' }}
              </button>
            </div>
            <p v-if="bundleError" class="exam-sync-banner bad" role="alert">{{ bundleError }}</p>
            <details class="exam-sync-details">
              <summary>调试与限流信息</summary>
              <pre class="exam-sync-excerpt">environment={{ runtime?.environment || center?.source.environment || 'development' }}
mode={{ runtime?.mode || 'unknown' }}
can_run_local={{ runtime?.can_run_local ?? false }}
browser_ready={{ runtime?.browser_ready ?? false }}
playwright_available={{ runtime?.playwright_available ?? false }}
source_code={{ center?.source.source_code || 'LOCAL_INBOX' }}
active_job={{ isJobActive }}</pre>
            </details>
          </div>

          <div v-if="lastReportResult || lastResult || currentExamId" class="card-footer-flow">
            <button type="button" class="ghost small" @click="goStep(selectedPaper ? 2 : 1)">
              {{ selectedPaper ? '← 去匹配试卷' : '← 去发现试卷' }}
            </button>
            <button v-if="currentExamId" type="button" class="primary small" @click="goStep(4)">进入核对入档 →</button>
          </div>
        </article>
      </template>

      <!-- 第四步：核对入档（总分锁定 & 本人排名统一于单卡内） -->
      <template #step-4>
        <div v-if="reviewLoading" class="card exam-sync-empty">正在读取成绩、草稿与本人排名…</div>
        <article v-else class="card" aria-label="第四步：核对入档">
          <div class="card-head">
            <div>
              <h3>第四步 · {{ reviewDetail?.title || currentExamTitle }}（核对入档）</h3>
              <p class="card-sub">{{ fmtExamMonth(reviewDetail?.exam_date) }} · 源：{{ SOURCE_KIND_LABELS[reviewDetail?.source_kind || 'manual'] || reviewDetail?.source_kind || '手工建档' }}</p>
            </div>
            <span :class="['chip', reviewDetail?.confirmed_by_user ? 'good' : 'wait']">
              {{ reviewDetail?.confirmed_by_user ? '总分已核对' : '总分待核对' }}
            </span>
          </div>

          <div class="exam-sync-review-kpis">
            <div>
              <b>{{ reviewDetail ? `${fmtPoints(reviewDetail.earned_points)} / ${fmtPoints(reviewDetail.max_points)}` : '—' }}</b>
              <span>总分（待核对不进入画像）</span>
            </div>
            <div>
              <b>{{ reviewCoverage.confirmedItems }} 题</b>
              <span>已人工确认逐题</span>
            </div>
            <div>
              <b>{{ reviewCoverage.draftItems }} 题</b>
              <span>待核对逐题草稿</span>
            </div>
            <div>
              <b>{{ reviewCoverage.attachments }} 份</b>
              <span>私有答题卡/原卷</span>
            </div>
          </div>

          <div v-if="!reviewDetail?.confirmed_by_user" class="exam-sync-confirm-box">
            <h4 style="margin-top: 0;">人工核对总分</h4>
            <p class="muted tiny">只有你对照成绩单确认后才会锁定；平台采集值默认不自动确认。</p>
            <div class="exam-sync-inline-form">
              <label>
                实得总分
                <input v-model.number="confirmTotalInput" type="number" min="0" step="0.5" />
              </label>
              <label class="exam-sync-check">
                <input v-model="confirmTotalAcknowledged" type="checkbox" />
                <span>我已对照成绩单人工核对</span>
              </label>
              <button type="button" class="primary" :disabled="confirmingTotal || !confirmTotalAcknowledged" @click="confirmTotal">
                {{ confirmingTotal ? '锁定中…' : '确认并锁定总分' }}
              </button>
            </div>
          </div>
          <div v-else class="exam-sync-locked">
            总分已人工锁定。平台后续若给出不同候选值，只记录冲突，不覆盖历史值。
          </div>

          <div style="margin-top: 16px; padding-top: 14px; border-top: 1px dashed var(--line);">
            <div class="card-head">
              <div>
                <h4 style="margin: 0;">本人排名快照（{{ reviewRanks?.ranks.length ?? 0 }} 个范围）</h4>
                <p class="card-sub">平台实际提供的本人排名；独立保存，不进入知识点能力画像。</p>
              </div>
            </div>
            <div v-if="reviewRanks && reviewRanks.ranks.length === 0" class="exam-sync-empty">
              <b>平台未提供可用排名</b>
              <p>系统不会用 0 或推算值补齐。缺失范围：{{ reviewRanks.missing_scopes.map(scope => RANK_SCOPE_LABELS[scope] || scope).join('、') }}。</p>
            </div>
            <ul v-else class="exam-sync-ranks" tabindex="0" aria-label="本人排名列表">
              <li v-for="rank in reviewRanks?.ranks ?? []" :key="rank.id">
                <div class="exam-sync-rank-main">
                  <b>{{ RANK_SCOPE_LABELS[rank.scope] || rank.scope }}</b>
                  <span>{{ formatRankValue(rank) }}</span>
                  <span v-if="rank.highest_score !== null && rank.highest_score !== undefined" class="chip subtle">
                    最高 {{ fmtPoints(rank.highest_score) }} 分
                  </span>
                  <span v-if="rank.percentile !== null" class="chip subtle">百分位 {{ Math.round(rank.percentile * 100) }}%</span>
                  <span :class="['chip', rank.ownership_status === 'verified' ? 'good' : 'bad']">
                    {{ rank.ownership_status === 'verified' ? '本人归属已验证' : '归属未验证' }}
                  </span>
                </div>
                <div class="exam-sync-rank-meta">
                  来源 {{ rank.source_name }} · 字段 <code>{{ rank.source_field }}</code> · 采集 {{ shortTime(rank.captured_at) }}
                  <span v-if="rank.history_count > 1" class="chip subtle">历史 {{ rank.history_count }} 条</span>
                </div>
                <div class="exam-sync-rank-actions">
                  <span :class="['chip', rank.review_status === 'confirmed' ? 'good' : 'wait']">
                    {{ rank.review_status === 'confirmed' ? '已人工确认' : '待确认来源' }}
                  </span>
                  <button
                    v-if="rank.review_status !== 'confirmed' && rank.ownership_status === 'verified'"
                    type="button"
                    class="ghost small"
                    :disabled="confirmingRankId === rank.id"
                    @click="confirmRank(rank.id)"
                  >
                    {{ confirmingRankId === rank.id ? '确认中…' : '确认排名来源' }}
                  </button>
                </div>
              </li>
            </ul>
            <div
              v-if="(reviewRanks?.total_ranks?.length ?? 0) > 0 || reviewRanks?.report_total"
              class="exam-sync-missing"
              style="margin-top: 8px;"
            >
              <b>同场全科总分排名与最高分</b>
              <span v-if="reviewRanks?.report_total">
                总分 {{ reviewRanks.report_total.report_total_score !== null ? fmtPoints(reviewRanks.report_total.report_total_score) : '—' }} / {{ reviewRanks.report_total.report_total_max !== null ? fmtPoints(reviewRanks.report_total.report_total_max) : '—' }}
                · 班排 {{ reviewRanks.report_total.total_class_rank ?? '—' }}
                · 年排 {{ reviewRanks.report_total.total_grade_rank ?? '—' }}{{ reviewRanks.report_total.total_participants ? ` / ${reviewRanks.report_total.total_participants}人` : '' }}
                · 班最高 {{ reviewRanks.report_total.total_class_highest !== null ? fmtPoints(reviewRanks.report_total.total_class_highest) : '—' }}
                · 年最高 {{ reviewRanks.report_total.total_grade_highest !== null ? fmtPoints(reviewRanks.report_total.total_grade_highest) : '—' }}
              </span>
            </div>
            <p class="muted tiny">{{ reviewRanks?.disclaimer || '本人排名不得用于推断中考成绩。' }}</p>
            <div class="exam-sync-missing">
              <b>缺失信息</b>
              <span>{{ reviewCoverage.missingRankScopes.length ? reviewCoverage.missingRankScopes.map(scope => RANK_SCOPE_LABELS[scope] || scope).join('、') : '四个排名范围均已提供' }}</span>
            </div>
          </div>

          <p v-if="reviewError" class="exam-sync-banner bad" role="alert">{{ reviewError }}</p>

          <div class="handoff-box">
            <div>
              <strong>入档核对就绪</strong>
              <span>若有逐题草稿，请前往「原卷与草稿校对」校对入账后再看错误分析。</span>
            </div>
            <div style="display: flex; gap: 8px; flex-wrap: wrap;">
              <button type="button" class="primary small" @click="openTab('papers')">去校对逐题草稿 →</button>
              <button type="button" class="ghost small" @click="openTab('scores')">查看总分台账</button>
              <button type="button" class="ghost small" @click="openTab('analysis')">错误分析</button>
            </div>
          </div>
        </article>
      </template>
    </StepFlowWorkspace>

    <footer class="exam-sync-footer stage-wrap">
      <p>待核对草稿、未锁定总分和本人排名都不会写入学生端能力画像。所有自动获取都受账号授权、平台规则与低频边界约束。</p>
      <span class="chip subtle">ST-EXAM-AUTOSYNC-01</span>
    </footer>
  </section>
</template>
