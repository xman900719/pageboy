<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import type { KnowledgeGameSubjectConfig, KnowledgeGraph, Subject } from '../api'
import { SUBJECT_LABELS } from '../api'
import { CanvasParticleFx, playGameSound } from '../config/gameFxEngine'
import {
  buildExpeditionCampaign,
  loadSubjectGameProgress,
  resolveRankSummary,
  saveSubjectGameProgress,
  type ExpeditionSlashOption,
  type SubjectGameProgress,
} from '../config/knowledgeGames'

const props = defineProps<{
  graph: KnowledgeGraph
  subject: Subject
  config: KnowledgeGameSubjectConfig
}>()

const emit = defineEmits<{
  (e: 'goPracticeFocus', code: string): void
}>()

const fxCanvasRef = ref<HTMLCanvasElement | null>(null)
const fx = new CanvasParticleFx()
const shaking = ref(false)

const progress = ref<SubjectGameProgress>(
  loadSubjectGameProgress(props.subject, props.config.reset_epoch),
)
const zoneIndex = ref(0)
const slashStep = ref<0 | 1 | 2 | 3>(0) // 0, 1, 2 为三连斩进行中，3 为破甲清零
const shields = ref<number>(props.config.initial_shields)
const combo = ref(0)
const feedbackText = ref('')
const feedbackTone = ref<'good' | 'warn' | ''>('')
const practicedBossCodes = ref<Set<string>>(new Set())

const zones = computed(() => buildExpeditionCampaign(props.graph, props.config))

const currentZone = computed(() => {
  if (zones.value.length === 0) return null
  return zones.value[zoneIndex.value % zones.value.length]
})

const currentSlash = computed(() => {
  const step = slashStep.value
  if (!currentZone.value || step === 3) return null
  return currentZone.value.slashes[step]
})

const bossHp = computed(() => {
  if (!currentZone.value) return 1000
  let hp = 1000
  for (let i = 0; i < slashStep.value; i += 1) {
    hp -= currentZone.value.slashes[i].damage
  }
  return Math.max(0, hp)
})

const bossHpPct = computed(() => Math.round((bossHp.value / 1000) * 100))

const isConquered = computed(() => slashStep.value >= 3)

const rank = computed(() => resolveRankSummary(progress.value.exp))

const heartsDisplay = computed(() => {
  const total = props.config.initial_shields
  const alive = Math.max(0, Math.min(total, shields.value))
  return '❤️'.repeat(alive) + '🖤'.repeat(Math.max(0, total - alive))
})

const mustPracticeFirst = computed(() => {
  if (props.config.practice_gate !== 'required' || !currentZone.value) return false
  return !practicedBossCodes.value.has(currentZone.value.boss.code)
})

function resetZoneBattle() {
  slashStep.value = 0
  feedbackText.value = ''
  feedbackTone.value = ''
}

function reloadFromConfig() {
  progress.value = loadSubjectGameProgress(props.subject, props.config.reset_epoch)
  shields.value = props.config.initial_shields
  combo.value = 0
  zoneIndex.value = 0
  practicedBossCodes.value = new Set()
  resetZoneBattle()
}

watch(
  [() => props.subject, () => props.config.reset_epoch, () => props.config.initial_shields, () => props.config.prioritize_weak],
  () => {
    reloadFromConfig()
  },
)

onMounted(() => {
  fx.attach(fxCanvasRef.value)
})

onBeforeUnmount(() => {
  fx.clear()
})

function triggerShake() {
  shaking.value = false
  requestAnimationFrame(() => {
    shaking.value = true
    window.setTimeout(() => {
      shaking.value = false
    }, 360)
  })
}

