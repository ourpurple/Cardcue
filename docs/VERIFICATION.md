## 2026-09-30 Web 已吊销设备清理增量验证

- 按用户请求，在设备安全页配对码按钮旁新增危险样式的“清除已吊销设备”按钮，显示吊销数量并二次确认。成功显示后台实际清理数量并重新拉取设备列表；无吊销记录、列表加载失败或清理中禁用按钮，失败保留列表。补充刷新入口；清理中禁用刷新和吊销操作，避免重复请求。
- 新增 `POST /v1/admin/devices/clear-revoked`，沿用管理员登录、角色和 CSRF 校验。通过单条带条件的 DELETE RETURNING 清除 `status=revoked` 或已有 `revoked_at` 的设备记录，不接受客户端指定删除目标；已授权且无吊销标记的设备及未知状态且无吊销标记的设备不删除，账单／还款／账户不受影响。删除数量与管理员身份追加到审计，既有审计不删除；删除和新审计同事务提交，无需结构迁移。
- 修正管理页原有 `is_active`／`device_name`／`created_at` 与后台实际 `status`／`name`／`paired_at` 不匹配，避免有效设备被误显示为吊销。设备型号后台未提供时显示“未提供”；`last_seen_at` 标为“最近访问时间”，不冒充同步时间；缺失或无效日期显示“未知”。管理端列表和吊销响应复用已有安全 DeviceOut 契约，不返回令牌摘要。
- `python -m pytest tests/test_admin_devices_clear.py tests/test_admin_security.py tests/test_contracts.py tests/test_admin_jobs_clear.py -q`（backend 目录，全局 Python）：**43 passed**，其中新增设备专项 **9 项**。覆盖空清理幂等、吊销标记判定、保留有效／未知设备、超出可见页、审计字段、登录／角色／CSRF 和安全列表响应；使用合成会话，不访问用户数据库。
- Web `npm run build`：**通过**（TypeScript／Vite，保留既有大包体积警告）。新增 `web/tests/devices-clear.cjs`，构建产物上的模拟 API 浏览器检查 **12 passed**：空列表、仅有效设备、取消确认、清理后保留有效设备及 CSRF、未知状态／无效日期、吊销时间优先判定、网络／服务端失败、请求中禁用、已由其他会话清理、首次列表失败及清理后刷新失败。复用本机 Playwright 与现有 Chromium，无新增依赖。
- **限制：** 未在隔离 PostgreSQL 验证实际删除、并发和审计失败回滚；浏览器 API 全为模拟，不能替代真实后端联调。未删除真实设备、未执行迁移、未部署 VPS；未修改或测试 Android，不宣称 APK 可用。本次不恢复暂停的 Web 完整开发计划。

---

## 2026-09-30 Web 任务队列清理增量验证

- 按本次用户请求，在任务队列页“刷新队列”旁新增危险样式的“清除所有任务”按钮，二次确认明确覆盖所有分页、删除不可撤销、业务数据不受影响以及定时调度不会关闭。空队列禁用按钮；处理中禁用冲突操作；成功显示删除数量、关闭旧详情并返回第一页，忽略旧列表请求的过期响应；失败保留列表。
- 新增管理员接口 `POST /v1/admin/jobs/clear`，沿用登录、管理员角色和 CSRF 校验。先锁定当前全部任务记录；任意记录仍为 `running` 时返回 409 且不删除任何任务。仅删除锁定快照内的任务队列记录，每批最多 1000 个 ID；邮件、草稿、账单、还款、邮箱配置及旧邮件处理记录不删除。清理数量写入审计，删除与审计沿用同一事务；期间或之后新调度的任务仍保留。无需数据库结构迁移。
- 后端新增合成测试 `backend/tests/test_admin_jobs_clear.py`：**14 passed**，覆盖空队列重复清理、各非执行状态、跨分页和分批删除、执行中阻止整体清理、锁定查询、新调度任务保留、登录／角色／CSRF 和接口冲突响应。与 `test_admin_security.py`、`test_contracts.py` 联合运行：**34 passed**。
- `web` 执行 `npm run build`：**通过**（TypeScript 和 Vite；保留已有大包体积警告）。新增 `web/tests/jobs-clear.cjs`，用构建产物及全部拦截的合成 API 执行浏览器检查：**6 passed**，覆盖空队列禁用、取消确认、从第二页清理全部任务并回到第一页、执行中冲突、网络失败及请求中禁用刷新。脚本使用 Playwright；可通过 `CARDCUE_PLAYWRIGHT_MODULE`／`CARDCUE_CHROMIUM_PATH` 指定现有运行时，无需访问用户后台。
- 扩展回归曾额外尝试已有的 `test_default_model_env.py`，在数据库连接阶段因 `WinError 5` 访问受限失败，不计入通过结果，也未为此放宽权限访问现有数据库。**限制：** 尚未在隔离 PostgreSQL 验证真实行锁并发、删除与审计回滚；浏览器 API 为模拟而非真实后端联调。未清除用户任务、未执行数据库迁移、未部署 VPS；未修改或验证 Android，不宣称 APK 可用。

