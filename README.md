# Fund-Keeper（理财小助理）

基金投资决策辅助工具。管理基金持仓、自动获取实时净值、AI 智能推荐加仓方案、每日操作建议分析与整体组合诊断。

## 技术栈

| 层   | 技术                                      |
| ---- | ----------------------------------------- |
| 前端 | Vue 3 + Vite 5 + Vant 4 + Big.js         |
| 后端 | Python FastAPI + Uvicorn + SQLite         |
| AI   | LLM（兼容 DeepSeek / OpenAI），支持流式输出 |
| 计算 | Big.js 高精度运算，避免浮点数精度问题     |

## 环境要求

| 依赖   | 版本       |
| ------ | ---------- |
| Node   | >= 20      |
| Python | >= 3.9     |

## 项目结构

```
fund-keeper/
├── frontend/                       # Vue 3 前端
│   ├── src/
│   │   ├── api/                    # Axios 请求封装
│   │   ├── components/             # 页面组件
│   │   │   ├── tabs/               # 底部 Tab 子页
│   │   │   ├── AuthPage.vue        # 登录/注册
│   │   │   ├── DailyAnalysis.vue   # 每日分析（核心页面）
│   │   │   ├── AIChat.vue          # AI 投资顾问对话
│   │   │   ├── PositionOverview.vue# 持仓总览
│   │   │   ├── OperationHistory.vue# 操作历史记录
│   │   │   ├── ConfigPanel.vue     # 投资规则配置
│   │   │   ├── FundModal.vue       # 基金编辑弹窗
│   │   │   ├── ManualTrade.vue     # 手动买卖操作
│   │   │   ├── AdviceResult.vue    # 操作建议展示
│   │   │   ├── HealthScore.vue     # 账户健康评分
│   │   │   ├── StrategyOverviewPanel.vue # 策略总览面板
│   │   │   └── AccountManagement.vue# 账号管理（admin）
│   │   ├── composables/            # 全局状态 + Store
│   │   └── utils/                  # 决策引擎、BigMath 等工具
│   ├── index.html
│   ├── vite.config.js              # Vite 配置（含 API 代理）
│   └── package.json
├── backend/                        # FastAPI 后端
│   ├── app/
│   │   ├── main.py                 # FastAPI 应用入口
│   │   ├── config.py               # 环境变量配置
│   │   ├── database.py             # SQLite 数据库初始化
│   │   ├── agent.py                # AI Agent（7 大 LLM 功能）
│   │   ├── fund_api.py             # 基金数据 API 对接（东方财富 + 新浪）
│   │   ├── models.py               # Pydantic 数据模型
│   │   └── routers/                # API 路由
│   │       ├── funds.py            # 基金 CRUD + 一键更新净值 + AI 推荐
│   │       ├── config.py           # 投资规则配置 + 移动止盈峰值
│   │       ├── history.py          # 操作历史 + AI 操作评价
│   │       ├── chat.py             # AI 对话 + 情绪文案 + 建议解读
│   │       ├── snapshots.py        # 每日快照
│   │       ├── calendar.py         # 交易日历
│   │       ├── auth.py             # 注册 / 登录 / 修改密码
│   │       └── admin.py            # 账号管理（admin）
│   ├── data/                       # SQLite 数据库文件目录
│   ├── requirements.txt
│   └── run.py                      # 启动脚本
├── deploy.ps1                      # 一键部署脚本（前端构建 → 上传 → 重启服务）
├── UPDATE_GUIDE.md                 # 服务器部署更新指南
└── README.md
```

## 快速开始

### 1. 后端

```bash
cd backend

# 创建虚拟环境（仅首次）
python -m venv venv

# 激活虚拟环境
venv\Scripts\activate              # Windows
# source venv/bin/activate          # macOS / Linux

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入 LLM_API_KEY 等必要配置

# 启动后端（默认 http://localhost:8000）
python run.py
```

`.env` 配置项说明：

| 变量                | 说明                          | 默认值                          |
| ------------------- | ----------------------------- | ------------------------------- |
| `LLM_API_KEY`       | AI 模型 API Key（必填）       | —                               |
| `LLM_BASE_URL`      | LLM API 地址                  | `https://api.deepseek.com`      |
| `LLM_MODEL`         | 模型名称                      | `deepseek-v4-pro`               |
| `LLM_FAST_MODEL`    | 快速模型（策略推荐/宏观分析等场景，AI 对话仍用 LLM_MODEL） | 空（与 LLM_MODEL 相同） |
| `UNIVERSAL_PASSWORD`| 通用密码（可登录任意账号）    | 空（不启用）                    |
| `HOST`              | 服务监听地址                  | `0.0.0.0`                       |
| `PORT`              | 服务端口                      | `8000`                          |
| `CORS_ORIGINS`      | 跨域允许的域名（逗号分隔）    | `*`                             |

### 2. 前端

