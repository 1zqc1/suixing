# 证据与状态 v0.3

本文件只记录**实际执行过**的验证。没有原始日志的内容一律不写成已验证。

## 1. 执行环境

| 项 | 值 |
|---|---|
| 日期 | 2026-11-21 |
| 主机 | Windows，Python 3.12 |
| 依赖 | numpy、rosbags（pip） |
| 未安装 | rclpy、cv2、onnxruntime、vision_msgs |
| 未连接 | VMware 来宾、实车、CPU3 |

## 2. 已执行

命令：

```bash
export PYTHONPATH=ros_ws/src/suixing_risk
python -m unittest discover -s tests -v
python check_m1.py inputs/m1-handoff-v0.1 --output results/v0.3/acceptance.json
python -m compileall ros_ws/src/suixing_risk/suixing_risk
```

| 检查 | 结果 |
|---|---|
| 单元测试 | 46 项全部通过（0.24 s） |
| 交接包 SHA-256 / 行数 / 列结构 | 通过 |
| rosbag2 回放 | 6 个话题、11 条消息，含 `/tf_static` |
| D6 新鲜度 | 20 ms 接受；30 ms 接受且索引 1、3 为未知；200 ms 拒绝 |
| 双目 | 两对图像，中位视差 4 px，中位深度 1.2 m |
| 几何仿真 | 5 个场景（空路、横穿、断流、近地障碍、语义升级） |
| 64 字节线帧 | 打包/解包往返一致，CRC 校验生效 |
| 语法编译 | 全部模块通过（含无法导入的 ROS 模块） |

仿真结果：

| 场景 | 左/直/右 | 限速 | 语义 |
|---|---|---|---|
| 空路 | CLEAR / CLEAR / CLEAR | `null` | 否 |
| 横穿 | DANGER / DANGER / DANGER | 0.0 | 否 |
| 断流 | UNKNOWN ×3 | 0.0 | 否 |
| 近地障碍 | DANGER ×3 | 0.0 | 否 |
| 语义升级 | DANGER ×3 | 0.0 | 是 |

原始结果：[acceptance.json](../results/v0.3/acceptance.json)。

## 3. 未执行

| 项 | 原因 | 状态 |
|---|---|---|
| `ros_node` / `semantic_ros` 实际运行 | 本机无 ROS 2 | 未运行，仅编译 |
| `vision_msgs` 发布路径 | 未安装该包 | 未运行 |
| YOLOv8 推理与检测框图 | 未装 cv2/onnxruntime，未下载模型 | 沿用 v0.2 证据 |
| 语义 → 风险的真实数据联调 | 需要带检测的录包 | 仅仿真 |
| 实车自由空间、时延、板端性能 | 无硬件 | 未验证 |
| RPMsg / CPU3 解码 | 属队长范围 | 未验证 |

## 4. 状态标记

按总纲 0.1 节：

| 内容 | 状态 |
|---|---|
| 几何核心、线协议、跟踪器、网格 | **V**（可复跑单测 + 验收） |
| M2 消息发布代码 | **P**（已实现未运行） |
| CLEAR 可达性（真实双目证据） | **V**（合成数据 + 单测），实采为 **P** |
| 语义升级 | **V**（仿真 + 单测） |
| 交接包原始数据与回放 | **C**（校验值一致） |

## 5. 对 v0.2 材料的两点更正

1. v0.2 README 声称 `results/ubuntu24`、`results/jammy` 与 `.jammy/run-in-jammy.sh` 存在，但这些文件**不在交付包内**，`A-M1-SHA256SUMS` 中也未列出。本版不再引用，除非补上原始构建与话题日志。
2. v0.2 的 `CLEAR` 只在注入仿真视野模型时成立，真实链路永远 `UNKNOWN`。v0.3 改为双目深度射线产生自由空间证据，单测 `test_real_free_space_reaches_clear` 覆盖该路径。

## 6. 复现

```bash
bash run-all.sh
```

脚本会跑单测、编译、交接包验收；检测到 cv2/onnxruntime 与模型时额外跑 YOLO。ROS 侧需在 Ubuntu 22.04 + Humble 环境执行：

```bash
colcon build --packages-select suixing_risk
ros2 run suixing_risk risk_node --ros-args -p semantic_association:=true
```

## v0.6 与 v0.7 Humble 复验

压缩包 `evidence/` 保存 v0.6 快照与 v0.7 的 Humble 原始回归日志，以及 v0.7 ROS 发布回调和主机 C 解码日志。上述旧节保留当时的基线记录。详见 [CPU3 交接](../CPU3-HANDOFF.md)。