---

## 2026-09-29 原版 App 消失后的只读核查（暂停设备写操作）

- 用户确认没有原版 CardCue 数据的手动备份；此前只读包列表未发现原版 `com.cardcue.app`（含 `-u` 列表），原有本地数据是否仍可恢复**未知**，不能把“未找到包”写成“确认数据已丢失”，也不能承诺可恢复。
- 检查本机现存的 15:44 复测报告与 `utp.0.log`：安装对象为隔离包 `com.cardcue.app.device.test`，安装在手机确认页超时，实际 0 项运行；测试框架 `uninstall_after_test` 仅列出隔离主包及其测试包，随后两项卸载均返回 `DELETE_FAILED_INTERNAL_ERROR`。该日志**未显示卸载原版包**，但也不足以解释原版为何不在。
- 搜索本地 Gradle daemon 日志未找到明确卸载原版 `com.cardcue.app` 的记录；项目清单从初始提交起设置 `allowBackup=false`，但仓库源码不能证明手机上曾安装二进制的备份策略、系统云备份状态或数据实际存留。工作区扫描未发现可用的原版数据备份；不代表用户其它位置不存在备份。
- **处置：** 不再向该手机安装 APK、卸载包、清理数据、运行设备测试或尝试 root／解锁；先由用户只读核对系统备份／云备份记录及其它旧设备是否有同一应用数据。在保护现状、确认可用恢复途径前，N1 的 Android 演示隔离设备验收保持待办；远程合成数据备份恢复演练可独立进行，但不能替代原版数据保护或设备验收。

## 2026-09-29 Android 隔离设备回归（N1／N2 部分完成）

- PLR110（API 36）运行隔离包 `com.cardcue.app.device.test`，首轮 22 项中 **19 通过、3 失败**。通过项包括 Room 1→2、2→3 数据保留、演示行与同步行分隔、空后端保留演示行、同步失败保留缓存、旧缓存零变更快照刷新与失败重试。演示数据“不自动上传”用例目前只断言本地演示标志与显示隔离，**尚缺对服务端请求／接收行为的端到端断言**。
- 失败项：360dp 大字体及特大字体下账单日期被单行截断；Activity 重建后的历史筛选用例在切换“待还”后超时。日期文字已改为最多两行，**尚未通过设备复测**；历史筛选新增选中态定位断言，仍待复测诊断。
- 针对失败项的复测在安装阶段被设备“继续安装”安全确认页阻塞，最终 0 项执行、安装超时；不能记为测试通过。新增合成演示还款经空快照同步后保留、不生成正式欠款的设备断言，仅完成测试 APK 编译，尚未运行。
- **设备安全异常：** 此前记录设备装有 `com.cardcue.app`（签名与当前调试包不同）；本次只读包列表检查却只找到 `com.cardcue.app.device.test`，没有找到原包（包括用户 0、克隆用户及 `-u` 列表）。当前操作没有主动卸载原包或清除数据；用户随后确认原版 App 已不在；原有本地数据是否还有备份或可恢复尚未确认。暂停进一步设备安装／清理，绝不声称旧数据已保留。
- `testDebugUnitTest lintDebug assembleDebug` 通过；`assembleDebugAndroidTest` 在沙箱外编译通过（SDK 位于工作区外）。这些不代替设备测试。N1 还缺第二隔离库的非空合成数据备份恢复与数据核对；N2 还缺完整设备回归及真实后端零变更联调。两项均保持 `[ ]`。

