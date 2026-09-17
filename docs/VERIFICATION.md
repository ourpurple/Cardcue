# 首版验证记录

更新日期：2026-09-17。状态：**P0 设备测试全部通过；S1 后台业务层、API、设备鉴权 45 项测试全部通过**。

## 2026-09-17 验证结果

### P0 验收通过

- 单元测试：`testDebugUnitTest` 通过（BillingTest 20 项 + HomeRulesTest 13 项）。
- Lint：`lintDebug` 通过，0 错误，1 项 kapt 性能建议（已有）。
- 构建：`assembleDebug` + `assembleDebugAndroidTest` 成功。
- 设备测试：`connectedDebugAndroidTest` 在 PLR110 / Android 16 真机上执行 **11 项测试，连续两次全部通过**，0 失败、0 跳过。
  - RepositoryTest（3 项）：种子/撤销、并发全额还款、数据库重开持久化。
  - PaymentFlowTest（5 项）：部分还款/撤销、全额还款、无效输入/取消、同帧重复保存、Activity 重建后历史导航。
  - CompactLayoutTest（3 项）：360dp 宽度下 fontScale 1.0/1.3/1.5 的文本不溢出、header 高度 <200dp、首张账单高度 <150dp、按钮触摸目标 ≥48dp、多卡滚动、金额/日期/尾号无裁切、USD 还款对话框输入/保存/取消。
- 测试数据隔离：TestCardCueApplication + 独立 UUID 命名测试数据库。测试 APK 卸载后不影响正式 App。日常数据库不被测试修改（手机上此前未安装 App，首次安装为全新种子数据）。
- Debug APK 已安装到真机，首页布局截图保存在 `android/app/build/compact-layout/home.png`（已加入 .gitignore）。

### 布局修复内容

- `home-total-CNY`、`home-cards-*`、`home-due-*` 的 Text 加入 `fillMaxWidth()` 和 `maxLines = 1`，消除 Compose paragraph width > measured size 的误报溢出。
- 还款按钮 `home-pay-*` 加入 `defaultMinSize(minHeight = 48.dp)`，满足 Material 48dp 最小触摸目标。
- 测试运行器 `CardCueTestRunner` 加入 `FLAG_KEEP_SCREEN_ON`，避免测试期间手机锁屏导致截图失败。

### 首页紧凑布局对比

- 旧版 header 占据大量空间（slogan、大间距、"同步邮箱"按钮独占一行），首屏只能显示 1 张账单卡片。
- 当前版本 header 紧凑（标题行合并"演示版"和"同步邮箱"，减少垂直间距，尾号与账期同行），首屏可显示约 3.5 张卡片。

### 环境

- JDK: Microsoft OpenJDK 17.0.20.1 (`C:\Users\Duolly\Documents\Codex\2026-09-16\wo\work\toolchain\jdk\jdk-17.0.20.1+1`)
- SDK: Platform 35, Build Tools 34+35 (`C:\Users\Duolly\Documents\Codex\2026-09-16\wo\work\toolchain\sdk`)
- Gradle: 8.9（华为镜像缓存，官方 checksum 验证）
- 设备：PLR110 / Android 16，序列号 3B666N00GE900000
- 使用 `--no-daemon` 避免沙箱网络限制。

### 尚待验收

- 真实进程重启验证（force-stop 后重新启动，核对数据一致）。
- 屏幕旋转、键盘遮挡的交互验证。
- API 26 兼容性验证（需模拟器或旧设备）。
- 后台新架构（S1 及以后）尚未实现。


## 2026-09-17 S1-04/05/06/07 验收通过

### API 集成测试（17 项全部通过）

