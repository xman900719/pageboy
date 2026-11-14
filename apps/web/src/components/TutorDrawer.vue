<script setup lang="ts">
import { ref, watch } from 'vue'
import {
  describeError,
  type ApiClient,
  type TutorSession,
  type WrongQuestionSummary,
} from '../api'
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

const QUICK_REPLIES = [
  '我先梳理一下题目给出的已知条件',
  '我选这个答案是因为没看清关键词，提示我下一步检查什么？',
  '这道题具体卡在解题的第二步了',
]

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
  } catch (e) {
    error.value = describeError(e)
  } finally {
    sending.value = false
  }
}

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
  <section class="tutor-drawer" aria-label="AI 错题引导讲解">
    <div class="tutor-head">
      <div>
        <span class="eyebrow">苏格拉底启发式引导 · 不直接给答案</span>
        <h3>错题 AI 引导订正</h3>
      </div>
      <button type="button" class="ghost small" @click="emit('close')">
        收起讲解
      </button>
    </div>

    <div class="tutor-question-brief">
      <div class="tutor-tags">
        <span
          v-for="title in wrongItem.knowledge_titles"
          :key="title"
          class="chip"
        >
          {{ title }}
        </span>
        <span class="chip bad">你的作答：{{ wrongItem.student_answer }}</span>
      </div>
      <p class="tutor-stem">
        <RichText :text="wrongItem.stem" />
      </p>
    </div>

    <div v-if="loading" class="tutor-loading">
      正在请 AI 老师阅读题目与你的作答思路，生成第一步引导问题…
    </div>

    <div v-else-if="error && !session" class="tutor-error-box">
      <p>{{ error }}</p>
      <button type="button" class="primary small" @click="initTutor">
        重新发起引导
      </button>
    </div>

    <div v-if="session" class="tutor-chat">
      <div class="tutor-turns" aria-live="polite">
        <div
          v-for="turn in session.turns"
          :key="turn.id"
          :class="['tutor-bubble', turn.role === 'assistant' ? 'ai' : 'student']"
        >
          <div class="bubble-meta">
            <b>{{ turn.role === 'assistant' ? '书童引导' : '我的思考' }}</b>
            <span v-if="turn.sanitized_guard_triggered" class="guard-pill">已开启防直接泄题保护</span>
          </div>
          <p class="bubble-text">
            <RichText :text="turn.content" />
          </p>
        </div>
      </div>

      <div class="quick-replies" aria-label="快捷思考回复">
        <button
          v-for="preset in QUICK_REPLIES"
          :key="preset"
          type="button"
          class="chip-btn"
          :disabled="sending"
          @click="sendText(preset)"
        >
          {{ preset }}
        </button>
      </div>

      <p v-if="error" class="form-error">{{ error }}</p>

      <form class="tutor-input-row" @submit.prevent="sendText()">
        <label class="sr-only" for="tutor-reply-input">输入你的思考或疑问</label>
        <textarea
          id="tutor-reply-input"
          v-model="draft"
          rows="2"
          :disabled="sending"
          placeholder="写下你的推理步骤、卡住的地方或新发现的线索…"
        />
        <button
          type="submit"
          class="primary"
          :disabled="sending || !draft.trim()"
        >
          {{ sending ? '思考中…' : '发送思路' }}
        </button>
      </form>
    </div>
  </section>
</template>
