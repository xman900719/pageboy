<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { createClient, SUBJECTS, SUBJECT_LABELS, type Subject } from './api'
import { clearDevAuthArtifacts, markDevLoggedIn, markDevLoggedOut, resolveDevAutoToken } from './devAuth'
import { VIEWS, type ViewId } from './copy'
import Notice, { type NoticeData, type NoticeTone } from './components/Notice.vue'
import Gate from './components/Gate.vue'
import PracticeView from './views/PracticeView.vue'
import GrowthView from './views/GrowthView.vue'
import KnowledgeGraphView from './views/KnowledgeGraphView.vue'

/** 本机记住的学生端令牌（P0-1 双凭据隔离）：仅当用户在令牌门显式勾选「在本机记住令牌」才写入。
 *  与管理端凭据（shutong.admin_token）彻底脱钩，防止凭据交叉复用。默认行为不变：仅页面内存。 */
const TOKEN_STORE_KEY = 'shutong.student_token'

const token = ref('')
const subject = ref<Subject>('math')
const view = ref<ViewId>('practice')
const focusKnowledgeCode = ref<string | null>(null)
const notice = ref<NoticeData | null>(null)

const client = computed(() => (token.value === '' ? null : createClient(token.value, 'student')))

function notify(text: string, tone: NoticeTone = 'info') {
  notice.value = { text, tone }
}

function clearNotice() {
  notice.value = null
}

function goPracticeWithFocus(code: string) {
  focusKnowledgeCode.value = code
  view.value = 'practice'
}

onMounted(() => {
  // 清理废弃的旧版全局凭据键，避免历史管理员凭据残留
  try {
    localStorage.removeItem('shutong.token')
  } catch {
    // 忽略异常
  }
  const saved = localStorage.getItem(TOKEN_STORE_KEY)
  if (saved) {
    createClient(saved, 'student')
      .verify()
      .then(() => {
        if (token.value !== '') return
        notify('已用本机记住的令牌自动进入。', 'success')
        token.value = saved
      })
      .catch(() => {
        // 令牌已失效（如服务端轮换）：如实清除，不留在本机。
        localStorage.removeItem(TOKEN_STORE_KEY)
      })
    return
  }
  if (import.meta.env.DEV) {
    const devToken = resolveDevAutoToken('student', import.meta.env.VITE_DEV_STUDENT_TOKEN)
    if (!devToken) return
    createClient(devToken, 'student')
      .verify()
      .then(() => {
        if (token.value !== '') return
        notify('已使用开发环境配置令牌自动进入。', 'success')
        token.value = devToken
      })
      .catch(() => {
        clearDevAuthArtifacts('student')
      })
  }
})

async function enter(nextToken: string, remember: boolean) {
  const candidate = createClient(nextToken, 'student')
  await candidate.verify() // throws on invalid token; nothing is kept on failure
  if (remember) localStorage.setItem(TOKEN_STORE_KEY, nextToken)
  else localStorage.removeItem(TOKEN_STORE_KEY)
  token.value = nextToken
  if (import.meta.env.DEV) {
    markDevLoggedIn('student', nextToken)
  }
  notify('已进入私有学习空间。', 'success')
}

function signOut() {
  try {
    localStorage.removeItem('shutong.token')
    localStorage.removeItem(TOKEN_STORE_KEY) // 退出 = 完整登出：本机记住的令牌一并清除
  } catch {
    // 忽略异常
  }
  if (import.meta.env.DEV) {
    markDevLoggedOut('student')
  }
  token.value = ''
  notice.value = null
}
</script>

<template>
  <div class="page">
    <header v-if="client" class="masthead">
      <div class="masthead-row">
        <div class="wordmark-block">
          <img
            class="brand-icon"
            src="/icons/apple-touch-icon.png"
            alt=""
            aria-hidden="true"
            width="44"
            height="44"
          />
          <div>
            <span class="wordmark">书童</span>
            <span class="tagline">目标驱动的中考练习 · 私人学习空间</span>
          </div>
        </div>
        <div class="masthead-side">
          <span class="pill">本地 · 私有</span>
          <button type="button" class="ghost small" @click="signOut">
            退出
          </button>
        </div>
      </div>
      <nav class="views" aria-label="主要视图">
        <button
          v-for="entry in VIEWS"
          :key="entry.id"
          type="button"
          :class="view === entry.id ? 'view-tab selected' : 'view-tab'"
          @click="view = entry.id"
        >
          <b>{{ entry.label }}</b>
          <small>{{ entry.hint }}</small>
        </button>
        <div class="subject-row" role="group" aria-label="科目">
          <button
            v-for="id in SUBJECTS"
            :key="id"
            type="button"
            :class="subject === id ? 'subject-chip selected' : 'subject-chip'"
            @click="subject = id; focusKnowledgeCode = null; notify(`已切换到${SUBJECT_LABELS[id]}。`)"
          >
            {{ SUBJECT_LABELS[id] }}
          </button>
        </div>
      </nav>
    </header>

    <main v-if="client" class="view" :key="`${view}:${subject}`">
      <PracticeView
        v-if="view === 'practice'"
        :client="client"
        :subject="subject"
        :notify="notify"
        :focus-knowledge-code="focusKnowledgeCode"
        @clearFocus="focusKnowledgeCode = null"
        @goView="view = $event"
      />
      <GrowthView
        v-else-if="view === 'growth'"
        :client="client"
        :subject="subject"
        :notify="notify"
        @goPracticeFocus="goPracticeWithFocus"
        @goView="view = $event"
      />
      <KnowledgeGraphView
        v-else-if="view === 'knowledge'"
        :client="client"
        :subject="subject"
        :notify="notify"
        @goPracticeFocus="goPracticeWithFocus"
      />
    </main>

    <Gate v-else :on-enter="enter" role="student" />

    <footer>书童 · 依据教育部 2022 年版课程标准与北京市中考真题构建 · 不作中考分数预测</footer>
    <Notice :notice="notice" @close="clearNotice" />
  </div>
</template>
