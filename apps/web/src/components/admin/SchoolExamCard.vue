<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import {
  ApiError,
  describeError,
  SCHOOL_SUBJECT_LABELS,
  type ApiClient,
  type SchoolCoachSession,
  type SchoolErrorCategory,
  type SchoolExam,
  type SchoolExamDetail,
  type SchoolExamErrorAnalysis,
  type SchoolExamItem,
  type SchoolExamRanksPayload,
  type SchoolSubject,
} from '../../api'
import { EXAM_NOTE, fmtBytes, fmtPoints, shortTime } from '../../copy'
import {
  getKnowledgeLabel,
  getMediaTypeLabel,
  getSchoolErrorCategoryLabel,
  getSubjectKnowledgeOptions,
  resolveKnowledgeCodeInput,
} from '../../config/knowledge'
import {
  compareQuestionLabel,
  formatQuestionLabelHeading,
  isSchoolItemFullScore,
  parseDraftBasisTags,
  summarizeSchoolExamItemScores,
} from '../../examSync'
import HelpBubble from '../HelpBubble.vue'
import { RichText } from '../../rich'
import SchoolExamSyncCenter from './SchoolExamSyncCenter.vue'
import StageTabStrip from './StageTabStrip.vue'
import StepFlowWorkspace from './StepFlowWorkspace.vue'
import type { StageGroup, StepDefinition, StepFlowContext } from './stepFlow'
import type { NoticeTone } from '../Notice.vue'

type Notify = (text: string, tone?: NoticeTone) => void
export type ExamTabId = 'scores' | 'papers' | 'items' | 'analysis'
type ScoreStepId = 'pick' | 'upload' | 'sync'
type PaperStepId = 'parse' | 'drafts'
type ItemStepId = 'list' | 'add'
type AnalysisStepId = 'overview' | 'knowledge' | 'history' | 'reflection'
type DraftFilterId = 'all' | 'unmapped' | 'lost' | 'correct' | 'ready'

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
  auto_matched: { label: '关键词关联', tone: 'good' },
  ai_matched: { label: 'AI 智能关联', tone: 'good' },
  type_inferred: { label: '考纲先验关联', tone: 'mid' },
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
const selectedRanks = ref<SchoolExamRanksPayload | null>(null)
const errorAnalysis = ref<SchoolExamErrorAnalysis | null>(null)
const loadingDetail = ref(false)
const activeTab = ref<ExamTabId>(props.initialTab ?? 'scores')
const scoreStep = ref<ScoreStepId>('pick')
const scorePickMode = ref<'list' | 'create'>('list')
const paperStep = ref<PaperStepId>('parse')
const itemStep = ref<ItemStepId>('list')
const analysisStep = ref<AnalysisStepId>('overview')

// 学科可选中文知识点列表（包含 2022 课标 135 个 *_cand 节点，去重同名标签供下拉补全）
const subjectKnowledgeOptions = computed(() => {
  const seenLabels = new Set<string>()
  return getSubjectKnowledgeOptions(props.subject, true).filter(opt => {
    if (seenLabels.has(opt.label)) return false
    seenLabels.add(opt.label)
    return true
  })
})

// 新建校考表单状态（不分科目、面向全科）
const examTitle = ref('')
const examDate = ref(new Date().toISOString().slice(0, 7))
const savingExam = ref(false)

// 私有原卷上传状态
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

// 已有小题的退回学生重写复盘状态（管理端只读查看学生复盘，不代填）
const returningItemId = ref<string | null>(null)
const returnReasonInput = ref('')
const returningSaving = ref(false)

// M2 自动解析与待核对明细核对台状态
const selectedParseAttachmentIds = ref<string[]>([])
const knownParseAttachmentIds = ref<Set<string>>(new Set())
const lastParseInitExamId = ref<string | null>(null)
const parseMode = ref<'auto' | 'skeleton_only'>('auto')
const maskStudentHeader = ref(true)
const replaceUnconfirmedDrafts = ref(false)
const parsingDrafts = ref(false)
const parseProgress = ref(0)
const parseStageText = ref('')
let parseProgressTimer: ReturnType<typeof setInterval> | null = null
const parseDraftError = ref('')
const lastParseSummary = ref('')
const discardingItemId = ref<string | null>(null)
const batchConfirming = ref(false)
const autoAssociatingDrafts = ref(false)
const autoAssociatedExamIds = ref<Set<string>>(new Set())
const draftFilter = ref<DraftFilterId>('all')
const draftErrorItemId = ref<string | null>(null)
const draftListRef = ref<HTMLUListElement | null>(null)
const draftEdits = ref<
  Record<
    string,
    {
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

const allParseAttachmentsSelected = computed(
  () =>
    parseableAttachments.value.length > 0 &&
    parseableAttachments.value.every(a => selectedParseAttachmentIds.value.includes(a.id)),
)
const answerCardAttachments = computed(
  () => parseableAttachments.value.filter(a => /答题卡|答题纸|answer.?card/i.test(a.filename)),
)
const hasAnswerCard = computed(() => answerCardAttachments.value.length > 0)
const unconfirmedDrafts = computed(() =>
  [...(selectedDetail.value?.items.filter(it => !it.confirmed_by_user) ?? [])].sort((x, y) =>
    compareQuestionLabel(x.question_label, y.question_label),
  ),
)
const stageSubjectFilter = ref<SchoolSubject>(props.subject)

const STAGE_SUBJECT_PREFIXES: Array<[string, SchoolSubject]> = [
  ['语文·', 'chinese'],
  ['数学·', 'math'],
  ['英语·', 'english'],
  ['物理·', 'physics'],
  ['道德与法治·', 'ethics'],
  ['道法·', 'ethics'],
]

function inferItemSubject(it: SchoolExamItem): SchoolSubject | null {
  const lbl = String(it.question_label || '').trim()
  for (const [prefix, code] of STAGE_SUBJECT_PREFIXES) {
    if (lbl.startsWith(prefix)) return code
  }
  const kid = String(it.knowledge_id || '').trim().toLowerCase()
  for (const code of ['chinese', 'math', 'english', 'physics', 'ethics'] as SchoolSubject[]) {
    if (kid.startsWith(`${code}.`)) return code
  }
  return null
}

const stageSubjectTabs = computed(() => {
  const detail = selectedDetail.value
  if (!detail || detail.subject !== 'all') return []
  const order: SchoolSubject[] = ['chinese', 'math', 'english', 'physics', 'ethics']
  const counts = new Map<SchoolSubject, number>()
  for (const it of detail.items) {
    if (!it.confirmed_by_user) continue
    const subj = inferItemSubject(it)
    if (subj) counts.set(subj, (counts.get(subj) ?? 0) + 1)
  }
  if (!counts.has(props.subject)) counts.set(props.subject, 0)
  return order
    .filter(code => counts.has(code))
    .map(code => ({
      subject: code,
      label: SCHOOL_SUBJECT_LABELS[code] || code,
      count: counts.get(code) ?? 0,
    }))
})

const confirmedItems = computed(() => {
  const detail = selectedDetail.value
  const list = detail?.items.filter(it => it.confirmed_by_user) ?? []
  const filtered =
    detail?.subject === 'all'
      ? list.filter(it => {
          const subj = inferItemSubject(it)
          return subj ? subj === stageSubjectFilter.value : stageSubjectFilter.value === props.subject
        })
      : list
  return [...filtered].sort((x, y) => compareQuestionLabel(x.question_label, y.question_label))
})
const lostConfirmedItems = computed(() =>
  confirmedItems.value.filter(it => it.earned_points < it.max_points),
)
const extractingStems = ref(false)
const extractStemProgress = ref('')
const stemExtractStatus = ref<{
  active: boolean
  total: number
  done: number
  embedded: number
  vision: number
  notFound: number
  note: string
  errorReason: string | null
} | null>(null)
const confirmingAllStems = ref(false)
const adminCoachOpenId = ref<string | null>(null)
const adminCoachLoadingId = ref<string | null>(null)
const adminCoachCache = ref<Record<string, SchoolCoachSession>>({})
const stemEdits = ref<
  Record<
    string,
    {
      stemText: string
      studentAnswerText: string
      expanded: boolean
      saving: boolean
    }
  >
>({})

const stemStats = computed(() => {
  const lost = lostConfirmedItems.value
  let confirmed = 0
  let draft = 0
  let unextracted = 0
  for (const it of lost) {
    if (it.stem_state === 'confirmed') confirmed += 1
    else if (it.stem_state === 'embedded_draft' || it.stem_state === 'vision_draft') draft += 1
    else if (!it.stem_state) unextracted += 1
  }
  return {
    totalLost: lost.length,
    confirmed,
    draft,
    unextracted,
    allRecognized: lost.length > 0 && unextracted === 0,
  }
})
const scoreSummary = computed(() => summarizeSchoolExamItemScores(selectedDetail.value))
const verifiedExamsCount = computed(
  () => (exams.value ?? []).filter(e => e.confirmed_by_user).length,
)
const pendingExamsCount = computed(
  () => (exams.value ?? []).filter(e => !e.confirmed_by_user).length,
)

const isNewItemLost = computed(
  () => itemEarned.value !== '' && itemMax.value !== '' && Number(itemEarned.value) < Number(itemMax.value)
)

const selectedExamSummary = computed(
  () => exams.value?.find(e => e.id === selectedExamId.value) ?? null
)

// 四阶段真实执行次序分组导航：前置立锚 → 材料入库（报告/同步/原卷） → 明细查漏 → 诊断终点
const examStageGroups = computed<StageGroup[]>(() => {
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
        errorAnalysis.value.recurring_knowledge.some(r => r.repeat_in_current_exam)),
  )

  return [
    {
      id: 'exam-stage-1',
      title: '第一阶段 · 建档与材料',
      tabs: [
        {
          id: 'scores',
          title: '总分台账与建档',
          badge: scoreBadge,
          wait: Boolean(ex && !ex.confirmed_by_user),
          done: Boolean(ex?.confirmed_by_user),
        },
      ],
    },
    {
      id: 'exam-stage-2',
      title: '第二阶段 · 明细提取与核对',
      tabs: [
        {
          id: 'papers',
          title: '原卷提取与明细核对',
          badge: paperDraftBadge,
          wait: draftCount > 0,
          done: Boolean(selectedDetail.value && draftCount === 0 && confirmedItems.value.length > 0),
        },
      ],
    },
    {
      id: 'exam-stage-3',
      title: '第三阶段 · 明细查漏',
      tabs: [
        {
          id: 'items',
          title: '已核对明细与补录',
          badge: confirmedBadge,
          done: confirmedItems.value.length > 0,
        },
      ],
    },
    {
      id: 'exam-stage-4',
      title: '第四阶段 · 诊断终点',
      tabs: [
        {
          id: 'analysis',
          title: '错误分析与复盘',
          badge: analysisBadge,
          wait: analysisWait,
          done: errorAnalysis.value?.status === 'analyzed',
        },
      ],
    },
  ]
})

const examContext = computed<StepFlowContext | null>(() => {
  if (!selectedDetail.value) return null
  return {
    eyebrow: '当前场次',
    title: selectedDetail.value.title,
    statusText: `${fmtPoints(selectedDetail.value.earned_points)} / ${fmtPoints(selectedDetail.value.max_points)} · ${selectedDetail.value.confirmed_by_user ? '已核对' : '未核对'}`,
    statusTone: selectedDetail.value.confirmed_by_user ? 'good' : 'wait',
  }
})

const scoreSteps = computed<StepDefinition[]>(() => {
  const hasExam = selectedDetail.value !== null
  const examPaperCount = selectedDetail.value?.attachments.filter(a => a.category !== 'answer_sheet').length ?? 0
  return [
    {
      id: 'pick',
      title: '1. 选定或新建校考档案',
      subtitle: selectedDetail.value ? '已选定档案' : '先从台账选定或建新档',
      badge: `${exams.value?.length ?? 0} 场`,
      done: hasExam,
      prereqMet: true,
    },
    {
      id: 'upload',
      title: '2. 上传原卷',
      subtitle: examPaperCount > 0 ? `已归档 ${examPaperCount} 份` : '存放于档案 exam-paper 目录',
      badge: `${examPaperCount} 份`,
      done: examPaperCount > 0,
      prereqMet: hasExam,
      lockReason: '请先在第 1 步选定或新建一场学校考试档案。',
    },
    {
      id: 'sync',
      title: '3. 全科校考同步',
      subtitle: '同步全科成绩与答题卡至 answer-sheet 目录',
      done: false,
      prereqMet: true,
    },
  ]
})

