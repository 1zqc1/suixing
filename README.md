# 随行 · 飞腾平台辅助出行

随行面向视障人士推行辅助。操作者主导推行与转向，系统在授权条件下提供有限助力，并在危险时请求制动和本地提示。Android 应用独立记录手机轨迹，并提供模拟车况的只读预览。

| 从这里开始 | 内容 |
|---|---|
| [三人分工与模块边界](docs/随行-三人分工方案.md) | 队长、A、B 的任务、接口责任和联调通过条件 |
| [开发环境与安装](docs/开发环境与安装.md) | Windows、Ubuntu、板端及各工具的版本和配置 |
| [开发与验收基线](docs/开发与验收基线.md) | 可复现项目、已取得的证据与待验收项 |
| [随行 Android 应用](android/suixing-app/README.md) | Android 16、百度地图、GPS 与模拟轨迹、本地回放、只读车况 |
| [队友 A · M2/M3 感知与风险交接](perception/m2-m3/README.md) | 双目标定、YOLO、ROS 2 风险融合、CPU3 接口与复验 |
| [M1 v0.1 合成交接包](samples/m1-handoff-v0.1/README.md) | D6、双目、TF、ROS 2 录包、风险摘要和车况接口样例 |
| [V4 两驱概念装配](docs/rover-v1-20261116/cad-v4-two-drive/README.md) · [辅助出行回放](docs/rover-v1-20261116/assist/README.md) | 概念 STEP、几何检查、融合与运动监督桌面原型 |
| [双赛总纲](docs/随行-双赛冲击国一总纲V1-2026-11-19.md) | 系统目标、安全边界、里程碑和比赛材料 |
| [开发环境验证工程](dev-env/) · [RPMsg 回环程序](Phytium/phytium-inspection/tools/rpmsg/rpmsg_echo_test.c) | ROS 2、交叉编译、ESP-SR、YOLO、最小 Android 验证入口 |

从 `main` 开分支开发，经验证后提 Pull Request。交接记录附 Git 提交、环境、数据或模型版本及哈希、复现命令、预期和实测。正式 Humble 构建与录包复验统一使用 Ubuntu 22.04。百度 AK、签名私钥、原始真机位置和设备私有日志保存在团队授权的本地环境。
