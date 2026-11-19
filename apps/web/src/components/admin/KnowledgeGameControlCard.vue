<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
  describeError,
  SUBJECT_LABELS,
  type ApiClient,
  type CandidateNode,
  type KnowledgeGameSubjectConfig,
  type Subject,
} from '../../api'
import { DEFAULT_GAME_CONFIG } from '../../config/knowledgeGames'
import type { NoticeTone } from '../Notice.vue'

type Notify = (text: string, tone?: NoticeTone) => void

const props = defineProps<{
  client: ApiClient
  subject: Subject
  notify: Notify
  candidates: CandidateNode[]
}>()

const loading = ref(false)
const saving = ref(false)
const configs = ref<Record<Subject, KnowledgeGameSubjectConfig>>({ ...DEFAULT_GAME_CONFIG })

const currentCfg = computed<KnowledgeGameSubjectConfig>(
  () => configs.value[props.subject] ?? DEFAULT_GAME_CONFIG[props.subject],
)

const activeNodeCount = computed(() => props.candidates.length)

async function loadConfigs() {
  loading.value = true
  try {
    const res = await props.client.adminKnowledgeGameConfig()
    configs.value = res.subjects
  } catch (e) {
    props.notify(`读取游戏管控配置失败：${describeError(e)}`, 'caution')
  } finally {
    loading.value = false
  }
}

async function saveUpdate(
  patch: Partial<KnowledgeGameSubjectConfig> & { increment_reset_epoch?: boolean },
  successMessage: string,
) {
  saving.value = true
  try {
    const cur = currentCfg.value
    const next = await props.client.adminUpdateKnowledgeGameConfig(props.subject, {
      alchemy_enabled: patch.alchemy_enabled ?? cur.alchemy_enabled,
      expedition_enabled: patch.expedition_enabled ?? cur.expedition_enabled,
      initial_shields: patch.initial_shields ?? cur.initial_shields,
      prioritize_weak: patch.prioritize_weak ?? cur.prioritize_weak,
      practice_gate: patch.practice_gate ?? cur.practice_gate,
      increment_reset_epoch: Boolean(patch.increment_reset_epoch),
    })
    configs.value = {
      ...configs.value,
      [props.subject]: next,
    }
    props.notify(successMessage, 'success')
  } catch (e) {
    props.notify(`保存游戏管控配置失败：${describeError(e)}`, 'caution')
  } finally {
    saving.value = false
  }
}

function toggleAlchemy() {
  const nextVal = !currentCfg.value.alchemy_enabled
  void saveUpdate(
    { alchemy_enabled: nextVal },
    `${SUBJECT_LABELS[props.subject]}「知识合成工坊」已${nextVal ? '开启' : '停用'}。`,
  )
}

function toggleExpedition() {
  const nextVal = !currentCfg.value.expedition_enabled
  void saveUpdate(
    { expedition_enabled: nextVal },
    `${SUBJECT_LABELS[props.subject]}「迷雾科技树探险」已${nextVal ? '开启' : '停用'}。`,
  )
}

function togglePrioritizeWeak() {
  const nextVal = !currentCfg.value.prioritize_weak
  void saveUpdate(
    { prioritize_weak: nextVal },
    `${SUBJECT_LABELS[props.subject]}已切换为「${nextVal ? '智能靶向薄弱点' : '按课标章节顺序'}」。`,
  )
}

function onShieldsChange(ev: Event) {
  const val = Number((ev.target as HTMLSelectElement).value) as 1 | 2 | 3
  void saveUpdate(
    { initial_shields: val },
    `${SUBJECT_LABELS[props.subject]}每局初始护盾已调整为 ${val} 颗。`,
  )
}

function onGateChange(ev: Event) {
  const val = (ev.target as HTMLSelectElement).value as 'recommended' | 'required'
  void saveUpdate(
    { practice_gate: val },
    `${SUBJECT_LABELS[props.subject]}通关闭环已切换为「${val === 'required' ? '强制练题闭环' : '推荐练习'}」。`,
  )
}

function resetStudentProgress() {
  void saveUpdate(
    { increment_reset_epoch: true },
    `已重置${SUBJECT_LABELS[props.subject]}学生端游戏闯关进度（不影响真实做题与校考证据）。`,
  )
}

watch(
  [() => props.client, () => props.subject],
  () => {
    void loadConfigs()
  },
  { immediate: true },
)
</script>

