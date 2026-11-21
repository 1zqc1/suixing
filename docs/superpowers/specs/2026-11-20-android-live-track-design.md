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

## 用户新增交接：M1 队友 B 只读车况

用户提供 m1-handoff-v0.1 并要求找到队友 B 的任务继续完成。交接 README 与 M1-接口草案明确：B 读取三个独立 vehicle-status JSON，制作只读状态页及回归，区分制动请求与执行回读。完整包已通过 SHA256SUMS 及审阅后的 verify.py 离线验证。

新增本地“车况样例”页面，入口接入现有 APP；页面固定标注合成样例、数据版本 m1-handoff-v0.1、未连接实车。展示系统状态、运动许可、急停、制动请求、制动执行回读、D6/双目健康、原因码和合成样本 UTC。三个场景独立切换，不串联推断锁存历史。运动许可来自布尔字段，不由 READY 推断。缺失、未知枚举、非法类型不得默认为正常或已确认施加。

| 输入 | 必须显示 |
|---|---|
| normal.json | 待机 READY；D6/双目在线；未请求制动；执行反馈 RELEASED；无运动许可 |
| sensor-offline.json | FAULT_SAFE；D6 离线；已请求制动；执行回读 UNKNOWN，尚未确认施加；无运动许可 |
| brake-latched.json | 制动锁存 BRAKE_LATCHED；已请求制动；执行回读 APPLIED，已确认施加；无运动许可 |

仅纳入 B 使用的三个原样 JSON 和来源/校验元数据。页面没有发车、解除锁存、制动或其他车辆控制操作；数据来源始终标记 mock。样本 UTC 只是合成展示时间，不能当作当前实车状态或跨设备新鲜度依据。A 的传感处理和队长的 ROS/RiskSummary 板端联调按交接分工保留给对应角色。

回归报告记录包版本、来源 SHA256、代码提交、命令、预期、实测、日志/页面截图。原有地图记录与回放继续验收；此新增任务在最终打包前完成。
