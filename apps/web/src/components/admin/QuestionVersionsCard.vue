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
import HelpBubble from '../../components/HelpBubble.vue'
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

const pendingVersions = computed(
  () => (versions.value ?? []).filter(v => v.status !== 'published')
)
const publishedVersions = computed(
  () => (versions.value ?? []).filter(v => v.status === 'published')
)
// 仅单侧有批量题目时切为纵向堆叠 + 多列网格，避免半宽列挤成超长列表
const singleActiveSide = computed(
  () =>
    (pendingVersions.value.length === 0 && publishedVersions.value.length >= 3) ||
    (publishedVersions.value.length === 0 && pendingVersions.value.length >= 3)
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
      <div class="card-head-tools">
        <HelpBubble
          :tone="canPublish ? 'teal' : 'caution'"
          compact
          title="发布门禁与版本规则"
          :label="canPublish ? '发布规则' : '发布受限说明'"
        >
          <ul>
            <li v-if="!canPublish">
              <strong>当前受限：</strong>题源尚未通过人工审核，或版权状态仍为「版权状态未核实」。请先在「题源与来源审核」完成来源人工审核，再执行发布。
            </li>
            <li><strong>两步人工门禁：</strong>新导入题目处于「待人工审核」草稿态；须先「人工审核通过」，才可执行「发布」进入正式题池。</li>
            <li><strong>版本只读不可覆盖：</strong>已发布题目进入练习与阶段诊断取题池，后续勘误仅能新增修订版本，不可覆盖既有版本。</li>
          </ul>
        </HelpBubble>
        <span v-if="!canPublish" class="chip wait">题源未审核 · 暂不可发布</span>
        <button type="button" class="ghost small" @click="reload">
          刷新
        </button>
      </div>
    </div>
    <p v-if="versions === null" class="muted">
      {{ loadError === '' ? '题目加载中…' : `题目加载失败：${loadError}` }}
    </p>
    <p v-else-if="versions.length === 0" class="muted">
      该题源还没有题目版本：请前往「附件解析与录入」上传附件并完成逐题确认导入，草稿会出现在这里。
    </p>
    <div v-else :class="singleActiveSide ? 'version-single-stack' : 'matrix-2col'">
      <div>
        <h3 class="sub-head" style="margin-top: 4px;">
          待审核 / 已审核草稿 ({{ pendingVersions.length }})
        </h3>
        <p v-if="pendingVersions.length === 0" class="muted tiny">
          当前没有待处理草稿。
        </p>
        <ul
          v-else
          :class="[
            'version-list',
            pendingVersions.length >= 3 && publishedVersions.length === 0 ? 'version-list--grid' : '',
          ]"
          tabindex="0"
          aria-label="待审核与已审核草稿列表"
        >
          <li v-for="v in pendingVersions" :key="v.id" class="version-row">
            <div class="version-head">
              <span :class="['badge', `qstatus-${v.status}`]">
                {{ QUESTION_STATUS_LABELS[v.status] }}
              </span>
              <KindBadge :kind="v.kind" />
              <span class="muted tiny">
                第 {{ v.version }} 版 · {{ v.max_points }} 分
              </span>
            </div>
            <p class="version-stem">
              <RichText :text="excerpt(v.stem, 90)" />
            </p>
            <div class="version-meta">
              <code v-for="kid in v.knowledge_ids" :key="kid" class="kid">
                {{ getKnowledgeLabel(kid) }}
              </code>
              <span v-if="v.group_context" class="muted tiny">含组内材料</span>
              <span v-if="v.media_attachment_id" class="muted tiny">含媒体附件</span>
            </div>
            <div class="version-foot">
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
      </div>

      <div>
        <h3 class="sub-head" style="margin-top: 4px;">
          已发布入池题目 ({{ publishedVersions.length }})
        </h3>
        <p v-if="publishedVersions.length === 0" class="muted tiny">
          当前题源尚无已发布题目；待左侧草稿审核并点击「发布」后将在此列出。
        </p>
        <ul
          v-else
          :class="[
            'version-list',
            publishedVersions.length >= 3 && pendingVersions.length === 0 ? 'version-list--grid' : '',
          ]"
          tabindex="0"
          aria-label="已发布入池题目列表"
        >
          <li v-for="v in publishedVersions" :key="v.id" class="version-row">
            <div class="version-head">
              <span :class="['badge', `qstatus-${v.status}`]">
                {{ QUESTION_STATUS_LABELS[v.status] }}
              </span>
              <KindBadge :kind="v.kind" />
              <span class="muted tiny">
                第 {{ v.version }} 版 · {{ v.max_points }} 分
              </span>
            </div>
            <p class="version-stem">
              <RichText :text="excerpt(v.stem, 90)" />
            </p>
            <div class="version-meta">
              <code v-for="kid in v.knowledge_ids" :key="kid" class="kid">
                {{ getKnowledgeLabel(kid) }}
              </code>
              <span v-if="v.group_context" class="muted tiny">含组内材料</span>
              <span v-if="v.media_attachment_id" class="muted tiny">含媒体附件</span>
            </div>
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>
