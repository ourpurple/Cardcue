# V2 隔离验证环境

测试库仅供合成数据使用。`backend/docker-compose.test.yml` 在本机回环地址开放 `55439`，数据库放在容器临时内存目录，停止容器后不会保留数据。不要使用 `backend/.env` 的用户数据库地址。运行前确认 Docker 可用。

```powershell
docker compose -f backend/docker-compose.test.yml up -d --wait
$env:CARDCUE_ISOLATED_TEST_DB_URL = 'postgresql+psycopg2://cardcue_v2_test:local-only-test-password@127.0.0.1:55439/cardcue_v2_test'
cd backend
.\.venv\Scripts\python.exe -m pytest -q tests/test_v2_migrations.py
```

迁移测试仅接受 `psycopg2` 和精确命名为 `cardcue_v2_test` 的独立数据库；远程地址还必须显式设置 `CARDCUE_REMOTE_TEST_DB=cardcue_v2_test`。每次在随机测试 schema 中分别执行空库升级、从 0007 升级并检验历史账户及卡片不丢失。失败时不得转而在用户库上重试。备份恢复演练和完整数据库集成测试仍需在此隔离库补齐，不能因为上述测试通过就勾选 N1。

Android 设备测试需要专用设备或启用硬件加速的模拟器；构建测试 APK 不算设备验收。不得安装测试 APK 到存有日常数据的设备后运行覆盖升级测试。

### 远程隔离库

现有远程业务库 `cardcube` 仅用于只读预检：当前角色无建库权限，不能将其当成可清理的测试库。请数据库管理员在同一 PostgreSQL 实例上新建 **`cardcue_v2_test`**，为独立测试角色授予该库的连接和建 schema 权限；不要将业务库中的账单或凭证复制过去。通过安全渠道配置测试角色的连接地址，在当前进程设置 `CARDCUE_ISOLATED_TEST_DB_URL` 和 `CARDCUE_REMOTE_TEST_DB=cardcue_v2_test` 后运行上述迁移测试。测试只在隔离库中创建、清理随机 schema，仍需另做备份恢复演练。不得将连接串或授权码提交到仓库。
在 `backend/.env` **追加**以下两项（该文件已被 Git 忽略），不要修改现有业务库的 `DATABASE_URL`／`DATABASE_SYNC_URL`。测试进程会读取这两项，环境变量同名值优先：

```dotenv
CARDCUE_ISOLATED_TEST_DB_URL=postgresql+psycopg2://测试账号:URL编码后的密码@152.70.238.24:5432/cardcue_v2_test
CARDCUE_REMOTE_TEST_DB=cardcue_v2_test
```

密码若有 `@`、`:`、`/`、`#`、`?`、`%` 等字符，须对密码部分做 URL 编码；不要把原密码或完整连接串发到聊天或提交到 Git。测试账号至少需要对此库的 `CONNECT` 和 `CREATE`（建 schema）权限；它**不需要**对业务库的写入权限。填好后可运行 `cd backend` 和 `.\.venv\Scripts\python.exe -m pytest -q tests/test_v2_migrations.py`，或告知我“已配置”，由我继续验证。
### N1 备份恢复准备与验收（尚未执行）

请由数据库管理员在**远程测试实例**安装与服务器兼容的 PostgreSQL 客户端工具（`pg_dump`、`pg_restore`），确认两者可执行，并新建第二个**空**库 `cardcue_v2_restore_test`，授予测试角色连接和建 schema 权限。`cardcue_v2_test` 是备份源，第二库只作恢复目标；绝不要对业务库 `cardcube` 执行这些操作，也不要复制真实账单。当前测试角色没有建库权限，不能通过迁移测试代替管理员准备。

演练时先在源库的随机测试 schema 中建立含合成账户、卡片、账单版本和整数分还款的非空数据，检查来源数据库名后用 `pg_dump -Fc` 备份该 schema；核对恢复目标确实为 `cardcue_v2_restore_test` 且无同名 schema，再用 `pg_restore --no-owner --no-acl` 恢复。分别核对 `alembic_version`、关联外键、整数分金额、行数与源库一致；最后只清理本轮生成的测试 schema 和含合成数据的本地备份文件。**不得使用 `--clean`、覆盖现有库、备份空库充数或将完整连接串／备份文件提交 Git。**在第二库和工具均确认可用前，N1 保持未勾选。

Android 设备首轮 22 项中 19 通过、3 失败；复测遇安装安全确认页并超时。设备原 `com.cardcue.app` 当前包状态异常，继续安装前须先查明旧数据状态。隔离包为 `com.cardcue.app.device.test`，测试 APK 不能当日常版安装。