const paperSteps = computed<StepDefinition[]>(() => {
  const hasExam = selectedDetail.value !== null
  const hasParseable = parseableAttachments.value.length > 0
  const hasDraftsOrConfirmed = unconfirmedDrafts.value.length > 0 || confirmedItems.value.length > 0
  return [
    {
      id: 'parse',
      title: '1. 自动提取待核对明细',
      subtitle: hasParseable ? `可选 ${parseableAttachments.value.length} 份附件` : '须先在第一阶段上传原卷',
      done: hasDraftsOrConfirmed,
      prereqMet: hasExam && hasParseable,
      lockReason: '请先在「第一阶段 · 第 2 步 上传原卷」上传可解析的原卷；若已从「全科校考同步」生成待核对明细，可直接点击第 2 步核对台。',
    },
    {
      id: 'drafts',
      title: '2. 逐题明细核对台',
      subtitle:
        unconfirmedDrafts.value.length > 0
          ? `待核对 ${unconfirmedDrafts.value.length} 题`
          : confirmedItems.value.length > 0
            ? '本页明细已全部入账'
            : '待第 1 步或全科同步生成明细',
      badge: `${unconfirmedDrafts.value.length} 题`,
      badgeTone: unconfirmedDrafts.value.length > 0 ? 'wait' : 'good',
      done: hasExam && unconfirmedDrafts.value.length === 0 && confirmedItems.value.length > 0,
      prereqMet: hasExam && hasDraftsOrConfirmed,
      lockReason: '当前场次还没有待核对明细：请先在第 1 步提取原卷，或从第一阶段第 3 步「全科校考同步」生成逐题待核对明细。',
    },
  ]
})

const itemSteps = computed<StepDefinition[]>(() => {
  const hasExam = selectedDetail.value !== null
  return [
    {
      id: 'list',
      title: '1. 已核对逐题明细与复盘',
      subtitle: `已核对 ${confirmedItems.value.length} 题`,
      badge: `${confirmedItems.value.length} 条`,
      done: confirmedItems.value.length > 0,
      prereqMet: hasExam,
      lockReason: '请先在「第一阶段 · 总分台账与建档」选定或新建一场学校考试。',
    },
    {
      id: 'add',
      title: '2. 人工补录已核对小题',
      subtitle: '对照纸质卷手工补充',
      done: confirmedItems.value.length > 0,
      prereqMet: hasExam,
      lockReason: '请先在「第一阶段 · 总分台账与建档」选定或新建一场学校考试。',
    },
  ]
})

const analysisSteps = computed<StepDefinition[]>(() => {
  const analyzed = Boolean(selectedDetail.value && errorAnalysis.value?.status === 'analyzed')
  return [
    {
      id: 'overview',
      title: '1. 本场失分概览与错因分布',
      subtitle: '总体失分 KPI 与错因占比',
      done: analyzed,
      prereqMet: analyzed,
      lockReason: '当前场次尚无已人工确认的失分小题明细，请先核对草稿或手工补录小题。',
    },
    {
      id: 'knowledge',
      title: '2. 失分考点排行与交叉诊断',
      subtitle: '校考失分 × 平时掌握对照',
      done: analyzed,
      prereqMet: analyzed,
      lockReason: '请先补充并确认失分小题明细。',
    },
    {
      id: 'history',
      title: '3. 同科历次顽固失分点对比',
      subtitle: '跨 ≥ 2 场校考重复失分',
      done: analyzed,
      prereqMet: analyzed,
      lockReason: '请先补充并确认失分小题明细。',
    },
    {
      id: 'reflection',
      title: '4. 失分题干与学生复盘',
      subtitle:
        lostConfirmedItems.value.length > 0
          ? `题干已确认 ${stemStats.value.confirmed}/${stemStats.value.totalLost}`
          : '查看学生复盘与留言',
      done: analyzed && stemStats.value.totalLost > 0 && stemStats.value.confirmed === stemStats.value.totalLost,
      prereqMet: analyzed,
      lockReason: '请先补充并确认失分小题明细。',
    },
  ]
})

async function selectStageSubject(subj: SchoolSubject) {
  stageSubjectFilter.value = subj
  if (selectedExamId.value) {
    try {
      errorAnalysis.value = await props.client.schoolExamErrorAnalysis(selectedExamId.value, subj)
    } catch {
      // ignore transient error
    }
  }
}

async function loadDetail(examId: string) {
  loadingDetail.value = true
  try {
    const [detail, analysis, ranks] = await Promise.all([
      props.client.schoolExamDetail(examId),
      props.client.schoolExamErrorAnalysis(examId, stageSubjectFilter.value),
      typeof props.client.schoolExamRanks === 'function'
        ? props.client.schoolExamRanks(examId).catch(() => null)
        : Promise.resolve(null),
    ])
    selectedDetail.value = detail
    errorAnalysis.value = analysis
    selectedRanks.value = ranks
    syncDraftStateFromDetail(detail)
    syncStemEditsFromDetail(detail)
  } catch (e) {
    selectedDetail.value = null
    errorAnalysis.value = null
    selectedRanks.value = null
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
    knownParseAttachmentIds.value = new Set(validAttachIds)
    lastParseInitExamId.value = detail.id
    parseDraftError.value = ''
    lastParseSummary.value = ''
    draftFilter.value = 'all'
    draftErrorItemId.value = null
  } else {
    const existingSet = new Set(validAttachIds)
    const kept = selectedParseAttachmentIds.value.filter(id => existingSet.has(id))
    const newlyAdded = validAttachIds.filter(id => !knownParseAttachmentIds.value.has(id))
    selectedParseAttachmentIds.value = [...kept, ...newlyAdded]
    knownParseAttachmentIds.value = existingSet
  }

  const nextEdits: typeof draftEdits.value = {}
  for (const it of detail.items) {
    if (it.confirmed_by_user) continue
    const isUnmapped = !it.knowledge_id || it.knowledge_id === 'unmapped'
    const label = isUnmapped ? '' : getKnowledgeLabel(it.knowledge_id)
    const displayKnowledge = isUnmapped
      ? ''
      : label !== it.knowledge_id
        ? label
        : (it.knowledge_name || it.knowledge_id)
    const lost = !isSchoolItemFullScore(it.earned_points, it.max_points)
    const prev = draftEdits.value[it.id]
    nextEdits[it.id] = prev
      ? {
          ...prev,
          knowledgeId: prev.knowledgeId.trim() ? prev.knowledgeId : displayKnowledge,
        }
      : {
          knowledgeId: displayKnowledge,
          errorCategory: lost ? (it.error_category ?? '') : '',
          errorNote: lost ? (it.error_note ?? '') : '',
        }
  }
  draftEdits.value = nextEdits
}

function examNeedsAutoAssociate(detail: SchoolExamDetail | null): boolean {
  if (!detail) return false
  const hasAttachments = Array.isArray(detail.attachments) && detail.attachments.length > 0
  return detail.items.some(
    it =>
      !it.confirmed_by_user &&
      (!it.knowledge_id ||
        it.knowledge_id === 'unmapped' ||
        !it.draft_knowledge_candidates ||
        it.draft_knowledge_candidates.length < 3 ||
        (hasAttachments && it.draft_confidence === 'type_inferred')),
  )
}

async function runAutoAssociateDrafts(options?: { overwrite?: boolean; silent?: boolean }) {
  if (!selectedDetail.value || autoAssociatingDrafts.value) return
  if (typeof props.client.autoAssociateSchoolExamItems !== 'function') return
  const examId = selectedDetail.value.id
  autoAssociatingDrafts.value = true
  try {
    const res = await props.client.autoAssociateSchoolExamItems(examId, {
      useAi: true,
      overwriteExisting: options?.overwrite ?? false,
    })
    if (options?.overwrite) {
      draftEdits.value = {}
    }
    if (res.updated > 0) {
      await loadDetail(examId)
      if (!options?.silent) {
        props.notify(`已自动补全 ${res.updated} 道明细的候选考点与初始关联（待人工核对后入账）。`, 'success')
      }
    } else if (!options?.silent) {
      props.notify('全部待核明细均已具备 3 个候选考点与初始关联。', 'info')
    }
  } catch (e) {
    if (!options?.silent) {
      props.notify(describeError(e), 'error')
    }
  } finally {
    autoAssociatingDrafts.value = false
  }
}

watch(
  [() => activeTab.value, () => paperStep.value, () => selectedDetail.value?.id],
  ([tab, step, examId]) => {
    if (tab !== 'papers' || step !== 'drafts' || !examId || !selectedDetail.value) return
    if (autoAssociatedExamIds.value.has(examId)) return
    if (!examNeedsAutoAssociate(selectedDetail.value)) return
    const nextSet = new Set(autoAssociatedExamIds.value)
    nextSet.add(examId)
    autoAssociatedExamIds.value = nextSet
    void runAutoAssociateDrafts({ overwrite: false, silent: true })
  },
)

async function refreshExams(preferId?: string, advanceToUpload = false) {
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
    if (list.length === 0) {
      scorePickMode.value = 'create'
    }
    if (targetId) {
      await loadDetail(targetId)
      if (advanceToUpload && preferId && preferId === targetId && activeTab.value === 'scores' && selectedDetail.value?.id === preferId) {
        scoreStep.value = 'upload'
      }
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
    stageSubjectFilter.value = props.subject
    scoreStep.value = 'pick'
    scorePickMode.value = 'list'
    paperStep.value = 'parse'
    itemStep.value = 'list'
    analysisStep.value = 'overview'
    paperFile.value = null
    uploadError.value = ''
    returningItemId.value = null
    returnReasonInput.value = ''
    stemExtractStatus.value = null
    adminCoachOpenId.value = null
    adminCoachCache.value = {}
    lastParseInitExamId.value = null
    selectedParseAttachmentIds.value = []
    parseDraftError.value = ''
    lastParseSummary.value = ''
    draftFilter.value = 'all'
    draftErrorItemId.value = null
    draftEdits.value = {}
    autoAssociatedExamIds.value = new Set()
    confirmDeleteExamId.value = null
    void refreshExams(props.initialExamId)
  },
  { immediate: true }
)

