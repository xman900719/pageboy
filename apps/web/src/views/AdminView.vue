<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
  describeError,
  SUBJECTS,
  SUBJECT_LABELS,
  type ApiClient,
  type RightsStatus,
  type SourceDetail,
  type Subject,
} from '../api'
import { ADMIN_PIPELINE_NOTE, RIGHTS_STATUS_LABELS } from '../copy'
import Note from '../components/Note.vue'
import type { NoticeTone } from '../components/Notice.vue'
import SourceReviewCard from '../components/admin/SourceReviewCard.vue'
import AttachmentCard from '../components/admin/AttachmentCard.vue'
import QuestionVersionsCard from '../components/admin/QuestionVersionsCard.vue'

type Notify = (text: string, tone?: NoticeTone) => void

const props = defineProps<{
  client: ApiClient
  subject: Subject
  notify: Notify
}>()

const sources = ref<SourceDetail[] | null>(null)
const loadError = ref('')
const selectedId = ref<string | null>(null)
const newTitle = ref('')
const newSubject = ref<Subject>(props.subject)
const newRights = ref<RightsStatus>('unknown')
const creating = ref(false)
const formError = ref('')

async function refresh() {
  try {
    const list = await props.client.adminSources()
    sources.value = list
    loadError.value = ''
    selectedId.value =
      selectedId.value !== null && list.some(s => s.id === selectedId.value)
        ? selectedId.value
        : (list[0]?.id ?? null)
  } catch (e) {
    loadError.value = describeError(e)
  }
}

watch(
  () => props.client,
  () => {
    void refresh()
  },
  { immediate: true }
)

const selected = computed(
  () => sources.value?.find(s => s.id === selectedId.value) ?? null
)

async function createSource() {
  if (newTitle.value.trim() === '') {
    formError.value = '请填写题源标题。'
    return
  }
  creating.value = true
  formError.value = ''
  try {
    const created = await props.client.addSource({
      title: newTitle.value.trim(),
      subject: newSubject.value,
      rightsStatus: newRights.value,
    })
    props.notify(`题源已登记（${created.id.slice(0, 8)}…）。下一步：上传附件并完成来源人工审核。`, 'success')
    newTitle.value = ''
    await refresh()
    selectedId.value = created.id
  } catch (e) {
    formError.value = describeError(e)
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <Note tone="discipline" title="人工审核流水线">
    {{ ADMIN_PIPELINE_NOTE }}
  </Note>

  <section class="card" aria-label="题源台账">
    <div class="card-head">
      <h2>题源台账</h2>
      <button type="button" class="ghost small" @click="refresh">
        刷新
      </button>
    </div>
    <p class="muted">
      登记试卷 / 教辅来源，逐个完成附件上传、来源人工审核与题目发布。数据只保存在本机私有库。
    </p>
    <p v-if="sources === null" class="muted">
      {{ loadError === '' ? '题源加载中…' : `题源加载失败：${loadError}` }}
    </p>
    <p v-else-if="sources.length === 0" class="muted">
      还没有题源：用下方表单登记第一个来源（示例文案均为虚构测试数据）。
    </p>
    <ul v-else class="source-list">
      <li
        v-for="s in sources"
        :key="s.id"
        :class="['source-item', s.id === selectedId ? 'selected' : '']"
      >
        <button
          type="button"
          class="source-pick"
          :aria-pressed="s.id === selectedId"
          @click="selectedId = s.id"
        >
          <span class="source-title">{{ s.source.title }}</span>
          <span class="muted tiny">
            {{ SUBJECT_LABELS[s.source.subject] }} · {{ s.attachments.length }} 个附件 · {{ s.reviews.length }} 次审核记录
          </span>
        </button>
        <span :class="['chip', s.source.verified ? 'good' : 'wait']">
          {{ s.source.verified ? '已人工审核' : '未审核' }}
        </span>
      </li>
    </ul>

    <form class="admin-form" @submit.prevent="createSource">
      <div class="admin-grid">
        <label>
          题源标题
          <input
            v-model="newTitle"
            placeholder="虚构测试数据：2025 区模拟卷（数学）"
            maxlength="256"
          />
        </label>
        <label>
          科目
          <select v-model="newSubject">
            <option v-for="id in SUBJECTS" :key="id" :value="id">
              {{ SUBJECT_LABELS[id] }}
            </option>
          </select>
        </label>
        <label class="wide">
          版权状态
          <select v-model="newRights">
            <option
              v-for="id in (Object.keys(RIGHTS_STATUS_LABELS) as RightsStatus[])"
              :key="id"
              :value="id"
            >
              {{ RIGHTS_STATUS_LABELS[id] }}
            </option>
          </select>
        </label>
      </div>
      <p class="muted tiny">
        版权状态为「未核实」的题源，即使完成人工审核也无法发布题目；请先补全授权或核查依据。
      </p>
      <p v-if="formError" class="form-error">{{ formError }}</p>
      <button type="submit" class="primary" :disabled="creating">
        {{ creating ? '登记中…' : '新建题源' }}
      </button>
    </form>
  </section>

  <div v-if="selected" :key="selected.id">
    <SourceReviewCard
      :client="client"
      :source="selected"
      :notify="notify"
      @reviewed="refresh"
    />
    <AttachmentCard
      :client="client"
      :source="selected"
      :notify="notify"
      @changed="refresh"
    />
    <QuestionVersionsCard
      :client="client"
      :source="selected"
      :notify="notify"
      @sourceChanged="refresh"
    />
  </div>
</template>
