"""Pydantic 数据模型 - 请求与响应定义"""

from typing import List, Optional

from pydantic import BaseModel, Field


# ==================== 加仓档位（需先定义，被 FundBase / ConfigUpdate 引用）====================

class AddTier(BaseModel):
    line: float
    ratio: float


# ==================== 基金 ====================

class FundBase(BaseModel):
    name: str
    fund_code: str = Field("", alias="fundCode")
    fund_shares: float = Field(0, alias="fundShares")
    initial_principal: float = Field(0, alias="initialPrincipal")
    buy_date: str = Field("", alias="buyDate")
    total_buy_amount: float = Field(0, alias="totalBuyAmount")
    total_sell_amount: float = Field(0, alias="totalSellAmount")
    current_market_value: float = Field(0, alias="currentMarketValue")
    current_return_rate: float = Field(0, alias="currentReturnRate")
    max_investment: float = Field(0, alias="maxInvestment")
    add_tiers: List[AddTier] = Field(default_factory=list, alias="addTiers")
    strategy_type: str = Field("downside", alias="strategyType")  # "downside" 越跌越买 | "pullback" 上涨回调加仓
    pullback_tiers: List[AddTier] = Field(default_factory=list, alias="pullbackTiers")  # 上涨回调加仓档位
    # 基金独立止盈止损（0 表示使用全局配置）
    stop_profit_line: float = Field(0, alias="stopProfitLine")
    stop_loss_line: float = Field(0, alias="stopLossLine")
    stop_profit_ratio: float = Field(0, alias="stopProfitRatio")
    stop_loss_ratio: float = Field(0, alias="stopLossRatio")

    model_config = {"populate_by_name": True, "by_alias": True}


class FundCreate(FundBase):
    pass


class FundUpdate(FundBase):
    pass


class FundOut(FundBase):
    id: str
    last_nav_update: str = Field("", alias="lastNavUpdate")


# ==================== 配置 ====================

class ConfigUpdate(BaseModel):
    style: str = "进取型"
    stop_profit_line: float = Field(20, alias="stopProfitLine")
    add_position_line: float = Field(-15, alias="addPositionLine")
    add_position_mode: str = Field("multi", alias="addPositionMode")
    add_tiers: List[AddTier] = Field(default_factory=list, alias="addTiers")
    stop_profit_ratio: float = Field(12, alias="stopProfitRatio")
    trailing_stop: float = Field(8, alias="trailingStop")
    use_trailing_stop: bool = Field(True, alias="useTrailingStop")
    extreme_volatility: float = Field(5, alias="extremeVolatility")
    enable_stop_loss: bool = Field(True, alias="enableStopLoss")
    stop_loss_line: float = Field(-25, alias="stopLossLine")
    stop_loss_ratio: float = Field(50, alias="stopLossRatio")
    free_days: int = Field(7, alias="freeDays")
    max_position: int = Field(40, alias="maxPosition")
    peak_return_rate: dict = Field(default_factory=dict, alias="peakReturnRate")

    model_config = {"populate_by_name": True}


# ==================== 天天基金查询 ====================

class FundQueryResponse(BaseModel):
    """基金代码查询返回"""
    code: str
    name: str
    date: str           # 净值日期
    nav: float          # 最新单位净值
    estimated_nav: Optional[float] = None  # 实时估算净值
    estimated_change: Optional[float] = None  # 估算涨跌幅 (%)
    update_time: Optional[str] = None  # 估值更新时间


class AutoUpdateResult(BaseModel):
    """单只基金自动更新结果（不写入数据库，仅返回计算结果供前端预览）"""
    fund_id: str = Field("", alias="fundId")
    fund_name: str = Field("", alias="fundName")
    fund_code: str = Field("", alias="fundCode")
    success: bool
    old_market_value: float = Field(0, alias="oldMarketValue")
    new_market_value: float = Field(0, alias="newMarketValue")
    today_change: Optional[float] = Field(None, alias="todayChange")
    today_profit: Optional[float] = Field(None, alias="todayProfit")
    calculated_return_rate: Optional[float] = Field(None, alias="calculatedReturnRate")
    message: str = ""


class AutoUpdateResponse(BaseModel):
    """一键更新净值返回"""
    updated_count: int = Field(0, alias="updatedCount")
    failed_count: int = Field(0, alias="failedCount")
    skipped_count: int = Field(0, alias="skippedCount")
    results: List[AutoUpdateResult] = Field(default_factory=list)


# ==================== 操作历史 ====================

class HistoryCreate(BaseModel):
    date: str
    fund_name: str = Field("", alias="fundName")
    type: str  # 买入 | 卖出
    amount: float
    return_rate: float = Field(0, alias="returnRate")
    note: str = ""

    model_config = {"by_alias": True}


