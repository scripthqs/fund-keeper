<template>
  <van-popup
    v-model:show="visible"
    position="bottom"
    round
    :style="{ height: '85%' }"
    :close-on-click-overlay="false"
    @click-overlay="closeWithConfirm"
  >
    <div class="flex flex-col h-full relative">
      <div
        class="flex items-center justify-between p-4 border-b flex-shrink-0"
        style="border-color: var(--border-color)"
      >
        <h3 class="font-semibold">
          {{ editingFundId ? "编辑基金" : "添加基金" }}
        </h3>
        <van-button round plain size="small" @click="closeWithConfirm"
          >✕</van-button
        >
      </div>
      <div class="flex-1 overflow-y-auto" @focusin="markInteracted">
        <van-form
          ref="formRef"
          label-width="7em"
          label-align="right"
          @submit="save"
        >
          <van-cell-group inset>
            <!-- 基金代码 + 查询按钮 -->
            <div class="flex items-center gap-1 px-0">
              <van-field
                v-model="form.fundCode"
                name="fundCode"
                label="基金代码"
                required
                placeholder="例：000001"
                class="flex-1"
                :rules="[
                  { required: true, message: '请输入基金代码' },
                  { pattern: /^\d{6}$/, message: '请输入6位基金代码' },
                ]"
              />
              <van-button
                type="primary"
                size="small"
                round
                :loading="querying"
                :disabled="!isValidCode"
                class="shrink-0 mr-3"
                @click="queryFundInfo"
                >查询</van-button
              >
            </div>

            <van-field
              v-model="form.name"
              name="name"
              label="基金名称"
              required
              placeholder="输入代码后自动查询，或手动填写"
              :rules="[{ required: true, message: '请输入基金名称' }]"
            />

            <van-field
              v-model.number="form.initialPrincipal"
              name="initialPrincipal"
              label="初始本金 (元)"
              required
              type="number"
              placeholder="10000"
              :rules="[
                { required: true, message: '请输入初始本金' },
                { validator: (val) => val > 0, message: '金额必须大于0' },
              ]"
            />

            <van-field
              v-model="form.buyDate"
              name="buyDate"
              label="买入日期"
              placeholder="YYYY-MM-DD"
              @click="showCalendar = true"
              readonly
            />

            <van-field
              v-model.number="form.currentMarketValue"
              name="currentMarketValue"
              label="当前市值 (元)"
              required
              type="number"
              placeholder="10000"
              :rules="[
                { required: true, message: '请输入当前市值' },
                { validator: (val) => val > 0, message: '金额必须大于0' },
              ]"
            />

            <van-field
              v-model.number="form.totalBuyAmount"
              name="totalBuyAmount"
              label="累计买入 (元)"
              required
              type="number"
              placeholder="10000"
              :rules="[
                { required: true, message: '请输入累计买入金额' },
                { validator: (val) => val > 0, message: '金额必须大于0' },
              ]"
            />

            <van-field
              v-model.number="form.totalSellAmount"
              name="totalSellAmount"
              label="累计卖出 (元)"
              type="number"
              placeholder="0"
            />

            <van-field
              :model-value="fmtReturnRate"
              name="currentReturnRate"
              label="总收益率 (%)"
              readonly
              :class="autoReturnRate >= 0 ? 'text-red-500' : 'text-green-500'"
            />
          </van-cell-group>

          <!-- ===== 基金独立加仓配置 ===== -->
          <van-cell-group inset style="margin-top: 12px">
            <div class="flex items-center justify-between px-3 py-2">
              <span
                class="text-sm font-medium"
                style="color: var(--text-primary)"
                >📊 加仓档位配置</span
              >
              <van-button
                size="mini"
                round
                plain
                type="primary"
                :loading="aiRecommending"
                @click="aiRecommend"
                >🤖 AI 推荐</van-button
              >
            </div>
            <van-field
              v-model.number="form.maxInvestment"
              name="maxInvestment"
              label="预算投入 (元)"
              type="number"
              placeholder="建议填写，AI推荐更加准确"
            />
            <div
              v-if="aiExplanation"
              class="px-3 py-2 text-xs"
              style="color: var(--text-secondary); line-height: 1.5"
            >
              💡 {{ aiExplanation }}
            </div>
            <!-- 宏观分析流式输出（打字机效果，阶段1） -->
            <div
              v-if="(aiRecommending && phase === 'macro') || macroStreamText"
              class="mx-3 mb-2 p-3 rounded-lg"
              style="
                background: linear-gradient(
                  135deg,
                  rgba(82, 196, 26, 0.08),
                  rgba(82, 196, 26, 0.02)
                );
                border: 1px solid rgba(82, 196, 26, 0.15);
              "
            >
              <div class="flex items-center gap-2 mb-1">
                <van-loading
                  v-if="aiRecommending && !macroDone"
                  size="12"
                  type="spinner"
                  color="#52c41a"
                />
                <span class="text-xs font-medium" style="color: #52c41a">
                  {{
                    fetchingData
                      ? "📈 正在获取行情、估值与回测数据..."
                      : aiRecommending && !macroDone
                        ? "📡 宏观政策分析中..."
                        : "📡 宏观政策分析"
                  }}
                </span>
              </div>
              <div
                class="text-xs whitespace-pre-wrap"
                style="
                  color: var(--text-primary);
                  line-height: 1.7;
                  min-height: 24px;
                "
              >
                {{ macroDisplayText || macroStreamText || " "
                }}<span
                  v-if="aiRecommending && !macroDone && macroStreamText"
                  class="inline-block w-1 h-3 ml-0.5 align-middle"
                  style="background: #52c41a; animation: blink 1s infinite"
                ></span>
              </div>
            </div>
            <!-- AI 流式输出策略分析（打字机效果，阶段2） -->
            <div
              v-if="(aiRecommending && phase === 'tier') || aiStreamText"
              class="mx-3 mb-2 p-3 rounded-lg"
              style="
                background: linear-gradient(
                  135deg,
                  rgba(139, 92, 246, 0.08),
                  rgba(59, 130, 246, 0.06)
                );
                border: 1px solid rgba(139, 92, 246, 0.15);
              "
            >
              <div class="flex items-center gap-2 mb-1">
                <van-loading
                  v-if="aiRecommending && phase === 'tier'"
                  size="12"
                  type="spinner"
                  color="#8b5cf6"
                />
                <span class="text-xs font-medium" style="color: #8b5cf6">
                  {{ aiStreamStatus || "AI 策略分析" }}
                </span>
              </div>
              <div
                class="text-xs whitespace-pre-wrap"
                style="
                  color: var(--text-primary);
                  line-height: 1.7;
                  min-height: 24px;
                "
              >
                {{ aiDisplayText || aiStreamText || " "
                }}<span
                  v-if="aiRecommending && phase === 'tier' && aiStreamText"
                  class="inline-block w-1 h-3 ml-0.5 align-middle"
                  style="background: #8b5cf6; animation: blink 1s infinite"
                ></span>
              </div>
            </div>
            <!-- 宏观分析结构化数据展示 -->
            <div
              v-if="macroAnalysis"
              class="mx-3 mb-2 p-2 rounded-lg text-xs"
              :style="
                macroAnalysis.error
                  ? {
                      background: 'rgba(100,100,100,0.06)',
                      border: '1px solid rgba(100,100,100,0.1)',
                    }
                  : macroBgStyle
              "
            >
              <div
                v-if="macroAnalysis.error"
                class="flex items-center gap-1 mb-1 font-medium"
                style="color: var(--text-secondary)"
              >
                <span>📡 宏观分析：未启用</span>
                <span :style="strategyStyleTag">{{ strategyLabel }}</span>
              </div>
              <div v-else class="flex items-center gap-1 mb-1 font-medium flex-wrap">
                <span>📡 宏观分析：{{ macroAnalysis.sector }}</span>
                <span :style="policyScoreStyle"
                  >{{ macroAnalysis.policyScore }}分</span
                >
                <span :style="strategyStyleTag">{{ strategyLabel }}</span>
                <span
                  v-if="macroAnalysis.dataDate"
                  class="font-normal"
                  style="color: var(--text-tertiary); font-size: 11px"
                  >· 实时行情截至 {{ macroAnalysis.dataDate }}</span
                >
              </div>
              <div
                v-if="macroAnalysis.keyPolicies?.length && !macroAnalysis.error"
                class="mb-1"
                style="color: var(--text-secondary)"
              >
                🏛️ {{ macroAnalysis.keyPolicies.join(" · ") }}
              </div>
              <div
                v-if="!macroAnalysis.error"
                style="color: var(--text-secondary)"
              >
                📈 {{ macroAnalysis.trend }}
              </div>
              <div class="mt-1" style="color: var(--text-tertiary)">
                {{ macroAnalysis.analysis }}
                <span
                  v-if="macroAnalysis.error && macroAnalysis.message"
                  class="block mt-1"
                  style="color: #999"
                  >原因：{{ macroAnalysis.message }}</span
                >
              </div>
            </div>
            <!-- 当前档位参数的历史回测摘要 -->
            <div
              v-if="backtestSummary"
              class="mx-3 mb-2 px-3 py-2 rounded-lg text-xs"
              style="
                background: rgba(24, 144, 255, 0.06);
                border: 1px solid rgba(24, 144, 255, 0.15);
                color: var(--text-secondary);
                line-height: 1.6;
              "
            >
              📊 原档位回测（{{ backtestSummary.start_date }} ~
              {{ backtestSummary.end_date }}）：触发
              {{ backtestSummary.trigger_count }}/{{
                backtestSummary.tier_count
              }}
              档，策略 {{ signed(backtestSummary.strategy_return) }} vs 持有
              {{ signed(backtestSummary.hold_return) }}，资金利用率
              {{ backtestSummary.utilization }}%
            </div>
            <div class="tier-grid p-3 flex flex-col gap-2" :key="tierKey">
              <div
                v-for="i in form.addTiers.length"
                :key="i"
                class="flex items-center gap-2"
              >
                <van-field
                  v-model.number="form.addTiers[i - 1].line"
                  :label="`第${i}档(%)`"
                  type="number"
                  size="small"
                  class="flex-1"
                />
                <van-field
                  v-model.number="form.addTiers[i - 1].ratio"
                  label="买入(%)"
                  type="number"
                  size="small"
                  class="flex-1"
                />
              </div>
            </div>

            <!-- 上涨回调加仓策略 -->
            <template
              v-if="
                form.strategyType === 'pullback' && form.pullbackTiers.length
              "
            >
              <div class="flex items-center gap-1 px-3 pt-2">
                <span class="text-sm font-medium" style="color: #fa8c16"
                  >📈 上涨回调加仓</span
                >
                <span
                  class="text-xs px-1 py-0.5 rounded"
                  style="background: rgba(250, 140, 22, 0.1); color: #fa8c16"
                  >牛市策略</span
                >
              </div>
              <div class="px-3 text-xs" style="color: var(--text-secondary)">
                在上涨趋势中，每当基金从近期高点回调一定比例时买入，不错过牛市行情
              </div>
              <div
                class="tier-grid p-3 flex flex-col gap-2"
                :key="pullbackTierKey"
              >
                <div
                  v-for="i in form.pullbackTiers.length"
                  :key="'pb' + i"
                  class="flex items-center gap-2"
                >
                  <van-field
                    v-model.number="form.pullbackTiers[i - 1].line"
                    :label="`回调${i}档(%)`"
                    type="number"
                    size="small"
                    class="flex-1"
                  />
                  <van-field
                    v-model.number="form.pullbackTiers[i - 1].ratio"
                    label="买入(%)"
                    type="number"
                    size="small"
                    class="flex-1"
                  />
                </div>
              </div>
            </template>
          </van-cell-group>

          <!-- ===== 基金独立止盈止损 ===== -->
          <van-cell-group inset style="margin-top: 12px">
            <span
              class="px-3 py-2 text-sm font-medium"
              style="color: var(--text-primary); display: block"
              >🎯 止盈止损配置</span
            >
            <div class="tier-grid p-3 grid grid-cols-2 gap-2">
              <van-field
                v-model.number="form.stopProfitLine"
                label="止盈线(%)"
                type="number"
                size="small"
                placeholder="如 25"
              />
              <van-field
                v-model.number="form.stopProfitRatio"
                label="止盈卖出(%)"
                type="number"
                size="small"
                placeholder="如 20"
              />
              <van-field
                v-model.number="form.stopLossLine"
                label="止损线(%)"
                type="number"
                size="small"
                placeholder="如 -30"
              />
              <van-field
                v-model.number="form.stopLossRatio"
                label="止损卖出(%)"
                type="number"
                size="small"
                placeholder="如 60"
              />
            </div>
            <div
              class="px-3 pb-3 text-xs text-right"
              style="color: var(--text-secondary)"
            >
              填 0 则使用全局配置 | AI 推荐会一并生成
            </div>
          </van-cell-group>
          <div class="flex gap-2 mt-4">
            <van-button
              type="primary"
              round
              block
              :loading="saving"
              loading-text="保存中..."
              @click="formRef?.submit()"
              >💾 保存</van-button
            >
            <van-button round plain block @click="closeWithConfirm"
              >取消</van-button
            >
          </div>
        </van-form>
      </div>
    </div>
  </van-popup>

  <van-calendar
    v-model:show="showCalendar"
    :min-date="minDate"
    :max-date="maxDate"
    @confirm="onDateConfirm"
  />
