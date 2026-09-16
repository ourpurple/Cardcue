# 首版验证记录

记录日期：2026-09-16。状态：**源码已编写，Android 构建与安装验收尚未完成**。

## 已通过

| 检查 | 结果 | 能证明什么 |
|---|---|---|
| 后台 `python -m pytest -q` | 14 项通过 | 健康接口、未实现能力声明、解析草稿字段约束和异常标记符合测试 |
| Kotlin PSI 语法检查 | 13 个 Kotlin / Gradle Kotlin 文件，无语法错误 | 源码可被 Kotlin 语法解析器读取；不包含依赖解析或类型检查 |

后台用例覆盖：缺失值保持为空、零金额与缺失区分、拒绝浮点数/字符串/布尔值金额、金额上限、日期冲突、最低还款额冲突、原文依据缺失、卡片尾号格式。它们不证明模型真实解析准确率，因为模型尚未接入。

## 已编写但未执行

- 20 个 Kotlin 金额与日期规则检查，由 JUnit 调用：金额精度、非法输入、部分还款、全额结清、撤销、超额还款、跨年和闰日等。
- Room 设备测试：演示数据初始化幂等、还款撤销、并发全额还款、数据库关闭再打开后持久化。
- Compose 设备测试：打开详情、录入部分还款、撤销记录。

## 尚未通过的验收门槛

- Gradle 依赖解析与编译。
- `testDebugUnitTest`、`lintDebug`、`assembleDebug`。
- `connectedDebugAndroidTest`。
- 模拟器或真机页面检查、字体缩放、安装启动、进程重启后的本地数据验证。
- APK 产物生成。**源码包不包含 APK。**

## 环境阻塞和已尝试动作

1. 用户指定目录是 `D:\code\cardcue`，当前会话只允许写入 `C:\Users\Duolly\Documents\Codex`。请求目录写入权限未获得授予，未向 D 盘目录写入。
2. 初次已下载 JDK 与 Android command-line tools。会话权限变化后网络受限，下载 Gradle 的请求出现 Windows 套接字权限错误 `WinError 10013`。
3. SDK Manager 无法下载平台清单，未能安装 `platforms;android-35`。本地没有完整 Gradle/Android SDK 缓存。
4. 尝试使用 command-line tools 内置的 Kotlin 库运行金额检查，但该库是供 Lint 使用的裁剪版本，缺少 JVM 代码生成类，不能用于 Kotlin 编译。因此未将金额检查标为通过。
5. 使用现有库仅执行 Kotlin PSI 语法检查，该检查与完整构建的区别已明确记录。

## 接续操作

在 Codex 将 `D:\code\cardcue` 打开为可写项目，并允许构建工具联网；将源码包解压到该目录。安装 Android Studio / SDK 后，执行 README 中的构建脚本。先解决编译或测试失败，再交付 APK。不要跳过构建验收直接接入真实账单。
