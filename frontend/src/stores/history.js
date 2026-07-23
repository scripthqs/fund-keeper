/**
 * Pinia Store - 操作历史
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'
import { uuid } from '../utils/helpers'

export const useHistoryStore = defineStore('history', () => {
  const history = ref([])
  const _historyLoaded = ref(false)

  const reasonMap = { sell: '触发止盈', buy: '触发加仓', stop_loss: '触发止损', trailing_sell: '移动止盈' }

  async function loadHistory() {
    if (_historyLoaded.value) return
    try {
      history.value = (await api.getHistory()).map(h => ({
        ...h,
        canUndo: !!h.snapshot_before,
        aiEvaluation: h.ai_evaluation || '',
      }))
    } catch {
      history.value = []
    }
    _historyLoaded.value = true
  }

  function resetLoadFlag() {
    _historyLoaded.value = false
  }

  function pushEntry(entry) {
    history.value.unshift({
      id: uuid(),
      date: new Date().toISOString().split('T')[0],
      ...entry,
      canUndo: true,
    })
  }

  async function undoAction(historyId) {
    const r = await api.undoAction(historyId)
    history.value = history.value.filter(h => h.id !== historyId)
    return r
  }

  async function clearHistory() {
    await api.clearHistory()
    history.value = []
  }

  async function evaluateHistory(historyId, onChunk) {
    const h = history.value.find(item => item.id === historyId)
    if (!h) throw new Error('记录不存在')

    let fullText = ''
    try {
      for await (const event of api.evaluateHistoryStream(historyId)) {
        if (event.connected) continue
        if (event.reasoning) continue
        if (event.error) throw new Error(event.error)
        if (event.done) break
        if (event.content) {
          fullText += event.content
          if (h) h.aiEvaluation = fullText
          if (onChunk) onChunk(event.content, fullText)
        }
      }
    } catch (e) {
      const r = await api.evaluateHistory(historyId)
      fullText = r.evaluation
      if (h) h.aiEvaluation = fullText
    }

    if (h) h.aiEvaluation = fullText
    return fullText
  }

  return {
    history,
    _historyLoaded,
    reasonMap,
    loadHistory,
    resetLoadFlag,
    pushEntry,
    undoAction,
    clearHistory,
    evaluateHistory,
  }
})