- **Health & Capabilities (2 项)**：version 0.2.0、stage s1-storage、accounts/statements/payments/device_auth 已启用、email_sync 未启用。
- **Account CRUD (3 项)**：创建/列表、获取/更新（alias 和 status）、404 not found。
- **Card CRUD (1 项)**：创建卡片关联账户、列出账户下的卡片。
- **Statement & Version (2 项)**：创建账单自动生成版本、读取明细含剩余金额、due_date < statement_date 被拒(409)。
- **Payment 事务安全 (7 项)**：记录还款扣减剩余、超额还款被拒(409)、币种不匹配被拒(409)、幂等 request_id 去重、撤销后恢复剩余并允许重新支付、重复撤销被拒(409)、列出账单还款记录。
- **Device Auth (2 项)**：配对返回一次性 token、列表含设备、撤销后 status=revoked 且 revoked_at 有值。

### 修复的问题

- **asyncpg event loop 冲突**：pytest-asyncio 默认 `function` scope loop 导致连接池跨 loop 复用失败。设置 `asyncio_default_test_loop_scope = "session"` 使所有异步测试共享同一 loop。
- **MissingGreenlet 序列化错误**：Service 层 `flush()` 后 Pydantic 序列化 ORM 对象时触发惰性加载。在所有 `flush()` 后添加 `session.refresh(obj)` 确保服务端生成的列（server_default、onupdate）已加载。

### 全量测试

- `python -m pytest -v`：**45 passed**, 0 failed, 0 skipped。
  - test_api.py: 3 项（health、capabilities、no-parser）
  - test_contracts.py: 11 项（合约验证）
  - test_models.py: 14 项（PostgreSQL 约束）
  - test_s1_api.py: 17 项（API 集成）

### 新增/修改文件

- `backend/cardcue_api/api/billing.py` — 账户/卡片/账单/还款路由
- `backend/cardcue_api/api/devices.py` — 设备配对/撤销路由
- `backend/cardcue_api/domain/schemas.py` — Pydantic DTO
- `backend/cardcue_api/services/billing.py` — BillingService (SELECT FOR UPDATE、幂等、撤销)
- `backend/cardcue_api/services/auth.py` — DeviceService (SHA-256 token hash)
- `backend/cardcue_api/persistence/device.py` — Device 模型
- `backend/cardcue_api/persistence/changelog.py` — ChangeLog 模型
- `backend/cardcue_api/migrations/versions/0002_...py` — 设备与变更日志迁移
- `backend/tests/conftest.py` — session scope engine dispose
- `backend/tests/test_s1_api.py` — 17 项 API 集成测试

## 历史记录

### 2026-09-16

当日状态：源码已编写，Android 构建与安装验收尚未完成。后台 `python -m pytest -q` 14 项通过。


## 2026-09-17 S1-01/02/03 验收通过

### 数据库连接与迁移

- PostgreSQL 18.0 (aarch64-unknown-linux-gnu) 远程连接成功。
- Alembic 迁移 `0001` 执行成功，创建 accounts、cards、statements、statement_versions、payments 共 5 张表。
- 所有金额字段使用 `BigInteger`，整数最小货币单位存储，不使用浮点数。

### 模型约束测试（14 项全部通过）

- **AccountCard (3 项)**：创建账户、卡片关联、无效外键被拒。
- **StatementVersion (7 项)**：创建账单与版本、金额整数回读验证、同账户同币种同账期唯一约束、due_date < statement_date 被拒、负金额被拒、最低还款超总额被拒、版本号唯一约束。
- **Payment (4 项)**：记录还款、撤销还款保留审计、零金额被拒、多币种独立记录。

### 全量测试

- `python -m pytest -q`：28 passed, 0 failed, 0 skipped (14 API/contract + 14 model)。

### 新增文件

- `backend/cardcue_api/config.py` — Pydantic Settings
- `backend/cardcue_api/persistence/models.py` — 5 个 SQLAlchemy 模型
- `backend/cardcue_api/persistence/database.py` — 异步/同步引擎
- `backend/cardcue_api/migrations/` — Alembic 配置与初始迁移
- `backend/tests/test_models.py` — 14 项约束测试
- `backend/.env.example` — 连接串模板
- `backend/pyproject.toml` — 新增数据库相关依赖
