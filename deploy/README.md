# CardCue VPS Docker 生产环境部署与运维手册

本文档指导如何在 VPS 服务器上使用 Docker Compose 部署 CardCue Web 管理端与后端服务，并配合宿主机现有的 Nginx/Caddy 反向代理接入 HTTPS，实现公网安全访问。

---

## 1. 架构与服务拓扑

```text
[ 客户端浏览器 / Android 手机 ]
            │ HTTPS (443)
            ▼
[ VPS 宿主机已有的 Nginx (终结 SSL) ] 
            │ 反向代理 (http://127.0.0.1:3000)
            ▼
┌── Docker 容器集群 (bridge: cardcue-net) ──────────────────────────────────┐
│                                                                          │
│  [ cardcue_web ] (Nginx, 宿主机端口 127.0.0.1:3000)                       │
│    ├─ 托管 React SPA 静态资源                                             │
│    └─ 容器内网反代 /v1/ 到 http://api:8000/v1/                            │
│                                                                          │
│  [ cardcue_api ] (FastAPI, 容器内网 8000)                                 │
│    ├─ 容器启动时自动执行 alembic upgrade head 数据库平滑升级               │
│    └─ 提供管理端业务 API、CSRF/会话鉴权、Android 增量同步接口             │
│                                                                          │
│  [ cardcue_worker ]                                                      │
│    └─ 消费后台任务队列 (执行 IMAP 只读收件、大模型账单智能提取)            │
│                                                                          │
│  [ cardcue_scheduler ]                                                   │
│    └─ 定时巡检已启用的邮箱配置，自动向队列派发收件任务                     │
│                                                                          │
│  [ cardcue_db ] (PostgreSQL 16 Alpine)                                   │
│    └─ 权威持久化存储 (挂载 Docker Volume: postgres_data)                 │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 部署前置要求

1. **VPS 环境**：Linux (Ubuntu 22.04/24.04, Debian 11/12 等)，已安装 **Docker** 与 **Docker Compose**（Docker 24.0+，Compose v2+）。
2. **域名与证书**：已解析到 VPS 的域名（如 `cardcue.yourdomain.com`），且已配置好 HTTPS 证书（如 Let's Encrypt Certbot）。
3. **反向代理**：VPS 宿主机上已运行反向代理（如 Nginx、Caddy 或 Traefik）。

---

## 3. 一键部署步骤

### 步骤一：克隆代码库并进入 deploy 目录
```bash
git clone https://github.com/your-username/Cardcue.git /opt/cardcue
cd /opt/cardcue/deploy
```

### 步骤二：配置环境变量
复制环境配置模板并编辑：
```bash
cp env.example .env
nano .env  # 或使用 vim
```

**必须重点修改的几个关键变量**：
1. `POSTGRES_PASSWORD`：设置一个高强度随机密码。同时将 `DATABASE_URL` 与 `DATABASE_SYNC_URL` 中的密码替换为此值。
2. `PUBLIC_ORIGIN`：填写您的公网完整 HTTPS 访问入口（**末尾切勿带斜杠**），例如：
   ```bash
   PUBLIC_ORIGIN=https://cardcue.yourdomain.com
   ```
3. `MAIL_ENCRYPTION_KEY`：生成至少 40 字符的密钥，用于 AES-256-GCM 加密数据库中的邮箱授权码和模型 API Key：
   ```bash
   # 生成命令示例:
   openssl rand -base64 36
   ```
   将生成的字符串填入 `MAIL_ENCRYPTION_KEY`。
4. `ENVIRONMENT=production`：保持为 production 状态，开启企业级 Cookie 安全标头与严格校验。

### 步骤三：配置 VPS 宿主机 Nginx
参考 `deploy/nginx.conf.example`，在宿主机 Nginx 配置反向代理：
```bash
# 复制样例配置文件到 Nginx 配置目录
sudo cp nginx.conf.example /etc/nginx/conf.d/cardcue.conf

# 编辑配置文件，将其中的 cardcue.yourdomain.com 替换为您真实的域名与 SSL 证书路径
sudo nano /etc/nginx/conf.d/cardcue.conf

