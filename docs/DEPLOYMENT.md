# CardCue VPS 部署与真实功能联调测试指南

本文档指导如何在 VPS 上部署 CardCue 后端服务，并使用 Android 手机进行全功能真实联调测试。

---

## 一、前期准备：代码同步

在开发电脑上，当前本地 `main` 分支包含 S1 至 R1 的全部完整功能（后台 FastAPI、Alembic 迁移、自驱 IMAP 调度器、规则与模型解析、草稿证据链、Android 启动同步与草稿审核）。

**在 VPS 拉取代码前，必须先在开发电脑上将最新提交推送到 GitHub：**

```bash
# 在开发电脑 (D:\code\Cardcue) 终端运行：
git push origin main
```

---

## 二、VPS 环境准备与拉取代码

登录到你的 VPS（例如 `152.70.238.24`）：

```bash
# 1. 创建工作目录并克隆代码
mkdir -p /opt/cardcue && cd /opt/cardcue
git clone https://github.com/ourpurple/Cardcue.git .

# 2. 配置环境变量
cp backend/.env.production.example backend/.env

# 3. 检查 backend/.env 中的数据库配置
# 如果 PostgreSQL 与后台运行在同一 VPS，请确认用户名、密码、端口无误
nano backend/.env
```

`backend/.env` 示例内容：
```env
DATABASE_URL=postgresql+asyncpg://cardcube:TPAdhfnyLmLptJxx@152.70.238.24:5432/cardcube
DATABASE_SYNC_URL=postgresql+psycopg2://cardcube:TPAdhfnyLmLptJxx@152.70.238.24:5432/cardcube
MAIL_ENCRYPTION_KEY=cardcue-secret-key-32-bytes-long!
MAIL_STORAGE_DIR=/app/data/mail_storage
MAIL_CHECK_INTERVAL_MINUTES=30
```

---

## 三、部署方式一：Docker Compose（推荐）

该方式将 FastAPI Web 服务与后台自驱邮件调度器作为独立容器运行，自动执行 Alembic 数据库迁移与健康检查。

### 1. 启动服务

```bash
# 在项目根目录执行
docker compose build
docker compose up -d
```

### 2. 检查运行状态与日志

```bash
# 查看容器状态
docker compose ps

# 查看 Web 服务日志
docker compose logs -f cardcue-api

# 查看后台邮件调度器日志
docker compose logs -f cardcue-scheduler
```

---

## 四、部署方式二：原生 Python 3.11 + Systemd

如果 VPS 未安装 Docker，可使用系统原生 Python 环境托管。

### 1. 安装依赖并执行迁移

```bash
cd /opt/cardcue/backend
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e .

# 执行数据库表迁移至最新版 (0004_s4_draft_tables)
.venv/bin/alembic upgrade head
```

### 2. 配置 Systemd 开机自启服务

```bash
# 复制服务配置文件
sudo cp deploy/cardcue-api.service /etc/systemd/system/
sudo cp deploy/cardcue-scheduler.service /etc/systemd/system/

# 重载并启动服务
sudo systemctl daemon-reload
sudo systemctl enable --now cardcue-api cardcue-scheduler

# 查看服务状态
sudo systemctl status cardcue-api
sudo systemctl status cardcue-scheduler
```

---

## 五、防火墙与网络端口放行

Android 手机需通过 HTTP 访问 VPS 上的 `8000` 端口。请确保 VPS 防火墙及云服务商安全组已开放 `8000` 端口：

```bash
# Ubuntu / Debian ufw
sudo ufw allow 8000/tcp

# 或 CentOS / RHEL firewalld
sudo firewall-cmd --zone=public --add-port=8000/tcp --permanent
sudo firewall-cmd --reload
```

---

## 六、全流程实机功能测试步骤

### 步骤 1：服务连通性与能力检测

在任意能访问 VPS 的终端（或手机浏览器）执行：

```bash
# 1. 检查健康状态
curl -s http://152.70.238.24:8000/health
# 预期返回: {"status":"ok","service":"cardcue","version":"0.5.0"}

# 2. 检查系统能力声明
curl -s http://152.70.238.24:8000/v1/capabilities
# 预期返回各模块 stage: "r1-delivery", sync: true, email_sync: true 等
```

### 步骤 2：初始化信用卡账户与卡片

为了让后续从邮件解析出的账单能正确匹配到银行账户，先初始化基础银行账户与卡片信息。

可在 VPS 或本地执行预置的初始化脚本：

```bash
python3 scripts/init-demo-data.py --server http://152.70.238.24:8000
```

