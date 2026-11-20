# 随行轨迹 · Android B1/B2

随行使用手机 GPS 或内置模拟路线绘制轨迹，按次保存在本机。无百度 AK 时，地图区域显示“轨迹示意 · 未配置百度地图 AK”。示意图中的线和标记来自轨迹点，不包含道路底图。

## 运行

1. 在本目录配置 Android SDK 35、Build Tools 35.0.0、JDK 21，使用工程自带的 Gradle 8.11.1。Windows 下 `Build.cmd` 优先使用已安装的 `D:\Android\java\jdk-21.0.13.1+2`。应用使用 Java 17 语法、AGP 8.9.2，最低 Android 6.0（API 23），目标 API 35，支持 arm64-v8a 和 x86_64。
2. 设置 `ANDROID_HOME` 或在本地 `local.properties` 写入 `sdk.dir=D:/Android/SDK`。在本目录运行 `.\Build.cmd testDebugUnitTest assembleDebug`，缓存就绪后可追加 `--offline`。
3. 通过 `adb install -r app/build/outputs/apk/debug/app-debug.apk` 安装并打开“随行”。在隐私弹窗选择同意，或选择“仅使用模拟和历史”。

## 记录与回放

- **模拟轨迹**使用 `app/src/main/assets/demo-track.csv`，约每秒一条，精度字段固定 3 米，所有点标记为 `DEMO`。开始、行走一段、结束后可打开历史。界面转入后台时结束并保存模拟会话，旋转屏幕会延续同一会话。
- **手机 GPS**需要隐私同意和使用期间的精确位置权限。系统定位未开启时可以跳转到设置。按“开始记录”后，位置型前台服务工作，离开界面仍可记录。Android 13 及以上可单独选择“允许显示记录通知”，从通知或应用内结束记录。撤回隐私同意会停止 GPS。
- **质量状态**显示精度、等待、定位错误或信号中断。坐标或精度无效、精度超过 80 米、过期、倒序和不合理跳点会被滤除。真实时间间隔超过 20 秒会开启新段。位置稳定时忽略抖动。时长来自首末已接受点的单调时间差，距离只累计同一段的相邻点。网络状态单独展示，断网可继续本地 GPS 记录。
- **本地历史**列出会话日期、来源、点数和完成状态。异常退出后重新打开应用，未结束的会话会标记为中断，已提交的点和空会话均可查询。选择会话后可逐步回放、取消回放或返回实时视图。回放速度用于快速预览。
- **导出 JSONL**通过系统文档选择器指定位置，无需存储权限。首行是 `suixing.track.v1` 会话元数据，后续每行是按序号排列的轨迹点。字段包括 `sessionId`、`sequence`、`segment`、`epochMillis`、`elapsedMillis`、`latitude`、`longitude`、`accuracyMeters`、`source` 与 `coordinateSystem=WGS84`。系统明确标记模拟定位时，GPS 点来源为 `PHONE_GPS_MOCK`。模拟器底层注入可能未带该标记，设备验收需单独记录测试环境。

## 配置百度地图

在百度地图开放平台创建 Android SDK 类型应用，绑定包名 `org.suixing.app` 和实际 APK 的签名证书 SHA1，并开通所需地图服务。可以用 `apksigner verify --print-certs app/build/outputs/apk/debug/app-debug.apk` 读取签名。Debug 与 Release 证书可能不同。[百度官方 AK 配置指南](https://lbs.baidu.com/docs/guide?title=android-guide/create-project/ak)

在已忽略的 `local.properties` 中设置 `baidu.map.ak=你的AK`，或设置环境变量 `BAIDU_MAP_AK`，再重新构建安装。同意隐私设置且配置了 AK 后才初始化百度地图。数据库和 JSONL 保留 WGS84，百度底图渲染使用官方坐标转换器转为 BD09LL。鉴权、原生库或底图数据加载失败会显示相应提示并退回轨迹示意图。

## 回归

```powershell
.\Build.cmd --offline testDebugUnitTest assembleDebug assembleDebugAndroidTest
adb -s emulator-5554 install -r app/build/outputs/apk/debug/app-debug.apk
adb -s emulator-5554 install -r -t app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
adb -s emulator-5554 shell am instrument -w -r -e class org.suixing.app.TrackStoreTest org.suixing.app.test/android.test.InstrumentationTestRunner
```

设备测试通过 Android 原生 SQLite 检查字段往返、按序读取、正常结束、进程中断恢复与空会话。单元测试涵盖滤波、里程、地图状态、定位心跳和长轨迹回放采样。示意图自动适配全程，百度底图就绪时才开放相机跟随操作。

要复验立即停止、启动期间 GPS 关闭、导出阻塞期间的逐点写入，以及示意图控件状态，可在专用 API 34 模拟器上运行完整设备套件。先安装上面的应用和测试 APK，确保应用空闲、系统位置开关已开启。在模拟器测试安装上运行以下命令，验证后恢复原权限。GPS 用例使用 Android 测试提供程序，并在结束时移除。

```powershell
adb -s emulator-5554 shell pm grant org.suixing.app android.permission.ACCESS_COARSE_LOCATION
adb -s emulator-5554 shell pm grant org.suixing.app android.permission.ACCESS_FINE_LOCATION
adb -s emulator-5554 shell appops set org.suixing.app android:mock_location allow
adb -s emulator-5554 shell am instrument -w org.suixing.app.test/android.test.InstrumentationTestRunner
```

API 34 模拟器的注入定位只验证软件链路，真实手机的户外 GPS、续航和有效 AK 底图仍需现场验收。

车辆读数尚未接入，预留事件字段与时间域见[只读风险事件约定](docs/read-only-risk-events.md)。
