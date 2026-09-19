# 首版验证记录

更新日期：2026-09-19。状态：**P0、S1、A1、S2+A2、S3、S4、R1 全部交付通过；真机 17 项设备测试全通过（PLR110 Android 16）；后台 89 项测试在远程 PostgreSQL (152.70.238.24) 上全通过**。


## 2026-09-19 R1 迁移、备份与完整交付验收通过

### 真机设备测试（17 项全部通过）

- **测试环境**：PLR110（Android 16，序列号 `3B666N00GE900000`）
- **命令**：`powershell -ExecutionPolicy Bypass -File .\scripts\build-android.ps1 -UseMirror -NoDaemon -DeviceTests`
- **执行结果**：17/17 passed, 0 failed, 0 skipped.
- **新增 R1 设备测试项（3 项新增，共 17 项）**：
  1. `demoDataNotAutoUploadedAndHasSeparateViewEntry`: 验证演示数据不自动上传到正式账本，Room v1 数据打标 `isDemo=true`，后台存在有效同步数据时优先展示权威账单，本地演示数据保留完整不丢失。
  2. `emptyBackendPreservesLocalDemoBills`: 验证当后端为空或新建库首次同步无账单时，客户端安全回退展示本地演示账单，不清除旧本地记录，不显示错误零欠款。
  3. `syncFailureDoesNotClearExistingSyncedRecords`: 验证网络异常或同步失败时，已缓存的权威同步账单与本地数据完好保留，不发生数据回退或清空。
  4. `migrationFrom1To2PreservesLegacyDataAndEnablesSyncedTables`: Room 数据库由 v1 升级至 v2 后，旧演示账单、还款记录与种子标记完全保留，同时 6 张同步表与元数据表就绪。
  5. `simultaneousFullPaymentsCannotOverpay`: 并发全额还款扣减互斥，严格防止超额还款。
  6. `offlinePaymentThrowsExceptionAndDoesNotMutate`: 离线模式只读铁律，断网时尝试还款立即熔断抛出异常，绝不本地乐观扣减。
  7. `syncedBillsMappingAndReactiveFlow`: 服务端快照/增量同步到本地 Room 后，响应式 Flow 自动映射为权威账单实体。
  8. `committedRecordsSurviveDatabaseReopen`: 数据库关闭后重新打开数据完整保留。
  9. `seedIsIdempotentAndPaymentsCanBeReversed`: 种子幂等性与还款撤销事务恢复。
  10. `defaultFontAt360dp`: 360dp 紧凑布局默认字体无截断溢出。
  11. `largeFontAt360dp`: 360dp 紧凑布局 1.3 倍大字体无截断溢出。
  12. `largestFontAt360dp`: 360dp 紧凑布局 1.5 倍特大字体无截断溢出。
  13. `fullPaymentSettlesAndDisablesAnotherPayment`: 全额还款后状态置为已结清，还款按钮安全置灰禁用。
  14. `invalidAmountsCannotSaveAndCancelDoesNotWrite`: 非法金额校验拦截，取消操作不产生写入。
  15. `activityRecreationKeepsDialogDraftAndHistoryNavigationWorks`: 旋转屏幕/Activity 重建保留还款弹窗输入草稿，历史筛选正常。
  16. `repeatedSaveDuringSameUiFrameWritesOnlyOnce`: 单帧多次连续点击防抖拦截，仅触发一次提交。
  17. `partialPaymentAndVoidRestoreBalanceAndKeepOriginalRecord`: 部分还款与撤销恢复剩余余额，保留完整审计记录。

### 后台远程数据库与备份恢复测试（89 项全部通过）

- **数据库**：远程 PostgreSQL 18.0 (`152.70.238.24:5432/cardcube`)
- **命令**：`python -m pytest backend/tests`
- **执行结果**：89 passed, 0 failed, 3 warnings in 658s（全量远程网络回归通过）
- **R1 交付与独立性验证（`test_r1_delivery.py` 4 项新增）**：
  1. `test_restore_triggers_cursor_out_of_range_and_forces_full_sync`: 模拟数据库备份恢复（序列重置）场景，当客户端游标大于恢复后的服务端最大序号时，服务端精准返回 `CURSOR_OUT_OF_RANGE` (HTTP 409)，促使客户端发起全量 bootstrap 同步重建本地状态。
  2. `test_health_and_capabilities_independent_of_devices`: `/health` 与 `/v1/capabilities` 不依赖任何已配对设备独立工作，明确声明 stage 为 `r1-delivery` 且 `backup_restore: True`。
  3. `test_backend_data_creation_without_active_app_session`: 后台定时收件与解析流水线在无 App 客户端连接时自驱运行，新生成的账户与账单可在后续客户端启动时完整同步。
  4. `test_payment_consistency_across_both_ends`: 移动端在线还款与撤销后，通过后台账单详情 API 查看，剩余金额与已还金额双端保持 100% 严格一致。