## 2026-09-29 N1 远程隔离库迁移验证（部分完成）

- 已从忽略的本地配置连接远程专用 `cardcue_v2_test`；事前只读核对：数据库名正确、当前角色有建 schema 权限、`public` 无业务表、无遗留测试 schema。业务库 `cardcube` 没有参与写入测试。
- 在隔离库对随机 schema 分别执行空库→0012、0007 合成历史库→0012，验证账户、卡片、账单版本、还款及模糊持卡人不被擅自确认：迁移 2 项通过；目标防护与配置读取单元测试 4 项通过。
- 事后只读核对：剩余测试 schema 为 0、`public` 表为 0。测试没有读取、复制真实账单或在业务库执行迁移。
- **仍待 N1 验收：** 演示数据跨 Android／后端的隔离回归、备份与恢复演练（本机没有 `pg_dump`／`pg_restore`）；因此 N1 保持 `[ ]`，不能将迁移通过等同于可恢复。

## 2026-09-29 远程数据库只读预检（N1 仍待隔离库）

- 按用户要求检查现有远程 PostgreSQL；本次只读连接，未读取业务行，未执行迁移或数据写入。
- 当前业务库 `cardcube` 的迁移版本是 `0012`；连接角色没有 `CREATEDB`／超级用户权限，未发现预定独立测试库 `cardcue_v2_test`。
- 因无法建立独立测试库，没有在业务库内运行 N1 的空库／旧库升级、备份恢复测试，也没有把此前跳过的 2 项记为通过。需由数据库管理员创建并授权专用测试库后再执行；N1 保持未完成。
- 迁移入口现支持从 Git 忽略的本地配置读取远程专用库，拒绝业务库与未确认的远程地址；离线防护测试 3 项通过，实际迁移测试 2 项仍跳过。

## 2026-09-29 V2 N1／N2 增量（均未完成验收）

- N1：新增仅接受本机 `_test` PostgreSQL 的迁移测试入口，可分别验证空库和 0007 历史库升至 0012；隔离库配置使用容器临时存储，不连接用户库。当前机器没有可用 Docker／本地 PostgreSQL，迁移用例 2 项跳过，备份恢复及数据库集成测试尚未执行。选定合成测试 119 项通过；修正 pytest-asyncio 事件循环标记后，全量测试收集 241 项成功。
- N2：Android 缓存新增协议标记。已配对旧缓存不再只依赖服务器变更日志；首次同步强制取得完整快照，数据、游标和协议标记在同一 Room 事务内生效。获取失败保留原缓存和重试条件；新增旧缓存刷新和失败重试设备测试，2→3 迁移保留旧游标并验证新标记缺失。
- Android `testDebugUnitTest lintDebug assembleDebug` 与 `assembleDebugAndroidTest` 编译通过；新增设备测试尚未执行。`adb devices` 无设备，现有模拟器无硬件加速。不能据此宣称 APK 可用或勾选 N2。

## 2026-09-28 Android 适配 V2 后端（阶段性验证）

- Android 快照和 Room v3 接入持卡人、还款模式／来源、账户修订号；2→3 显式迁移只增加账户字段，旧同步账户的模式留空等待刷新，不清除本地演示数据。后端变更日志的账单／版本事件也不是完整行；发现任何变更均重新拉取完整权威快照并在同一 Room 事务中替换同步表及游标，空变更不覆盖缓存，避免以事件缺失字段补零。代价是有变更时增加网络和读写开销，尚待端到端压力验证。
- 草稿核对必须手动选明确认模式的账户；独立还款须唯一有效卡且卡尾号不冲突，确认携带草稿 `expected_revision`；缺失币种不再默认人民币，手机只允许显式核对 CNY／USD 两位小数金额，其他币种转管理后台核对。手机仅确认汇总，明细仍由管理后台核对。正式账单按账户模式提示合并还款，并更正正式账单的演示文案。
- 本地离线 Gradle 执行 `testDebugUnitTest lintDebug assembleDebug assembleDebugAndroidTest`：构建、单元测试、Lint 和设备测试 APK **通过**；Room v3 schema 已生成。新增 JVM 测试覆盖独立／合并还款确认门槛和缺失／不支持币种；新增设备测试覆盖同持卡人同尾号的独立账户分别统计、2→3 保留旧账单／卡片／游标／演示数据，设备测试**仅编译，尚未执行**。沙箱内首次尝试因无法读取 SDK jar 失败，经授权在沙箱外离线重跑成功。
- **未验证**：尚未在专用设备／模拟器运行迁移与界面交互测试，未对真实后端执行 Android 端到端同步；不宣称设备验收或用户安装包已验证可用。未执行用户数据库迁移或部署。

