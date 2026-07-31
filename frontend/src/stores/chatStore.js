/**
 * 聊天消息 Store
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'

export const useChatStore = defineStore('chat', () => {
  const chatMessages = ref([])

  const _chatLoaded = ref(false)

  function resetFlags() {
    _chatLoaded.value = false
  }

  /** 加载聊天历史 */
  async function loadMessages() {
    if (_chatLoaded.value) return
    chatMessages.value = await api.getChatMessages().catch(() => [])
    _chatLoaded.value = true
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
        if (event.tool_call && onToolCall) onToolCall(event.tool_call, event.tool_args)
        if (event.tool_result) {
          if (onToolResult) await onToolResult(event.tool_result, event.content)
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

  async function clearChat() {
    await api.clearChatMessages()
    chatMessages.value = []
  }

  return {
    chatMessages,
    _chatLoaded, resetFlags,
    loadMessages, sendChatMessage, sendChatMessageStream, sendSmartMessage, clearChat,
  }
})