```bash
cd frontend

# 安装依赖（仅首次）
npm install

# 启动开发服务器（默认 http://localhost:5173）
npm run dev

# 生产构建
npm run build
```

> 开发模式下，前端 `vite.config.js` 已配置 API 代理，`/api` 请求自动转发到后端。

### 3. 访问

- **开发模式**：浏览器打开 `http://localhost:5173`（Vite dev server 自动代理 API）
- **生产模式**：后端启动后直接访问 `http://localhost:8000`（后端内置静态文件服务，自动托管前端 dist）

## 一键部署

在项目根目录打开 PowerShell，运行：

```powershell
# 同时部署前后端（最常用）
.\deploy.ps1

# 只部署前端
.\deploy.ps1 -Target frontend

# 只部署后端（并自动重启服务）
.\deploy.ps1 -Target backend

# 只更新 Python 依赖
.\deploy.ps1 -Target deps
```

详细部署说明见 [UPDATE_GUIDE.md](./UPDATE_GUIDE.md)。

## 主要功能

### 基金持仓管理
- 添加 / 编辑 / 删除基金（名称、代码、份额、本金、买入日期、市值等）
- **一键更新净值**：从东方财富 + 新浪财经自动获取所有基金最新净值与涨跌幅
  - 盘中使用新浪实时估值净值计算市值，实时反映涨跌；晚间净值结算后自动切回已结算净值
  - 预览模式：确认后写库，可撤销
- 单只基金手动获取实时涨跌幅

### 规则引擎与操作建议
- **投资规则配置**：止盈线、止损线、加仓线、移动止盈阈值等，支持 4 种预设风格（保守 / 稳健 / 激进 / 自定义）
- **规则引擎**：8 级优先级决策（极端波动保护 → 止损 → 移动止盈 → 固定止盈 → 金字塔加仓 → 单档加仓 → 接近加仓提示 → 安全持有）
- **操作建议 + AI 解读**：自动判定操作类型和金额，AI 用自然语言解释判断逻辑
- **安全垫 / 压力测试**：评估当前持仓抗风险能力和回本难度
- **股票价格预警**：基于持仓股票价格触发风险提示

### AI 智能投顾
- **对话式分析**：支持多轮对话的基金持仓分析（流式 + 非流式）
- **AI 推荐加仓档位**：结合预算约束 + 宏观政策 + 持仓数据，自动生成 4 档金字塔加仓方案 + 止盈止损线（流式两阶段：宏观分析 → 策略生成）
- **AI 整体组合分析**：对所有持仓进行系统性诊断，逐个基金给出状态判断和操作建议（流式 + 非流式）
- **情绪文案**：毒舌 / 幽默的投资段子，根据持仓数据生成
- **操作评价**：每次买卖操作后 AI 自动点评，数据保存到历史记录

### 数据记录与账号
- **操作历史**：完整买卖记录，支持筛选、撤回
- **每日快照**：自动 / 手动保存基金每日净值数据
- **交易日历**：自动识别中国节假日，仅交易日可操作，实时倒计时距 15:00 收盘时间
- **账号系统**：注册 / 登录 / 修改密码 / admin 账号管理
- **通用密码**：配置后一个密码可登录任意账号

### 用户体验
- 深色 / 浅色主题切换
- 打字机动画展示 AI 流式回复
- 账户健康评分仪表盘

## 规则引擎逻辑

决策引擎按优先级从高到低依次判断，命中即停止：

| 优先级 | 规则           | 条件                     | 操作       |
| ------ | -------------- | ------------------------ | ---------- |
| 1      | 极端波动保护   | 单日涨跌 ≥ ±8%           | 不操作     |
| 2      | 止损保护       | 总收益率 ≤ 止损线        | 卖出止损   |
| 3      | 移动止盈       | 从最高点回撤 ≥ 移动止盈线| 回撤卖出   |
| 4      | 固定止盈       | 总收益率 ≥ 止盈线        | 达标卖出   |
| 5      | 金字塔加仓     | 当前跌幅达到多档加仓线   | 越跌越买   |
| 6      | 单档加仓       | 当前跌幅达到加仓线       | 加仓       |
| 7      | 接近加仓区域   | 距加仓线 ≤ 2%            | 等待提示   |
| 8      | 安全区间       | 未触发以上任何规则       | 持有不动   |

## 基金数据来源

| 数据               | 来源                       | 说明                           |
| ------------------ | -------------------------- | ------------------------------ |
| 基金名称           | 东方财富 `pingzhongdata`   | HTTP 接口                      |
| 最新已结算净值     | 东方财富 `f10/lsjz`        | 晚间约 20:00 更新，取第一条     |
| 盘中实时估值净值   | 新浪财经 `getEstimateNetworthPic` | 交易时段每分钟更新，支付宝同款数据源 |
| 实时估值涨跌幅     | 同上 `networth` 分时列表   | 盘中实时，取最新一条            |

## AI 功能清单

