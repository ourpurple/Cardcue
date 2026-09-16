# CardCue

个人自用的 Android 信用卡账单工具。**当前为 0.1.0 首版源码，使用演示数据；Android APK 尚未完成构建验证。**

## 当前能力

- Compose 账单首页：按还款日排序、各币种独立汇总、近期到期数量。
- 账户账单模型：多张卡可关联同一份账单，金额只计一次。
- 账单详情、历史筛选、本地 Room 持久化。
- 部分或全额还款记录、金额校验、撤销留痕。
- 金额使用整数分，拒绝多余小数、零值、负数和超额还款。
- FastAPI 服务骨架、健康检查及下一阶段解析数据结构草案。

当前 App **不读取邮箱、不调用模型、不转账、不发送通知**。页面会明确显示演示状态。当前没有备份功能，卸载或清除数据会丢失本地记录。

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

脚本校验官方 Gradle SHA-256，生成标准 Gradle Wrapper，然后运行单元测试、Lint 和 debug APK 构建。由于本次环境无法完成依赖下载，源码包暂不包含生成的 Wrapper JAR；首次成功运行脚本后，请把 `gradlew`、`gradlew.bat` 与 `gradle/wrapper/` 提交到版本管理。

成功后 APK 位于 `android/app/build/outputs/apk/debug/app-debug.apk`。后续也可使用：

```powershell
cd D:\code\cardcue\android
.\gradlew.bat testDebugUnitTest lintDebug assembleDebug
```

连接设备或启动模拟器后，运行 `scripts/build-android.ps1 -DeviceTests`，或用 Wrapper 执行 `connectedDebugAndroidTest`。UI 测试要求全新安装的演示数据库；先卸载测试版会删除其全部本地数据。

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

新浪 IMAP 手动同步 → 邮件去重与筛选 → 附件提取 → 大模型结构化解析 → 原文核对与确认入账。详见 [开发计划](docs/PLAN.md)。

邮箱授权码、模型密钥及真实邮件样本不要提交到 Git。`.gitignore` 已排除常见凭证文件与邮件样本。

## 验证状态

后台测试已通过。Android 源码已做语法检查，但尚未通过 Gradle 编译、Lint、设备数据库测试或页面运行验证。语法检查不等于可安装 APK。详见 [验证记录](docs/VERIFICATION.md)。
