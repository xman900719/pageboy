<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  describeError,
  SCHOOL_SUBJECT_LABELS,
  type ApiClient,
  type K12100BackfillResult,
  type K12100RuntimeStatus,
  type K12100SubjectResult,
  type K12100SyncJob,
  type SchoolErrorCategory,
  type SchoolExam,
  type SchoolExamDetail,
  type SchoolExamErrorAnalysis,
  type SchoolExamItem,
  type SchoolSubject,
} from '../../api'
import { EXAM_NOTE, fmtBytes, fmtPoints, shortTime } from '../../copy'
import {
  getKnowledgeLabel,
  getMediaTypeLabel,
  getSchoolErrorCategoryLabel,
  SCHOOL_ERROR_CATEGORY_OPTIONS,
} from '../../config/knowledge'
import type { NoticeTone } from '../Notice.vue'

type Notify = (text: string, tone?: NoticeTone) => void
type ExamTabId = 'scores' | 'papers' | 'items' | 'analysis' | 'create'

const DIAGNOSIS_TAG_META: Record<string, { label: string; tone: string }> = {
  double_weak: { label: '双重薄弱 · 优先突破', tone: 'bad' },
  blind_spot: { label: '证据盲区 · 建议诊断', tone: 'wait' },
  exam_slip: { label: '平时已达标 · 排查粗心/审题', tone: 'good' },
  archive_review: { label: '档案复盘', tone: 'mid' },
}

const PRACTICE_STATUS_TEXT: Record<string, string> = {
  weak: '日常薄弱',
  mastered: '日常已掌握',
  insufficient: '日常样本不足',
  untested: '日常尚未作答',
  not_applicable: '无公共图谱',
}

const DRAFT_CONFIDENCE_META: Record<string, { label: string; tone: string }> = {
  high: { label: '高置信识别', tone: 'good' },
  medium: { label: '中等置信', tone: 'mid' },
  low: { label: '低置信 · 请核对分值', tone: 'bad' },
  skeleton_only: { label: '仅题号与分值骨架', tone: 'wait' },
  external_sync: { label: '外部平台抓取', tone: 'mid' },
}

function fmtPct(rate: number | null | undefined): string {
  if (rate === null || rate === undefined) return '—'
  return `${Math.round(rate * 100)}%`
}

// 校卷附件允许与后端一致的 35 MiB 上限
const MAX_PAPER_BYTES = 35 * 1024 * 1024
const DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
const ALLOWED_TYPES = new Set(['application/pdf', DOCX_MIME, 'image/png', 'image/jpeg'])
const EXT_TYPES: Record<string, string> = {
  pdf: 'application/pdf',
  docx: DOCX_MIME,
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
}

function pickPaperMime(file: File): string | null {
  if (ALLOWED_TYPES.has(file.type)) return file.type
  const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
  return EXT_TYPES[ext] ?? null
}

const K12_MAX_BUNDLE_BYTES = 15 * 1024 * 1024

const SCORE_STATUS_LABEL: Record<string, { text: string; tone: string }> = {
  created_confirmed: { text: '已补建并锁定总分', tone: 'good' },
  created_unconfirmed: { text: '已补建（总分待手锁）', tone: 'wait' },
  confirmed_now: { text: '已核对锁定总分', tone: 'good' },
  updated_unconfirmed: { text: '已更新暂存总分', tone: 'wait' },
  already_confirmed_match: { text: '总分已锁且一致', tone: 'good' },
  locked_conflict: { text: '保留原锁分（分值不同）', tone: 'bad' },
}

const STEM_MODE_LABEL: Record<string, string> = {
  pdf_deepseek: '原卷 PDF + DeepSeek 提干',
  pdf_local_regex: '原卷 PDF 本地切分',
  no_pdf: '无原卷（按大题客观结构）',
  empty_pdf: '原卷 PDF 无文字层',
  pdf_parse_failed: '原卷提取异常（已跳过）',
  disabled: '未启用 PDF 提干',
}

const props = defineProps<{
  client: ApiClient
  subject: SchoolSubject
  notify: Notify
  initialExamId?: string
  initialTab?: ExamTabId
}>()

const emit = defineEmits<{
  (e: 'select-subject', subject: SchoolSubject, examId?: string, tab?: 'scores' | 'items'): void
}>()

const exams = ref<SchoolExam[] | null>(null)
const selectedExamId = ref<string | null>(null)
const selectedDetail = ref<SchoolExamDetail | null>(null)
const errorAnalysis = ref<SchoolExamErrorAnalysis | null>(null)
const loadingDetail = ref(false)
const activeTab = ref<ExamTabId>(props.initialTab ?? 'scores')

// k12100.com 全科补全抽屉状态与轮询管理
const showK12100Panel = ref(false)
const loadingK12Status = ref(false)
const runtimeStatus = ref<K12100RuntimeStatus | null>(null)
const k12ExamKeyword = ref('')
const k12TargetDate = ref('')
const k12SeriesPrefix = ref('')
const k12ConfirmTotalScores = ref(true)
const k12ExtractExistingPdfs = ref(true)
const k12UploadMissingCards = ref(true)
const k12ReplaceUnconfirmedDrafts = ref(true)
const k12UseAi = ref(true)
const k12ShowBrowserWindow = ref(false)
const startingK12Job = ref(false)
const importingK12Bundle = ref(false)
const activeK12Job = ref<K12100SyncJob | null>(null)
const lastK12Result = ref<K12100BackfillResult | null>(null)
const k12ErrorText = ref('')
const k12BundleInputRef = ref<HTMLInputElement | null>(null)
let k12PollTimer: ReturnType<typeof setInterval> | null = null

const isK12JobActive = computed(() => {
  const st = activeK12Job.value?.state
  return st === 'queued' || st === 'collecting' || st === 'backfilling'
})

const computedCliCommand = computed(() => {
  const base = runtimeStatus.value?.recommended_cli_command || 'uv run python scripts/k12100_sync.py collect --config-dir ~/.config/shutong'
  const parts = [base]
  const kw = k12ExamKeyword.value.trim()
  if (kw && !base.includes('--exam-keyword')) {
    parts.push(`--exam-keyword "${kw.replace(/"/g, '')}"`)
  }
  if (!k12ConfirmTotalScores.value && base.includes('backfill')) {
    parts.push('--no-confirm-total-scores')
  }
  return parts.join(' ')
})

// B1「? 校考录入说明」锚点浮层气泡状态
const showHelp = ref(false)
const helpAnchorRef = ref<HTMLElement | null>(null)

// 新建校考表单状态
const examTitle = ref('')
const examDate = ref(new Date().toISOString().slice(0, 10))
const examEarned = ref<number | ''>('')
const examMax = ref(100)
const createConfirmed = ref(true)
const savingExam = ref(false)

// 待核对总分补充确认状态
const confirmEarned = ref<number | ''>('')
const confirmingExam = ref(false)

// 私有原卷/答题卡上传状态
const paperFile = ref<File | null>(null)
const paperInputRef = ref<HTMLInputElement | null>(null)
const uploadingPaper = ref(false)
const uploadError = ref('')

// 逐题得分与错因补录状态
const itemLabel = ref('')
const itemKnowledgeId = ref('')
const itemEarned = ref<number | ''>('')
const itemMax = ref<number | ''>('')
const itemErrorCategory = ref<SchoolErrorCategory | ''>('')
const itemErrorNote = ref('')
const savingItem = ref(false)
const confirmingItemId = ref<string | null>(null)

// 已有小题的行内错因与复盘备注编辑状态
const editingAnalysisItemId = ref<string | null>(null)
const editErrorCategory = ref<SchoolErrorCategory | ''>('')
const editErrorNote = ref('')
const savingAnalysis = ref(false)

// M2 自动解析与草稿校对台状态
const selectedParseAttachmentIds = ref<string[]>([])
const lastParseInitExamId = ref<string | null>(null)
const parseMode = ref<'auto' | 'skeleton_only'>('auto')
const maskStudentHeader = ref(true)
const replaceUnconfirmedDrafts = ref(false)
const parsingDrafts = ref(false)
const parseDraftError = ref('')
const lastParseSummary = ref('')
const discardingItemId = ref<string | null>(null)
const batchConfirming = ref(false)
const draftEdits = ref<
  Record<
    string,
    {
      earnedPoints: number | ''
      maxPoints: number | ''
      knowledgeId: string
      errorCategory: SchoolErrorCategory | ''
      errorNote: string
    }
  >
>({})

const PARSEABLE_MEDIA_TYPES = new Set([
  'application/pdf',
  DOCX_MIME,
  'image/png',
  'image/jpeg',
])

const parseableAttachments = computed(
  () => selectedDetail.value?.attachments.filter(a => PARSEABLE_MEDIA_TYPES.has(a.media_type)) ?? []
)
const unconfirmedDrafts = computed(
  () => selectedDetail.value?.items.filter(it => !it.confirmed_by_user) ?? []
)
const confirmedItems = computed(
  () => selectedDetail.value?.items.filter(it => it.confirmed_by_user) ?? []
)

const isNewItemLost = computed(
  () => itemEarned.value !== '' && itemMax.value !== '' && Number(itemEarned.value) < Number(itemMax.value)
)

const selectedExamSummary = computed(
  () => exams.value?.find(e => e.id === selectedExamId.value) ?? null
)

