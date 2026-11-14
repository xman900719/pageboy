<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
  describeError,
  SUBJECT_LABELS,
  type ApiClient,
  type GrowthStatus,
  type Subject,
  type Validation,
} from '../api'
import ValidationPanel from '../components/ValidationPanel.vue'
import Note from '../components/Note.vue'
import type { NoticeTone } from '../components/Notice.vue'

const props = defineProps<{
  client: ApiClient
  subject: Subject
  notify: (text: string, tone?: NoticeTone) => void
}>()

const emit = defineEmits<{
  (e: 'goPracticeFocus', code: string): void
  (e: 'goView', view: 'practice' | 'growth' | 'knowledge'): void
}>()

const growth = ref<GrowthStatus | null>(null)
const validation = ref<Validation | null>(null)
const loading = ref(false)
const error = ref('')

// 目标设定表单状态
const showGoalForm = ref(false)
const targetPoints = ref('')
const maxPoints = ref('100')
const minutesPerDay = ref('20')
const savingGoal = ref(false)
const goalError = ref('')

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    const [g, v] = await Promise.all([
      props.client.growthStatus(props.subject),
      props.client.validation(props.subject),
    ])
    growth.value = g
    validation.value = v
    if (g.current_goal) {
      targetPoints.value = String(g.current_goal.target_points)
      maxPoints.value = String(g.current_goal.max_points)
      minutesPerDay.value = String(g.current_goal.minutes_per_day)
    } else if (!targetPoints.value) {
      targetPoints.value = '85'
    }
  } catch (e) {
    error.value = describeError(e)
  } finally {
    loading.value = false
  }
}

async function submitGoal() {
  const tgt = Number(targetPoints.value)
  const max = Number(maxPoints.value)
  const mins = Number(minutesPerDay.value)
  if (!Number.isFinite(tgt) || !Number.isFinite(max) || tgt < 0 || max <= 0 || tgt > max) {
    goalError.value = '请输入有效的目标分数（0 ≤ 目标分 ≤ 满分）。'
    return
  }
  if (!Number.isFinite(mins) || mins < 5 || mins > 240) {
    goalError.value = '每日学习时长需在 5–240 分钟之间。'
    return
  }
  goalError.value = ''
  savingGoal.value = true
  try {
    const saved = await props.client.setGoal({
      subject: props.subject,
      targetPoints: tgt,
      maxPoints: max,
      minutesPerDay: mins,
    })
    props.notify(`目标已保存（第 ${saved.version} 版）。`, 'success')
    showGoalForm.value = false
    await loadAll()
  } catch (e) {
    goalError.value = describeError(e)
  } finally {
    savingGoal.value = false
  }
}

function fmtPct(rate: number | null | undefined): string {
  if (rate === null || rate === undefined) return '样本不足'
  const val = Math.round(rate * 1000) / 10
  return `${Number.isInteger(val) ? val : val.toFixed(1)}%`
}

// 计算领域能力雷达 SVG 多边形几何
const radarGeom = computed(() => {
  const domains = growth.value?.domain_radar ?? []
  const count = domains.length
  if (count < 3) return null
  const cx = 140
  const cy = 140
  const maxR = 92
  const rings = [0.25, 0.5, 0.75, 1]
  const axes = domains.map((d, i) => {
    const angle = (-Math.PI / 2) + (2 * Math.PI * i) / count
    const ratio = d.observed_rate !== null && d.observed_rate !== undefined ? Math.max(0.08, d.observed_rate) : 0.06
    return {
      code: d.domain_code,
      name: d.domain_name,
      rate: d.observed_rate,
      tested: d.observed_rate !== null && d.observed_rate !== undefined,
      xEnd: cx + maxR * Math.cos(angle),
      yEnd: cy + maxR * Math.sin(angle),
      xLabel: cx + (maxR + 24) * Math.cos(angle),
      yLabel: cy + (maxR + 20) * Math.sin(angle),
      xVal: cx + maxR * ratio * Math.cos(angle),
      yVal: cy + maxR * ratio * Math.sin(angle),
    }
  })
  const ringPolygons = rings.map(scale =>
    domains
      .map((_, i) => {
        const angle = (-Math.PI / 2) + (2 * Math.PI * i) / count
        return `${(cx + maxR * scale * Math.cos(angle)).toFixed(1)},${(cy + maxR * scale * Math.sin(angle)).toFixed(1)}`
      })
      .join(' ')
  )
  const dataPolygon = axes.map(a => `${a.xVal.toFixed(1)},${a.yVal.toFixed(1)}`).join(' ')
  return { cx, cy, axes, ringPolygons, dataPolygon }
})