</template>

<script setup>
import { ref, inject, watch, computed } from "vue";
import { showTip, showError, askConfirm } from "../utils/dialog";
import { round, B } from "../utils/bigMath";
import { api } from "../api";

const emit = defineEmits(["close"]);
const store = inject("store");
const editingFundId = inject("editingFundId");
const saving = ref(false);
const querying = ref(false);
const aiRecommending = ref(false);
const aiExplanation = ref("");
const aiStreamText = ref(""); // 流式接收的策略分析文本（阶段2）
const aiStreamStatus = ref(""); // 流式状态文案
const aiDisplayText = ref(""); // 打字机显示的策略文本
const aiTypewriterRunning = ref(false);
// 宏观分析流式状态（阶段1）
const macroStreamText = ref(""); // 流式接收的宏观分析文本
const macroDisplayText = ref(""); // 打字机显示的宏观文本
const macroTypewriterRunning = ref(false);
const phase = ref(""); // 当前流式阶段：'macro' | 'tier'
const macroAnalysis = ref(null);
const backtestSummary = ref(null); // 当前档位参数的历史回测摘要
const fetchingData = ref(false); // 正在抓取行情/估值/回测数据（LLM 开始前）
const macroDone = ref(false); // 宏观分析流是否结束（宏观/策略两路并发，各自独立）
const strategyStyle = ref("");
const hasInteracted = ref(false);
const visible = ref(true);
const showCalendar = ref(false);
const formRef = ref(null);

