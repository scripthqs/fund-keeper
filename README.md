# 📊 Fund-Keeper（理财小助理）

基金投资决策辅助工具。基于自定义投资规则，自动分析每日基金数据并给出买卖操作建议。

## 技术栈

| 层 | 技术 |
|---|------|
| 前端 | Vue 3 + Vite + Vant 4 |
| 后端 | Python FastAPI + Uvicorn |
| 数据库 | SQLite |
| AI | LLM（兼容 DeepSeek / OpenAI） |
| 计算 | Big.js 高精度运算 |

## 项目结构

```
fund-keeper/
├── frontend/              # Vue 3 前端
│   └── src/
│       ├── components/    # 页面组件
│       ├── composables/   # 全局 Store
│       ├── utils/         # 决策引擎、BigMath 等
│       └── api/           # Axios 请求封装
├── backend/               # FastAPI 后端
│   ├── run.py             # 启动入口
│   └── app/
│       ├── routers/       # API 路由
│       ├── agent.py       # AI Agent
│       └── database.py    # 数据库
└── UPDATE_GUIDE.md        # 部署更新指南
```

## 快速开始

### 后端

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
cp .env.example .env         # 编辑 .env 填入 LLM_API_KEY 等
python run.py                # 默认 http://localhost:8000
```

### 前端

```bash
cd frontend
npm install
npm run dev                  # 开发模式 http://localhost:5173
npm run build                # 构建到 dist/
```

## 主要功能

- **基金持仓管理**：添加 / 编辑基金信息（名称、本金、买入日期、市值等）
- **每日数据录入**：输入今日涨跌幅或收益，自动计算总收益率
- **投资规则配置**：止盈线、加仓线、止损线，支持 4 种预设风格一键切换
- **操作建议分析**：基于规则引擎生成买卖建议（止盈 / 止损 / 加仓 / 持有）
- **移动止盈**：从最高收益率回撤超阈值自动提示卖出
- **金字塔加仓**：多档位越跌越买策略
- **安全垫 / 压力测试**：评估当前持仓抗风险能力
- **AI 投资顾问**：LLM 对话式投资分析 + 情绪文案
- **操作历史**：买卖记录，支持 CSV 导出
- **深色 / 浅色主题**

## 规则引擎逻辑

按优先级依次判断：

1. 极端波动（±8%）→ 不操作
2. 止损保护 → 卖出止损
3. 移动止盈 → 回撤卖出
4. 固定止盈 → 达标卖出
5. 金字塔加仓 → 越跌越买（4 档）
6. 单档加仓 → 跌到加仓线
7. 接近加仓区域 → 等待提示
8. 安全区间 → 持有不动
