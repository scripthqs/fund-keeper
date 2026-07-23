/**
 * Pinia Store - 全局策略配置
 */
import { defineStore } from 'pinia'
import { reactive, ref } from 'vue'
import { api } from '../api'
import { DEFAULT_CONFIG } from '../utils/constants'

export const useConfigStore = defineStore('config', () => {
  const config = reactive({ ...DEFAULT_CONFIG })
  const _configLoaded = ref(false)

  async function loadConfig() {
    if (_configLoaded.value) return
    try {
      const cfg = await api.getConfig()
      Object.assign(config, DEFAULT_CONFIG, cfg)
    } catch {
      /* 使用默认配置 */
    }
    _configLoaded.value = true
  }

  function resetLoadFlag() {
    _configLoaded.value = false
  }

  async function saveConfig(d) {
    Object.assign(config, d)
    try {
      await api.updateConfig(d)
    } catch (e) {
      console.error('配置保存失败:', e)
    }
  }

  async function updatePeakReturn(fid, pr) {
    if (!config.peakReturnRate) config.peakReturnRate = {}
    config.peakReturnRate[fid] = pr
    api.updatePeakReturn(fid, pr).catch(e => console.error('峰值更新失败:', e))
  }

  return {
    config,
    _configLoaded,
    loadConfig,
    resetLoadFlag,
    saveConfig,
    updatePeakReturn,
  }
})