const minDate = new Date(2000, 0, 1);
const maxDate = new Date();

const defaultTiers = () => [
  { line: -8, ratio: 5 },
  { line: -12, ratio: 10 },
  { line: -17, ratio: 18 },
  { line: -22, ratio: 28 },
];

const defaultPullbackTiers = () => [
  { line: -3, ratio: 5 },
  { line: -6, ratio: 10 },
  { line: -10, ratio: 20 },
  { line: -15, ratio: 35 },
];

// 新建基金默认档位（与默认策略一致，可按需修改）

const form = ref({
  name: "",
  fundCode: "",
  initialPrincipal: 0,
  buyDate: new Date().toISOString().split("T")[0],
  currentMarketValue: 0,
  totalBuyAmount: 0,
  totalSellAmount: 0,
  currentReturnRate: 0,
  maxInvestment: undefined,
  addTiers: defaultTiers(),
  strategyType: "downside",
  pullbackTiers: [],
  stopProfitLine: 0,
  stopLossLine: 0,
  stopProfitRatio: 0,
  stopLossRatio: 0,
});

/** 编辑模式下表单初始快照，用于检测是否有实际修改 */
const formSnapshot = ref(null);

const hasFormData = computed(() => {
  const f = form.value;
  const snap = formSnapshot.value;
  // 编辑模式：对比快照，检查是否有任何字段被修改
  if (snap) {
    for (const key of Object.keys(snap)) {
      if (key === "addTiers" || key === "pullbackTiers") {
        const a = f[key] || [];
        const b = snap[key] || [];
        if (a.length !== b.length) return true;
        if (a.some((t, i) => t.line !== b[i].line || t.ratio !== b[i].ratio))
          return true;
      } else if (f[key] !== snap[key]) {
        return true;
      }
    }
    return false;
  }
  // 新增模式：检查是否有任何有效数据
  return (
    f.name.trim() !== "" ||
    f.initialPrincipal > 0 ||
    f.currentMarketValue > 0 ||
    f.totalBuyAmount > 0 ||
    f.totalSellAmount > 0 ||
    f.maxInvestment > 0
  );
});

