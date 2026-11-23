# 双目安装与标定

## 安装与共同视野

- 把相机安装在同一刚性支架，镜头朝前，左光心位于右光心左方。固定对焦、分辨率、裁剪和图像方向。记录基线、相机高度、俯角、横滚及外壳遮挡位置。支架移位或图像配置变更后复测。
- 用拉尺和已知尺寸的目标测校正后双目共同可见区域。沿左转、直行、右转的实际车体扫掠边界布点，覆盖车头近区、车体两侧、低矮目标及实际停车距离之外的障碍。对每点记录左右目是否可见、能否产生稳定视差、深度误差及 D6 是否覆盖。静态角视野只说明光学覆盖，目标必须有实测视差才计入可用范围。
- 基线和镜头选择结合最远保留距离、允许深度误差及最近可见距离。可用标定后的焦距估算 `d = fx × B / Z`。近处实际视差超过搜索上限或无法同时进入两目时会出现缺测。最大、最小有效距离均须用标尺验证。现有匹配器使用水平视差，镜头必须适用针孔与 `plumb_bob` 模型。

## 准备图像

使用不等行列数的矩形棋盘格，记录**内角点**行列数及实测单格边长（米）。用车辆计划使用的分辨率采集未校正的双目原图。棋盘完整进入两目，布置在两目公共视野的中央和各边缘，分别改变距离、俯仰和偏航。拟合至少需要 10 组成功识别、不同姿态的双目图。另留至少 3 组不同姿态或位置作独立验证。连续重复拍摄同一姿态不能代替视野覆盖。

CSV 的图像路径相对清单目录。每行应是同一次采集的原始图像对。时间戳列可省略或同时留空，工具会在报告中标明实际参与时差统计的组数。

```csv
split,left,right,left_stamp_ns,right_stamp_ns
fit,raw/left_001.png,raw/right_001.png,1700000000000000000,1700000000000500000
holdout,raw/left_031.png,raw/right_031.png,1700000003000000000,1700000003000500000
```

## 离线标定与验收

工具使用 OpenCV 的棋盘角点检测、单目内参、固定内参双目标定与水平极线校正，输出 ROS 相机校准 YAML。可在已经装有 OpenCV、NumPy 的视觉环境中补装 PyYAML，也可使用 `tools/calibration/requirements.txt` 安装离线工具依赖。以下命令的棋盘格参数仅作示例，实际使用时以测量值为准。 [OpenCV 标定接口](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html) · [ROS image_pipeline Humble 标定实现](https://github.com/ros-perception/image_pipeline/blob/humble/camera_calibration/src/camera_calibration/calibrator.py)

```bash
python3 tools/calibration/calibrate_stereo.py \
  --manifest captures/pairs.csv --out calibration/run-01 \
  --cols 9 --rows 6 --square-m 0.042
```

`report.json` 保存拟合 RMS、每组留出样本的单目重投影 RMS 与校正后对应角点垂直差 P95、基线、可用像素矩形及其远场角宽。可以用 `--max-fit-rmse-px`、`--max-holdout-rmse-px`、`--max-holdout-vertical-p95-px` 控制像素级验收，用 `--measured-baseline-m` 和 `--max-baseline-error-m` 检查基线偏差。留出误差门槛逐组应用，任一门槛未通过时只写报告并以状态 1 退出。未设门槛时，报告的通过状态为空。

`left.yaml` 和 `right.yaml` 交给相机驱动或 `camera_info_manager`。分别核对每侧 `image_raw` 与 `camera_info` 的 `frame_id`、分辨率和采集时刻。YAML 中的相机名称可以通过 `--left-name`、`--right-name` 匹配驱动。右目投影基线由 `-P[0,3] / P[0,0]` 给出，单位米。报告中的 `right_from_left` 描述同一点从左目坐标到右目坐标的换算。车身坐标系到相机光学帧的静态 TF 须单独实测。 [ROS CameraInfo](https://github.com/ros2/common_interfaces/blob/humble/sensor_msgs/msg/CameraInfo.msg) · [camera_info_manager](https://index.ros.org/p/camera_info_manager/)

运行时四条双目消息复用真实采样时间，建议用同一触发时钟。在动态场景检查两幅图、两条 `CameraInfo` 与 `/d6/scan` 的时间差分布、坏帧率及丢帧次数。现有同步器的默认双目配对上限是 5 ms，几何融合的 D6/双目证据对齐上限是 40 ms。工具默认 5 ms 的离线时差筛选只使用清单中提供的两幅图的时间戳。车端验收需另外提交四路消息和 D6 的原始时间戳。 [实车参数模板](../config/vehicle.example.yaml)

## 待实车提供的资料

- 棋盘格内角点行列数、单格实测边长、左右成对原图和时间戳、拟合与留出划分。
- 左右相机型号、镜头、分辨率、帧率、触发模式、实测基线及支架位置。三个静态 TF 须覆盖车身到左右相机光学帧、车身到 D6。
- 车体尺寸、最小转弯半径、目标速度与实测停车距离。给定希望识别的最小障碍高度和最远距离，便于确定视野验收点。
- 留出场景中有测距真值的目标和低矮障碍。保存 `image_raw`、`camera_info`、`/d6/scan`、`/odom`、`/tf` 和 `/tf_static`，包含光照、遮挡或不同路面条件。

## 合成图回归

```bash
python3 -m unittest discover -s tools/calibration -v
```

回归用已知 96 mm 基线的两目模型渲染棋盘格图，取 12 组拟合、4 组留出，校验基线、误差门槛和 ROS YAML 输出。另用 Humble 工作区的 OpenCV 4.11 运行工具，得到 96.25 mm 基线、0.062 px 双目拟合 RMS、0.041 px 留出垂直误差 P95，并由风险算法读取导出的投影矩阵。该结果是合成图的工具链验证。
