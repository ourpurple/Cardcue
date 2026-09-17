# 首版验证记录

更新日期：2026-09-17。状态：**P0 设备测试全部通过，布局修复验证完成；后台新架构尚未实现**。

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

## 历史记录

### 2026-09-16

当日状态：源码已编写，Android 构建与安装验收尚未完成。后台 `python -m pytest -q` 14 项通过。