watch(
  [() => props.client, () => props.subject],
  () => {
    void loadAll()
  },
  { immediate: true }
)
</script>

<template>
  <div class="view-stack">
    <section class="card" aria-label="成长状态总览">
      <div class="card-head">
        <div>
          <h2>{{ SUBJECT_LABELS[subject] }}成长状态总览</h2>
          <p class="card-sub">
            清晰展示当前优势模块、薄弱短板与待探索盲区；证据不足时不推算成绩。
          </p>
        </div>
        <div class="head-actions">
          <button type="button" class="ghost small" @click="loadAll" :disabled="loading">
            {{ loading ? '刷新中…' : '刷新状态' }}
          </button>
          <button type="button" class="primary small" @click="emit('goView', 'knowledge')">
            查看知识图谱
          </button>
        </div>
      </div>

      <p v-if="error" class="form-error">{{ error }}</p>

      <template v-if="growth">
        <div class="growth-kpis">
          <div class="kpi-tile ok">
            <b>{{ growth.summary_counts.mastered_count ?? 0 }}</b>
            <span>当前优势（已掌握）</span>
          </div>
          <div class="kpi-tile bad">
            <b>{{ growth.summary_counts.weak_count ?? 0 }}</b>
            <span>当前不足（待突破）</span>
          </div>
          <div class="kpi-tile wait">
            <b>{{ growth.summary_counts.insufficient_count ?? 0 }}</b>
            <span>证据不足（继续累积）</span>
          </div>
          <div class="kpi-tile neutral">
            <b>{{ growth.summary_counts.untested_count ?? 0 }}</b>
            <span>暂未测验盲区</span>
          </div>
        </div>

        <!-- 领域维度可视化：雷达图 + 分领域条形统计 -->
        <div class="domain-visual-grid">
          <div v-if="radarGeom" class="radar-box" aria-label="领域能力分布雷达图">
            <h3>知识领域能力雷达</h3>
            <svg viewBox="0 0 280 280" class="radar-svg" role="img" aria-label="各知识领域实测得分率雷达图">
              <polygon
                v-for="(pts, idx) in radarGeom.ringPolygons"
                :key="idx"
                :points="pts"
                class="radar-ring"
              />
              <line
                v-for="ax in radarGeom.axes"
                :key="`axis-${ax.code}`"
                :x1="radarGeom.cx"
                :y1="radarGeom.cy"
                :x2="ax.xEnd"
                :y2="ax.yEnd"
                class="radar-axis"
              />
              <polygon :points="radarGeom.dataPolygon" class="radar-area" />
              <circle
                v-for="ax in radarGeom.axes"
                :key="`pt-${ax.code}`"
                :cx="ax.xVal"
                :cy="ax.yVal"
                r="4"
                :class="ax.tested ? 'radar-dot tested' : 'radar-dot untested'"
              />
              <text
                v-for="ax in radarGeom.axes"
                :key="`lbl-${ax.code}`"
                :x="ax.xLabel"
                :y="ax.yLabel"
                text-anchor="middle"
                class="radar-label"
              >
                {{ ax.name.replace(/^（.*?）|\(.*?\)/g, '').slice(0, 6) }}
              </text>
            </svg>
            <p class="muted tiny">实测得分率仅在具备有效作答样本后绘制；未测领域显示于中心基点。</p>
          </div>

          <div class="domain-bars-box" aria-label="分领域掌握进度条">
            <h3>分领域掌握详情</h3>
            <ul class="domain-bar-list">
              <li v-for="d in growth.domain_radar" :key="d.domain_code" class="domain-bar-row">
                <div class="domain-bar-head">
                  <b>{{ d.domain_name }}</b>
                  <span class="domain-rate-text">{{ fmtPct(d.observed_rate) }}</span>
                </div>
                <div class="bar-track" aria-hidden="true">
                  <div
                    class="bar-fill"
                    :style="{ width: d.observed_rate !== null && d.observed_rate !== undefined ? `${Math.round(d.observed_rate * 100)}%` : '0%' }"
                  />
                </div>
                <div class="domain-bar-meta">
                  <span class="ok-txt">掌握 {{ d.mastered_count }}</span>
                  <span class="bad-txt">待突破 {{ d.weak_count }}</span>
                  <span class="muted">未知/未测 {{ d.insufficient_count + d.untested_count }}</span>
                </div>
              </li>
            </ul>
          </div>
        </div>

        <Note title="评价口径声明" tone="discipline">
          {{ growth.disclaimer }}
        </Note>
      </template>
    </section>

    <!-- 优势 vs 不足 双栏形象对比 -->
    <div v-if="growth" class="strength-weak-grid">
      <section class="card strength-card" aria-label="当前优势知识点">
        <div class="card-head">
          <h2>当前优势 ({{ growth.strengths.length }})</h2>
          <span class="chip good">稳固保持</span>
        </div>
        <p v-if="growth.strengths.length === 0" class="muted">
          尚未形成达到稳定阈值（{{ Math.round(growth.planning_threshold * 100) }}% 且 ≥3 题独立样本）的优势知识点，完成更多练习后将自动点亮。
        </p>
        <ul v-else class="growth-topic-list">
          <li v-for="item in growth.strengths" :key="item.code" class="growth-topic-row ok">
            <div class="topic-row-main">
              <b>{{ item.name }}</b>
              <small class="muted">已验 {{ item.sample_size }} 题 · 得分率 {{ fmtPct(item.observed_rate) }}</small>
            </div>
            <div class="mini-bar" aria-hidden="true">
              <div class="mini-bar-fill ok" :style="{ width: `${Math.round((item.observed_rate ?? 0) * 100)}%` }" />
            </div>
          </li>
        </ul>
      </section>

      <section class="card weakness-card" aria-label="当前不足与薄弱短板">
        <div class="card-head">
          <h2>当前不足 ({{ growth.weaknesses.length }})</h2>
          <span class="chip bad">重点突破</span>
        </div>
        <p v-if="growth.weaknesses.length === 0" class="muted">
          暂未发现已确认低于阈值的薄弱知识点。如果仍有“证据不足”或“暂未测验”项目，建议通过综合练习继续排查。
        </p>
        <ul v-else class="growth-topic-list">
          <li v-for="item in growth.weaknesses" :key="item.code" class="growth-topic-row bad">
            <div class="topic-row-main">
              <b>{{ item.name }}</b>
              <small class="muted">已验 {{ item.sample_size }} 题 · 得分率 {{ fmtPct(item.observed_rate) }}</small>
            </div>
            <button
              type="button"
              class="primary small"
              @click="emit('goPracticeFocus', item.code)"
            >
              针对练习
            </button>
          </li>
        </ul>
      </section>
    </div>

    <!-- 证据不足与待探索盲区 -->
    <section
      v-if="growth && (growth.developing.length > 0 || growth.untested_highlights.length > 0)"
      class="card"
      aria-label="证据不足与待探索盲区"
    >
      <div class="card-head">
        <div>
          <h2>待巩固与待测探索</h2>
          <p class="card-sub">样本量不足 3 题或尚未测验的知识点暂不下定论，点选即可定向体验练习。</p>
        </div>
      </div>
      <div class="explore-chip-grid">
        <button
          v-for="item in [...growth.developing, ...growth.untested_highlights].slice(0, 14)"
          :key="item.code"
          type="button"
          class="explore-node-btn"
          @click="emit('goPracticeFocus', item.code)"
        >
          <span>{{ item.name }}</span>
          <small>{{ item.sample_size > 0 ? `${item.sample_size} 题 · ${fmtPct(item.observed_rate)}` : '未测验' }}</small>
        </button>
      </div>
    </section>

    <!-- 学习目标设定 + 独立复测阶段对比 -->
    <section class="card" aria-label="学习目标与阶段验证">
      <div class="card-head">
        <div>
          <h2>学习目标与阶段复测验证</h2>
          <p v-if="growth?.current_goal" class="card-sub">
            目标版本 v{{ growth.current_goal.version }} · 目标 {{ growth.current_goal.target_points }} / {{ growth.current_goal.max_points }} 分 · 每天 {{ growth.current_goal.minutes_per_day }} 分钟
          </p>
          <p v-else class="card-sub">尚未设定学习目标，可在此记录每日练习期望。</p>
        </div>
        <button type="button" class="ghost small" @click="showGoalForm = !showGoalForm">
          {{ showGoalForm ? '收起表单' : (growth?.current_goal ? '修改目标' : '设定目标') }}
        </button>
      </div>

      <form v-if="showGoalForm" class="goal-form" @submit.prevent="submitGoal">
        <label>
          科目目标分
          <input v-model="targetPoints" type="number" step="0.5" min="0" />
        </label>
        <label>
          科目满分
          <input v-model="maxPoints" type="number" step="0.5" min="1" />
        </label>
        <label>
          每天分钟数
          <input v-model="minutesPerDay" type="number" min="5" max="240" />
        </label>
        <p v-if="goalError" class="form-error">{{ goalError }}</p>
        <button type="submit" class="primary small" :disabled="savingGoal">
          {{ savingGoal ? '保存中…' : '保存目标' }}
        </button>
      </form>

      <ValidationPanel v-if="validation" :validation="validation" />
    </section>
  </div>
</template>
