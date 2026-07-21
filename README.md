# Fund-Keeper（理财小助理）

基金投资决策辅助工具。基于自定义投资规则，自动分析每日基金数据并给出买卖操作建议。

## 技术栈

| 层   | 技术                                      |
| ---- | ----------------------------------------- |
| 前端 | Vue 3 + Vite 5 + Vant 4 + Big.js         |
| 后端 | Python FastAPI + Uvicorn + SQLite         |
| AI   | LLM（兼容 DeepSeek / OpenAI），对话式投顾 |
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
│   │   ├── composables/            # 全局状态管理（Store）
│   │   └── utils/                  # 决策引擎、BigMath 等工具
│   ├── index.html
│   ├── vite.config.js              # Vite 配置（含 API 代理）
│   └── package.json
├── backend/                        # FastAPI 后端
│   ├── app/
│   │   ├── main.py                 # FastAPI 应用入口
│   │   ├── config.py               # 环境变量配置
│   │   ├── database.py             # SQLite 数据库初始化
│   │   ├── agent.py                # AI Agent（LLM 对话）
│   │   ├── fund_api.py             # 天天基金 API 对接
│   │   ├── models.py               # Pydantic 数据模型
│   │   └── routers/                # API 路由
│   │       ├── funds.py            # 基金 CRUD + 快照
│   │       ├── config.py           # 投资规则配置
│   │       ├── history.py          # 操作历史记录
│   │       ├── chat.py             # AI 对话接口
│   │       ├── snapshots.py        # 每日快照
│   │       └── calendar.py         # 交易日历
│   ├── data/                       # SQLite 数据库文件目录
│   ├── requirements.txt
│   └── run.py                      # 启动脚本
├── UPDATE_GUIDE.md                 # 部署更新指南
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

| 变量          | 说明                      | 默认值                          |
| ------------- | ------------------------- | ------------------------------- |
| `LLM_API_KEY` | AI 模型 API Key（必填）   | —                               |
| `LLM_BASE_URL`| LLM API 地址              | `https://api.deepseek.com`      |
| `LLM_MODEL`   | 模型名称                  | `deepseek-v4-pro`              |
| `HOST`        | 服务监听地址              | `0.0.0.0`                       |
| `PORT`        | 服务端口                  | `8000`                          |
| `CORS_ORIGINS`| 跨域允许的域名（逗号分隔）| `*`                             |

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

> 开发模式下，前端 `vite.config.js` 已配置 API 代理，`/api` 请求自动转发到后端。如需修改后端地址，编辑 `vite.config.js` 中的 `proxy.target`。

### 3. 访问

- **开发模式**：浏览器打开 `http://localhost:5173`（Vite dev server 自动代理 API）
- **生产模式**：后端启动后直接访问 `http://localhost:8000`（后端内置静态文件服务，自动托管前端 dist）

## 主要功能

- **基金持仓管理**：添加 / 编辑基金信息（名称、基金代码、份额、本金、买入日期、市值等），支持通过天天基金 API 自动获取最新净值
- **每日数据录入**：输入每日涨跌幅或盈亏金额，自动计算收益率
- **投资规则配置**：止盈线、加仓线、止损线、移动止盈等参数，支持 4 种预设风格（保守型 / 稳健型 / 激进型 / 自定义）一键切换
- **操作建议分析**：基于规则引擎生成买卖建议（止盈 / 止损 / 加仓 / 持有）
- **移动止盈**：从历史最高收益率回撤超过阈值时自动提示卖出
- **金字塔加仓**：多档位越跌越买策略（最多 4 档），根据跌幅逐步加大买入比例
- **安全垫 / 压力测试**：评估当前持仓的抗风险能力和回血难度
- **AI 投资顾问**：LLM 对话式投资分析，提供市场情绪解读和个性化建议
- **操作历史**：完整买卖记录，支持 CSV 导出
- **交易日历**：自动识别中国节假日，仅交易日可操作
- **深色 / 浅色主题**：支持切换

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

## API 路由一览

| 方法   | 路径                        | 说明             |
| ------ | --------------------------- | ---------------- |
| GET    | `/api/health`               | 健康检查         |
| GET    | `/api/funds`                | 获取基金列表     |
| POST   | `/api/funds`                | 添加基金         |
| PUT    | `/api/funds/{id}`           | 更新基金         |
| DELETE | `/api/funds/{id}`           | 删除基金         |
| POST   | `/api/funds/{id}/snapshots` | 获取基金快照     |
| POST   | `/api/funds/describe`       | 根据代码查询基金 |
| GET    | `/api/config`               | 获取投资规则配置 |
| PUT    | `/api/config`               | 更新投资规则配置 |
| GET    | `/api/history`              | 获取操作历史     |
| POST   | `/api/history`              | 添加操作记录     |
| DELETE | `/api/history/{id}`         | 删除操作记录     |
| GET    | `/api/history/export`       | 导出 CSV         |
| GET    | `/api/chat`                 | 获取聊天记录     |
| POST   | `/api/chat`                 | 发送 AI 对话     |
| DELETE | `/api/chat`                 | 清空聊天记录     |
| POST   | `/api/snapshots`            | 批量获取快照     |
| GET    | `/api/calendar`             | 获取交易日历     |
