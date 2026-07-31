/**
 * 配置 + AI 状态 Store
 */
import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import { api } from '../api'
import { DEFAULT_CONFIG } from '../utils/constants'

export const useConfigStore = defineStore('config', () => {
  const config = reactive({ ...DEFAULT_CONFIG })
  const aiStatus = ref({ configured: false, model: '', connected: false })

  // ---- 加载标记 ----
  const _configLoaded = ref(false)
  const _healthLoaded = ref(false)

  function resetFlags() {
    _configLoaded.value = false
    _healthLoaded.value = false
  }

  /** 加载 AI 健康状态 */
  async function loadHealth() {
    if (_healthLoaded.value) return
    try {
      const health = await api.health().catch(() => ({ llm_configured: false, model: '' }))
      aiStatus.value = { configured: health.llm_configured, model: health.model, connected: true }
      _healthLoaded.value = true
    } catch {}
  }

  async function saveConfig(d) {
    Object.assign(config, d)
    try { await api.updateConfig(d) } catch (e) { console.error('配置保存失败:', e) }
  }

  async function updatePeakReturn(fid, pr) {
    if (!config.peakReturnRate) config.peakReturnRate = {}
    config.peakReturnRate[fid] = pr
    api.updatePeakReturn(fid, pr).catch(e => console.error('峰值更新失败:', e))
  }

  return {
    config, aiStatus,
    _configLoaded, _healthLoaded, resetFlags,
    loadHealth, saveConfig, updatePeakReturn,
  }
})