### 关键架构与性能优化交付

1. **Bootstrap WAN 延迟性能调优**：
   - 优化前：`get_bootstrap` 对每张账单单独发起 `get_statement_detail` 查询，在面对远程数据库时产生 466 次顺次网络往返，全量同步耗时 >70 秒。
   - 优化后：重构为 3 次批量查询（单次 `IN (version_ids)` 抓取最新版本，单次 `IN (statement_ids)` 聚合有效还款额，纯内存 O(1) 组装），远程 WAN 耗时由 >70s 降至 ~1s。
2. **真机测试防抖与键盘干扰规避**：
   - 在 `CardCueTestRunner` 中注入 `setShowWhenLocked(true)`、`setTurnScreenOn(true)` 及 `KeyguardManager.requestDismissKeyguard`，消除手机锁屏对自动化测试的影响。
   - 在 `PaymentFlowTest` 中针对软键盘弹出遮挡提交按钮问题增加 `closeKeyboard()` 统一收起，增加列表滚动至目标元素后再点击的鲁棒逻辑。
3. **国内 Gradle 与依赖镜像加速**：
   - `gradle-wrapper.properties` 切换至华为云 Gradle 8.9 官方镜像并校验官方 SHA-256 哈希，彻底解决海外 `services.gradle.org` 超时中断问题。
   - `settings.gradle.kts` 配置阿里云与腾讯云 Maven 镜像，加速构建和依赖下载。

---

## 2026-09-18 S4 后台解析与人工确认验收通过

### 后台远程数据库测试（85 项全部通过）

- **数据库**：远程 PostgreSQL 18.0 (152.70.238.24:5432/cardcube)，Alembic 迁移 `0004_s4_draft_tables.py` 应用完成（`statement_drafts`, `draft_evidence` 表）。
- **执行命令**：`python -m pytest backend/tests --tb=short -q`
- **执行结果**：85 passed, 0 failed, 0 skipped（耗时约 31 分钟，受远程数据库延迟影响）。
- **S4 解析与草稿测试（19 项新增）**：
  - `test_parsing.py` (16 项)：
    1. `test_html_plain_text_extraction`: HTML 文本提取基础。
    2. `test_html_table_extraction`: HTML 表格结构化提取。
    3. `test_html_remote_resource_blocked`: 远程资源加载禁止。
    4. `test_html_size_limit_enforced`: 超大 HTML 截断保护。
    5. `test_pdf_text_extraction`: PDF 文本提取。
    6. `test_pdf_page_limit`: PDF 页数限制。
    7. `test_pdf_encrypted_detection`: 加密 PDF 标记 `encrypted_pdf`。
    8. `test_pdf_ocr_required_detection`: 扫描件标记 `ocr_required`。
    9. `test_evidence_creation_and_validation`: Evidence 创建与字段校验。
    10. `test_evidence_source_provenance`: 证据来源追溯。
    11. `test_evidence_conflict_detection`: 多来源冲突检测。
    12. `test_evidence_missing_field_handling`: 缺失字段不填 0 不猜测。
    13. `test_model_adapter_structured_output`: 模型输出结构化校验。
    14. `test_model_adapter_cache_hit`: 输入指纹缓存命中。
    15. `test_model_adapter_retry_limit`: 限次重试防无界费用。
    16. `test_model_adapter_rule_fallback_when_no_key`: 无 API 密钥时规则回退。
  - `test_drafts_api.py` (2 项)：
    17. `test_drafts_end_to_end_flow`: 草稿创建→证据审查→人工确认→正式账单版本生成全流程。
    18. `test_storage_expiration_policy`: 受保护原文/附件过期清理策略。
  - `test_contracts.py` (11 项)：StatementDraft 与 Evidence 合约规则全量回归。
