<template>
  <div class="smart-chat">
    <!-- AI 状态栏 -->
    <div class="ai-status-bar">
      <span class="text-xs" style="color:var(--text-secondary)">AI 服务：</span>
      <van-tag v-if="!aiStatus.connected" type="danger" round size="small">❌ 未连接</van-tag>
      <van-tag v-else-if="aiStatus.configured" type="success" round size="small">✅ {{ aiStatus.model }}</van-tag>
      <van-tag v-else type="danger" round size="small">⚠️ 未配置 Key</van-tag>
      <span class="text-xs ml-auto" style="color:var(--text-secondary)">{{ tradingBadge.icon }} {{ tradingBadge.text }}</span>
    </div>

    <!-- 消息区域 -->
    <div ref="msgContainer" class="msg-area" @scroll="onScroll">
      <!-- 欢迎语 -->
      <div v-if="messages.length === 0" class="welcome">
        <div class="welcome-icon">🤖</div>
        <div class="welcome-title">你好，我是你的理财小助手</div>
        <div class="welcome-desc">我可以帮你查看持仓、分析盈亏、检查预警、更新净值…<br>直接告诉我你想做什么，或点击下方快捷标签 👇</div>
      </div>

      <!-- 消息列表 -->
      <div v-for="(msg, i) in messages" :key="i" class="msg-row" :class="msg.role">
        <div class="msg-avatar">{{ msg.role === 'user' ? '👤' : '🤖' }}</div>
        <div class="msg-bubble" :class="msg.role">
          <!-- 流式加载中 -->
          <div v-if="msg.role === 'assistant' && loading && i === messages.length - 1 && !msg.content" class="typing-dots">
            <span></span><span></span><span></span>
          </div>
          <!-- Markdown 内容 -->
          <div v-else v-html="renderMarkdown(msg?.content || '')"></div>
        </div>
      </div>

      <!-- 工具调用状态提示 -->
      <div v-if="toolStatus" class="tool-status">
        <van-loading type="spinner" size="14px" color="#3b82f6" />
        <span>{{ toolStatus }}</span>
      </div>

      <div ref="msgEnd"></div>
    </div>

    <!-- 输入区域 -->
    <div class="input-area">
      <div class="input-row">
        <input
          ref="inputEl"
          v-model="input"
          class="chat-input"
          placeholder="输入消息，或点击快捷标签..."
          @keydown.enter.exact="send()"
          :disabled="loading"
        />
        <button class="send-btn" @click="send()" :disabled="loading || !input.trim()">
          <span v-if="loading" class="send-spinner"></span>
          <span v-else>➤</span>
        </button>
      </div>
      <div class="input-hint">
        <span @click="toggleSearch" class="search-toggle" :class="{ active: webSearchEnabled }">
          {{ webSearchEnabled ? '🌐 联网搜索 · 开' : '🌐 联网搜索 · 关' }}
        </span>
        <span @click="clearChat" class="clear-link">🗑 清空</span>
        <span class="fund-count">📊 {{ fundCount }} 只</span>
      </div>
    </div>

    <!-- 快捷标签 -->
    <div class="quick-tags">
      <button
        v-for="tag in quickTags"
        :key="tag.label"
        class="quick-tag"
        :class="{ active: tag.label === activeTag }"
        @click="quickAction(tag)"
        :disabled="loading"
      >
        <span class="tag-icon">{{ tag.icon }}</span>
        <span class="tag-label">{{ tag.label }}</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, watch, onMounted, computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useFundStore, useConfigStore, useChatStore } from '../stores/appStore'
import { renderMarkdown } from '../utils/helpers'
import { askConfirm } from '../utils/dialog'

const fundStore = useFundStore()
const configStore = useConfigStore()
const chatStore = useChatStore()
const { chatMessages: messages } = storeToRefs(chatStore)
const { aiStatus } = storeToRefs(configStore)
const input = ref('')
const loading = ref(false)
const msgContainer = ref(null)
const msgEnd = ref(null)
const inputEl = ref(null)
const toolStatus = ref('')
const activeTag = ref('')
const webSearchEnabled = ref(true)

