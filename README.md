# suixing
飞腾参赛

随行项目的团队协作仓库。首批提交保存比赛总纲、三人分工、已验收的工具链基线和最小验证工程。

| 内容 | 位置 |
|---|---|
| 项目范围、模块边界与比赛阶段 | [双赛总纲](docs/随行-双赛冲击国一总纲V1-2026-11-19.md) |
| 三人任务、开发环境与联调顺序 | [三人分工方案](docs/随行-三人分工方案.md) |
| 已验收结果与复验入口 | [开发与验收基线](docs/开发与验收基线.md) |
| ESP-SR、Android 和 ROS 2 样例 | [最小验证工程](dev-env/tests/) |
| 飞腾 Linux 端 RPMsg 自测程序 | [rpmsg_echo_test.c](Phytium/phytium-inspection/tools/rpmsg/rpmsg_echo_test.c) |

日常开发从 `main` 开分支，测试通过后提交 Pull Request。交接时附上提交号、数据或模型版本、复现命令与实测结果。Humble 构建及录包回放统一在 Ubuntu 22.04 上验收。