- **全量测试套件覆盖**：
  - `test_api.py` (3 项): 健康检查、特性声明、未启用模型状态。
  - `test_contracts.py` (11 项): 整数货币单位运算、不可变版本与证据链合约。
  - `test_mail_sync.py` (15 项): 邮件加密、分类、解析、存储、只读 IMAP、增量游标与调度器。
  - `test_models.py` (14 项): 远程 PostgreSQL 唯一约束、外键级联、CHECK 约束。
  - `test_parsing.py` (16 项): HTML/PDF 提取、证据链、模型适配器。
  - `test_drafts_api.py` (2 项): 草稿全流程与存储过期。
  - `test_s1_api.py` (17 项): 账户、卡片、账单、版本、还款事务安全、设备配对与撤销。
  - `test_sync_api.py` (6 项): 设备 Token 鉴权、全量快照、增量日志、游标越界、在线还款与撤销。
  - `conftest.py`: 修复 asyncpg 连接池隔离（每个测试函数前后 `engine.dispose()`），解决 `pytest-asyncio 0.26` + `anyio 4.x` 事件循环冲突。

### Android 手机端草稿审核集成（S4-05）

- **功能联动**：
  - `DraftReviewDialog.kt`：展示原文依据、账户选择、人工修改和确认/拒绝。
  - `SyncManager.kt`：集成 `fetchPendingDrafts()`、`confirmDraft()`、`rejectDraft()` 接口。
  - `CardCueViewModel`：新增 `pendingDrafts`、`confirmDraft`、`rejectDraft`、`parseAllPending` 方法。
  - `HomeScreen.kt`：修复 BillCard testTag 使用 `$\{s.id\}` 后缀，解决设备测试定位问题。
- **Android 测试验证**：
  - 单元测试（`testDebugUnitTest`）：全部通过。
  - 代码合规检查（`lintDebug`）：0 错误通过。
  - 真机设备测试（`connectedDebugAndroidTest`）：PLR110（Android 16）14/14 项全部通过，100% 成功率。

### 环境修复

- **Python 虚拟环境重建**：原 `.venv` 丢失，使用 `D:\dev\python311\python.exe` 重建。
- **依赖补全**：`lxml>=5.0` 和 `PyMuPDF>=1.24` 添加到 `pyproject.toml` 的 `dependencies`。
- **版本兼容修复**：降级 `fastapi<0.120`、`httpx<0.28` 以避免 `starlette 1.6` 与 `asyncpg` 的异步冲突。
- **pytest-asyncio 适配**：移除 `test_parsing.py`、`test_mail_sync.py`、`test_drafts_api.py` 中冗余的 `@pytest.mark.asyncio` 装饰器（`asyncio_mode=auto` + `session` 级循环已自动处理）。

---
## 2026-09-18 S3 后台定时收件验收通过

### 后台远程数据库与邮件引擎测试（66 项全部通过）

- **数据库**：远程 PostgreSQL 18.0 (152.70.238.24:5432/cardcube)，Alembic 迁移 `0003_s3_mail_tables.py` 应用完成（`mailboxes`, `mail_cursors`, `mail_jobs`, `email_sources`, `email_attachments` 共 5 张新表）。
- **执行命令**：`python -m pytest backend/tests -v`
- **执行结果**：66 passed, 0 failed, 0 skipped.
- **S3 邮件拉取与调度测试（15 项）**：
  1. `test_token_encryption_and_decryption`: Fernet 对称加密、解密与凭证安全。
  2. `test_token_decryption_invalid_fails`: 损坏的密文解密失败保护。
  3. `test_token_masking`: 凭证掩码与日志/API 零泄漏。
  4. `test_bank_domain_detection`: 国内外 21 家主流银行域名精准识别。
  5. `test_classifier_monthly_statement`: 信用卡电子对账单/月结单分类。
  6. `test_classifier_filters_marketing_and_alerts`: 自动过滤动账通知、还款提醒、营销与验证码。
  7. `test_decode_mime_header`: RFC822 头部解码（UTF-8、GB18030 多编码回退）。
  8. `test_sanitize_filename_prevents_path_traversal`: 附件文件名路径穿越（`../`）防御。
  9. `test_parse_email_bytes_with_attachments`: 邮件 MIME 树解析与正文指纹计算。
  10. `test_storage_save_and_read`: 受保护存储层落盘与回读。
  11. `test_storage_rejects_path_traversal`: 存储目录越界防御。
  12. `test_sync_incremental_and_read_only_invariants`: 只读 IMAP 严格保证（`BODY.PEEK[]`、`readonly=True`、无删除/标记已读操作）、增量游标递增与指纹去重。
  13. `test_uidvalidity_reset_recovers_gracefully`: 服务端 UIDVALIDITY 重置时游标平滑恢复不丢件。
  14. `test_scheduler_detects_due_mailboxes`: 独立调度器自动识别到期邮箱并驱动任务。
  15. `test_mail_api_endpoints`: 邮箱 CRUD、`/v1/mail/sync-now` 手动触发、`/v1/mail/jobs` 任务跟踪、`/v1/mail/sources` 来源列表 REST 接口。
