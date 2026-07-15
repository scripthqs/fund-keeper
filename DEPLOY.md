# 服务器部署指南

## 服务器目录规划（支持多项目）

```
/opt/
├── fund-keeper/              ← 项目1：理财小助理
│   ├── backend/              ← 后端代码
│   │   ├── app/
│   │   ├── venv/             ← Python虚拟环境（服务器上创建）
│   │   ├── data/             ← SQLite数据库（自动生成）
│   │   ├── .env              ← 环境变量（服务器上创建）
│   │   ├── requirements.txt
│   │   └── run.py
│   └── dist/                 ← 前端构建产物
│       ├── index.html
│       └── assets/
│
├── project-2/                ← 项目2（未来）
│   ├── backend/
│   └── dist/
│
└── project-3/                ← 项目3（未来）
    ├── backend/
    └── dist/

端口分配表（每个项目用不同端口）：
  fund-keeper  → 8000
  project-2    → 8002
  project-3    → 8003
  ...
```

---

## 第一步：本地打包

### 1.1 打包前端

```powershell
cd d:\Work\fund-keeper\frontend
npm run build
```

打包产物在 `d:\Work\fund-keeper\frontend\dist\`

### 1.2 需要上传到服务器的文件

只需要以下两部分：

```
要上传的文件：
├── backend/                  ← 整个后端目录（不含 venv 和 data）
│   ├── app/
│   ├── requirements.txt
│   ├── .env.example
│   └── run.py
└── frontend/dist/            ← 只上传 dist 目录（构建产物）
    ├── index.html
    └── assets/
```

**不需要上传的：**
- `frontend/node_modules/`（体积大，服务器不需要）
- `frontend/src/`（源码，服务器只需要构建产物）
- `backend/data/`（服务器上自动生成）
- `backend/venv/`（服务器上创建）

---

## 第二步：上传文件到服务器

用你的图形化工具（如 WinSCP、Xftp 等），连接到服务器，创建目录并上传：

### 2.1 在服务器上创建项目目录

```bash
sudo mkdir -p /opt/fund-keeper
```

### 2.2 上传文件

把本地的文件复制到服务器的对应位置：

```
本地路径                                    →  服务器路径
─────────────────────────────────────────────────────────────
d:\Work\fund-keeper\backend\              →  /opt/fund-keeper/backend/
d:\Work\fund-keeper\frontend\dist\        →  /opt/fund-keeper/dist/
```

上传后服务器上的结构应该是：

```
/opt/fund-keeper/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── agent.py
│   │   └── routers/
│   ├── requirements.txt
│   ├── .env.example
│   └── run.py
└── dist/
    ├── index.html
    └── assets/
        ├── index-xxx.css
        └── index-xxx.js
```

---

## 第三步：服务器上配置后端

SSH 连接到服务器，执行以下命令：

### 3.1 创建 Python 虚拟环境并安装依赖

```bash
cd /opt/fund-keeper/backend

# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 退出虚拟环境
deactivate
```

### 3.2 创建 .env 配置文件

```bash
cd /opt/fund-keeper/backend
cp .env.example .env
nano .env
```

修改 `.env` 内容：

```ini
# LLM 配置
LLM_API_KEY=sk-你的API密钥
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat

# 服务配置（端口设为 8000，给未来项目留空间）
HOST=127.0.0.1
PORT=8000

# CORS（改成你的域名）
CORS_ORIGINS=https://yourdomain.com
```

保存退出（nano 编辑器：`Ctrl+O` 回车保存，`Ctrl+X` 退出）

### 3.3 修改后端配置，指向前端 dist 目录

```bash
nano /opt/fund-keeper/backend/app/config.py
```

找到 `FRONTEND_DIR` 那几行，改成：

```python
# 前端构建产物目录（与 backend 同级的 dist 目录）
FRONTEND_DIST_DIR = BASE_DIR.parent / "dist"
FRONTEND_DIR = FRONTEND_DIST_DIR
```

保存退出。

### 3.4 测试后端能否正常启动

```bash
cd /opt/fund-keeper/backend
source venv/bin/activate
python run.py
```

看到 `Uvicorn running on http://127.0.0.1:8000` 就说明成功了。
按 `Ctrl+C` 退出，继续下一步。

