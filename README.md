# CardCue

个人自用的 Android 信用卡账单工具。**当前仍是 0.1.0 本地演示版本；目标已调整为后台统一存储和定时解析、Android 启动同步。新架构尚未实现，P0 新增设备测试仍待完整验证。**

## 当前能力

- Compose 账单首页：按还款日排序、各币种独立汇总、近期到期数量。
- 账户账单模型：多张卡可关联同一份账单，金额只计一次。
- 账单详情、历史筛选、本地 Room 持久化。
- 部分或全额还款记录、金额校验、撤销留痕。
- 金额使用整数分，拒绝多余小数、零值、负数和超额还款。
- FastAPI 服务骨架、健康检查及下一阶段解析数据结构草案。

当前 App **不读取邮箱、不调用模型、不转账、不发送通知**。页面会明确显示演示状态。当前没有备份功能，卸载或清除数据会丢失本地记录。

## 已确定的目标架构

- 后台定时读取新浪邮箱，统一完成文档提取、模型解析与草稿管理；手机关闭不影响收件。
- 后台统一保存账户、卡片、账单、版本、邮件来源和还款记录。Android 使用 Room 缓存，启动时自动同步。
- 手机提供核对、确认入账、记录还款与撤销；后台校验并保存。首版后台模式离线可查看缓存，写入需联网。
- Android 按首页、账单、账户、同步等功能拆分；邮箱授权码和模型密钥只保存在后台。
- 保留现有本地数据，通过明确迁移区分旧演示数据和服务端正式账单，不自动上传演示欠款。

完整职责、业务模型、同步协议与迁移原则见 [架构说明](docs/ARCHITECTURE.md)。以上是目标设计，当前 App 仍独立运行。

## 目录

```text
android/     原生 Android 工程（Kotlin + Compose + Room）
backend/     FastAPI 服务骨架和解析字段草案
docs/        开发阶段、架构、验证记录
scripts/     Windows 构建辅助脚本
```

## Android 开发

要求：JDK 17、Android SDK Platform 35、Android Build Tools 35.0.0；运行设备最低 Android 8.0 / API 26。Gradle 使用 8.9，Android Gradle Plugin 使用 8.7.3，Kotlin 使用 2.0.21。

1. 将工程放到 `D:\code\cardcue`，用 Android Studio 打开其中的 `android` 目录。
2. 用 Android Studio SDK Manager 安装 Platform 35、Build Tools 35.0.0，以及模拟器或手机调试工具。
3. 设置 `JAVA_HOME` 与 `ANDROID_HOME`，或给下方脚本传入路径。
4. 首次运行构建脚本需要联网下载 Gradle 和 Maven 依赖：

```powershell
cd D:\code\cardcue
.\scripts\build-android.ps1 -JavaHome '你的JDK目录' -AndroidHome '你的Android SDK目录'
```

工程已包含标准 Gradle Wrapper，下载版本由官方 SHA-256 固定。脚本运行单元测试、Lint 和 debug APK 构建。官方 Gradle 下载超时时可加 `-UseMirror`：优先复用项目内的镜像缓存，缓存缺失时下载镜像并校验 SHA-256。此选项只影响 Gradle 发行包，不改变 Google/Maven 依赖仓库。

若依赖下载出现 `Permission denied: getsockopt`，可在允许联网的终端加 `-NoDaemon`，避免复用此前在受限会话中启动的 Gradle 后台进程：

```powershell
.\scripts\build-android.ps1 -UseMirror -NoDaemon -DeviceTests
```

`-NoDaemon` 不会授予网络权限；构建进程仍需获准访问依赖仓库。未连接测试设备时去掉 `-DeviceTests`。

成功后 APK 位于 `android/app/build/outputs/apk/debug/app-debug.apk`。后续也可使用：

```powershell
cd D:\code\cardcue\android
.\gradlew.bat testDebugUnitTest lintDebug assembleDebug
```

连接专用测试设备或启动模拟器后，运行 `scripts/build-android.ps1 -DeviceTests`，或用 Wrapper 执行 `connectedDebugAndroidTest`。新增测试已改为由专用 Application 注入独立数据库，目前仍待完整回归；不要为了测试卸载 App 或清除日常数据库。

## 后台开发

首版 App 独立运行，不需要启动后台。后台目前只有健康检查和能力声明。

```powershell
cd D:\code\cardcue\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn cardcue_api.main:app --reload --host 127.0.0.1
```

本地文档：`http://127.0.0.1:8000/docs`。不要将当前无鉴权的开发服务公开到互联网。

## 下一阶段

先完成当前 P0 测试改动的验证，再依次推进后台业务与 PostgreSQL 存储基础、Android 功能拆分、启动同步与在线写入、后台定时收件、模型解析和人工确认，最后完成旧数据迁移与后台备份恢复验收。任务、依赖和验收标准详见 [开发计划](docs/PLAN.md)。

邮箱授权码、模型密钥及真实邮件样本不要提交到 Git。`.gitignore` 已排除常见凭证文件与邮件样本。

## 验证状态

后台原有 14 项测试已通过。P0 首页规则与测试隔离改造后的主程序构建、单元测试和 Lint 已通过；新增设备测试在编译阶段发现问题，修正后尚未完整重跑。Android 16 真机上的 4 项设备测试通过记录属于此前版本，不能作为当前 P0 或新架构验收结果。详见 [验证记录](docs/VERIFICATION.md)。
