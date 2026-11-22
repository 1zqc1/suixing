# Android 案例与开发工具核对记录

核对日期：2026-11-20。按用户要求，在 APP 实现之前检索 GitHub，核对来源并安装适用工具。

## 可参考的案例

| 来源 | 对随行的用途 | 采用范围 |
|---|---|---|
| [Android 官方 platform-samples/location](https://github.com/android/platform-samples/tree/main/samples/location) | 定位权限、持续定位更新、生命周期 | 参考官方行为约束；Apache-2.0；项目采用 Java LocationManager，保持现有技术选择 |
| [BaiduMapTrace](https://github.com/zhuhaoHappig/BaiduMapTrace) | 百度轨迹绘制、漂移处理的效果参考 | 该案例依赖鹰眼 AK/serviceId；本版无需云端鹰眼。仓库元数据未标识许可证，不复制其代码 |
| [YunMap](https://github.com/yeyunHZ/YunMap) | 地图接口封装、覆盖物与生命周期分离 | 参考接口边界；不引入其旧 SDK 依赖，不复制未确认许可的代码 |

百度 SDK 的依赖、隐私初始化和坐标转换以[官方 Android 文档](https://lbsyun.baidu.com/docs/android?title=androidsdk%2Fguide%2Fcreate-project%2Fandroidstudio)为准。示例仓库不作为当前 SDK 版本依据。

## 已配置 MCP

- 上游：[mobile-next/mobile-mcp](https://github.com/mobile-next/mobile-mcp)，固定 npm `@mobilenext/mobile-mcp@1.0.18`。
- 本机安装：`D:\Phytium\tools\mobile-mcp`；依赖树由该目录 `package-lock.json` 固定，安装使用 `--ignore-scripts`。
- Codex 服务名：`suixing_mobile`，通过 Node 的绝对路径和 `launch-mobile-mcp.cjs` 启动 stdio，不依赖每次下载 latest。Windows 启动器托管前台 mobilecli 守护进程，避免自动脱离进程在当前宿主环境退出；已实际验证初始化和设备发现，连接关闭时清理自己启动的进程。
- SDK：`D:\Android\SDK`；MCP 状态目录放在工具目录；设置上游支持的 `MOBILEMCP_DISABLE_TELEMETRY=1`。
- Codex 只启用 24 项本地测试工具，涵盖设备列表、界面读取、点击、安装、日志、位置注入与限时录屏。云设备登录和分配工具未启用。
- Codex 配置修改前已在用户 `.codex` 私有目录内备份；其他 MCP 配置保留。
- 实测：JSON-RPC 初始化成功，返回 server `mobile-mcp 1.0.18`、35 项上游工具；发现在线 `AndroidReady_API_34`；成功读取 Android 界面元素及前台 `check.readiness.MainActivity`。
- 原始验证记录：`D:\Phytium\work\tooling-audit\mobile-mcp-verification.json`。它只证明 MCP 与本机模拟器通信，不代表随行业务 APP 已通过验收。
- 已通过独立 stdio 客户端完成验证。修改本机配置后，在新会话中以 `codex mcp get suixing_mobile --json` 和设备列表核对服务。

配置字段参照 [Codex 官方 MCP 文档](https://developers.openai.com/codex/mcp/)。

Windows 实测/上游兼容记录：[mobile-mcp issue538](https://github.com/mobile-next/mobile-mcp/issues/538)记录了提前停止录屏、日志过滤和方向恢复问题。当前服务源码仍采用 Windows 上硬终止的 stop 路径，因此配置中停用提前停止录屏；使用明确 timeLimit 等待自然完成。日志读取不传 filter，返回后再筛选；旋转回归前记录并在结束后恢复 accelerometer_rotation 和 user_rotation。字体和网络等测试设置也保存原值，原值不存在时删除临时设置而不是写入字符串 null。

## 已安装的新 Skills

来源：[Google android/skills](https://github.com/android/skills)，固定提交 `c72942584fff970dac86ced78b367fce0c441e52`，Apache-2.0。使用 Codex 自带 skill-installer 安装，补齐上游 LICENSE.txt。

| Skill | 使用时机 |
|---|---|
| android-permissions-security | 前台定位、精确/大致位置、拒绝与永久拒绝、组件导出审查 |
| testing-setup | 分析测试层次，轨迹算法单测、SQLite/服务与模拟器业务回归 |
| edge-to-edge | API35 状态栏/导航栏安全区域；Compose 示例按原生 Views 语义适配 |
| anr-audit-and-fix | 静态检查定位回调、数据库写入等阻塞，先证明线程和阻塞再报风险 |

安装目录为用户 `.codex\skills` 对应名称的文件夹。下一轮对话可自动发现；当前实现可以读取已安装文件作为指引。

适用边界：首版已获确认使用 Java 原生界面、纯 Java 单元测试和设备回归；不因 Skills 中的通用 Compose/Hilt/截图框架建议扩大技术范围。仅安装与本项目相关的四项，没有批量导入无关 Skills。

## 仓库内排障 Skill

项目内的 [debugging-suixing-android](../.agents/skills/debugging-suixing-android/SKILL.md) 提供 Windows 工具链、真机调试、百度底图、系统返回和 GPS 回放的排查入口与验证方式。需要权限审查、测试设计或应用 ANR 排查时，继续参照上面的专项 Skills。

## 复核方法

1. `codex mcp get suixing_mobile --json` 检查服务配置。
2. 新会话调用 `mobile_list_available_devices`，使用返回的设备 ID；MCP 的 ID 可能是 AVD 名，不能直接假设为 adb 的 emulator-5554。
3. `mobile_list_elements_on_screen` 读取目标应用，再按当前返回的元素引用操作。
4. 核对上述 Skills 文件夹包含 SKILL.md、相关 references 和许可证。

后续问题先检索官方仓库与 GitHub Issues，再按本机日志定位；版本、权限或协议修复均保留可重现命令和验证结果。