const fundCount = computed(() => (fundStore.funds || []).length)

// 交易状态
const tradingBadge = ref({ icon: '⚪', text: '加载中...' })
async function loadTradingStatus() {
  try {
    const r = await fetch('/api/calendar/trading-status')
    const d = await r.json()
    if (d.trading) {
      tradingBadge.value = { icon: '🕘', text: '交易中' }
    } else {
      tradingBadge.value = { icon: '⚪', text: d.holiday_name || '休市' }
    }
  } catch { tradingBadge.value = { icon: '⚪', text: '' } }
}

// 快捷标签
const quickTags = [
  { icon: '📊', label: '持仓概览', msg: '帮我看看当前持仓概况' },
  { icon: '💰', label: '盈亏分析', msg: '分析一下各基金的盈亏情况' },
  { icon: '⚠️', label: '风险预警', msg: '检查所有基金的止盈止损预警' },
  { icon: '📊', label: '实时净值', msg: '帮我查一下所有基金的最新净值和涨跌' },
  { icon: '🎯', label: '操作建议', msg: '根据当前持仓给出操作建议' },
  { icon: '⚙️', label: '投资配置', msg: '查看当前的投资配置' },
  { icon: '📈', label: '走势快照', msg: '帮我看看持仓的近期走势' },
  { icon: '💚', label: '健康评分', msg: '评估一下持仓健康度' },
  { icon: '📜', label: '操作历史', msg: '查看最近的买卖操作记录' },
]

async function quickAction(tag) {
  activeTag.value = tag.label
  await send(tag.msg)
  setTimeout(() => { activeTag.value = '' }, 2000)
}

function toggleSearch() {
  webSearchEnabled.value = !webSearchEnabled.value
}

async function send(customMsg) {
  const message = customMsg || input.value.trim()
  if (!message || loading.value) return
  input.value = ''
  loading.value = true
  toolStatus.value = ''

  try {
    let ctx = fundStore.buildFundContext()
    // 根据联网开关注入指令
    if (webSearchEnabled.value) {
      ctx += '\n\n🌐 用户已开启联网搜索。遇到最新新闻、政策、行情、基金资讯等问题，请调用 search_web 工具获取实时信息后再回答。'
    } else {
      ctx += '\n\n⚠️ 用户已关闭联网搜索功能，请不要调用 search_web 工具，基于已有知识和数据回答即可。'
    }
    await chatStore.sendSmartMessage(
      message,
      ctx,
      // onChunk
      () => { nextTick(scrollToBottom) },
      // onToolCall
      (toolName, args) => {
        const labels = {
          get_holdings_summary: '📊 正在获取持仓数据...',
          get_fund_detail: '🔍 正在查询基金详情...',
          check_alerts: '⚠️ 正在检查预警状态...',
          get_trading_suggestions: '💡 正在分析操作建议...',
          update_all_nav: '📊 正在获取实时净值...',
          get_investment_config: '⚙️ 正在读取配置...',
          get_snapshot_history: '📈 正在加载走势数据...',
          get_operation_history: '📜 正在获取历史记录...',
          execute_trade: '💸 正在执行交易...',
          add_fund_quick: '➕ 正在添加基金...',
          update_fund: '✏️ 正在更新基金数据...',
          get_health_score: '💚 正在评估健康度...',
          get_trading_status: '📅 正在获取交易状态...',
          search_web: '🌐 正在联网搜索...',
        }
        toolStatus.value = labels[toolName] || `🔧 正在调用 ${toolName}...`
      },
      // onToolResult
      async (toolName) => {
        toolStatus.value = ''
        // 写库类工具执行后刷新持仓，保持各 Tab 数据同步
        if (['update_fund', 'execute_trade', 'add_fund_quick'].includes(toolName)) {
          await fundStore.refreshFunds()
        }
      }
    )
  } catch (e) {
    console.error('智能对话失败:', e)
    messages.value.push({
      role: 'assistant',
      content: `❌ 请求失败：${e.message}\n\n请检查后端服务和 LLM API Key 配置。`
    })
  } finally {
    loading.value = false
    toolStatus.value = ''
    await scrollToBottom()
  }
}

