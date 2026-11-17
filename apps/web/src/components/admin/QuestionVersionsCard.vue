<script setup lang="ts">
import { computed, ref, watch } from 'vue'
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
import StepFlowWorkspace from './StepFlowWorkspace.vue'
import type { StepDefinition } from './stepFlow'

type Notify = (text: string, tone?: NoticeTone) => void
type VersionStepId = 'pending' | 'published'

const props = defineProps<{
  client: ApiClient
  source: SourceDetail
  notify: Notify
}>()

const emit = defineEmits<{
  (e: 'sourceChanged'): void
  (e: 'go-source-review'): void
  (e: 'go-attachments'): void
  (e: 'go-health'): void
}>()

const versions = ref<QuestionVersion[] | null>(null)
const loadError = ref('')
const busyId = ref<string | null>(null)
const verStep = ref<VersionStepId>('pending')

const canPublish = computed(
  () => props.source.source.verified && props.source.source.rights_status !== 'unknown',
)

const pendingVersions = computed(
  () => (versions.value ?? []).filter(v => v.status !== 'published'),
)
const publishedVersions = computed(
  () => (versions.value ?? []).filter(v => v.status === 'published'),
)

async function reload() {
  try {
    const list = await props.client.sourceQuestions(props.source.id)
    versions.value = list
    loadError.value = ''
    const hasPending = list.some(v => v.status !== 'published')
    const hasPublished = list.some(v => v.status === 'published')
    if (!hasPending && hasPublished) {
      verStep.value = 'published'
    } else if (hasPending) {
      verStep.value = 'pending'
    }
  } catch (e) {
    loadError.value = describeError(e)
  }
}

watch(
  () => props.source.id,
  () => {
    void reload()
  },
  { immediate: true },
)

const steps = computed<StepDefinition[]>(() => {
  const loaded = versions.value !== null
  const totalCount = versions.value?.length ?? 0
  return [
    {
      id: 'pending',
      title: '1. 待处理草稿审核与发布',
      subtitle:
        pendingVersions.value.length > 0
          ? `待处理 ${pendingVersions.value.length} 题`
          : '草稿已全部发布',
      badge: `${pendingVersions.value.length} 题`,
      badgeTone: pendingVersions.value.length > 0 ? 'wait' : 'good',
      done: loaded && totalCount > 0 && pendingVersions.value.length === 0,
      prereqMet: !loaded || totalCount > 0,
      lockReason: '当前题源还没有题目草稿，请先在「第二阶段 · 附件解析与录入」完成逐题导入。',
    },
    {
      id: 'published',
      title: '2. 已发布入池题目（只读）',
      subtitle:
        publishedVersions.value.length > 0
          ? `已入池 ${publishedVersions.value.length} 题`
          : '待第 1 步完成发布',
      badge: `${publishedVersions.value.length} 题`,
      badgeTone: publishedVersions.value.length > 0 ? 'good' : 'subtle',
      done: publishedVersions.value.length > 0,
      prereqMet: publishedVersions.value.length > 0,
      lockReason: '尚未发布任何题目入池，请先在第 1 步完成题目人工审核并点击「发布」。',
    },
  ]
})

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
  <div role="region" aria-label="题目草稿与发布">
    <StepFlowWorkspace
      v-model="verStep"
      :steps="steps"
      steps-aria-label="题目审核与发布步骤"
    >
      <template #locked>
        <section class="card" aria-label="题目草稿与发布空状态">
          <div class="card-head">
            <h2>题目草稿与发布</h2>
            <button type="button" class="ghost small" @click="reload">
              刷新
            </button>
          </div>
          <p v-if="versions === null" class="muted">
            {{ loadError === '' ? '题目加载中…' : `题目加载失败：${loadError}` }}
          </p>
          <div v-else>
            <p class="muted">
              该题源还没有题目版本：请前往「第二阶段 · 附件解析与录入」上传附件并完成逐题确认导入，草稿会出现在这里。
            </p>
            <button type="button" class="primary small" @click="emit('go-attachments')">
              前往附件解析与录入 →
            </button>
          </div>
        </section>
      </template>

      <!-- 第 1 步：待审核 / 已审核待发布草稿 -->
      <template #step-pending>
        <section class="card" aria-label="待审核与已审核草稿">
          <div class="card-head">
            <div>
              <h2>第 1 步 · 待审核 / 已审核草稿 ({{ pendingVersions.length }})</h2>
              <p class="card-sub">两步人工门禁：待人工审核 → 人工审核通过 → 发布入池</p>
            </div>
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

          <div v-if="!canPublish" class="gate-alert-banner">
            <span>
              <b>发布前置门禁阻断：</b>当前题源尚未通过人工审核（或上传新附件后已重置为未审核），或版权状态未核实。可先完成题目人工审核，发布前须回第一阶段确认来源。
            </span>
            <button type="button" class="primary small" @click="emit('go-source-review')">
              前往来源人工审核 →
            </button>
          </div>

          <div v-if="pendingVersions.length === 0">
            <p class="muted">当前没有待处理草稿，本源题目已全部发布入池。</p>
            <button
              v-if="publishedVersions.length > 0"
              type="button"
              class="primary small"
              @click="verStep = 'published'"
            >
              查看第 2 步：已发布入池题目 ({{ publishedVersions.length }}) →
            </button>
          </div>

          <ul
            v-else
            class="version-list version-list--grid"
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
        </section>
      </template>

      <!-- 第 2 步：已发布入池题目（只读） -->
      <template #step-published>
        <section class="card" aria-label="已发布入池题目">
          <div class="card-head">
            <div>
              <h2>第 2 步 · 已发布入池题目 ({{ publishedVersions.length }})</h2>
              <p class="card-sub">已入练习与阶段诊断取题池，版本永久只读不可覆盖。</p>
            </div>
            <button type="button" class="ghost small" @click="reload">
              刷新
            </button>
          </div>
          <ul
            class="version-list version-list--grid"
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
          <div class="handoff-box">
            <div>
              <strong>题库入池闭环完成！</strong>
              <span>可前往「第四阶段 · 题库余量体检」查看各知识点未见题余量。</span>
            </div>
            <button type="button" class="primary small" @click="emit('go-health')">
              前往题库余量体检 →
            </button>
          </div>
        </section>
      </template>
    </StepFlowWorkspace>
  </div>
</template>
