<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  describeError,
  SUBJECT_LABELS,
  type AdminWrongDiagnosticDetail,
  type AdminWrongDiagnosticListItem,
  type ApiClient,
  type Subject,
} from '../../api'
import { COGNITIVE_GAP_LABELS, fmtPoints, KIND_LABELS, resolveAnswerContent, shortTime } from '../../copy'
import HelpBubble from '../HelpBubble.vue'
import type { NoticeTone } from '../Notice.vue'
import { RichText } from '../../rich'
import StepFlowWorkspace from './StepFlowWorkspace.vue'
import type { StepDefinition, StepFlowContext } from './stepFlow'

const props = defineProps<{
  client: ApiClient
  subject: Subject
  notify: (text: string, tone?: NoticeTone) => void
}>()

type DiagFilter = 'all' | 'with_dialogue' | 'pending_analyze' | 'pending_choice' | 'adopted'
type DiagStepId = 'pick' | 'analyze' | 'decide'

const loadingList = ref(false)
const loadingDetail = ref(false)
const analyzing = ref(false)
const savingChoice = ref(false)
const listError = ref('')
const detailError = ref('')
const filterMode = ref<DiagFilter>('all')
const activeStep = ref<DiagStepId>('pick')

const items = ref<AdminWrongDiagnosticListItem[]>([])
const selectedAttemptId = ref<string | null>(null)
const detail = ref<AdminWrongDiagnosticDetail | null>(null)
const draftOptionId = ref<'opt_1' | 'opt_2' | 'opt_3' | null>(null)
const draftNote = ref('')

const dialogueCount = computed(() => items.value.filter(it => it.tutor_turn_count > 0).length)
const pendingAnalyzeCount = computed(() => items.value.filter(it => !it.has_diagnosis).length)
const adoptedCount = computed(() => items.value.filter(it => Boolean(it.selected_option_id)).length)
const pendingChoiceCount = computed(() => items.value.filter(it => it.has_diagnosis && !it.selected_option_id).length)

const filteredItems = computed(() => {
  if (filterMode.value === 'with_dialogue') return items.value.filter(it => it.tutor_turn_count > 0)
  if (filterMode.value === 'pending_analyze') return items.value.filter(it => !it.has_diagnosis)
  if (filterMode.value === 'pending_choice') return items.value.filter(it => it.has_diagnosis && !it.selected_option_id)
  if (filterMode.value === 'adopted') return items.value.filter(it => Boolean(it.selected_option_id))
  return items.value
})

const selectedListItem = computed(
  () => items.value.find(it => it.attempt_id === selectedAttemptId.value) ?? null
)

const adoptedSolutionTitle = computed(() => {
  const diag = detail.value?.diagnosis
  if (!diag?.selected_option_id) return ''
  return diag.solutions.find(s => s.option_id === diag.selected_option_id)?.title ?? ''
})

const diagContext = computed<StepFlowContext | null>(() => {
  const cur = selectedListItem.value
  if (!cur) return null
  const statusText = cur.selected_option_id
    ? `已采纳：${cur.selected_solution_title || '对策'}`
    : cur.has_diagnosis
      ? '已剖析待选方案'
      : '待 AI 剖析'
  return {
    eyebrow: '当前诊断错题',
    title: `${cur.knowledge_titles[0] ?? SUBJECT_LABELS[props.subject]} · 学生作答 ${cur.student_answer}`,
    statusText: `${cur.tutor_turn_count > 0 ? `我的书童对话 ${cur.tutor_turn_count} 轮 · ` : ''}${statusText}`,
    statusTone: cur.selected_option_id ? 'good' : cur.has_diagnosis ? 'wait' : 'mid',
  }
})

const diagSteps = computed<StepDefinition[]>(() => {
  const hasDetail = detail.value !== null
  const hasDiag = Boolean(detail.value?.diagnosis)
  const hasAdopted = Boolean(detail.value?.diagnosis?.selected_option_id)
  return [
    {
      id: 'pick',
      title: '1. 选定待诊断错题',
      subtitle: selectedListItem.value ? '已选定当前错题' : '先从台账点选一道错题',
      badge: `${items.value.length} 题`,
      done: hasDetail,
      prereqMet: true,
    },
    {
      id: 'analyze',
      title: '2. 对话回放与 AI 剖析',
      subtitle: hasDiag ? '已剖析真正错因' : '查看对话并触发 AI 分析',
      badge: detail.value ? `${detail.value.tutor_turns.length} 轮对话` : undefined,
      badgeTone: detail.value && detail.value.tutor_turns.length > 0 ? 'mid' : 'subtle',
      done: hasDiag,
      prereqMet: hasDetail,
      lockReason: '请先在第 1 步选定一道错题。',
    },
    {
      id: 'decide',
      title: '3. 三选一解决对策',
      subtitle: hasAdopted ? '已采纳并同步学生端' : '3 列方案卡拍板并附备注',
      badge: hasAdopted ? '已采纳' : '3 选 1',
      badgeTone: hasAdopted ? 'good' : 'wait',
      done: hasAdopted,
      prereqMet: hasDiag,
      lockReason: '请先在第 2 步点击「AI 分析真正错因」生成 3 套解决对策。',
    },
  ]
})

