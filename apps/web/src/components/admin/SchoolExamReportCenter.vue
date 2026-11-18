<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  describeError,
  type ApiClient,
  type SchoolExamReport,
  type SchoolExamReportAttachment,
  type SchoolSubject,
} from '../../api'
import {
  getReportLinkMatchLabel,
  getReportMatchStateLabel,
  getReportScopeStatusLabel,
  getReportStatusLabel,
  getSubjectLabel,
} from '../../config/knowledge'
import type { NoticeTone } from '../Notice.vue'
import StepFlowWorkspace from './StepFlowWorkspace.vue'
import type { StepDefinition, StepFlowContext } from './stepFlow'

type Notify = (text: string, tone?: NoticeTone) => void
type ReportStepId = 'discover' | 'match' | 'parse' | 'confirm'

const props = defineProps<{
  client: ApiClient
  subject: SchoolSubject
  notify: Notify
}>()

const emit = defineEmits<{
  (e: 'open-scores'): void
  (e: 'open-papers-drafts', examId?: string): void
}>()

const reportStep = ref<ReportStepId>('discover')
const reports = ref<SchoolExamReport[] | null>(null)
const selectedId = ref<string | null>(null)
const loading = ref(false)
const scanning = ref(false)
const matching = ref(false)
const confirming = ref(false)
const savingIdentity = ref(false)
const editGrade = ref('')
const editType = ref('')
const editYear = ref('')
const cardAttachments = ref<SchoolExamReportAttachment[]>([])
const buildingCards = ref(false)
const cardRotation = ref(0)
const previewUrl = ref<string | null>(null)
const previewName = ref('')
const supplementSubject = ref('')
const supplementScore = ref<number | ''>('')
const supplementMax = ref<number | ''>(100)
const supplementClassRank = ref<number | ''>('')
const supplementGradeRank = ref<number | ''>('')
const savingSubject = ref(false)
const generatingDrafts = ref(false)
const draftsGeneratedHere = ref(false)
const matchUnresolved = ref<string[]>([])
const matchAmbiguous = ref<string[]>([])

const selected = computed(() => reports.value?.find(item => item.id === selectedId.value) ?? null)

async function loadCards() {
  if (!selected.value) {
    cardAttachments.value = []
    matchUnresolved.value = []
    matchAmbiguous.value = []
    return
  }
  try {
    cardAttachments.value = await props.client.listSchoolExamReportAnswerCards(selected.value.id)
  } catch {
    cardAttachments.value = []
  }
}

function syncEditIdentity() {
  if (!selected.value) return
  editGrade.value = selected.value.grade ?? ''
  editType.value = selected.value.exam_type ?? ''
  editYear.value = selected.value.academic_year ?? ''
}

watch(
  selected,
  () => {
    draftsGeneratedHere.value = false
    syncEditIdentity()
    void loadCards()
  },
  { immediate: true },
)

const linkedCount = computed(() => selected.value?.linked_exam_ids.length ?? 0)
const questionCount = computed(() => selected.value?.questions.length ?? 0)
const sessionOnlySubjects = computed(
  () => (selected.value?.linked_exam_ids ?? []).filter(link => link.match === 'SESSION_ONLY'),
)
const isMatchReady = computed(
  () => Boolean(selected.value && ['EXACT_MATCH', 'PARTIAL_MATCH'].includes(selected.value.match_state)),
)
const canConfirm = computed(
  () => Boolean(selected.value && isMatchReady.value && selected.value.status !== 'confirmed'),
)

function fmtScore(value: number | null | undefined): string {
  return value === null || value === undefined ? '缺失' : String(value)
}

function scopeTone(status: string): string {
  return status === 'CONSISTENT' ? 'good' : status === 'DIFFERENT_SCOPE_POSSIBLE' ? 'wait' : 'bad'
}

const reportContext = computed<StepFlowContext | null>(() => {
  if (!selected.value) return null
  return {
    eyebrow: '当前报告册',
    title: selected.value.title || selected.value.filename,
    statusText: `${getReportMatchStateLabel(selected.value.match_state)} · ${getReportStatusLabel(selected.value.status)}`,
    statusTone: selected.value.status === 'confirmed' ? 'good' : 'wait',
  }
})

