# 飞腾派 V3 · 随行 v0.5

v0.5 接入地图级 A* 规划。车辆在 `map` 坐标中接收目标点，规划节点在 `/map` 占据栅格上生成路径，并发布 `/suixing/global_path` 供 RViz 查看。未知区域、地图外区域、达到占据阈值的栅格均不可通行。障碍按车体外接半径、风险余量和栅格分辨率膨胀，搜索禁止斜切墙角。

局部控制沿路径选择追踪目标。每个候选前进弧线同时经过地图检查和 D6、双目、YOLOv8 风险检查。地图更新或当前位姿无法继续接入已有路径时重新规划。缺少地图、定位 TF、可行路径或新鲜传感器数据时输出零速。YOLOv8n 检测经同帧双目和 TF 转成车体坐标后参与局部风险计算。

全局 A* 使用二维栅格，车辆的前进转弯能力由局部层检查。狭窄转角、需要倒车或目标方向在车后时可能停车。实时障碍由局部层处理。全局绕路需要对应障碍进入上游发布的栅格。当前按位置判断到达，目标朝向不参与控制。

## Humble 部署

在飞腾派 V3 的 Ubuntu 22.04 环境准备 ROS 2 Humble、colcon、包内 `package.xml` 依赖及 ARM64 可用的 OpenCV 与 ONNX Runtime。先启动设备驱动、里程计和 TF，确认话题时钟一致。两幅校正图像与两份 CameraInfo 使用同一采样时间。

地图模式需要活跃的 `nav_msgs/OccupancyGrid` 地图和 `map → odom` 定位 TF，另需继续提供 `/odom`、D6、双目及传感器 TF。可使用既有 SLAM 或定位系统；静态地图模式可由下面的启动文件加载地图，定位仍由 AMCL 或已有定位节点提供。 [Humble OccupancyGrid](https://docs.ros.org/en/ros2_packages/humble/api/nav_msgs/index.html) · [Nav2 Map Server](https://api.nav2.org/nav2-humble/html/classnav2__map__server_1_1MapServer.html)

在解压目录执行：

```bash
source /opt/ros/humble/setup.bash
colcon build --base-paths ros_ws/src --build-base ros_ws/build --install-base ros_ws/install
source ros_ws/install/local_setup.bash
ros2 launch suixing_risk navigation.launch.py model_path:="$PWD/inputs/yolo/yolov8n.onnx"
```

默认速度上限 0.25 m/s、到点半径 0.15 m、扫描与双目数据有效期 100 ms、双源同步差不超过 40 ms、里程计有效期 30 ms。默认曲率 1.15 m⁻¹，车体前、后、半宽分别为 0.30、0.55、0.30 m，均为仿真假设。通过 `ros2 launch suixing_risk navigation.launch.py --show-args` 查看速度、时效、曲率和尺寸参数。实车按后轴中心的 `base_link` 测量尺寸，并按底盘执行器验证实际转弯半径和制动距离。

已有 `/map` 发布者时直接使用上述启动命令。仅有静态地图 YAML 时，先安装 Humble 的 `nav2_map_server` 与 `nav2_lifecycle_manager`，再追加 `map_yaml:=/绝对路径/场地.yaml`。从已有发布者加载地图时，`/map` 使用 Reliable / Transient Local QoS。可用 `map_topic`、`map_frame` 修改默认值。使用仿真或录包时让相关节点使用同一时钟，并按需传入 `use_sim_time:=true`。

用新鲜时间戳发送目标。例子下发 `map` 坐标内的点 (2.1, 0)，实际使用时填入地图上已知可通行的坐标。

```bash
ros2 topic pub --once /suixing/navigation_goal geometry_msgs/msg/PoseStamped \
  '{header: {stamp: now, frame_id: map}, pose: {position: {x: 2.1, y: 0.0}, orientation: {w: 1.0}}}'
ros2 topic echo /suixing/global_path --qos-durability transient_local --once
ros2 topic echo /suixing/cmd_vel_candidate
ros2 topic echo /suixing/navigation_status
ros2 service call /suixing/cancel_navigation std_srvs/srv/Trigger '{}'
```

RViz 将 Fixed Frame 设置为 `map`，添加 Map 和 Path 显示，Path 话题选 `/suixing/global_path`。启动时传 `global_planning:=false` 可使用 v0.4 的里程计目标模式，此时发送 `odom` 坐标。

## 底盘接口

- `/suixing/cmd_vel_candidate` 是 `geometry_msgs/TwistStamped`。速度是 m/s，偏航角速度是 rad/s。转弯曲率为 `angular.z / linear.x`。若底盘接口需要舵角，按实测轴距和转向标定转换。
- `/suixing/navigation_status` 是 JSON，含 `stamp_ns`、`valid_until_ns` 和动作或停车原因。底盘桥应以相同时间戳匹配指令与状态，非零指令仅在截止前有效。过期、断流、急停和底盘故障均由底盘桥撤权。默认候选话题不接电机。
- 现有 64 字节 `/suixing/risk_frame` 继续为 CPU3 提供 v0.3 风险摘要。字节布局和原先的扫掠配置保持兼容。导航候选指令与 CPU3 制动许可需通过车上已有仲裁集成。
- 若板上经常观察到 `expired_during_compute`，记录端到端时延和匹配率。尤其检查 YOLO 检测返回时对应双目帧是否仍新鲜，阈值按实测时延和制动预算确定。

## 回归

```bash
export PYTHONPATH="$PWD/ros_ws/src/suixing_risk"
python3 -m unittest discover -s tests -v
```

全局规划回归覆盖地图墙体绕行、未知区域与无解目标、旋转地图原点、地图轨迹拒绝和闭环到点。闭环使用合成传感器和理想运动模型。实车地图、定位精度、跨进程通信、板端实时性和 CPU3 联调仍需在飞腾派 V3 上验收。