<template>
  <section class="card admin-game-control-card" aria-label="闯关游戏基础管控">
    <div class="card-head">
      <div>
        <h3>🛠️ {{ SUBJECT_LABELS[subject] }} · 学生端双游戏基础管控台</h3>
        <p class="card-sub">
          控制学生端「知识点展示」下「知识合成工坊（方案二）」与「迷雾科技树探险（方案三）」的启停、容错护盾、靶向策略与练题闭环，严格与正式能力证据隔离。
        </p>
      </div>
      <span class="chip good">
        {{ loading ? '同步中…' : saving ? '保存中…' : '● 已与学生端实时同步' }}
      </span>
    </div>

    <div class="admin-control-grid">
      <div class="admin-panel-card">
        <div class="admin-panel-head">
          <h4>🎛️ 双游戏开关与玩法规则控制</h4>
        </div>

        <div class="control-row">
          <div class="control-copy">
            <b>⚗️ 启用「知识合成工坊」（方案二）</b>
            <small>控制学生端知识点展示下是否开放滚雪球合成工坊</small>
          </div>
          <button
            type="button"
            :class="['toggle-pill', currentCfg.alchemy_enabled ? '' : 'off']"
            :aria-pressed="currentCfg.alchemy_enabled"
            :disabled="saving"
            @click="toggleAlchemy"
          >
            {{ currentCfg.alchemy_enabled ? '✓ 已开启' : '已停用' }}
          </button>
        </div>

        <div class="control-row">
          <div class="control-copy">
            <b>🧭 启用「迷雾科技树探险」（方案三）</b>
            <small>控制学生端知识点展示下是否开放三岛激光破甲探险</small>
          </div>
          <button
            type="button"
            :class="['toggle-pill', currentCfg.expedition_enabled ? '' : 'off']"
            :aria-pressed="currentCfg.expedition_enabled"
            :disabled="saving"
            @click="toggleExpedition"
          >
            {{ currentCfg.expedition_enabled ? '✓ 已开启' : '已停用' }}
          </button>
        </div>

        <div class="control-row">
          <div class="control-copy">
            <label for="admin-game-shields"><b>❤️ 每局初始护盾生命数</b></label>
            <small>点错干扰陷阱卡时扣除护盾，控制容错率</small>
          </div>
          <select
            id="admin-game-shields"
            class="admin-select"
            :value="currentCfg.initial_shields"
            :disabled="saving"
            @change="onShieldsChange"
          >
            <option :value="3">3 颗护盾 ❤️❤️❤️ (标准推荐)</option>
            <option :value="2">2 颗护盾 ❤️❤️ (进阶挑战)</option>
            <option :value="1">1 颗护盾 ❤️ (无伤大师)</option>
          </select>
        </div>

        <div class="control-row">
          <div class="control-copy">
            <b>🎯 优先靶向学生「未掌握/待突破」考点</b>
            <small>开启后自动将学生薄弱考点优先排入合成目标与 3 号 BOSS 要塞</small>
          </div>
          <button
            type="button"
            :class="['toggle-pill', currentCfg.prioritize_weak ? '' : 'off']"
            :aria-pressed="currentCfg.prioritize_weak"
            :disabled="saving"
            @click="togglePrioritizeWeak"
          >
            {{ currentCfg.prioritize_weak ? '✓ 智能靶向薄弱点' : '按章节顺序' }}
          </button>
        </div>

        <div class="control-row">
          <div class="control-copy">
            <label for="admin-game-gate"><b>⚔️ 通关后真题专项练习闭环要求</b></label>
            <small>控制爆出新卡或击碎 BOSS 护甲后是否要求前往练题巩固</small>
          </div>
          <select
            id="admin-game-gate"
            class="admin-select"
            :value="currentCfg.practice_gate"
            :disabled="saving"
            @change="onGateChange"
          >
            <option value="recommended">推荐练习（可自由继续下一关）</option>
            <option value="required">强制闭环（需先点前往练题才解锁下一关）</option>
          </select>
        </div>
      </div>

      <div class="admin-panel-card">
        <div class="admin-panel-head">
          <h4>📊 自动生成关卡概览与学生进度控制</h4>
        </div>

        <table class="preview-table">
          <thead>
            <tr>
              <th>游戏模块</th>
              <th>数据源与生成逻辑</th>
              <th>当前状态</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><b>⚗️ 知识合成工坊</b></td>
              <td>依据 {{ activeNodeCount }} 个课标节点与先修拓扑边动态生成滚雪球进化链</td>
              <td>{{ currentCfg.alchemy_enabled ? '已开放' : '已停用' }}</td>
            </tr>
            <tr>
              <td><b>🧭 迷雾科技树探险</b></td>
              <td>依据先修路径构建三岛破甲航线（1000 HP 要塞 + 避坑秘籍宝箱）</td>
              <td>{{ currentCfg.expedition_enabled ? '已开放' : '已停用' }}</td>
            </tr>
          </tbody>
        </table>

        <div class="control-row">
          <div class="control-copy">
            <b>🎓 重置学生端{{ SUBJECT_LABELS[subject] }}游戏进度</b>
            <small>当前重置纪元：第 {{ currentCfg.reset_epoch }} 版 · 仅清除游戏段位/配方，绝不影响正式答题与校考证据</small>
          </div>
          <button
            type="button"
            class="ghost small"
            :disabled="saving"
            @click="resetStudentProgress"
          >
            ↺ 重置本学科游戏进度
          </button>
        </div>
      </div>
    </div>
  </section>
</template>