// 五类内容 Tab 定义及实时状态/计数徽章
const categoryTabs = computed(() => {
  const listCount = exams.value?.length ?? 0
  const ex = selectedDetail.value ?? selectedExamSummary.value
  const scoreBadge = ex ? (ex.confirmed_by_user ? '已核对' : '待补总分') : `${listCount} 场`
  const paperBadge = selectedDetail.value ? `${selectedDetail.value.attachments.length} 份` : '附件'
  const draftCount = unconfirmedDrafts.value.length
  const itemBadge = selectedDetail.value
    ? draftCount > 0
      ? `${draftCount} 待核对`
      : `${selectedDetail.value.items.length} 条`
    : '明细'
  const analysisBadge =
    errorAnalysis.value?.status === 'analyzed'
      ? `失分 ${errorAnalysis.value.overview.lost_item_count} 题`
      : errorAnalysis.value?.status === 'no_errors_recorded'
        ? '无失分'
        : '待录明细'
  const analysisWait = Boolean(
    errorAnalysis.value?.status === 'analyzed' &&
      (errorAnalysis.value.overview.uncategorized_item_count > 0 ||
        errorAnalysis.value.recurring_knowledge.some(r => r.repeat_in_current_exam))
  )

  return [
    {
      id: 'scores' as const,
      title: '总分台账与核对',
      sub: '校考列表 · 总分与锁分',
      badge: scoreBadge,
      wait: Boolean(ex && !ex.confirmed_by_user),
    },
    {
      id: 'papers' as const,
      title: '原卷与答题卡',
      sub: '私有原件上传 · 归档列表',
      badge: paperBadge,
      wait: false,
    },
    {
      id: 'items' as const,
      title: '逐题得分与考点',
      sub: props.subject === 'ethics' ? '逐题失分 · 错因标注' : '自动解析 · 草稿校对与明细',
      badge: itemBadge,
      wait: draftCount > 0,
    },
    {
      id: 'analysis' as const,
      title: '错误分析与复盘',
      sub: '错因分布 · 跨场顽固失分',
      badge: analysisBadge,
      wait: analysisWait,
    },
    {
      id: 'create' as const,
      title: '+ 新建校考档案',
      sub: '录入已核对 / 暂存待核对',
      badge: '建档',
      wait: false,
    },
  ]
})

function toggleHelp() {
  showHelp.value = !showHelp.value
}

function closeHelp() {
  showHelp.value = false
}

function onDocumentPointerDown(event: Event) {
  if (!showHelp.value) return
  const target = event.target as Node | null
  if (helpAnchorRef.value && target && !helpAnchorRef.value.contains(target)) {
    closeHelp()
  }
}

function onDocumentKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && showHelp.value) {
    closeHelp()
  }
}

onMounted(() => {
  document.addEventListener('pointerdown', onDocumentPointerDown)
  document.addEventListener('keydown', onDocumentKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocumentPointerDown)
  document.removeEventListener('keydown', onDocumentKeydown)
  stopK12Polling()
})

async function loadDetail(examId: string) {
  loadingDetail.value = true
  try {
    const [detail, analysis] = await Promise.all([
      props.client.schoolExamDetail(examId),
      props.client.schoolExamErrorAnalysis(examId),
    ])
    selectedDetail.value = detail
    errorAnalysis.value = analysis
    confirmEarned.value = detail.earned_points
    syncDraftStateFromDetail(detail)
  } catch (e) {
    selectedDetail.value = null
    errorAnalysis.value = null
    props.notify(describeError(e), 'error')
  } finally {
    loadingDetail.value = false
  }
}

function syncDraftStateFromDetail(detail: SchoolExamDetail) {
  const validAttachIds = detail.attachments
    .filter(a => PARSEABLE_MEDIA_TYPES.has(a.media_type))
    .map(a => a.id)
  if (lastParseInitExamId.value !== detail.id) {
    selectedParseAttachmentIds.value = [...validAttachIds]
    lastParseInitExamId.value = detail.id
    parseDraftError.value = ''
    lastParseSummary.value = ''
  } else {
    const existingSet = new Set(validAttachIds)
    const kept = selectedParseAttachmentIds.value.filter(id => existingSet.has(id))
    selectedParseAttachmentIds.value = kept.length > 0 ? kept : [...validAttachIds]
  }

  const nextEdits: typeof draftEdits.value = {}
  for (const it of detail.items) {
    if (it.confirmed_by_user) continue
    nextEdits[it.id] = draftEdits.value[it.id] ?? {
      earnedPoints: it.earned_points,
      maxPoints: it.max_points,
      knowledgeId: it.knowledge_id,
      errorCategory: it.error_category ?? '',
      errorNote: it.error_note ?? '',
    }
  }
  draftEdits.value = nextEdits
}

async function refreshExams(preferId?: string) {
  try {
    const list = await props.client.schoolExams(props.subject)
    exams.value = list
    const targetId =
      preferId && list.some(e => e.id === preferId)
        ? preferId
        : selectedExamId.value && list.some(e => e.id === selectedExamId.value)
          ? selectedExamId.value
          : (list[0]?.id ?? null)
    selectedExamId.value = targetId
    if (targetId) {
      await loadDetail(targetId)
    } else {
      selectedDetail.value = null
      errorAnalysis.value = null
    }
  } catch {
    exams.value = null
    selectedExamId.value = null
    selectedDetail.value = null
    errorAnalysis.value = null
  }
}

watch(
  [() => props.client, () => props.subject],
  () => {
    stopK12Polling()
    paperFile.value = null
    uploadError.value = ''
    showHelp.value = false
    editingAnalysisItemId.value = null
    lastParseInitExamId.value = null
    selectedParseAttachmentIds.value = []
    parseDraftError.value = ''
    lastParseSummary.value = ''
    draftEdits.value = {}
    void refreshExams(props.initialExamId)
  },
  { immediate: true }
)

async function selectExam(examId: string) {
  selectedExamId.value = examId
  uploadError.value = ''
  editingAnalysisItemId.value = null
  await loadDetail(examId)
}

async function saveExam() {
  const title = examTitle.value.trim()
  if (title === '') {
    props.notify('请填写考试名称。', 'caution')
    return
  }
  if (createConfirmed.value && examEarned.value === '') {
    props.notify('请填写考试名称与得分。', 'caution')
    return
  }
  const earned = examEarned.value === '' ? 0 : Number(examEarned.value)
  savingExam.value = true
  try {
    const created = await props.client.addSchoolExam({
      subject: props.subject,
      title,
      examDate: examDate.value,
      earnedPoints: earned,
      maxPoints: Number(examMax.value),
      confirmedByUser: createConfirmed.value,
    })
    props.notify(
      createConfirmed.value
        ? `学校考试已记录。${EXAM_NOTE}`
        : '待核对学校考试档案已暂存，请上传原卷/答题卡并在后续补充确认总分。',
      'success'
    )
    examTitle.value = ''
    examEarned.value = ''
    await refreshExams(created.id)
    activeTab.value = 'scores'
  } catch (e) {
    props.notify(describeError(e), 'error')
  } finally {
    savingExam.value = false
  }
}

async function confirmSelectedExam() {
  if (!selectedDetail.value) return
  if (confirmEarned.value === '') {
    props.notify('请填写实得总分。', 'caution')
    return
  }
  confirmingExam.value = true
  try {
    await props.client.confirmSchoolExam(selectedDetail.value.id, Number(confirmEarned.value))
    props.notify(`校考总分已人工核对并锁定。${EXAM_NOTE}`, 'success')
    await refreshExams(selectedDetail.value.id)
  } catch (e) {
    props.notify(describeError(e), 'error')
  } finally {
    confirmingExam.value = false
  }
}

function onPaperFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  paperFile.value = target.files?.[0] ?? null
  if (paperFile.value) {
    uploadError.value = ''
  }
}

function onPaperInputClick() {
  if (typeof paperInputRef.value?.showPicker === 'function') {
    try {
      paperInputRef.value.showPicker()
    } catch {
      // 浏览器已原生处理或不支持时静默忽略
    }
  }
}

function clearPaperFile() {
  paperFile.value = null
  if (paperInputRef.value) paperInputRef.value.value = ''
  uploadError.value = ''
}

async function uploadPaper() {
  if (!selectedDetail.value) return
  if (!paperFile.value) {
    uploadError.value = '请先选择试卷或答题卡文件。'
    return
  }
  const mime = pickPaperMime(paperFile.value)
  if (mime === null) {
    uploadError.value = '仅支持 PDF / DOCX / PNG / JPG 文件。'
    return
  }
  if (paperFile.value.size > MAX_PAPER_BYTES) {
    uploadError.value = '校卷附件超过 35 MiB 上限。'
    return
  }
  if (paperFile.value.size === 0) {
    uploadError.value = '附件内容为空，无法上传。'
    return
  }
  uploadingPaper.value = true
  uploadError.value = ''
  try {
    const named = new File([paperFile.value], paperFile.value.name, { type: mime })
    const saved = await props.client.uploadSchoolPaper(selectedDetail.value.id, named)
    clearPaperFile()
    props.notify(`私人校卷附件「${saved.filename}」已加密隔离归档。`, 'success')
    await loadDetail(selectedDetail.value.id)
  } catch (e) {
    uploadError.value = describeError(e)
  } finally {
    uploadingPaper.value = false
  }
}

async function addItem() {
  if (!selectedDetail.value) return
  const label = itemLabel.value.trim()
  const kid = itemKnowledgeId.value.trim()
  if (label === '' || kid === '' || itemEarned.value === '' || itemMax.value === '') {
    props.notify('请完整填写题号、知识点编码、小题得分与满分。', 'caution')
    return
  }
  const earnedNum = Number(itemEarned.value)
  const maxNum = Number(itemMax.value)
  const lost = earnedNum < maxNum
  savingItem.value = true
  try {
    await props.client.addSchoolExamItems(selectedDetail.value.id, [
      {
        question_label: label,
        knowledge_id: kid,
        earned_points: earnedNum,
        max_points: maxNum,
        scoring_origin: 'manual_entry',
        error_category: lost && itemErrorCategory.value ? itemErrorCategory.value : null,
        error_note: lost && itemErrorNote.value.trim() ? itemErrorNote.value.trim() : null,
      },
    ])
    props.notify('已录入并确认校考小题得分。', 'success')
    itemLabel.value = ''
    itemEarned.value = ''
    itemErrorCategory.value = ''
    itemErrorNote.value = ''
    await loadDetail(selectedDetail.value.id)
  } catch (e) {
    props.notify(describeError(e), 'error')
  } finally {
    savingItem.value = false
  }
}

function displayKnowledgeName(it: SchoolExamItem): string {
  const local = getKnowledgeLabel(it.knowledge_id)
  if (local !== it.knowledge_id) return local
  return it.knowledge_name && it.knowledge_name !== it.knowledge_id ? it.knowledge_name : it.knowledge_id
}

function resolveDraftKnowledgeHint(it: SchoolExamItem, currentCode: string): string {
  const trimmed = currentCode.trim()
  if (!trimmed) return '请填写或点选上方候选考点'
  const cand = it.draft_knowledge_candidates?.find(c => c.knowledge_id === trimmed)
  if (cand) return cand.title
  const local = getKnowledgeLabel(trimmed)
  if (local !== trimmed) return local
  if (trimmed === it.knowledge_id && it.knowledge_name && it.knowledge_name !== trimmed) {
    return it.knowledge_name
  }
  return trimmed
}