| 功能            | 模式      | 路由                       |
| --------------- | --------- | -------------------------- |
| 投资顾问对话     | 非流式/流式 | `/api/chat` / `/api/chat/stream` |
| 情绪文案生成     | 非流式/流式 | `/api/emotion` / `/api/emotion/stream` |
| 操作建议解读     | 非流式/流式 | `/api/advice/interpret` / `/api/advice/interpret/stream` |
| 宏观政策分析     | 嵌入推荐流程 | 档位推荐内并发调用          |
| 智能档位推荐     | 非流式/流式 | `/api/funds/ai-recommend-tiers` / stream |
| 整体组合分析     | 非流式/流式 | `/api/funds/overall-analysis` / stream |
| 操作评价         | 非流式/流式 | `/api/history/evaluate/{id}` / stream |

## API 路由一览

### 基金 (`/api/funds`)

| 方法   | 路径                              | 说明                       |
| ------ | --------------------------------- | -------------------------- |
| GET    | `/api/funds`                      | 获取基金列表               |
| POST   | `/api/funds`                      | 添加基金                   |
| PUT    | `/api/funds/{id}`                 | 编辑基金                   |
| DELETE | `/api/funds/{id}`                 | 删除基金                   |
| GET    | `/api/funds/query-fund`           | 查询单只基金实时数据       |
| POST   | `/api/funds/auto-update`          | 一键更新全部基金净值       |
| POST   | `/api/funds/action`               | 执行买卖操作               |
| POST   | `/api/funds/undo/{history_id}`    | 撤回操作                   |
| POST   | `/api/funds/ai-recommend-tiers`   | AI 推荐加仓档位            |
| POST   | `/api/funds/ai-recommend-tiers/stream` | AI 推荐加仓（流式 SSE）|
| POST   | `/api/funds/overall-analysis`     | AI 整体组合分析            |
| POST   | `/api/funds/overall-analysis/stream` | AI 整体组合分析（流式） |
| GET    | `/api/funds/network-check`        | 外部 API 网络连通诊断      |

### AI 对话 (`/api`)

| 方法   | 路径                              | 说明                       |
| ------ | --------------------------------- | -------------------------- |
| POST   | `/api/chat`                       | AI 投资顾问对话            |
| POST   | `/api/chat/stream`                | AI 投资顾问对话（流式 SSE）|
| POST   | `/api/emotion`                    | 生成情绪文案               |
| POST   | `/api/emotion/stream`             | 生成情绪文案（流式 SSE）   |
| POST   | `/api/advice/interpret`           | AI 解读操作建议            |
| POST   | `/api/advice/interpret/stream`    | AI 解读操作建议（流式）    |
| GET    | `/api/chat/messages`              | 获取聊天记录               |
| DELETE | `/api/chat/messages`              | 清空聊天记录               |

### 操作历史 (`/api/history`)

| 方法   | 路径                              | 说明                       |
| ------ | --------------------------------- | -------------------------- |
| GET    | `/api/history`                    | 获取操作历史               |
| POST   | `/api/history`                    | 添加操作记录               |
| DELETE | `/api/history`                    | 清空操作历史               |
| POST   | `/api/history/evaluate/{id}`      | AI 评价某次操作            |
| POST   | `/api/history/evaluate/stream/{id}`| AI 评价某次操作（流式）    |

### 配置 (`/api/config`)

| 方法 | 路径                              | 说明                       |
| ---- | --------------------------------- | -------------------------- |
| GET  | `/api/config`                     | 获取投资规则配置           |
| PUT  | `/api/config`                     | 更新投资规则配置           |
| PUT  | `/api/config/peak-return`         | 更新峰值收益率（移动止盈） |

### 快照 (`/api/snapshots`)

| 方法 | 路径                        | 说明                       |
| ---- | --------------------------- | -------------------------- |
| GET  | `/api/snapshots/{fund_id}`  | 获取基金历史快照           |
| POST | `/api/snapshots`            | 保存每日快照               |

### 交易日历 (`/api/calendar`)

| 方法 | 路径                              | 说明                       |
| ---- | --------------------------------- | -------------------------- |
| GET  | `/api/calendar/trading-status`    | 查询今日交易状态           |

### 账号 (`/api/auth`)

| 方法 | 路径                              | 说明                       |
| ---- | --------------------------------- | -------------------------- |
| POST | `/api/auth/register`              | 注册                       |
| POST | `/api/auth/login`                 | 登录                       |
| POST | `/api/auth/change-password`       | 修改密码                   |

### 管理 (`/api/admin`)

| 方法   | 路径                              | 说明                       |
| ------ | --------------------------------- | -------------------------- |
| GET    | `/api/admin/accounts`             | 查看所有账号               |
| POST   | `/api/admin/accounts`             | 添加账号                   |
| DELETE | `/api/admin/accounts/{user_id}`   | 删除账号及关联数据         |

### 系统

| 方法 | 路径              | 说明                       |
| ---- | ----------------- | -------------------------- |
| GET  | `/api/health`     | 健康检查（含 LLM 状态）    |