- **全量测试套件覆盖**：
  - `test_api.py` (3 项): 健康检查、特性声明（`email_sync: True`, `version: 0.3.0`）、未启用模型状态。
  - `test_contracts.py` (11 项): 整数货币单位运算、不可变版本与证据链合约。
  - `test_mail_sync.py` (15 项): 邮件加密、分类、解析、存储、只读 IMAP、增量游标与调度器。
  - `test_models.py` (14 项): 远程 PostgreSQL 唯一约束、外键级联、CHECK 约束。
  - `test_s1_api.py` (17 项): 账户、卡片、账单、版本、还款事务安全、设备配对与撤销。
  - `test_sync_api.py` (6 项): 设备 Token 鉴权保护、全量快照、增量日志、游标越界检测、在线还款与撤销、幂等防重。

### Android 手机端协同集成（S3-07）

- **功能联动**：
  - `SyncApiClient` & `SyncManager`：集成 `triggerMailSync()` 与 `getMailJobs()` 接口。
  - `CardCueViewModel`：新增 `checkNewEmails()`，触发后台检查新邮件任务并向 UI 发送状态通知。
  - `CardCueApp`：在同步信息弹窗中增加“检查新邮件”操作入口，与后台自驱调度器使用相同的任务机制。
- **Android 测试验证**：
  - 单元测试（`testDebugUnitTest`）：3 个测试套件全部通过。
  - 代码合规检查（`lintDebug`）：0 错误通过。
  - 真机设备测试（`connectedDebugAndroidTest`）：PLR110（Android 16）14/14 项全部通过，100% 成功率。

---

## 2026-09-18 S2 + A2 数据同步闭环验收通过

### 真机设备测试（14 项全部通过）

- **测试环境**：PLR110（Android 16，序列号 `3B666N00GE900000`）
- **命令**：`powershell -ExecutionPolicy Bypass -File .\scripts\build-android.ps1 -NoDaemon -DeviceTests`
- **执行耗时**：54s，14/14 tests passed, 0 failed, 0 skipped.
- **测试项目**：
  1. `migrationFrom1To2PreservesLegacyDataAndEnablesSyncedTables`: 验证从 Room v1 升级到 v2 时旧数据无损保留，新表支持增删改查。
  2. `simultaneousFullPaymentsCannotOverpay`: 并发全额还款扣减互斥，防止超额还款。
  3. `offlinePaymentThrowsExceptionAndDoesNotMutate`: 验证离线只读铁律，未联网时记录还款直接抛出异常，绝不本地乐观扣减。
  4. `syncedBillsMappingAndReactiveFlow`: 验证服务端快照/增量同步到 Room 后，响应式 Flow 自动映射为权威账单实体（包含多卡尾号合并、银行卡面标识与还款记录）。
  5. `committedRecordsSurviveDatabaseReopen`: 数据库关闭重开后数据持久化。
  6. `seedIsIdempotentAndPaymentsCanBeReversed`: 种子幂等性与本地还款撤销。
  7. `defaultFontAt360dp`: 360dp 紧凑布局默认字体无溢出。
  8. `largeFontAt360dp`: 360dp 紧凑布局 1.3 倍大字体无溢出。
  9. `largestFontAt360dp`: 360dp 紧凑布局 1.5 倍特大字体无溢出。
  10. `fullPaymentSettlesAndDisablesAnotherPayment`: 全额还款后状态变为已结清并禁用还款按钮。
  11. `invalidAmountsCannotSaveAndCancelDoesNotWrite`: 无效金额无法提交，取消操作不写入。
  12. `activityRecreationKeepsDialogDraftAndHistoryNavigationWorks`: 旋转屏幕/Activity 重建保留还款弹窗草稿，历史筛选正常。
  13. `repeatedSaveDuringSameUiFrameWritesOnlyOnce`: 同一 UI 帧重复点击防抖，仅触发一次写入。
  14. `partialPaymentAndVoidRestoreBalanceAndKeepOriginalRecord`: 部分还款与撤销恢复余额，保留审计记录。