function toggleParseAttachment(attachmentId: string) {
  const list = selectedParseAttachmentIds.value
  selectedParseAttachmentIds.value = list.includes(attachmentId)
    ? list.filter(id => id !== attachmentId)
    : [...list, attachmentId]
}

async function runParseDrafts() {
  if (!selectedDetail.value) return
  if (selectedParseAttachmentIds.value.length === 0) {
    parseDraftError.value = '请至少勾选一份原卷或答题卡附件。'
    return
  }
  parsingDrafts.value = true
  parseDraftError.value = ''
  try {
    const res = await props.client.parseSchoolExamDrafts(selectedDetail.value.id, {
      attachmentIds: selectedParseAttachmentIds.value,
      mode: parseMode.value,
      maskStudentHeader: maskStudentHeader.value,
      replaceUnconfirmedDrafts: replaceUnconfirmedDrafts.value,
    })
    const modeLabel = res.parser_mode_used.startsWith('deepseek_vision')
      ? `DeepSeek 多模态（送检 ${res.meta.pages_sent ?? 0} 页，脱敏 ${res.meta.masked_pages ?? 0} 页）`
      : '本地规则文字骨架提取'
    const skippedMsg =
      res.skipped_labels.length > 0 ? `；已跳过 ${res.skipped_labels.length} 道既有题目` : ''
    lastParseSummary.value = `${modeLabel}：生成 ${res.created_items.length} 条待核对草稿${skippedMsg}`
    props.notify(lastParseSummary.value, 'success')
    draftEdits.value = {}
    await loadDetail(selectedDetail.value.id)
  } catch (e) {
    parseDraftError.value = describeError(e)
  } finally {
    parsingDrafts.value = false
  }
}

function applyCandidateKnowledge(itemId: string, knowledgeId: string) {
  const edit = draftEdits.value[itemId]
  if (edit) {
    edit.knowledgeId = knowledgeId
  }
}

function buildDraftConfirmEntry(it: SchoolExamItem) {
  const edit = draftEdits.value[it.id]
  const earnedNum = Number(edit ? edit.earnedPoints : it.earned_points)
  const maxNum = Number(edit ? edit.maxPoints : it.max_points)
  const kid = (edit ? edit.knowledgeId : it.knowledge_id).trim()
  if (Number.isNaN(earnedNum) || Number.isNaN(maxNum) || maxNum <= 0 || maxNum > 100 || earnedNum < 0) {
    return { error: `「${it.question_label}」分值须在 0 到满分（≤100）之间。` }
  }
  if (earnedNum > maxNum) {
    return { error: `「${it.question_label}」实得分（${earnedNum}）不能大于满分（${maxNum}）。` }
  }
  if (!kid) {
    return { error: `「${it.question_label}」知识点编码不能为空。` }
  }
  const lost = earnedNum < maxNum
  return {
    payload: {
      itemId: it.id,
      earnedPoints: earnedNum,
      maxPoints: maxNum,
      knowledgeId: kid,
      errorCategory: lost && edit?.errorCategory ? edit.errorCategory : null,
      errorNote: lost && edit?.errorNote.trim() ? edit.errorNote.trim() : null,
    },
  }
}

async function confirmDraftItemWithEdits(it: SchoolExamItem) {
  if (!selectedDetail.value) return
  const built = buildDraftConfirmEntry(it)
  if ('error' in built && built.error) {
    props.notify(built.error, 'caution')
    return
  }
  const p = built.payload!
  const confirmInput = {
    earnedPoints: p.earnedPoints,
    maxPoints: p.maxPoints,
    knowledgeId: p.knowledgeId,
    errorCategory: p.errorCategory,
    errorNote: p.errorNote,
  }
  confirmingItemId.value = it.id
  try {
    await props.client.confirmSchoolExamItem(selectedDetail.value.id, it.id, confirmInput)
    props.notify(`「${it.question_label}」已完成人工核对并正式入账。`, 'success')
    await loadDetail(selectedDetail.value.id)
  } catch (e) {
    props.notify(describeError(e), 'error')
  } finally {
    confirmingItemId.value = null
  }
}

async function discardDraftItem(it: SchoolExamItem) {
  if (!selectedDetail.value) return
  discardingItemId.value = it.id
  try {
    await props.client.discardSchoolExamItem(selectedDetail.value.id, it.id)
    props.notify(`已丢弃「${it.question_label}」未确认草稿。`, 'info')
    await loadDetail(selectedDetail.value.id)
  } catch (e) {
    props.notify(describeError(e), 'error')
  } finally {
    discardingItemId.value = null
  }
}

async function confirmAllDraftsBatch() {
  if (!selectedDetail.value || unconfirmedDrafts.value.length === 0) return
  const entries = []
  for (const it of unconfirmedDrafts.value) {
    const built = buildDraftConfirmEntry(it)
    if ('error' in built && built.error) {
      props.notify(built.error, 'caution')
      return
    }
    entries.push(built.payload!)
  }
  batchConfirming.value = true
  try {
    const res = await props.client.confirmSchoolExamItemsBatch(selectedDetail.value.id, entries)
    props.notify(`已批量确认 ${res.evidence_created} 道校考小题并更新错误分析。`, 'success')
    await loadDetail(selectedDetail.value.id)
  } catch (e) {
    props.notify(describeError(e), 'error')
  } finally {
    batchConfirming.value = false
  }
}

function startEditAnalysis(it: SchoolExamItem) {
  editingAnalysisItemId.value = it.id
  editErrorCategory.value = it.error_category ?? ''
  editErrorNote.value = it.error_note ?? ''
}

function cancelEditAnalysis() {
  editingAnalysisItemId.value = null
  editErrorCategory.value = ''
  editErrorNote.value = ''
}

async function saveItemAnalysis(it: SchoolExamItem) {
  if (!selectedDetail.value) return
  savingAnalysis.value = true
  try {
    await props.client.updateSchoolExamItemAnalysis(selectedDetail.value.id, it.id, {
      errorCategory: editErrorCategory.value || null,
      errorNote: editErrorNote.value.trim() || null,
    })
    props.notify(`已保存「${it.question_label}」的错因分类与复盘备注。`, 'success')
    cancelEditAnalysis()
    await loadDetail(selectedDetail.value.id)
  } catch (e) {
    props.notify(describeError(e), 'error')
  } finally {
    savingAnalysis.value = false
  }
}

function jumpToEditItem(itemId: string) {
  activeTab.value = 'items'
  const target = selectedDetail.value?.items.find(it => it.id === itemId)
  if (target) {
    startEditAnalysis(target)
  }
}

function stopK12Polling() {
  if (k12PollTimer !== null) {
    clearInterval(k12PollTimer)
    k12PollTimer = null
  }
}

function buildK12BackfillOptions(includeHeadless = false) {
  return {
    ...(k12ExamKeyword.value.trim() ? { examKeyword: k12ExamKeyword.value.trim() } : {}),
    ...(k12TargetDate.value.trim() ? { targetExamDate: k12TargetDate.value.trim() } : {}),
    ...(k12SeriesPrefix.value.trim() ? { seriesTitlePrefix: k12SeriesPrefix.value.trim() } : {}),
    maxExams: 1,
    confirmTotalScores: k12ConfirmTotalScores.value,
    extractExistingPdfs: k12ExtractExistingPdfs.value,
    uploadMissingCards: k12UploadMissingCards.value,
    replaceUnconfirmedDrafts: k12ReplaceUnconfirmedDrafts.value,
    useAi: k12UseAi.value,
    ...(includeHeadless ? { headless: !k12ShowBrowserWindow.value } : {}),
  }
}

function startK12Polling(jobId: string) {
  stopK12Polling()
  const pollOnce = async () => {
    try {
      const job = await props.client.k12100SyncJob(jobId)
      activeK12Job.value = job
      if (job.state === 'completed') {
        stopK12Polling()
        lastK12Result.value = job.result
        k12ErrorText.value = ''
        await refreshExams()
        const totals = job.result?.totals
        props.notify(
          totals
            ? `k12100 全科补全完成：处理 ${totals.subjects_processed} 科，生成 ${totals.drafts_created} 道待校对草稿。`
            : 'k12100 全科补全完成。',
          'success'
        )
      } else if (job.state === 'failed') {
        stopK12Polling()
        k12ErrorText.value = job.error_message || job.stage_message || '同步任务失败。'
        props.notify(k12ErrorText.value, 'error')
      }
    } catch (e) {
      stopK12Polling()
      k12ErrorText.value = describeError(e)
      props.notify(k12ErrorText.value, 'error')
    }
  }
  k12PollTimer = setInterval(() => {
    void pollOnce()
  }, 1500)
}

async function loadK12100Status() {
  loadingK12Status.value = true
  try {
    const status = await props.client.k12100SyncStatus()
    runtimeStatus.value = status
    if (status.latest_job) {
      activeK12Job.value = status.latest_job
      if (status.latest_job.result) {
        lastK12Result.value = status.latest_job.result
      }
      if (
        status.latest_job.state === 'queued' ||
        status.latest_job.state === 'collecting' ||
        status.latest_job.state === 'backfilling'
      ) {
        startK12Polling(status.latest_job.job_id)
      }
    }
  } catch (e) {
    k12ErrorText.value = describeError(e)
  } finally {
    loadingK12Status.value = false
  }
}

async function toggleK12100Panel() {
  showK12100Panel.value = !showK12100Panel.value
  if (showK12100Panel.value) {
    k12ErrorText.value = ''
    await loadK12100Status()
  }
}

async function runHostK12100Sync() {
  startingK12Job.value = true
  k12ErrorText.value = ''
  try {
    const job = await props.client.startK12100SyncJob(buildK12BackfillOptions(true))
    activeK12Job.value = job
    startK12Polling(job.job_id)
    props.notify('已发起 k12100 全科补全后台任务，请留意阶段进度…', 'info')
  } catch (e) {
    k12ErrorText.value = describeError(e)
    props.notify(k12ErrorText.value, 'error')
    await loadK12100Status()
  } finally {
    startingK12Job.value = false
  }
}

