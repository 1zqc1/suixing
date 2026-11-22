# 随行 App 运行排查

## 百度地图鉴权与底图

**表现与影响。** 地图面板可能显示轨迹示意、授权失败或底图超时。轨迹采集和本地回放有独立的数据路径。用同一 APK 分别核对配置、鉴权和道路底图。

| 证据 | 排查与修正 |
|---|---|
| 未配置 AK、包名或签名不匹配 | 确认 `sdk.dir` 与 `baidu.map.ak` 各占 `local.properties` 一行。工程优先使用本地文件中的 AK，缺省时读取 `BAIDU_MAP_AK`。核对实际 APK 的 `org.suixing.app`、`apksigner verify --print-certs` 输出的证书 SHA-1、百度控制台的 Android 应用类型和地图服务。重建后核对实际安装包。使用者同意隐私设置后才初始化 SDK。[配置说明](../../../../android/suixing-app/README.md#配置百度地图) |
| SDK 鉴权返回 `-11` | 按百度官方定义排查 HTTPS。核对设备网络、时间和代理，待网络连通后用同一 APK 冷启动。发现密钥、包名或签名绑定不符时再处理绑定。 |
| 鉴权返回 `0`，底图仍白。渲染回调 `1004` 并报告网络连接错误 | 可用同一 APK 比较测试 AVD 的 Wi-Fi 与模拟蜂窝网络，观察同一视图有无道路和地名。本项目曾在模拟蜂窝网络看到真实底图，而虚拟 Wi-Fi 超时。其他设备按实测判断。 |
| 实际道路已画出，但应用还显示底图超时 | 核对 `onMapLoaded`、鉴权和渲染回调的先后。本项目正常加载时可只收到 `onMapLoaded`，没有单独的正向 render 回调。现有 `MapReadiness` 以鉴权成功、加载完成且无当前渲染失败为就绪条件，鉴权失败或未加载时保留回退。滚动容器里使用 `TextureMapView`。 |

**验证与预防。** 查看实际道路、地名和至少一段轨迹覆盖物。Logo 与缩放控件只说明地图视图已创建。修改就绪逻辑时复跑 `MapReadinessTest`，覆盖无正向 render 回调、加载超时和授权失败。日志记录阶段和错误码，排除 AK、完整请求 URL 和用户坐标。[百度官方错误码说明](https://lbsyun.baidu.com/index.php?title=模板:FAQ-Android-map) · [百度地图视图指南](https://lbsyun.baidu.com/docs/android?title=androidsdk%2Fguide%2Fcreate-map%2Fshowmap)

## 系统返回与 IDE 检查

**表现与影响。** `GestureBackNavigation` 可能把 `MainActivity.onBackPressed()` 标红。实际行为涉及取消历史回放、退出历史和系统返回。

**排查与修正。** 先跑构建和 Lint。核对 Manifest 的返回回调设置和 `MainActivity` 的 API 分支。API 33 及以上使用 `OnBackInvokedCallback`，Android 12L 及以下使用旧接口。确认新回调已生效、旧方法承担兼容后，只在该旧方法上抑制 `GestureBackNavigation` 和弃用告警。

**验证与预防。** 回放中按系统返回应先取消回放，再按一次应回到实时页。升级目标 API 后复测新版本，并在可用的旧版本上验证兼容路径。[Android 预测性返回指南](https://developer.android.com/guide/navigation/custom-back/predictive-back-gesture)

## GPS 采样分段与回放

**表现与影响。** 实时点数增长不均，回放中的「时长」跳跃，历史地图分段，或断网时轨迹仍可录制和回放。当前 App 将通过过滤的点存入本机 SQLite。百度道路底图独立下载和缓存。

**排查与修正。**

1. 对照 `PhoneService` 的定位请求、`TrackFilter` 的保存条件和 `MainActivity` 的回放进度。当前 GPS 请求的 1000 ms 是更新间隔下限。过期、精度差、跳点和小幅位移都可能被拒绝。「位置稳定，已忽略定位抖动」表示 App 收到回调并命中去抖。阈值为 `max(1.5 m, 本次精度 × 0.3)`。
2. 从同一会话的 JSONL 跳过元数据行，检查 `sequence` 的连续性，用相邻点的 `elapsedMillis` 做差。对照 `segment`、`accuracyMeters` 与 `source`。当前间隔超过 20,000 ms 才开启新段。20,999 ms 和 20,001 ms 均会分段，17,000 ms 仍在同一段。分段保持同一会话，连线和距离按段处理。
3. 回放以预览节奏推进保存点，屏幕「时长」取已显示轨迹的采样时间跨度。JSONL 只有接受点且无逐点网络状态。判断具体空档的成因需要录制时的系统回调间隔、过滤原因和本地保存结果。证据不足时记录原因待确认。验收按实测保存点统计，保留原始时间差与分段。

**验证与预防。** 真机选择「手机 GPS」，保持系统定位与精确位置权限，先记录一段。关闭 Wi-Fi 和移动数据，继续移动并核对点数。恢复联网后观察同一会话是否继续采样，结束并回放。单独记录已缓存区域的底图显示情况。修改过滤规则时复跑 `TrackFilterTest` 的去抖、乱序和 20 秒边界用例。验收证据优先保留点数、相对时长、典型间隔与分段统计。[Android 定位回调参数](https://developer.android.com/reference/android/location/LocationManager)

## 回归与验收范围

在 `android/suixing-app` 按 [项目回归命令](../../../../android/suixing-app/README.md#回归) 构建和测试。准备提交时一并运行 `lintDebug`。设备回归记录实际选中的设备和结果。M1 样例按 [车况回归说明](../../../../android/suixing-app/docs/m1-vehicle-status.md) 核对三种只读场景及制动请求与执行回读。验收记录注明本地样例、模拟定位或真机实测各自覆盖的范围。