const steps = computed<StepDefinition[]>(() => [
  {
    id: 'discover',
    title: '1. 发现文件',
    subtitle: reports.value ? `${reports.value.length} 份报告册` : '扫描 inbox PDF',
    badge: reports.value ? `${reports.value.length} 份` : undefined,
    done: selected.value !== null,
    prereqMet: true,
  },
  {
    id: 'match',
    title: '2. 关联考试',
    subtitle: selected.value ? getReportMatchStateLabel(selected.value.match_state) : '补录身份并匹配',
    badge: selected.value ? `${linkedCount.value} 科` : undefined,
    badgeTone: isMatchReady.value ? 'good' : 'wait',
    done: isMatchReady.value,
    prereqMet: selected.value !== null,
    lockReason: '请先在第 1 步扫描并选定一份分析报告册。',
  },
  {
    id: 'parse',
    title: '3. 成绩与答题卡',
    subtitle: selected.value ? `${selected.value.pages} 页 · 逐题 ${questionCount.value}` : '核查口径与切图',
    badge: cardAttachments.value.length > 0 ? `${cardAttachments.value.length} 页卡` : undefined,
    done: isMatchReady.value && (selected.value?.status === 'confirmed' || cardAttachments.value.length > 0),
    prereqMet: isMatchReady.value,
    lockReason: '请先在第 2 步完成至少部分学科的校考档案关联（全部或部分匹配），否则无法同步答题卡或成绩。',
  },
  {
    id: 'confirm',
    title: '4. 核对入档',
    subtitle: selected.value?.status === 'confirmed' ? '已人工确认' : '确认并生成待核明细',
    badge: selected.value?.status === 'confirmed' ? '已确认' : '待确认',
    badgeTone: selected.value?.status === 'confirmed' ? 'good' : 'wait',
    done: selected.value?.status === 'confirmed' && draftsGeneratedHere.value,
    prereqMet: isMatchReady.value,
    lockReason: '请先在第 2 步完成校考档案关联后再执行确认入档与生成逐题待核对明细。',
  },
])

async function load(preferId?: string) {
  loading.value = true
  try {
    const rows = await props.client.schoolExamReports()
    reports.value = rows
    selectedId.value =
      (preferId && rows.some(item => item.id === preferId) ? preferId : null) ??
      (selectedId.value && rows.some(item => item.id === selectedId.value) ? selectedId.value : null) ??
      (rows[0]?.id ?? null)
  } catch (error) {
    reports.value = null
    props.notify(describeError(error), 'error')
  } finally {
    loading.value = false
  }
}

async function scan() {
  scanning.value = true
  try {
    const result = await props.client.scanSchoolExamReports()
    await load(result.reports[0]?.id)
    props.notify(`报告扫描完成：发现 ${result.discovered} 份，跳过 ${result.skipped} 份。`, 'success')
  } catch (error) {
    props.notify(describeError(error), 'error')
  } finally {
    scanning.value = false
  }
}

function selectReport(id: string) {
  selectedId.value = id
}

function selectReportAndAdvance(id: string) {
  selectedId.value = id
  reportStep.value = 'match'
}

async function rematch() {
  if (!selected.value) return
  matching.value = true
  try {
    const result = await props.client.matchSchoolExamReport(selected.value.id)
    matchUnresolved.value = result.match.unresolved_subjects
    matchAmbiguous.value = result.match.ambiguous_subjects
    await load(result.report.id)
    props.notify(
      result.match.match_state === 'EXACT_MATCH'
        ? '全部学科已唯一关联，请继续核对成绩并人工确认。'
        : `关联结果：未匹配 ${result.match.unresolved_subjects.length} 科，歧义 ${result.match.ambiguous_subjects.length} 科。`,
      result.match.match_state === 'EXACT_MATCH' ? 'success' : 'caution',
    )
  } catch (error) {
    props.notify(describeError(error), 'error')
  } finally {
    matching.value = false
  }
}