function triggerK12BundlePicker() {
  k12BundleInputRef.value?.click()
}

async function handleK12BundleFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (file.size > K12_MAX_BUNDLE_BYTES) {
    k12ErrorText.value = '上传的采集包体积超过 15 MiB 上限，请减少场次或剔除大图后重试。'
    props.notify(k12ErrorText.value, 'caution')
    return
  }
  k12ErrorText.value = ''
  importingK12Bundle.value = true
  try {
    const parsed = JSON.parse(await file.text()) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error('所选 JSON 文件根节点必须是对象格式。')
    }
    const res = await props.client.importK12100Bundle(
      parsed as Record<string, unknown>,
      buildK12BackfillOptions(false)
    )
    lastK12Result.value = res
    await refreshExams()
    props.notify(
      `采集包导入完成：补全 ${res.totals.subjects_processed} 科，新建 ${res.totals.created_exams} 科，生成 ${res.totals.drafts_created} 道待校对草稿。`,
      'success'
    )
  } catch (e) {
    k12ErrorText.value = e instanceof SyntaxError ? 'JSON 文件格式损坏，无法解析。' : describeError(e)
    props.notify(k12ErrorText.value, 'error')
  } finally {
    importingK12Bundle.value = false
  }
}

async function copyCliCommand() {
  const cmd = computedCliCommand.value
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(cmd)
      props.notify('已复制宿主机采集命令，请粘贴至本地终端执行。', 'success')
      return
    }
  } catch {
    // 剪贴板权限受限时降级提示手动复制
  }
  props.notify(`请手动复制命令：${cmd}`, 'info')
}

async function jumpToResultSubject(row: K12100SubjectResult) {
  if (row.subject === props.subject) {
    await selectExam(row.exam_id)
    activeTab.value = 'items'
    showK12100Panel.value = false
    return
  }
  emit('select-subject', row.subject, row.exam_id, 'items')
}
</script>