class HistoryOut(HistoryCreate):
    id: str
    ai_evaluation: str = Field("", alias="aiEvaluation")


class HistoryEvaluateRequest(BaseModel):
    """AI 评价操作历史的请求"""
    history_id: str = Field("", alias="historyId")


class HistoryEvaluateResponse(BaseModel):
    evaluation: str


# ==================== 聊天 ====================

class ChatMessage(BaseModel):
    role: str  # user | assistant
    content: str


class ChatRequest(BaseModel):
    message: str
    fund_context: Optional[str] = None
    history: List[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str


# ==================== 情绪文案 ====================

class EmotionRequest(BaseModel):
    fund_name: str = Field("", alias="fundName")
    today_change: float = Field(0, alias="todayChange")
    total_return: float = Field(0, alias="totalReturn")
    market_value: float = Field(0, alias="marketValue")


class EmotionResponse(BaseModel):
    title: str
    lines: List[str]


# ==================== AI 解读 ====================

class AdviceInterpretRequest(BaseModel):
    fund_name: str = Field("", alias="fundName")
    fund_data: dict = Field(default_factory=dict, alias="fundData")
    rule_result: dict = Field(default_factory=dict, alias="ruleResult")
    warning: Optional[dict] = None
    config_info: Optional[dict] = Field(None, alias="configInfo")


class AdviceInterpretResponse(BaseModel):
    interpretation: str


# ==================== 快照 ====================

class SnapshotCreate(BaseModel):
    fund_id: str = Field("", alias="fundId")
    safety_cushion: Optional[float] = Field(None, alias="safetyCushion")
    recovery_needed: Optional[float] = Field(None, alias="recoveryNeeded")
    today_change: float = Field(0, alias="todayChange")
    total_return: float = Field(0, alias="totalReturn")

    model_config = {"by_alias": True}


class SnapshotOut(SnapshotCreate):
    date: str


# ==================== 执行操作 ====================

class ExecuteActionRequest(BaseModel):
    fund_id: str = Field("", alias="fundId")
    action_type: str = Field("", alias="actionType")  # 买入 | 卖出
    amount: float
    reason_type: str = Field("", alias="reasonType")
    is_max: bool = Field(False, alias="isMax")
    note: str = Field("", alias="note")  # 手动操作自定义备注


class ExecuteActionResponse(BaseModel):
    ok: bool
    fund: FundOut
    history_id: str = Field("", alias="historyId")


# ==================== AI 推荐加仓档位 ====================

class TierRecommendRequest(BaseModel):
    fund_name: str = Field("", alias="fundName")
    total_buy_amount: float = Field(0, alias="totalBuyAmount")
    initial_principal: float = Field(0, alias="initialPrincipal")
    max_investment: float = Field(0, alias="maxInvestment")
    current_return_rate: float = Field(0, alias="currentReturnRate")
    current_market_value: float = Field(0, alias="currentMarketValue")
    hold_days: int = Field(0, alias="holdDays")

    model_config = {"populate_by_name": True}


class MacroAnalysisResult(BaseModel):
    """宏观政策分析结果"""
    sector: str = ""                    # 所属行业/赛道
    policy_score: int = Field(50, alias="policyScore")       # 政策支持评分 0-100
    key_policies: List[str] = Field(default_factory=list, alias="keyPolicies")  # 关联国家政策
    trend: str = ""                     # 政策趋势判断
    aggressiveness: float = 0           # 策略调整系数 -0.5~+0.5
    analysis: str = ""                  # 简要分析


class TierRecommendResponse(BaseModel):
    tiers: List[AddTier]  # 下跌加仓档位
    strategy_type: str = Field("downside", alias="strategyType")  # 推荐策略类型
    pullback_tiers: List[AddTier] = Field(default_factory=list, alias="pullbackTiers")  # 上涨回调加仓档位
    stop_profit_line: float = Field(0, alias="stopProfitLine")
    stop_loss_line: float = Field(0, alias="stopLossLine")
    stop_profit_ratio: float = Field(0, alias="stopProfitRatio")
    stop_loss_ratio: float = Field(0, alias="stopLossRatio")
    strategy_style: str = Field("", alias="strategyStyle")     # 策略风格标签
    macro_analysis: Optional[MacroAnalysisResult] = Field(None, alias="macroAnalysis")  # 宏观分析结果
    explanation: str = ""


# ==================== AI 整体组合分析 ====================

class OverallAnalysisRequest(BaseModel):
    """AI 整体组合分析请求 - 传入格式化的全部持仓文本"""
    portfolio_text: str = Field("", alias="portfolioText")


class OverallAnalysisResponse(BaseModel):
    """AI 整体组合分析响应"""
    analysis: str


# ==================== 用户认证 ====================

class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    ok: bool
    message: str = ""
    username: str = ""