async function buildCards() {
  if (!selected.value) return
  buildingCards.value = true
  try {
    const result = await props.client.buildSchoolExamReportAnswerCards(selected.value.id, Number(cardRotation.value) || 0)
    cardAttachments.value = result.attachments
    props.notify(`已生成 ${result.created} 页答题卡私有附件。`, 'success')
  } catch (error) {
    props.notify(describeError(error), 'error')
  } finally {
    buildingCards.value = false
  }
}

async function previewCard(attachment: SchoolExamReportAttachment) {
  if (!selected.value) return
  try {
    let target = attachment
    const desiredRotation = Number(cardRotation.value) || 0
    if (target.rotation !== desiredRotation) {
      const updated = await props.client.buildSchoolExamReportAnswerCards(selected.value.id, desiredRotation)
      cardAttachments.value = updated.attachments
      target = updated.attachments.find(item => item.id === attachment.id) ?? target
    }
    const blob = await props.client.fetchSchoolExamReportAnswerCardImage(selected.value.id, target.id)
    if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = URL.createObjectURL(blob)
    previewName.value = attachment.filename
  } catch (error) {
    props.notify(describeError(error), 'error')
  }
}

async function supplementStats() {
  if (!selected.value || !supplementSubject.value || supplementScore.value === '' || supplementMax.value === '') {
    props.notify('请选择学科并填写得分/满分。', 'caution')
    return
  }
  savingSubject.value = true
  try {
    await props.client.supplementSchoolExamReportSubject(selected.value.id, {
      subject: supplementSubject.value,
      score: Number(supplementScore.value),
      max_score: Number(supplementMax.value),
      class_rank: supplementClassRank.value === '' ? null : Number(supplementClassRank.value),
      grade_rank: supplementGradeRank.value === '' ? null : Number(supplementGradeRank.value),
    })
    await props.client.matchSchoolExamReport(selected.value.id)
    await load(selected.value.id)
    supplementSubject.value = ''
    supplementScore.value = ''
    supplementClassRank.value = ''
    supplementGradeRank.value = ''
    props.notify('已补录学科统计并重新关联。', 'success')
  } catch (error) {
    props.notify(describeError(error), 'error')
  } finally {
    savingSubject.value = false
  }
}

async function saveIdentity() {
  if (!selected.value) return
  savingIdentity.value = true
  try {
    const report = await props.client.updateSchoolExamReport(selected.value.id, {
      grade: editGrade.value.trim() || null,
      exam_type: editType.value.trim() || null,
      academic_year: editYear.value.trim() || null,
    })
    await load(report.id)
    props.notify('报告身份已补录；请重新执行关联后核对。', 'success')
  } catch (error) {
    props.notify(describeError(error), 'error')
  } finally {
    savingIdentity.value = false
  }
}

async function generateDrafts() {
  if (!selected.value) return
  generatingDrafts.value = true
  try {
    const result = await props.client.generateSchoolExamReportItemDrafts(selected.value.id)
    if (result.created === 0) {
      props.notify(
        `未生成待核对明细：${(result.unmapped_subjects || []).map(code => getSubjectLabel(code)).join('、') || '没有已关联校考'}。请先补录/关联校考档案。`,
        'caution',
      )
    } else {
      draftsGeneratedHere.value = true
      props.notify(
        `已生成 ${result.created} 条待核对明细（无需原卷/答题卡）；请到“原卷与明细核对”映射知识点并逐题确认。`,
        'success',
      )
    }
  } catch (error) {
    props.notify(describeError(error), 'error')
  } finally {
    generatingDrafts.value = false
  }
}

async function confirmReport() {
  if (!selected.value) return
  confirming.value = true
  try {
    const report = await props.client.confirmSchoolExamReport(selected.value.id)
    await load(report.id)
    const applied = report.ledger?.applied_subjects?.length ?? 0
    const conflicts = report.ledger?.conflict_subjects?.length ?? 0
    props.notify(
      conflicts
        ? `报告已确认；${applied} 科已回写台账，${conflicts} 科因历史已确认冲突未覆盖。`
        : `报告已确认；${applied} 科成绩已回写校考台账。`,
      conflicts ? 'caution' : 'success',
    )
  } catch (error) {
    props.notify(describeError(error), 'error')
  } finally {
    confirming.value = false
  }
}