<template>
  <section class="exam-workspace" aria-label="学校考试总分">
    <!-- 顶部栏：科目状态 + 精简口径徽章（S1）+ 锚点说明气泡（B1） -->
    <div class="exam-topbar">
      <div class="exam-topbar-left">
        <h2>学校考试 · {{ SCHOOL_SUBJECT_LABELS[subject] }}</h2>
        <span class="chip">共 {{ exams?.length ?? 0 }} 场</span>
        <span class="inline-honest-tag">口径：总分不产生考点证据，也不折算成知识点表现</span>
      </div>
      <div class="exam-topbar-actions">
        <div ref="helpAnchorRef" class="help-bubble-anchor">
          <button
            type="button"
            class="help-trigger"
            :aria-expanded="showHelp"
            aria-controls="school-exam-help-popover"
            @click="toggleHelp"
          >
            <span class="help-dot" aria-hidden="true">?</span>
            校考录入说明
          </button>
          <div
            v-if="showHelp"
            id="school-exam-help-popover"
            class="help-popover"
            role="dialog"
            aria-label="校考录入说明"
          >
            <div class="help-popover-head">
              <b>校考录入与私有档案说明</b>
              <button type="button" class="help-close" aria-label="关闭说明" @click="closeHelp">
                ×
              </button>
            </div>
            <ul>
              <li>
                <strong>总分口径：</strong>由家长或管理员依据纸质答卷如实录入；<b>{{ EXAM_NOTE }}</b> 不作为中考预测。
              </li>
              <li>
                <strong>先归档后补分：</strong>若仅先留存空白原卷与学生答题卡，可取消勾选人工核对；成绩公布后再补充实得总分并确认锁定。
              </li>
              <li>
                <strong>隐私与题库隔离：</strong>私人校卷原卷与学生答题卡仅在私有存储加密隔离保存，不提供公开下载入口，绝不进入公开题库或学生练习流。
              </li>
            </ul>
          </div>
        </div>
        <button
          type="button"
          :class="['k12-drawer-trigger', showK12100Panel ? 'active' : '']"
          :aria-expanded="showK12100Panel"
          aria-controls="k12100-backfill-drawer"
          @click="toggleK12100Panel"
        >
          <span v-if="isK12JobActive" class="sync-pulse-dot" aria-hidden="true" />
          从 k12100 补全各科
        </button>
        <button type="button" class="ghost small" @click="refreshExams()">
          刷新
        </button>
      </div>
    </div>

    <!-- k12100.com 手动全科补全可折叠抽屉（宿主机直跑 + 隔离容器采集包双模闭环） -->
    <section
      v-if="showK12100Panel"
      id="k12100-backfill-drawer"
      class="card k12-backfill-drawer"
      aria-label="从 k12100 补全各科校考信息"
    >
      <div class="card-head">
        <div>
          <h3>从 k12100.com 手动补全各科校考信息</h3>
          <p class="card-sub">
            对齐已录入月考系列、自动补建缺失科目与答题卡、抽提已有原卷 PDF 题干并生成待人工校对草稿
          </p>
        </div>
        <div class="k12-head-right">
          <span v-if="loadingK12Status" class="chip">探测运行态…</span>
          <span
            v-else-if="runtimeStatus?.can_run_local"
            class="chip good"
          >
            宿主机直连就绪 · {{ runtimeStatus.credentials.username_masked || '已配置' }}
          </span>
          <span v-else class="chip wait">
            隔离 / 离线导入模式
          </span>
          <button type="button" class="ghost small" @click="showK12100Panel = false">
            收起
          </button>
        </div>
      </div>

      <div class="analysis-callout">
        <strong>安全与审核口径（INV-04）：</strong>
        仅在管理员手动触发时执行单次采集/导入（限 1~3 场，遇风控/验证码立即熔断）。所有逐题知识点归属与错因建议
        <b>强制标记为「OCR / 同步草稿（待核对）」</b>，须经「OCR / 同步草稿校对台」人工确认后才计入能力画像。
        <span v-if="runtimeStatus && !runtimeStatus.can_run_local && runtimeStatus.unavailable_reason" class="k12-isolation-note">
          当前环境说明：{{ runtimeStatus.unavailable_reason }}
        </span>
      </div>

      <div class="k12-options-grid">
        <label>
          考试关键词筛选（可选）
          <input
            v-model="k12ExamKeyword"
            placeholder="如：统一练习一 / 期中考试（留空抓取最新 1 场）"
          />
        </label>
        <label>
          统一对齐校考日期（可选）
          <input v-model="k12TargetDate" type="date" />
        </label>
        <label>
          补建缺失科目标题前缀（可选）
          <input
            v-model="k12SeriesPrefix"
            placeholder="留空自动匹配同月/同系列档案前缀"
          />
        </label>
      </div>

      <div class="k12-checks-grid">
        <label class="k12-check-item">
          <input v-model="k12ConfirmTotalScores" type="checkbox" />
          <span>以 k12100 官方总分直接确认锁定各科总分（已手动锁定且分值不同时自动保留原值）</span>
        </label>
        <label class="k12-check-item">
          <input v-model="k12ExtractExistingPdfs" type="checkbox" />
          <span>从库中已上传原卷 PDF 自动抽提真实题干与设问</span>
        </label>
        <label class="k12-check-item">
          <input v-model="k12UploadMissingCards" type="checkbox" />
          <span>为尚无附件的科目补传 k12100 答题卡 JPEG</span>
        </label>
        <label class="k12-check-item">
          <input v-model="k12ReplaceUnconfirmedDrafts" type="checkbox" />
          <span>覆盖同题号尚未人工确认的旧草稿（已确认题目永不改写）</span>
        </label>
        <label class="k12-check-item">
          <input v-model="k12UseAi" type="checkbox" />
          <span>使用 DeepSeek 自动匹配课标考点与失分错因建议</span>
        </label>
        <label v-if="runtimeStatus?.can_run_local" class="k12-check-item">
          <input v-model="k12ShowBrowserWindow" type="checkbox" />
          <span>弹出可见 Chromium 窗口（首次登录或遇滑块/图形验证码时勾选）</span>
        </label>
      </div>

      <div class="k12-action-split">
        <div v-if="runtimeStatus?.can_run_local" class="k12-mode-box host-ready">
          <div class="k12-mode-head">
            <b>方式 A · 宿主机直接采集并全科补全</b>
            <span class="chip mid">
              DeepSeek：{{ runtimeStatus.deepseek_configured ? '已配置' : '未配置（将用本地规则）' }}
            </span>
          </div>
          <p class="muted tiny">
            复用本机 0700/0600 持久化浏览器会话与账号低频翻看，全程不暴露明文密码与学生姓名。
          </p>
          <button
            type="button"
            class="primary"
            :disabled="startingK12Job || isK12JobActive || importingK12Bundle"
            @click="runHostK12100Sync"
          >
            {{ startingK12Job || isK12JobActive ? '正在采集并补全各科…' : '手动启动 k12100 全科补全' }}
          </button>
        </div>

        <div class="k12-mode-box">
          <div class="k12-mode-head">
            <b>
              {{ runtimeStatus?.can_run_local ? '方式 B · 导入宿主机脱敏采集包 (.json)' : '上传宿主机导出的脱敏采集包 (.json)' }}
            </b>
            <span class="chip">{{ runtimeStatus?.can_run_local ? '通用导入 / 离线重放' : '隔离容器推荐' }}</span>
          </div>
          <p class="muted tiny">
            适用于容器化生产端或已在宿主机预先采集的场景；上传文件体积上限 15 MiB，服务端先清洗 PII 再入库。
          </p>
          <div class="k12-bundle-actions">
            <input
              ref="k12BundleInputRef"
              type="file"
              accept=".json,application/json"
              class="sr-only-input"
              aria-label="选择 k12100 脱敏采集包 JSON 文件"
              @change="handleK12BundleFile"
            />
            <button
              type="button"
              :class="runtimeStatus?.can_run_local ? 'secondary' : 'primary'"
              :disabled="importingK12Bundle || isK12JobActive"
              @click="triggerK12BundlePicker"
            >
              {{ importingK12Bundle ? '正在解析与入库…' : '选择脱敏采集包 (.json) 并导入' }}
            </button>
          </div>
          <div class="k12-cli-box">
            <span class="muted tiny">宿主机导出 / CLI 直连参考命令：</span>
            <div class="k12-cli-row">
              <code>{{ computedCliCommand }}</code>
              <button type="button" class="ghost small" @click="copyCliCommand">
                复制命令
              </button>
            </div>
          </div>
        </div>
      </div>

      <div v-if="activeK12Job" class="k12-job-status">
        <div class="k12-job-head">
          <b>任务进度 · {{ activeK12Job.state }}</b>
          <span
            :class="[
              'chip',
              activeK12Job.state === 'completed'
                ? 'good'
                : activeK12Job.state === 'failed'
                  ? 'bad'
                  : 'wait',
            ]"
          >
            {{ activeK12Job.stage_message }}
          </span>
        </div>
      </div>

      <p v-if="k12ErrorText" class="k12-error-banner" role="alert">
        {{ k12ErrorText }}
      </p>

      <div v-if="lastK12Result" class="k12-result-block">
        <div class="k12-result-head">
          <b>
            补全结果 · {{ lastK12Result.source_exam_title }}
            <small v-if="lastK12Result.source_exam_date" class="muted">（源日期 {{ lastK12Result.source_exam_date }}）</small>
          </b>
          <div class="k12-result-kpis">
            <span class="chip good">处理 {{ lastK12Result.totals.subjects_processed }} 科</span>
            <span class="chip">新建 {{ lastK12Result.totals.created_exams }} 科</span>
            <span class="chip">补传卡图 {{ lastK12Result.totals.attachments_uploaded }} 张</span>
            <span class="chip wait">待核对草稿 {{ lastK12Result.totals.drafts_created }} 题</span>
          </div>
        </div>
        <div class="table-scroll">
          <table class="trace">
            <thead>
              <tr>
                <th>科目</th>
                <th>对齐校考档案</th>
                <th>总分处理</th>
                <th>原卷提干与 AI 标注</th>
                <th>附件</th>
                <th>生成草稿</th>
                <th>快捷校对</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in lastK12Result.subjects" :key="row.exam_id">
                <td><b>{{ row.subject_label }}</b></td>
                <td class="answer-cell">
                  <div>{{ row.exam_title }}</div>
                  <div class="muted tiny">{{ row.exam_date }}</div>
                  <div v-if="row.warning" class="k12-row-warn">{{ row.warning }}</div>
                </td>
                <td>
                  <div>{{ fmtPoints(row.earned_points) }} / {{ fmtPoints(row.max_points) }}</div>
                  <span :class="['chip', SCORE_STATUS_LABEL[row.score_status]?.tone || 'mid']">
                    {{ SCORE_STATUS_LABEL[row.score_status]?.text || row.score_status }}
                  </span>
                </td>
                <td>
                  <div>{{ STEM_MODE_LABEL[row.stem_mode] || row.stem_mode }}</div>
                  <div class="muted tiny">{{ row.parser_mode_used }}</div>
                </td>
                <td>{{ row.attachments_uploaded > 0 ? `+${row.attachments_uploaded} 张` : '保持已有' }}</td>
                <td><b>{{ row.drafts_created }}</b> 题</td>
                <td>
                  <button
                    type="button"
                    class="ghost small"
                    @click="jumpToResultSubject(row)"
                  >
                    去校对草稿
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <!-- 同类内容卡片分类 Tab 导航 -->
    <div class="category-tabs" role="tablist" aria-label="校考同类内容分类">
      <button
        v-for="tab in categoryTabs"
        :key="tab.id"
        :id="`exam-tab-${tab.id}`"
        type="button"
        role="tab"
        :aria-selected="activeTab === tab.id"
        :aria-controls="`exam-panel-${tab.id}`"
        :class="['cat-tab', activeTab === tab.id ? 'active' : '']"
        @click="activeTab = tab.id"
      >
        <span class="cat-tab-text">
          <b>{{ tab.title }}</b>
          <small>{{ tab.sub }}</small>
        </span>
        <span :class="['cat-tab-badge', tab.wait ? 'wait' : '']">{{ tab.badge }}</span>
      </button>
    </div>

    <!-- 在原卷/逐题/错误分析 Tab 下展示当前处理场次快速切换条 -->
    <div
      v-if="(activeTab === 'papers' || activeTab === 'items' || activeTab === 'analysis') && exams && exams.length > 0 && selectedDetail"
      class="active-exam-bar"
    >
      <div class="active-exam-info">
        <span class="muted tiny">当前查看场次：</span>
        <b>{{ selectedDetail.title }}</b>
        <span :class="['chip', selectedDetail.confirmed_by_user ? 'good' : 'wait']">
          {{ fmtPoints(selectedDetail.earned_points) }} / {{ fmtPoints(selectedDetail.max_points) }} ·
          {{ selectedDetail.confirmed_by_user ? '已核对' : '未核对' }}
        </span>
      </div>
      <div v-if="exams.length > 1" class="active-exam-switcher">
        <span class="muted tiny">快速切换：</span>
        <button
          v-for="ex in exams"
          :key="ex.id"
          type="button"
          :class="['mini-switch-btn', ex.id === selectedExamId ? 'selected' : '']"
          @click="selectExam(ex.id)"
        >
          {{ ex.exam_date }} ({{ fmtPoints(ex.earned_points) }}/{{ fmtPoints(ex.max_points) }})
        </button>
      </div>
    </div>

    <!-- Tab 1：总分台账与核对（校考列表卡 + 选中场次总分概览与补分锁定卡） -->
    <div
      v-if="activeTab === 'scores'"
      id="exam-panel-scores"
      role="tabpanel"
      aria-labelledby="exam-tab-scores"
      class="tab-card-grid-2"
    >
      <section class="card" aria-label="已录校考台账">
        <div class="card-head">
          <div>
            <h3>已录校考台账 · {{ SCHOOL_SUBJECT_LABELS[subject] }}</h3>
            <p class="card-sub">点击场次即可在右侧查看总分状态或补充核对</p>
          </div>
          <span class="chip">{{ exams?.length ?? 0 }} 场</span>
        </div>
        <p v-if="exams === null" class="muted">已录入考试加载中…</p>
        <p v-else-if="exams.length === 0" class="muted">
          当前科目还没有录入过学校考试记录，可点击上方「+ 新建校考档案」添加。
        </p>
        <ul v-else class="exam-list">
          <li
            v-for="exam in exams"
            :key="exam.id"
            :class="['exam-item', exam.id === selectedExamId ? 'selected' : '']"
          >
            <button
              type="button"
              class="source-pick exam-pick"
              :aria-pressed="exam.id === selectedExamId"
              @click="selectExam(exam.id)"
            >
              <span class="exam-title">{{ exam.title }}</span>
              <span class="muted tiny">
                {{ exam.exam_date }} · <b>{{ fmtPoints(exam.earned_points) }} / {{ fmtPoints(exam.max_points) }}</b>
              </span>
            </button>
            <span :class="['chip', exam.confirmed_by_user ? 'good' : 'wait']">
              {{ exam.confirmed_by_user ? '已核对' : '未核对' }}
            </span>
          </li>
        </ul>
      </section>

      <section class="card exam-detail" aria-label="总分概览与核对锁定">
        <p v-if="selectedExamId && loadingDetail && !selectedDetail" class="muted">正在加载校考详情…</p>
        <template v-else-if="selectedDetail">
          <div class="card-head">
            <div>
              <h3>总分概览：{{ selectedDetail.title }}</h3>
              <p class="card-sub">总分仅作阶段台账记录，不折算考点得分</p>
            </div>
            <span :class="['chip', selectedDetail.confirmed_by_user ? 'good' : 'wait']">
              {{ selectedDetail.confirmed_by_user ? '总分已核对锁定' : '总分待补充确认' }}
            </span>
          </div>

          <div class="exam-kpi-row">
            <div :class="['kpi-tile', selectedDetail.confirmed_by_user ? 'good' : 'wait']">
              <b>{{ fmtPoints(selectedDetail.earned_points) }} / {{ fmtPoints(selectedDetail.max_points) }}</b>
              <span>实得 / 满分</span>
            </div>
            <div class="kpi-tile">
              <b>{{ selectedDetail.exam_date }}</b>
              <span>考试日期</span>
            </div>
            <div class="kpi-tile">
              <b>{{ selectedDetail.attachments.length }} 份</b>
              <span>私有原件附件</span>
            </div>
          </div>

          <div v-if="!selectedDetail.confirmed_by_user" class="exam-confirm-panel">
            <p class="muted tiny" style="margin: 0 0 8px;">
              该场考试当前为待核对归档状态，核实成绩后可在此补充实得总分（确认后不可改写）。
            </p>
            <div class="confirm-inline-row">
              <label>
                补充实得总分
                <input
                  type="number"
                  :min="0"
                  :max="selectedDetail.max_points"
                  step="0.5"
                  v-model.number="confirmEarned"
                />
              </label>
              <button
                type="button"
                class="primary"
                @click="confirmSelectedExam"
                :disabled="confirmingExam"
              >
                {{ confirmingExam ? '确认中…' : '确认并锁定总分' }}
              </button>
            </div>
          </div>
          <p v-else class="muted tiny" style="margin: 8px 0 0;">
            该场次总分已完成人工核对并锁定，不支持通过接口重复覆写；如需挂载纸质原卷可切至「原卷与答题卡」页签。
          </p>
        </template>
        <template v-else>
          <div class="card-head">
            <h3>总分概览与核对锁定</h3>
          </div>
          <p class="muted">请先在左侧选择一场学校考试，或切换至「+ 新建校考档案」录入。</p>
        </template>
      </section>
    </div>

    <!-- Tab 2：原卷与答题卡（私有原件上传卡 + 已归档附件列表卡） -->
    <div
      v-else-if="activeTab === 'papers'"
      id="exam-panel-papers"
      role="tabpanel"
      aria-labelledby="exam-tab-papers"
      class="tab-card-stack"
    >
      <section v-if="!selectedDetail" class="card" aria-label="私有原卷与答题卡">
        <div class="card-head">
          <h3>原卷与答题卡</h3>
        </div>
        <p class="muted">当前尚未选定学校考试，请先前往「总分台账与核对」选定场次或「+ 新建校考档案」建档。</p>
      </section>
      <template v-else>
        <section class="card" aria-label="上传私有原卷与答题卡">
          <div class="card-head">
            <div>
              <h3>上传私有原卷与答题卡</h3>
              <p class="card-sub">支持 PDF / DOCX / PNG / JPG（单份不超过 35 MiB）</p>
            </div>
            <span class="chip mid">私有加密隔离 · 不入公共题库</span>
          </div>
          <label for="school-paper-input">
            选择试卷或答题卡文件（PDF / DOCX / PNG / JPG，不超过 35 MiB）
          </label>
          <input
            id="school-paper-input"
            ref="paperInputRef"
            type="file"
            accept=".pdf,.docx,.png,.jpg,.jpeg,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/png,image/jpeg"
            @change="onPaperFileChange"
            @click="onPaperInputClick"
          />
          <div style="margin-top: 10px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
            <button
              type="button"
              class="primary"
              @click="uploadPaper"
              :disabled="uploadingPaper || !paperFile"
            >
              {{ uploadingPaper ? '上传中…' : '上传原卷 / 答题卡' }}
            </button>
            <span v-if="paperFile" class="chip good">
              已选文件：<b>{{ paperFile.name }}</b>（{{ fmtBytes(paperFile.size) }}）
            </span>
            <button
              v-if="paperFile && !uploadingPaper"
              type="button"
              class="ghost small"
              @click="clearPaperFile"
            >
              清空
            </button>
          </div>
          <p v-if="uploadError" class="form-error">{{ uploadError }}</p>
        </section>

        <section class="card exam-detail" aria-label="已归档原卷与答题卡列表">
          <div class="card-head">
            <div>
              <h3>已归档原卷与答题卡（{{ selectedDetail.attachments.length }}）</h3>
              <p class="card-sub">仅内部私有保管，不提供公开下载入口</p>
            </div>
            <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
              <button
                v-if="parseableAttachments.length > 0"
                type="button"
                class="ghost small"
                @click="activeTab = 'items'"
              >
                前往解析 M2 草稿
              </button>
              <span class="chip good">SHA-256 完整性校验</span>
            </div>
          </div>
          <p v-if="selectedDetail.attachments.length === 0" class="muted">
            还没有挂载原卷或答题卡附件。
          </p>
          <ul v-else class="attachment-list">
            <li v-for="att in selectedDetail.attachments" :key="att.id" class="attachment-row">
              <div class="attachment-main">
                <b>{{ att.filename }}</b>
                <span class="chip good">私有已隔离</span>
                <span class="muted tiny">
                  {{ fmtBytes(att.byte_size) }} · {{ getMediaTypeLabel(att.media_type) }}
                </span>
              </div>
              <div class="attachment-meta">
                文件校验摘要 {{ att.sha256.slice(0, 16) }}… · 归档于 {{ shortTime(att.created_at) }}
              </div>
            </li>
          </ul>
        </section>
      </template>
    </div>

    <!-- Tab 3：逐题得分与考点（明细列表与 OCR 确认卡 + 人工补录小题卡） -->
    <div
      v-else-if="activeTab === 'items'"
      id="exam-panel-items"
      role="tabpanel"
      aria-labelledby="exam-tab-items"
      class="tab-card-stack"
    >
      <section v-if="!selectedDetail" class="card" aria-label="逐题得分与考点明细">
        <div class="card-head">
          <h3>逐题得分与考点明细</h3>
        </div>
        <p class="muted">当前尚未选定学校考试，请先在「总分台账与核对」选定场次。</p>
      </section>
      <template v-else>
        <!-- M2 自动抽取与草稿生成卡 -->
        <section class="card" aria-label="自动解析 M2 草稿">
          <div class="card-head">
            <div>
              <h3>从原卷/答题卡自动解析 M2 草稿</h3>
              <p class="card-sub">
                支持从已归档原卷/答题卡自动抽取题号、分值、候选考点与失分线索（所有结果均以未确认草稿落库）
              </p>
            </div>
            <span class="chip wait">不直接进能力画像</span>
          </div>

          <div v-if="parseableAttachments.length === 0" class="attachment-actions">
            <span class="muted">当前考试尚未归档可解析的原卷或答题卡（PDF / DOCX / PNG / JPG）。</span>
            <button type="button" class="ghost small" @click="activeTab = 'papers'">
              前往「原卷与答题卡」上传
            </button>
          </div>
          <template v-else>
            <span class="field-label">勾选参与本次解析的附件（可多选原卷 + 答题卡联合解析）</span>
            <div class="parse-attach-list">
              <label
                v-for="att in parseableAttachments"
                :key="att.id"
                :class="['parse-attach-chip', selectedParseAttachmentIds.includes(att.id) ? 'selected' : '']"
              >
                <input
                  type="checkbox"
                  :checked="selectedParseAttachmentIds.includes(att.id)"
                  @change="toggleParseAttachment(att.id)"
                />
                <span>{{ att.filename }}</span>
                <small class="muted">({{ getMediaTypeLabel(att.media_type) }})</small>
              </label>
            </div>

            <div class="parse-controls-grid">
              <label>
                解析方式
                <select v-model="parseMode" class="parse-mode-select" aria-label="草稿解析方式">
                  <option value="auto">DeepSeek 多模态联合识别（原卷 + 答题卡，识别错点与候选考点）</option>
                  <option value="skeleton_only">仅本地提取题号与分值骨架（不联网，纯文字卷适用）</option>
                </select>
              </label>
            </div>

            <div v-if="parseMode === 'auto'" class="confirm-box">
              <input id="parse-mask-header" type="checkbox" v-model="maskStudentHeader" />
              <label for="parse-mask-header">
                送检视觉模型前自动遮罩答题卡首页顶部姓名/考场/座位号区域（24% 隐私脱敏）
              </label>
            </div>

            <div class="confirm-box">
              <input id="parse-replace-unconfirmed" type="checkbox" v-model="replaceUnconfirmedDrafts" />
              <label for="parse-replace-unconfirmed">
                重生成时清理本场尚未人工确认的旧草稿（已人工确认题目永久锁定，绝不覆盖）
              </label>
            </div>

            <div class="attachment-actions">
              <button
                type="button"
                class="primary"
                :disabled="parsingDrafts || selectedParseAttachmentIds.length === 0"
                @click="runParseDrafts"
              >
                {{ parsingDrafts ? '解析中…' : '生成待核对草稿' }}
              </button>
              <span v-if="lastParseSummary" class="chip good">{{ lastParseSummary }}</span>
            </div>
            <p v-if="parseDraftError" class="form-error">{{ parseDraftError }}</p>
          </template>
        </section>

        <!-- M2 草稿校对台：未人工确认前严禁进能力画像与错误分析 -->
        <section v-if="unconfirmedDrafts.length > 0" class="card" aria-label="草稿校对台">
          <div class="card-head">
            <div>
              <h3>OCR / 同步草稿校对台（未确认前不进能力画像）</h3>
              <p class="card-sub">
                请核对以下 {{ unconfirmedDrafts.length }} 道草稿的实得分、满分、课标考点与错因，点击「确认入账」或底部批量确认后生效
              </p>
            </div>
            <span class="chip wait">待核对 {{ unconfirmedDrafts.length }} 题</span>
          </div>

          <ul class="draft-card-list">
            <li v-for="it in unconfirmedDrafts" :key="it.id" class="draft-card-item">
              <div class="draft-card-head">
                <b>{{ it.question_label }}</b>
                <span
                  :class="['chip', DRAFT_CONFIDENCE_META[it.draft_confidence ?? '']?.tone ?? 'wait']"
                >
                  {{ DRAFT_CONFIDENCE_META[it.draft_confidence ?? '']?.label ?? '草稿待核对' }}
                </span>
                <span class="chip wait">未确认 · 不进画像</span>
              </div>
              <p v-if="it.draft_reason" class="draft-reason">识别依据：{{ it.draft_reason }}</p>

              <div v-if="it.draft_knowledge_candidates?.length" class="candidate-chip-row">
                <span class="muted tiny">候选考点：</span>
                <button
                  v-for="cand in it.draft_knowledge_candidates"
                  :key="cand.knowledge_id"
                  type="button"
                  :title="cand.reason"
                  :class="[
                    'candidate-chip-btn',
                    draftEdits[it.id]?.knowledgeId === cand.knowledge_id ? 'active' : '',
                  ]"
                  @click="applyCandidateKnowledge(it.id, cand.knowledge_id)"
                >
                  {{ cand.title }} ({{ cand.knowledge_id }})
                </button>
              </div>

              <div v-if="draftEdits[it.id]" class="draft-edit-grid">
                <label>
                  实得分
                  <input
                    type="number"
                    min="0"
                    step="0.5"
                    v-model.number="draftEdits[it.id].earnedPoints"
                    :aria-label="`${it.question_label} 草稿实得分`"
                  />
                </label>
                <label>
                  满分
                  <input
                    type="number"
                    min="0.5"
                    max="100"
                    step="0.5"
                    v-model.number="draftEdits[it.id].maxPoints"
                    :aria-label="`${it.question_label} 草稿满分`"
                  />
                </label>
                <label>
                  知识点编码（{{ resolveDraftKnowledgeHint(it, draftEdits[it.id].knowledgeId) }}）
                  <input
                    v-model="draftEdits[it.id].knowledgeId"
                    class="mono-input"
                    :aria-label="`${it.question_label} 草稿知识点编码`"
                  />
                </label>
                <label>
                  错因分类
                  <select
                    v-model="draftEdits[it.id].errorCategory"
                    :disabled="Number(draftEdits[it.id].earnedPoints) >= Number(draftEdits[it.id].maxPoints)"
                    :aria-label="`${it.question_label} 草稿错因分类`"
                  >
                    <option value="">暂不归类</option>
                    <option
                      v-for="opt in SCHOOL_ERROR_CATEGORY_OPTIONS"
                      :key="opt.value"
                      :value="opt.value"
                    >
                      {{ opt.label }}
                    </option>
                  </select>
                </label>
                <label class="wide-note">
                  错题复盘备注
                  <input
                    v-model="draftEdits[it.id].errorNote"
                    maxlength="500"
                    placeholder="失分题目可填写原因，满分题自动忽略"
                    :aria-label="`${it.question_label} 草稿复盘备注`"
                  />
                </label>
              </div>

              <div class="attachment-actions">
                <button
                  type="button"
                  class="primary small"
                  :disabled="confirmingItemId === it.id || batchConfirming || discardingItemId === it.id"
                  @click="confirmDraftItemWithEdits(it)"
                >
                  {{ confirmingItemId === it.id ? '确认中…' : '确认入账' }}
                </button>
                <button
                  type="button"
                  class="ghost small"
                  :disabled="confirmingItemId === it.id || batchConfirming || discardingItemId === it.id"
                  @click="discardDraftItem(it)"
                >
                  {{ discardingItemId === it.id ? '丢弃中…' : '丢弃草稿' }}
                </button>
              </div>
            </li>
          </ul>

          <div class="draft-card-foot">
            <span class="muted tiny">共 {{ unconfirmedDrafts.length }} 道待核对草稿，批量确认整批校验原子提交</span>
            <button
              type="button"
              class="primary"
              :disabled="batchConfirming || confirmingItemId !== null || discardingItemId !== null"
              @click="confirmAllDraftsBatch"
            >
              {{ batchConfirming ? '批量确认中…' : '批量确认本页已核对草稿' }}
            </button>
          </div>
        </section>

        <section class="card" aria-label="逐题得分与考点明细">
          <div class="card-head">
            <div>
              <h3>已核对逐题得分与考点明细（{{ confirmedItems.length }}）</h3>
              <p class="card-sub">
                {{
                  subject === 'ethics'
                    ? '道法暂未建立公共课标知识图谱，可按自定义主题标注错因与复盘备注（不入四科核心图谱）'
                    : '以下已完成人工确认的逐题明细已纳入学科能力证据与错误分析'
                }}
              </p>
            </div>
            <span class="chip">{{ subject === 'ethics' ? '道法 · 校考复盘档案' : '细粒度证据' }}</span>
          </div>
          <p v-if="confirmedItems.length === 0" class="muted">
            {{
              unconfirmedDrafts.length > 0
                ? '当前题目均在上方草稿校对台等待人工确认；确认后将在此显示并生成分析结果。'
                : '还没有录入已确认的逐题得分明细。'
            }}
          </p>
          <ul v-else class="attachment-list">
            <li v-for="it in confirmedItems" :key="it.id" class="attachment-row">
              <div class="attachment-main">
                <b>{{ it.question_label }}</b>
                <span>{{ displayKnowledgeName(it) }}</span>
                <span><b>{{ fmtPoints(it.earned_points) }} / {{ fmtPoints(it.max_points) }}</b></span>
                <span v-if="it.earned_points < it.max_points" class="chip bad">
                  失 -{{ fmtPoints(it.max_points - it.earned_points) }} 分
                </span>
                <span
                  v-if="it.earned_points < it.max_points"
                  :class="['chip', it.error_category ? 'mid' : 'wait']"
                >
                  {{ getSchoolErrorCategoryLabel(it.error_category) }}
                </span>
                <span class="chip good">已确认</span>
              </div>
              <p v-if="it.error_note" class="item-error-note">
                复盘备注：{{ it.error_note }}
              </p>
              <div class="attachment-actions" style="display: flex; gap: 8px; flex-wrap: wrap;">
                <button
                  v-if="it.earned_points < it.max_points"
                  type="button"
                  class="ghost small"
                  @click="editingAnalysisItemId === it.id ? cancelEditAnalysis() : startEditAnalysis(it)"
                >
                  {{ editingAnalysisItemId === it.id ? '收起复盘编辑' : '标注/修改错因' }}
                </button>
              </div>
              <div v-if="editingAnalysisItemId === it.id" class="inline-analysis-editor">
                <div class="admin-grid">
                  <label>
                    错因分类
                    <select
                      v-model="editErrorCategory"
                      :aria-label="`${it.question_label} 错因分类`"
                    >
                      <option value="">未归类错因</option>
                      <option
                        v-for="opt in SCHOOL_ERROR_CATEGORY_OPTIONS"
                        :key="opt.value"
                        :value="opt.value"
                      >
                        {{ opt.label }}
                      </option>
                    </select>
                  </label>
                  <label>
                    错题复盘备注
                    <input
                      v-model="editErrorNote"
                      :aria-label="`${it.question_label} 错题复盘备注`"
                      maxlength="500"
                      placeholder="记录失分原因与改进要点"
                    />
                  </label>
                </div>
                <div style="display: flex; gap: 8px; margin-top: 8px;">
                  <button
                    type="button"
                    class="primary small"
                    :disabled="savingAnalysis"
                    @click="saveItemAnalysis(it)"
                  >
                    {{ savingAnalysis ? '保存中…' : '保存复盘' }}
                  </button>
                  <button type="button" class="ghost small" @click="cancelEditAnalysis">
                    取消
                  </button>
                </div>
              </div>
            </li>
          </ul>
        </section>

        <section class="card" aria-label="人工补录已核对小题">
          <div class="card-head">
            <div>
              <h3>人工补录已核对小题</h3>
              <p class="card-sub">对照纸质阅卷结果逐题补充；若该题未拿满分，可同步标注错因分类与复盘备注</p>
            </div>
            <button
              v-if="subject === 'ethics'"
              type="button"
              class="ghost small"
              @click="itemKnowledgeId = '道法综合主题'"
            >
              填入默认主题
            </button>
          </div>
          <div class="admin-grid">
            <label>
              题号（如 第1题）
              <input v-model="itemLabel" placeholder="第1题" />
            </label>
            <label>
              知识点编码
              <input
                v-model="itemKnowledgeId"
                class="mono-input"
                :placeholder="subject === 'ethics' ? '如：法治与责任（支持直接填主题）' : '如 math.eq.quadratic'"
              />
            </label>
            <label>
              小题得分
              <input type="number" min="0" step="0.5" v-model.number="itemEarned" />
            </label>
            <label>
              小题满分
              <input type="number" min="0.5" max="100" step="0.5" v-model.number="itemMax" />
            </label>
            <template v-if="isNewItemLost">
              <label>
                错因分类（失分题选填）
                <select v-model="itemErrorCategory">
                  <option value="">暂不归类</option>
                  <option
                    v-for="opt in SCHOOL_ERROR_CATEGORY_OPTIONS"
                    :key="opt.value"
                    :value="opt.value"
                  >
                    {{ opt.label }}
                  </option>
                </select>
              </label>
              <label>
                错题复盘备注
                <input
                  v-model="itemErrorNote"
                  maxlength="500"
                  placeholder="如：漏看条件 / 判别式未讨论 / 材料要点缺失"
                />
              </label>
            </template>
          </div>
          <button type="button" class="primary" @click="addItem" :disabled="savingItem">
            {{ savingItem ? '录入中…' : '录入已核对小题' }}
          </button>
        </section>
      </template>
    </div>

    <!-- Tab 4：错误分析与复盘（数据不足诚实提示 + 本场错因分布 + 考点交叉诊断 + 同科历次顽固失分对比） -->
    <div
      v-else-if="activeTab === 'analysis'"
      id="exam-panel-analysis"
      role="tabpanel"
      aria-labelledby="exam-tab-analysis"
      class="tab-card-stack"
    >
      <section v-if="!selectedDetail || !errorAnalysis" class="card" aria-label="错误分析与复盘">
        <div class="card-head">
          <h3>错误分析与复盘</h3>
        </div>
        <p class="muted">
          {{ loadingDetail ? '正在加载错误分析数据…' : '当前尚未选定学校考试，请先在「总分台账与核对」选定场次或「+ 新建校考档案」建档。' }}
        </p>
      </section>
      <template v-else>
        <!-- 数据不足或尚无失分时的诚实引导卡 -->
        <section
          v-if="errorAnalysis.status !== 'analyzed'"
          class="card"
          aria-label="错误分析数据状态说明"
        >
          <div class="card-head">
            <div>
              <h3>本场错误分析 · {{ errorAnalysis.title }}</h3>
              <p class="card-sub">严格遵守诚实诊断口径，绝不从试卷总分反推考点得分</p>
            </div>
            <span class="chip wait">
              {{ errorAnalysis.status === 'insufficient_items' ? '待补充逐题失分明细' : '暂无失分记录' }}
            </span>
          </div>
          <div class="analysis-callout">
            <b>{{ errorAnalysis.diagnosis_summary }}</b>
          </div>
          <div class="exam-kpi-row">
            <div class="kpi-tile">
              <b>
                {{
                  errorAnalysis.confirmed_by_user
                    ? `${fmtPoints(errorAnalysis.overview.earned_points)} / ${fmtPoints(errorAnalysis.overview.max_points)}`
                    : '待确认'
                }}
              </b>
              <span>卷面总分</span>
            </div>
            <div class="kpi-tile">
              <b>{{ errorAnalysis.overview.confirmed_item_count }} 题</b>
              <span>已核对小题明细</span>
            </div>
            <div class="kpi-tile wait">
              <b>{{ errorAnalysis.overview.unconfirmed_draft_count }} 题</b>
              <span>待人工确认 OCR 草稿</span>
            </div>
          </div>
          <div style="display: flex; gap: 10px; flex-wrap: wrap; align-items: center;">
            <button type="button" class="primary" @click="activeTab = 'items'">
              前往补录失分小题
            </button>
            <button type="button" class="ghost small" @click="activeTab = 'papers'">
              查看原卷与答题卡
            </button>
          </div>
        </section>

        <!-- 已有失分明细时的分析三卡片 -->
        <template v-else>
          <!-- 卡片 1：本场失分概览与错因分布 -->
          <section class="card" aria-label="本场失分概览与错因分布">
            <div class="card-head">
              <div>
                <h3>本场失分概览与错因分布</h3>
                <p class="card-sub">仅汇总已人工核对的逐题失分；未单独归类的失分小题保持如实标示</p>
              </div>
              <span class="chip mid">
                已归因 {{ errorAnalysis.overview.lost_item_count }} 题 · -{{ fmtPoints(errorAnalysis.overview.itemized_lost_points) }} 分
              </span>
            </div>
            <div class="analysis-callout">
              <b>{{ errorAnalysis.diagnosis_summary }}</b>
              <div
                v-if="errorAnalysis.overview.unconfirmed_draft_count > 0"
                style="margin-top: 6px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;"
              >
                <span class="muted tiny">
                  另有 {{ errorAnalysis.overview.unconfirmed_draft_count }} 道 OCR 草稿小题待核对，确认后自动纳入统计。
                </span>
                <button type="button" class="ghost small" @click="activeTab = 'items'">
                  去核对草稿
                </button>
              </div>
            </div>

            <div class="exam-analysis-kpis">
              <div class="kpi-tile bad">
                <b>{{ errorAnalysis.overview.lost_item_count }} / {{ errorAnalysis.overview.confirmed_item_count }} 题</b>
                <span>已核对失分题 / 总核对题</span>
              </div>
              <div class="kpi-tile">
                <b>
                  -{{ fmtPoints(errorAnalysis.overview.itemized_lost_points) }}
                  <template v-if="errorAnalysis.overview.paper_lost_points !== null">
                    / -{{ fmtPoints(errorAnalysis.overview.paper_lost_points) }}
                  </template>
                  分
                </b>
                <span>
                  {{
                    errorAnalysis.overview.paper_lost_points !== null
                      ? '已归因失分 / 卷面总失分'
                      : '已归因失分（卷面总分待核对）'
                  }}
                </span>
              </div>
              <div class="kpi-tile wait">
                <b>
                  {{
                    errorAnalysis.overview.primary_error_category
                      ? getSchoolErrorCategoryLabel(errorAnalysis.overview.primary_error_category)
                      : '待标注'
                  }}
                </b>
                <span>首要错因类型</span>
              </div>
              <div class="kpi-tile">
                <b>{{ errorAnalysis.overview.primary_knowledge_name || '—' }}</b>
                <span>首要失分考点</span>
              </div>
            </div>

            <h4 class="sub-head" style="margin: 12px 0 8px;">各错因类型失分占比</h4>
            <ul class="error-cat-list">
              <li v-for="cat in errorAnalysis.by_category" :key="cat.category" class="error-cat-row">
                <div class="error-cat-head">
                  <b>{{ getSchoolErrorCategoryLabel(cat.category) }}</b>
                  <span>
                    <b>-{{ fmtPoints(cat.lost_points) }} 分</b>
                    （占 {{ fmtPct(cat.share_of_itemized_loss) }} · {{ cat.item_count }} 题）
                  </span>
                </div>
                <div class="error-bar-track" aria-hidden="true">
                  <div
                    class="error-bar-fill"
                    :style="{ width: `${Math.max(4, Math.round(cat.share_of_itemized_loss * 100))}%` }"
                  />
                </div>
                <div class="muted tiny">
                  涉及题号：{{ cat.question_labels.join('、') }}
                  <button
                    v-if="cat.category === 'uncategorized'"
                    type="button"
                    class="link-btn"
                    @click="activeTab = 'items'"
                  >
                    前往补充错因标注
                  </button>
                </div>
              </li>
            </ul>
          </section>

          <!-- 卡片 2：本场失分考点排行与平时掌握度交叉诊断 -->
          <section class="card" aria-label="本场失分考点排行与交叉诊断">
            <div class="card-head">
              <div>
                <h3>本场失分考点排行与交叉诊断</h3>
                <p class="card-sub">
                  {{
                    errorAnalysis.has_taxonomy
                      ? '将本次校考失分与日常练习/阶段诊断的独立首次作答表现交叉对照'
                      : '道法科目未建公共知识图谱，按录入手工主题归集复盘与失分占比'
                  }}
                </p>
              </div>
              <span class="chip">
                {{ errorAnalysis.has_taxonomy ? '校考失分 × 平时掌握对照' : '主题失分排行' }}
              </span>
            </div>
            <ul class="attachment-list">
              <li v-for="kn in errorAnalysis.by_knowledge" :key="kn.knowledge_id" class="attachment-row">
                <div class="attachment-main">
                  <b>{{ kn.knowledge_name }}</b>
                  <span class="chip bad">失 -{{ fmtPoints(kn.lost_points) }} 分</span>
                  <span class="chip subtle">占已归因 {{ fmtPct(kn.share_of_itemized_loss) }}</span>
                  <span
                    :class="['chip', DIAGNOSIS_TAG_META[kn.diagnosis_tag]?.tone || 'mid']"
                  >
                    {{ DIAGNOSIS_TAG_META[kn.diagnosis_tag]?.label || kn.diagnosis_tag }}
                  </span>
                </div>
                <div class="attachment-meta">
                  本场得分率 {{ fmtPct(kn.exam_observed_rate) }}（涉及 {{ kn.question_labels.join('、') }}）
                  <template v-if="errorAnalysis.has_taxonomy">
                    · 平时作答：{{ PRACTICE_STATUS_TEXT[kn.practice_status] || kn.practice_status }}
                    <template v-if="kn.practice_observed_rate !== null">
                      （{{ fmtPct(kn.practice_observed_rate) }} / {{ kn.practice_sample_size }} 题）
                    </template>
                  </template>
                  <template v-if="kn.categories.length > 0">
                    · 错因：{{ kn.categories.map(c => getSchoolErrorCategoryLabel(c)).join('、') }}
                  </template>
                </div>
                <p
                  v-for="(noteItem, idx) in kn.notes"
                  :key="`${kn.knowledge_id}-${idx}`"
                  class="item-error-note"
                >
                  {{ noteItem.question_label }} 复盘：{{ noteItem.note }}
                </p>
              </li>
            </ul>

            <h4 class="sub-head" style="margin: 14px 0 8px;">失分小题明细速览（点击可回「逐题得分」修改复盘）</h4>
            <ul class="attachment-list">
              <li v-for="li in errorAnalysis.lost_items" :key="li.id" class="attachment-row">
                <div class="attachment-main">
                  <b>{{ li.question_label }}</b>
                  <span>{{ li.knowledge_name }}</span>
                  <span class="chip bad">-{{ fmtPoints(li.lost_points) }} 分</span>
                  <span :class="['chip', li.error_category ? 'mid' : 'wait']">
                    {{ getSchoolErrorCategoryLabel(li.error_category) }}
                  </span>
                  <button
                    type="button"
                    class="ghost small"
                    style="margin-left: auto;"
                    @click="jumpToEditItem(li.id)"
                  >
                    补充/修改错因
                  </button>
                </div>
                <p v-if="li.error_note" class="item-error-note">
                  复盘备注：{{ li.error_note }}
                </p>
              </li>
            </ul>
          </section>
        </template>

        <!-- 卡片 3：同科历次校考顽固失分点对比（只要有同科跨场重复失分即呈现） -->
        <section class="card" aria-label="同科历次校考顽固失分点对比">
          <div class="card-head">
            <div>
              <h3>同科历次校考顽固失分点对比</h3>
              <p class="card-sub">
                自动统计「{{ SCHOOL_SUBJECT_LABELS[subject] }}」跨 ≥ 2 场已核对校考重复扣分的知识点
              </p>
            </div>
            <span class="chip">
              已统计 {{ errorAnalysis.history_summary.same_subject_exams_with_items }} / {{ errorAnalysis.history_summary.same_subject_exam_count }} 场含明细校考
            </span>
          </div>
          <p v-if="errorAnalysis.recurring_knowledge.length === 0" class="muted">
            当前「{{ SCHOOL_SUBJECT_LABELS[subject] }}」暂无跨 2 场以上重复失分的考点；连续多次月考或期中/期末录入逐题明细后，系统将自动识别顽固薄弱环节。
          </p>
          <ul v-else class="attachment-list">
            <li
              v-for="rk in errorAnalysis.recurring_knowledge"
              :key="rk.knowledge_id"
              class="attachment-row"
            >
              <div class="attachment-main">
                <b>{{ rk.knowledge_name }}</b>
                <span v-if="rk.repeat_in_current_exam" class="chip bad">本场再次失分</span>
                <span class="chip wait">跨 {{ rk.exam_count }} 场共 {{ rk.total_item_count }} 题</span>
                <span class="chip bad">累计失 -{{ fmtPoints(rk.total_lost_points) }} 分</span>
              </div>
              <div class="attachment-meta">
                涉及场次：
                {{
                  rk.exams
                    .map(ex => `${ex.exam_date} ${ex.title}（-${fmtPoints(ex.lost_points)} 分 / ${ex.item_count} 题）`)
                    .join('；')
                }}
              </div>
            </li>
          </ul>
          <p class="muted tiny disclaimer" style="margin-bottom: 0;">
            {{ errorAnalysis.disclaimer }}
          </p>
        </section>
      </template>
    </div>

    <!-- Tab 4：+ 新建校考档案（专注建档卡片，提交后自动跳回「总分台账与核对」并选中） -->
    <div
      v-else
      id="exam-panel-create"
      role="tabpanel"
      aria-labelledby="exam-tab-create"
      class="tab-card-stack"
    >
      <section class="card" aria-label="新建学校考试档案">
        <div class="card-head">
          <div>
            <h3>新建 / 暂存校考档案 · {{ SCHOOL_SUBJECT_LABELS[subject] }}</h3>
            <p class="card-sub">可先只暂存档案与上传原卷，成绩公布后再回「总分台账与核对」补充锁定总分</p>
          </div>
          <span class="chip mid">建档与总分登记</span>
        </div>
        <div class="exam-create-grid">
          <label class="wide">
            考试名称
            <input v-model="examTitle" placeholder="如：九年级十月统一练习" />
          </label>
          <label>
            考试日期
            <input type="date" v-model="examDate" />
          </label>
          <label>
            获得分数
            <input
              type="number"
              :min="0"
              step="0.5"
              v-model.number="examEarned"
              :placeholder="createConfirmed ? '' : '暂存可留空（默认 0）'"
            />
          </label>
          <label>
            考试满分
            <input type="number" :min="1" step="0.5" v-model.number="examMax" />
          </label>
        </div>
        <div class="confirm-box">
          <input id="exam-create-confirmed" type="checkbox" v-model="createConfirmed" />
          <label for="exam-create-confirmed">
            我已人工核对总分（若仅先归档空白原卷与答题卡、稍后补分，可取消勾选）
          </label>
        </div>
        <button type="button" class="primary" @click="saveExam" :disabled="savingExam">
          {{ savingExam ? '保存中…' : (createConfirmed ? '记录已核对总分' : '暂存待核对档案') }}
        </button>
      </section>
    </div>
  </section>
</template>
