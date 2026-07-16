# 更新指南

## 服务器信息

| | 地址 | 角色 |
|---|---|---|
| 国内服务器 | 1.14.152.133 | 中转跳板 |
| 海外服务器 | 23.95.169.175 | 实际运行 |

> 国内服务器通过图形化工具（WinSCP / Xftp）连接，海外服务器通过国内服务器 SSH 连接。

---

## 只更新前端

适用于：改了页面样式、功能逻辑，没动后端代码。

```powershell
# ========== 在你电脑上 ==========
cd d:\Work\fund-keeper\frontend
npm run build
```

然后用图形化工具把本地 `dist\` 文件夹拖到国内服务器的 `/opt/fund-keeper/dist/`（覆盖）。

在国内服务器 SSH 终端执行：

```bash
scp -r /opt/fund-keeper/dist/* root@23.95.169.175:/opt/fund-keeper/dist/
```

**不需要重启任何服务**，刷新浏览器即可。

---

## 只更新后端

适用于：改了 `backend/app/` 下的 Python 代码。

用图形化工具把本地 `backend\app\` 文件夹拖到国内服务器的 `/opt/fund-keeper/backend/app/`（覆盖）。

在国内服务器 SSH 终端执行：

```bash
scp -r /opt/fund-keeper/backend/app/* root@23.95.169.175:/opt/fund-keeper/backend/app/
ssh root@23.95.169.175 "sudo systemctl restart fund-keeper"
```

---

## 同时更新前后端

适用于：前后端都改了。

```powershell
# ========== 在你电脑上 ==========
cd d:\Work\fund-keeper\frontend
npm run build
```

用图形化工具上传：
- 本地 `dist\` → 国内 `/opt/fund-keeper/dist/`（覆盖）
- 本地 `backend\app\` → 国内 `/opt/fund-keeper/backend/app/`（覆盖）

在国内服务器 SSH 终端执行：

```bash
scp -r /opt/fund-keeper/dist/* root@23.95.169.175:/opt/fund-keeper/dist/
scp -r /opt/fund-keeper/backend/app/* root@23.95.169.175:/opt/fund-keeper/backend/app/
ssh root@23.95.169.175 "sudo systemctl restart fund-keeper"
```

---

## 查看后端日志（排查错误用）

```bash
ssh root@23.95.169.175 "sudo journalctl -u fund-keeper -f"
```

按 `Ctrl+C` 退出。

---

## DeepSeek 识图配置

如果你要使用 AI 识图功能，请确认 `backend/.env` 里使用的是 DeepSeek 官方 v4 配置：

```bash
LLM_API_KEY=你的DeepSeekKey
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-pro
LLM_VISION_MODEL=deepseek-v4-pro
```

如果这些值还保留着旧的 `/v1` 或旧模型名，识图请求可能会被后端判定为不可用。

---

## 常用命令速查

```bash
# 查看后端状态
ssh root@23.95.169.175 "sudo systemctl status fund-keeper"

# 重启后端
ssh root@23.95.169.175 "sudo systemctl restart fund-keeper"

# 重载 Nginx（改过 Nginx 配置才需要）
ssh root@23.95.169.175 "sudo nginx -t && sudo systemctl reload nginx"

# 修改 API Key 等配置
ssh root@23.95.169.175
nano /opt/fund-keeper/backend/.env
# 改完重启：sudo systemctl restart fund-keeper
```