# 测试配置无误后重载 Nginx
sudo nginx -t
sudo nginx -s reload
```

### 步骤四：启动 Docker 容器集群
在 `/opt/cardcue/deploy` 目录下执行：
```bash
docker compose up -d --build
```

查看所有容器是否正常运行：
```bash
docker compose ps
```
您应该看到 5 个容器状态均为 `Up`：
- `cardcue_db` (healthy)
- `cardcue_api` (Up)
- `cardcue_worker` (Up)
- `cardcue_scheduler` (Up)
- `cardcue_web` (Up, 127.0.0.1:3000->80/tcp)

### 步骤五：创建初始管理员账号
为了杜绝默认弱口令安全风险，系统不设置默认密码，请在 API 容器中通过 CLI 交互式创建首个管理员：
```bash
docker compose exec api python -m cardcue_api.admin.cli create-admin --username admin
```
- 终端会提示输入密码（**必须不少于 14 个字符**）。
- 输入完成并确认后，数据库将使用 `scrypt` 算法哈希存储。

---

## 4. 首次登录与配置指引

1. **登录系统**：
   - 打开浏览器，访问 `https://cardcue.yourdomain.com`。
   - 输入您创建的管理员账号与密码，进入总览仪表盘。

2. **配置邮箱与授权码 (W3)**：
   - 点击侧边栏 **“邮箱配置”**。
   - 新增邮箱配置，如使用新浪邮箱可点击快捷预设自动填充服务器参数（`imap.sina.com:993`，启用 SSL）。
   - 输入您的邮箱地址与授权码（授权码提交后即在数据库被高强加密存储，页面展示脱敏掩码）。
   - 点击 **“只读测试”**：后台将安全连接邮箱并列举收件箱，**不修改任何已读状态**。
   - 测试成功后，点击 **“启用同步”**，调度器将开始周期性安全收件。

3. **配置大模型服务 (W4)**：
   - 点击侧边栏 **“模型配置”**。
   - 填写兼容 OpenAI 协议的模型 Base URL（如 DeepSeek、OpenAI、OneAPI 等）与 API Key。
   - 设置 Temperature（推荐 0）、Max Tokens 与每日调用限额。
   - 点击 **“连通测试”**：后台使用虚拟合成账单文本验证模型返回与结构解析能力，**不泄露任何真实账单**。
   - 测试通过后点击 **“设为默认模型”**。

4. **草稿审核与入账 (W4)**：
   - 邮件拉取并经大模型提取后，会在 **“草稿审核”** 中生成待审草稿。
   - 在比对页面核验提取出的金额与邮件原文依据片段，指定归属的账户与卡片后点击 **“确认入账”**，生成权威正式账单。

5. **账单与还款管理 (W2)**：
   - 在 **“正式账单”** 中查看分币种应还金额与结清状态。
   - 支持部分还款或全额结清记账（页面明确提示仅用于个人记账，不会发起银行转账）。

6. **Android 手机配对 (W5)**：
   - 点击侧边栏 **“设备管理”** -> **“生成设备配对码”**。
   - 系统将生成一个 10 分钟有效的短效一次性高熵配对码。
   - 在手机 App 中输入此配对码完成相互握手互信，即可实现离线与在线双向安全同步。

---

## 5. 日常运维与常用命令

### 查看日志
```bash
# 查看所有服务实时日志
docker compose logs -f

# 查看 API 鉴权与业务访问日志
docker compose logs -f api

# 查看 Worker 收信与模型提取日志
docker compose logs -f worker

# 查看 Scheduler 定时任务调度日志
docker compose logs -f scheduler
```

### 重置管理员密码
若忘记管理员密码，可随时在 VPS 宿主机执行：
```bash
docker compose exec api python -m cardcue_api.admin.cli reset-password --username admin
```

### 数据库备份与恢复
权威账本数据至关重要，建议每日配置定时冷备份：
```bash
# 备份数据库到宿主机 sql 文件
docker compose exec -t db pg_dump -U cardcue cardcue | gzip > /opt/backups/cardcue_$(date +%Y%m%d).sql.gz

# 灾难恢复导入
gunzip -c /opt/backups/cardcue_20260920.sql.gz | docker compose exec -T db psql -U cardcue -d cardcue
```

### 更新版本升级
```bash
cd /opt/cardcue
git pull
cd deploy
docker compose build
docker compose up -d
# API 容器启动时会自动应用新的 Alembic 增量迁移，无缝平滑升级
```
