"""Pydantic 数据模型 - 请求与响应定义"""

from typing import List, Optional

from pydantic import BaseModel, Field


# ==================== 基金 ====================

class FundBase(BaseModel):
    name: str
    initial_principal: float = Field(0, alias="initialPrincipal")
    buy_date: str = Field("", alias="buyDate")
    total_buy_amount: float = Field(0, alias="totalBuyAmount")
    total_sell_amount: float = Field(0, alias="totalSellAmount")
    current_market_value: float = Field(0, alias="currentMarketValue")
    current_return_rate: float = Field(0, alias="currentReturnRate")

    model_config = {"populate_by_name": True, "serialization_by_alias": True}


class FundCreate(FundBase):
    pass


class FundUpdate(FundBase):
    pass


class FundOut(FundBase):
    id: str


# ==================== 配置 ====================

class AddTier(BaseModel):
    line: float
    ratio: float


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


# ==================== 操作历史 ====================

class HistoryCreate(BaseModel):
    date: str
    fund_name: str = Field("", alias="fundName")
    type: str  # 买入 | 卖出
    amount: float
    return_rate: float = Field(0, alias="returnRate")
    note: str = ""

    model_config = {"serialization_by_alias": True}


class HistoryOut(HistoryCreate):
    id: str


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


# ==================== 快照 ====================

class SnapshotCreate(BaseModel):
    fund_id: str = Field("", alias="fundId")
    safety_cushion: Optional[float] = Field(None, alias="safetyCushion")
    recovery_needed: Optional[float] = Field(None, alias="recoveryNeeded")
    today_change: float = Field(0, alias="todayChange")
    total_return: float = Field(0, alias="totalReturn")

    model_config = {"serialization_by_alias": True}


class SnapshotOut(SnapshotCreate):
    date: str


# ==================== 每日数据智能解析 ====================

class DailyParseRequest(BaseModel):
    message: str
    funds: List[dict] = Field(default_factory=list)


class DailyParseResult(BaseModel):
    fundId: str = ""
    fundName: str = ""
    todayChange: float = 0
    totalReturn: float = 0


class DailyParseResponse(BaseModel):
    results: List[DailyParseResult] = Field(default_factory=list)
    message: str = ""


# ==================== 执行操作 ====================

class ExecuteActionRequest(BaseModel):
    fund_id: str = Field("", alias="fundId")
    action_type: str = Field("", alias="actionType")  # 买入 | 卖出
    amount: float
    reason_type: str = Field("", alias="reasonType")
    is_max: bool = Field(False, alias="isMax")
    note: str = Field("", alias="note")  # 手动操作自定义备注
