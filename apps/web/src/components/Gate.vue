<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { describeError } from '../api'

const props = withDefaults(
  defineProps<{
    onEnter: (token: string, remember: boolean) => Promise<void>
    allowRemember?: boolean
    role?: 'student' | 'admin'
  }>(),
  {
    allowRemember: true,
    role: 'student',
  }
)

const value = ref('')
const busy = ref(false)
const error = ref('')
const visible = ref(false)
// 默认不勾选，学生端必须由用户主动勾选才持久化；管理端不支持记住
const remember = ref(false)

onMounted(() => {
  // 清理废弃的旧版全局凭据键，避免历史管理员凭据残留
  try {
    localStorage.removeItem('shutong.token')
  } catch {
    // 忽略异常
  }
})

async function pasteToken() {
  try {
    const text = (await navigator.clipboard.readText()).trim()
    if (text === '') {
      error.value = '剪贴板为空：请先复制访问令牌，或在输入框长按 / Ctrl+V 粘贴。'
      return
    }
    value.value = text
    error.value = ''
  } catch {
    error.value = '无法读取剪贴板：请在输入框长按 / Ctrl+V 粘贴。'
  }
}

async function submit() {
  if (value.value.trim() === '') {
    error.value = '请输入访问令牌。'
    return
  }
  busy.value = true
  error.value = ''
  try {
    const tokenVal = value.value.trim()
    await props.onEnter(tokenVal, props.allowRemember ? remember.value : false)
  } catch (e) {
    error.value = describeError(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="gate">
    <section class="card gate-card">
      <div class="gate-head">
        <span class="seal big" aria-hidden="true">
          书
        </span>
        <div>
          <span class="wordmark">书童</span>
          <span class="tagline">目标驱动的中考练习 · 私人学习空间</span>
        </div>
      </div>
      <form @submit.prevent="submit">
        <label>
          访问令牌
          <span class="token-row">
            <input
              :type="visible ? 'text' : 'password'"
              v-model="value"
              placeholder="SHUTONG_TOKEN"
              autocomplete="off"
              autofocus
            />
            <button
              type="button"
              class="ghost"
              @click="visible = !visible"
              :aria-pressed="visible"
              :aria-label="visible ? '隐藏令牌' : '显示令牌'"
            >
              {{ visible ? '隐藏' : '显示' }}
            </button>
            <button
              type="button"
              class="ghost"
              @click="pasteToken"
              :disabled="busy"
              aria-label="粘贴令牌"
            >
              粘贴
            </button>
          </span>
        </label>
        <div v-if="allowRemember" class="confirm-box gate-remember">
          <input
            id="gate-remember"
            type="checkbox"
            v-model="remember"
          />
          <label for="gate-remember">在本机记住令牌（私有设备：冷启动免输入；退出即清除）</label>
        </div>
        <div v-else class="gate-remember gate-admin-memory-notice">
          <small class="muted">管理凭据安全策略：仅在当前页面内存持有，不支持本机持久化记住。</small>
        </div>
        <p v-if="error" class="form-error">{{ error }}</p>
        <button type="submit" class="primary" :disabled="busy">
          {{ busy ? '验证中…' : '进入' }}
        </button>
      </form>
      <ul class="gate-notes">
        <li v-if="allowRemember">令牌默认只保留在当前页面内存；仅当你显式勾选「在本机记住令牌」后才写入本机存储（仅限个人私有设备，不会经网络传给第三方），退出即清除。</li>
        <li v-else>综合管理工作台管理令牌仅保存在当前页面响应式内存中，关闭或刷新页面后自动失效，杜绝持久化存储风险。</li>
        <li>私有单人工具：练习记录、学校试卷与个人信息不会被公开传播。</li>
        <li>只有管理员人工审核发布的题目才会出现；题库与知识点均依据教育部 2022 年版课程标准与北京市中考真题严格审校。</li>
      </ul>
    </section>
  </main>
</template>