function answerSlash(opt: ExpeditionSlashOption) {
  if (!currentZone.value || !currentSlash.value) return
  if (!opt.correct) {
    shields.value = Math.max(1, shields.value - 1)
    combo.value = 0
    feedbackText.value = '💥 破雾受阻！护盾损耗 1 颗，请对照 1 号岛与航道路牌重新判断。'
    feedbackTone.value = 'warn'
    playGameSound('error', progress.value.soundEnabled)
    triggerShake()
    fx.burst('red')
    return
  }

  combo.value += 1
  const nextStep = (slashStep.value + 1) as 1 | 2 | 3
  slashStep.value = nextStep

  if (nextStep >= 3) {
    const bonusExp = combo.value >= 3 ? 150 : 100
    const nextCleared = progress.value.clearedZoneIds.includes(currentZone.value.id)
      ? progress.value.clearedZoneIds
      : [...progress.value.clearedZoneIds, currentZone.value.id]
    const nextTips = progress.value.collectedTips.includes(currentZone.value.secretTip)
      ? progress.value.collectedTips
      : [...progress.value.collectedTips, currentZone.value.secretTip]
    progress.value = {
      ...progress.value,
      exp: progress.value.exp + bonusExp,
      bestCombo: Math.max(progress.value.bestCombo, combo.value),
      clearedZoneIds: nextCleared,
      collectedTips: nextTips,
    }
    saveSubjectGameProgress(props.subject, progress.value)
    feedbackText.value = ''
    feedbackTone.value = 'good'
    playGameSound('win', progress.value.soundEnabled)
    triggerShake()
    fx.burst('gold')
  } else {
    feedbackText.value = `⚡ 命中破甲 -${currentZone.value.slashes[nextStep - 1].damage} HP！连击 x${combo.value}`
    feedbackTone.value = 'good'
    playGameSound('tap', progress.value.soundEnabled)
  }
}

function toggleSound() {
  progress.value = {
    ...progress.value,
    soundEnabled: !progress.value.soundEnabled,
  }
  saveSubjectGameProgress(props.subject, progress.value)
}

function selectZone(idx: number) {
  zoneIndex.value = idx
  shields.value = props.config.initial_shields
  resetZoneBattle()
}

function advanceNextZone() {
  if (zones.value.length === 0) return
  zoneIndex.value = (zoneIndex.value + 1) % zones.value.length
  shields.value = props.config.initial_shields
  resetZoneBattle()
}

function attackBossPractice() {
  if (!currentZone.value) return
  practicedBossCodes.value = new Set([...practicedBossCodes.value, currentZone.value.boss.code])
  emit('goPracticeFocus', currentZone.value.boss.code)
}
</script>

