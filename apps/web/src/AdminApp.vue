<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { createClient, SUBJECTS, SUBJECT_LABELS, type Subject, type PoolHealth } from './api'
import { ADMIN_VIEWS, type AdminViewId } from './copy'
import Notice, { type NoticeData, type NoticeTone } from './components/Notice.vue'
import Gate from './components/Gate.vue'
import AdminView from './views/AdminView.vue'
import PoolHealthCard from './components/PoolHealthCard.vue'
import SchoolExamCard from './components/admin/SchoolExamCard.vue'
import Note from './components/Note.vue'

const TOKEN_STORE_KEY = 'shutong.token'

const token = ref('')
const subject = ref<Subject>('math')
const view = ref<AdminViewId>('ledger')
const notice = ref<NoticeData | null>(null)
const poolHealth = ref<PoolHealth | null>(null)
const poolLoading = ref(false)

const client = computed(() => (token.value === '' ? null : createClient(token.value)))

function notify(text: string, tone: NoticeTone = 'info') {
  notice.value = { text, tone }
}

function clearNotice() {
  notice.value = null
}

async function loadPoolHealth() {
  if (!client.value) return
  poolLoading.value = true
  try {
    poolHealth.value = await client.value.poolHealth(subject.value)
  } catch {
    poolHealth.value = null
  } finally {
    poolLoading.value = false
  }
}

watch(
  [() => client.value, () => subject.value, () => view.value],
  () => {
    if (view.value === 'health') {
      void loadPoolHealth()
    }
  },
  { immediate: true }
)

onMounted(() => {
  const saved = localStorage.getItem(TOKEN_STORE_KEY)
  if (saved === null || saved === '') return
  createClient(saved)
    .verify()
    .then(() => {
      if (token.value !== '') return
      notify('已用本机记住的令牌自动进入管理台。', 'success')
      token.value = saved
    })
    .catch(() => {
      localStorage.removeItem(TOKEN_STORE_KEY)
    })
})

async function enter(nextToken: string, remember: boolean) {
  const candidate = createClient(nextToken)
  await candidate.verify()
  if (remember) localStorage.setItem(TOKEN_STORE_KEY, nextToken)
  else localStorage.removeItem(TOKEN_STORE_KEY)
  token.value = nextToken
  notify('已进入综合管理工作台。', 'success')
}

function signOut() {
  localStorage.removeItem(TOKEN_STORE_KEY)
  token.value = ''
  notice.value = null
}
</script>

<template>
  <div class="page admin-page">
    <header v-if="client" class="masthead">
      <div class="masthead-row">
        <div class="wordmark-block">
          <span class="seal" aria-hidden="true">
            管
          </span>
          <div>
            <span class="wordmark">书童 · 综合管理工作台</span>
            <span class="tagline">题库审核 · 题库体检 · 真实校考台账</span>
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
        <div class="subject-row" role="group" aria-label="科目">
          <button
            v-for="id in SUBJECTS"
            :key="id"
            type="button"
            :class="subject === id ? 'subject-chip selected' : 'subject-chip'"
            @click="subject = id; notify(`已切换到${SUBJECT_LABELS[id]}。`)"
          >
            {{ SUBJECT_LABELS[id] }}
          </button>
        </div>
      </nav>
    </header>

    <main v-if="client" class="view" :key="`${view}:${subject}`">
      <AdminView
        v-if="view === 'ledger'"
        :client="client"
        :subject="subject"
        :notify="notify"
      />

      <div v-else-if="view === 'health'" class="home-grid">
        <section class="card" aria-label="题库体检">
          <div class="card-head">
            <h2>题库体检大屏</h2>
            <button type="button" class="ghost small" @click="loadPoolHealth">
              刷新
            </button>
          </div>
          <PoolHealthCard v-if="poolHealth" :data="poolHealth" />
          <p v-else class="muted">{{ poolLoading ? '加载中…' : '题库体检加载失败。' }}</p>
        </section>
        <div class="home-side">
          <Note title="题库体检说明">
            题库体检反映当前科目各知识点的题目储备总量、未见题余量以及已被练习或诊断消耗的曝光情况。请确保各知识点均有充足的未见题储备，以支持客观阶段诊断。
          </Note>
        </div>
      </div>

      <div v-else-if="view === 'exams'" class="home-grid">
        <SchoolExamCard
          :client="client"
          :subject="subject"
          :notify="notify"
        />
        <div class="home-side">
          <Note title="校考录入说明">
            学校考试（如阶段月考、期中、期末试卷）由家长或管理员依据纸质答卷如实录入总得分。总分仅用于阶段记录，不作为中考预测，亦不虚构单个考点得分。
          </Note>
        </div>
      </div>
    </main>

    <Gate v-else :on-enter="enter" />

    <footer>开发管理版 · 演示数据均为虚构测试数据 · 仅供管理与审核使用</footer>
    <Notice :notice="notice" @close="clearNotice" />
  </div>
</template>
