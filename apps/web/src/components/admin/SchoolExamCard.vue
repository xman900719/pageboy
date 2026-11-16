<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  describeError,
  SCHOOL_SUBJECT_LABELS,
  type ApiClient,
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
  getSubjectKnowledgeOptions,
  resolveKnowledgeCodeInput,
  SCHOOL_ERROR_CATEGORY_OPTIONS,
} from '../../config/knowledge'
import HelpBubble from '../HelpBubble.vue'
import SchoolExamReportCenter from './SchoolExamReportCenter.vue'
import SchoolExamSyncCenter from './SchoolExamSyncCenter.vue'
import type { NoticeTone } from '../Notice.vue'

type Notify = (text: string, tone?: NoticeTone) => void
export type ExamTabId = 'scores' | 'papers' | 'items' | 'analysis' | 'sync' | 'report'

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
  auto_matched: { label: '系统自动匹配 · 待确认', tone: 'mid' },
  ai_matched: { label: 'DeepSeek 匹配 · 待确认', tone: 'mid' },
}

function fmtExamMonth(value?: string | null): string {
  const text = String(value || '').trim()
  return /^\d{4}-\d{2}/.test(text) ? text.slice(0, 7) : (text || '未填')
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

const props = defineProps<{
  client: ApiClient
  subject: SchoolSubject
  notify: Notify
  initialExamId?: string
  initialTab?: ExamTabId
}>()

const emit = defineEmits<{
  (e: 'select-subject', subject: SchoolSubject, examId?: string, tab?: 'scores' | 'papers' | 'items'): void
}>()

const exams = ref<SchoolExam[] | null>(null)
const selectedExamId = ref<string | null>(null)
const confirmDeleteExamId = ref<string | null>(null)
const deletingExamId = ref<string | null>(null)
const selectedDetail = ref<SchoolExamDetail | null>(null)
const errorAnalysis = ref<SchoolExamErrorAnalysis | null>(null)
const loadingDetail = ref(false)
const activeTab = ref<ExamTabId>(props.initialTab ?? 'scores')

// 学科可选中文知识点列表（供手动补录与草稿校对输入提示）
const subjectKnowledgeOptions = computed(() => getSubjectKnowledgeOptions(props.subject, false))

// 新建校考表单状态
const examTitle = ref('')
const examDate = ref(new Date().toISOString().slice(0, 7))
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
const answerCardAttachments = computed(
  () => parseableAttachments.value.filter(a => /答题卡|答题纸|answer.?card/i.test(a.filename)),
)
const hasAnswerCard = computed(() => answerCardAttachments.value.length > 0)
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

// 五类内容矩阵协同子 Tab 定义及实时状态徽章
const categoryTabs = computed(() => {
  const listCount = exams.value?.length ?? 0
  const ex = selectedDetail.value ?? selectedExamSummary.value
  const scoreBadge = ex ? (ex.confirmed_by_user ? '已核对' : '待补总分') : `${listCount} 场`
  const draftCount = unconfirmedDrafts.value.length
  const paperDraftBadge = draftCount > 0
    ? `${draftCount} 待核对`
    : selectedDetail.value
      ? `${selectedDetail.value.attachments.length} 份`
      : '原卷'
  const confirmedBadge = selectedDetail.value ? `${confirmedItems.value.length} 条` : '明细'
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
  const syncBadge = '四步'

  return [
    {
      id: 'scores' as const,
      title: '总分台账与建档',
      badge: scoreBadge,
      wait: Boolean(ex && !ex.confirmed_by_user),
    },
    {
      id: 'papers' as const,
      title: '原卷与草稿校对',
      badge: paperDraftBadge,
      wait: draftCount > 0,
    },
    {
      id: 'items' as const,
      title: '已核对明细与补录',
      badge: confirmedBadge,
      wait: false,
    },
    {
      id: 'analysis' as const,
      title: '错误分析与复盘',
      badge: analysisBadge,
      wait: analysisWait,
    },
    {
      id: 'sync' as const,
      title: '全科校考同步',
      badge: syncBadge,
      wait: false,
    },
    {
      id: 'report' as const,
      title: '报告导入与核对',
      badge: '四步',
      wait: false,
    },
  ]
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
    const label = getKnowledgeLabel(it.knowledge_id)
    const displayKnowledge =
      label !== it.knowledge_id ? label : (it.knowledge_name || it.knowledge_id)
    nextEdits[it.id] = draftEdits.value[it.id] ?? {
      earnedPoints: it.earned_points,
      maxPoints: it.max_points,
      knowledgeId: displayKnowledge,
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
    paperFile.value = null
    uploadError.value = ''
    editingAnalysisItemId.value = null
    lastParseInitExamId.value = null
    selectedParseAttachmentIds.value = []
    parseDraftError.value = ''
    lastParseSummary.value = ''
    draftEdits.value = {}
    confirmDeleteExamId.value = null
    void refreshExams(props.initialExamId)
  },
  { immediate: true }
)

async function selectExam(examId: string) {
  selectedExamId.value = examId
  uploadError.value = ''
  editingAnalysisItemId.value = null
  confirmDeleteExamId.value = null
  await loadDetail(examId)
}

async function deleteExam(examId: string) {
  deletingExamId.value = examId
  try {
    const result = await props.client.deleteSchoolExam(examId)
    confirmDeleteExamId.value = null
    if (selectedExamId.value === examId) selectedExamId.value = null
    await refreshExams()
    props.notify(
      `已删除该场校考（逐题 ${result.items_deleted}、附件 ${result.attachments_deleted}、排名 ${result.rank_snapshots_deleted}）。`,
      'success',
    )
  } catch (error) {
    props.notify(describeError(error), 'error')
  } finally {
    deletingExamId.value = null
  }
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
  const kid = resolveKnowledgeCodeInput(itemKnowledgeId.value, props.subject)
  if (label === '' || kid === '' || itemEarned.value === '' || itemMax.value === '') {
    props.notify('请完整填写题号、所属知识点、小题得分与满分。', 'caution')
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
  const local = getKnowledgeLabel(trimmed)
  const label =
    cand?.title ||
    (local !== trimmed ? local : null) ||
    (trimmed === it.knowledge_id && it.knowledge_name && it.knowledge_name !== trimmed ? it.knowledge_name : null) ||
    trimmed
  return it.draft_confidence === 'auto_matched' ? `系统自动匹配：${label}（待确认）` : label
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
      ? `智能多模态识别（送检 ${res.meta.pages_sent ?? 0} 页，脱敏 ${res.meta.masked_pages ?? 0} 页）`
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

function resolveDraftKnowledgeCode(it: SchoolExamItem, rawInput: string): string {
  const trimmed = rawInput.trim()
  if (!trimmed) return ''
  const matchedCand = it.draft_knowledge_candidates?.find(
    c => c.knowledge_id === trimmed || c.title === trimmed
  )
  if (matchedCand) return matchedCand.knowledge_id
  return resolveKnowledgeCodeInput(trimmed, props.subject)
}

function applyCandidateKnowledge(itemId: string, knowledgeId: string, title?: string) {
  const edit = draftEdits.value[itemId]
  if (edit) {
    const label = getKnowledgeLabel(knowledgeId)
    edit.knowledgeId = label !== knowledgeId ? label : (title || knowledgeId)
  }
}

function buildDraftConfirmEntry(it: SchoolExamItem) {
  const edit = draftEdits.value[it.id]
  const earnedNum = Number(edit ? edit.earnedPoints : it.earned_points)
  const maxNum = Number(edit ? edit.maxPoints : it.max_points)
  const rawKnowledge = edit ? edit.knowledgeId : it.knowledge_id
  const kid = resolveDraftKnowledgeCode(it, rawKnowledge)
  if (Number.isNaN(earnedNum) || Number.isNaN(maxNum) || maxNum <= 0 || maxNum > 100 || earnedNum < 0) {
    return { error: `「${it.question_label}」分值须在 0 到满分（≤100）之间。` }
  }
  if (earnedNum > maxNum) {
    return { error: `「${it.question_label}」实得分（${earnedNum}）不能大于满分（${maxNum}）。` }
  }
  if (!kid || kid === 'unmapped') {
    return { error: `「${it.question_label}」所属知识点不能为空或 unmapped。` }
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

async function openExamFromSync(examId: string, tab: 'scores' | 'papers' | 'items' | 'analysis') {
  if (examId) {
    await selectExam(examId)
  }
  activeTab.value = tab
}

async function handleSyncPapersImported(examId: string) {
  await refreshExams(examId || undefined)
}
</script>

<template>
  <section class="exam-workspace admin-workspace" aria-label="学校考试总分">
    <!-- 二级工作区子 Tab 条（方案二：矩阵协同） -->
    <div class="admin-subtab-strip">
      <div class="admin-subtab-list" role="tablist" aria-label="学校考试工作区">
        <button
          v-for="tab in categoryTabs"
          :key="tab.id"
          :id="`exam-tab-${tab.id}`"
          type="button"
          role="tab"
          :aria-selected="activeTab === tab.id"
          :aria-controls="`exam-panel-${tab.id}`"
          :class="['admin-subtab', activeTab === tab.id ? 'active' : '']"
          @click="activeTab = tab.id"
        >
          <span>{{ tab.title }}</span>
          <span :class="['admin-subtab-badge', tab.wait ? 'wait' : '']">{{ tab.badge }}</span>
        </button>
      </div>

      <div class="admin-subtab-tools">
        <span class="chip">{{ SCHOOL_SUBJECT_LABELS[subject] }} · {{ exams?.length ?? 0 }} 场</span>
        <HelpBubble title="校考录入说明" label="校考录入说明">
          <ul>
            <li>
              <strong>总分口径：</strong>由家长或管理员依据纸质答卷如实录入；<b>{{ EXAM_NOTE }}</b>
            </li>
            <li>
              <strong>先归档后补分：</strong>若仅先留存空白原卷与学生答题卡，可取消勾选人工核对；成绩公布后再补充实得总分并确认锁定。
            </li>
            <li>
              <strong>隐私与题库隔离：</strong>私人校卷原卷与学生答题卡仅在私有存储加密隔离保存，不提供公开下载入口，绝不进入公开题库或学生练习流。
            </li>
          </ul>
        </HelpBubble>
        <button type="button" class="ghost small" @click="refreshExams()">
          刷新
        </button>
      </div>
    </div>

    <!-- 在原卷/已核对/错误分析子 Tab 下展示当前处理场次快速切换条 -->
    <div
      v-if="(activeTab === 'papers' || activeTab === 'items' || activeTab === 'analysis') && exams && exams.length > 0 && selectedDetail"
      class="matrix-context-bar"
    >
      <div class="matrix-context-main">
        <span class="eyebrow">当前场次</span>
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
          {{ fmtExamMonth(ex.exam_date) }} ({{ fmtPoints(ex.earned_points) }}/{{ fmtPoints(ex.max_points) }})
        </button>
      </div>
    </div>

    <!-- 全局复用：当前学科知识点中文补全列表（供草稿校对与手工补录共用） -->
    <datalist :id="`school-exam-knowledge-list-${subject}`">
      <option v-for="opt in subjectKnowledgeOptions" :key="opt.code" :value="opt.label" />
    </datalist>

    <!-- 子 Tab 1：总分台账与建档（3 列矩阵：已录校考台账 | 总分概览与锁定 | 新建校考档案） -->
    <div
      v-if="activeTab === 'scores'"
      id="exam-panel-scores"
      role="tabpanel"
      aria-labelledby="exam-tab-scores"
      class="matrix-3col"
    >
      <section class="card" aria-label="已录校考台账">
        <div class="card-head">
          <div>
            <h3>已录校考台账 · {{ SCHOOL_SUBJECT_LABELS[subject] }}</h3>
            <p class="card-sub">点击场次即可在中间栏查看总分或补充核对</p>
          </div>
          <span class="chip">{{ exams?.length ?? 0 }} 场</span>
        </div>
        <p v-if="exams === null" class="muted">已录入考试加载中…</p>
        <p v-else-if="exams.length === 0" class="muted">
          当前科目还没有录入过学校考试记录，可直接在右侧栏登记首场校考档案。
        </p>
        <ul v-else class="exam-list" tabindex="0" aria-label="已录校考场次列表">
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
                {{ fmtExamMonth(exam.exam_date) }} · <b>{{ fmtPoints(exam.earned_points) }} / {{ fmtPoints(exam.max_points) }}</b>
              </span>
            </button>
            <span :class="['chip', exam.confirmed_by_user ? 'good' : 'wait']">
              {{ exam.confirmed_by_user ? '已核对' : '未核对' }}
            </span>
            <div class="exam-delete">
              <template v-if="confirmDeleteExamId === exam.id">
                <span class="muted tiny">删除本场？</span>
                <button
                  type="button"
                  class="ghost small"
                  :disabled="deletingExamId === exam.id"
                  :aria-label="`确认删除 ${exam.title}`"
                  @click.stop="deleteExam(exam.id)"
                >
                  {{ deletingExamId === exam.id ? '删除中…' : '确认删除' }}
                </button>
                <button type="button" class="ghost small" @click.stop="confirmDeleteExamId = null">取消</button>
              </template>
              <button
                v-else
                type="button"
                class="ghost small"
                :aria-label="`删除 ${exam.title}`"
                title="删除本场校考，同时删除逐题得分、原卷附件与排名快照，不可撤销"
                @click.stop="confirmDeleteExamId = exam.id"
              >
                删除
              </button>
            </div>
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
              <b>{{ fmtExamMonth(selectedDetail.exam_date) }}</b>
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
            该场次总分已完成人工核对并锁定；如需挂载原卷或校对草稿，可切换至「原卷与草稿校对」。
          </p>
          <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px;">
            <button type="button" class="ghost small" @click="activeTab = 'papers'">
              前往原卷与草稿校对
            </button>
            <button type="button" class="ghost small" @click="activeTab = 'analysis'">
              查看错误分析
            </button>
          </div>
        </template>
        <template v-else>
          <div class="card-head">
            <h3>总分概览与核对锁定</h3>
          </div>
          <p class="muted">请先在左侧选择一场学校考试，或在右侧直接新建校考档案。</p>
        </template>
      </section>

      <section class="card" aria-label="新建学校考试档案">
        <div class="card-head">
          <div>
            <h3>新建 / 暂存校考档案 · {{ SCHOOL_SUBJECT_LABELS[subject] }}</h3>
            <p class="card-sub">可先只暂存档案，成绩公布后再补锁总分</p>
          </div>
          <HelpBubble compact title="校考建档口径" label="建档说明">
            <p>{{ EXAM_NOTE }} 若暂未出分，可取消勾选人工核对先建档上传原卷。</p>
          </HelpBubble>
        </div>
        <div class="exam-create-grid">
          <label class="wide">
            考试名称
            <input v-model="examTitle" placeholder="如：九年级十月统一练习" />
          </label>
          <label>
            考试日期
            <input type="month" v-model="examDate" />
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

    <!-- 子 Tab 2：原卷与草稿校对（4:6 矩阵：左栏上传与自动解析触发 | 右栏待核对草稿校对台） -->
    <div
      v-else-if="activeTab === 'papers'"
      id="exam-panel-papers"
      role="tabpanel"
      aria-labelledby="exam-tab-papers"
    >
      <section v-if="!selectedDetail" class="card" aria-label="私有原卷与答题卡">
        <div class="card-head">
          <h3>原卷与草稿校对</h3>
        </div>
        <p class="muted">当前尚未选定学校考试，请先前往「总分台账与建档」选定或新建场次。</p>
      </section>
      <div v-else class="matrix-4-6">
        <!-- 左栏：私有原卷上传 + 附件清单 + 自动解析控制 -->
        <div class="matrix-col-stack">
          <section class="card" aria-label="上传私有原卷与答题卡">
            <div class="card-head">
              <div>
                <h3>上传私有原卷与答题卡</h3>
                <p class="card-sub">支持文档与清晰图片格式（单份不超过 35 MiB）</p>
              </div>
              <HelpBubble compact title="原卷加密与隐私隔离" label="隔离说明">
                <p>私人校卷与答题卡仅加密保存在私有存储空间，不提供公开下载入口，绝不进入公共题库。</p>
              </HelpBubble>
            </div>
            <label for="school-paper-input">
              选择试卷或答题卡文件（不超过 35 MiB）
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

            <div class="exam-detail" style="margin-top: 14px; padding-top: 12px; border-top: 1px dashed var(--line);" aria-label="已归档原卷与答题卡列表">
              <div class="card-head">
                <span class="field-label" style="margin: 0;">已归档原卷与答题卡（{{ selectedDetail.attachments.length }}）</span>
                <span class="chip good">原件校验已隔离</span>
              </div>
              <p v-if="selectedDetail.attachments.length === 0" class="muted tiny" style="margin-top: 6px;">
                还没有挂载原卷或答题卡附件。
              </p>
              <ul v-else class="attachment-list" tabindex="0" aria-label="已归档原卷与答题卡列表">
                <li v-for="att in selectedDetail.attachments" :key="att.id" class="attachment-row">
                  <div class="attachment-main">
                    <b>{{ att.filename }}</b>
                    <span class="chip good">私有已隔离</span>
                    <span class="muted tiny">
                      {{ fmtBytes(att.byte_size) }} · {{ getMediaTypeLabel(att.media_type) }}
                    </span>
                  </div>
                  <div class="attachment-meta" :title="`校验摘要：${att.sha256}`">
                    已完成完整性校验 · 归档于 {{ shortTime(att.created_at) }}
                  </div>
                </li>
              </ul>
            </div>
          </section>

          <section class="card" aria-label="自动解析待核对草稿">
            <div class="card-head">
              <div>
                <h3>从原卷/答题卡自动解析草稿</h3>
                <p class="card-sub">
                  抽取题号、分值、候选考点与失分线索，所有结果均为待核对草稿
                </p>
              </div>
              <span class="chip wait">未确认不进画像</span>
            </div>

            <div v-if="parseableAttachments.length === 0" class="attachment-actions">
              <span class="muted">
                请先在上方上传可解析的原卷文档或答题卡图片；若已有分析报告册，也可直接从报告生成逐题草稿。
              </span>
              <button type="button" class="ghost small" @click="activeTab = 'report'">去“报告导入与核对”生成</button>
            </div>
            <template v-else>
              <span class="field-label">勾选参与本次解析的附件（支持多份联合识别）</span>
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
                    <option value="auto">智能多模态联合识别（原卷 + 答题卡，识别错点与候选考点）</option>
                    <option value="skeleton_only">仅本地提取题号与分值骨架（不联网，纯文字卷适用）</option>
                  </select>
                </label>
              </div>

              <div v-if="parseMode === 'auto'" class="confirm-box">
                <input id="parse-mask-header" type="checkbox" v-model="maskStudentHeader" />
                <label for="parse-mask-header">
                  送检识别模型前自动遮罩答题卡顶部姓名/考场/座位号区域（隐私脱敏保护）
                </label>
              </div>

              <div class="confirm-box">
                <input id="parse-replace-unconfirmed" type="checkbox" v-model="replaceUnconfirmedDrafts" />
                <label for="parse-replace-unconfirmed">
                  重生成时清理本场尚未人工确认的旧草稿（已人工确认题目永久锁定，绝不覆盖）
                </label>
              </div>

              <div class="attachment-actions">
                <p v-if="parseMode === 'auto' && !hasAnswerCard" class="muted tiny">
                  提示：未检测到命名含「答题卡/答题纸」的附件；若仅上传了空白原卷，建议选择「仅本地提取题号与分值骨架」或去「报告导入与核对」生成逐题草稿。
                </p>
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
        </div>

        <!-- 右栏：待核对草稿校对台 -->
        <div class="matrix-col-stack">
          <section class="card" aria-label="草稿校对台">
            <div class="card-head">
              <div>
                <h3>待核对草稿校对台（未确认前不进能力画像）</h3>
                <p class="card-sub">
                  核对实得分、满分、所属知识点与错因分类，点击「确认入账」或批量确认后正式生效
                </p>
              </div>
              <div class="card-head-tools">
                <HelpBubble compact tone="caution" title="草稿核对红线说明" label="校对口径">
                  <p>所有自动识别与同步入库的逐题结果均锁定为「未确认草稿」，绝不直接修改知识点掌握状态或错误分析，须人工逐条核对或批量确认后方能入账。</p>
                </HelpBubble>
                <span v-if="unconfirmedDrafts.length > 0" class="chip wait">待核对 {{ unconfirmedDrafts.length }} 题</span>
              </div>
            </div>

            <template v-if="unconfirmedDrafts.length > 0">
              <ul class="draft-card-list" tabindex="0" aria-label="解析草稿逐题校对列表">
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
                        resolveDraftKnowledgeCode(it, draftEdits[it.id]?.knowledgeId ?? '') === cand.knowledge_id ? 'active' : '',
                      ]"
                      @click="applyCandidateKnowledge(it.id, cand.knowledge_id, cand.title)"
                    >
                      {{ cand.title || getKnowledgeLabel(cand.knowledge_id) }}
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
                      所属知识点（{{ resolveDraftKnowledgeHint(it, draftEdits[it.id].knowledgeId) }}）
                      <input
                        v-model="draftEdits[it.id].knowledgeId"
                        :list="`school-exam-knowledge-list-${subject}`"
                        :aria-label="`${it.question_label} 草稿所属知识点`"
                        placeholder="点选候选或输入知识点中文名"
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
            </template>
            <div v-else>
              <p class="muted">
                当前场次暂无待核对草稿：可在左侧勾选原卷/答题卡发起解析，或切换「已核对明细与补录」手工录入小题。
              </p>
              <button type="button" class="ghost small" @click="activeTab = 'items'">
                前往已核对明细与补录
              </button>
            </div>
          </section>
        </div>
      </div>
    </div>

    <!-- 子 Tab 3：已核对明细与补录（6:4 矩阵：已核对明细与复盘编辑 | 人工补录已核对小题） -->
    <div
      v-else-if="activeTab === 'items'"
      id="exam-panel-items"
      role="tabpanel"
      aria-labelledby="exam-tab-items"
    >
      <section v-if="!selectedDetail" class="card" aria-label="逐题得分与考点明细">
        <div class="card-head">
          <h3>已核对明细与补录</h3>
        </div>
        <p class="muted">当前尚未选定学校考试，请先在「总分台账与建档」选定或新建场次。</p>
      </section>
      <div v-else class="matrix-6-4">
        <section class="card" aria-label="逐题得分与考点明细">
          <div class="card-head">
            <div>
              <h3>已核对逐题得分与考点明细（{{ confirmedItems.length }}）</h3>
              <p class="card-sub">
                {{
                  subject === 'ethics'
                    ? '道法暂未建立公共课标知识图谱，可按自定义主题标注错因与复盘备注'
                    : '已完成人工确认的逐题明细已纳入学科能力证据与错误分析'
                }}
              </p>
            </div>
            <div class="card-head-tools">
              <button
                v-if="unconfirmedDrafts.length > 0"
                type="button"
                class="ghost small"
                @click="activeTab = 'papers'"
              >
                待核对草稿 ({{ unconfirmedDrafts.length }}) →
              </button>
              <span class="chip">{{ subject === 'ethics' ? '道法 · 校考复盘档案' : '细粒度证据' }}</span>
            </div>
          </div>
          <p v-if="confirmedItems.length === 0" class="muted">
            {{
              unconfirmedDrafts.length > 0
                ? '当前题目均在「原卷与草稿校对」等待人工确认；确认后将在此显示并生成分析结果。'
                : '还没有录入已确认的逐题得分明细，可在右侧表单手工补录。'
            }}
          </p>
          <ul v-else class="attachment-list" tabindex="0" aria-label="已确认逐题得分明细列表">
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
              <p class="card-sub">对照纸质阅卷结果逐题补充；未拿满分可同步标注错因</p>
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
              所属知识点
              <input
                v-model="itemKnowledgeId"
                :list="`school-exam-knowledge-list-${subject}`"
                :placeholder="subject === 'ethics' ? '如：法治与责任（支持直接填主题）' : '请从下拉选取或输入知识点中文名'"
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
      </div>
    </div>

    <!-- 子 Tab 4：错误分析与复盘（上方 2 列对比概览与考点排行 + 下方整行历次顽固失分对比） -->
    <div
      v-else-if="activeTab === 'analysis'"
      id="exam-panel-analysis"
      role="tabpanel"
      aria-labelledby="exam-tab-analysis"
      class="matrix-col-stack"
    >
      <section v-if="!selectedDetail || !errorAnalysis" class="card" aria-label="错误分析与复盘">
        <div class="card-head">
          <h3>错误分析与复盘</h3>
        </div>
        <p class="muted">
          {{ loadingDetail ? '正在加载错误分析数据…' : '当前尚未选定学校考试，请先在「总分台账与建档」选定或新建场次。' }}
        </p>
      </section>
      <template v-else>
        <!-- 数据不足或尚无失分时的诚实状态卡 -->
        <section
          v-if="errorAnalysis.status !== 'analyzed'"
          class="card"
          aria-label="错误分析数据状态说明"
        >
          <div class="card-head">
            <div>
              <h3>本场错误分析 · {{ errorAnalysis.title }}</h3>
              <p class="card-sub">{{ errorAnalysis.diagnosis_summary }}</p>
            </div>
            <div class="card-head-tools">
              <HelpBubble compact title="错误分析口径说明" label="分析口径">
                <p>严格遵守诚实诊断口径，绝不从试卷总分反推考点得分；{{ errorAnalysis.disclaimer }}</p>
              </HelpBubble>
              <span class="chip wait">
                {{ errorAnalysis.status === 'insufficient_items' ? '待补充逐题失分明细' : '暂无失分记录' }}
              </span>
            </div>
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
              <span>待核对自动提取草稿</span>
            </div>
          </div>
          <div style="display: flex; gap: 10px; flex-wrap: wrap; align-items: center;">
            <button type="button" class="primary" @click="activeTab = 'items'">
              前往补录失分小题
            </button>
            <button type="button" class="ghost small" @click="activeTab = 'papers'">
              查看原卷与草稿校对
            </button>
          </div>
        </section>

        <!-- 已有失分明细时的 2 列主诊断 + 跨场次历次复盘 -->
        <template v-else>
          <div class="matrix-2col">
            <!-- 左栏：本场失分概览与错因分布 -->
            <section class="card" aria-label="本场失分概览与错因分布">
              <div class="card-head">
                <div>
                  <h3>本场失分概览与错因分布</h3>
                  <p class="card-sub">{{ errorAnalysis.diagnosis_summary }}</p>
                </div>
                <div class="card-head-tools">
                  <HelpBubble compact title="统计范围说明" label="口径说明">
                    <p>仅汇总已人工核对的逐题失分；未单独归类的失分小题保持如实标示。</p>
                    <p v-if="errorAnalysis.overview.unconfirmed_draft_count > 0">
                      另有 {{ errorAnalysis.overview.unconfirmed_draft_count }} 道自动提取草稿待核对，确认后自动纳入统计。
                    </p>
                  </HelpBubble>
                  <span class="chip mid">
                    已归因 {{ errorAnalysis.overview.lost_item_count }} 题 · -{{ fmtPoints(errorAnalysis.overview.itemized_lost_points) }} 分
                  </span>
                </div>
              </div>

              <div
                v-if="errorAnalysis.overview.unconfirmed_draft_count > 0"
                style="margin-bottom: 10px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;"
              >
                <span class="chip wait">
                  另有 {{ errorAnalysis.overview.unconfirmed_draft_count }} 题草稿待核对
                </span>
                <button type="button" class="ghost small" @click="activeTab = 'papers'">
                  去校对草稿
                </button>
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
              <ul class="error-cat-list" tabindex="0" aria-label="错因归类统计列表">
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

            <!-- 右栏：本场失分考点排行与平时掌握度交叉诊断 -->
            <section class="card" aria-label="本场失分考点排行与交叉诊断">
              <div class="card-head">
                <div>
                  <h3>本场失分考点排行与交叉诊断</h3>
                  <p class="card-sub">
                    {{
                      errorAnalysis.has_taxonomy
                        ? '对比本次校考失分与日常练习独立首答表现'
                        : '道法科目无公共知识图谱，按手工主题归集复盘'
                    }}
                  </p>
                </div>
                <span class="chip">
                  {{ errorAnalysis.has_taxonomy ? '校考失分 × 平时掌握对照' : '主题失分排行' }}
                </span>
              </div>
              <ul class="attachment-list" tabindex="0" aria-label="本场失分考点排行列表">
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

              <h4 class="sub-head" style="margin: 14px 0 8px;">失分小题明细速览（点击可回明细页修改复盘）</h4>
              <ul class="attachment-list" tabindex="0" aria-label="失分小题明细列表">
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
          </div>
        </template>

        <!-- 下方整行：同科历次校考顽固失分点对比 -->
        <section class="card" aria-label="同科历次校考顽固失分点对比">
          <div class="card-head">
            <div>
              <h3>同科历次校考顽固失分点对比</h3>
              <p class="card-sub">
                自动统计「{{ SCHOOL_SUBJECT_LABELS[subject] }}」跨 ≥ 2 场已核对校考重复扣分的知识点
              </p>
            </div>
            <div class="card-head-tools">
              <HelpBubble compact title="校考数据诚实声明" label="诚实口径">
                <p>{{ errorAnalysis.disclaimer }}</p>
              </HelpBubble>
              <span class="chip">
                已统计 {{ errorAnalysis.history_summary.same_subject_exams_with_items }} / {{ errorAnalysis.history_summary.same_subject_exam_count }} 场含明细校考
              </span>
            </div>
          </div>
          <p v-if="errorAnalysis.recurring_knowledge.length === 0" class="muted">
            当前「{{ SCHOOL_SUBJECT_LABELS[subject] }}」暂无跨 2 场以上重复失分的考点；连续多次录入逐题明细后，系统将自动识别顽固薄弱环节。
          </p>
          <ul v-else class="attachment-list" tabindex="0" aria-label="同科历次顽固失分考点列表">
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
                    .map(ex => `${fmtExamMonth(ex.exam_date)} ${ex.title}（-${fmtPoints(ex.lost_points)} 分 / ${ex.item_count} 题）`)
                    .join('；')
                }}
              </div>
            </li>
          </ul>
        </section>
      </template>
    </div>

    <!-- 子 Tab 5：全科校考同步（发现 → 匹配 → 获取 → 核对四步工作流） -->
    <div
      v-else-if="activeTab === 'sync'"
      id="exam-panel-sync"
      role="tabpanel"
      aria-labelledby="exam-tab-sync"
    >
      <SchoolExamSyncCenter
        :client="client"
        :subject="subject"
        :notify="notify"
        :selected-exam-id="selectedExamId"
        @open-exam="openExamFromSync"
        @papers-imported="handleSyncPapersImported"
      />
    </div>

    <!-- 子 Tab 6：校考报告导入与核对（发现 → 关联 → 解析 → 核对四步工作流） -->
    <div
      v-else
      id="exam-panel-report"
      role="tabpanel"
      aria-labelledby="exam-tab-report"
    >
      <SchoolExamReportCenter :client="client" :subject="subject" :notify="notify" />
    </div>
  </section>
</template>
