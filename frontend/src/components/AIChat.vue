<template>
  <div class="card">
    <div class="flex items-center justify-between p-4 cursor-pointer" @click="collapsed = !collapsed">
      <h2 class="font-semibold text-base flex items-center gap-2"><span>🤖</span> AI 投资顾问</h2>
      <span class="transition-transform duration-300 text-sm" :style="{ transform: collapsed ? 'rotate(-90deg)' : 'rotate(0deg)', color: 'var(--text-secondary)' }">▼</span>
    </div>
    <div v-show="!collapsed" class="px-4 pb-4">
      <!-- AI 服务状态 -->
      <div class="flex items-center gap-2 mb-3">
        <span class="text-xs" style="color:var(--text-secondary)">AI 服务状态：</span>
        <van-tag v-if="!store.aiStatus.value.connected" type="danger" round size="small">❌ 后端未连接</van-tag>
        <van-tag v-else-if="store.aiStatus.value.configured" type="success" round size="small">✅ 已连接 ({{ store.aiStatus.value.model }})</van-tag>
        <van-tag v-else type="danger" round size="small">⚠️ 未配置 API Key</van-tag>
      </div>
      <!-- 聊天消息区域 -->
      <div ref="msgContainer" class="mb-3 rounded-lg p-3 overflow-y-auto" style="background:var(--bg-primary);min-height:120px;max-height:360px;">
        <div v-if="messages.length === 0" class="text-center text-xs py-4" style="color:var(--text-secondary)">
          👋 你好！我是你的 AI 投资顾问。<br>你可以直接提问，或点击下方按钮快速分析当前持仓。
        </div>
        <div v-for="(msg, i) in messages" :key="i" class="flex mb-3" :class="msg.role === 'user' ? 'justify-end' : 'justify-start'">
          <div class="chat-bubble" :class="msg.role" v-html="renderMarkdown(msg.content)"></div>
        </div>
      </div>
      <!-- 快捷操作 -->
      <div class="flex gap-2 mb-3 flex-wrap">
        <van-button round plain size="small" @click="quick('请根据我当前的基金持仓数据，做一次全面的综合分析，包括各基金的表现、仓位合理性、以及需要注意的风险点。')">📊 分析当前持仓</van-button>
        <van-button round plain size="small" @click="quick('基于我当前的持仓和投资规则（止盈线、加仓线、极端波动线），请重点评估当前面临的风险，哪些基金最值得警惕？')">⚠️ 风险评估</van-button>
        <van-button round plain size="small" @click="quick('根据当前持仓情况和投资规则，请给出具体的操作策略建议，哪些该止盈、哪些该加仓、哪些继续持有？')">📋 策略建议</van-button>
        <van-button type="danger" round size="small" @click="clearChat">🗑 清空对话</van-button>
      </div>
      <!-- 输入区域 -->
      <div class="flex gap-2">
        <input type="text" class="input-field flex-1 text-sm" v-model="input" placeholder="输入你的问题..." @keydown.enter.exact.prevent="send">
        <van-button type="primary" round :loading="loading" @click="send">发送</van-button>
      </div>
      <van-loading v-if="loading" type="spinner" size="16px" class="text-center py-3" color="#3b82f6">
        <span class="ml-2 text-xs" style="color:var(--text-secondary)">AI 正在思考...</span>
      </van-loading>
    </div>
  </div>
</template>

<script setup>
import { ref, inject, nextTick, watch } from 'vue'
import { escapeHtml } from '../utils/helpers'
import { askConfirm } from '../utils/dialog'

const store = inject('store')
const collapsed = ref(true)
const input = ref('')
const loading = ref(false)
const msgContainer = ref(null)

const messages = store.chatMessages

function renderMarkdown(content) {
  let html = escapeHtml(content)
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre class="text-xs my-1 p-2 rounded" style="background:var(--bg-primary)">$2</pre>')
  html = html.replace(/`([^`]+)`/g, '<code class="text-xs px-1 rounded" style="background:var(--bg-primary)">$1</code>')
  html = html.replace(/\n/g, '<br>')
  return html
}

async function send(customMsg) {
  const message = customMsg || input.value.trim()
  if (!message) return
  input.value = ''
  loading.value = true
  try {
    const ctx = store.buildFundContext()
    await store.sendChatMessage(message, ctx)
  } catch (e) {
    store.chatMessages.value.push({ role: 'assistant', content: `❌ 请求失败：${e.message}\n\n请检查后端服务是否正常运行，以及 LLM API Key 是否已配置。` })
  } finally {
    loading.value = false
    await scrollToBottom()
  }
}

function quick(msg) { collapsed.value = false; send(msg) }

async function clearChat() {
  if (!await askConfirm('确定清空所有聊天记录吗？')) return
  await store.clearChat()
}

async function scrollToBottom() {
  await nextTick()
  if (msgContainer.value) msgContainer.value.scrollTop = msgContainer.value.scrollHeight
}

watch(messages, () => scrollToBottom(), { deep: true })
</script>
