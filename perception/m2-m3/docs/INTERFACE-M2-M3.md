# M2/M3 接口冻结记录 v1.0

适用范围：队友 A 交付的语义（M2）与风险融合（M3）首版。冻结日期 2026-11-21，对应 `suixing_risk 0.3.0`。

本文件是 A 与队长之间的唯一接口依据。任何字段、话题或语义变化都必须先改这里，再改代码。

## 1. 语言边界

| 层 | 语言 | 依赖 | 约束 |
|---|---|---|---|
| 算法核心 `geometry` / `freespace` / `perception` / `protocol` / `tracker` | Python 3 | numpy，无 ROS | 二期整体移植 C++17，只替换适配层 |
| ROS 2 适配 `ros_node` / `semantic_ros` | Python 3 | rclpy，可选 cv2/onnxruntime/vision_msgs | 只做消息转换、TF、参数和诊断，不放算法 |
| 线协议 `protocol` | Python 3 | 仅标准库 | 与 C 结构体逐字节对应，见线格式文档 |

冻结结论：**首版 Python，接口按 C++ 可移植设计**。核心模块禁止 `import rclpy`，保证移植时不需要重写逻辑。总纲第 6 节要求的 C++17 设备侧属于二期，队长已知悉并同意先交 Python 版。

## 2. 话题与消息

| 话题 | 类型 | 方向 | QoS | 说明 |
|---|---|---|---|---|
| `/d6/scan` | `sensor_msgs/LaserScan` | 输入 | SensorData | 低位扫描，`frame_id` 由 TF 转到 `base_link` |
| `/stereo/left/image_raw`、`/stereo/right/image_raw` | `sensor_msgs/Image` | 输入 | SensorData | 校正后灰度/彩色，必须与 `camera_info` 同 stamp |
| `/stereo/{left,right}/camera_info` | `sensor_msgs/CameraInfo` | 输入 | SensorData | 用 `P` 矩阵取焦距、主点和基线 |
| `/odom` | `nav_msgs/Odometry` | 输入 | 默认 | 只取 `twist.linear.x` 作为车速；缺失时 TTC 为 `null` |
| `/tf`、`/tf_static` | `tf2_msgs/TFMessage` | 输入 | 默认 | 必须有 `base_link` |
| `/suixing/detections_2d` | `vision_msgs/Detection2DArray` | 输出（M2 正式） | SensorData | 坐标仍为图像像素 |
| `/suixing/detection_model` | `std_msgs/String` | 输出 | Transient Local | 模型版本，`{"model_version": "..."}` |
| `/suixing/detections` | `std_msgs/String` | 输出（调试） | 默认 | 兼容 v0.2 的 JSON，不作为对接依据 |
| `/suixing/scene_objects` | `std_msgs/String` | 输出（调试） | 默认 | 语义与双目关联后的 `base_link` 位置证据 |
| `/suixing/risk_summary` | `std_msgs/String` | 输出（调试） | 默认 | 人类可读 JSON |
| `/suixing/risk_frame` | `std_msgs/UInt8MultiArray` | 输出（可选） | 默认 | 64 字节定长帧，队长桥接到 RPMsg |

`Detection2DArray` 字段约定：

- `detections[i].header` = 源图像 `header`，供融合按 stamp 配对；不做时间插值。
- `detections[i].id` = 跟踪 ID 的十进制字符串，连续帧保持稳定，丢失超过 5 帧后回收。
- `detections[i].results[0].hypothesis.class_id` = 类别名，`score` = 置信度。
- `detections[i].bbox.center` 与 `size_x/size_y` 使用**图像像素**，不转米。
- 模型版本不重复写进每条检测，由 `/suixing/detection_model` 单独发布；`vision_msgs` 没有对应字段，硬塞会破坏标准语义。

风险节点参数 `semantic_association:=true` 时同时订阅两种检测消息，优先使用 `Detection2DArray`；`vision_msgs` 未安装时退回 JSON 并打警告。

## 3. 融合契约

1. **语义只能增加风险，不能放行。** 关联对象按类别半径（person 0.30、bicycle 0.40、motorcycle 0.45、car 0.90、truck 1.10、bus 1.20 m）作为额外障碍物加入扫掠；不参与覆盖判定，不参与 `CLEAR` 的证明。
2. 置信度低于 0.35、位置非有限值、`x<=0` 或高度不在 `[0, 1.6] m` 的对象直接丢弃。
3. 语义必须与双目同帧（同 `stamp`、同 `frame_id`、图像尺寸一致）才使用，否则只发布场景证据、不进风险。
4. **覆盖判定**：三个探测点（车前 `0.30+0.07 m`，横向 `±0.30+0.07 m`）需要 D6 与双目观测均新鲜且配对成功。配对后，每个探测点至少被其中一个传感器证明"已观测且无占用"才算覆盖。算法配置 `require_stereo_coverage=True` 时，每个探测点要求双源均有覆盖。
5. `suggested_speed_limit_mps`：直行 `DANGER` 或直行未覆盖 → `0.0`（停车）；`CAUTION` → 0.30；`CLEAR` → `null`（本节点不限制）。这是建议值，不是执行指令。

方向 TTC 可选输出、板端实采验收和录包要求见 [M3 验收](M3-RISK-VALIDATION.md)。

## 4. 坐标系与时间

- `base_link`：x 向前、y 向左、z 向上，原点在后轴中心的地面投影。
- 相机与雷达只通过 TF 进入 `base_link`，代码内不写死安装位置。
- `source_age_ms` = 生成时刻 − 采样时间；`received_age_ms` = 生成时刻 − 节点收到时间（同样走 ROS 时钟，`use_sim_time` 有效）。
- 新鲜度一律以采样时间 + 设备有效期判断；接收时间只用于诊断，不能延长有效期。

## 5. 分工

| 内容 | 负责人 |
|---|---|
| M2 消息语义、跟踪 ID、模型版本发布 | A |
| `RiskSummary` 字段语义与 64 字节编码器 | A |
| RPMsg 传输、CPU3 侧解码与 CRC 校验、失效处理 | 队长 |
| 回放断言与验收脚本维护 | B |
| 制动执行与车况回读 | 队长 |

## 6. 二期 C++ 移植清单

按依赖从少到多：`protocol.py`（纯标准库，可直接对照 C 结构体）→ `freespace.py` / `geometry.py`（numpy 向量化为 Eigen）→ `perception.py`（SAD 换 SGBM）→ TF/ROS 适配层（保持话题不变）。话题、消息和线格式不随语言变化。

## 7. 与总纲的已知偏离

| 总纲要求 | 现状 | 处理 |
|---|---|---|
| C++17 负责设备和融合 | 首版 Python | 二期移植，接口已隔离 |
| `vision_msgs` 复用标准消息 | 已完成 | 见第 2 节 |
| 语义提高风险先验 | 已完成（只升级） | 见第 3 节 |
| 定长风险帧 + CRC | 已完成 | 见 `RISKSUMMARY-WIRE.md` |
| 实车双目自由空间 | 已改为真实双目射线证据 | 仍需实采标定验证 |
