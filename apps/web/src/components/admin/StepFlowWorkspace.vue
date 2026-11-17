<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { evaluateStepClick, resolveActiveStepId, type StepDefinition, type StepFlowContext } from './stepFlow'

const props = withDefaults(
  defineProps<{
    steps: StepDefinition[]
    modelValue?: string
    context?: StepFlowContext | null
    stepsAriaLabel?: string
    wide?: boolean
  }>(),
  {
    modelValue: '',
    context: null,
    stepsAriaLabel: '工作流步骤',
    wide: false,
  },
)

const emit = defineEmits<{
  (e: 'update:modelValue', id: string): void
}>()

const gateWarning = ref('')

const activeId = computed(() => resolveActiveStepId(props.steps, props.modelValue))
const activeStep = computed(() => props.steps.find(step => step.id === activeId.value) ?? props.steps[0] ?? null)

watch(
  [() => props.steps, () => props.modelValue],
  () => {
    const resolved = resolveActiveStepId(props.steps, props.modelValue)
    if (resolved && resolved !== props.modelValue) {
      emit('update:modelValue', resolved)
    }
  },
  { immediate: true, deep: true },
)

function handleStepClick(stepId: string) {
  const verdict = evaluateStepClick(props.steps, stepId)
  if (!verdict.allowed) {
    gateWarning.value = verdict.warning
    return
  }
  gateWarning.value = ''
  emit('update:modelValue', verdict.nextId)
}

function clearWarning() {
  gateWarning.value = ''
}
</script>

<template>
  <div :class="['step-flow-workspace', wide ? 'step-flow-wide' : 'stage-wrap']">
    <div v-if="context || $slots['context-actions']" class="matrix-context-bar">
      <div v-if="context" class="matrix-context-main">
        <span class="eyebrow">{{ context.eyebrow }}</span>
        <b>{{ context.title }}</b>
        <span v-if="context.statusText" :class="['chip', context.statusTone ?? 'subtle']">
          {{ context.statusText }}
        </span>
      </div>
      <div v-if="$slots['context-actions']" class="matrix-context-actions">
        <slot name="context-actions" />
      </div>
    </div>

    <ol
      v-if="steps.length > 1"
      class="step-pill-bar"
      :aria-label="stepsAriaLabel"
    >
      <li v-for="(step, idx) in steps" :key="step.id" class="step-pill-item">
        <button
          type="button"
          :aria-current="activeStep?.id === step.id ? 'step' : undefined"
          :aria-disabled="!step.prereqMet ? 'true' : undefined"
          :class="[
            'step-pill',
            !step.prereqMet
              ? 'locked'
              : activeStep?.id === step.id
                ? 'active'
                : step.done
                  ? 'done'
                  : '',
          ]"
          @click="handleStepClick(step.id)"
        >
          <span class="step-icon" aria-hidden="true">
            {{ !step.prereqMet ? '🔒' : step.done && activeStep?.id !== step.id ? '✓' : idx + 1 }}
          </span>
          <span class="step-copy">
            <b>{{ step.title }}</b>
            <small>{{ !step.prereqMet ? '前置未满 · 待解锁' : (step.subtitle || '') }}</small>
          </span>
          <span
            v-if="step.badge"
            :class="['step-badge', 'chip', step.badgeTone ?? 'subtle']"
          >
            {{ step.badge }}
          </span>
        </button>
      </li>
    </ol>

    <div v-if="gateWarning" class="gate-alert-banner" role="alert">
      <span>{{ gateWarning }}</span>
      <button type="button" class="ghost small" @click="clearWarning">
        知道了
      </button>
    </div>

    <div v-if="activeStep" class="step-stage-body">
      <div v-if="!activeStep.prereqMet" :key="`locked-${activeStep.id}`" class="step-stage-slot">
        <slot name="locked" :step="activeStep">
          <section class="card" :aria-label="activeStep.title">
            <div class="card-head">
              <h3>{{ activeStep.title }}</h3>
              <span class="chip wait">前置未就绪</span>
            </div>
            <p class="muted">{{ activeStep.lockReason || '请先完成前置步骤后再继续。' }}</p>
          </section>
        </slot>
      </div>
      <div v-else :key="`step-${activeStep.id}`" class="step-stage-slot">
        <slot :name="`step-${activeStep.id}`" :step="activeStep" />
      </div>
    </div>
  </div>
</template>