<template>
  <div class="game-container-root" :class="{ shaking }" aria-label="迷雾科技树探险游戏">
    <canvas ref="fxCanvasRef" class="game-fx-canvas" aria-hidden="true" />

    <div v-if="!currentZone" class="game-empty-state">
      <p>当前{{ SUBJECT_LABELS[subject] }}知识图谱节点不足，暂无可生成的探险航线。</p>
    </div>

    <template v-else>
      <!-- 轻盈无框状态条 -->
      <div class="airy-hud">
        <div class="hud-rank-pill">
          <span>{{ rank.icon }} {{ rank.title }}</span>
          <div class="mini-exp-track" aria-hidden="true">
            <div class="mini-exp-fill" :style="{ width: `${rank.progressPct}%` }" />
          </div>
          <span class="rank-tease-txt">{{ rank.nextTease }}</span>
        </div>

        <div class="hud-vitals">
          <span class="vital-pill" :aria-label="`当前剩余护盾 ${shields} 颗`">{{ heartsDisplay }}</span>
          <span class="vital-pill combo">🔥 连击 x{{ combo }}</span>
          <span class="vital-pill">🎁 秘籍 {{ progress.collectedTips.length }}</span>
          <button
            type="button"
            class="demo-link-btn"
            :aria-pressed="progress.soundEnabled"
            @click="toggleSound"
          >
            {{ progress.soundEnabled ? '🔊 音效开' : '🔇 静音' }}
          </button>
          <button type="button" class="demo-link-btn" @click="resetZoneBattle">
            ↺ 重置本战区
          </button>
        </div>
      </div>

      <!-- 战区切换条 -->
      <div v-if="zones.length > 1" class="game-chain-strip" role="group" aria-label="选择科技树探险战区">
        <button
          v-for="(z, idx) in zones.slice(0, 6)"
          :key="z.id"
          type="button"
          :class="['chip-btn', idx === zoneIndex ? 'selected' : '']"
          @click="selectZone(idx)"
        >
          {{ z.hasWeakBoss ? '🔥 ' : '' }}{{ z.title }}
        </button>
      </div>

      <!-- 大留白三岛星盘与破甲擂台 -->
      <section class="spacious-expedition-canvas" aria-label="迷雾科技树探险棋盘">
        <div class="spacious-islands-map">
          <!-- 1 号起点炮台岛 -->
          <div class="airy-island conquered">
            <span class="airy-crown">🚩 1 号先修岛 · 已开火</span>
            <div class="airy-icon" aria-hidden="true">{{ currentZone.island1.icon }}</div>
            <div class="airy-title">{{ currentZone.island1.name }}</div>
            <div class="airy-sub">✓ 先修基石就绪</div>
          </div>

          <div class="slim-beam-bridge">
            <span class="slim-beam-tag">{{ currentZone.bridge1Label }}</span>
            <div class="slim-beam-line lit" />
          </div>

          <!-- 2 号迷雾枢纽岛 -->
          <div :class="['airy-island', isConquered ? 'conquered' : 'exploring']">
            <span class="airy-crown">
              {{ isConquered ? '🚩 2 号枢纽岛 · 已占领' : '👆 当前攻占：三连斩破雾' }}
            </span>
            <div class="airy-icon" aria-hidden="true">{{ isConquered ? '🚩' : currentZone.island2.icon }}</div>
            <div class="airy-title">{{ currentZone.island2.name }}</div>
            <div class="airy-sub">
              {{ isConquered ? '✓ 破甲激光已发射' : '🎁 占领掉落秘籍宝箱' }}
            </div>
          </div>

          <div class="slim-beam-bridge">
            <span class="slim-beam-tag">{{ currentZone.bridge2Label }}</span>
            <div :class="['slim-beam-line', isConquered ? 'lit' : '']" />
          </div>

          <!-- 3 号 BOSS 要塞岛 -->
          <div class="airy-island boss">
            <span class="airy-crown">
              {{ isConquered ? '💥 护甲已碎 (0 HP)' : currentZone.hasWeakBoss ? '👹 3 号薄弱 BOSS 要塞' : '🏰 3 号进阶 BOSS 要塞' }}
            </span>
            <div class="airy-icon" aria-hidden="true">{{ isConquered ? '🏳️' : currentZone.boss.icon }}</div>
            <div class="airy-title">{{ currentZone.boss.name }}</div>
            <div class="boss-hp-wrap">
              <div class="boss-hp-label">
                <span>🛡️ 要塞护甲</span>
                <span>{{ bossHp }} / 1000</span>
              </div>
              <div class="boss-hp-track">
                <div class="boss-hp-fill" :style="{ width: `${bossHpPct}%` }" />
              </div>
            </div>
          </div>
        </div>

        <p v-if="feedbackText && !isConquered" :class="['game-inline-feedback', feedbackTone]">
          {{ feedbackText }}
        </p>

        <!-- 状态二：破甲清零后原地切换宝箱开箱与总攻舞台 -->
        <div v-if="isConquered" class="ssr-reveal-stage" role="status" aria-live="polite">
          <span class="ssr-reveal-crown">💥 致命破甲 (-1000 HP) · 掉落考场避坑秘籍宝箱 🎁</span>
          <h4>【{{ currentZone.boss.name }}】护甲已清零！</h4>
          <div class="ssr-formula-pill">
            🎁 {{ currentZone.secretTip }}
          </div>
          <p class="ssr-next-hook">
            你已完整打通「{{ currentZone.island1.name }} ➔ {{ currentZone.island2.name }} ➔ {{ currentZone.boss.name }}」先修航道，现在是收复这座要塞的最佳时机！
          </p>
          <p v-if="mustPracticeFirst" class="game-gate-hint">
            🔒 管理端已启用「练题闭环门禁」：请先点击下方按钮前往专项练习收复该要塞，即可进军下一片战区。
          </p>
          <div class="ssr-actions">
            <button type="button" class="gold-cta" @click="attackBossPractice">
              ⚔️ 趁护甲清零：立即收复 BOSS 要塞
            </button>
            <button
              type="button"
              class="primary-cta"
              :disabled="mustPracticeFirst"
              @click="advanceNextZone"
            >
              进军下一片迷雾战区 ▶
            </button>
          </div>
        </div>

        <!-- 状态一：底部大字号三连斩擂台卡 -->
        <div v-else-if="currentSlash" class="airy-quiz-card">
          <div class="airy-quiz-top">
            <span class="slash-progress-tag">⚔️ {{ currentSlash.label }}</span>
            <span class="chest-hint-inline">🎁 三连斩全中掉落：考场避坑秘籍宝箱</span>
          </div>
          <p class="airy-quiz-q">{{ currentSlash.question }}</p>
          <div class="airy-options-grid">
            <button
              v-for="opt in currentSlash.options"
              :key="opt.letter"
              type="button"
              class="airy-opt-btn"
              @click="answerSlash(opt)"
            >
              <span class="opt-letter">{{ opt.letter }}</span>
              <b class="airy-opt-text">{{ opt.text }}</b>
            </button>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>