const isValidCode = computed(() => /^\d{6}$/.test(form.value.fundCode || ""));

/** 档位内容指纹，变化时强制重建整个档位区域 */
const tierKey = computed(() =>
  (form.value.addTiers || []).map((t) => t.line + "," + t.ratio).join("|"),
);
/** 回调加仓档位内容指纹 */
const pullbackTierKey = computed(() =>
  (form.value.pullbackTiers || []).map((t) => t.line + "," + t.ratio).join("|"),
);

/** 自动计算总收益率 = (市值 - 累计买入 + 累计卖出) ÷ 累计买入 × 100 */
const autoReturnRate = computed(() => {
  const f = form.value;
  if (!f.totalBuyAmount || f.totalBuyAmount <= 0) return null;
  const profit = B(f.currentMarketValue || 0)
    .minus(f.totalBuyAmount)
    .plus(f.totalSellAmount || 0);
  return round(profit.div(f.totalBuyAmount).times(100));
});

const fmtReturnRate = computed(() => {
  const r = autoReturnRate.value;
  if (r == null) return "--";
  return (r >= 0 ? "+" : "") + r.toFixed(2) + "%";
});

/** 自动收益率变化时同步到表单字段，避免 AI 推荐拿到旧值 */
watch(autoReturnRate, (val) => {
  if (val != null) form.value.currentReturnRate = val;
});

