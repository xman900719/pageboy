<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import {
  describeError,
  type ApiClient,
  type SchoolCoachDraft,
  type SchoolCoachSession,
} from '../api'
import { RichText } from '../rich'

const props = defineProps<{
  client: ApiClient
  itemId: string
  questionHeading: string
  sceneHint?: string
}>()

const emit = defineEmits<{
  (e: 'backToGuide'): void
  (e: 'applyDraft', draft: SchoolCoachDraft): void
  (e: 'turnsUpdated', count: number): void
}>()

const session = ref<SchoolCoachSession | null>(null)
const loading = ref(false)
const sending = ref(false)
const summarizing = ref(false)
const error = ref('')
const inputText = ref('')
const messagesRef = ref<HTMLElement | null>(null)

const QUICK_REPLIES = [
  '我第一步不知道怎么下手',
  '我觉得是中间步骤算岔了',
  '我大概明白错在哪里了',
]

async function scrollToBottom() {
  await nextTick()
  const el = messagesRef.value
  if (!el) return
  el.scrollTop = el.scrollHeight
}

async function initCoach() {
  loading.value = true
  error.value = ''
  try {
    const existing = await props.client.getSchoolReflectionCoach(props.itemId)
    if (existing.started && existing.turns.length > 0) {
      session.value = existing
    } else {
      session.value = await props.client.startSchoolReflectionCoach(props.itemId, props.sceneHint || null)
    }
    emit('turnsUpdated', session.value.turns.length)
    await scrollToBottom()
  } catch (e) {
    error.value = describeError(e)
  } finally {
    loading.value = false
  }
}

async function sendText(preset?: string) {
  const content = (preset ?? inputText.value).trim()
  if (!content || sending.value) return
  sending.value = true
  error.value = ''
  try {
    session.value = await props.client.sendSchoolReflectionCoachMessage(props.itemId, content)
    if (!preset) inputText.value = ''
    emit('turnsUpdated', session.value.turns.length)
    await scrollToBottom()
  } catch (e) {
    error.value = describeError(e)
  } finally {
    sending.value = false
  }
}

async function summarizeToDraft() {
  if (summarizing.value || !session.value?.can_summarize) return
  summarizing.value = true
  error.value = ''
  try {
    const updated = await props.client.summarizeSchoolReflectionCoach(props.itemId)
    session.value = updated
    if (updated.draft_summary) {
      emit('applyDraft', updated.draft_summary)
    }
  } catch (e) {
    error.value = describeError(e)
  } finally {
    summarizing.value = false
  }
}

watch(
  () => props.itemId,
  () => {
    session.value = null
    inputText.value = ''
    void initCoach()
  },
  { immediate: true },
)
</script>

<template>
  <section class="tutor-drawer chat-window school-coach-panel" :aria-label="`${questionHeading} 书童陪你想`">
    <div class="chat-header">
      <div class="chat-agent">
        <img
          class="ai-avatar-img"
          src="/icons/apple-touch-icon.png"
          alt="我的书童"
          width="34"
          height="34"
        />
        <div class="chat-agent-title">
          <h3>
            <span class="online-dot" aria-hidden="true" />
            书童陪你想
          </h3>
          <span class="muted tiny">聊清思路后一键整理成提醒卡</span>
        </div>
      </div>
      <button type="button" class="ghost small" @click="emit('backToGuide')">
        返回三步卡片
      </button>
    </div>

    <div v-if="loading" class="chat-loading-box">
      我的书童正在看题，马上和你一起理一理…
    </div>

    <div v-else-if="error && !session" class="chat-loading-box">
      <p style="margin: 0 0 8px;">{{ error }}</p>
      <div style="display: flex; gap: 8px; flex-wrap: wrap; justify-content: center;">
        <button type="button" class="primary small" @click="initCoach">
          再试一次
        </button>
        <button type="button" class="ghost small" @click="emit('backToGuide')">
          改用三步卡片
        </button>
      </div>
    </div>

    <template v-if="session">
      <div ref="messagesRef" class="tutor-turns chat-messages" aria-live="polite">
        <div
          v-for="turn in session.turns"
          :key="turn.id"
          :class="['msg-row', turn.role === 'assistant' ? 'ai' : 'stu']"
        >
          <img
            v-if="turn.role === 'assistant'"
            class="msg-avatar-img"
            src="/icons/apple-touch-icon.png"
            alt=""
            aria-hidden="true"
            width="28"
            height="28"
          />
          <span v-else class="msg-avatar" aria-hidden="true">我</span>
          <div class="msg-bubble-wrap">
            <div class="msg-sender">
              <b>{{ turn.role === 'assistant' ? '我的书童' : '我' }}</b>
              <span v-if="turn.sanitized_guard_triggered" class="guard-pill">引导模式</span>
            </div>
            <p class="msg-bubble">
              <RichText :text="turn.content" />
            </p>
          </div>
        </div>
        <div v-if="sending" class="msg-row ai">
          <img class="msg-avatar-img" src="/icons/apple-touch-icon.png" alt="" aria-hidden="true" width="28" height="28" />
          <div class="msg-bubble-wrap">
            <p class="msg-bubble muted">正在想下一个小问题…</p>
          </div>
        </div>
      </div>

      <p v-if="error" class="reflection-reject-alert" role="alert">{{ error }}</p>

      <div class="quick-replies">
        <button
          v-for="qr in QUICK_REPLIES"
          :key="qr"
          type="button"
          class="chip-btn starter"
          :disabled="sending || session.user_turn_count >= session.max_user_turns"
          @click="sendText(qr)"
        >
          {{ qr }}
        </button>
      </div>

      <form class="chat-input-row" @submit.prevent="sendText()">
        <input
          v-model="inputText"
          type="text"
          maxlength="400"
          :aria-label="`${questionHeading} 给书童发消息`"
          :disabled="sending || session.user_turn_count >= session.max_user_turns"
          placeholder="说说你当时的想法，书童陪你一步步找卡点…"
        />
        <button
          type="submit"
          class="primary small"
          :disabled="sending || !inputText.trim() || session.user_turn_count >= session.max_user_turns"
        >
          {{ sending ? '发送中…' : '发送' }}
        </button>
      </form>

      <div class="coach-summarize-bar">
        <span v-if="!session.can_summarize" class="muted tiny">
          和书童聊满 2 轮（说出自己的思路）后，可一键整理成提醒卡草稿（当前 {{ session.user_turn_count }}/2）
        </span>
        <button
          v-else
          type="button"
          class="primary small"
          :disabled="summarizing || sending"
          @click="summarizeToDraft"
        >
          {{ summarizing ? '正在按你的话整理草稿…' : '把刚才聊明白的整理成提醒卡草稿 →' }}
        </button>
      </div>
    </template>
  </section>
</template>
