<template>
  <van-pull-refresh v-model="refreshing" @refresh="onRefresh">
    <div class="tab-page">
      <DailyAnalysis ref="dailyAnalysisRef" @add-fund="$emit('addFund', $event)" />
      <AdviceResult v-if="showAdvice" @close="showAdvice = false" @action-done="showAdvice = false" />

      <!-- AI 整体组合分析结果（放在最后） -->
      <div v-if="oa.overallAnalysisResult || oa.overallAnalyzing" class="mt-3 overall-analysis-card" :class="{ 'overall-loading': oa.overallAnalyzing }">
        <div class="overall-analysis-header">
          <span class="overall-analysis-title">🤖 AI 整体组合分析</span>
          <span v-if="oa.overallAnalyzing" class="overall-analysis-status">
            <van-loading size="14" color="#12edd7" /> 分析中...
          </span>
          <span v-else class="overall-analysis-time">{{ oa.overallAnalysisTime }}</span>
        </div>
        <!-- 加载中：还没收到任何内容 -->
        <div v-if="oa.overallAnalyzing && !oa.overallAnalysisResult" class="overall-analysis-loading-text">
          <van-loading size="18" color="#12edd7" />
          <span>{{ oa.streamConnected ? (oa.reasoningPhase ? '正在深度思考，分析您的持仓...' : '已连接，正在等待 AI 生成回复...') : '正在连接分析服务...' }}</span>
        </div>
        <!-- 流式输出中：显示原始文本，保持打字机效果 -->
        <div v-else-if="oa.overallAnalyzing && oa.overallAnalysisResult" class="overall-analysis-body overall-analysis-stream-text">{{ oa.overallAnalysisResult }}</div>
        <!-- 完成：渲染 Markdown -->
        <div v-else class="overall-analysis-body" v-html="renderMarkdown(oa.overallAnalysisResult)"></div>
        <div v-if="oa.overallAnalysisResult" class="overall-analysis-footer">
          <van-button size="small" round plain type="primary" :loading="oa.overallAnalyzing" @click="oa.refreshOverallAnalysis()">🔄 重新分析</van-button>
        </div>
      </div>
    </div>
  </van-pull-refresh>
</template>

<script setup>
import { ref, inject, computed, unref } from 'vue'
import DailyAnalysis from '../DailyAnalysis.vue'
import AdviceResult from '../AdviceResult.vue'
import { renderMarkdown } from '../../utils/helpers'

const store = inject('store')
const showAdvice = inject('showAdvice')
const refreshing = ref(false)

const dailyAnalysisRef = ref(null)

// 通过 computed 代理 DailyAnalysis 暴露的状态，保持响应式
const oa = computed(() => {
  const da = dailyAnalysisRef.value
  if (!da) return {
    overallAnalyzing: false,
    overallAnalysisResult: '',
    overallAnalysisTime: '',
    streamConnected: false,
    reasoningPhase: false,
  }
  return {
    overallAnalyzing: unref(da.overallAnalyzing),
    overallAnalysisResult: unref(da.overallAnalysisResult),
    overallAnalysisTime: unref(da.overallAnalysisTime),
    streamConnected: unref(da.streamConnected),
    reasoningPhase: unref(da.reasoningPhase),
    refreshOverallAnalysis: da.refreshOverallAnalysis,
  }
})

async function onRefresh() {
  await store.refreshForTab('holdings')
  refreshing.value = false
}
</script>

<script>
export default { emits: ['addFund'] }
</script>

<style scoped>
/* AI 整体组合分析卡片 */
.overall-analysis-card {
  background: linear-gradient(135deg, rgba(18, 237, 215, 0.06), rgba(18, 237, 215, 0.02));
  border: 1px solid rgba(18, 237, 215, 0.15);
  border-radius: 12px;
  padding: 12px;
  transition: all 0.3s ease;
}
.overall-analysis-card.overall-loading {
  opacity: 0.9;
}
.overall-analysis-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(18, 237, 215, 0.1);
}
.overall-analysis-title {
  font-size: 14px;
  font-weight: 600;
  color: #12edd7;
}
.overall-analysis-status {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}
.overall-analysis-time {
  font-size: 11px;
  color: var(--text-secondary);
}
.overall-analysis-loading-text {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 24px 12px;
  font-size: 13px;
  color: var(--text-secondary);
}
.overall-analysis-body {
  font-size: 14px;
  line-height: 1.8;
  color: #2c3e50;
  word-break: break-word;
  padding: 4px 0;
}

/* 流式输出原始文本：保留换行和空白，模拟打字机效果 */
.overall-analysis-stream-text {
  white-space: pre-wrap;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  font-size: 14px;
  line-height: 1.85;
  color: #2c3e50;
}

/* Markdown 渲染后的子元素样式 */
.overall-analysis-body :deep(h1) {
  font-size: 16px;
  font-weight: 700;
  margin: 12px 0 6px;
  color: #0ba890;
}
.overall-analysis-body :deep(h2) {
  font-size: 15px;
  font-weight: 700;
  margin: 10px 0 5px;
  color: #0ba890;
}
.overall-analysis-body :deep(h3) {
  font-size: 14px;
  font-weight: 600;
  margin: 8px 0 4px;
  color: #34495e;
}
.overall-analysis-body :deep(p) {
  margin: 6px 0;
  color: #2c3e50;
}
.overall-analysis-body :deep(strong) {
  color: #0ba890;
  font-weight: 700;
}
.overall-analysis-body :deep(ul),
.overall-analysis-body :deep(ol) {
  margin: 4px 0 8px;
  padding-left: 20px;
}
.overall-analysis-body :deep(ul) {
  list-style: none;
}
.overall-analysis-body :deep(ul li) {
  position: relative;
  margin: 3px 0;
  padding-left: 4px;
}
.overall-analysis-body :deep(ul li::before) {
  content: '';
  position: absolute;
  left: -16px;
  top: 9px;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: rgba(18, 237, 215, 0.5);
}
.overall-analysis-body :deep(ol li) {
  margin: 3px 0;
}
.overall-analysis-body :deep(pre) {
  background: rgba(18, 237, 215, 0.06);
  border: 1px solid rgba(18, 237, 215, 0.12);
  border-radius: 6px;
  padding: 10px 12px;
  margin: 6px 0;
  font-size: 12px;
  line-height: 1.6;
  overflow-x: auto;
}
.overall-analysis-body :deep(pre code) {
  background: none;
  padding: 0;
  font-size: 12px;
  color: inherit;
}
.overall-analysis-body :deep(code) {
  background: rgba(18, 237, 215, 0.08);
  border-radius: 3px;
  padding: 1px 5px;
  font-size: 12px;
  color: #12edd7;
}
.overall-analysis-footer {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid rgba(18, 237, 215, 0.1);
  display: flex;
  justify-content: flex-end;
}
</style>
