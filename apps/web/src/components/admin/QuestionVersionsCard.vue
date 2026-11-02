<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
  ApiError,
  describeError,
  type ApiClient,
  type QuestionVersion,
  type SourceDetail,
} from '../../api'
import { QUESTION_STATUS_LABELS, excerpt } from '../../copy'
import { KindBadge } from '../../components/Badges'
import Note from '../../components/Note.vue'
import { RichText } from '../../rich'
import type { NoticeTone } from '../../components/Notice.vue'
import { getKnowledgeLabel } from '../../config/knowledge'

type Notify = (text: string, tone?: NoticeTone) => void

const props = defineProps<{
  client: ApiClient
  source: SourceDetail
  notify: Notify
}>()

const emit = defineEmits<{
  (e: 'sourceChanged'): void
}>()

const versions = ref<QuestionVersion[] | null>(null)
const loadError = ref('')
const busyId = ref<string | null>(null)

async function reload() {
  try {
    versions.value = await props.client.sourceQuestions(props.source.id)
    loadError.value = ''
  } catch (e) {
    loadError.value = describeError(e)
  }
}

watch(
  () => props.source,
  () => {
    void reload()
  },
  { immediate: true }
)

const canPublish = computed(
  () => props.source.source.verified && props.source.source.rights_status !== 'unknown'
)

async function review(version: QuestionVersion) {
  busyId.value = version.id
  try {
    await props.client.reviewQuestion(version.id)
    props.notify(`第 ${version.version} 版已标记为人工审核，可以发布。`, 'success')
    await reload()
  } catch (e) {
    props.notify(describeError(e), 'error')
  } finally {
    busyId.value = null
  }
}

async function publish(version: QuestionVersion) {
  busyId.value = version.id
  try {
    await props.client.publishQuestion(version.id)
    props.notify('题目已发布，现在会进入练习与诊断的取题池。', 'success')
    await reload()
    emit('sourceChanged')
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) {
      props.notify(describeError(e), 'caution')
    } else {
      props.notify(describeError(e), 'error')
    }
  } finally {
    busyId.value = null
  }
}
</script>

<template>
  <section class="card" aria-label="题目草稿与发布">
    <div class="card-head">
      <h2>题目草稿与发布</h2>
      <button type="button" class="ghost small" @click="reload">
        刷新
      </button>
    </div>
    <Note v-if="!canPublish" tone="caution">
      发布暂不可用：题源未通过人工审核，或版权状态仍为「未核实」。请先完成上方来源人工审核，再发布题目。
    </Note>
    <p v-if="versions === null" class="muted">
      {{ loadError === '' ? '题目加载中…' : `题目加载失败：${loadError}` }}
    </p>
    <p v-else-if="versions.length === 0" class="muted">
      该题源还没有题目版本：上传附件并完成逐题确认导入后，草稿会出现在这里。
    </p>
    <ul v-else class="version-list">
      <li v-for="v in versions" :key="v.id" class="version-row">
        <div class="version-head">
          <span :class="['badge', `qstatus-${v.status}`]">
            {{ QUESTION_STATUS_LABELS[v.status] }}
          </span>
          <KindBadge :kind="v.kind" />
          <span class="muted tiny">
            v{{ v.version }} · {{ v.question_id.slice(0, 8) }}… · {{ v.max_points }} 分
          </span>
        </div>
        <p class="version-stem">
          <RichText :text="excerpt(v.stem, 90)" />
        </p>
        <div class="version-meta">
          <code v-for="kid in v.knowledge_ids" :key="kid" class="kid">
            {{ getKnowledgeLabel(kid) }} · {{ kid }}
          </code>
          <span v-if="v.group_context" class="muted tiny">含组内材料</span>
          <span v-if="v.media_attachment_id" class="muted tiny">含媒体附件</span>
        </div>
        <div v-if="v.status === 'draft' || v.status === 'reviewed'" class="version-foot">
          <button
            v-if="v.status === 'draft'"
            type="button"
            class="ghost small"
            :disabled="busyId !== null"
            @click="review(v)"
          >
            {{ busyId === v.id ? '提交中…' : '人工审核通过' }}
          </button>
          <template v-if="v.status === 'reviewed'">
            <button
              type="button"
              class="primary small"
              :disabled="!canPublish || busyId !== null"
              :title="canPublish ? undefined : '题源未通过人工审核（或版权未核实），发布暂不可用'"
              @click="publish(v)"
            >
              {{ busyId === v.id ? '发布中…' : '发布' }}
            </button>
            <span v-if="!canPublish" class="version-blocked">
              题源未通过人工审核（或版权未核实），发布暂不可用
            </span>
          </template>
        </div>
      </li>
    </ul>
  </section>
</template>