### 后台远程数据库与同步 API 测试（51 项全部通过）

- **数据库**：远程 PostgreSQL 18.0 (`152.70.238.24:5432/cardcube`)
- **命令**：`python -m pytest backend/tests`
- **执行结果**：51 passed, 0 failed, 0 skipped
  - `test_api.py` (3 项): 健康检查、特性声明、未启用模型状态。
  - `test_contracts.py` (11 项): 整数货币单位最小面值运算、不可变版本合约。
  - `test_models.py` (14 项): 远程 PostgreSQL 唯一约束、外键级联、CHECK 约束。
  - `test_s1_api.py` (17 项): 账户、卡片、账单、版本、还款事务安全、设备配对与撤销。
  - `test_sync_api.py` (6 项): 设备 Token 鉴权保护、全量快照 (`/v1/sync/bootstrap`)、基于 `commit_seq` 增量日志 (`/v1/sync/changes`)、游标越界检测 (`CURSOR_OUT_OF_RANGE`)、在线还款与撤销命令、`request_id` 幂等防重。

### Android 功能拆分与架构重构 (A1 + A2)

- **模块拆分**：
  - `common/ui`: `Theme.kt`, `SharedComponents.kt`
  - `feature/home`: `HomeScreen.kt`（紧凑布局，单屏显示 3.5 张卡片，展示演示/离线/已连接状态徽标，支持手动下拉同步）
  - `feature/billing`: `DetailScreen.kt`, `PaymentDialog.kt`
  - `feature/history`: `HistoryScreen.kt`
  - `feature/settings`: `SettingsScreen.kt`
  - `sync`: `SyncModels.kt`, `SyncApiClient.kt`, `SyncManager.kt`（自动配对、快照暂存激活、增量合并、离线熔断）
- **数据层升级**：
  - Room v2 数据库包含 6 张服务端同步表与游标元数据表。
  - `BillRepository` 实现自动识别双轨数据：存在服务端同步游标时显示权威同步账单；未连接/首次启动展示演示账单。

---

## 2026-09-17 S1 验收通过

### API 集成测试（17 项全部通过）

- **Health & Capabilities (2 项)**：version 0.2.0、stage s1-storage、accounts/statements/payments/device_auth 已启用、email_sync 未启用。
- **Account CRUD (3 项)**：创建/列表、获取/更新（alias 和 status）、404 not found。
- **Card CRUD (1 项)**：创建卡片关联账户、列出账户下的卡片。
- **Statement & Version (2 项)**：创建账单自动生成版本、读取明细含剩余金额、due_date < statement_date 被拒(409)。
- **Payment 事务安全 (7 项)**：记录还款扣减剩余、超额还款被拒(409)、币种不匹配被拒(409)、幂等 request_id 去重、撤销后恢复剩余并允许重新支付、重复撤销被拒(409)、列出账单还款记录。
- **Device Auth (2 项)**：配对返回一次性 token、列表含设备、撤销后 status=revoked 且 revoked_at 有值。

### 远程数据库约束测试（14 项全部通过）

- **AccountCard (3 项)**：创建账户、卡片关联、无效外键被拒。
- **StatementVersion (7 项)**：创建账单与版本、金额整数回读验证、同账户同币种同账期唯一约束、due_date < statement_date 被拒、负金额被拒、最低还款超总额被拒、版本号唯一约束。
- **Payment (4 项)**：记录还款、撤销还款保留审计、零金额被拒、多币种独立记录。

---

## 2026-09-16 初始记录

- 演示版源码编写，Android 初始架构与 Room v1 数据库。
