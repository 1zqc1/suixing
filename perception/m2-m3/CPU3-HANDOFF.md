# 随行 v0.7 · CPU3 感知与风险交接

## 启动感知与风险

使用 ROS 2 Humble，先启动现有 D6、校准后的双目、传感器 TF 和里程计发布者。确认 `/d6/scan`、`/stereo/{left,right}/{image_raw,camera_info}` 与 `/odom` 都在相同时间域。启动入口只启动 YOLOv8 和风险节点，默认发布 JSON 和 64 字节二进制风险帧。

```bash
source /opt/ros/humble/setup.bash
colcon build --base-paths ros_ws/src --build-base ros_ws/build --install-base ros_ws/install
source ros_ws/install/local_setup.bash
ros2 launch suixing_risk perception_risk.launch.py model_path:="$PWD/inputs/yolo/yolov8n.onnx"
```

实车运动采用两轮差速、使用者发起和 CPU3 裁决许可。车端适配器需把 CPU3/STM32 已验证的反馈映射到 [整车差速接口](VEHICLE.md)。

## CPU3 接收与台架联调

1. 在队长的 CPU3 固件中接入 `cpu3/risk_rx.c` 和 `risk_rx.h`。先通过原有 32 字节台架自测，然后在 CPU3 风险接收入口加入 64 字节分支。RPMsg 回调按原始数据和长度调用 `sx_decode`。Linux 发送的是 ROS 话题中的 64 个数据字节。
2. CPU3 要有经过验证的 Linux ROS 时钟映射，才能判断排队迟到帧。把转换后的当前纳秒传入解码器，并独立使用 CPU3 单调计时器记录有效帧的接收期限。时钟未对齐时仍可验 CRC 和字段，`SX_STALE` 不得提供有效风险证据。期限用严格小于，恰好到期撤销。CPU3 对会话、序号和接收看门狗做校验，重复或倒序帧不能续期。CPU3 还需要结合实际方向风险、用户发起动作和底盘其他许可逻辑作最后裁决。C 参考实现只解码单帧。
3. 在电机输出隔离的台架上，将 `fixtures/` 中三组 `risk.bin` 逐一送到 CPU3，记录接收长度、CRC、三方向状态和原因。用正常帧分别在接收期限前一纳秒和正好到期时验收，再停止发送确认本地看门狗撤权。
4. 若队长确认 Linux 端提供的是 RPMsg 字符设备，可另启下列转发器。设备编号以团队固件和 BSP 配置为准。已有转发进程时由其发送这些帧，避免同一端点的多写入者。

```bash
ros2 run suixing_risk rpmsg_risk --ros-args -p device:=/dev/rpmsgN
```

本地对应关系：

| 报文 | ROS JSON | 二进制 |
|---|---|---|
| 正常，采样后 20 ms | 三方向 CLEAR，有效期 120 ms | 64 字节，序号 1 |
| 恰好到期，采样后 140 ms | 三方向 UNKNOWN，建议零速 | 64 字节，采样时间 0，序号 2 |
| 两路断流 | 三方向 UNKNOWN，建议零速 | 64 字节，采样时间 0，序号 3 |

每组都包含固定输入、实际 ROS 发布回调捕获的 `expected.json`、`risk.bin` 和 `risk.hex`。可交由队长和 B 使用同一组输入独立核对。

## 复验

```bash
export PYTHONPATH="$PWD/ros_ws/src/suixing_risk"
python3 -m unittest discover -s tests -v
python3 verify_cpu3_ros.py
cc -std=c11 -Wall -Wextra -Werror cpu3/risk_rx.c cpu3/test_risk_rx.c -o /tmp/suixing-risk-test
/tmp/suixing-risk-test
```

原始 Humble 日志在 `evidence/`。ROS 报文验收通过真实节点的发布回调捕获，当前容器限制 DDS UDP，跨进程通信和 CPU3 端点收包待实板复验。重建的 v0.6 快照提交和 v0.7 源码提交在 `evidence/SOURCE-REVISIONS.txt`。

## A 的 M1 原录包验收

关闭 YOLO，风险节点内部继续运行 D6 和双目几何感知：

```bash
ros2 launch suixing_risk perception_risk.launch.py enable_yolo:=false use_sim_time:=true
```

用独立 ROS 域运行下列确定性验收。脚本自己启动风险节点与录包驱动，无需同时运行上述 launch。需要 ROS 2 Humble、NumPy、OpenCV 和包的 ROS 依赖。它按数据库记录顺序重放原始 11 条 CDR 消息，从 ROS 话题订阅 JSON 与 64 字节原始载荷。在最新采样后 40 ms、100 ms 和 150 ms 各导出一组。100 ms 是两路共同的精确到期点，之后停止输入，继续推进仿真时钟。

```bash
source /opt/ros/humble/setup.bash
export PYTHONPATH="$PWD/ros_ws/src/suixing_risk${PYTHONPATH:+:$PYTHONPATH}"
export ROS_LOCALHOST_ONLY=1 ROS_DOMAIN_ID=93
mkdir -p m1-capture
set -o pipefail
python3 verify_m1_topics.py --output m1-capture 2>&1 | tee m1-capture/replay.log
```

原录包没有里程计且覆盖有限，新鲜阶段实际结果仍是三向 UNKNOWN，双路均有效且对齐，剩余有效期 60 ms。到期与持续断流时双路均无效、采样时间和有效期为空、建议限速为零，编码继续以同一会话发布更新的序号和生成时刻。两种失效场景在线格式 v1 均归为 `reason=1`。这些帧用于收包和解码对照，真机回执由队长的台架记录提供。
