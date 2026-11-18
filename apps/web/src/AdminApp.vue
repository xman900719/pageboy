<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  createClient,
  SCHOOL_SUBJECTS,
  SCHOOL_SUBJECT_LABELS,
  SUBJECTS,
  SUBJECT_LABELS,
  type SchoolSubject,
  type Subject,
} from './api'
import { clearDevAuthArtifacts, markDevLoggedIn, markDevLoggedOut, resolveDevAutoToken } from './devAuth'
import { ADMIN_VIEWS, type AdminViewId } from './copy'
import Notice, { type NoticeData, type NoticeTone } from './components/Notice.vue'
import Gate from './components/Gate.vue'
import AdminView, { type LedgerSubTab } from './views/AdminView.vue'
import SchoolExamCard from './components/admin/SchoolExamCard.vue'
import KnowledgeReviewCard from './components/admin/KnowledgeReviewCard.vue'

// P0-1 安全整改：管理端令牌仅当前页面内存保存，不再写入 localStorage，杜绝同源本地持久化串用风险
const token = ref('')
const subject = ref<Subject>('math')
// 学校考试支持额外的「道法（ethics）」科目，与核心四科隔离管理
const examSubject = ref<SchoolSubject>('math')
const pendingExamId = ref<string | undefined>(undefined)
const pendingExamTab = ref<'scores' | 'papers' | 'items'>('scores')
const ledgerSubTab = ref<LedgerSubTab>('sources')
const view = ref<AdminViewId>('ledger')
const notice = ref<NoticeData | null>(null)

const client = computed(() => (token.value === '' ? null : createClient(token.value, 'admin')))

function notify(text: string, tone: NoticeTone = 'info') {
  notice.value = { text, tone }
}

function clearNotice() {
  notice.value = null
}

onMounted(() => {
  // 清理废弃旧键与历史可能残留的管理端本地存储，确保仅当前会话内存持有，不发生任何凭据持久化
  try {
    localStorage.removeItem('shutong.token')
    localStorage.removeItem('shutong.admin_token')
  } catch {
    // 忽略受沙箱环境限制的异常
  }
  if (!import.meta.env.DEV) {
    clearDevAuthArtifacts('admin')
    return
  }
  const devToken = resolveDevAutoToken('admin', import.meta.env.VITE_DEV_ADMIN_TOKEN)
  if (!devToken) return
  createClient(devToken, 'admin')
    .verify()
    .then(() => {
      if (token.value !== '') return
      notify('已使用开发环境配置令牌自动进入管理端（仅开发模式）。', 'success')
      token.value = devToken
    })
    .catch(() => {
      clearDevAuthArtifacts('admin')
    })
})

async function enter(nextToken: string, _remember?: boolean) {
  const candidate = createClient(nextToken, 'admin')
  await candidate.verify()
  // 严格仅保留在当前页面响应式内存中，不写入 localStorage 与 sessionStorage（仅 Vite DEV 模式支持免重输）
  token.value = nextToken
  if (import.meta.env.DEV) {
    markDevLoggedIn('admin', nextToken)
  }
  notify('已进入综合管理工作台（管理凭据仅内存保存）。', 'success')
}

function signOut() {
  try {
    localStorage.removeItem('shutong.admin_token')
  } catch {
    // 忽略异常
  }
  if (import.meta.env.DEV) {
    markDevLoggedOut('admin')
  } else {
    clearDevAuthArtifacts('admin')
  }
  token.value = ''
  notice.value = null
}
</script>

<template>
  <div class="page admin-page">
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
            <span class="wordmark">书童 · 综合管理工作台</span>
            <span class="tagline">题库 · 学校考试 · 知识点库</span>
          </div>
        </div>
        <div class="masthead-side">
          <span class="pill">本地 · 管理端</span>
          <button type="button" class="ghost small" @click="signOut">
            退出
          </button>
        </div>
      </div>
      <nav class="views" aria-label="管理视图">
        <button
          v-for="entry in ADMIN_VIEWS"
          :key="entry.id"
          type="button"
          :class="view === entry.id ? 'view-tab selected' : 'view-tab'"
          @click="view = entry.id"
        >
          <b>{{ entry.label }}</b>
          <small>{{ entry.hint }}</small>
        </button>
        <div v-if="view === 'exams'" class="subject-row" role="group" aria-label="科目">
          <button
            v-for="id in SCHOOL_SUBJECTS"
            :key="id"
            type="button"
            :class="examSubject === id ? 'subject-chip selected' : 'subject-chip'"
            @click="
              examSubject = id;
              pendingExamId = undefined;
              pendingExamTab = 'scores';
              if (id !== 'ethics') subject = id;
              notify(`已切换到${SCHOOL_SUBJECT_LABELS[id]}。`)
            "
          >
            {{ SCHOOL_SUBJECT_LABELS[id] }}
          </button>
        </div>
        <div v-else class="subject-row" role="group" aria-label="科目">
          <button
            v-for="id in SUBJECTS"
            :key="id"
            type="button"
            :class="subject === id ? 'subject-chip selected' : 'subject-chip'"
            @click="subject = id; examSubject = id; notify(`已切换到${SUBJECT_LABELS[id]}。`)"
          >
            {{ SUBJECT_LABELS[id] }}
          </button>
        </div>
      </nav>
    </header>

    <main v-if="client" class="view" :key="`${view}:${view === 'exams' ? examSubject : subject}`">
      <AdminView
        v-if="view === 'ledger'"
        v-model:sub-tab="ledgerSubTab"
        :client="client"
        :subject="subject"
        :notify="notify"
      />

      <div v-else-if="view === 'exams'" class="admin-exams-full">
        <SchoolExamCard
          :client="client"
          :subject="examSubject"
          :notify="notify"
          :initial-exam-id="pendingExamId"
          :initial-tab="pendingExamTab"
          @select-subject="
            (nextSubj, targetExamId, targetTab = 'items') => {
              pendingExamId = targetExamId
              pendingExamTab = targetTab
              examSubject = nextSubj
              if (nextSubj !== 'ethics') subject = nextSubj
            }
          "
        />
      </div>

      <div v-else-if="view === 'knowledge'" class="admin-knowledge-full">
        <KnowledgeReviewCard
          :client="client"
          :subject="subject"
          :notify="notify"
        />
      </div>
    </main>

    <Gate v-else :on-enter="enter" :allow-remember="false" role="admin" />

    <footer>书童综合管理工作台 · 依据教育部 2022 年版课程标准与北京市中考真题构建 · 仅供管理与教研审核使用</footer>
    <Notice :notice="notice" @close="clearNotice" />
  </div>
</template>

<style scoped>
.admin-exams-full,
.admin-knowledge-full {
  width: 100%;
  max-width: 100%;
}
</style>