function goToPapersDrafts() {
  const firstMatch = selected.value?.linked_exam_ids.find(l => l.subject === props.subject) ?? selected.value?.linked_exam_ids[0]
  emit('open-papers-drafts', firstMatch?.exam_id)
}

onMounted(() => void load())
</script>

<template>
  <section class="report-center" aria-label="校考报告导入与核对">
    <StepFlowWorkspace
      v-model="reportStep"
      :steps="steps"
      :context="reportContext"
      steps-aria-label="校考报告导入四步向导"
    >
      <!-- 第一步 · 发现文件 -->
      <template #step-discover>
        <section class="card" aria-label="第一步 · 发现文件">
          <div class="card-head">
            <div>
              <h3>第一步 · 发现分析报告册</h3>
              <p class="card-sub">
                扫描当前私有 inbox 中的分析报告册；不访问外部平台，不伪造缺失数据。
              </p>
            </div>
            <div class="report-actions">
              <button type="button" class="ghost small" :disabled="loading" @click="load()">
                {{ loading ? '加载中…' : '刷新报告' }}
              </button>
              <button type="button" class="primary small" :disabled="scanning" @click="scan">
                {{ scanning ? '解析中…' : '扫描报告册' }}
              </button>
            </div>
          </div>

          <div v-if="reports === null" class="muted">报告加载中…</div>
          <div v-else-if="reports.length === 0" class="muted">
            当前环境还没有已登记的分析报告册。请先将报告 PDF 放入私有 inbox，再点击“扫描报告册”。
          </div>
          <template v-else>
            <ul class="exam-list report-list" aria-label="分析报告册列表">
              <li
                v-for="report in reports"
                :key="report.id"
                :class="['exam-item', report.id === selectedId ? 'selected' : '']"
              >
                <button
                  type="button"
                  class="source-pick"
                  :aria-pressed="report.id === selectedId"
                  @click="selectReport(report.id)"
                >
                  <span class="exam-title">{{ report.title || report.filename }}</span>
                  <span class="muted tiny">{{ report.pages }} 页 · {{ getReportStatusLabel(report.status) }} · {{ getReportMatchStateLabel(report.match_state) }}</span>
                </button>
                <button
                  type="button"
                  class="ghost small"
                  @click="selectReportAndAdvance(report.id)"
                >
                  关联考试 →
                </button>
              </li>
            </ul>
            <div v-if="selected" class="card-footer-flow">
              <span class="muted tiny">已选定「{{ selected.title || selected.filename }}」</span>
              <button type="button" class="primary small" @click="reportStep = 'match'">
                下一步：关联校考档案 →
              </button>
            </div>
          </template>
        </section>
      </template>

      <!-- 第二步 · 关联考试 -->
      <template #step-match>
        <article v-if="selected" class="card" aria-label="第二步 · 关联考试">
          <div class="card-head">
            <div>
              <h3>第二步 · 关联考试</h3>
              <p class="card-sub">{{ selected.filename }}</p>
            </div>
            <span :class="['chip', isMatchReady ? 'good' : 'wait']">
              {{ getReportMatchStateLabel(selected.match_state) }}
            </span>
          </div>

          <dl class="report-kv">
            <div><dt>学年度</dt><dd>{{ selected.academic_year || '缺失' }}</dd></div>
            <div><dt>年级</dt><dd>{{ selected.grade || '缺失' }}</dd></div>
            <div><dt>考试类型</dt><dd>{{ selected.exam_type || '缺失' }}</dd></div>
            <div><dt>报告时间</dt><dd>{{ selected.report_time || '缺失' }}</dd></div>
          </dl>

          <div class="report-edit-row">
            <label>年级<input v-model="editGrade" placeholder="如：9 / 九年级 / 初三" /></label>
            <label>考试类型<input v-model="editType" placeholder="如：统一练习一 / 期中考试" /></label>
            <label>学年度<input v-model="editYear" placeholder="如：2026-2027" /></label>
            <button type="button" class="ghost small" :disabled="savingIdentity" @click="saveIdentity">
              {{ savingIdentity ? '保存中…' : '保存补录' }}
            </button>
          </div>

          <p v-if="selected.linked_exam_ids.length === 0" class="muted">尚未关联任何单科校考档案。</p>
          <ul v-else class="report-linked-list" aria-label="已关联校考">
            <li v-for="link in selected.linked_exam_ids" :key="link.exam_id">
              <b>{{ getSubjectLabel(link.subject) }}</b>
              <span>{{ link.title }}</span>
              <small>{{ link.exam_date }} · {{ getReportLinkMatchLabel(link.match) }}</small>
            </li>
          </ul>

          <p v-if="selected.linked_exam_ids.some(link => link.match === 'SESSION_ONLY')" class="report-scope-note">
            部分学科仅建立场次关联：报告中该科没有成绩行，系统未伪造成绩，后续可在此补录统计。
          </p>

          <div v-if="sessionOnlySubjects.length" class="report-edit-row">
            <label>
              补齐学科
              <select v-model="supplementSubject">
                <option value="">请选择</option>
                <option v-for="link in sessionOnlySubjects" :key="link.subject" :value="link.subject">
                  {{ getSubjectLabel(link.subject) }}
                </option>
              </select>
            </label>
            <label>得分<input v-model.number="supplementScore" type="number" min="0" step="0.5" /></label>
            <label>满分<input v-model.number="supplementMax" type="number" min="0.5" step="0.5" /></label>
            <label>班排<input v-model.number="supplementClassRank" type="number" min="1" /></label>
            <label>年排<input v-model.number="supplementGradeRank" type="number" min="1" /></label>
            <button type="button" class="ghost small" :disabled="savingSubject" @click="supplementStats">
              {{ savingSubject ? '保存中…' : '补录并重新关联' }}
            </button>
          </div>

          <div v-if="matchUnresolved.length || (!isMatchReady && selected.match_state === 'NOT_FOUND')" class="gate-alert-banner">
            <span>
              缺少对应校考档案{{ matchUnresolved.length ? `（${matchUnresolved.map(code => getSubjectLabel(code)).join('、')}）` : '' }}。
              请先在「第一阶段 · 总分台账与建档」中补录该科校考，再回来重新执行关联。
            </span>
            <button type="button" class="primary small" @click="emit('open-scores')">
              前往总分台账与建档 →
            </button>
          </div>

          <p v-if="matchAmbiguous.length" class="report-scope-note">
            存在多个同科候选：{{ matchAmbiguous.map(code => getSubjectLabel(code)).join('、') }}。请先整理重复档案。
          </p>

          <div class="card-footer-flow">
            <button type="button" class="ghost small" :disabled="matching" @click="rematch">
              {{ matching ? '关联中…' : '重新执行关联' }}
            </button>
            <button
              type="button"
              class="primary small"
              :disabled="!isMatchReady"
              @click="reportStep = 'parse'"
            >
              下一步：成绩校验与答题卡 →
            </button>
          </div>
        </article>
      </template>

      <!-- 第三步 · 成绩与报告解析 -->
      <template #step-parse>
        <article v-if="selected" class="card" aria-label="第三步 · 成绩与报告解析">
          <div class="card-head">
            <div>
              <h3>第三步 · 成绩与报告解析</h3>
              <p class="card-sub">{{ selected.pages }} 页 · 置信度 {{ selected.confidence }}</p>
            </div>
            <span :class="['chip', scopeTone(selected.scope_status)]">
              {{ getReportScopeStatusLabel(selected.scope_status) }}
            </span>
          </div>

          <dl class="report-total">
            <div><dt>报告总分</dt><dd>{{ fmtScore(selected.report_total_score) }} / {{ fmtScore(selected.report_total_max) }}</dd></div>
            <div><dt>已列学科合计</dt><dd>{{ fmtScore(selected.listed_subject_score) }} / {{ fmtScore(selected.listed_subject_max) }}</dd></div>
            <div><dt>总分班排</dt><dd>{{ selected.total_class_rank ?? '缺失' }}</dd></div>
            <div><dt>总分年排</dt><dd>{{ selected.total_grade_rank ?? '缺失' }}</dd></div>
            <div><dt>总分班最高</dt><dd>{{ fmtScore(selected.total_class_highest ?? null) }}</dd></div>
            <div><dt>总分年最高</dt><dd>{{ fmtScore(selected.total_grade_highest ?? null) }}</dd></div>
            <div><dt>实考人数</dt><dd>{{ selected.total_participants ?? '缺失' }}</dd></div>
          </dl>

          <p v-if="selected.scope_status !== 'CONSISTENT'" class="report-scope-note">
            报告总分与已列学科合计不一致。保留报告原始总分，等待人工确认统计范围；系统不自动改写。
          </p>

          <table class="report-subject-table">
            <thead>
              <tr><th>学科</th><th>得分/满分</th><th>班排</th><th>年排</th><th>实考</th><th>页码</th></tr>
            </thead>
            <tbody>
              <tr v-for="item in selected.subjects" :key="item.subject">
                <td>{{ item.name || getSubjectLabel(item.subject) }}</td>
                <td>{{ fmtScore(item.score) }} / {{ fmtScore(item.max_score) }}</td>
                <td>{{ item.class_rank ?? '—' }}</td>
                <td>{{ item.grade_rank ?? '—' }}</td>
                <td>{{ item.participants ?? '—' }}</td>
                <td>{{ item.page ?? '—' }}</td>
              </tr>
            </tbody>
          </table>

          <p class="muted tiny">
            逐题 {{ questionCount }} 条；答题卡 {{ Object.keys(selected.answer_card_pages).length }} 个学科。逐题和答题卡仍需逐项人工核对。
          </p>
          <ul v-if="Object.keys(selected.answer_card_pages).length" class="report-warnings" aria-label="答题卡页范围">
            <li v-for="(pages, code) in selected.answer_card_pages" :key="code">
              答题卡 · {{ code }}：第 {{ pages.join('、') }} 页
            </li>
          </ul>

          <div class="report-edit-row">
            <label>
              旋转角度
              <select v-model.number="cardRotation" aria-label="答题卡旋转角度">
                <option :value="0">0°</option>
                <option :value="90">90°</option>
                <option :value="180">180°</option>
                <option :value="270">270°</option>
              </select>
            </label>
            <button
              type="button"
              class="ghost small"
              :disabled="buildingCards || !Object.keys(selected.answer_card_pages).length"
              @click="buildCards"
            >
              {{ buildingCards ? '生成中…' : '生成答题卡附件' }}
            </button>
            <span class="muted tiny">选择角度后点“生成”；点“预览”会自动同步当前角度。</span>
          </div>

          <ul v-if="cardAttachments.length" class="report-linked-list" aria-label="答题卡私有附件">
            <li v-for="card in cardAttachments" :key="card.id">
              <b>{{ card.subject }}</b>
              <span>第 {{ card.page_number }} 页 · {{ card.rotation }}°</span>
              <button type="button" class="ghost small" @click="previewCard(card)">
                预览
              </button>
            </li>
          </ul>

          <div v-if="previewUrl" class="report-card-preview-box">
            <img :src="previewUrl" :alt="previewName" class="report-card-preview" />
            <p class="muted tiny">
              <a :href="previewUrl" target="_blank" rel="noopener">{{ previewName }}</a>（仅管理端当前会话可访问）
            </p>
          </div>

          <ul v-if="selected.warnings.length" class="report-warnings">
            <li v-for="warning in selected.warnings" :key="warning">{{ warning }}</li>
          </ul>

          <div class="card-footer-flow">
            <button type="button" class="ghost small" @click="reportStep = 'match'">
              ← 返回关联考试
            </button>
            <button type="button" class="primary small" @click="reportStep = 'confirm'">
              下一步：确认入档与生成待核明细 →
            </button>
          </div>
        </article>
      </template>

      <!-- 第四步 · 核对入档 -->
      <template #step-confirm>
        <article v-if="selected" class="card" aria-label="第四步 · 核对入档">
          <div class="card-head">
            <div>
              <h3>第四步 · 核对入档与生成待核对明细</h3>
              <p class="card-sub">已关联 {{ linkedCount }} / {{ selected.subjects.length }} 科 · 推荐顺序：① 人工确认报告 → ② 生成待核对明细 → ③ 逐题核对入账</p>
            </div>
            <span :class="['chip', selected.status === 'confirmed' ? 'good' : 'wait']">
              {{ selected.status === 'confirmed' ? '已确认' : '待核对' }}
            </span>
          </div>

          <p v-if="selected.match_state === 'AMBIGUOUS'" class="report-scope-note">
            存在多个同科候选，请先整理重复档案后再确认。
          </p>
          <p v-else-if="selected.match_state === 'NOT_FOUND'" class="report-scope-note">
            尚未找到任何对应校考档案，不能确认。
          </p>
          <p v-else-if="selected.match_state === 'PARTIAL_MATCH'" class="report-scope-note">
            部分学科已关联；缺卷学科允许后续补录，不影响本次人工确认。
          </p>
          <p v-else class="muted">
            确认只记录“已人工核对报告”状态并回写台账总分与答题卡；报告中的总分、排名、逐题和答题卡不会被写成已验证知识点错误。
          </p>

          <div class="report-actions" style="margin: 12px 0;">
            <button type="button" class="primary small" :disabled="!canConfirm || confirming" @click="confirmReport">
              {{ confirming ? '确认中…' : selected.status === 'confirmed' ? '① 已人工确认报告' : '① 人工确认报告' }}
            </button>
            <button type="button" class="ghost small" :disabled="generatingDrafts" @click="generateDrafts">
              {{ generatingDrafts ? '生成中…' : '② 生成待核对明细到台账' }}
            </button>
          </div>

          <p class="muted tiny">
            待核对明细直接从分析报告生成，不需要原卷/答题卡；进入「原卷提取与明细核对」的逐题明细核对台时，系统会自动结合已上传原卷匹配候选知识点，人工核对确认后即可用于错误分析与复盘。
          </p>

          <div class="handoff-box">
            <div>
              <strong>{{ draftsGeneratedHere ? '待核对明细已生成！' : '去逐题明细核对台逐题确认' }}</strong>
              <span>在「原卷与明细核对」第 3 步核对台确认知识点与失分题错因后，即可查看「错误分析与复盘」。</span>
            </div>
            <button type="button" class="primary small" @click="goToPapersDrafts">
              前往逐题明细核对台 →
            </button>
          </div>
        </article>
      </template>
    </StepFlowWorkspace>
  </section>
