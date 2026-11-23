# 随行 · 队友 A · 感知与风险交接

本目录导入自队友 A 的 Git bundle，交接版本为 fff709018a8d2bfb680350a8d3534e6e26433b56。下列命令从本目录执行。YOLO 模型和公开示例图片由 `bash download-vision-assets.sh` 从上游下载并校验。内置 M1 录包为交接时的合成测试副本。

当前版本、复验和待补实车资料见 [M2/M3 开发交付](docs/M2-M3-DELIVERY.md)。

v0.5 地图规划与导航升级见 [飞腾派 V3 部署与导航](NAVIGATION.md)。下文为原 v0.3 基线说明。
CPU3 接入请使用 [v0.7 感知与风险交接](CPU3-HANDOFF.md)。

整车启动、实测标定与底盘协议见 [飞腾派 V3 实车集成](VEHICLE.md)。


2026-11-21 · 版本 0.3.0

本包接收 D6 扫描、左右图像与相机参数，经 TF 转到 `base_link`，计算双目视差、占用与自由空间，发布左/直/右三方向风险摘要。几何核心、语义增强、闭环仿真和 ROS 2 适配共用同一套逻辑。

## 0.3.0 变更

| 变更 | 解决的问题 | 入口 |
|---|---|---|
| 双目深度射线生成自由空间证据 | 真实链路永远 `UNKNOWN`，`CLEAR` 不可达 | `freespace.py`、`geometry.py` |
| 视差上限按 `fx·b/min_depth` 自适应 | 固定 24 px 导致近场 1 m 内全盲 | `perception.disparity_limit` |
| M2 冻结为 `vision_msgs/Detection2DArray` + 跟踪 ID + 模型版本 | 原来只有 JSON，没有标准消息 | `semantic_ros.py`、`tracker.py` |
| 64 字节 `RiskSummary` 定长帧 + CRC16 | 没有可上板的线格式 | `protocol.py` |
| 语义只升级风险、实现建议限速 | 语义未参与融合，限速恒空 | `geometry.summarize` |
| 46 项单测 + `run-all.sh` | 只有一次性脚本，不可回归 | `tests/`、`run-all.sh` |

接口冻结见 [M2/M3 接口](docs/INTERFACE-M2-M3.md)，线格式见 [RiskSummary 线格式](docs/RISKSUMMARY-WIRE.md)，验证范围见 [证据](docs/EVIDENCE.md)。

## 快速开始

无 ROS 2 的开发机可使用 Python 3.10 和 rosbags 离线复验。先在 Python 虚拟环境安装依赖：

```bash
python -m pip install -r requirements-vision.txt -r tools/calibration/requirements.txt rosbags==0.10.11
```

需要复验 YOLO 时先运行 `bash download-vision-assets.sh`。随后运行：

```bash
bash run-all.sh
```

单跑交接包验收：

```bash
export PYTHONPATH=ros_ws/src/suixing_risk
python check_m1.py inputs/m1-handoff-v0.1 --output results/v0.3/acceptance.json
```

Ubuntu 22.04 + ROS 2 Humble：

```bash
bash run-jammy.sh
```

## 话题

| 话题 | 类型 | 说明 |
|---|---|---|
| `/suixing/detections_2d` | `vision_msgs/Detection2DArray` | M2 正式输出，像素坐标，`id` 为跟踪号 |
| `/suixing/detection_model` | `std_msgs/String` | 模型版本，Transient Local |
| `/suixing/risk_frame` | `std_msgs/UInt8MultiArray` | 64 字节定长帧，需 `publish_wire_frame:=true` |
| `/suixing/risk_summary` | `std_msgs/String` | 调试 JSON |
| `/suixing/detections` | `std_msgs/String` | 兼容调试 JSON |
| `/suixing/scene_objects` | `std_msgs/String` | 语义与双目关联证据 |

参数：`semantic_association`（默认 false）、`min_depth_m`（0.25）、`max_disparity`（0 表示自适应）、`require_stereo_coverage`（默认 false，单源可证明覆盖）、`publish_wire_frame`。

## 语义与避障

`semantic_node` 默认订阅 `/stereo/left/image_raw`，用官方 YOLOv8n ONNX 在 CPU 推理，输出标准检测消息与可选框图。开启风险节点的 `semantic_association` 后，按相同采样时间和图像尺寸关联双目；只有框内有足够一致视差点才输出 `base_link` 位置。

语义只做加法：按类别半径作为额外障碍加入扫掠，**从不放行**。置信度低于 0.35 或位置非法直接丢弃。

`simulate_avoidance.py` 在数值仿真中驱动车体，每步重算传感器观测，只用原风险核心裁决。地面真值只用于计算净距指标。

## 已验证结果

| 用例 | 结果 |
|---|---|
| 交接包校验 | SHA-256、列结构、3 行 D6、2 对图像、3 份车况 |
| 录包回放 | 6 个话题、11 条消息，含 `/tf_static` |
| D6 新鲜度 | 20 ms 接受 / 30 ms 接受且缺测 / 200 ms 拒绝 |
| 双目 | 中位视差 4 px，中位深度 1.2 m |
| 几何仿真 | 空路 `CLEAR`、横穿 `DANGER`、断流 `UNKNOWN`、近地障碍 `DANGER`、语义升级 `DANGER` |
| 单元测试 | 46 项通过 |
| 线协议 | 往返一致，CRC 错误被拒 |

运行离线验收后，结果生成在本地的 `results/v0.3/acceptance.json`。

## 已知边界

- 未在 ROS 2 运行时执行，`rclpy`、`vision_msgs` 路径只做了语法编译。
- 未下载模型、未装 cv2/onnxruntime，YOLO 证据沿用 0.2.0。
- 实车双目标定、自由空间扣除、端到端时延和板端性能均未验证。
- `TTC` 只在有车速且有 D6 轨迹时输出；无速度真值时为 `null`，区间是算法步进结果，不是精度指标。
- RPMsg/CPU3 解码由队长实现，本包只提供字节串与 C 结构体。

## 数据与出处

原样本版本 `m1-handoff-v0.1`，基线提交 `b0d17fce44f967be418c7583fb03186d3b44c9e2`，以包内 `SHA256SUMS` 为准。模型与图片出处见 [视觉资源](inputs/yolo/SOURCES.md)。上游接口参考 [LaserScan](https://github.com/ros2/common_interfaces/blob/humble/sensor_msgs/msg/LaserScan.msg)、[Image](https://github.com/ros2/common_interfaces/blob/humble/sensor_msgs/msg/Image.msg)、[Humble rosbag2](https://github.com/ros2/rosbag2/tree/humble)。

## 给队长和 B

- 队长：先按 [接口文档](docs/INTERFACE-M2-M3.md) 对齐话题与字段，再用 [线格式](docs/RISKSUMMARY-WIRE.md) 实现 RPMsg 编解码；`valid_ms` 过期必须撤权。
- B：用 `run-all.sh` 复跑固定样本；断言在 `tests/`，新增场景直接加用例。