/** 宏观分析背景色 */
const macroBgStyle = computed(() => {
  const score = macroAnalysis.value?.policyScore ?? 50;
  if (score >= 80)
    return {
      background:
        "linear-gradient(135deg, rgba(255,77,79,0.08), rgba(255,77,79,0.02))",
      border: "1px solid rgba(255,77,79,0.15)",
    };
  if (score >= 60)
    return {
      background:
        "linear-gradient(135deg, rgba(255,170,0,0.08), rgba(255,170,0,0.02))",
      border: "1px solid rgba(255,170,0,0.15)",
    };
  if (score >= 40)
    return {
      background:
        "linear-gradient(135deg, rgba(100,100,100,0.06), rgba(100,100,100,0.02))",
      border: "1px solid rgba(100,100,100,0.1)",
    };
  return {
    background:
      "linear-gradient(135deg, rgba(0,122,255,0.06), rgba(0,122,255,0.02))",
    border: "1px solid rgba(0,122,255,0.12)",
  };
});

/** 政策评分颜色 */
const policyScoreStyle = computed(() => {
  const score = macroAnalysis.value?.policyScore ?? 50;
  if (score >= 80) return { color: "#ff4d4f", fontWeight: "bold" };
  if (score >= 60) return { color: "#fa8c16", fontWeight: "bold" };
  if (score >= 40) return { color: "#666" };
  return { color: "#1890ff", fontWeight: "bold" };
});

/** 策略风格标签 */
const strategyStyleTag = computed(() => {
  const style = strategyStyle.value || macroAnalysis.value?.aggressiveness;
  if (typeof style === "number") {
    if (style > 0.15)
      return {
        color: "#ff4d4f",
        background: "rgba(255,77,79,0.1)",
        padding: "1px 6px",
        borderRadius: "4px",
      };
    if (style < -0.15)
      return {
        color: "#1890ff",
        background: "rgba(24,144,255,0.1)",
        padding: "1px 6px",
        borderRadius: "4px",
      };
    return {
      color: "#666",
      background: "rgba(100,100,100,0.08)",
      padding: "1px 6px",
      borderRadius: "4px",
    };
  }
  if (style?.includes("激进"))
    return {
      color: "#ff4d4f",
      background: "rgba(255,77,79,0.1)",
      padding: "1px 6px",
      borderRadius: "4px",
    };
  if (style?.includes("保守") || style?.includes("防御"))
    return {
      color: "#1890ff",
      background: "rgba(24,144,255,0.1)",
      padding: "1px 6px",
      borderRadius: "4px",
    };
  return {
    color: "#666",
    background: "rgba(100,100,100,0.08)",
    padding: "1px 6px",
    borderRadius: "4px",
  };
});

/** 策略标签文字 */
const strategyLabel = computed(() => {
  if (macroAnalysis.value?.error) return "AI 推荐";
  return strategyStyle.value || "标准策略";
});

function markInteracted() {
  hasInteracted.value = true;
}

/** 带符号的百分比展示：12.3 → "+12.3%"，-4.5 → "-4.5%" */
function signed(v) {
  if (v == null) return "--";
  return (v >= 0 ? "+" : "") + v + "%";
}