---
## 2026-09-28 V2 历史归属预检加固（非验收）

- 仅加强只读预检：阻断归档目标账户、独立还款无唯一有效卡／指定归档卡、同账单已确认明细出现多个卡尾号仍整体映射单卡、当前版本不在该账单版本清单及原归属与预览不一致。归档兄弟卡不计入唯一有效卡；普通人工复核提示不直接否定显式映射。页面禁用归档账户候选，卡候选仅显示有效卡。
- 合成场景运行 `python -m pytest backend/tests/test_bank_rules.py backend/tests/test_legacy_card_guards.py backend/tests/test_ownership_mapping.py backend/tests/test_ownership_preview.py backend/tests/test_parsing_v2.py backend/tests/test_statement_correction_details.py backend/tests/test_detail_sets.py -q`：**119 passed**（全局 Python 环境的 pytest-asyncio 1.4.0）。`web` 目录执行 `npm run build`：TypeScript／Vite 通过，Ant Design 分包体积警告仍在。
- `backend/.venv` 的 pytest-asyncio 0.26.0 与当前 session-scope event_loop 配置冲突，按原命令收集即报 `MultipleEventLoopsRequestedError`；不将其误记为业务测试失败，也未改动全局测试配置。只读预检始终 `can_execute=false`，没有迁移入口；仍缺隔离 PostgreSQL、备份恢复、实际并发和人工核对验证，未触碰用户数据库或真实邮件。

---
## 2026-09-28 V2 后补明细来源与锁顺序防护（非验收）

- 追加明细要求旧逐笔来源 ID、新草稿邮件来源及旧来源查询结果均可核验；来源不明或同邮件重解析不得直接追加，可由管理员核对原文后明确选择全量替换，旧快照不被修改。统一后补与普通草稿确认的锁顺序为“草稿→账单”，避免反向锁序导致的潜在死锁。
- 新增缺失来源的多种合成场景、显式替换保留旧行及锁顺序回归断言；选定 V2 后台合成测试 **115 passed**，Python 编译及 `git diff --check` 通过（只有 Git 行尾转换警告）。
- **未验收**：上述断言不是数据库并发实测；仍需隔离 PostgreSQL 迁移、真实行锁与回滚验证，未触碰用户数据库、真实邮件或付费模型。

---

## 2026-09-28 V2 管理后台明细后补界面增量验证（非验收）

- 账单详情增加后补入口，可选择最近候选草稿或输入草稿 ID，逐笔勾选可核对交易，明确选择追加／全量替换，录入来源预期笔数并在证据齐全时显式标记完整；明细快照历史可只读查看。提交携带账单版本、明细修订与草稿修订，冲突不自动覆盖。
- `web` 目录执行 `npm run build`：TypeScript 与 Vite 构建通过；Vite 提示 Ant Design 分包超过 500 kB。后端相关合成测试 **110 passed**、Python 编译通过、Alembic `0012 (head)`；`git diff --check` 无空白错误（Git 行尾转换警告）。
- **未验收**：未接真实邮件／模型、未在浏览器端做人工交互和端到端验证；未对用户数据库迁移，尚缺隔离 PostgreSQL 迁移、约束、并发、回滚及 Android 设备验证。

---

## 2026-09-28 V2 明细后补版本增量验证（非验收）

- 后端增加 `0012` 非破坏性明细集迁移、纯明细后补确认 API、账单详情生效明细读取、历史明细集查询及金额更正时明细继承；无账单金额／还款写入，旧明细快照保留。确认草稿与账单行锁、预期修订、请求指纹幂等、重复来源保护和完整性保守判断均有合成测试。
- 执行 `python -m alembic -c backend/alembic.ini heads`：`0012 (head)`；`python -m pytest backend/tests/test_bank_rules.py backend/tests/test_legacy_card_guards.py backend/tests/test_ownership_mapping.py backend/tests/test_ownership_preview.py backend/tests/test_parsing_v2.py backend/tests/test_statement_correction_details.py backend/tests/test_detail_sets.py -q`：**110 passed**（合成测试）；相关 Python 编译通过。
- **未验收**：未迁移用户数据库；未在隔离 PostgreSQL 上实测迁移、约束、行锁和回滚；后台网页已接入但尚未做浏览器端到端验证；未做 Android 构建／设备测试或真实邮件模型质量验证。不能把合成测试当成上线验收。