</template>

<style scoped>
.report-center { display: flex; flex-direction: column; gap: 14px; }
.report-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.report-list { margin-top: 0; }
.report-kv, .report-total { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 8px; margin: 10px 0; }
.report-kv div, .report-total div { border: 1px solid var(--line-soft); border-radius: var(--radius-s); padding: 8px 10px; }
.report-kv dt, .report-total dt { font-size: 0.76rem; color: var(--muted); }
.report-kv dd, .report-total dd { margin: 2px 0 0; font-weight: 600; }
.report-linked-list { list-style: none; padding: 0; margin: 8px 0; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.report-linked-list li { display: flex; gap: 8px; flex-wrap: wrap; border: 1px solid var(--line-soft); border-radius: 8px; padding: 8px 10px; background: var(--card-warm); }
@media (max-width: 900px) {
  .report-linked-list { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 640px) {
  .report-linked-list { grid-template-columns: 1fr; }
}
.report-subject-table { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 0.82rem; }
.report-subject-table th, .report-subject-table td { text-align: left; border-bottom: 1px solid var(--line-soft); padding: 6px 4px; }
.report-scope-note { border-left: 3px solid var(--amber-line, #e2c58e); padding: 8px 10px; background: var(--amber-soft); border-radius: var(--radius-s); }
.report-warnings { margin: 8px 0 0; padding-left: 18px; color: var(--muted); }
.report-edit-row { display: flex; gap: 8px; align-items: flex-end; flex-wrap: wrap; margin: 8px 0; }
.report-edit-row label { margin: 0; flex: 0 1 180px; }
.report-edit-row label input { margin-top: 4px; }
.report-card-preview-box { margin-top: 10px; display: flex; flex-direction: column; gap: 6px; }
.report-card-preview { max-width: 100%; max-height: 420px; object-fit: contain; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: #fff; }
</style>