function onDateConfirm(date) {
  form.value.buyDate = date.toISOString().split("T")[0];
  showCalendar.value = false;
}

async function queryFundInfo() {
  const code = (form.value.fundCode || "").trim();
  if (!/^\d{6}$/.test(code)) {
    showTip("请输入6位基金代码");
    return;
  }
  querying.value = true;
  try {
    const info = await store.queryFund(code);
    form.value.name = info.name;
    // 展示查询结果（含实时估值）
    let tipMsg = `已查询到：${info.name}（净值 ${info.nav}`;
    if (info.estimated_nav != null && info.estimated_nav > 0) {
      const sign =
        info.estimated_change != null && info.estimated_change >= 0 ? "+" : "";
      tipMsg += `，估算 ${info.estimated_nav} ${sign}${info.estimated_change ?? "--"}%`;
      if (info.update_time) tipMsg += ` ${info.update_time}`;
    }
    tipMsg += "）";
    showTip(tipMsg);
  } catch (e) {
    const errMsg = e.message || "未知错误";
    showError(errMsg);
  } finally {
    querying.value = false;
  }
}

watch(
  editingFundId,
  async (id) => {
    formRef.value?.resetValidation();
    aiExplanation.value = "";
    aiStreamText.value = "";
    aiDisplayText.value = "";
    aiTypewriterRunning.value = false;
    macroStreamText.value = "";
    macroDisplayText.value = "";
    macroTypewriterRunning.value = false;
    phase.value = "";
    aiStreamStatus.value = "";
    macroAnalysis.value = null;
    backtestSummary.value = null;
    fetchingData.value = false;
    macroDone.value = false;
    strategyStyle.value = "";

    if (id) {
      const fund = store.funds.value.find((f) => f.id === id);
      if (fund) {
        Object.assign(form.value, {
          ...fund,
          maxInvestment: fund.maxInvestment ?? 0,
          addTiers: fund.addTiers?.length ? [...fund.addTiers] : defaultTiers(),
          strategyType: fund.strategyType || "downside",
          pullbackTiers: fund.pullbackTiers?.length
            ? [...fund.pullbackTiers]
            : [],
          stopProfitLine: fund.stopProfitLine ?? 0,
          stopLossLine: fund.stopLossLine ?? 0,
          stopProfitRatio: fund.stopProfitRatio ?? 0,
          stopLossRatio: fund.stopLossRatio ?? 0,
        });
        // 编辑模式：保存初始快照，用于后续检测是否有实际修改
        formSnapshot.value = JSON.parse(JSON.stringify(form.value));
      }
      hasInteracted.value = false;
    } else {
      Object.assign(form.value, {
        name: "",
        fundCode: "",
        initialPrincipal: 0,
        buyDate: new Date().toISOString().split("T")[0],
        currentMarketValue: 0,
        totalBuyAmount: 0,
        totalSellAmount: 0,
        currentReturnRate: 0,
        maxInvestment: undefined,
        addTiers: defaultTiers(),
        strategyType: "downside",
        pullbackTiers: [],
        stopProfitLine: 0,
        stopLossLine: 0,
        stopProfitRatio: 0,
        stopLossRatio: 0,
      });
      // 新增模式：清空快照，使用 hasFormData 的增量检查逻辑
      formSnapshot.value = null;
      hasInteracted.value = false;
    }
  },
  { immediate: true },
);