async function clearChat() {
  if (!await askConfirm('确定清空所有聊天记录吗？')) return
  await chatStore.clearChat()
}

function scrollToBottom() {
  nextTick(() => {
    msgEnd.value?.scrollIntoView({ behavior: 'smooth' })
  })
}

let userScrolledUp = false
function onScroll() {
  if (!msgContainer.value) return
  const el = msgContainer.value
  userScrolledUp = el.scrollHeight - el.scrollTop - el.clientHeight > 80
}

watch(messages, () => {
  if (!userScrolledUp) scrollToBottom()
}, { deep: true })

onMounted(() => {
  loadTradingStatus()
  scrollToBottom()
})
</script>

<style scoped>
.smart-chat {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 130px);
  max-height: calc(100vh - 130px);
}

/* AI 状态栏 */
.ai-status-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--bg-primary);
  border-radius: 10px;
  margin-bottom: 8px;
  flex-shrink: 0;
}

/* 消息区域 */
.msg-area {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
  scroll-behavior: smooth;
  -webkit-overflow-scrolling: touch;
}

.welcome {
  text-align: center;
  padding: 30px 16px 20px;
}
.welcome-icon { font-size: 40px; margin-bottom: 10px; }
.welcome-title { font-size: 16px; font-weight: 600; color: var(--text-primary); margin-bottom: 8px; }
.welcome-desc { font-size: 12px; color: var(--text-secondary); line-height: 1.7; }

/* 消息行 */
.msg-row {
  display: flex;
  flex-direction: column;
  margin-bottom: 14px;
}
.msg-row.user { align-items: flex-end; }
.msg-row:not(.user) { align-items: flex-start; }

.msg-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  flex-shrink: 0;
  background: var(--bg-primary);
  margin-bottom: 3px;
}

/* 气泡 */
.msg-bubble {
  width: 100%;
  padding: 8px 12px;
  border-radius: 14px;
  font-size: 14px;
  line-height: 1.75;
  word-break: break-word;
}
.msg-bubble.user {
  max-width: 80%;
  background: linear-gradient(135deg, #12edd7, #0ec4b0);
  color: #fff;
  border-top-right-radius: 4px;
  border-bottom-right-radius: 4px;
}
.msg-bubble.assistant {
  background: var(--bg-primary);
  color: var(--text-primary);
  border-top-left-radius: 4px;
  border-bottom-left-radius: 4px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  overflow-x: auto;
}

/* ===== AI 回复 Markdown 排版 ===== */
.msg-bubble.assistant :deep(p) {
  margin: 0 0 0.6em;
}
.msg-bubble.assistant :deep(p:last-child) {
  margin-bottom: 0;
}
.msg-bubble.assistant :deep(strong) {
  font-weight: 600;
  color: var(--text-primary);
}
.msg-bubble.assistant :deep(h1),
.msg-bubble.assistant :deep(h2),
.msg-bubble.assistant :deep(h3) {
  margin: 0.8em 0 0.4em;
  font-weight: 600;
  line-height: 1.4;
}
.msg-bubble.assistant :deep(h1:first-child),
.msg-bubble.assistant :deep(h2:first-child),
.msg-bubble.assistant :deep(h3:first-child) {
  margin-top: 0;
}
.msg-bubble.assistant :deep(ul),
.msg-bubble.assistant :deep(ol) {
  margin: 0.4em 0;
  padding-left: 1.4em;
}
.msg-bubble.assistant :deep(li) {
  margin-bottom: 0.25em;
  line-height: 1.7;
}
.msg-bubble.assistant :deep(table) {
  width: auto;
  min-width: 100%;
  margin: 0.6em 0;
  border-collapse: collapse;
  font-size: 13px;
  white-space: nowrap;
}
.msg-bubble.assistant :deep(th),
.msg-bubble.assistant :deep(td) {
  padding: 6px 10px;
  border: 1px solid var(--border-color);
  text-align: left;
  word-break: keep-all;
}
.msg-bubble.assistant :deep(th) {
  background: rgba(0,0,0,0.03);
  font-weight: 600;
}
.msg-bubble.assistant :deep(code) {
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 0.9em;
  background: rgba(0,0,0,0.06);
  color: #e74c3c;
  font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
}
.msg-bubble.assistant :deep(pre) {
  margin: 0.6em 0;
  padding: 10px 14px;
  border-radius: 8px;
  background: rgba(0,0,0,0.04);
  overflow-x: auto;
  font-size: 12px;
  line-height: 1.5;
}
.msg-bubble.assistant :deep(pre code) {
  padding: 0;
  background: none;
  color: inherit;
}
.msg-bubble.assistant :deep(blockquote) {
  margin: 0.5em 0;
  padding: 4px 12px;
  border-left: 3px solid #12edd7;
  color: var(--text-secondary);
}
.msg-bubble.assistant :deep(hr) {
  margin: 0.8em 0;
  border: none;
  border-top: 1px solid var(--border-color);
}
.msg-bubble.assistant :deep(a) {
  color: #3b82f6;
  text-decoration: none;
}
.msg-bubble.assistant :deep(a:hover) {
  text-decoration: underline;
}

html.dark .msg-bubble.assistant :deep(th) {
  background: rgba(255,255,255,0.04);
}
html.dark .msg-bubble.assistant :deep(code) {
  background: rgba(255,255,255,0.08);
}
html.dark .msg-bubble.assistant :deep(pre) {
  background: rgba(255,255,255,0.04);
}

/* 打字动画 */
.typing-dots {
  display: flex;
  gap: 4px;
  padding: 4px 0;
}
.typing-dots span {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--text-secondary);
  animation: typing 1.4s infinite;
}
.typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.typing-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes typing {
  0%,60%,100% { opacity: 0.3; transform: translateY(0); }
  30% { opacity: 1; transform: translateY(-4px); }
}

