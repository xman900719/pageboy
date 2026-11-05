<script setup lang="ts">
import { ref, watch } from 'vue'
import {
  describeError,
  type ApiClient,
  type SchoolExam,
  type Subject,
} from '../../api'
import { EXAM_NOTE, fmtPoints } from '../../copy'
import Note from '../Note.vue'
import type { NoticeTone } from '../Notice.vue'

type Notify = (text: string, tone?: NoticeTone) => void

const props = defineProps<{
  client: ApiClient
  subject: Subject
  notify: Notify
}>()

const exams = ref<SchoolExam[] | null>(null)
const examTitle = ref('')
const examDate = ref(new Date().toISOString().slice(0, 10))
const examEarned = ref<number | ''>('')
const examMax = ref(100)
const savingExam = ref(false)

async function refreshExams() {
  try {
    exams.value = await props.client.schoolExams(props.subject)
  } catch {
    exams.value = null
  }
}

watch(
  [() => props.client, () => props.subject],
  () => {
    void refreshExams()
  },
  { immediate: true }
)

async function saveExam() {
  if (examTitle.value.trim() === '' || examEarned.value === '') {
    props.notify('请填写考试名称与得分。', 'caution')
    return
  }
  savingExam.value = true
  try {
    await props.client.addSchoolExam({
      subject: props.subject,
      title: examTitle.value.trim(),
      examDate: examDate.value,
      earnedPoints: Number(examEarned.value),
      maxPoints: Number(examMax.value),
      confirmedByUser: true,
    })
    props.notify(`学校考试已记录。${EXAM_NOTE}`, 'success')
    examTitle.value = ''
    examEarned.value = ''
    await refreshExams()
  } catch (e) {
    props.notify(describeError(e), 'error')
  } finally {
    savingExam.value = false
  }
}
</script>

<template>
  <section class="card" aria-label="学校考试总分">
    <div class="card-head">
      <h2>学校考试总分</h2>
      <button type="button" class="ghost small" @click="refreshExams">
        刷新
      </button>
    </div>
    <Note tone="caution">{{ EXAM_NOTE }}</Note>
    <div class="exam-form">
      <div class="goal-fields">
        <label>
          考试名称
          <input v-model="examTitle" placeholder="如：学校月考" />
        </label>
        <label>
          考试日期
          <input type="date" v-model="examDate" />
        </label>
        <label>
          获得分数
          <input type="number" :min="0" v-model.number="examEarned" />
        </label>
        <label>
          考试满分
          <input type="number" :min="1" v-model.number="examMax" />
        </label>
      </div>
      <button type="button" class="primary" @click="saveExam" :disabled="savingExam">
        {{ savingExam ? '保存中…' : '记录已核对总分' }}
      </button>
    </div>
    <p v-if="exams === null" class="muted">已录入考试加载中…</p>
    <p v-else-if="exams.length === 0" class="muted">还没有录入过学校考试总分。</p>
    <ul v-else class="exam-list">
      <li v-for="exam in exams" :key="exam.id">
        <span>{{ exam.exam_date }}</span>
        <span class="exam-title">{{ exam.title }}</span>
        <span>
          <b>{{ fmtPoints(exam.earned_points) }} / {{ fmtPoints(exam.max_points) }}</b>
        </span>
        <span :class="['chip', exam.confirmed_by_user ? 'good' : 'wait']">
          {{ exam.confirmed_by_user ? '已核对' : '未核对' }}
        </span>
      </li>
    </ul>
  </section>
</template>
