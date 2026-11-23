# 飞腾派 V3 · M2/M3 开发交付

## 代码入口

| 部分 | 已交付 |
|---|---|
| 双目 | 默认 SAD，增加可选 OpenCV StereoSGBM。按标定参数缓存校正映射，去除校正补边中的匹配。标定 CLI 从双目棋盘图生成左右 ROS 相机标定 YAML 和留出误差报告。 [视差后端参考](https://docs.opencv.org/4.12.0/d2/d85/classcv_1_1StereoSGBM.html) · [标定操作](STEREO-CALIBRATION.md) |
| YOLOv8n | 数据集预检、微调入口、ONNX 校验、PyTorch 与实际 ONNX 推理链的逐图输出对照。默认继续使用交接包内的基线模型。 [训练与导出](YOLO-TRAINING.md) |
| M3 | JSON 输出左／直／右 TTC，同步修正里程计时效和未来时间戳处理。整车入口共享实测车身尺寸与曲率。64 字节 SXR1 v1 继续编码直行 TTC。 [风险验收](M3-RISK-VALIDATION.md) |
| 整车接口 | ROS 差速桥根据候选车体速度下发左右轮缘目标速度，从实测轮速积分里程计，按反馈和时效裁决是否请求制动。保留 Ackermann 仿真入口。 [部署与差速协议](../VEHICLE.md) |

纯感知回放可用：

```bash
ros2 launch suixing_risk perception_risk.launch.py \
  use_sim_time:=true enable_yolo:=true model_path:="$PWD/inputs/yolo/yolov8n.onnx" \
  stereo_backend:=sgbm publish_perception_diagnostics:=true
```

`stereo_backend:=sad` 可复跑历史视差路径。两种匹配器的有效区域可能不同，应以实采共同视野和 V3 上的处理时延确定采用哪种。`min_depth_m` 控制自动确定的视差搜索范围，`max_disparity_cap` 控制其上限。`risk_front_m`、`risk_back_m`、`risk_half_width_m` 和 `risk_curvature_per_m` 可配置独立 M3 启动的扫掠几何。整车入口使用已经提供的 `navigation_*` 几何参数。

打开诊断后录制 `/suixing/perception_diagnostics`。它按风险序号给出端上处理耗时、最近有效双目样本的视差像素数和有效深度像素数、深度中位数、自由栅格数，以及里程计年龄、语义年龄和 D6/双目偏差。算力不足时同时检查 `/suixing/detections` 的推理耗时、端到端年龄和持续断流次数。

## 本地复验

在 Ubuntu 22.04 / ROS 2 Humble 和项目视觉依赖环境运行：

```bash
source /opt/ros/humble/setup.bash
export PYTHONPATH="$PWD/ros_ws/src/suixing_risk${PYTHONPATH:+:$PYTHONPATH}"
export ROS_LOCALHOST_ONLY=1 ROS_DOMAIN_ID=96

python3 -m unittest discover -s tests -v
python3 -m unittest discover -s tools/calibration -v
python3 verify_m1_topics.py --output /tmp/m1-capture
python3 verify_cpu3_ros.py
python3 verify_m3_ros.py --stereo-backend sad
python3 verify_m3_ros.py --stereo-backend sgbm
```

M3 ROS 回归通过实际话题验证 D6 与 Odom 的 TTC、精确到期、未来 Odom 拒绝和差速许可撤销。ONNX 与双目融合测试用公开图片和合成的 8 px 视差，验证关联位置和到期失效。标定回归用已知基线的合成图，含成功导出和超差阻断。原 M1 录包回归和 C 解码回归用于确认接口兼容。

## 需要补齐的实车输入

| 提供什么 | 最少包含 | 用于验收 |
|---|---|---|
| 相机和标定采集 | 相机型号、镜头、分辨率、帧率、固定对焦、实测基线、高度与俯角。棋盘内角点列/行、实测格长、同一时钟的左右原图。至少 10 组有效拟合及 3 组独立留出姿态，覆盖共同视野中央及边缘 | 生成实车标定、验证极线误差与近远深度误差 |
| 车体和底盘测量 | `base_link` 到左目、右目及 D6 的刚体变换，车头/车尾距离、半宽、有效轮距、轮速单位与方向、最大轮速、最小转弯半径、目标速度和制动距离 | 设置三方向扫掠、盲区和差速约束 |
| 实采 ROS 2 录包与真值 | 同一时钟的 D6、左右原图及两条 CameraInfo、Odom、TF。保留空路、左/直/右障碍、横穿、低矮目标、遮挡和两路断流的试次时间、目标距离或位置轨迹、速度与预计受影响方向 | 测视差、覆盖、语义关联、TTC、漏警和误警 |
| YOLO 微调数据 | 车载图片或原视频、待识别类目、YOLO 标框（含确认无目标的帧），按采集路段、日期或视频划分训练、验证和独立测试 | 训练车载模型、导出和确认类别召回率与误检 |
| 导航场地和 V3 联调信息 | 场地占据地图及 YAML、起终点和测试路径、V3 的镜像和 ROS 环境、CPU3/STM32 实际命令与回执协议、RPMsg 设备/端点、时钟映射与制动反馈日志。若硬件由队长保管，需要台架联调时段 | 测地图定位、闭环避障、V3 时延、风险帧回执、撤权和制动回读 |

建议实采启用诊断后，与原始传感器一起录下面的话题。若 YOLO 关闭，可以省略检测与场景话题。

```bash
ros2 bag record -o vehicle_m3_trial \
  /d6/scan /stereo/left/image_raw /stereo/right/image_raw \
  /stereo/left/camera_info /stereo/right/camera_info /odom /tf /tf_static \
  /suixing/detections /suixing/detections_2d /suixing/detection_model \
  /suixing/scene_objects /suixing/risk_summary /suixing/risk_frame \
  /suixing/perception_diagnostics
```

保存 `ros2 bag info` 输出，核对六个传感器/里程计输入话题都收到消息，并确认 `/tf_static` 中包含传感器外参。试次真值用相同 ROS 时间戳，可将表头设为 `trial_id,stamp_ns,target_id,x_m,y_m,z_m,vehicle_speed_mps,expected_direction`，同时标注坐标系和测量方法。