/* 工具状态 */
.tool-status {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  font-size: 11px;
  color: var(--text-secondary);
  background: rgba(59,130,246,0.06);
  border-radius: 8px;
  margin: 4px 0;
}

/* 快捷标签 (横向滚动) */
.quick-tags {
  display: flex;
  gap: 6px;
  padding: 6px 0;
  flex-shrink: 0;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
}
.quick-tags::-webkit-scrollbar { display: none; }

.quick-tag {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px 10px;
  border-radius: 14px;
  border: 1px solid rgba(18,237,215,0.25);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 12px;
  white-space: nowrap;
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}
.quick-tag:active, .quick-tag.active {
  background: rgba(18,237,215,0.12);
  border-color: #12edd7;
  transform: scale(0.96);
}
.quick-tag:disabled { opacity: 0.5; cursor: not-allowed; }
.tag-icon { font-size: 14px; }
.tag-label { font-weight: 500; }

/* 输入区域 */
.input-area {
  flex-shrink: 0;
  padding-top: 6px;
}
.input-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.chat-input {
  flex: 1;
  padding: 10px 14px;
  border-radius: 20px;
  border: 1px solid rgba(0,0,0,0.08);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
}
.chat-input:focus { border-color: #12edd7; }
.chat-input::placeholder { color: var(--text-secondary); font-size: 13px; }

.send-btn {
  width: 40px; height: 40px;
  border-radius: 50%;
  border: none;
  background: linear-gradient(135deg, #12edd7, #0ec4b0);
  color: #fff;
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.15s, opacity 0.15s;
  flex-shrink: 0;
}
.send-btn:active { transform: scale(0.92); }
.send-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.send-spinner {
  width: 16px; height: 16px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.input-hint {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 8px 0;
  font-size: 11px;
  color: var(--text-secondary);
}
.search-toggle {
  cursor: pointer;
  padding: 2px 8px;
  border-radius: 10px;
  transition: all 0.2s;
  font-weight: 500;
}
.search-toggle.active {
  background: rgba(18,237,215,0.12);
  color: #12edd7;
}
.search-toggle:not(.active) {
  opacity: 0.5;
}
.clear-link { cursor: pointer; }
.clear-link:hover { color: #e74c3c; }
.fund-count { opacity: 0.7; }
</style>