async function selectExam(examId: string) {
  selectedExamId.value = examId
  uploadError.value = ''
  returningItemId.value = null
  returnReasonInput.value = ''
  stemExtractStatus.value = null
  adminCoachOpenId.value = null
  adminCoachCache.value = {}
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
  savingExam.value = true
  try {
    const created = await props.client.addSchoolExam({
      subject: 'all',
      title,
      examDate: examDate.value,
      earnedPoints: 100,
      maxPoints: 100,
      confirmedByUser: false,
    })
    props.notify(
      `全科校考档案已创建（已在 school-exams 下建立档案目录）。${EXAM_NOTE}`,
      'success'
    )
    examTitle.value = ''
    await refreshExams(created.id)
    scorePickMode.value = 'list'
    activeTab.value = 'scores'
    scoreStep.value = 'upload'
  } catch (e) {
    props.notify(describeError(e), 'error')
  } finally {
    savingExam.value = false
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
    uploadError.value = '请先选择原卷文件。'
    return
  }
  const mime = pickPaperMime(paperFile.value)
  if (mime === null) {
    uploadError.value = '仅支持 PDF / DOCX / PNG / JPG 文件。'
    return
  }
  if (paperFile.value.size > MAX_PAPER_BYTES) {
    uploadError.value = '原卷附件超过 35 MiB 上限。'
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
    props.notify(`原卷「${saved.filename}」已存入档案 exam-paper 目录。`, 'success')
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
    itemStep.value = 'list'
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
  if (!trimmed) return ''
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

function toggleSelectAllParseAttachments() {
  if (allParseAttachmentsSelected.value) {
    selectedParseAttachmentIds.value = []
    return
  }
  selectedParseAttachmentIds.value = parseableAttachments.value.map(a => a.id)
}

function stopParseProgressTimer() {
  if (parseProgressTimer !== null) {
    clearInterval(parseProgressTimer)
    parseProgressTimer = null
  }
}

async function runParseDrafts() {
  if (!selectedDetail.value) return
  if (selectedParseAttachmentIds.value.length === 0) {
    parseDraftError.value = '请至少勾选一份原卷或答题卡附件。'
    return
  }
  parsingDrafts.value = true
  parseDraftError.value = ''
  parseProgress.value = 10
  parseStageText.value =
    parseMode.value === 'auto'
      ? `正在准备 ${selectedParseAttachmentIds.value.length} 份附件并执行隐私脱敏遮罩…`
      : `正在本地读取 ${selectedParseAttachmentIds.value.length} 份附件并提取题号骨架…`
  stopParseProgressTimer()
  parseProgressTimer = setInterval(() => {
    if (parseProgress.value < 45) {
      parseProgress.value += 6
      if (parseProgress.value >= 35) {
        parseStageText.value =
          parseMode.value === 'auto'
            ? '正在调用识别模型解析逐题得分与错因线索…'
            : '正在解析文本结构与题号分值…'
      }
    } else if (parseProgress.value < 78) {
      parseProgress.value += 3
      if (parseProgress.value >= 70) {
        parseStageText.value = '正在匹配候选知识点并生成待核对明细…'
      }
    } else if (parseProgress.value < 92) {
      parseProgress.value += 1
    }
  }, 350)
  try {
    const res = await props.client.parseSchoolExamDrafts(selectedDetail.value.id, {
      attachmentIds: selectedParseAttachmentIds.value,
      mode: parseMode.value,
      maskStudentHeader: maskStudentHeader.value,
      replaceUnconfirmedDrafts: replaceUnconfirmedDrafts.value,
    })
    parseProgress.value = 100
    parseStageText.value = '提取完成，正在刷新待核对明细…'
    const modeLabel = res.parser_mode_used.startsWith('deepseek_vision')
      ? `智能多模态识别（送检 ${res.meta.pages_sent ?? 0} 页，脱敏 ${res.meta.masked_pages ?? 0} 页）`
      : '本地规则文字骨架提取'
    const skippedMsg =
      res.skipped_labels.length > 0 ? `；已跳过 ${res.skipped_labels.length} 道既有题目` : ''
    lastParseSummary.value = `${modeLabel}：生成 ${res.created_items.length} 条待核对明细${skippedMsg}`
    props.notify(lastParseSummary.value, 'success')
    draftEdits.value = {}
    draftFilter.value = 'all'
    draftErrorItemId.value = null
    await loadDetail(selectedDetail.value.id)
    if (unconfirmedDrafts.value.length > 0) {
      paperStep.value = 'drafts'
    }
  } catch (e) {
    parseDraftError.value = describeError(e)
  } finally {
    stopParseProgressTimer()
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

function isDraftKnowledgeReady(it: SchoolExamItem): boolean {
  const edit = draftEdits.value[it.id]
  const raw = edit ? edit.knowledgeId : (it.knowledge_id === 'unmapped' ? '' : it.knowledge_id)
  const kid = resolveDraftKnowledgeCode(it, raw)
  return Boolean(kid && kid !== 'unmapped')
}

const draftFilterCounts = computed(() => {
  const list = unconfirmedDrafts.value
  let unmapped = 0
  let lost = 0
  let correct = 0
  let ready = 0
  for (const it of list) {
    const isReady = isDraftKnowledgeReady(it)
    if (isReady) ready += 1
    else unmapped += 1
    if (isSchoolItemFullScore(it.earned_points, it.max_points)) correct += 1
    else lost += 1
  }
  return { all: list.length, unmapped, lost, correct, ready }
})

const filteredDrafts = computed(() => {
  const list = unconfirmedDrafts.value
  if (draftFilter.value === 'unmapped') return list.filter(it => !isDraftKnowledgeReady(it))
  if (draftFilter.value === 'lost') return list.filter(it => !isSchoolItemFullScore(it.earned_points, it.max_points))
  if (draftFilter.value === 'correct') return list.filter(it => isSchoolItemFullScore(it.earned_points, it.max_points))
  if (draftFilter.value === 'ready') return list.filter(isDraftKnowledgeReady)
  return list
})

const readyDrafts = computed(() => unconfirmedDrafts.value.filter(isDraftKnowledgeReady))

const hasCandidateSuggestions = computed(() =>
  unconfirmedDrafts.value.some(
    it => !isDraftKnowledgeReady(it) && ((it.draft_knowledge_candidates?.length ?? 0) > 0 || props.subject === 'ethics'),
  ),
)

function applyCandidateKnowledge(itemId: string, knowledgeId: string, title?: string) {
  const edit = draftEdits.value[itemId]
  if (edit) {
    const label = getKnowledgeLabel(knowledgeId)
    edit.knowledgeId = label !== knowledgeId ? label : (title || knowledgeId)
    if (draftErrorItemId.value === itemId) draftErrorItemId.value = null
  }
}

function applyAllTopCandidates() {
  let applied = 0
  for (const it of unconfirmedDrafts.value) {
    if (isDraftKnowledgeReady(it)) continue
    const top = it.draft_knowledge_candidates?.[0]
    if (top) {
      applyCandidateKnowledge(it.id, top.knowledge_id, top.title)
      applied += 1
    } else if (props.subject === 'ethics' && draftEdits.value[it.id]) {
      draftEdits.value[it.id].knowledgeId = '道法综合主题'
      applied += 1
    }
  }
  if (applied > 0) {
    props.notify(`已为 ${applied} 道待核对明细填入推荐考点，请抽检后确认入账。`, 'success')
  }
}

function findPrevReadyKnowledge(itemId: string): string | null {
  const list = unconfirmedDrafts.value
  const idx = list.findIndex(it => it.id === itemId)
  if (idx <= 0) return null
  for (let i = idx - 1; i >= 0; i -= 1) {
    const prev = list[i]
    if (isDraftKnowledgeReady(prev)) {
      const val = draftEdits.value[prev.id]?.knowledgeId.trim()
      if (val) return val
    }
  }
  return null
}

function copyPrevDraftKnowledge(itemId: string) {
  const prevLabel = findPrevReadyKnowledge(itemId)
  const edit = draftEdits.value[itemId]
  if (prevLabel && edit) {
    edit.knowledgeId = prevLabel
    if (draftErrorItemId.value === itemId) draftErrorItemId.value = null
  }
}

async function focusDraftItem(itemId: string) {
  draftErrorItemId.value = itemId
  if (draftFilter.value !== 'all') {
    draftFilter.value = 'all'
    await nextTick()
  }
  const el = draftListRef.value?.querySelector<HTMLElement>(`[data-draft-item-id="${itemId}"]`)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    const input = el.querySelector<HTMLInputElement>('input[data-knowledge-input]')
    input?.focus({ preventScroll: true })
  }
}

function buildDraftConfirmEntry(it: SchoolExamItem) {
  const edit = draftEdits.value[it.id]
  const earnedNum = it.earned_points
  const maxNum = it.max_points
  const rawKnowledge = edit ? edit.knowledgeId : (it.knowledge_id === 'unmapped' ? '' : it.knowledge_id)
  const kid = resolveDraftKnowledgeCode(it, rawKnowledge)
  const heading = formatQuestionLabelHeading(it.question_label)
  if (Number.isNaN(earnedNum) || Number.isNaN(maxNum) || maxNum <= 0 || maxNum > 100 || earnedNum < 0 || earnedNum > maxNum) {
    return { error: `「${heading}」卷面分值异常（${earnedNum}/${maxNum}），请移除或重新解析。` }
  }
  if (!kid || kid === 'unmapped') {
    return { error: `「${heading}」请先选择或填写所属知识点后再确认入账。` }
  }
  const lost = !isSchoolItemFullScore(earnedNum, maxNum)
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
    await focusDraftItem(it.id)
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
    if (draftErrorItemId.value === it.id) draftErrorItemId.value = null
    props.notify(`「${formatQuestionLabelHeading(it.question_label)}」已完成人工核对并正式入账。`, 'success')
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
    if (draftErrorItemId.value === it.id) draftErrorItemId.value = null
    props.notify(`已移除「${formatQuestionLabelHeading(it.question_label)}」待核对明细。`, 'info')
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
      await focusDraftItem(it.id)
      return
    }
    entries.push(built.payload!)
  }
  batchConfirming.value = true
  try {
    const res = await props.client.confirmSchoolExamItemsBatch(selectedDetail.value.id, entries)
    draftErrorItemId.value = null
    props.notify(`已批量确认 ${res.evidence_created} 条待核对明细并更新错误分析。`, 'success')
    await loadDetail(selectedDetail.value.id)
  } catch (e) {
    props.notify(describeError(e), 'error')
  } finally {
    batchConfirming.value = false
  }
}

async function confirmReadyDraftsBatch() {
  if (!selectedDetail.value || readyDrafts.value.length === 0) return
  const entries = []
  for (const it of readyDrafts.value) {
    const built = buildDraftConfirmEntry(it)
    if ('error' in built && built.error) {
      props.notify(built.error, 'caution')
      await focusDraftItem(it.id)
      return
    }
    entries.push(built.payload!)
  }
  batchConfirming.value = true
  try {
    const res = await props.client.confirmSchoolExamItemsBatch(selectedDetail.value.id, entries)
    draftErrorItemId.value = null
    props.notify(`已先确认 ${res.evidence_created} 条已就绪待核对明细并更新错误分析。`, 'success')
    await loadDetail(selectedDetail.value.id)
  } catch (e) {
    props.notify(describeError(e), 'error')
  } finally {
    batchConfirming.value = false
  }
}

function startReturnReflection(it: SchoolExamItem) {
  returningItemId.value = it.id
  returnReasonInput.value = it.return_reason || '请进一步写明具体出错步骤与可执行的改进方法'
}

function cancelReturnReflection() {
  returningItemId.value = null
  returnReasonInput.value = ''
}

async function submitReturnReflection(it: SchoolExamItem) {
  if (!selectedDetail.value) return
  const reason = returnReasonInput.value.trim() || '请进一步写明具体出错步骤与可执行的改进方法'
  returningSaving.value = true
  try {
    await props.client.returnSchoolExamItemReflection(selectedDetail.value.id, it.id, reason)
    props.notify(`已将「${it.question_label}」退回学生端重写复盘。`, 'info')
    cancelReturnReflection()
    await loadDetail(selectedDetail.value.id)
  } catch (e) {
    props.notify(describeError(e), 'error')
  } finally {
    returningSaving.value = false
  }
}

function jumpToEditItem(_itemId: string) {
  activeTab.value = 'analysis'
  analysisStep.value = 'reflection'
}

function syncStemEditsFromDetail(detail: SchoolExamDetail) {
  const next: typeof stemEdits.value = {}
  for (const it of detail.items) {
    if (!it.confirmed_by_user || it.earned_points >= it.max_points) continue
    const prev = stemEdits.value[it.id]
    next[it.id] = {
      stemText: it.stem_text ?? '',
      studentAnswerText: it.student_answer_text ?? '',
      expanded: prev?.expanded ?? Boolean(it.stem_state === 'vision_draft' || it.stem_state === 'embedded_draft'),
      saving: false,
    }
  }
  stemEdits.value = next
}

function stemStateLabel(state: SchoolExamItem['stem_state']): { text: string; tone: string } {
  if (state === 'confirmed') return { text: '题干已确认', tone: 'good' }
  if (state === 'vision_draft') return { text: 'AI 草稿待确认', tone: 'wait' }
  if (state === 'embedded_draft') return { text: '文字层草稿待确认', tone: 'wait' }
  if (state === 'not_found') return { text: '未识别到·请手动填写', tone: 'bad' }
  if (state === 'extracting') return { text: '识别中…', tone: 'mid' }
  return { text: '待识别', tone: 'subtle' }
}

async function extractStems() {
  if (!selectedDetail.value || extractingStems.value) return
  extractingStems.value = true
  const examId = selectedDetail.value.id
  const pendingLabels = lostConfirmedItems.value
    .filter(it => !it.stem_state)
    .map(it => formatQuestionLabelHeading(it.question_label))
  const totalTarget = pendingLabels.length || stemStats.value.unextracted
  let doneCount = 0
  let totalEmbedded = 0
  let totalVision = 0
  let totalNotFound = 0
  let unavailableReason: string | null = null

  stemExtractStatus.value = {
    active: true,
    total: totalTarget,
    done: 0,
    embedded: 0,
    vision: 0,
    notFound: 0,
    note: totalTarget > 0 ? `准备识别 ${totalTarget} 道失分题…` : '检查待识别题目…',
    errorReason: null,
  }

  try {
    while (true) {
      const nextLabels = pendingLabels.slice(doneCount, doneCount + 2)
      const batchHint = nextLabels.length > 0 ? `（正在识别：${nextLabels.join('、')}）` : ''
      extractStemProgress.value =
        totalTarget > 0 ? `正在识别 (${doneCount}/${totalTarget})…` : '正在识别…'
      if (stemExtractStatus.value) {
        stemExtractStatus.value.note =
          totalTarget > 0
            ? `已处理 ${doneCount} / ${totalTarget} 题${batchHint}`
            : '正在识别中…'
      }

      const res = await props.client.extractSchoolExamStems(examId, {
        maskStudentHeader: true,
        batchSize: 2,
      })
      if (res.requested === 0) {
        break
      }
      doneCount += res.requested
      totalEmbedded += res.embedded
      totalVision += res.vision
      totalNotFound += res.not_found
      if (res.ai_unavailable_reason) {
        unavailableReason = res.ai_unavailable_reason
      }
      const nextTotal = Math.max(totalTarget, doneCount + res.remaining_unextracted)
      if (stemExtractStatus.value) {
        stemExtractStatus.value.total = nextTotal
        stemExtractStatus.value.done = doneCount
        stemExtractStatus.value.embedded = totalEmbedded
        stemExtractStatus.value.vision = totalVision
        stemExtractStatus.value.notFound = totalNotFound
      }
      await loadDetail(examId)
      if (res.remaining_unextracted <= 0 || res.ai_unavailable_reason) {
        break
      }
    }

    if (doneCount === 0) {
      stemExtractStatus.value = null
      props.notify('本场失分题均已完成题干识别，无需重复解析。', 'info')
    } else if (unavailableReason) {
      const reasonText = describeError(new ApiError(503, unavailableReason))
      if (stemExtractStatus.value) {
        stemExtractStatus.value.active = false
        stemExtractStatus.value.note = `已从 PDF 文字层提取 ${totalEmbedded} 题，其余待识别题目已保留为待识别。`
        stemExtractStatus.value.errorReason = reasonText
      }
      props.notify(`已从 PDF 文字层提取 ${totalEmbedded} 题；视觉 AI 不可用：${reasonText}`, 'info')
    } else {
      if (stemExtractStatus.value) {
        stemExtractStatus.value.active = false
        stemExtractStatus.value.done = stemExtractStatus.value.total
        stemExtractStatus.value.note = `全部 ${doneCount} 题处理完成：文字层 ${totalEmbedded} 题、AI 识别 ${totalVision} 题、未识别到 ${totalNotFound} 题（可手动补录）。`
        stemExtractStatus.value.errorReason = null
      }
      props.notify(
        `已识别 ${totalEmbedded + totalVision} 题（文字层 ${totalEmbedded}、AI ${totalVision}，未识别到 ${totalNotFound}），请核对后确认。`,
        'success',
      )
    }
  } catch (e) {
    const reasonText = describeError(e)
    if (doneCount > 0) {
      await loadDetail(examId)
    }
    if (stemExtractStatus.value) {
      stemExtractStatus.value.active = false
      stemExtractStatus.value.note =
        doneCount > 0
          ? `前 ${doneCount} 题结果已保存，剩余题目未锁定，可点击「提取失分题题干与作答」继续。`
          : '本次未能完成识别，待识别题目已恢复，可重试或手动填写。'
      stemExtractStatus.value.errorReason = reasonText
    }
    props.notify(
      doneCount > 0
        ? `前 ${doneCount} 题已保存；后续批次中断：${reasonText}`
        : `识别失败：${reasonText}`,
      'error',
    )
  } finally {
    extractingStems.value = false
    extractStemProgress.value = ''
  }
}

async function saveItemStem(it: SchoolExamItem, confirm: boolean) {
  if (!selectedDetail.value) return
  const edit = stemEdits.value[it.id]
  if (!edit || edit.saving) return
  if (confirm && !edit.stemText.trim()) {
    props.notify(`请先填写「${it.question_label}」的题干内容后再确认。`, 'error')
    return
  }
  edit.saving = true
  try {
    await props.client.patchSchoolExamItemStem(selectedDetail.value.id, it.id, {
      stem_text: edit.stemText.trim() || null,
      student_answer_text: edit.studentAnswerText.trim() || null,
      confirm,
    })
    props.notify(
      confirm ? `「${it.question_label}」题干已确认并同步至学生端。` : `已保存「${it.question_label}」题干草稿。`,
      'success',
    )
    await loadDetail(selectedDetail.value.id)
  } catch (e) {
    props.notify(describeError(e), 'error')
  } finally {
    edit.saving = false
  }
}

async function toggleAdminCoachView(itemId: string) {
  if (!selectedDetail.value) return
  if (adminCoachOpenId.value === itemId) {
    adminCoachOpenId.value = null
    return
  }
  adminCoachOpenId.value = itemId
  if (adminCoachCache.value[itemId]) return
  adminCoachLoadingId.value = itemId
  try {
    const res = await props.client.getAdminSchoolExamItemCoach(selectedDetail.value.id, itemId)
    adminCoachCache.value = { ...adminCoachCache.value, [itemId]: res }
  } catch (e) {
    props.notify(describeError(e), 'error')
    adminCoachOpenId.value = null
  } finally {
    adminCoachLoadingId.value = null
  }
}

async function confirmAllStems() {
  if (!selectedDetail.value || confirmingAllStems.value) return
  confirmingAllStems.value = true
  try {
    const res = await props.client.confirmSchoolExamStems(selectedDetail.value.id)
    props.notify(`已批量确认 ${res.confirmed_count} 道失分题题干。`, 'success')
    await loadDetail(selectedDetail.value.id)
  } catch (e) {
    props.notify(describeError(e), 'error')
  } finally {
    confirmingAllStems.value = false
  }
}

async function openExamFromSync(examId: string, tab: 'scores' | 'papers' | 'items' | 'analysis') {
  if (examId) {
    await selectExam(examId)
    const targetSubject = selectedDetail.value?.subject
    if (targetSubject && targetSubject !== 'all' && targetSubject !== props.subject) {
      const safeTab: 'scores' | 'papers' | 'items' = tab === 'analysis' ? 'items' : tab
      emit('select-subject', targetSubject, examId, safeTab)
      return
    }
  }
  activeTab.value = tab
  if (tab === 'papers' && unconfirmedDrafts.value.length > 0) {
    paperStep.value = 'drafts'
  } else if (tab === 'scores' && selectedDetail.value) {
    scoreStep.value = 'upload'
  }
}

function goAnalysisAddItems() {
  activeTab.value = 'items'
  itemStep.value = 'add'
}

async function selectExamAndAdvance(examId: string) {
  await selectExam(examId)
  scoreStep.value = 'upload'
}

function enterPapersStage() {
  activeTab.value = 'papers'
  if (unconfirmedDrafts.value.length > 0 && parseableAttachments.value.length === 0) {
    paperStep.value = 'drafts'
  } else if (parseableAttachments.value.length > 0 && unconfirmedDrafts.value.length === 0) {
    paperStep.value = 'parse'
  } else if (unconfirmedDrafts.value.length > 0) {
    paperStep.value = 'drafts'
  } else {
    paperStep.value = 'parse'
  }
}

watch(
  () => activeTab.value,
  tab => {
    if (tab === 'papers' && unconfirmedDrafts.value.length > 0 && parseableAttachments.value.length === 0) {
      paperStep.value = 'drafts'
    }
  },
)

async function handleSyncPapersImported(examId: string) {
  await refreshExams(examId || undefined)
}
</script>

<template>
  <section class="exam-workspace admin-workspace" aria-label="学校考试总分">
    <!-- 顶部信息汇总卡（与知识点审核工作台同款紧凑摘要条） -->
    <div class="slim-tool-bar" role="region" aria-label="学校考试工作台总览">
      <div class="slim-tool-main">
        <div class="slim-tool-title-row">
          <h2>{{ SCHOOL_SUBJECT_LABELS[subject] }}学校考试工作台</h2>
          <div class="status-badges-row status-banner" role="region" aria-label="学校考试状态统计">
            <span class="badge pending">待核对: {{ pendingExamsCount }}</span>
            <span class="badge approved">已核对: {{ verifiedExamsCount }}</span>
            <span class="badge total">场次总数: {{ exams?.length ?? 0 }}</span>
            <span :class="['badge', unconfirmedDrafts.length > 0 ? 'pending' : 'clauses']">
              待核明细: {{ unconfirmedDrafts.length }} 题
            </span>
          </div>
        </div>
        <div class="sub-head">
          <span>当前科目：{{ SCHOOL_SUBJECT_LABELS[subject] }} · 私人校卷原卷与答题卡加密隔离保存，绝不进入公开题库</span>
          <span
            v-if="(exams?.length ?? 0) > 0 && pendingExamsCount === 0 && unconfirmedDrafts.length === 0"
            class="audit-note audit-ok"
          >
            当前科目已录场次均已完成人工核对，且无待核对明细。
          </span>
          <span v-else-if="unconfirmedDrafts.length > 0" class="audit-note">
            当前场次尚有 {{ unconfirmedDrafts.length }} 条待核对明细等待人工确认。
          </span>
          <span v-else-if="pendingExamsCount > 0" class="audit-note">
            尚有 {{ pendingExamsCount }} 场考试待核对实得总分或确认锁定。
          </span>
        </div>
      </div>

      <div class="slim-tool-actions">
        <HelpBubble compact title="校考录入说明" label="校考录入说明">
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

    <!-- 四阶段分组导航条：第一阶段总分建档 → 第二阶段三路入库 → 第三阶段明细查漏 → 第四阶段诊断终点 -->
    <StageTabStrip
      :model-value="activeTab"
      :groups="examStageGroups"
      region-label="学校考试阶段工作区"
      id-prefix="exam"
      @update:model-value="id => (activeTab = id as ExamTabId)"
    />

    <!-- 全局复用：当前学科知识点中文补全列表（供草稿校对与手工补录共用） -->
    <datalist :id="`school-exam-knowledge-list-${subject}`">
      <option v-for="opt in subjectKnowledgeOptions" :key="opt.code" :value="opt.label" />
    </datalist>

    <!-- 第一阶段 · 前置立锚：校考建档、原卷上传与全科同步（1. 选定或新建校考档案 → 2. 上传原卷 → 3. 全科校考同步） -->
    <div
      v-if="activeTab === 'scores'"
      id="exam-panel-scores"
      role="tabpanel"
      aria-labelledby="exam-tab-scores"
    >
      <StepFlowWorkspace
        :model-value="scoreStep"
        :steps="scoreSteps"
        :context="examContext"
        steps-aria-label="校考建档与同步步骤"
        @update:model-value="id => (scoreStep = id as ScoreStepId)"
      >
        <template #step-pick>
          <section
            class="card"
            :aria-label="scorePickMode === 'create' ? '新建学校考试档案' : '已录校考台账'"
          >
            <div class="card-head">
              <div>
                <h3>
                  {{
                    scorePickMode === 'create'
                      ? '新建 / 暂存校考档案 · 全科'
                      : `已录校考台账 · ${SCHOOL_SUBJECT_LABELS[subject]}（含全科档案）`
                  }}
                </h3>
                <p class="card-sub">
                  {{
                    scorePickMode === 'create'
                      ? '新建档案不分科目、面向全科，并在 school-exams 下新建档案目录'
                      : '先选定一场学校考试或新建档案，再进入第 2 步上传原卷'
                  }}
                </p>
              </div>
              <div class="card-head-tools">
                <div class="mode-switch" role="group" aria-label="台账与建档切换">
                  <button
                    type="button"
                    :class="['mode-switch-btn', scorePickMode === 'list' ? 'active' : '']"
                    @click="scorePickMode = 'list'"
                  >
                    已录校考台账 ({{ exams?.length ?? 0 }})
                  </button>
                  <button
                    type="button"
                    :class="['mode-switch-btn', scorePickMode === 'create' ? 'active' : '']"
                    @click="scorePickMode = 'create'"
                  >
                    ＋ 新建 / 暂存档案
                  </button>
                </div>
                <HelpBubble v-if="scorePickMode === 'create'" compact title="校考建档口径" label="建档说明">
                  <p>{{ EXAM_NOTE }} 新建档案不分科目面向全科，自动在 school-exams 下建立专属档案目录。</p>
                </HelpBubble>
              </div>
            </div>

            <template v-if="scorePickMode === 'list'">
              <p v-if="exams === null" class="muted">已录入考试加载中…</p>
              <div v-else-if="exams.length === 0" class="muted">
                <p>当前还没有录入过学校考试记录，点击右上角「＋ 新建 / 暂存档案」登记首场校考。</p>
                <button type="button" class="primary small" @click="scorePickMode = 'create'">
                  ＋ 新建首场校考档案
                </button>
              </div>
              <template v-else>
                <ul class="exam-list" tabindex="0" aria-label="已录校考场次列表">
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
                      <span class="exam-title">
                        {{ exam.title }}
                        <span v-if="exam.subject === 'all'" class="chip subtle" style="margin-left: 6px;">全科</span>
                      </span>
                      <span class="muted tiny">
                        {{ fmtExamMonth(exam.exam_date) }} · <b>{{ fmtPoints(exam.earned_points) }} / {{ fmtPoints(exam.max_points) }}</b>
                      </span>
                    </button>
                    <span :class="['chip', exam.confirmed_by_user ? 'good' : 'wait']">
                      {{ exam.confirmed_by_user ? '已核对' : '未核对' }}
                    </span>
                    <button
                      type="button"
                      class="ghost small"
                      @click="selectExamAndAdvance(exam.id)"
                    >
                      提交考试信息
                    </button>
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

                <div v-if="selectedDetail" class="card-footer-flow">
                  <span class="muted tiny">已选中「{{ selectedDetail.title }}」</span>
                  <button type="button" class="primary small" @click="scoreStep = 'upload'">
                    下一步：2. 上传原卷 →
                  </button>
                </div>
              </template>
            </template>

            <template v-else>
              <div class="exam-create-grid">
                <label class="wide">
                  考试名称
                  <input v-model="examTitle" placeholder="如：九年级十月统一练习" />
                </label>
                <label>
                  考试日期
                  <input type="month" v-model="examDate" />
                </label>
              </div>
              <div class="card-footer-flow">
                <button
                  v-if="exams && exams.length > 0"
                  type="button"
                  class="ghost small"
                  @click="scorePickMode = 'list'"
                >
                  ← 返回已录校考台账
                </button>
                <span v-else />
                <button type="button" class="primary" @click="saveExam" :disabled="savingExam">
                  {{ savingExam ? '保存中…' : '提交考试信息并建档' }}
                </button>
              </div>
            </template>
          </section>
        </template>

        <template #step-upload>
          <section v-if="selectedDetail" class="card" aria-label="上传原卷">
            <div class="card-head">
              <div>
                <h3>上传原卷</h3>
                <p class="card-sub">支持 PDF / DOCX / PNG / JPG 格式（单份不超过 35 MiB），保存至档案目录下 exam-paper/</p>
              </div>
              <HelpBubble compact title="原卷加密与隐私隔离" label="隔离说明">
                <p>私人校卷原卷保存在对应档案的 exam-paper 私有目录中，不提供公开下载入口，绝不进入公共题库。</p>
              </HelpBubble>
            </div>
            <label for="school-paper-input">
              选择原卷文件（不超过 35 MiB）
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
                {{ uploadingPaper ? '上传中…' : '上传原卷' }}
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

            <div class="exam-detail" style="margin-top: 14px; padding-top: 12px; border-top: 1px dashed var(--line);" aria-label="已归档原卷列表">
              <div class="card-head">
                <span class="field-label" style="margin: 0;">已归档原卷与附件（{{ selectedDetail.attachments.length }}）</span>
                <span class="chip good">原件校验已隔离</span>
              </div>
              <p v-if="selectedDetail.attachments.length === 0" class="muted tiny" style="margin-top: 6px;">
                还没有上传原卷附件。
              </p>
              <ul v-else class="attachment-list" tabindex="0" aria-label="已归档原卷列表">
                <li v-for="att in selectedDetail.attachments" :key="att.id" class="attachment-row">
                  <div class="attachment-main">
                    <b>{{ att.filename }}</b>
                    <span class="chip good">{{ att.category === 'answer_sheet' ? 'answer-sheet' : 'exam-paper' }}</span>
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

            <div class="card-footer-flow">
              <button type="button" class="ghost small" @click="scoreStep = 'pick'">
                ← 上一步：选定或新建校考档案
              </button>
              <button type="button" class="primary small" @click="scoreStep = 'sync'">
                下一步：3. 全科校考同步 →
              </button>
            </div>
          </section>
        </template>

        <template #step-sync>
          <section class="card" aria-label="全科校考同步">
            <div class="card-head">
              <div>
                <h3>全科校考同步</h3>
                <p class="card-sub">从 k12100 或本地收件箱同步全科成绩与明细，答题卡自动存放于档案目录 answer-sheet/</p>
              </div>
            </div>
            <SchoolExamSyncCenter
              :client="client"
              :subject="subject"
              :notify="notify"
              :selected-exam-id="selectedExamId"
              @open-exam="openExamFromSync"
              @papers-imported="handleSyncPapersImported"
            />
            <div class="card-footer-flow" style="margin-top: 12px;">
              <button type="button" class="ghost small" @click="scoreStep = 'upload'">
                ← 上一步：上传原卷
              </button>
              <button type="button" class="primary small" @click="enterPapersStage">
                下一步：进入第二阶段 · 明细提取与核对 →
              </button>
            </div>
          </section>
        </template>
      </StepFlowWorkspace>
    </div>

    <!-- 第二阶段（入口 3）：原卷与明细核对（单卡三步：1. 上传私有原卷与答题卡 → 2. 自动提取待核对明细 → 3. 逐题明细核对台） -->
    <div
      v-else-if="activeTab === 'papers'"
      id="exam-panel-papers"
      role="tabpanel"
      aria-labelledby="exam-tab-papers"
    >
      <StepFlowWorkspace
        :model-value="paperStep"
        :steps="paperSteps"
        :context="examContext"
        steps-aria-label="原卷与明细核对步骤"
        @update:model-value="id => (paperStep = id as PaperStepId)"
      >
        <template #context-actions>
          <div v-if="exams && exams.length > 1" class="active-exam-switcher">
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
          <button type="button" class="ghost small" @click="activeTab = 'scores'">
            ← 回第一阶段选场次
          </button>
        </template>

        <template #locked="{ step }">
          <section class="card" aria-label="私有原卷与答题卡">
            <div class="card-head">
              <h3>{{ step.title }}</h3>
              <span class="chip wait">前置未就绪</span>
            </div>
            <p class="muted">{{ step.lockReason || '请先完成前置步骤。' }}</p>
            <div class="card-footer-flow">
              <button
                v-if="!selectedDetail"
                type="button"
                class="primary small"
                @click="activeTab = 'scores'"
              >
                ← 前往第一阶段选定校考
              </button>
              <template v-else-if="step.id === 'parse'">
                <button type="button" class="primary small" @click="activeTab = 'scores'; scoreStep = 'upload'">
                  ← 前往第一阶段第 2 步上传原卷
                </button>
                <button
                  v-if="unconfirmedDrafts.length > 0"
                  type="button"
                  class="ghost small"
                  @click="paperStep = 'drafts'"
                >
                  前往第 2 步核对明细 →
                </button>
              </template>
              <template v-else>
                <button
                  type="button"
                  class="primary small"
                  @click="parseableAttachments.length > 0 ? (paperStep = 'parse') : (activeTab = 'scores', scoreStep = 'upload')"
                >
                  ← {{ parseableAttachments.length > 0 ? '前往第 1 步提取待核对明细' : '前往第一阶段第 2 步上传原卷' }}
                </button>
                <button type="button" class="ghost small" @click="activeTab = 'scores'; scoreStep = 'sync'">
                  去「全科校考同步」同步考试与明细
                </button>
              </template>
            </div>
          </section>
        </template>

        <template #step-parse>
          <section v-if="selectedDetail" class="card" aria-label="自动提取待核对明细">
            <div class="card-head">
              <div>
                <h3>从原卷/答题卡自动提取待核对明细</h3>
                <p class="card-sub">
                  抽取题号、分值、候选考点与失分线索，所有结果均为待核对明细
                </p>
              </div>
              <span class="chip wait">未确认不进画像</span>
            </div>

            <div class="parse-attach-toolbar">
              <span class="field-label" style="margin: 0;">
                勾选参与本次解析的附件（支持多份联合识别，已选 {{ selectedParseAttachmentIds.length }} / {{ parseableAttachments.length }}）
              </span>
              <label v-if="parseableAttachments.length > 0" class="parse-select-all">
                <input
                  type="checkbox"
                  :checked="allParseAttachmentsSelected"
                  @change="toggleSelectAllParseAttachments"
                />
                <span>{{ allParseAttachmentsSelected ? '取消全选' : '全选' }}</span>
              </label>
            </div>
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
                提取方式
                <select v-model="parseMode" class="parse-mode-select" aria-label="待核对明细提取方式">
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
                重生成时清理本场尚未人工确认的旧待核对明细（已人工确认题目永久锁定，绝不覆盖）
              </label>
            </div>

            <div class="attachment-actions">
              <p v-if="parseMode === 'auto' && !hasAnswerCard" class="muted tiny">
                提示：未检测到命名含「答题卡/答题纸」的附件；若仅上传了空白原卷，建议选择「仅本地提取题号与分值骨架」或先在「第一阶段第 3 步 · 全科校考同步」同步答题卡与逐题明细。
              </p>
              <button
                type="button"
                class="primary"
                :disabled="parsingDrafts || selectedParseAttachmentIds.length === 0"
                @click="runParseDrafts"
              >
                {{ parsingDrafts ? '提取中…' : '生成待核对明细' }}
              </button>
              <span v-if="lastParseSummary" class="chip good">{{ lastParseSummary }}</span>
            </div>
            <div v-if="parsingDrafts" class="exam-sync-progress" aria-live="polite" style="margin-top: 10px;">
              <div class="exam-sync-progress-head">
                <b>{{ parseStageText }}</b>
                <span class="muted tiny">{{ parseProgress }}%</span>
              </div>
              <div
                class="exam-sync-progress-bar"
                role="progressbar"
                :aria-valuenow="parseProgress"
                aria-valuemin="0"
                aria-valuemax="100"
                aria-label="待核对明细提取进度"
              >
                <span class="exam-sync-progress-fill" :style="{ width: `${parseProgress}%` }"></span>
              </div>
            </div>
            <p v-if="parseDraftError" class="form-error">{{ parseDraftError }}</p>

            <div class="card-footer-flow">
              <button type="button" class="ghost small" @click="activeTab = 'scores'; scoreStep = 'upload'">
                ← 返回第一阶段第 2 步 · 上传原卷
              </button>
              <button
                v-if="unconfirmedDrafts.length > 0 || confirmedItems.length > 0"
                type="button"
                class="primary small"
                @click="paperStep = 'drafts'"
              >
                前往第 2 步 · 逐题明细核对台 →
              </button>
            </div>
          </section>
        </template>

        <template #step-drafts>
          <section v-if="selectedDetail" class="card" aria-label="逐题明细核对台">
            <div class="card-head">
              <div>
                <h3>逐题明细核对台（未确认前不进能力画像）</h3>
                <p class="card-sub">
                  所有分值已锁定只读；请核对所属知识点（及失分题错因），点击「确认入账」或批量确认后生效
                </p>
              </div>
              <div class="card-head-tools">
                <HelpBubble compact tone="caution" title="明细核对红线说明" label="校对口径">
                  <p>所有自动识别与同步入库的逐题结果均锁定为「待核对明细」，绝不直接修改知识点掌握状态或错误分析，须人工逐条核对或批量确认后方能入账；确认后分数与知识点永久锁定。</p>
                </HelpBubble>
                <span v-if="unconfirmedDrafts.length > 0" class="chip wait">待核对 {{ unconfirmedDrafts.length }} 题</span>
              </div>
            </div>

            <template v-if="unconfirmedDrafts.length > 0">
              <!-- 顶部只读分值对账与统计条 -->
              <div class="draft-summary-bar" role="region" aria-label="小题分值只读汇总">
                <div class="draft-summary-main">
                  <span>
                    小题汇总（已核 + 待核）：<b>{{ fmtPoints(scoreSummary.totalEarned) }} / {{ fmtPoints(scoreSummary.totalMax) }} 分</b>
                  </span>
                  <span v-if="scoreSummary.earnedDiff !== null" :class="['chip', scoreSummary.earnedDiff === 0 ? 'good' : 'wait']">
                    {{
                      scoreSummary.earnedDiff === 0
                        ? `与卷面总分（${fmtPoints(selectedDetail.earned_points)} 分）完全吻合 ✓`
                        : `与卷面总分差 ${scoreSummary.earnedDiff > 0 ? '+' : ''}${fmtPoints(scoreSummary.earnedDiff)} 分`
                    }}
                  </span>
                  <span v-else class="chip subtle">
                    卷面总分待核对（参考 {{ fmtPoints(selectedDetail.earned_points) }} / {{ fmtPoints(selectedDetail.max_points) }} 分）
                  </span>
                </div>
                <div class="draft-summary-counts muted tiny">
                  <span>满分作答正确 {{ scoreSummary.correctPendingCount }} 题</span>
                  <span>·</span>
                  <span>失分待归因 {{ scoreSummary.lostPendingCount }} 题</span>
                  <span>·</span>
                  <span>已填考点 {{ readyDrafts.length }} / {{ unconfirmedDrafts.length }} 题</span>
                </div>
              </div>

              <!-- 状态筛选与快捷填充工具条 -->
              <div class="draft-toolbar">
                <div class="draft-filter-pills" role="group" aria-label="按核对状态筛选题目">
                  <button
                    type="button"
                    :class="['chip-btn', draftFilter === 'all' ? 'selected' : '']"
                    @click="draftFilter = 'all'"
                  >
                    全部 ({{ draftFilterCounts.all }})
                  </button>
                  <button
                    type="button"
                    :class="['chip-btn', draftFilter === 'unmapped' ? 'selected' : '']"
                    @click="draftFilter = 'unmapped'"
                  >
                    待补考点 ({{ draftFilterCounts.unmapped }})
                  </button>
                  <button
                    type="button"
                    :class="['chip-btn', draftFilter === 'lost' ? 'selected' : '']"
                    @click="draftFilter = 'lost'"
                  >
                    失分题 ({{ draftFilterCounts.lost }})
                  </button>
                  <button
                    type="button"
                    :class="['chip-btn', draftFilter === 'correct' ? 'selected' : '']"
                    @click="draftFilter = 'correct'"
                  >
                    满分正确 ({{ draftFilterCounts.correct }})
                  </button>
                  <button
                    type="button"
                    :class="['chip-btn', draftFilter === 'ready' ? 'selected' : '']"
                    @click="draftFilter = 'ready'"
                  >
                    已就绪 ({{ draftFilterCounts.ready }})
                  </button>
                </div>
                <div class="draft-toolbar-actions">
                  <button
                    type="button"
                    class="ghost small"
                    :disabled="autoAssociatingDrafts || batchConfirming"
                    @click="runAutoAssociateDrafts({ overwrite: false })"
                  >
                    {{ autoAssociatingDrafts ? '正在匹配候选…' : '智能补全关联' }}
                  </button>
                  <button
                    v-if="hasCandidateSuggestions"
                    type="button"
                    class="ghost small"
                    @click="applyAllTopCandidates"
                  >
                    {{ subject === 'ethics' ? '未填项设为默认主题' : '一键采纳首选候选考点' }}
                  </button>
                </div>
              </div>

              <p v-if="filteredDrafts.length === 0" class="muted" style="margin: 10px 0;">
                当前筛选条件下暂无待核对明细，可切换「全部」查看。
              </p>

              <!-- 方案三：三栏纵向堆叠卡（每卡全宽单列堆叠、分数只读、满分题不展示错因与复盘备注） -->
              <ul v-else ref="draftListRef" class="draft-card-list" tabindex="0" aria-label="待核对明细逐题列表">
                <li
                  v-for="it in filteredDrafts"
                  :key="it.id"
                  :data-draft-item-id="it.id"
                  :class="[
                    'draft-card-item',
                    isSchoolItemFullScore(it.earned_points, it.max_points) ? 'is-correct' : 'is-lost',
                    draftErrorItemId === it.id ? 'has-error' : '',
                  ]"
                >
                  <div class="draft-card-head">
                    <b>{{ formatQuestionLabelHeading(it.question_label) }}</b>
                    <span
                      :class="['chip', DRAFT_CONFIDENCE_META[it.draft_confidence ?? '']?.tone ?? 'wait']"
                    >
                      {{ DRAFT_CONFIDENCE_META[it.draft_confidence ?? '']?.label ?? '待核对明细' }}
                    </span>
                    <span class="chip wait">未确认 · 不进画像</span>
                  </div>

                  <!-- 所有分数只读不可编辑 -->
                  <div
                    :class="[
                      'draft-score-banner',
                      isSchoolItemFullScore(it.earned_points, it.max_points) ? 'ok' : 'lost',
                    ]"
                    :aria-label="`${formatQuestionLabelHeading(it.question_label)} 只读分值：实得 ${fmtPoints(it.earned_points)} / 满分 ${fmtPoints(it.max_points)} 分`"
                  >
                    <span>实得 {{ fmtPoints(it.earned_points) }} / 满分 {{ fmtPoints(it.max_points) }} 分</span>
                    <span>
                      {{
                        isSchoolItemFullScore(it.earned_points, it.max_points)
                          ? '✓ 作答正确'
                          : `✗ 失 ${fmtPoints(it.max_points - it.earned_points)} 分`
                      }}
                    </span>
                  </div>

                  <!-- 方式一：结构化识别依据微标签 -->
                  <div
                    v-if="parseDraftBasisTags(it.draft_reason, it.draft_confidence).length"
                    class="draft-basis-tags"
                    aria-label="识别依据"
                  >
                    <span
                      v-for="tag in parseDraftBasisTags(it.draft_reason, it.draft_confidence)"
                      :key="`${tag.kind}-${tag.label}`"
                      :class="['draft-basis-tag', `is-${tag.kind}`]"
                      :title="it.draft_reason || tag.label"
                    >
                      {{ tag.label }}
                    </span>
                  </div>

                  <!-- 方式一：每题必显 Top-3 候选考点芯片行 -->
                  <div class="candidate-block" aria-label="候选考点">
                    <span class="candidate-block-label">候选考点（点击直选）：</span>
                    <div v-if="it.draft_knowledge_candidates?.length" class="candidate-chip-row">
                      <button
                        v-for="(cand, cIdx) in it.draft_knowledge_candidates"
                        :key="cand.knowledge_id"
                        type="button"
                        :title="cand.reason"
                        :class="[
                          'candidate-chip-btn',
                          resolveDraftKnowledgeCode(it, draftEdits[it.id]?.knowledgeId ?? '') === cand.knowledge_id ? 'active' : '',
                        ]"
                        @click="applyCandidateKnowledge(it.id, cand.knowledge_id, cand.title)"
                      >
                        <span class="cand-rank">{{ ['①', '②', '③'][cIdx] || `${cIdx + 1}.` }}</span>
                        <span>{{ cand.title || getKnowledgeLabel(cand.knowledge_id) }}</span>
                        <span
                          v-if="resolveDraftKnowledgeCode(it, draftEdits[it.id]?.knowledgeId ?? '') === cand.knowledge_id"
                          class="cand-check"
                          aria-hidden="true"
                        >
                          ✓
                        </span>
                      </button>
                    </div>
                    <div v-else class="muted tiny">
                      {{ autoAssociatingDrafts ? '正在匹配 Top-3 候选考点…' : '暂无候选，可点上方「智能补全关联」或直接输入' }}
                    </div>
                  </div>

                  <div v-if="draftEdits[it.id]" class="draft-stack-fields">
                    <div class="draft-field-stack">
                      <div class="draft-field-label-row">
                        <label :for="`draft-kid-${it.id}`">所属知识点（必填）</label>
                        <div class="draft-field-label-tools">
                          <span v-if="isDraftKnowledgeReady(it)" class="draft-auto-tag">已自动关联</span>
                          <button
                            v-if="findPrevReadyKnowledge(it.id)"
                            type="button"
                            class="link-btn"
                            @click="copyPrevDraftKnowledge(it.id)"
                          >
                            同上题
                          </button>
                        </div>
                      </div>
                      <input
                        :id="`draft-kid-${it.id}`"
                        data-knowledge-input
                        v-model="draftEdits[it.id].knowledgeId"
                        :list="`school-exam-knowledge-list-${subject}`"
                        :class="{ 'input-auto-linked': isDraftKnowledgeReady(it) }"
                        :aria-label="`${formatQuestionLabelHeading(it.question_label)} 所属知识点`"
                        placeholder="点击选择或输入所属知识点中文名…"
                        @input="draftErrorItemId === it.id && (draftErrorItemId = null)"
                      />
                      <small v-if="resolveDraftKnowledgeHint(it, draftEdits[it.id].knowledgeId)" class="draft-knowledge-hint">
                        {{ resolveDraftKnowledgeHint(it, draftEdits[it.id].knowledgeId) }}
                      </small>
                    </div>

                    <!-- 仅核对分数与考点；失分题确认后推送学生端完成错因分类与防敷衍复盘 -->
                    <p v-if="!isSchoolItemFullScore(it.earned_points, it.max_points)" class="draft-lost-student-hint">
                      失分题确认入账后，将推送至学生端「校考复盘」由学生本人归因与复盘
                    </p>
                    <p v-else class="draft-correct-hint">
                      ✓ 实得分与满分一致（作答正确），无需复盘
                    </p>
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
                      {{ discardingItemId === it.id ? '移除中…' : '移除待核项' }}
                    </button>
                  </div>
                </li>
              </ul>

              <div class="draft-card-foot">
                <span class="muted tiny">
                  共 {{ unconfirmedDrafts.length }} 题待核对（已填妥考点 {{ readyDrafts.length }} 题），批量确认整批原子提交
                </span>
                <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                  <button
                    v-if="readyDrafts.length > 0 && readyDrafts.length < unconfirmedDrafts.length"
                    type="button"
                    class="ghost"
                    :disabled="batchConfirming || confirmingItemId !== null || discardingItemId !== null"
                    @click="confirmReadyDraftsBatch"
                  >
                    {{ batchConfirming ? '确认中…' : `先确认已就绪项 (${readyDrafts.length} 题)` }}
                  </button>
                  <button
                    type="button"
                    class="primary"
                    :disabled="batchConfirming || confirmingItemId !== null || discardingItemId !== null"
                    @click="confirmAllDraftsBatch"
                  >
                    {{ batchConfirming ? '批量确认中…' : '批量确认本页待核明细' }}
                  </button>
                </div>
              </div>
            </template>
            <div v-else>
              <p class="muted">
                当前场次暂无待核对明细：可返回上传或提取原卷，或进入「第三阶段 · 已核对明细与补录」查看或手工录入小题。
              </p>
            </div>

            <div class="card-footer-flow">
              <button
                type="button"
                class="ghost small"
                @click="parseableAttachments.length > 0 ? (paperStep = 'parse') : (activeTab = 'scores', scoreStep = 'upload')"
              >
                ← {{ parseableAttachments.length > 0 ? '返回第 1 步 · 重新解析' : '前往第一阶段第 2 步 · 上传原卷' }}
              </button>
              <button type="button" class="primary small" @click="activeTab = 'items'">
                前往第三阶段 · 已核对明细与补录 →
              </button>
            </div>
          </section>
        </template>
      </StepFlowWorkspace>
    </div>

    <!-- 第三阶段 · 明细查漏：已核对明细与补录（单卡两步：1. 已核对逐题明细与复盘 → 2. 人工补录已核对小题） -->
    <div
      v-else-if="activeTab === 'items'"
      id="exam-panel-items"
      role="tabpanel"
      aria-labelledby="exam-tab-items"
    >
      <StepFlowWorkspace
        :model-value="itemStep"
        :steps="itemSteps"
        :context="examContext"
        steps-aria-label="逐题明细与补录步骤"
        @update:model-value="id => (itemStep = id as ItemStepId)"
      >
        <template #context-actions>
          <div v-if="exams && exams.length > 1" class="active-exam-switcher">
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
        </template>

        <template #locked="{ step }">
          <section class="card" aria-label="逐题得分与考点明细">
            <div class="card-head">
              <h3>已核对明细与补录</h3>
              <span class="chip wait">前置未就绪</span>
            </div>
            <p class="muted">{{ step.lockReason || '当前尚未选定学校考试，请先在「总分台账与建档」选定或新建场次。' }}</p>
            <div class="card-footer-flow">
              <button type="button" class="primary small" @click="activeTab = 'scores'">
                ← 前往第一阶段选定校考
              </button>
            </div>
          </section>
        </template>

        <template #step-list>
          <section v-if="selectedDetail" class="card" aria-label="逐题得分与考点明细">
            <div v-if="stageSubjectTabs.length > 0" class="exam-sync-subject-tabs" role="tablist" aria-label="明细查漏科目切换">
              <button
                v-for="tab in stageSubjectTabs"
                :key="tab.subject"
                type="button"
                role="tab"
                :aria-selected="stageSubjectFilter === tab.subject"
                :class="['exam-sync-subject-tab', { active: stageSubjectFilter === tab.subject }]"
                @click="selectStageSubject(tab.subject)"
              >
                <span>{{ tab.label }}</span>
                <span class="chip tiny subtle">{{ tab.count }}</span>
              </button>
            </div>
            <div class="card-head">
              <div>
                <h3>已核对逐题得分与考点明细（{{ confirmedItems.length }}）</h3>
                <p class="card-sub">
                  {{
                    stageSubjectFilter === 'ethics'
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
                  @click="activeTab = 'papers'; paperStep = 'drafts'"
                >
                  待核对明细 ({{ unconfirmedDrafts.length }}) →
                </button>
                <span class="chip">{{ stageSubjectFilter === 'ethics' ? '道法 · 校考复盘档案' : '细粒度证据' }}</span>
              </div>
            </div>
            <p v-if="confirmedItems.length === 0" class="muted">
              {{
                unconfirmedDrafts.length > 0
                  ? '当前题目均在「原卷与明细核对」等待人工确认；确认后将在此显示并生成分析结果。'
                  : '还没有录入已确认的逐题得分明细，可点击下方「第 2 步 · 人工补录小题」手工补充。'
              }}
            </p>
            <ul v-else class="attachment-list" tabindex="0" aria-label="已确认逐题得分明细列表">
              <li v-for="it in confirmedItems" :key="it.id" class="attachment-row">
                <div class="attachment-main">
                  <b>{{ formatQuestionLabelHeading(it.question_label) }}</b>
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
                  <span
                    v-if="it.earned_points < it.max_points"
                    :class="[
                      'chip',
                      it.reflection_status === 'completed'
                        ? 'good'
                        : it.reflection_status === 'needs_revision'
                          ? 'bad'
                          : 'wait',
                    ]"
                  >
                    {{
                      it.reflection_status === 'completed'
                        ? '学生已复盘'
                        : it.reflection_status === 'needs_revision'
                          ? '已退回重写'
                          : '待学生复盘'
                    }}
                  </span>
                  <span class="chip good">已确认</span>
                </div>
              </li>
            </ul>

            <div class="card-footer-flow">
              <button type="button" class="ghost small" @click="itemStep = 'add'">
                ＋ 第 2 步：人工补录已核对小题
              </button>
              <button type="button" class="primary small" @click="activeTab = 'analysis'">
                前往第四阶段 · 错误分析与复盘 →
              </button>
            </div>
          </section>
        </template>

        <template #step-add>
          <section v-if="selectedDetail" class="card" aria-label="人工补录已核对小题">
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
              <p v-if="isNewItemLost" class="muted tiny" style="grid-column: 1 / -1; margin: 0;">
                本小题未拿满分，录入后将自动进入学生端「校考复盘」由学生本人归因与填写复盘。
              </p>
            </div>

            <div class="card-footer-flow">
              <button type="button" class="ghost small" @click="itemStep = 'list'">
                ← 返回第 1 步 · 已核对明细列表
              </button>
              <button type="button" class="primary" @click="addItem" :disabled="savingItem">
                {{ savingItem ? '录入中…' : '录入已核对小题' }}
              </button>
            </div>
          </section>
        </template>
      </StepFlowWorkspace>
    </div>

    <!-- 第四阶段 · 诊断终点：错误分析与复盘（单卡三步：1. 失分概览与错因分布 → 2. 失分考点排行与交叉诊断 → 3. 同科历次顽固失分点对比） -->
    <div
      v-else-if="activeTab === 'analysis'"
      id="exam-panel-analysis"
      role="tabpanel"
      aria-labelledby="exam-tab-analysis"
    >
      <StepFlowWorkspace
        :model-value="analysisStep"
        :steps="analysisSteps"
        :context="examContext"
        steps-aria-label="错误分析与复盘步骤"
        @update:model-value="id => (analysisStep = id as AnalysisStepId)"
      >
        <template #context-actions>
          <div v-if="exams && exams.length > 1" class="active-exam-switcher">
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
        </template>

        <template #locked>
          <section v-if="!selectedDetail || !errorAnalysis" class="card" aria-label="错误分析与复盘">
            <div class="card-head">
              <h3>错误分析与复盘</h3>
              <span class="chip wait">前置未就绪</span>
            </div>
            <p class="muted">
              {{ loadingDetail ? '正在加载错误分析数据…' : '当前尚未选定学校考试，请先在「总分台账与建档」选定或新建场次。' }}
            </p>
            <div v-if="!loadingDetail" class="card-footer-flow">
              <button type="button" class="primary small" @click="activeTab = 'scores'">
                ← 前往第一阶段选定校考
              </button>
            </div>
          </section>

          <section v-else class="card" aria-label="错误分析数据状态说明">
            <div v-if="stageSubjectTabs.length > 0" class="exam-sync-subject-tabs" role="tablist" aria-label="诊断终点科目切换">
              <button
                v-for="tab in stageSubjectTabs"
                :key="tab.subject"
                type="button"
                role="tab"
                :aria-selected="stageSubjectFilter === tab.subject"
                :class="['exam-sync-subject-tab', { active: stageSubjectFilter === tab.subject }]"
                @click="selectStageSubject(tab.subject)"
              >
                <span>{{ tab.label }}</span>
                <span class="chip tiny subtle">{{ tab.count }}</span>
              </button>
            </div>
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
                <span>待核对明细</span>
              </div>
            </div>
            <div class="card-footer-flow">
              <button type="button" class="ghost small" @click="activeTab = 'papers'">
                查看原卷与明细核对
              </button>
              <button type="button" class="primary" @click="goAnalysisAddItems">
                前往补录失分小题
              </button>
            </div>
          </section>
        </template>

        <template #step-overview>
          <section v-if="errorAnalysis" class="card" aria-label="本场失分概览与错因分布">
            <div v-if="stageSubjectTabs.length > 0" class="exam-sync-subject-tabs" role="tablist" aria-label="诊断终点科目切换">
              <button
                v-for="tab in stageSubjectTabs"
                :key="tab.subject"
                type="button"
                role="tab"
                :aria-selected="stageSubjectFilter === tab.subject"
                :class="['exam-sync-subject-tab', { active: stageSubjectFilter === tab.subject }]"
                @click="selectStageSubject(tab.subject)"
              >
                <span>{{ tab.label }}</span>
                <span class="chip tiny subtle">{{ tab.count }}</span>
              </button>
            </div>
            <div class="card-head">
              <div>
                <h3>本场失分概览与错因分布</h3>
                <p class="card-sub">{{ errorAnalysis.diagnosis_summary }}</p>
              </div>
              <div class="card-head-tools">
                <HelpBubble compact title="统计范围说明" label="口径说明">
                  <p>仅汇总已人工核对的逐题失分；未单独归类的失分小题保持如实标示。</p>
                  <p v-if="errorAnalysis.overview.unconfirmed_draft_count > 0">
                    另有 {{ errorAnalysis.overview.unconfirmed_draft_count }} 条自动提取待核对明细，确认后自动纳入统计。
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
                另有 {{ errorAnalysis.overview.unconfirmed_draft_count }} 条明细待核对
              </span>
              <button type="button" class="ghost small" @click="activeTab = 'papers'; paperStep = 'drafts'">
                去逐题核对
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
                    @click="activeTab = 'items'; itemStep = 'list'"
                  >
                    前往补充错因标注
                  </button>
                </div>
              </li>
            </ul>

            <div class="card-footer-flow">
              <button type="button" class="ghost small" @click="activeTab = 'items'; itemStep = 'list'">
                ← 回第三阶段修改错因标注
              </button>
              <button type="button" class="primary small" @click="analysisStep = 'knowledge'">
                下一步：失分考点排行与交叉诊断 →
              </button>
            </div>
          </section>
        </template>

        <template #step-knowledge>
          <section v-if="errorAnalysis" class="card" aria-label="本场失分考点排行与交叉诊断">
            <div v-if="stageSubjectTabs.length > 0" class="exam-sync-subject-tabs" role="tablist" aria-label="诊断终点科目切换">
              <button
                v-for="tab in stageSubjectTabs"
                :key="tab.subject"
                type="button"
                role="tab"
                :aria-selected="stageSubjectFilter === tab.subject"
                :class="['exam-sync-subject-tab', { active: stageSubjectFilter === tab.subject }]"
                @click="selectStageSubject(tab.subject)"
              >
                <span>{{ tab.label }}</span>
                <span class="chip tiny subtle">{{ tab.count }}</span>
              </button>
            </div>
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
                    查看复盘与题干
                  </button>
                </div>
                <p v-if="li.error_note" class="item-error-note">
                  复盘备注：{{ li.error_note }}
                </p>
              </li>
            </ul>

            <div class="card-footer-flow">
              <button type="button" class="ghost small" @click="analysisStep = 'overview'">
                ← 上一步：本场失分概览
              </button>
              <button type="button" class="primary small" @click="analysisStep = 'history'">
                下一步：同科历次顽固失分点对比 →
              </button>
            </div>
          </section>
        </template>

        <template #step-history>
          <section v-if="errorAnalysis" class="card" aria-label="同科历次校考顽固失分点对比">
            <div v-if="stageSubjectTabs.length > 0" class="exam-sync-subject-tabs" role="tablist" aria-label="诊断终点科目切换">
              <button
                v-for="tab in stageSubjectTabs"
                :key="tab.subject"
                type="button"
                role="tab"
                :aria-selected="stageSubjectFilter === tab.subject"
                :class="['exam-sync-subject-tab', { active: stageSubjectFilter === tab.subject }]"
                @click="selectStageSubject(tab.subject)"
              >
                <span>{{ tab.label }}</span>
                <span class="chip tiny subtle">{{ tab.count }}</span>
              </button>
            </div>
            <div class="card-head">
              <div>
                <h3>同科历次校考顽固失分点对比</h3>
                <p class="card-sub">
                  自动统计「{{ SCHOOL_SUBJECT_LABELS[stageSubjectFilter] }}」跨 ≥ 2 场已核对校考重复扣分的知识点
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
              当前「{{ SCHOOL_SUBJECT_LABELS[stageSubjectFilter] }}」暂无跨 2 场以上重复失分的考点；连续多次录入逐题明细后，系统将自动识别顽固薄弱环节。
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

            <div class="card-footer-flow">
              <button type="button" class="ghost small" @click="analysisStep = 'knowledge'">
                ← 上一步：失分考点排行诊断
              </button>
              <button type="button" class="primary small" @click="analysisStep = 'reflection'">
                下一步：失分题干与学生复盘 →
              </button>
            </div>
          </section>
        </template>

        <template #step-reflection>
          <section v-if="errorAnalysis && selectedDetail" class="card" aria-label="失分题干与学生复盘">
            <div v-if="stageSubjectTabs.length > 0" class="exam-sync-subject-tabs" role="tablist" aria-label="诊断终点科目切换">
              <button
                v-for="tab in stageSubjectTabs"
                :key="tab.subject"
                type="button"
                role="tab"
                :aria-selected="stageSubjectFilter === tab.subject"
                :class="['exam-sync-subject-tab', { active: stageSubjectFilter === tab.subject }]"
                @click="selectStageSubject(tab.subject)"
              >
                <span>{{ tab.label }}</span>
                <span class="chip tiny subtle">{{ tab.count }}</span>
              </button>
            </div>
            <div class="card-head">
              <div>
                <h3>失分题干与学生复盘</h3>
                <p class="card-sub">
                  集中抽取并确认失分题原题与学生作答（逐题仅 AI 识别一次），并查看学生复盘或留言退回。
                </p>
              </div>
              <div class="card-head-tools">
                <span class="chip">
                  题干已确认 {{ stemStats.confirmed }} / {{ stemStats.totalLost }}
                </span>
                <button
                  type="button"
                  class="primary small"
                  :disabled="extractingStems || stemStats.allRecognized || lostConfirmedItems.length === 0"
                  @click="extractStems"
                >
                  {{
                    extractingStems
                      ? extractStemProgress || '正在识别…'
                      : stemStats.allRecognized
                        ? '已全部识别'
                        : '提取失分题题干与作答（AI 识别）'
                  }}
                </button>
                <button
                  v-if="stemStats.draft > 0"
                  type="button"
                  class="ghost small"
                  :disabled="confirmingAllStems"
                  @click="confirmAllStems"
                >
                  {{ confirmingAllStems ? '确认中…' : `全部确认题干 (${stemStats.draft})` }}
                </button>
              </div>
            </div>

            <div
              v-if="stemExtractStatus"
              :class="[
                'stem-progress-panel',
                stemExtractStatus.errorReason ? 'has-error' : stemExtractStatus.active ? 'is-running' : 'is-done',
              ]"
              aria-live="polite"
            >
              <div class="stem-progress-head">
                <b>
                  {{
                    stemExtractStatus.errorReason
                      ? 'AI 识别中断'
                      : stemExtractStatus.active
                        ? '正在逐批识别失分题题干与作答'
                        : '本轮识别已完成'
                  }}
                </b>
                <span class="muted tiny">
                  {{ stemExtractStatus.done }} / {{ Math.max(stemExtractStatus.total, 1) }} 题
                  ({{ Math.min(100, Math.round((stemExtractStatus.done / Math.max(stemExtractStatus.total, 1)) * 100)) }}%)
                </span>
              </div>
              <div
                class="stem-progress-track"
                role="progressbar"
                :aria-valuenow="stemExtractStatus.done"
                :aria-valuemin="0"
                :aria-valuemax="Math.max(stemExtractStatus.total, 1)"
              >
                <div
                  class="stem-progress-fill"
                  :style="{
                    width: `${Math.min(100, Math.round((stemExtractStatus.done / Math.max(stemExtractStatus.total, 1)) * 100))}%`,
                  }"
                />
              </div>
              <p class="stem-progress-note">{{ stemExtractStatus.note }}</p>
              <p v-if="stemExtractStatus.errorReason" class="stem-progress-error" role="alert">
                失败原因：{{ stemExtractStatus.errorReason }}
              </p>
            </div>

            <p v-if="lostConfirmedItems.length === 0" class="muted">
              当前场次暂无已确认的失分题。
            </p>
            <ul v-else class="attachment-list" tabindex="0" aria-label="失分题干与学生复盘列表">
              <li v-for="it in lostConfirmedItems" :key="it.id" class="attachment-row admin-reflection-item-card">
                <div class="admin-reflection-block-row">
                  <b>{{ formatQuestionLabelHeading(it.question_label) }}</b>
                  <span class="chip bad">失 -{{ fmtPoints(it.max_points - it.earned_points) }} 分</span>
                </div>
                <div class="admin-reflection-block-row">
                  <span class="muted tiny">考点：</span>
                  <span>{{ displayKnowledgeName(it) }}</span>
                </div>
                <div class="admin-reflection-block-row">
                  <span :class="['chip', it.error_category ? 'mid' : 'wait']">
                    {{ getSchoolErrorCategoryLabel(it.error_category) }}
                  </span>
                  <span
                    :class="[
                      'chip',
                      it.reflection_status === 'completed'
                        ? 'good'
                        : it.reflection_status === 'needs_revision'
                          ? 'bad'
                          : 'wait',
                    ]"
                  >
                    {{
                      it.reflection_status === 'completed'
                        ? '学生已复盘'
                        : it.reflection_status === 'needs_revision'
                          ? '已退回重写'
                          : '待学生复盘'
                    }}
                  </span>
                  <span :class="['chip', stemStateLabel(it.stem_state).tone]">
                    {{ stemStateLabel(it.stem_state).text }}
                  </span>
                </div>

                <!-- 学生复盘内容只读区（每类内容独立新行显示） -->
                <div
                  v-if="it.stuck_point || it.fix_strategy || it.error_note || it.return_reason"
                  class="admin-reflection-readonly"
                >
                  <div v-if="it.return_reason" class="admin-reflection-field">
                    <span class="admin-reflection-field-label" style="color: var(--red);">退回重写要求</span>
                    <p class="item-error-note" style="color: var(--red);">{{ it.return_reason }}</p>
                  </div>
                  <div v-if="it.stuck_point" class="admin-reflection-field">
                    <span class="admin-reflection-field-label">失分卡点</span>
                    <p class="item-error-note">{{ it.stuck_point }}</p>
                  </div>
                  <div v-if="it.fix_strategy" class="admin-reflection-field">
                    <span class="admin-reflection-field-label">改进对策</span>
                    <p class="item-error-note">{{ it.fix_strategy }}</p>
                  </div>
                  <div v-else-if="it.error_note && !it.stuck_point" class="admin-reflection-field">
                    <span class="admin-reflection-field-label">复盘备注</span>
                    <p class="item-error-note">{{ it.error_note }}</p>
                  </div>
                </div>

                <!-- 题干与学生作答折叠编辑/确认区 -->
                <div v-if="stemEdits[it.id]" class="stem-editor-box">
                  <div class="attachment-actions" style="display: flex; gap: 8px; flex-wrap: wrap; align-items: center;">
                    <button
                      type="button"
                      class="ghost small"
                      @click="stemEdits[it.id].expanded = !stemEdits[it.id].expanded"
                    >
                      {{ stemEdits[it.id].expanded ? '收起原题与作答' : '编辑 / 确认原题与作答' }}
                    </button>
                    <button
                      v-if="it.reflection_status === 'completed' || it.error_note"
                      type="button"
                      class="ghost small"
                      @click="returningItemId === it.id ? cancelReturnReflection() : startReturnReflection(it)"
                    >
                      {{ returningItemId === it.id ? '收起退回框' : '退回重写' }}
                    </button>
                    <button
                      v-if="(it.coach_turn_count ?? 0) > 0"
                      type="button"
                      class="ghost small"
                      @click="toggleAdminCoachView(it.id)"
                    >
                      {{
                        adminCoachOpenId === it.id
                          ? '收起书童对话'
                          : `查看书童对话过程（${it.coach_turn_count} 条）`
                      }}
                    </button>
                  </div>

                  <div v-if="adminCoachOpenId === it.id" class="admin-coach-readonly" style="margin-top: 8px;">
                    <p v-if="adminCoachLoadingId === it.id" class="muted tiny" style="margin: 0;">
                      正在加载学生与书童的复盘对话记录…
                    </p>
                    <template v-else-if="adminCoachCache[it.id]?.turns.length">
                      <div
                        v-for="t in adminCoachCache[it.id].turns"
                        :key="t.id"
                        :class="['admin-coach-turn', t.role === 'assistant' ? 'is-ai' : 'is-stu']"
                      >
                        <span class="admin-reflection-field-label">
                          {{ t.role === 'assistant' ? '我的书童' : '学生' }}
                        </span>
                        <p class="item-error-note"><RichText :text="t.content" /></p>
                      </div>
                    </template>
                    <p v-else class="muted tiny" style="margin: 0;">暂无对话记录。</p>
                  </div>

                  <div v-if="stemEdits[it.id].expanded" class="inline-analysis-editor" style="margin-top: 8px;">
                    <div class="admin-grid">
                      <label style="grid-column: 1 / -1;">
                        {{ it.question_label }} 原题题干（支持 $...$ 公式）
                        <textarea
                          v-model="stemEdits[it.id].stemText"
                          rows="3"
                          maxlength="800"
                          :aria-label="`${it.question_label} 原题题干`"
                          placeholder="可人工补录或修正原题题干（仅确认后对学生可见）"
                        />
                      </label>
                      <div v-if="stemEdits[it.id].stemText.trim()" class="stem-preview-box" style="grid-column: 1 / -1;">
                        <span class="muted tiny">公式预览：</span>
                        <RichText :text="stemEdits[it.id].stemText" />
                      </div>
                      <label style="grid-column: 1 / -1;">
                        {{ it.question_label }} 学生当时作答（可选）
                        <textarea
                          v-model="stemEdits[it.id].studentAnswerText"
                          rows="2"
                          maxlength="400"
                          :aria-label="`${it.question_label} 学生当时作答`"
                          placeholder="选填：学生在答题卡上的作答过程或答案"
                        />
                      </label>
                    </div>
                    <div style="display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap;">
                      <button
                        type="button"
                        class="primary small"
                        :disabled="stemEdits[it.id].saving"
                        @click="saveItemStem(it, true)"
                      >
                        {{ stemEdits[it.id].saving ? '保存中…' : it.stem_state === 'confirmed' ? '保存修改' : '确认题干' }}
                      </button>
                      <button
                        v-if="it.stem_state !== 'confirmed'"
                        type="button"
                        class="ghost small"
                        :disabled="stemEdits[it.id].saving"
                        @click="saveItemStem(it, false)"
                      >
                        暂存草稿
                      </button>
                    </div>
                  </div>
                </div>

                <!-- 退回重写（家长留言）编辑框 -->
                <div v-if="returningItemId === it.id" class="inline-analysis-editor" style="margin-top: 8px;">
                  <div class="admin-grid">
                    <label style="grid-column: 1 / -1;">
                      退回学生重写原因
                      <input
                        v-model="returnReasonInput"
                        :aria-label="`${it.question_label} 退回重写原因`"
                        maxlength="200"
                        placeholder="说明学生复盘哪里过于笼统、需要补充什么细节"
                      />
                    </label>
                  </div>
                  <div style="display: flex; gap: 8px; margin-top: 8px;">
                    <button
                      type="button"
                      class="primary small"
                      :disabled="returningSaving"
                      @click="submitReturnReflection(it)"
                    >
                      {{ returningSaving ? '退回中…' : '确认退回重写' }}
                    </button>
                    <button type="button" class="ghost small" @click="cancelReturnReflection">
                      取消
                    </button>
                  </div>
                </div>
              </li>
            </ul>

            <div class="card-footer-flow">
              <button type="button" class="ghost small" @click="analysisStep = 'history'">
                ← 上一步：历次顽固失分点
              </button>
            </div>
          </section>
        </template>
      </StepFlowWorkspace>
    </div>
  </section>
</template>
