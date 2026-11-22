# Windows 工具链与设备排查

从 [应用工程](../../../../android/suixing-app/README.md) 核对当前 SDK、Build Tools、Gradle 和 JDK 版本。随行 0.2.0 的已验证基线为 API 36、Build Tools 36.0.0、Gradle 8.11.1 和 JDK 21。机器上的路径与 PowerShell 版本按当前工作区要求使用。

## SDK 下载与路径

**表现与影响。** SDK Manager 报 `Premature EOF` 或 `SSLHandshakeException: Remote host terminated the handshake` 时，部分组件仍可能安装成功。按失败包区分构建依赖的 SDK Platform、Build Tools，以及运行模拟器依赖的 Emulator、系统镜像。

**排查与修正。**

1. 核对 IDE 的 SDK Location、项目 `local.properties` 和同一目录里的组件安装结果。若 Build Tools 已写入该路径，优先核查失败下载的 HTTPS 链路和代理。
2. `sdk.dir` 指向 SDK 根目录，百度配置另用 `baidu.map.ak`。Windows 编辑器提示盘符转义时，可使用 `sdk.dir=D\:/Android/SDK`。以构建日志确认 SDK 路径能否解析。
3. 用失败包的具体地址验证 HTTPS。比较直连和已配置的代理，分别重试所需组件。自定义更新源报错时，可暂时停用该源后用官方源验证。需要单独下载时，按 Google 官方仓库元数据校验版本和哈希，并保留 HTTPS 验证。

**验证与预防。** 确认目标平台有 `android.jar`，Build Tools 可执行，再走项目的 [Build.cmd](../../../../android/suixing-app/Build.cmd)。需要模拟器时，另核对 Emulator 和系统镜像。记录成功使用的组件版本和网络条件，遇到重试时优先处理失败包。[Android SDK Manager 指南](https://developer.android.com/studio/intro/update#sdk-manager)

## Gradle 生成缓存

**表现与影响。** `mergeExtDexDebug` 或 `mergeDebugGlobalSynthetics` 报 `Could not read workspace metadata`。路径指向 `caches/<Gradle 版本>/transforms/<条目>/metadata.bin`，且堆栈在读取元数据时出现 `EOFException` 或 `Buffer underflow`，可以定位到具体的生成缓存条目。文件存在且非空的情况也需按堆栈判断。

**排查与修正。**

1. 保留首次失败的任务和相关堆栈。用独立 `GRADLE_USER_HOME` 和 `--project-cache-dir`，以 wrapper 指定的 Gradle 版本、相同的 JDK 和 SDK 对照构建。隔离环境可在线预热，离线时使用同版本的 wrapper 分发包和完整的 `modules-2` 依赖缓存，复制时跳过锁文件与待排查的 `transforms`。新缓存单纯缺依赖时，补齐依赖再做对照。成功后再判断是否需要修复 IDE 使用的常用缓存。
2. 修复常用缓存时，先确认没有活动构建，停止相关的空闲 Gradle daemon。核对报错版本、实际路径和条目 ID。将已确认损坏的生成条目移到同一版本目录下的独立备份位置，保留依赖下载缓存和项目文件。条目仍被占用时，优先用独立缓存继续任务。

**验证与预防。** 用普通 `Build.cmd` 重新构建并复跑原失败任务。独立缓存通过只说明隔离环境可用。遇到异常重启，先用原入口验证，再决定要处理的缓存范围。[Gradle 上游同类问题](https://github.com/gradle/gradle/issues/28974)

## 模拟器与 Windows 冻结

**表现与影响。** Device Manager 可能提示 Emulator 版本不受支持或建议迁移到 Windows 虚拟机监控程序平台（WHPX）。模拟器单独退出与 Windows 画面、鼠标一起冻结需要分别排查。整机冻结会中断 IDE、Gradle 和设备测试。

**排查与修正。**

1. 按 IDE 提示的最低版本核对 Emulator 组件。分别检查 Emulator 程序版本和 AVD 的系统镜像 API。
2. 整机冻结时，用 Windows System 日志的 `Kernel-Power 41` 和 `6008` 对齐重启时间，核对蓝屏转储、WHEA、存储和显卡事件。事件 41 记录异常关机。缺少蓝屏错误码或其他佐证时，保留根因未确定的结论。比较模拟器日志和故障报告的时间，确认事件在冻结前还是重启后。
3. 用实际 SDK 下的 `emulator.exe -accel-check` 确认加速器。反复冻结时，先用 USB 真机对照。恢复模拟器测试时优先验证 Google 推荐的 WHPX，先只改变加速器。如果 Windows 功能已启用但 Hypervisor 未运行，可在管理员终端查询 `bcdedit /enum "{current}"`。当 `hypervisorlaunchtype` 明确为 `Off`，由获授权的人改为 `Auto` 后重启。若 WHPX 上仍有图形问题，再单独用 Software 图形模式对照。[模拟器加速指南](https://developer.android.com/studio/run/emulator-acceleration) · [微软事件 41 说明](https://learn.microsoft.com/en-us/troubleshoot/windows-client/performance/event-id-41-restart)

**验证与预防。** 重启后确认 `-accel-check` 显示 WHPX 可用，再以单台 AVD 验证原触发操作。记录 AVD、加速器和图形模式。短时通过后继续保留原冻结原因待确认的结论。

## USB 真机调试

**表现与影响。** Android Studio 只列出模拟器，或 ADB 列表为空、显示 `unauthorized`，此时无法向该手机部署或附加调试器。

**排查与修正。** 使用当前 SDK 的 `adb devices -l`。列表为空时，确认手机已解锁并启用 USB 调试，再核对数据线、端口和 Windows ADB 驱动。显示 `unauthorized` 时，由手机使用者确认 RSA 授权。显示 `device` 后，使用 Android Studio 的 `Ctrl+Shift+A` 搜索 `Attach Debugger to Android Process`，选择手机上的 `org.suixing.app`。命令行安装使用 `adb -s <设备ID> install -r <调试APK>` 保留应用数据。签名冲突时先确认安装来源和数据保留方式。[Android 真机调试指南](https://developer.android.com/studio/run/device)

**验证与预防。** 分别确认目标设备在线、APK 安装、主界面启动和调试器附加。IDE 里的断点需以实际命中验证。Windows JDB 通过 ADB 的本地 JDWP 转发测试时，使用 `SocketAttach`，验证后移除转发。