async function aiRecommend() {
  const f = form.value;
  if (!f.initialPrincipal || f.initialPrincipal <= 0) {
    showTip("请先填写初始本金");
    return;
  }
  aiRecommending.value = true;
  aiExplanation.value = "";
  aiStreamText.value = "";
  aiDisplayText.value = "";
  aiTypewriterRunning.value = false;
  macroStreamText.value = "";
  macroDisplayText.value = "";
  macroTypewriterRunning.value = false;
  macroAnalysis.value = null;
  backtestSummary.value = null;
  fetchingData.value = false;
  macroDone.value = false;
  phase.value = "macro";
  aiStreamStatus.value = "";

  // 清除旧 timer
  clearTypewriter("macro");
  clearTypewriter("tier");

  try {
    // 计算持有天数
    const buyMs = new Date(f.buyDate).getTime();
    const nowMs = Date.now();
    const holdDays = buyMs > 0 ? Math.floor((nowMs - buyMs) / 86400000) : 0;

    for await (const event of api.aiRecommendTiersStream({
      fundName: f.name || "待配置基金",
      fundCode: (f.fundCode || "").trim(),
      currentTiers: (f.addTiers || [])
        .filter((t) => t.ratio > 0 && t.line < 0)
        .map((t) => ({ line: t.line, ratio: t.ratio })),
      totalBuyAmount: f.totalBuyAmount || f.initialPrincipal,
      initialPrincipal: f.initialPrincipal,
      maxInvestment: f.maxInvestment || 0,
      currentReturnRate: autoReturnRate.value ?? (f.currentReturnRate || 0),
      currentMarketValue: f.currentMarketValue || f.initialPrincipal,
      holdDays,
    })) {
      if (event.connected) continue;
      if (event.reasoning) {
        const p = event.phase || phase.value;
        aiStreamStatus.value =
          p === "macro"
            ? "📡 AI 正在思考宏观政策..."
            : "AI 正在深度思考策略...";
        continue;
      }
      if (event.status) {
        const statusMap = {
          fetching_data: "📈 正在获取行情、估值与回测数据...",
          macro_analyzing: "📡 正在分析宏观政策环境...",
          generating_strategy: "📊 正在生成加仓档位策略...",
        };
        aiStreamStatus.value = statusMap[event.status] || aiStreamStatus.value;
        fetchingData.value = event.status === "fetching_data";
        // 策略开始生成：宏观可能仍在流式，两个卡片各自独立播放，不打断宏观
        if (event.status === "generating_strategy") {
          phase.value = "tier";
        }
        if (event.status === "macro_done") {
          macroDone.value = true;
          clearTypewriter("macro");
          macroDisplayText.value = macroStreamText.value; // 显示全部
        }
        continue;
      }
      if (event.error) {
        throw new Error(event.error);
      }

      // 阶段1：宏观分析文本流
      if (event.macroContent) {
        macroStreamText.value += event.macroContent;
        if (!macroTypewriterRunning.value) {
          startTypewriter("macro");
        }
        continue;
      }

      // 阶段2：策略分析文本流
      if (event.content) {
        aiStreamText.value += event.content;
        if (!aiTypewriterRunning.value) {
          startTypewriter("tier");
        }
        continue;
      }

      if (event.done && event.result) {
        const result = event.result;
        if (result.tiers?.length) {
          form.value.addTiers = result.tiers.map((t) => ({
            line: t.line,
            ratio: t.ratio,
          }));
        }
        form.value.strategyType = result.strategyType || "downside";
        if (result.pullbackTiers?.length) {
          form.value.pullbackTiers = result.pullbackTiers.map((t) => ({
            line: t.line,
            ratio: t.ratio,
          }));
        } else {
          form.value.pullbackTiers = [];
        }
        if (result.stopProfitLine)
          form.value.stopProfitLine = result.stopProfitLine;
        if (result.stopLossLine) form.value.stopLossLine = result.stopLossLine;
        if (result.stopProfitRatio)
          form.value.stopProfitRatio = result.stopProfitRatio;
        if (result.stopLossRatio)
          form.value.stopLossRatio = result.stopLossRatio;
        aiExplanation.value = result.explanation || "";
        macroAnalysis.value = result.macroAnalysis || null;
        backtestSummary.value = result.backtest || null;
        strategyStyle.value = result.strategyStyle || "";
        macroDone.value = true;
        // 等待两个打字机完成显示
        clearTypewriter("macro");
        macroDisplayText.value = macroStreamText.value;
        await waitForTypewriterDrain("tier");
        showTip("✅ AI 已结合宏观政策分析推荐完整交易策略");
        break;
      }
    }
  } catch (e) {
    showError("AI 推荐失败: " + (e.message || "网络错误"));
  } finally {
    aiRecommending.value = false;
    aiStreamStatus.value = "";
    phase.value = "";
    clearTypewriter("macro");
    clearTypewriter("tier");
    aiTypewriterRunning.value = false;
    macroTypewriterRunning.value = false;
  }
}

