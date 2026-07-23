"""
Agent 包入口。
重新导出所有公共 API，完全向后兼容原有的 from app.agent import ... 。
"""

from ._common import (
    _safe_parse_json,
    _brute_parse_json,
    _JSON_FIELD_FALLBACK,
    INVESTMENT_ADVISOR_PROMPT,
    EMOTION_SYSTEM_PROMPT,
    INTERPRET_ADVICE_PROMPT,
    MACRO_ANALYSIS_PROMPT,
    MACRO_ANALYSIS_STREAM_PROMPT,
    TIER_RECOMMEND_PROMPT,
    EVALUATE_OPERATION_PROMPT,
    OVERALL_ANALYSIS_PROMPT,
    _build_interpret_user_message,
    _build_recommend_user_message,
)

from .emotion import (
    generate_emotion,
    generate_emotion_stream,
)

from .advisor import (
    chat_with_advisor,
    chat_with_advisor_stream,
    interpret_advice,
    interpret_advice_stream,
)

from .macro import (
    analyze_fund_macro,
    analyze_fund_macro_stream,
)

from .tiers import (
    recommend_add_tiers,
    recommend_add_tiers_stream,
    evaluate_operation,
    evaluate_operation_stream,
    analyze_overall_portfolio,
    analyze_overall_portfolio_stream,
)

__all__ = [
    # JSON 工具
    "_safe_parse_json",
    "_brute_parse_json",
    "_JSON_FIELD_FALLBACK",
    # Prompts
    "INVESTMENT_ADVISOR_PROMPT",
    "EMOTION_SYSTEM_PROMPT",
    "INTERPRET_ADVICE_PROMPT",
    "MACRO_ANALYSIS_PROMPT",
    "MACRO_ANALYSIS_STREAM_PROMPT",
    "TIER_RECOMMEND_PROMPT",
    "EVALUATE_OPERATION_PROMPT",
    "OVERALL_ANALYSIS_PROMPT",
    # Helpers
    "_build_interpret_user_message",
    "_build_recommend_user_message",
    # 情绪
    "generate_emotion",
    "generate_emotion_stream",
    # 顾问
    "chat_with_advisor",
    "chat_with_advisor_stream",
    "interpret_advice",
    "interpret_advice_stream",
    # 宏观
    "analyze_fund_macro",
    "analyze_fund_macro_stream",
    # 策略
    "recommend_add_tiers",
    "recommend_add_tiers_stream",
    "evaluate_operation",
    "evaluate_operation_stream",
    "analyze_overall_portfolio",
    "analyze_overall_portfolio_stream",
]
