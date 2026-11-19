<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import type { KnowledgeGameSubjectConfig, KnowledgeGraph, Subject } from '../api'
import { SUBJECT_LABELS } from '../api'
import { CanvasParticleFx, playGameSound } from '../config/gameFxEngine'
import {
  buildAlchemyCampaign,
  loadSubjectGameProgress,
  resolveRankSummary,
  saveSubjectGameProgress,
  type AlchemyCard,
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
const chainIndex = ref(0)
const stepIndex = ref(0)

const slot1Filled = ref(false)
const slot2Filled = ref(false)
const catalystFilled = ref(false)
const shields = ref<number>(props.config.initial_shields)
const combo = ref(0)
const feedbackText = ref('')
const feedbackTone = ref<'good' | 'warn' | ''>('')
const practicedTargetCodes = ref<Set<string>>(new Set())

const chains = computed(() => buildAlchemyCampaign(props.graph, props.config))

const currentChain = computed(() => {
  if (chains.value.length === 0) return null
  return chains.value[chainIndex.value % chains.value.length]
})

const currentStep = computed(() => {
  if (!currentChain.value || currentChain.value.steps.length === 0) return null
  return currentChain.value.steps[stepIndex.value % currentChain.value.steps.length]
})

const allFilled = computed(() => slot1Filled.value && slot2Filled.value && catalystFilled.value)

const rank = computed(() => resolveRankSummary(progress.value.exp))

const heartsDisplay = computed(() => {
  const total = props.config.initial_shields
  const alive = Math.max(0, Math.min(total, shields.value))
  return '❤️'.repeat(alive) + '🖤'.repeat(Math.max(0, total - alive))
})

const mustPracticeFirst = computed(() => {
  if (props.config.practice_gate !== 'required' || !currentStep.value) return false
  return !practicedTargetCodes.value.has(currentStep.value.targetCode)
})

function syncStepInitialSlots() {
  const st = currentStep.value
  slot1Filled.value = Boolean(st?.slot1.fromPrevStep)
  slot2Filled.value = false
  catalystFilled.value = false
  feedbackText.value = ''
  feedbackTone.value = ''
}

function reloadFromConfig() {
  progress.value = loadSubjectGameProgress(props.subject, props.config.reset_epoch)
  shields.value = props.config.initial_shields
  combo.value = 0
  chainIndex.value = 0
  stepIndex.value = 0
  practicedTargetCodes.value = new Set()
  syncStepInitialSlots()
}

watch(
  [() => props.subject, () => props.config.reset_epoch, () => props.config.initial_shields, () => props.config.prioritize_weak],
  () => {
    reloadFromConfig()
  },
)

onMounted(() => {
  fx.attach(fxCanvasRef.value)
  syncStepInitialSlots()
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

function isCardUsed(card: AlchemyCard): boolean {
  if (card.role === 'slot1') return slot1Filled.value
  if (card.role === 'slot2') return slot2Filled.value
  if (card.role === 'catalyst') return catalystFilled.value
  return false
}

function playCard(card: AlchemyCard) {
  if (!currentStep.value || allFilled.value) return

  if (card.role === 'trap') {
    shields.value = Math.max(1, shields.value - 1)
    combo.value = 0
    feedbackText.value = `💣 误触干扰陷阱「${card.name}」！炉温波动损耗 1 颗护盾，请对照目标选择前置基石与内在法则。`
    feedbackTone.value = 'warn'
    playGameSound('error', progress.value.soundEnabled)
    triggerShake()
    fx.burst('red')
    return
  }

  if (isCardUsed(card)) return

  if (card.role === 'slot1') slot1Filled.value = true
  if (card.role === 'slot2') slot2Filled.value = true
  if (card.role === 'catalyst') catalystFilled.value = true

  combo.value += 1
  const nowComplete = slot1Filled.value && slot2Filled.value && catalystFilled.value

  if (nowComplete) {
    const bonusExp = combo.value >= 4 ? 120 : 80
    const nextUnlocked = progress.value.unlockedRecipeIds.includes(currentStep.value.id)
      ? progress.value.unlockedRecipeIds
      : [...progress.value.unlockedRecipeIds, currentStep.value.id]
    progress.value = {
      ...progress.value,
      exp: progress.value.exp + bonusExp,
      bestCombo: Math.max(progress.value.bestCombo, combo.value),
      unlockedRecipeIds: nextUnlocked,
    }
    saveSubjectGameProgress(props.subject, progress.value)
    feedbackText.value = ''
    feedbackTone.value = 'good'
    playGameSound('win', progress.value.soundEnabled)
    fx.burst('gold')
  } else {
    feedbackText.value = `✓ 「${card.name}」已嵌入合成底座！`
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

function selectChain(idx: number) {
  chainIndex.value = idx
  stepIndex.value = 0
  shields.value = props.config.initial_shields
  syncStepInitialSlots()
}

function advanceNextRecipe() {
  if (!currentChain.value) return
  if (stepIndex.value + 1 < currentChain.value.steps.length) {
    stepIndex.value += 1
  } else {
    chainIndex.value = (chainIndex.value + 1) % chains.value.length
    stepIndex.value = 0
    shields.value = props.config.initial_shields
  }
  syncStepInitialSlots()
}

function launchTargetedPractice() {
  if (!currentStep.value) return
  practicedTargetCodes.value = new Set([...practicedTargetCodes.value, currentStep.value.targetCode])
  emit('goPracticeFocus', currentStep.value.targetCode)
}
</script>

<template>
  <div class="game-container-root" :class="{ shaking }" aria-label="知识合成工坊游戏">
    <canvas ref="fxCanvasRef" class="game-fx-canvas" aria-hidden="true" />

    <div v-if="!currentChain || !currentStep" class="game-empty-state">
      <p>当前{{ SUBJECT_LABELS[subject] }}知识图谱节点不足，暂无可生成的合成配方。</p>
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
          <span class="vital-pill">📖 配方 {{ progress.unlockedRecipeIds.length }}</span>
          <button
            type="button"
            class="demo-link-btn"
            :aria-pressed="progress.soundEnabled"
            @click="toggleSound"
          >
            {{ progress.soundEnabled ? '🔊 音效开' : '🔇 静音' }}
          </button>
          <button type="button" class="demo-link-btn" @click="syncStepInitialSlots">
            ↺ 重置本阶
          </button>
        </div>
      </div>

      <!-- 关卡切换条 -->
      <div v-if="chains.length > 1" class="game-chain-strip" role="group" aria-label="选择合成进化链">
        <button
          v-for="(ch, idx) in chains.slice(0, 6)"
          :key="ch.id"
          type="button"
          :class="['chip-btn', idx === chainIndex ? 'selected' : '']"
          @click="selectChain(idx)"
        >
          {{ ch.hasWeakTarget ? '🎯 ' : '' }}{{ ch.title }}
        </button>
      </div>

      <!-- 大留白金字塔合成舞台 -->
      <section class="spacious-alchemy-canvas" aria-label="知识合成工坊操作舞台">
        <div class="target-focal-header">
          <div class="evo-stepper-minimal">
            <span
              v-for="(st, sIdx) in currentChain.steps"
              :key="st.id"
              :class="[
                sIdx < stepIndex ? 'done' : sIdx === stepIndex ? 'cur' : st.rarity === 'ssr' ? 'ssr' : '',
              ]"
            >
              {{ sIdx + 1 }}. {{ st.targetName }}
              <template v-if="sIdx < stepIndex"> ✓</template>
              <template v-if="sIdx < currentChain.steps.length - 1"> ➔ </template>
            </span>
          </div>

          <h3 class="target-main-title">
            <span>🔮 合成目标：{{ currentStep.targetName }}</span>
            <span :class="['target-rarity-pill', currentStep.rarity]">{{ currentStep.rarityLabel }}</span>
          </h3>
        </div>

        <!-- 反馈提示条 -->
        <p v-if="feedbackText && !allFilled" :class="['game-inline-feedback', feedbackTone]">
          {{ feedbackText }}
        </p>

        <!-- 状态二：三槽集齐原地切换独占爆卡舞台 -->
        <div v-if="allFilled" class="ssr-reveal-stage" role="status" aria-live="polite">
          <span class="ssr-reveal-crown">
            ✨ 完美合成 · 已解锁 {{ currentStep.rarityLabel }} 新卡
          </span>
          <div class="ssr-crown-emoji" aria-hidden="true">👑</div>
          <h4>{{ currentStep.targetName }}</h4>
          <div class="ssr-formula-pill">
            {{ currentStep.slot1.name }} ＋ {{ currentStep.slot2.name }} ──[ {{ currentStep.catalyst.name }} ]──▶ {{ currentStep.targetName }}
          </div>
          <p class="ssr-next-hook">
            <template v-if="stepIndex + 1 < currentChain.steps.length">
              🔥 <b>滚雪球进化就绪：</b>这张新卡将自动载入下一回合 1 号底座，用于合成<b>【{{ currentChain.steps[stepIndex + 1].targetName }}】</b>！
            </template>
            <template v-else>
              🎉 你已打通本条知识进化链的全部合成配方（{{ currentStep.targetDesc }}）！
            </template>
          </p>
          <p v-if="mustPracticeFirst" class="game-gate-hint">
            🔒 管理端已启用「练题闭环门禁」：请先点击下方按钮前往专项练习巩固此考点，即可继续下一阶。
          </p>
          <div class="ssr-actions">
            <button type="button" class="primary-cta" @click="launchTargetedPractice">
              🎯 趁热做专项练习巩固
            </button>
            <button
              type="button"
              class="gold-cta"
              :disabled="mustPracticeFirst"
              @click="advanceNextRecipe"
            >
              {{ stepIndex + 1 < currentChain.steps.length ? '🔥 带着新卡冲击下一阶 ▶' : '解锁下一条合成链 ▶' }}
            </button>
          </div>
        </div>

        <!-- 状态一：中间 3 宽敞底座 + 底部 4 极简手牌 -->
        <template v-else>
          <div class="three-pedestals-row">
            <div :class="['spacious-pedestal', slot1Filled ? 'filled rare-origin' : 'active-focus']">
              <span class="slot-badge">
                {{ slot1Filled ? (currentStep.slot1.fromPrevStep ? '🔵 上轮合成卡' : '✓ 前置基石 ①') : '👆 第 1 步：基石 ①' }}
              </span>
              <div class="slot-emoji" aria-hidden="true">{{ slot1Filled ? currentStep.slot1.icon : '➕' }}</div>
              <div class="slot-name">{{ slot1Filled ? currentStep.slot1.name : '待放入前置基石 ①' }}</div>
              <div class="slot-hint">{{ slot1Filled ? currentStep.slot1.hint : '点击下方手牌投入' }}</div>
            </div>

            <div :class="['plus-sign', slot1Filled && slot2Filled ? 'lit' : '']" aria-hidden="true">＋</div>

            <div :class="['spacious-pedestal', slot2Filled ? 'filled' : (slot1Filled ? 'active-focus' : '')]">
              <span class="slot-badge">{{ slot2Filled ? '✓ 前置基石 ②' : '👆 第 2 步：基石 ②' }}</span>
              <div class="slot-emoji" aria-hidden="true">{{ slot2Filled ? currentStep.slot2.icon : '➕' }}</div>
              <div class="slot-name">{{ slot2Filled ? currentStep.slot2.name : '待放入前置基石 ②' }}</div>
              <div class="slot-hint">{{ slot2Filled ? '已就绪' : currentStep.slot2.hint }}</div>
            </div>

            <div :class="['plus-sign', catalystFilled ? 'lit' : '']" aria-hidden="true">＋</div>

            <div :class="['spacious-pedestal', catalystFilled ? 'filled catalyst' : (slot1Filled && slot2Filled ? 'active-focus' : '')]">
              <span class="slot-badge">{{ catalystFilled ? '⚡ 内在转化法则' : '👆 第 3 步：关系法则' }}</span>
              <div class="slot-emoji" aria-hidden="true">{{ catalystFilled ? '⚡' : '🔑' }}</div>
              <div class="slot-name">{{ catalystFilled ? currentStep.catalyst.name : '待注入内在转化法则' }}</div>
              <div class="slot-hint">{{ catalystFilled ? '已激活' : currentStep.catalyst.hint }}</div>
            </div>
          </div>

          <div class="clean-hand-area">
            <div class="clean-hand-label">🃏 点击下方手牌投入发光底座（排除 1 张 💣 干扰陷阱卡）</div>
            <div class="clean-hand-grid">
              <button
                v-for="card in currentStep.cards"
                :key="card.id"
                type="button"
                :disabled="isCardUsed(card)"
                :class="[
                  'clean-card',
                  card.isCatalyst ? 'catalyst-card' : '',
                  card.isTrap ? 'trap-card' : '',
                  card.isRareOrigin ? 'rare-origin' : '',
                  isCardUsed(card) ? 'used' : '',
                ]"
                @click="playCard(card)"
              >
                <span class="clean-card-tag">{{ card.tag }}</span>
                <span class="clean-card-emoji" aria-hidden="true">{{ card.icon }}</span>
                <span class="clean-card-title">{{ card.name }}</span>
              </button>
            </div>
          </div>
        </template>
      </section>
    </template>
  </div>
</template>
