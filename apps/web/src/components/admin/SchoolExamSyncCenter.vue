<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  describeError,
  type ApiClient,
  type K12100BackfillResult,
  type K12100ReportJobResult,
  type K12100RuntimeStatus,
  type K12100SyncedReportSummary,
  type K12100SyncJob,
  type K12100SyncReadiness,
  type SchoolExamDetail,
  type SchoolExamRanksPayload,
  type SchoolExamScanRun,
  type SchoolExamSyncCenter,
  type SchoolSubject,
} from '../../api'
import { fmtBytes, fmtPoints, shortTime } from '../../copy'
import {
  deriveReviewCoverage,
  formatPaperExamIdentity,
  formatPaperSubject,
  formatRankValue,
  getMatchMeta,
  getReportActionMeta,
  RANK_SCOPE_LABELS,
  summarizeReportJob,
  type SyncStep,
} from '../../examSync'
import type { NoticeTone } from '../Notice.vue'
import StepFlowWorkspace from './StepFlowWorkspace.vue'
import type { StepDefinition } from './stepFlow'

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
  (e: 'step-change', step: SyncStep): void
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

const SOURCE_KIND_LABELS: Record<string, string> = {
  manual: '手工建档',
  k12100: '平台同步',
  local_scan: '本地扫描',
  import: '离线导入',
}

const center = ref<SchoolExamSyncCenter | null>(null)
const loading = ref(false)
const loadError = ref('')
const activeStep = ref<SyncStep>(1)
const scanning = ref(false)
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

const SUBJECT_LABELS: Record<string, string> = {
  chinese: '语文',
  math: '数学',
  english: '英语',
  physics: '物理',
  ethics: '道德与法治',
  daofa: '道德与法治',
  history: '历史',
  geography: '地理',
  biology: '生物',
  chemistry: '化学',
  all: '全科',
}

