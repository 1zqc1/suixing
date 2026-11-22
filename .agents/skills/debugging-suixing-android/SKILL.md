---
name: debugging-suixing-android
description: Use when the Suixing Android app has SDK download or Gradle build failures, Windows emulator freezes, USB debugging issues, Baidu Map authorization or basemap errors, predictive Back inspections, or irregular GPS recording and replay on a device.
---

# 排查随行 Android 问题

适用于 `android/suixing-app` 的 B1/B2 地图与轨迹、真机联调和 Windows 开发环境。先定位故障发生在哪层，再验证最小修正。APK 构建、USB 接通、百度鉴权、道路底图可见和真机定位分别需要对应的证据。

## 按表现找入口

| 表现 | 先看 |
|---|---|
| SDK 下载出现 `Premature EOF`、TLS 握手中断或 `sdk.dir` 标红 | [SDK 下载与路径](references/windows-toolchain.md#sdk-下载与路径) |
| Gradle 的 `metadata.bin` 读取失败 | [Gradle 缓存](references/windows-toolchain.md#gradle-生成缓存) |
| 模拟器启动失败、Windows 整机冻结或手机没有出现在设备列表 | [模拟器](references/windows-toolchain.md#模拟器与-windows-冻结) · [USB 真机](references/windows-toolchain.md#usb-真机调试) |
| 「未配置 AK」「授权失败（-11）」「底图加载超时」或地图只显示示意 | [百度地图](references/app-runtime.md#百度地图鉴权与底图) |
| `onBackPressed()` 标红或系统返回从历史页直接退出 | [返回手势](references/app-runtime.md#系统返回与-ide-检查) |
| 断网后轨迹点仍增加、回放时长跳变，或相邻保存点相隔约 20 秒 | [GPS 采样与本地回放](references/app-runtime.md#gps-采样分段与回放) |

## 开始排查

1. 核对当前分支、实际构建的 APK、目标设备与系统 API。确认症状发生在构建、启动、实时记录或历史回放的哪个阶段。USB 真机与模拟器并存时，用实际设备 ID 指定目标。
2. 记录首个相关错误、触发操作、相对时间和能区分原因的对照结果。复用项目的 [构建和设备回归](../../../android/suixing-app/README.md) 与 [Android 工具指南](../../../docs/android-github-tooling.md)。涉及权限、测试设计或应用 ANR 时，按需使用指南中对应的 Skill。
3. 用原入口复验。记录提交号、APK 版本、设备或 AVD、API、网络状态、命令、预期与实测。分别注明模拟定位、户外真机和待验证的范围。

## 注意事项

- 百度 AK 保存在本地配置。日志保留错误码、签名匹配结果和底图状态。提交前核对变更范围，排除 `local.properties`、含 AK 的 APK、真机轨迹和带位置的截图。
- 分析轨迹时优先报告点序号、时间差、分段和精度统计。通过测试 AVD 注入定位或调整网络时，记录测试环境并在复测后恢复临时设置。
- USB 首次调试授权由手机持有人确认。重启 Windows、调整启动项或重置设备前，确认操作范围并保留现有数据。
