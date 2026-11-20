# 随行 B1/B2 Android 首版设计

用户已确认：按 B1/B2 范围实现，百度 Android AK 稍后配置。代码以 1zqc1/suixing 为准，首轮不接入车辆控制、家属共享或语音固件。

## 范围与交付
新建 android/suixing-app，提供模拟轨迹、手机 GPS 轨迹、开始/结束记录、SQLite 本地保存、历史回放、JSONL 导出、定位精度/失联/断网状态。交付源码、Debug APK、模拟轨迹、回归命令及实测结果。

## 环境
保留 dev-env/tests/android-baseline。队友 B 本机使用已验证的 JDK 21 / Gradle 8.11.1 / AGP 8.9.2 / compileSdk 35 / Build Tools 35.0.0，Java 17 源码，minSdk 23。团队原 JDK17/API36 验收基线不修改。本机可在 AndroidReady_API_34 验证，手机户外验收需另行实测。

## 数据与模块
- org.suixing.app.core：纯 Java LocationFix、TrackPoint、TrackFilter、TrackMetrics。epochMillis 用于展示/跨设备 UTC 事件关联，elapsedMillis 用于排序、过期、距离分段；不可混用。
- Android TrackStore：SQLite sessions/points，逐点持久化，进程重启恢复未结束会话为 interrupted。原始坐标固定 WGS84，存精度、来源、序号、段号与两种时间。
- 手机定位：Android LocationManager，仅用户同意且授予精确定位后启动 location 类型前台服务。停止即注销定位并关闭服务。不自动上传。
- 模拟轨迹：固定 assets/demo-track.csv，标记 DEMO。模拟模式不请求定位权限。
- MapPanel：配置有效 AK 且用户同意后才初始化百度 Map SDK 9.0.0。使用官方转换器把 WGS84 转 BD09LL，仅用于地图显示。未配置 AK 使用明确标注的坐标轨迹示意，不伪装百度地图或真实当前位置。
- 历史：记录结束保存；会话回放仅显示历史位置，不把历史点混入实时记录。不同分段不画连接线。导出由用户选择文件位置。
- 预留只读风险事件协议文档，未提供的队长/A 接口不伪造为在线连接。

## 质量规则
过滤非法/非有限坐标，精度 >80m，超过15秒的陈旧采样，未来 >1秒的采样，倒序/重复 elapsed 时间，以及不合理跳点。断流 >20秒后新建轨迹段。步行最大合理速度12m/s，跳点阈值考虑定位误差。断网不停止本地 GPS 记录，不补造路径或危险状态。
界面中文，主按钮不小于48dp，有 contentDescription；明确模拟/实时/回放来源，展示点数、距离、时长、精度与网络状态。

## 验收
纯 Java 单元测试覆盖校验、时序、跳点、断流分段及跨段距离；模拟器回归覆盖模拟记录/停止/历史/回放/进程重启、权限路径和离线本地持久化。签名报告提供包名 org.suixing.app 和 Debug SHA1，供用户申请 AK。缺少 AK 的真实百度底图与手机户外步行，明确列为待配置/待实测。