function syncDraftFromDetail(next: AdminWrongDiagnosticDetail | null) {
  if (!next?.diagnosis) {
    draftOptionId.value = null
    draftNote.value = ''
    return
  }
  draftOptionId.value = next.diagnosis.selected_option_id ?? null
  draftNote.value = next.diagnosis.admin_note ?? ''
}

async function loadDetail(attemptId: string) {
  selectedAttemptId.value = attemptId
  loadingDetail.value = true
  detailError.value = ''
  try {
    const res = await props.client.adminWrongDiagnosticDetail(attemptId)
    detail.value = res
    syncDraftFromDetail(res)
  } catch (e) {
    detailError.value = describeError(e)
  } finally {
    loadingDetail.value = false
  }
}

async function selectAndAdvance(attemptId: string) {
  await loadDetail(attemptId)
  if (!detailError.value && detail.value) {
    activeStep.value = 'analyze'
  }
}

async function loadList(keepSelected = true) {
  loadingList.value = true
  listError.value = ''
  try {
    const list = await props.client.adminWrongDiagnostics(props.subject, 30)
    items.value = list
    if (list.length === 0) {
      selectedAttemptId.value = null
      detail.value = null
      syncDraftFromDetail(null)
      activeStep.value = 'pick'
      return
    }
    const targetId =
      keepSelected && selectedAttemptId.value && list.some(x => x.attempt_id === selectedAttemptId.value)
        ? selectedAttemptId.value
        : list[0].attempt_id
    await loadDetail(targetId)
  } catch (e) {
    listError.value = describeError(e)
  } finally {
    loadingList.value = false
  }
}

async function runAnalysis() {
  if (!detail.value || analyzing.value) return
  analyzing.value = true
  detailError.value = ''
  try {
    const updated = await props.client.adminAnalyzeWrongDiagnostic(detail.value.attempt_id)
    detail.value = updated
    syncDraftFromDetail(updated)
    props.notify('AI 已完成错误真正原因剖析并生成 3 个可选解决对策，可进入第 3 步选定。', 'success')
    await loadList(true)
  } catch (e) {
    detailError.value = describeError(e)
  } finally {
    analyzing.value = false
  }
}

async function saveSelectedSolution() {
  if (!detail.value?.diagnosis || !draftOptionId.value || savingChoice.value) return
  savingChoice.value = true
  detailError.value = ''
  try {
    const updated = await props.client.adminSelectWrongDiagnosticSolution(detail.value.attempt_id, {
      optionId: draftOptionId.value,
      adminNote: draftNote.value.trim() || null,
    })
    detail.value = updated
    syncDraftFromDetail(updated)
    props.notify('已保存选定解决对策，并已同步至学生端「近期错题回顾」。', 'success')
    await loadList(true)
  } catch (e) {
    detailError.value = describeError(e)
  } finally {
    savingChoice.value = false
  }
}

watch(
  [() => props.client, () => props.subject],
  () => {
    selectedAttemptId.value = null
    detail.value = null
    filterMode.value = 'all'
    activeStep.value = 'pick'
    void loadList(false)
  },
  { immediate: true }
)
</script>

