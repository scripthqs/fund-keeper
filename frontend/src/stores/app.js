/**
 * Pinia Store - 应用级状态（UI、用户、加载编排）
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'
import { useFundStore } from './fund'
import { useConfigStore } from './config'
import { useHistoryStore } from './history'
import { useChatStore } from './chat'

export const useAppStore = defineStore('app', () => {
  // ========== 加载状态 ==========
  const loading = ref(false)

  // ========== 用户状态 ==========
  const isLoggedIn = ref(false)
  const userInfo = ref(null)

  // ========== UI 状态 ==========
  const isDark = ref(false)
  const activeTab = ref('holdings')
  const fundModalVisible = ref(false)
  const editingFundId = ref(null)
  const showAdvice = ref(false)
  const analysisData = ref(null)

  // ========== 交易状态 ==========
  const tradingBadge = ref({ icon: '', text: '', class: '' })
  const tradingCache = ref(null)

  // ========== 数据加载编排 ==========
  /**
   * 按 Tab 按需加载数据
   */
  async function loadForTab(tabName, showLoading = false) {
    const fundStore = useFundStore()
    const configStore = useConfigStore()
    const historyStore = useHistoryStore()
    const chatStore = useChatStore()

    // 重置对应标志，确保拿到最新数据
    switch (tabName) {
      case 'holdings':
        fundStore.resetLoadFlags()
        configStore.resetLoadFlag()
        chatStore.resetLoadFlags()
        break
      case 'trade':
        fundStore.resetLoadFlags()
        configStore.resetLoadFlag()
        historyStore.resetLoadFlag()
        chatStore.resetLoadFlags()
        break
      case 'strategy':
        fundStore.resetLoadFlags()
        configStore.resetLoadFlag()
        chatStore.resetLoadFlags()
        break
      case 'mine':
        fundStore.resetLoadFlags()
        configStore.resetLoadFlag()
        historyStore.resetLoadFlag()
        chatStore.resetLoadFlags()
        break
    }

    if (showLoading) loading.value = true
    try {
      switch (tabName) {
        case 'holdings':
          await Promise.all([fundStore.loadFunds(), configStore.loadConfig(), fundStore.loadSnapshots(), chatStore.loadChatAndHealth()])
          break
        case 'trade':
          await Promise.all([fundStore.loadFunds(), configStore.loadConfig(), historyStore.loadHistory(), chatStore.loadChatAndHealth()])
          break
        case 'strategy':
          await Promise.all([fundStore.loadFunds(), configStore.loadConfig(), chatStore.loadChatAndHealth()])
          break
        case 'mine':
          await Promise.all([fundStore.loadFunds(), configStore.loadConfig(), historyStore.loadHistory(), chatStore.loadChatAndHealth()])
          break
      }
    } catch (e) {
      console.error('加载数据失败:', e)
      chatStore.aiStatus.connected = false
    } finally {
      if (showLoading) loading.value = false
    }
  }

  async function refreshForTab(tabName) {
    await loadForTab(tabName)
  }

  async function loadAll() {
    const fundStore = useFundStore()
    const configStore = useConfigStore()
    const historyStore = useHistoryStore()
    const chatStore = useChatStore()

    fundStore.resetLoadFlags()
    configStore.resetLoadFlag()
    historyStore.resetLoadFlag()
    chatStore.resetLoadFlags()

    loading.value = true
    try {
      const [cfg, fundList, hist, chat, health] = await Promise.all([
        api.getConfig().catch(() => ({ ...configStore.config })),
        api.getFunds().catch(() => []),
        api.getHistory().catch(() => []),
        api.getChatMessages().catch(() => []),
        api.health().catch(() => ({ llm_configured: false, model: '' })),
      ])

      Object.assign(configStore.config, cfg)
      fundStore.funds = fundList
      historyStore.history = hist.map(h => ({ ...h, canUndo: !!h.snapshot_before, aiEvaluation: h.ai_evaluation || '' }))
      chatStore.chatMessages = chat
      chatStore.aiStatus = { configured: health.llm_configured, model: health.model, connected: true }

      for (const f of fundStore.funds) {
        try {
          const snaps = await api.getSnapshots(f.id)
          fundStore.dailySnapshots[f.id] = snaps.map(s => ({
            date: s.date, safetyCushion: s.safetyCushion,
            recoveryNeeded: s.recoveryNeeded, todayChange: s.todayChange,
            totalReturn: s.totalReturn,
          }))
        } catch { /* skip */ }
      }

      fundStore._fundsLoaded = true
      fundStore._snapshotsLoaded = true
      configStore._configLoaded = true
      historyStore._historyLoaded = true
      chatStore._chatLoaded = true
      chatStore._healthLoaded = true
    } catch (e) {
      console.error('加载数据失败:', e)
      chatStore.aiStatus.connected = false
    } finally {
      loading.value = false
    }
  }

  // ========== 登录 ==========
  function checkLoginState() {
    try {
      const saved = localStorage.getItem('fund_keeper_user')
      if (saved) {
        const data = JSON.parse(saved)
        if (data.loggedInAt && Date.now() - data.loggedInAt < 30 * 24 * 60 * 60 * 1000) {
          userInfo.value = data
          isLoggedIn.value = true
          return true
        }
      }
    } catch { /* ignore */ }
    return false
  }

  function doLogin(info) {
    userInfo.value = info
    isLoggedIn.value = true
  }

  function doLogout() {
    localStorage.removeItem('fund_keeper_user')
    window.location.reload()
  }

  // ========== 主题 ==========
  function toggleTheme() {
    isDark.value = !isDark.value
    document.documentElement.classList.toggle('dark', isDark.value)
  }

  function initTheme() {
    if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
      isDark.value = true
      document.documentElement.classList.add('dark')
    }
  }

  // ========== 弹窗 ==========
  function openFundModal(id) {
    editingFundId.value = null
    fundModalVisible.value = true
    // 通过 nextTick 在 App.vue 层处理
    return { async: true, id }
  }

  function closeFundModal() {
    fundModalVisible.value = false
  }

  // ========== 交易状态 ==========
  async function fetchTradingStatus() {
    try {
      const today = new Date().toISOString().slice(0, 10)
      if (tradingCache.value && tradingCache.value.date === today) return tradingCache.value
      const res = await fetch('/api/calendar/trading-status')
      const data = await res.json()
      tradingCache.value = { ...data, date: today }
      return data
    } catch {
      return null
    }
  }

  function updateTradingBadge() {
    const d = new Date()
    const day = d.getDay()
    const h = d.getHours()
    const m = d.getMinutes()

    const ts = tradingCache.value
    if (ts && ts.date === new Date().toISOString().slice(0, 10)) {
      if (!ts.trading) {
        if (ts.holiday && ts.holiday_name) {
          tradingBadge.value = { icon: '🎌', text: `${ts.holiday_name}休市`, class: 'badge-closed' }
        } else {
          tradingBadge.value = { icon: '⚪', text: '今日休市', class: 'badge-closed' }
        }
        return
      }
    } else {
      if (day === 0 || day === 6) {
        tradingBadge.value = { icon: '⚪', text: '今日休市', class: 'badge-closed' }
        return
      }
    }

    if (h < 15) {
      const remain = (14 - h) * 60 + (60 - m)
      const rh = Math.floor(remain / 60)
      const rm = remain % 60
      tradingBadge.value = { icon: '🕘', text: `距截止 ${rh}时${rm}分`, class: 'badge-trading' }
    } else {
      tradingBadge.value = { icon: '⏸️', text: '已闭市 · 明日净值', class: 'badge-closed' }
    }
  }

  return {
    loading,
    isLoggedIn,
    userInfo,
    isDark,
    activeTab,
    fundModalVisible,
    editingFundId,
    showAdvice,
    analysisData,
    tradingBadge,
    tradingCache,
    loadForTab,
    refreshForTab,
    loadAll,
    checkLoginState,
    doLogin,
    doLogout,
    initTheme,
    toggleTheme,
    openFundModal,
    closeFundModal,
    fetchTradingStatus,
    updateTradingBadge,
  }
})
