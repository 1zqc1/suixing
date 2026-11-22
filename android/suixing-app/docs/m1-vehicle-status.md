# M1 只读车况样例

在随行首页点“车况样例”，选择“待机”“D6 离线”或“制动锁存”。数据来自交接包 `m1-handoff-v0.1` 的 `vehicle-status/`，其清单标注架构版本 `0.1`、来源 `mock`、样本包仓库基线 `b0d17fce44f967be418c7583fb03186d3b44c9e2`。下列文件原样存放在 `app/src/main/assets/m1-handoff-v0.1/vehicle-status/`。SHA-256 取自交接包 `SHA256SUMS`。

| 样例 | SHA-256 |
|---|---|
| `normal.json` | `00f389be8f829d2366d17fa35b3cf9c23d94d96a7bd2f7fde207f0e08e6e00e7` |
| `sensor-offline.json` | `fb2638940efeb994d0fffe3fecc3c188f8a8c9c403cbadf55fef3afc94531bf5` |
| `brake-latched.json` | `96beafd46f166160ce817274b8fda4971724a5f852892d109ba7a482a7af01ef` |

| 场景 | 系统状态 | 运动许可 | 制动请求 | 制动执行回读 | D6 雷达 | 双目相机 | 原因码 |
|---|---|---|---|---|---|---|---|---|
| 待机 | `READY` | 无 | 未请求 | `RELEASED`，已释放 | 在线 | 在线 | `NONE` |
| D6 离线 | `FAULT_SAFE` | 无 | 已请求 | `UNKNOWN`，尚未确认施加 | 离线 | 在线 | `D6_OFFLINE` |
| 制动锁存 | `BRAKE_LATCHED` | 无 | 已请求 | `APPLIED`，已确认施加 | 在线 | 在线 | `HAZARD` |

三份样例的急停字段均未激活，时间均为合成的 `2026-11-20T00:00:00Z`。切换时重新读取所选文件，因此任一场景都可独立查看。格式、数据来源或版本无法读取时，页面显示样例不可用。可读样例中的未知枚举、字段缺失或类型错误显示为未知。运动许可、急停和制动请求只接受 JSON 布尔值。页面使用本地文件，屏幕顶部持续显示来源、版本和未连接实车提示。样本时间仅供展示。

解析使用 Gson 2.11.0 的严格流式读取模式。忽略的成员也接受字面量语法检查，其容器嵌套最多 32 层。短窗口内，标题和返回键随场景区滚动，精简后的来源与版本提示仍固定显示。[Gson 2.11.0 发布说明](https://github.com/google/gson/discussions/2677)

## 回归命令

在 Android 应用目录构建并安装 APK，然后运行车况设备测试。首次构建需要下载尚未缓存的依赖。

```powershell
.\Build.cmd testDebugUnitTest assembleDebug assembleDebugAndroidTest
adb -s emulator-5554 install -r app/build/outputs/apk/debug/app-debug.apk
adb -s emulator-5554 install -r -t app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
adb -s emulator-5554 shell am instrument -w -r -e class org.suixing.app.vehicle.VehicleStatusDeviceTest org.suixing.app.test/android.test.InstrumentationTestRunner
```

设备测试读取 APK 中的三个原样文件，覆盖页面切换、缺失或无效字段和不支持的 JSON。单元测试检查运动许可布尔字段、制动请求与执行回读的展示。
