<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import {
  describeError,
  type ApiClient,
  type TutorSession,
  type WrongQuestionSummary,
} from '../api'
import { resolveAnswerContent } from '../copy'
import { RichText } from '../rich'

const props = defineProps<{
  client: ApiClient
  wrongItem: WrongQuestionSummary
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const session = ref<TutorSession | null>(null)
const loading = ref(false)
const sending = ref(false)
const error = ref('')
const draft = ref('')
const messagesRef = ref<HTMLElement | null>(null)

const QUICK_REPLIES = [
  '为什么我选的答案不对？',
  '这道题第一步该怎么想？',
  '我明白了，再考我一个小问题',
]

async function scrollToBottom() {
  await nextTick()
  const el = messagesRef.value
  if (!el) return
  el.scrollTop = el.scrollHeight
}

async function initTutor() {
  loading.value = true
  error.value = ''
  try {
    const existing = await props.client.getTutorForAttempt(props.wrongItem.attempt_id)
    if (existing.started && existing.turns.length > 0) {
      session.value = existing
    } else {
      session.value = await props.client.startTutorForAttempt(props.wrongItem.attempt_id)
    }
    await scrollToBottom()
  } catch (e) {
    error.value = describeError(e)
  } finally {
    loading.value = false
  }
}

async function sendText(text?: string) {
  const content = (text ?? draft.value).trim()
  if (!content || !session.value?.id || sending.value) return
  sending.value = true
  error.value = ''
  try {
    session.value = await props.client.sendTutorMessage(session.value.id, content)
    if (!text) draft.value = ''
    await scrollToBottom()
  } catch (e) {
    error.value = describeError(e)
  } finally {
    sending.value = false
  }
}

watch(
  () => session.value?.turns.length ?? 0,
  () => {
    void scrollToBottom()
  }
)

watch(
  () => props.wrongItem.attempt_id,
  () => {
    session.value = null
    draft.value = ''
    void initTutor()
  },
  { immediate: true }
)
</script>

<template>
  <section class="tutor-drawer chat-window" aria-label="AI 错题引导讲解">
    <div class="chat-header">
      <div class="chat-agent">
        <img
          class="ai-avatar-img"
          src="/icons/apple-touch-icon.png"
          alt="我的书童"
          width="36"
          height="36"
        />
        <div class="chat-agent-title">
          <h3>
            <span class="online-dot" aria-hidden="true" />
            我的书童
          </h3>
          <div class="chat-answer-pills">
            <span class="chip bad">
              错答：<RichText :text="resolveAnswerContent(wrongItem.student_answer, wrongItem.options)" />
            </span>
            <span v-if="wrongItem.correct_answer" class="chip good">
              正解：<RichText :text="resolveAnswerContent(wrongItem.correct_answer, wrongItem.options)" />
            </span>
          </div>
        </div>
      </div>
      <button type="button" class="ghost small" @click="emit('close')">
        收起
      </button>
    </div>

    <slot name="banner" />

    <div v-if="loading" class="chat-loading-box">
      我的书童正在看题，马上开始对话…
    </div>

    <div v-else-if="error && !session" class="chat-loading-box">
      <p style="margin: 0 0 8px;">{{ error }}</p>
      <button type="button" class="primary small" @click="initTutor">
        重新唤醒我的书童
      </button>
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
      </div>

      <div class="chat-quick-bar" aria-label="快捷思考回复">
        <button
          v-for="preset in QUICK_REPLIES"
          :key="preset"
          type="button"
          class="quick-chip"
          :disabled="sending"
          @click="sendText(preset)"
        >
          {{ preset }}
        </button>
      </div>

      <p v-if="error" class="form-error" style="padding: 0 12px;">{{ error }}</p>

      <form class="chat-composer" @submit.prevent="sendText()">
        <label class="sr-only" for="tutor-reply-input">跟我的书童对话</label>
        <textarea
          id="tutor-reply-input"
          v-model="draft"
          rows="1"
          :disabled="sending"
          placeholder="跟我的书童说说你的想法，或哪里卡住了…"
        />
        <button
          type="submit"
          class="chat-send-btn"
          :disabled="sending || !draft.trim()"
        >
          {{ sending ? '回复中…' : '发送' }}
        </button>
      </form>
    </template>
  </section>
</template>