const reviewDetail = ref<SchoolExamDetail | null>(null)
const reviewRanks = ref<SchoolExamRanksPayload | null>(null)
const reviewLoading = ref(false)
const confirmTotalInput = ref<number | ''>('')
const confirmTotalAcknowledged = ref(false)
const confirmingTotal = ref(false)
const confirmingRankId = ref<string | null>(null)
const reviewError = ref('')
const activeReviewSubject = ref<string>('')
const rankTab = ref<'subject' | 'total'>('subject')

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
const isJobActive = computed(
  () => job.value?.state === 'queued' || job.value?.state === 'collecting' || job.value?.state === 'backfilling',
)
const currentExamId = computed(() => focusedExamId.value ?? props.selectedExamId ?? null)
const currentExamTitle = computed(
  () => reviewDetail.value?.title ?? '尚未关联考试档案',
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
const reviewCoverage = computed(() => {
  const scope =
    reviewDetail.value?.subject === 'all' && activeReviewTab.value && activeReviewTab.value.subject !== 'all'
      ? (activeReviewTab.value.subject as SchoolSubject)
      : undefined
  return deriveReviewCoverage(reviewDetail.value, reviewRanks.value, scope)
})

const jobProgress = computed(() => {
  const j = job.value
  if (!j) return 0
  if (typeof j.progress_percent === 'number' && j.progress_percent > 0) {
    return Math.min(100, Math.max(0, Math.round(j.progress_percent)))
  }
  return { queued: 10, collecting: 40, backfilling: 75, completed: 100, failed: 100 }[j.state] ?? 0
})

interface ReviewSubjectTab {
  subject: string
  subject_label: string
  exam_id: string
  earned_points: number | null
  max_points: number | null
  confirmed_by_user: boolean
}

const matchedReviewReport = computed<K12100SyncedReportSummary | null>(() => {
  const examId = currentExamId.value
  if (!syncedReports.value.length) return null
  if (examId) {
    const found = syncedReports.value.find(rep => rep.exams.some(ex => ex.exam_id === examId))
    if (found) return found
  }
  return syncedReports.value.length === 1 ? syncedReports.value[0] : null
})

const reviewSubjectTabs = computed<ReviewSubjectTab[]>(() => {
  const rep = matchedReviewReport.value
  if (rep && rep.exams.length > 0) {
    return rep.exams.map(ex => ({
      subject: ex.subject,
      subject_label: ex.subject_label || SUBJECT_LABELS[ex.subject] || ex.subject,
      exam_id: ex.exam_id,
      earned_points: ex.earned_points,
      max_points: ex.max_points,
      confirmed_by_user: ex.confirmed_by_user,
    }))
  }
  if (reviewDetail.value) {
    const subj = reviewDetail.value.subject || 'all'
    return [
      {
        subject: subj,
        subject_label: SUBJECT_LABELS[subj] || subj,
        exam_id: reviewDetail.value.id,
        earned_points: reviewDetail.value.earned_points,
        max_points: reviewDetail.value.max_points,
        confirmed_by_user: reviewDetail.value.confirmed_by_user,
      },
    ]
  }
  return []
})

const activeReviewTab = computed<ReviewSubjectTab | null>(() => {
  const tabs = reviewSubjectTabs.value
  if (!tabs.length) return null
  return tabs.find(t => t.subject === activeReviewSubject.value) ?? tabs[0]
})

const activeSubjectConfirmed = computed(() => {
  if (reviewDetail.value?.subject === 'all' && activeReviewTab.value && activeReviewTab.value.subject !== 'all') {
    return activeReviewTab.value.confirmed_by_user
  }
  return Boolean(reviewDetail.value?.confirmed_by_user)
})

const activeSubjectRanks = computed(() => {
  const ranks = reviewRanks.value?.ranks ?? []
  const tabSubj = activeReviewTab.value?.subject
  if (!tabSubj || tabSubj === 'all') return ranks
  const scoped = ranks.filter(r => r.subject_scope === tabSubj)
  return scoped.length > 0 ? scoped : ranks.filter(r => r.subject_scope === 'total' || !r.subject_scope)
})

const filteredMissingRankScopes = computed(() =>
  reviewCoverage.value.missingRankScopes.filter(scope => scope !== 'school' && scope !== 'region'),
)

const hasTotalRankSummary = computed(
  () => (reviewRanks.value?.total_ranks?.length ?? 0) > 0 || Boolean(reviewRanks.value?.report_total),
)

const activeStepStr = computed({
  get: () => String(activeStep.value),
  set: (val: string) => {
    const num = Number(val) as SyncStep
    if (num >= 1 && num <= 4) {
      goStep(num)
    }
  },
})

const syncSteps = computed<StepDefinition[]>(() => {
  return [
    {
      id: '1',
      title: '发现试卷',
      subtitle: '扫描原卷目录并查看列表',
      badge: center.value ? `${papers.value.length} 份` : '待加载',
      done: papers.value.length > 0,
      prereqMet: true,
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
      lockReason: '请先从 k12100 报告同步结果或已发现试卷选择一场考试后再核对入档。',
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

async function loadCenter() {
  loading.value = true
  loadError.value = ''
  try {
    center.value = await props.client.schoolExamSyncCenter(props.selectedExamId || undefined)
  } catch (error) {
    center.value = null
    loadError.value = describeError(error)
  } finally {
    loading.value = false
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
    const result = await props.client.scanSchoolExamPapers({
      examId: props.selectedExamId || undefined,
    })
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
          await loadCenter()
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
          : '采集任务结束：逐题信息已作为待核对明细保存。'
        collectionError.value = blocked > 0 ? message : ''
        props.notify(message, blocked > 0 ? 'caution' : 'success')
        await loadReview(currentExamId.value)
      } else if (latest.state === 'failed') {
        stopPolling()
        if (latest.report_result) {
          lastReportResult.value = latest.report_result
        }
        await loadCenter()
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
      archiveExamId: currentExamId.value || props.selectedExamId || undefined,
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

function selectReviewSubject(tab: ReviewSubjectTab) {
  activeReviewSubject.value = tab.subject
  confirmTotalAcknowledged.value = false
  if (tab.exam_id && tab.exam_id !== reviewDetail.value?.id) {
    focusedExamId.value = tab.exam_id
    void loadReview(tab.exam_id)
    return
  }
  confirmTotalInput.value = tab.earned_points ?? ''
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
    rankTab.value = 'subject'
    const tabs = reviewSubjectTabs.value
    if (tabs.length > 0 && !tabs.some(t => t.subject === activeReviewSubject.value)) {
      activeReviewSubject.value = tabs[0].subject
    }
    const activeTab = tabs.find(t => t.subject === activeReviewSubject.value) ?? tabs[0]
    if (activeTab && detail.subject === 'all' && activeTab.subject !== 'all') {
      confirmTotalInput.value = activeTab.earned_points ?? ''
    } else {
      confirmTotalInput.value = detail.confirmed_by_user ? detail.earned_points : detail.earned_points || ''
    }
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
    const subjParam =
      detail.subject === 'all' && activeReviewTab.value && activeReviewTab.value.subject !== 'all'
        ? activeReviewTab.value.subject
        : undefined
    await props.client.confirmSchoolExam(detail.id, Number(confirmTotalInput.value), subjParam)
    props.notify('该科总分已人工核对并锁定；其余学科保持各自独立核对状态。', 'success')
    focusedExamId.value = detail.id
    await Promise.all([
      loadReview(detail.id),
      loadCenter(),
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
    await loadCenter()
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
      archiveExamId: props.selectedExamId || undefined,
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
    void loadCenter()
    if (examId && !focusedExamId.value) void loadReview(examId)
  },
)

watch(
  activeStep,
  step => {
    emit('step-change', step)
  },
  { immediate: true },
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
        <span class="muted tiny">{{ selectedExamId ? '档案原卷目录' : '私有收件箱' }}</span>
        <code>{{ center?.source.directory_display || '$PAGEBOY_HOME/development/data/school-exams/inbox' }}</code>
      </div>
      <div class="exam-sync-top-actions">
        <span :class="['chip', isJobActive ? 'wait' : job?.state === 'failed' ? 'bad' : 'subtle']">
          {{ isJobActive ? `采集中 · ${getJobStateLabel(job?.state)}` : job ? `采集${getJobStateLabel(job.state)}` : '未启动采集' }}
        </span>
        <button type="button" class="ghost small" :disabled="loading" @click="loadCenter()">
          {{ loading ? '刷新中…' : '刷新同步中心' }}
        </button>
      </div>
    </header>

    <p v-if="loadError" class="exam-sync-banner bad stage-wrap" role="alert">{{ loadError }}</p>
    <p v-if="actionNotice" :class="['exam-sync-banner', actionTone, 'stage-wrap']" role="status">{{ actionNotice }}</p>

    <StepFlowWorkspace
      v-model="activeStepStr"
      :steps="syncSteps"
      steps-aria-label="校考同步四步工作流"
    >
      <!-- 第一步：发现试卷（合并为单一卡片） -->
      <template #step-1>
        <article class="card" aria-label="发现试卷">
          <div class="card-head">
            <p class="card-sub" style="margin: 0;">本地扫描不会伪造远程下载；任何文件都不会自动进入公共题库。</p>
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
          </div>

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
              <div class="exam-paper-row">
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
              </div>
            </li>
          </ul>
          <div class="card-footer-flow" style="margin-top: 12px;">
            <span />
            <button type="button" class="primary small" @click="goStep(3)">
              下一步：k12100 报告同步 →
            </button>
          </div>
        </article>
      </template>

      <!-- 第三步：k12100 报告同步（自动下载总分报告、新建/更新/补全考试档案） -->
      <template #step-3>
        <article class="card" aria-label="第三步：k12100 报告同步">
          <div class="card-head">
            <p class="card-sub" style="margin: 0;">考试时间取自 k12100 首页，学年 / 年级 / 考试类型 / 学科取自下载的总分分析报告与首页元数据；按原卷所属场次下载。</p>
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
            <div><b>答题卡附件</b><span>从报告册切分并同步各科答题卡至档案目录 answer-sheet/</span></div>
          </div>

          <div class="exam-sync-safety" role="note" style="margin-bottom: 10px;">
            <b>低频与核对红线</b>
            <ul>
              <li>单账号、单会话、串行；每次最多下载 3 场未同步场次，遇验证码或 401/403/429 立即熔断停止。</li>
              <li>新建或更新的总分与待核对明细均保持待人工核对，绝不直接写入能力画像。</li>
            </ul>
          </div>

          <p v-if="runtime && !runtime.can_run_local" class="exam-sync-blocked" role="note">
            本机直连不可用：{{ runtime.unavailable_reason || '当前环境无法启动宿主机浏览器' }}。可使用下方离线采集包同步。
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
                  ? '各场次均已具备日期、全科成绩、待核对明细、答题卡及班/年排名与最高分；点击下方按钮仅检查 k12100 首页是否有新增场次，已完整场次不会重复下载。'
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
              <span class="muted tiny">{{ jobProgress }}% · {{ shortTime(job.updated_at) }}</span>
            </div>
            <div
              class="exam-sync-progress-bar"
              role="progressbar"
              :aria-valuenow="jobProgress"
              aria-valuemin="0"
              aria-valuemax="100"
              aria-label="同步任务进度"
            >
              <span :class="['exam-sync-progress-fill', job.state]" :style="{ width: `${jobProgress}%` }"></span>
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
              <div><b>{{ reportSummary.draftsChanged }} 题</b><span>待核明细变更（切图 {{ reportSummary.cardsSynced }} 页）</span></div>
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
                      待核对 {{ ex.draft_count }} / 已确认 {{ ex.confirmed_item_count }} 题 · 附件 {{ ex.attachment_count }} 份
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
              <div><dt>科目</dt><dd>{{ currentResultRow.subject_label || '全科' }}</dd></div>
              <div><dt>总分</dt><dd>{{ fmtPoints(currentResultRow.earned_points) }} / {{ fmtPoints(currentResultRow.max_points) }} · {{ currentResultRow.confirmed_by_user ? '已核对' : '待核对' }}</dd></div>
              <div><dt>答题卡</dt><dd>新上传 {{ currentResultRow.attachments_uploaded }} 份</dd></div>
              <div><dt>待核对明细</dt><dd>{{ currentResultRow.drafts_created }} 题待人工确认</dd></div>
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
                <p class="muted tiny">合法导出的脱敏 JSON；服务端二次 PII 清洗并强制待核对门禁。</p>
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

          <div class="card-footer-flow" style="margin-top: 12px;">
            <button type="button" class="ghost small" @click="goStep(1)">
              ← 上一步：发现试卷
            </button>
            <button
              v-if="currentExamId || syncedReports[0]?.exams[0]?.exam_id"
              type="button"
              class="primary small"
              @click="currentExamId ? goStep(4) : inspectReportExam(syncedReports[0].exams[0].exam_id)"
            >
              下一步：核对入档 →
            </button>
          </div>
        </article>
      </template>

      <!-- 第四步：核对入档（所有科目分 Tab 核对总分与本人排名） -->
      <template #step-4>
        <div v-if="reviewLoading" class="card exam-sync-empty">正在读取成绩、待核对明细与本人排名…</div>
        <article v-else class="card" aria-label="第四步：核对入档">
          <div class="card-head">
            <p class="card-sub" style="margin: 0;">{{ reviewDetail?.title || currentExamTitle }} · {{ fmtExamMonth(reviewDetail?.exam_date) }} · 源：{{ SOURCE_KIND_LABELS[reviewDetail?.source_kind || 'manual'] || reviewDetail?.source_kind || '手工建档' }}</p>
            <span :class="['chip', activeSubjectConfirmed ? 'good' : 'wait']">
              {{ activeSubjectConfirmed ? '总分已核对' : '总分待核对' }}
            </span>
          </div>

          <div v-if="reviewSubjectTabs.length > 0" class="exam-sync-subject-tabs" role="tablist" aria-label="核对科目切换">
            <button
              v-for="tab in reviewSubjectTabs"
              :key="tab.subject"
              type="button"
              role="tab"
              :aria-selected="activeReviewTab?.subject === tab.subject"
              :class="['exam-sync-subject-tab', { active: activeReviewTab?.subject === tab.subject }]"
              @click="selectReviewSubject(tab)"
            >
              <span>{{ tab.subject_label }}</span>
              <span :class="['chip', 'tiny', tab.confirmed_by_user ? 'good' : 'wait']">
                {{ tab.confirmed_by_user ? '已核' : '待核' }}
              </span>
            </button>
          </div>

          <div class="exam-sync-review-kpis">
            <div>
              <b>
                {{
                  activeReviewTab && activeReviewTab.earned_points !== null && activeReviewTab.max_points !== null
                    ? `${fmtPoints(activeReviewTab.earned_points)} / ${fmtPoints(activeReviewTab.max_points)}`
                    : reviewDetail
                      ? `${fmtPoints(reviewDetail.earned_points)} / ${fmtPoints(reviewDetail.max_points)}`
                      : '—'
                }}
              </b>
              <span>{{ activeReviewTab ? `${activeReviewTab.subject_label}总分` : '总分' }}（待核对不进入画像）</span>
            </div>
            <div>
              <b>{{ reviewCoverage.confirmedItems }} 题</b>
              <span>已人工确认逐题</span>
            </div>
            <div>
              <b>{{ reviewCoverage.draftItems }} 题</b>
              <span>待核对明细</span>
            </div>
            <div>
              <b>{{ reviewCoverage.attachments }} 份</b>
              <span>私有答题卡/原卷</span>
            </div>
          </div>

          <div v-if="!activeSubjectConfirmed" class="exam-sync-confirm-box">
            <h4 style="margin-top: 0;">人工核对总分{{ activeReviewTab ? `（${activeReviewTab.subject_label}）` : '' }}</h4>
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
            <div class="card-head" style="gap: 8px; flex-wrap: wrap;">
              <div>
                <h4 style="margin: 0;">
                  {{
                    rankTab === 'total' && hasTotalRankSummary
                      ? '同场全科总分排名与最高分'
                      : `本人排名快照（${activeSubjectRanks.length} 个范围）`
                  }}
                </h4>
                <p class="card-sub">平台实际提供的本人排名；独立保存，不进入知识点能力画像。</p>
              </div>
              <div
                v-if="hasTotalRankSummary"
                class="subject-row"
                role="tablist"
                aria-label="排名维度"
              >
                <button
                  type="button"
                  role="tab"
                  :aria-selected="rankTab === 'subject'"
                  :class="rankTab === 'subject' ? 'subject-chip selected' : 'subject-chip'"
                  @click="rankTab = 'subject'"
                >
                  本学科排名
                </button>
                <button
                  type="button"
                  role="tab"
                  :aria-selected="rankTab === 'total'"
                  :class="rankTab === 'total' ? 'subject-chip selected' : 'subject-chip'"
                  @click="rankTab = 'total'"
                >
                  同场全科总分排名与最高分
                </button>
              </div>
            </div>
            <template v-if="rankTab === 'total' && hasTotalRankSummary">
              <div v-if="reviewRanks?.report_total" class="exam-sync-missing" style="margin-bottom: 8px;">
                <b>全科总分汇总</b>
                <span>
                  总分 {{ reviewRanks.report_total.report_total_score !== null ? fmtPoints(reviewRanks.report_total.report_total_score) : '—' }} / {{ reviewRanks.report_total.report_total_max !== null ? fmtPoints(reviewRanks.report_total.report_total_max) : '—' }}
                  · 班排 {{ reviewRanks.report_total.total_class_rank ?? '—' }}
                  · 年排 {{ reviewRanks.report_total.total_grade_rank ?? '—' }}{{ reviewRanks.report_total.total_participants ? ` / ${reviewRanks.report_total.total_participants}人` : '' }}
                  · 班最高 {{ reviewRanks.report_total.total_class_highest !== null ? fmtPoints(reviewRanks.report_total.total_class_highest) : '—' }}
                  · 年最高 {{ reviewRanks.report_total.total_grade_highest !== null ? fmtPoints(reviewRanks.report_total.total_grade_highest) : '—' }}
                </span>
              </div>
              <ul v-if="(reviewRanks?.total_ranks?.length ?? 0) > 0" class="exam-sync-ranks" tabindex="0" aria-label="全科总分排名列表">
                <li v-for="rank in reviewRanks?.total_ranks ?? []" :key="rank.id">
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
            </template>
            <template v-else>
              <div v-if="reviewRanks && activeSubjectRanks.length === 0" class="exam-sync-empty">
                <b>平台未提供可用排名</b>
                <p>
                  {{
                    filteredMissingRankScopes.length
                      ? `系统不会用 0 或推算值补齐。缺失范围：${filteredMissingRankScopes.map(scope => RANK_SCOPE_LABELS[scope] || scope).join('、')}。`
                      : '系统不会用 0 或推算值补齐。'
                  }}
                </p>
              </div>
              <ul v-else class="exam-sync-ranks" tabindex="0" aria-label="本人排名列表">
                <li v-for="rank in activeSubjectRanks" :key="rank.id">
                  <div class="exam-sync-rank-main">
                    <b>
                      {{
                        activeReviewTab?.subject === 'all' && rank.subject_scope
                          ? `${SUBJECT_LABELS[rank.subject_scope] || rank.subject_scope} · ${RANK_SCOPE_LABELS[rank.scope] || rank.scope}`
                          : (RANK_SCOPE_LABELS[rank.scope] || rank.scope)
                      }}
                    </b>
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
              <div class="exam-sync-missing" style="margin-top: 8px;">
                <b>缺失信息</b>
                <span>{{ filteredMissingRankScopes.length ? filteredMissingRankScopes.map(scope => RANK_SCOPE_LABELS[scope] || scope).join('、') : '班级、年级排名均已提供' }}</span>
              </div>
            </template>
            <p class="muted tiny">{{ reviewRanks?.disclaimer || '本人排名不得用于推断中考成绩。' }}</p>
          </div>

          <p v-if="reviewError" class="exam-sync-banner bad" role="alert">{{ reviewError }}</p>
        </article>
      </template>
    </StepFlowWorkspace>

    <footer class="exam-sync-footer stage-wrap">
      <p>待核对明细、未锁定总分和本人排名都不会写入学生端能力画像。所有自动获取都受账号授权、平台规则与低频边界约束。</p>
    </footer>
  </section>
</template>