// ===== 双打字机 =====
const typewriterTimers = { macro: null, tier: null };
function startTypewriter(name) {
  const isMacro = name === "macro";
  if (isMacro) macroTypewriterRunning.value = true;
  else aiTypewriterRunning.value = true;

  typewriterTimers[name] = setInterval(() => {
    const src = isMacro ? macroStreamText : aiStreamText;
    const dst = isMacro ? macroDisplayText : aiDisplayText;
    if (dst.value.length < src.value.length) {
      // 自适应步进：积压越多走得越快，避免大段缓冲内容被打字动画拖住
      const backlog = src.value.length - dst.value.length;
      const step = backlog > 200 ? 8 : backlog > 80 ? 4 : 2;
      const next = Math.min(src.value.length, dst.value.length + step);
      dst.value = src.value.slice(0, next);
    } else {
      clearTypewriter(name);
    }
  }, 30);
}
function clearTypewriter(name) {
  if (typewriterTimers[name]) {
    clearInterval(typewriterTimers[name]);
    typewriterTimers[name] = null;
  }
}
function waitForTypewriterDrain(name) {
  return new Promise((resolve) => {
    const isMacro = name === "macro";
    const src = isMacro ? macroStreamText : aiStreamText;
    const dst = isMacro ? macroDisplayText : aiDisplayText;
    const check = () => {
      if (dst.value.length >= src.value.length) {
        resolve();
      } else {
        setTimeout(check, 50);
      }
    };
    check();
  });
}

async function closeWithConfirm() {
  if (hasFormData.value) {
    if (!(await askConfirm("表单有未保存的数据，确定关闭吗？"))) return;
  }
  formRef.value?.resetValidation();
  visible.value = false;
  emit("close");
}

/** 将空字符串 / NaN 统一转为数字 0，避免 Pydantic 422 */
function cleanNumeric(val) {
  if (
    val === "" ||
    val === null ||
    val === undefined ||
    (typeof val === "number" && isNaN(val))
  )
    return 0;
  return val;
}

async function save() {
  saving.value = true;
  try {
    // 如果所有档位比例都为 0 或无有效值，视为不使用独立配置
    const validTiers = (form.value.addTiers || []).filter(
      (t) => t.ratio > 0 && t.line < 0,
    );
    const validPullbackTiers = (form.value.pullbackTiers || []).filter(
      (t) => t.ratio > 0 && t.line < 0,
    );
    const raw = form.value;
    const data = {
      name: raw.name,
      fundCode: raw.fundCode || "",
      initialPrincipal: cleanNumeric(raw.initialPrincipal),
      buyDate: raw.buyDate,
      totalBuyAmount:
        cleanNumeric(raw.totalBuyAmount) || cleanNumeric(raw.initialPrincipal),
      totalSellAmount: cleanNumeric(raw.totalSellAmount),
      currentMarketValue:
        cleanNumeric(raw.currentMarketValue) ||
        cleanNumeric(raw.initialPrincipal),
      currentReturnRate: 0,
      maxInvestment: cleanNumeric(raw.maxInvestment),
      addTiers: validTiers,
      strategyType: raw.strategyType || "downside",
      pullbackTiers: validPullbackTiers,
      stopProfitLine: cleanNumeric(raw.stopProfitLine),
      stopLossLine: cleanNumeric(raw.stopLossLine),
      stopProfitRatio: cleanNumeric(raw.stopProfitRatio),
      stopLossRatio: cleanNumeric(raw.stopLossRatio),
    };
    // 自动计算总收益率
    const profit = B(data.currentMarketValue || 0)
      .minus(data.totalBuyAmount)
      .plus(data.totalSellAmount || 0);
    data.currentReturnRate =
      data.totalBuyAmount > 0
        ? round(profit.div(data.totalBuyAmount).times(100))
        : 0;
    if (editingFundId.value) await store.updateFund(editingFundId.value, data);
    else await store.createFund(data);
    hasInteracted.value = false;
    formRef.value?.resetValidation();
    visible.value = false;
    emit("close");
  } catch (e) {
    showError("保存失败: " + e.message);
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
/* van-field error 样式微调 */
::deep(.van-field--error .van-field__control) {
  --van-field-control-error-color: #ef4444;
}

/* 档位/止盈止损网格内的半宽字段：标签宽度自适应内容，避免被表单级 label-width=7em 遮挡 */
.tier-grid :deep(.van-field__label) {
  width: auto !important;
  flex: none;
  white-space: nowrap;
  font-size: 0.8rem;
  margin-right: 6px;
}
.tier-grid :deep(.van-field__control) {
  min-width: 0;
}
/* AI 打字机光标闪烁 */
@keyframes blink {
  0%,
  50% {
    opacity: 1;
  }
  51%,
  100% {
    opacity: 0;
  }
}
</style>
