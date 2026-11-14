<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  describeError,
  SCHOOL_SUBJECT_LABELS,
  type ApiClient,
  type SchoolExam,
  type SchoolExamDetail,
  type SchoolSubject,
} from '../../api'
import { EXAM_NOTE, fmtBytes, fmtPoints, shortTime } from '../../copy'
import { getKnowledgeLabel, getMediaTypeLabel } from '../../config/knowledge'
import type { NoticeTone } from '../Notice.vue'

type Notify = (text: string, tone?: NoticeTone) => void
type ExamTabId = 'scores' | 'papers' | 'items' | 'create'

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
}>()

const exams = ref<SchoolExam[] | null>(null)
const selectedExamId = ref<string | null>(null)
const selectedDetail = ref<SchoolExamDetail | null>(null)
const loadingDetail = ref(false)
const activeTab = ref<ExamTabId>('scores')

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

// 逐题得分补录状态
const itemLabel = ref('')
const itemKnowledgeId = ref('')
const itemEarned = ref<number | ''>('')
const itemMax = ref<number | ''>('')
const savingItem = ref(false)
const confirmingItemId = ref<string | null>(null)

const selectedExamSummary = computed(
  () => exams.value?.find(e => e.id === selectedExamId.value) ?? null
)

// 四类内容 Tab 定义及实时状态/计数徽章
const categoryTabs = computed(() => {
  const listCount = exams.value?.length ?? 0
  const ex = selectedDetail.value ?? selectedExamSummary.value
  const scoreBadge = ex ? (ex.confirmed_by_user ? '已核对' : '待补总分') : `${listCount} 场`
  const paperBadge = selectedDetail.value ? `${selectedDetail.value.attachments.length} 份` : '附件'
  const itemBadge =
    props.subject === 'ethics'
      ? '无图谱'
      : selectedDetail.value
        ? `${selectedDetail.value.items.length} 条`
        : '明细'

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
      sub: props.subject === 'ethics' ? '道法仅档案记录' : 'OCR 核对 · 人工补录明细',
      badge: itemBadge,
      wait: false,
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
})

async function loadDetail(examId: string) {
  loadingDetail.value = true
  try {
    const detail = await props.client.schoolExamDetail(examId)
    selectedDetail.value = detail
    confirmEarned.value = detail.earned_points
  } catch (e) {
    selectedDetail.value = null
    props.notify(describeError(e), 'error')
  } finally {
    loadingDetail.value = false
  }
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
    }
  } catch {
    exams.value = null
    selectedExamId.value = null
    selectedDetail.value = null
  }
}

watch(
  [() => props.client, () => props.subject],
  () => {
    paperFile.value = null
    uploadError.value = ''
    showHelp.value = false
    void refreshExams()
  },
  { immediate: true }
)

async function selectExam(examId: string) {
  selectedExamId.value = examId
  uploadError.value = ''
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
  savingItem.value = true
  try {
    await props.client.addSchoolExamItems(selectedDetail.value.id, [
      {
        question_label: label,
        knowledge_id: kid,
        earned_points: Number(itemEarned.value),
        max_points: Number(itemMax.value),
        scoring_origin: 'manual_entry',
      },
    ])
    props.notify('已录入并确认校考小题得分。', 'success')
    itemLabel.value = ''
    itemEarned.value = ''
    await loadDetail(selectedDetail.value.id)
  } catch (e) {
    props.notify(describeError(e), 'error')
  } finally {
    savingItem.value = false
  }
}

async function confirmDraftItem(itemId: string, earned: number) {
  if (!selectedDetail.value) return
  confirmingItemId.value = itemId
  try {
    await props.client.confirmSchoolExamItem(selectedDetail.value.id, itemId, earned)
    props.notify('OCR 草稿小题得分已人工确认。', 'success')
    await loadDetail(selectedDetail.value.id)
  } catch (e) {
    props.notify(describeError(e), 'error')
  } finally {
    confirmingItemId.value = null
  }
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
        <button type="button" class="ghost small" @click="refreshExams()">
          刷新
        </button>
      </div>
    </div>

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

    <!-- 在原卷/逐题 Tab 下展示当前处理场次快速切换条 -->
    <div
      v-if="(activeTab === 'papers' || activeTab === 'items') && exams && exams.length > 0 && selectedDetail"
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
            <span class="chip good">SHA-256 完整性校验</span>
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
        <section class="card" aria-label="逐题得分与考点明细">
          <div class="card-head">
            <div>
              <h3>逐题得分与考点明细（{{ selectedDetail.items.length }}）</h3>
              <p class="card-sub">
                {{
                  subject === 'ethics'
                    ? '道德与法治（道法）暂未建立课标知识图谱，建议主要通过原卷与总分归档'
                    : '只有人工确认后的逐题明细，才会进入学科能力证据'
                }}
              </p>
            </div>
            <span class="chip">{{ subject === 'ethics' ? '道法 · 仅档案记录' : '细粒度证据' }}</span>
          </div>
          <p v-if="selectedDetail.items.length === 0" class="muted">
            还没有录入逐题得分明细。
          </p>
          <ul v-else class="attachment-list">
            <li v-for="it in selectedDetail.items" :key="it.id" class="attachment-row">
              <div class="attachment-main">
                <b>{{ it.question_label }}</b>
                <span>{{ getKnowledgeLabel(it.knowledge_id) }}</span>
                <span><b>{{ fmtPoints(it.earned_points) }} / {{ fmtPoints(it.max_points) }}</b></span>
                <span :class="['chip', it.confirmed_by_user ? 'good' : 'wait']">
                  {{ it.confirmed_by_user ? '已确认' : 'OCR 草稿待核对' }}
                </span>
              </div>
              <div v-if="!it.confirmed_by_user && it.scoring_origin === 'ocr_draft'" class="attachment-actions">
                <button
                  type="button"
                  class="ghost small"
                  :disabled="confirmingItemId === it.id"
                  @click="confirmDraftItem(it.id, it.earned_points)"
                >
                  {{ confirmingItemId === it.id ? '确认中…' : '人工确认该题得分' }}
                </button>
              </div>
            </li>
          </ul>
        </section>

        <section class="card" aria-label="人工补录已核对小题">
          <div class="card-head">
            <div>
              <h3>人工补录已核对小题</h3>
              <p class="card-sub">对照纸质阅卷结果逐题补充</p>
            </div>
          </div>
          <div class="admin-grid">
            <label>
              题号（如 第1题）
              <input v-model="itemLabel" placeholder="第1题" />
            </label>
            <label>
              知识点编码
              <input v-model="itemKnowledgeId" class="mono-input" placeholder="如 math.eq.quadratic" />
            </label>
            <label>
              小题得分
              <input type="number" min="0" step="0.5" v-model.number="itemEarned" />
            </label>
            <label>
              小题满分
              <input type="number" min="0.5" max="100" step="0.5" v-model.number="itemMax" />
            </label>
          </div>
          <button type="button" class="primary" @click="addItem" :disabled="savingItem">
            {{ savingItem ? '录入中…' : '录入已核对小题' }}
          </button>
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
