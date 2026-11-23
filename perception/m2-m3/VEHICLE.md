# 飞腾派 V3 实车集成

## 地图和定位

`vehicle.launch.py` 加载静态地图 YAML，启动 Nav2 Map Server、AMCL 及两个生命周期管理器。Map Server 发布 `/map`；AMCL 使用 `/d6/scan` 和 `odom → base_link`，收到初始位姿后提供 `map → odom`。使用 RViz 的 **2D Pose Estimate** 在 `map` 中标初始位姿，再发送导航目标。左右轮速反馈默认驱动本包的 `/odom` 和动态 TF。已有融合里程计时，将 `publish_wheel_odom` 设为 `false`，由原定位链提供这两个输出。AMCL 参数需结合场地图和底盘运动误差验证。 [Humble AMCL 源码](https://api.nav2.org/nav2-humble/html/amcl__node_8cpp_source.html)

## D6、双目与 YOLOv8

D6 厂商驱动发布 `sensor_msgs/LaserScan` 到 `/d6/scan`。双目驱动在 `/stereo_driver/{left,right}` 下为每次采样发布 `image_raw` 和 `camera_info`。保留采集时间戳，先在驱动层完成触发同步或时钟映射，所有采样时间须在同一 ROS 时钟域。同步器默认允许四条消息之间最多 5 ms 偏差，校验帧名、分辨率、投影矩阵和右目基线，用最早的采样时刻作为配对时间。D6 与双目保持原有 40 ms 证据对齐要求。

把实测 D6 和左右光学坐标系外参填入 `config/vehicle.example.yaml` 的副本，并由实际双目标定产生两路 CameraInfo。几何节点按 CameraInfo 进行校正，YOLOv8n 对同一左目帧推理。推理结果按采样时间回配深度，滞后的匹配结果经里程计补偿车身运动并扩大占用范围。实车启动模式要求语义匹配在有效期内；断流、帧无法回配或计算超时会停车。相机内参、双目基线和外参均须实测。

## ROS 底盘接口

实车模板选择 `drive_mode: differential`。把实际车端 ROS 适配器接到以下话题，两个话题均使用 `std_msgs/msg/String`。轮速为轮缘线速度 m/s，车辆前进时两边均为正。ROS 消息里的时间使用同一个 ROS 时钟域。航向角速度左转为正。参考 ROS 2 Control 从车体速度生成轮速、从实测轮速计算里程计的接口设计。 [ros2_control diff_drive_controller](https://control.ros.org/humble/doc/ros2_controllers/diff_drive_controller/doc/userdoc.html)

| 话题 | 方向 | JSON 字段 |
|---|---|---|
| `/suixing/chassis/feedback` | 驱动 → 桥 | `stamp_ns`（实测时间）、`left_wheel_mps`、`right_wheel_mps`、`motion_permitted`、`estop_active`、`fault`、`brake_applied` |
| `/suixing/chassis/command` | 桥 → 驱动 | `stamp_ns`、`valid_until_ns`、`left_wheel_mps`、`right_wheel_mps`、`brake` |

桥接节点匹配同时间戳的候选速度和导航状态，以实测轮距 `B` 换算左右轮目标 `v - ωB/2` 与 `v + ωB/2`。任一轮超出上限或需要反转时请求制动，以保持导航扫掠评估用的曲率。当前局部导航只规划前进弧线。里程计独立使用左右轮实测速度并输出 `odom → base_link`。配置 `drive_mode: ackermann` 可继续使用历史仿真，保留上表对应位置的 `speed_mps` 和 `steering_rad`。

上电先请求制动。使能需要新鲜、许可有效的反馈，左右轮各自接近静止，且反馈已制动。收到急停、故障、许可撤销或反馈超时时撤销使能。候选到期或越界时请求制动，制动报文的左右轮目标和有效期均为零。CPU3/STM32 适配器应把实际许可和制动反馈映射到这四个布尔字段，并在车端独立执行有效期、急停和断链看门狗。64 字节风险帧沿用现有 RPMsg 合同。当前仓库未包含实车消息到 ROS 的硬件映射。

在驱动输出隔离的台架上确认轮速方向、命令与反馈、急停和制动执行。软件使能入口如下。

```bash
ros2 service call /suixing/chassis/arm std_srvs/srv/SetBool '{data: true}'
ros2 service call /suixing/chassis/arm std_srvs/srv/SetBool '{data: false}'
```

## 启动

先安装包内 `package.xml` 所列的 Humble 依赖，准备 ARM64 上可用的 ONNX Runtime 和 OpenCV。启动厂家传感器驱动及底盘驱动后，在解压目录执行下面命令。尖括号内是实测车身参数。示例模板要求填入轮距、轮速上限和三个静态外参。车体尺寸和曲率会同时传给局部导航和风险摘要。

```bash
source /opt/ros/humble/setup.bash
colcon build --base-paths ros_ws/src --build-base ros_ws/build --install-base ros_ws/install
source ros_ws/install/local_setup.bash
ros2 launch suixing_risk vehicle.launch.py \
  map_yaml:=/绝对路径/场地.yaml model_path:="$PWD/inputs/yolo/yolov8n.onnx" \
  vehicle_params:=/绝对路径/实测参数.yaml \
  navigation_curvature_per_m:=<允许曲率> navigation_front_m:=<车体前伸量> \
  navigation_back_m:=<车体后伸量> navigation_half_width_m:=<车体半宽>
```

曲率单位为 m⁻¹，其余尺寸为米，车体坐标原点采用后轴中心。可执行曲率须满足 `atan(轴距 × 曲率) ≤ 舵角上限`。配置文件示例故意保留拒绝启动的占位值。启动后检查 `/map`、`/odom`、`/stereo/left/image_raw`、`/suixing/detections_2d`、`/suixing/chassis/command` 及两段定位 TF。

## 验证

在 Humble 环境中从源码根目录执行：

```bash
export PYTHONPATH="$PWD/ros_ws/src/suixing_risk"
python3 -m unittest discover -s tests
python3 verify_vehicle_ros.py
```

回归共 64 项。ROS 回调验证使用合成输入，覆盖双目配对、拒绝错帧、里程计发布、指令过期和急停撤权。实车地图、D6 与双目安装参数、底盘协议和制动响应需要在飞腾派 V3 与对应设备上验收。
