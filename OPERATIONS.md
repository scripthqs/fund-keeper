# 日常运维速查表

## 一、更新前端代码

前端改了代码后，需要本地重新打包再上传：

```powershell
# 本电脑上操作
cd d:\Work\fund-keeper\frontend
npm run build
```

然后用图形化工具，把 `d:\Work\fund-keeper\frontend\dist\` 里的文件覆盖到服务器的 `/opt/fund-keeper/dist/`

**不需要重启任何服务**，刷新浏览器即可看到更新。

---

## 二、更新后端代码

后端改了代码后，用图形化工具把 `d:\Work\fund-keeper\backend\app\` 覆盖到服务器的 `/opt/fund-keeper/backend/app/`

然后 SSH 执行：

```bash
sudo systemctl restart fund-keeper
```

---

## 三、数据库管理

### 数据库文件位置
```
/opt/fund-keeper/backend/data/fund_keeper.db
```

### 备份数据库
```bash
cp /opt/fund-keeper/backend/data/fund_keeper.db /opt/fund-keeper/backend/data/fund_keeper_backup_$(date +%Y%m%d).db
```

### 查看数据库内容
```bash
sqlite3 /opt/fund-keeper/backend/data/fund_keeper.db
```
进入后可以执行 SQL：
```sql
.tables                                    -- 查看所有表
SELECT * FROM funds;                       -- 查看所有基金
SELECT * FROM history ORDER BY date DESC;  -- 查看操作历史
SELECT * FROM chat_messages;               -- 查看聊天记录
SELECT * FROM config;                      -- 查看配置
.quit                                      -- 退出
```

### 清空所有数据（重置）
```bash
sqlite3 /opt/fund-keeper/backend/data/fund_keeper.db
DELETE FROM funds;
DELETE FROM history;
DELETE FROM chat_messages;
DELETE FROM snapshots;
.quit
```

---

## 四、服务管理命令

```bash
sudo systemctl status fund-keeper     # 查看运行状态
sudo systemctl restart fund-keeper    # 重启后端
sudo systemctl stop fund-keeper       # 停止后端
sudo systemctl start fund-keeper      # 启动后端
sudo journalctl -u fund-keeper -f     # 查看实时日志（排错用）
```

---

## 五、Nginx 管理

```bash
sudo systemctl reload nginx           # 修改配置后重载
sudo systemctl restart nginx          # 重启 Nginx
sudo nginx -t                         # 测试配置是否正确
```

---

## 六、部署新项目（模板）

以后部署新项目，步骤一样：

1. **上传文件**到 `/opt/新项目名/`
2. **安装依赖**：`cd /opt/新项目名/backend && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
3. **配置 .env**：端口换成 8002、8003...
4. **创建 service 文件**：`nano /etc/systemd/system/新项目名.service`（端口对应改）
5. **启动服务**：`sudo systemctl daemon-reload && sudo systemctl enable --now 新项目名`
6. **创建 Nginx 配置**：`nano /etc/nginx/conf.d/新项目名.conf`（端口对应改）
7. **重载 Nginx**：`sudo nginx -t && sudo systemctl reload nginx`
