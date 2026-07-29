/**
 * Pinia Store - AI 聊天 & 服务状态
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'

export const useChatStore = defineStore('chat', () => {
  const chatMessages = ref([])
  const aiStatus = ref({ configured: false, model: '', connected: false })
  const _chatLoaded = ref(false)
  const _healthLoaded = ref(false)

  async function loadChatAndHealth() {
    const promises = []
    if (!_chatLoaded.value) promises.push(api.getChatMessages().catch(() => []))
    if (!_healthLoaded.value) promises.push(api.health().catch(() => ({ llm_configured: false, model: '' })))

    if (promises.length === 0) return

    const results = await Promise.all(promises)
    let ri = 0
    if (!_chatLoaded.value) {
      chatMessages.value = results[ri++]
      _chatLoaded.value = true
    }
    if (!_healthLoaded.value) {
      const health = results[ri]
      aiStatus.value = { configured: health.llm_configured, model: health.model, connected: true }
      _healthLoaded.value = true
    }
  }

  function resetLoadFlags() {
    _chatLoaded.value = false
    _healthLoaded.value = false
  }

  async function sendChatMessage(message, fundContext) {
    const recent = chatMessages.value.slice(-20)
    const r = await api.chat(message, fundContext, recent)
    chatMessages.value.push({ role: 'user', content: message })
    chatMessages.value.push({ role: 'assistant', content: r.reply })
    return r.reply
  }

  async function sendChatMessageStream(message, fundContext, onChunk) {
    const recent = chatMessages.value.slice(-20)
    chatMessages.value.push({ role: 'user', content: message })
    const aiIdx = chatMessages.value.length
    chatMessages.value.push({ role: 'assistant', content: '' })

    let fullReply = ''
    try {
      for await (const event of api.chatStream(message, fundContext, recent)) {
        if (event.done) break
        if (event.content) {
          fullReply += event.content
          chatMessages.value[aiIdx].content = fullReply
          if (onChunk) onChunk(event.content, fullReply)
        }
      }
    } catch (e) {
      chatMessages.value[aiIdx].content = 'AI 回复失败: ' + (e.message || '网络错误')
      throw e
    }
    return fullReply
  }

  async function clearChat() {
    await api.clearChatMessages()
    chatMessages.value = []
  }

  /** 智能对话（Function Calling）：AI 自动调用工具获取实时数据 */
  async function sendSmartMessage(message, fundContext, onChunk, onToolCall, onToolResult) {
    const recent = chatMessages.value.slice(-20)
    chatMessages.value.push({ role: 'user', content: message })
    const aiIdx = chatMessages.value.length
    chatMessages.value.push({ role: 'assistant', content: '' })

    let fullReply = ''
    try {
      for await (const event of api.chatSmartStream(message, fundContext, recent)) {
        if (!event) continue
        if (event.done) break
        if (event.error) {
          chatMessages.value[aiIdx].content = 'AI 回复失败: ' + event.error
          throw new Error(event.error)
        }
        if (event.tool_call) {
          if (onToolCall) onToolCall(event.tool_call, event.tool_args)
        }
        // 工具结果事件：只通知回调，不混入AI回复
        if (event.tool_result) {
          if (onToolResult) onToolResult(event.tool_result, event.content)
          continue
        }
        if (event.content) {
          fullReply += event.content
          chatMessages.value[aiIdx].content = fullReply
          if (onChunk) onChunk(event.content, fullReply)
        }
      }
    } catch (e) {
      if (!chatMessages.value[aiIdx].content) {
        chatMessages.value[aiIdx].content = 'AI 回复失败: ' + (e.message || '网络错误')
      }
      throw e
    }
    return fullReply
  }

  return {
    chatMessages,
    aiStatus,
    _chatLoaded,
    _healthLoaded,
    loadChatAndHealth,
    resetLoadFlags,
    sendChatMessage,
    sendChatMessageStream,
    sendSmartMessage,
    clearChat,
  }
})