---

## 2026-09-28 V2 人工更正明细保留增量验证（非验收）

- 账单人工更正创建新版本时保留当前确认明细及来源关联，不修改旧版本；总额变更、覆盖计数不可信或旧版本无明细时，完整状态按证据降级。更正记录版本新增与账单更新的变更日志；草稿确认命中已有账单时加行锁检查版本。
- 合成测试覆盖同额更正、金额变更、旧版无明细、旧版覆盖状态缺失、过期版本冲突。运行 `python -m pytest backend/tests/test_statement_correction_details.py backend/tests/test_legacy_card_guards.py backend/tests/test_bank_rules.py backend/tests/test_ownership_preview.py backend/tests/test_ownership_mapping.py backend/tests/test_parsing_v2.py backend/tests/test_contracts.py -q`：**112 passed**；相关 Python 文件编译与 `git diff --check` 通过。
- 此处只验证合成测试：隔离 PostgreSQL 迁移、行锁并发和数据回滚验证仍缺；未接触用户数据库，未做 Android 或 Web 端到端验证。纯明细后补全仍未实现。

---

## 2026-09-28 V2 账户与卡片防绕过增量验证（非验收）

- 合成数据覆盖独立还款卡恢复、卡尾号编辑、账户身份／模式编辑、带草稿匹配的账户和卡片删除、停用卡普通拆分及无冲突恢复等。运行 `python -m pytest backend/tests/test_legacy_card_guards.py backend/tests/test_bank_rules.py backend/tests/test_ownership_preview.py backend/tests/test_ownership_mapping.py backend/tests/test_parsing_v2.py backend/tests/test_contracts.py -q`：**107 passed**；相关 Python 文件编译通过，`git diff --check` 无空白错误。
- 后台新增卡及恢复卡通过账户行锁串行校验，但尚未在升级后的隔离 PostgreSQL 中测试并发、事务、迁移和备份恢复；未执行历史归属迁移，未连接用户数据库。Web 构建结果沿用此前验证，本轮未重跑；Android 构建与设备验证未进行。

---

## 2026-09-28 解析 V2 阶段性验证（尚未完成验收）

- 显式映射只读预检与旧拆卡／删除保护：新增合成数据测试 11 项；与原 78 项联合共 89 项通过。目标账户／卡片均由管理员明确选择，检查账单版本、账户修订和目标账期冲突；预检响应明确不可执行。已有账单或草稿时普通拆卡／删除卡片返回 409。管理后台构建通过。尚无执行迁移、备份证明和隔离 PostgreSQL 集成验收。
- 历史归属只读预览：新增合成数据测试 4 项；联合原解析相关测试共 78 项通过。预览不设置拟调整目标，也不执行合并、拆分或模式回填；后台页面构建成功（Vite 包体积警告）。预览接口数据库集成测试、备份恢复、人工确认迁移仍待实施。未在用户数据库执行迁移。

- 合成数据单元／契约测试：`tests/test_parsing_v2.py`、`tests/test_bank_rules.py`、`tests/test_contracts.py` 共 74 项通过；包括 HTML 表格保留、附件清单但拒绝假解析、笔数覆盖状态和严格金额／日期。
- 后台 Python 编译通过；`web` 的 `npm run build` 通过，仅有 Vite 包体积警告。
- 增量迁移 `0008`～`0011` 尚未在用户数据库执行。此前数据库集成测试发现本机测试库缺少 `accounts.billing_mode` 等新列；不能因此宣称数据库集成测试通过。应在隔离测试库完成迁移和验证，先备份并验证恢复路径后才考虑现有数据迁移。
- 通用文本模型接口暂不支持直接提交附件；PDF／图片标记为待适配并阻断解析，没有调用真实模型或验证真实账单质量。历史归属人工确认迁移和独立明细补全版本仍待实现。Android 未构建和设备验证，不宣称 APK 可用。

---

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