或使用 `curl` 自行创建：
```bash
# 创建招商银行账户
curl -X POST http://152.70.238.24:8000/v1/accounts \
  -H "Content-Type: application/json" \
  -d '{"bank": "招商银行", "alias": "招行信用卡", "reference": "CMB_01"}'

# 创建卡片 (替换 <account_id>)
curl -X POST http://152.70.238.24:8000/v1/accounts/<account_id>/cards \
  -H "Content-Type: application/json" \
  -d '{"card_tail": "9759", "card_holder": "本人", "color_hex": "#C25259", "card_type": "credit"}'
```

### 步骤 3：Android 手机连接与初次同步

1. 确保手机安装了最新的 `app-debug.apk`（安装包位于 `android/app/build/outputs/apk/debug/app-debug.apk`）。
2. 打开手机上的 CardCue App：
   - App 启动时会自动连接 `http://152.70.238.24:8000` 并完成设备自动配对 (`/v1/devices/pair`)。
   - 自动获取全量快照 (`/v1/sync/bootstrap`)，将步骤 2 创建的账户和卡片拉取并缓存到本地 Room 数据库。
3. 点击首页右上角或顶部的“同步”状态，可查看服务连接状态、设备配对 ID 及上次同步时间。

### 步骤 4：配置真实邮箱并测试邮件收取与解析

#### 4.1 录入邮箱配置 (IMAP)
通过 API 录入你的账单邮箱（以 163 邮箱为例，需使用邮箱开启 IMAP 后生成的授权密码）：

```bash
curl -X POST http://152.70.238.24:8000/v1/mailboxes \
  -H "Content-Type: application/json" \
  -d '{
    "email_address": "your_bill_email@163.com",
    "imap_host": "imap.163.com",
    "imap_port": 993,
    "use_ssl": true,
    "auth_token": "YOUR_IMAP_AUTH_CODE",
    "auth_type": "password",
    "check_interval_minutes": 30
  }'
```

#### 4.2 验证邮箱连通性
```bash
# 替换为创建返回的 mailbox_id
curl -X POST http://152.70.238.24:8000/v1/mailboxes/<mailbox_id>/test-connection
# 预期返回: {"success": true, "message": "Connection and credentials verified"}
```

#### 4.3 触发收取邮件与解析
你可以通过两种方式触发：
- **方式 A（手机端）**：点击手机同步弹窗内的 **“收取邮件”** 按钮，后台将立即拉取邮件；随后点击 **“解析邮件”**，后台将对收到的账单邮件进行 HTML/PDF 文本提取并生成草稿。
- **方式 B（终端触发）**：
  ```bash
  # 立即收取
  curl -X POST http://152.70.238.24:8000/v1/mail/sync-now
  # 触发待处理邮件解析为草稿
  curl -X POST http://152.70.238.24:8000/v1/drafts/parse-all-pending
  ```

### 步骤 5：手机端审核草稿并确认入账

1. 回到手机 CardCue 首页，当存在待审核草稿时，首页顶部会出现 **“待处理账单草稿 (N)”** 卡片。
2. 点击草稿进入审核弹窗：
   - 弹窗展示提取出的银行、应还金额、最低还款额、账单日、到期日。
   - 点击 **“查看提取依据与原文摘录”**，核对后台提取的原文凭据与置信度。
   - 下拉选择归属的信用卡账户（若银行名称匹配，会自动默认选中）。
3. 检查无误后，点击 **“确认入账”**：
   - 手机端向后台提交确认，生成正式账单版本。
   - 账单立即出现在正式账单列表中，进入还款倒计时追踪！

### 步骤 6：在线还款与撤销闭环测试

1. 在手机账单列表中点击已入账的账单，进入账单详情页。
2. 点击 **“记一笔还款”**，输入还款金额（例如 500 元）和备注（例如“手机银行转账”）。
3. 提交后：
   - 手机将还款请求发送至后台 `/v1/payments`。
   - 后台校验剩余欠款并记录事务，生成变更日志。
   - 手机端待还金额实时扣减，剩余欠款准确更新。
4. 点击该笔还款记录并选择 **“撤销还款”**：
   - 后台记录撤销状态，剩余欠款立即恢复。

### 步骤 7：后台自驱定时检查验证

1. 在手机上直接退出或强行停止 CardCue App。
2. 观察 VPS 上的 `cardcue-scheduler` 日志（`docker compose logs -f cardcue-scheduler` 或 `systemctl status cardcue-scheduler`）。
3. 调度器按照配置的轮询周期（默认 30 分钟）独立自驱唤醒，自动检索新邮件；当用户重新打开手机 App 时，会自动增量同步最新生成的草稿和账单。