---

## 第四步：配置 Systemd 服务（后台常驻 + 开机自启）

```bash
sudo nano /etc/systemd/system/fund-keeper.service
```

粘贴以下内容：

```ini
[Unit]
Description=Fund Keeper Backend (FastAPI)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/fund-keeper/backend
ExecStart=/opt/fund-keeper/backend/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

保存退出，然后执行：

```bash
# 重新加载 systemd
sudo systemctl daemon-reload

# 设置开机自启
sudo systemctl enable fund-keeper

# 启动服务
sudo systemctl start fund-keeper

# 查看运行状态
sudo systemctl status fund-keeper
```

看到绿色的 `active (running)` 就说明成功了。

常用管理命令：

```bash
sudo systemctl restart fund-keeper   # 重启
sudo systemctl stop fund-keeper      # 停止
sudo journalctl -u fund-keeper -f    # 查看实时日志
```

---

## 第五步：配置 Nginx 反向代理

```bash
sudo nano /etc/nginx/conf.d/fund-keeper.conf
```

粘贴以下内容（把 `yourdomain.com` 换成你的域名）：

```nginx
server {
    listen 80;
    server_name yourdomain.com;
    # HTTP 跳转 HTTPS
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name yourdomain.com;

    # SSL 证书路径（改成你实际的路径）
    ssl_certificate     /path/to/your/fullchain.pem;
    ssl_certificate_key /path/to/your/privkey.pem;

    # 前端静态文件（Vue 构建产物）
    location / {
        root /opt/fund-keeper/dist;
        try_files $uri $uri/ /index.html;
    }

    # API 请求代理到后端
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

保存退出，测试并重载 Nginx：

```bash
sudo nginx -t              # 测试配置是否正确
sudo systemctl reload nginx  # 重载配置
```

---

## 第六步：验证

浏览器访问 `https://yourdomain.com`，应该能看到理财小助理页面。

---

## 未来部署新项目时的模板

以后部署新项目，重复以下步骤：

### 1. 本地打包
```powershell
cd 项目目录/frontend && npm run build
```

### 2. 上传到服务器
```
/opt/新项目名/backend/   ← 后端代码
/opt/新项目名/dist/      ← 前端构建产物
```

### 3. 服务器配置（换端口和项目名）
```bash
# 创建虚拟环境
cd /opt/新项目名/backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 配置 .env（端口改为 8002）
cp .env.example .env && nano .env

# 创建 systemd 服务
sudo nano /etc/systemd/system/新项目名.service
# ExecStart 里端口改为 8002

sudo systemctl daemon-reload
sudo systemctl enable --now 新项目名

# 创建 Nginx 配置
sudo nano /etc/nginx/conf.d/新项目名.conf
# proxy_pass 端口改为 8002，root 指向 /opt/新项目名/dist
sudo nginx -t && sudo systemctl reload nginx
```

### 端口分配参考

| 项目 | 端口 |
|------|------|
| fund-keeper | 8000 |
| 第二个项目 | 8002 |
| 第三个项目 | 8003 |
| ... | ... |

---

## 常见问题

### Q: 修改了前端代码，怎么更新？
1. 本地重新 `npm run build`
2. 把新的 `dist/` 目录覆盖到服务器 `/opt/fund-keeper/dist/`
3. 不需要重启后端（Nginx 直接读静态文件）

### Q: 修改了后端代码，怎么更新？
1. 把新的 `backend/app/` 目录覆盖到服务器
2. `sudo systemctl restart fund-keeper`

### Q: 数据库在哪？
```
/opt/fund-keeper/backend/data/fund_keeper.db
```
备份时直接复制这个文件即可。

### Q: 查看后端日志
```bash
sudo journalctl -u fund-keeper -f
```