<template>
  <div class="admin-workspace" role="region" aria-label="错题 AI 深度诊断工作台">
    <!-- 顶部信息汇总卡（沿用题库 / 学校考试 / 知识点库同款 .slim-tool-bar） -->
    <div class="slim-tool-bar" role="region" aria-label="错题诊断工作台总览">
      <div class="slim-tool-main">
        <div class="slim-tool-title-row">
          <h2>{{ SUBJECT_LABELS[subject] }}错题诊断工作台</h2>
          <div class="status-badges-row status-banner" role="region" aria-label="错题诊断状态统计">
            <span class="badge pending">待 AI 分析: {{ pendingAnalyzeCount }}</span>
            <span class="badge pending">待定对策: {{ pendingChoiceCount }}</span>
            <span class="badge approved">已定对策: {{ adoptedCount }}</span>
            <span class="badge clauses">有对话记录: {{ dialogueCount }} / {{ items.length }}</span>
          </div>
        </div>
        <div class="sub-head">
          <span>当前科目：{{ SUBJECT_LABELS[subject] }} · 结合数据库保存的「我的书童」对话记录剖析真正错因，并三选一对策同步给学生端</span>
          <span
            v-if="items.length > 0 && pendingAnalyzeCount === 0 && pendingChoiceCount === 0"
            class="audit-note audit-ok"
          >
            当前学科近期错题已全部完成 AI 剖析与对策采纳。
          </span>
          <span v-else-if="pendingAnalyzeCount > 0" class="audit-note">
            尚有 {{ pendingAnalyzeCount }} 道错题待 AI 分析，请按三步流程选定并剖析。
          </span>
        </div>
      </div>

      <div class="slim-tool-actions">
        <HelpBubble compact title="错题诊断三步流程" label="诊断说明">
          <p>① 从台账选定待诊断错题（支持按对话状态筛选）；② 回放学生与「我的书童」的持久化对话并手动触发 AI 剖析真正原因；③ 在 3 套不同维度对策中选定 1 套，同步至学生端错题建议。</p>
        </HelpBubble>
        <button type="button" class="ghost small" :disabled="loadingList" @click="loadList(true)">
          {{ loadingList ? '刷新中…' : '刷新' }}
        </button>
      </div>
    </div>

    <p v-if="listError" class="form-error">{{ listError }}</p>

    <div v-if="!loadingList && items.length === 0" class="card">
      <p class="muted" style="margin: 0;">
        {{ SUBJECT_LABELS[subject] }}暂无客观失分错题记录。学生练习出现错题并与「我的书童」开展引导对话后，可在此查看完整对话并分析根因。
      </p>
    </div>

    <!-- 方案 A：沿用前三项同款 StepFlowWorkspace 三步锁步单卡流 -->
    <StepFlowWorkspace
      v-else
      v-model="activeStep"
      :steps="diagSteps"
      :context="diagContext"
      steps-aria-label="错题诊断工作流步骤"
      wide
    >
      <template #context-actions>
        <button
          v-if="activeStep !== 'pick'"
          type="button"
          class="ghost small"
          @click="activeStep = 'pick'"
        >
          切换错题
        </button>
      </template>

      <!-- 第 1 步：选定待诊断错题 -->
      <template #step-pick>
        <section class="card" aria-label="选定待诊断错题">
          <div class="card-head">
            <div>
              <h3>第 1 步 · 选定要诊断的{{ SUBJECT_LABELS[subject] }}错题</h3>
              <p class="card-sub">一眼对比题目考点、与「我的书童」对话轮次及当前诊断进度，选中后进入第 2 步。</p>
            </div>
            <div class="filter-pills" role="group" aria-label="错题诊断筛选">
              <button type="button" :class="['chip-btn', filterMode === 'all' ? 'selected' : '']" @click="filterMode = 'all'">
                全部 ({{ items.length }})
              </button>
              <button type="button" :class="['chip-btn', filterMode === 'with_dialogue' ? 'selected' : '']" @click="filterMode = 'with_dialogue'">
                有对话 ({{ dialogueCount }})
              </button>
              <button type="button" :class="['chip-btn', filterMode === 'pending_analyze' ? 'selected' : '']" @click="filterMode = 'pending_analyze'">
                待剖析 ({{ pendingAnalyzeCount }})
              </button>
              <button type="button" :class="['chip-btn', filterMode === 'pending_choice' ? 'selected' : '']" @click="filterMode = 'pending_choice'">
                待定对策 ({{ pendingChoiceCount }})
              </button>
              <button type="button" :class="['chip-btn', filterMode === 'adopted' ? 'selected' : '']" @click="filterMode = 'adopted'">
                已定对策 ({{ adoptedCount }})
              </button>
            </div>
          </div>

          <p v-if="filteredItems.length === 0" class="muted">当前筛选条件下暂无错题。</p>

          <div v-else class="diag-ledger-grid">
            <button
              v-for="item in filteredItems"
              :key="item.attempt_id"
              type="button"
              :class="['diag-ledger-tile', selectedAttemptId === item.attempt_id ? 'active' : '']"
              @click="selectAndAdvance(item.attempt_id)"
            >
              <div class="diag-item-meta">
                <div class="diag-tags">
                  <span class="chip">{{ item.knowledge_titles[0] ?? (KIND_LABELS[item.kind] ?? item.kind) }}</span>
                  <span v-if="item.tutor_turn_count > 0" class="chip mid">
                    对话 {{ item.tutor_turn_count }} 轮
                  </span>
                  <span v-else class="chip subtle">尚无对话</span>
                </div>
                <span v-if="item.selected_option_id" class="chip good">
                  已定：{{ item.selected_solution_title }}
                </span>
                <span v-else-if="item.has_diagnosis" class="chip wait">待选方案</span>
                <span v-else class="chip">待剖析</span>
              </div>
              <p class="diag-item-stem"><RichText :text="item.stem_excerpt" /></p>
              <div class="diag-item-foot">
                <span class="muted tiny">
                  作答：<RichText :text="resolveAnswerContent(item.student_answer, item.options)" />
                  · {{ fmtPoints(item.earned_points ?? 0) }} / {{ fmtPoints(item.max_points) }} · {{ shortTime(item.created_at) }}
                </span>
                <span class="chip mid">进入剖析 →</span>
              </div>
            </button>
          </div>

          <div v-if="detail" class="card-footer-flow">
            <span class="muted">
              当前已加载：<RichText :text="selectedListItem?.stem_excerpt ?? ''" />
            </span>
            <button type="button" class="primary" @click="activeStep = 'analyze'">
              下一步：查看引导对话与 AI 剖析 →
            </button>
          </div>
        </section>
      </template>

      <!-- 第 2 步：对话回放与 AI 错因剖析 -->
      <template #step-analyze>
        <section class="card" aria-label="对话回放与 AI 错因剖析">
          <div class="card-head">
            <div>
              <h3>第 2 步 · 引导对话回放与 AI 错误根因剖析</h3>
              <p class="card-sub">左侧核对原题、标准答案与「我的书童」持久化对话，右侧手动触发 AI 剖析真正原因。</p>
            </div>
            <button type="button" class="ghost small" @click="activeStep = 'pick'">
              ← 返回重选错题
            </button>
          </div>

          <div v-if="loadingDetail" class="tutor-loading">正在读取题目详情与数据库保存的对话记录…</div>

          <div v-else-if="detail" class="diag-split-2">
            <!-- 左列：原题与对话回放 -->
            <div class="diag-panel">
              <div class="diag-panel-head">
                <b>题目与作答对照</b>
                <div class="diag-tags">
                  <span v-for="kp in detail.knowledge_titles" :key="kp" class="chip">{{ kp }}</span>
                </div>
              </div>
              <p class="diag-stem"><RichText :text="detail.stem" /></p>
              <ul v-if="detail.options.length > 0" class="diag-options">
                <li v-for="(opt, idx) in detail.options" :key="idx">
                  <RichText :text="opt" />
                </li>
              </ul>
              <div class="diag-answer-compare">
                <span class="chip bad">
                  学生作答：<RichText :text="resolveAnswerContent(detail.student_answer, detail.options)" />
                </span>
                <span class="chip good">
                  参考答案：<RichText :text="resolveAnswerContent(detail.correct_answer, detail.options)" />
                </span>
                <span class="muted tiny">得分 {{ fmtPoints(detail.earned_points ?? 0) }} / {{ fmtPoints(detail.max_points) }}</span>
              </div>

              <div class="diag-dialogue-section">
                <div class="diag-panel-head">
                  <b>学生与「我的书童」对话回放（数据库直读）</b>
                  <span class="chip">{{ detail.tutor_turns.length }} 轮</span>
                </div>
                <p v-if="detail.tutor_turns.length === 0" class="muted" style="margin: 8px 0 0;">
                  该题尚未在学生端开启与「我的书童」的对话；仍可点击右侧按钮直接结合题干与错答分析可能错因。
                </p>
                <div v-else class="tutor-turns" style="margin-top: 8px;">
                  <div
                    v-for="turn in detail.tutor_turns"
                    :key="turn.id"
                    :class="['tutor-bubble', turn.role === 'assistant' ? 'ai' : 'student']"
                  >
                    <div class="bubble-meta">
                      <b>{{ turn.role === 'assistant' ? '我的书童' : '学生' }}</b>
                      <span class="muted tiny">#{{ turn.turn_index }}</span>
                      <span v-if="turn.sanitized_guard_triggered" class="guard-pill">引导保护</span>
                    </div>
                    <p class="bubble-text"><RichText :text="turn.content" /></p>
                  </div>
                </div>
              </div>
            </div>

            <!-- 右列：AI 剖析面板 -->
            <div class="diag-panel diag-ai-panel">
              <div class="diag-panel-head">
                <div>
                  <b>AI 错误根因深度剖析</b>
                  <p class="muted tiny" style="margin: 2px 0 0;">
                    结合原题、参考答案、错答及对话轨迹定位深层根因，并准备 3 套可选方案。
                  </p>
                </div>
                <button
                  type="button"
                  class="primary small"
                  :disabled="analyzing"
                  @click="runAnalysis"
                >
                  {{ analyzing ? 'AI 剖析中…' : (detail.diagnosis ? '重新分析错因' : 'AI 分析真正错因') }}
                </button>
              </div>

              <p v-if="detailError" class="form-error">{{ detailError }}</p>

              <div v-if="!detail.diagnosis" class="diag-empty-hint">
                <p class="muted" style="margin: 0;">
                  尚未生成 AI 错因分析，请点击右上角「<b>AI 分析真正错因</b>」。
                </p>
              </div>

              <div v-else class="diag-result-body">
                <div class="root-cause-card">
                  <div class="root-cause-head">
                    <b>错误真正原因</b>
                    <span class="chip wait">
                      {{ COGNITIVE_GAP_LABELS[detail.diagnosis.cognitive_gap_type] ?? detail.diagnosis.cognitive_gap_type }}
                    </span>
                  </div>
                  <p class="root-cause-text"><RichText :text="detail.diagnosis.root_cause_summary" /></p>
                  <p class="evidence-text">
                    <b>对话 / 作答关键依据：</b><RichText :text="detail.diagnosis.evidence_from_dialogue" />
                  </p>
                </div>

                <div class="handoff-box">
                  <div>
                    <strong>已生成 3 套不同维度的解决对策</strong>
                    <span>前往第 3 步全宽查看 3 套方案并选定其一同步给学生端。</span>
                  </div>
                  <button type="button" class="primary small" @click="activeStep = 'decide'">
                    下一步：从 3 个解决对策中拍板 →
                  </button>
                </div>
              </div>
            </div>
          </div>
        </section>
      </template>

      <!-- 第 3 步：全宽 3 列拍板解决对策 -->
      <template #step-decide>
        <section class="card" aria-label="三选一解决对策拍板">
          <div class="card-head">
            <div>
              <h3>第 3 步 · 从 AI 给出的 3 套解决对策中选定并同步给学生端</h3>
              <p v-if="detail?.diagnosis" class="card-sub">
                真正原因：<RichText :text="detail.diagnosis.root_cause_summary" />
              </p>
            </div>
            <button type="button" class="ghost small" @click="activeStep = 'analyze'">
              ← 回看对话与错因
            </button>
          </div>

          <p v-if="detailError" class="form-error">{{ detailError }}</p>

          <div v-if="detail?.diagnosis" class="solutions-block">
            <div class="solutions-3col" role="radiogroup" aria-label="可选解决方法">
              <button
                v-for="(sol, idx) in detail.diagnosis.solutions"
                :key="sol.option_id"
                type="button"
                role="radio"
                :aria-checked="draftOptionId === sol.option_id"
                :class="[
                  'solution-card',
                  draftOptionId === sol.option_id ? 'selected' : '',
                  detail.diagnosis.selected_option_id === sol.option_id ? 'adopted' : '',
                ]"
                @click="draftOptionId = sol.option_id"
              >
                <div class="solution-card-head">
                  <span class="solution-idx">方案 {{ idx + 1 }}</span>
                  <span class="chip mid">{{ sol.approach_focus }}</span>
                </div>
                <b class="solution-title"><RichText :text="sol.title" /></b>
                <p class="solution-rationale"><RichText :text="sol.rationale" /></p>
                <ol class="solution-steps">
                  <li v-for="(step, sIdx) in sol.action_steps" :key="sIdx">
                    <RichText :text="step" />
                  </li>
                </ol>
              </button>
            </div>

            <label class="diag-note-field">
              <span>家长 / 老师补充辅导备注（可选，会随方案一同展示给学生）</span>
              <textarea
                v-model="draftNote"
                rows="2"
                maxlength="500"
                placeholder="例如：今晚先用红笔把等号跨项符号圈出来，再做 3 题巩固…"
              />
            </label>

            <div class="card-footer-flow">
              <span v-if="detail.diagnosis.selected_option_id" class="chip good">
                当前已采纳：{{ adoptedSolutionTitle }}
              </span>
              <span v-else class="muted tiny">请先点选上方 3 张方案卡中的 1 个</span>
              <button
                type="button"
                class="primary"
                :disabled="!draftOptionId || savingChoice"
                @click="saveSelectedSolution"
              >
                {{ savingChoice ? '保存中…' : '确认采用此方案（同步给学生端）' }}
              </button>
            </div>
          </div>
        </section>
      </template>
    </StepFlowWorkspace>
  </div>
</template>
