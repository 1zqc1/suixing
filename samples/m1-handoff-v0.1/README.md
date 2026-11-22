# 随行 M1 首轮交接包 v0.1

面向 A 的传感输入联调、B 的只读状态回归，以及队长的 Humble 回放和风险摘要接口联调。录包、图像、时间、标定、TF 和车况均为合成数据，适用于接口验证。实采传感能力、TTC 精度、实机时延和安全闭环仍待验收。

## 先验包

解压后在包根目录运行。需要 Python 3，验证过程可离线运行。

```bash
python3 verify.py
```

Windows 可用 `py -3 verify.py`。预期输出 `PASS SHA-256, 3 D6 rows, 2 stereo pairs, 3 vehicle statuses, 2 risk cases`。版本和录包话题计数在 `manifest.json`。交接记录填写数据版本、代码提交号、运行命令、预期、实测和日志位置。

## A 的输入与预期

| 文件 | 检查项 |
|---|---|
| `sensors/d6-scan.mock.jsonl` | 第 1 条年龄 20 ms，有效。第 2 条年龄 30 ms，两处 `null` 保留原角度索引并按未知处理。第 3 条年龄 200 ms，已过期，从融合输入剔除 |
| `sensors/stereo.mock.jsonl`、`images/` | 两对 96 × 64 的灰度 PGM。按 `stamp_ns` 配对左右图，再与 D6 的前两帧对齐。每行 `payload.path` 相对于包根目录 |
| `sensors/stereo-calibration.mock.json` | 可检查左右相机参数、像素尺寸及坐标系接入。图像的合成视差为 4 px，与 D6 距离没有共同的物理真值 |

D6 和双目按来源分别维护序号，两侧图像共用双目采集会话。跨源按同一合成 ROS 采样时钟对齐。离线回归使用样本里的接收时刻或回放时钟。

## B 的输入与预期

| 文件 | 页面和回归预期 |
|---|---|
| `vehicle-status/normal.json` | 待机，两种传感器在线，无运动许可 |
| `vehicle-status/sensor-offline.json` | D6 离线，已请求制动，制动回读未知，无运动许可 |
| `vehicle-status/brake-latched.json` | 制动锁存且已有执行回读，无运动许可 |

复测时记录页面是否区分「已请求制动」和「已确认施加」。三份数据为独立场景。

## 队长在 Jammy 回放

在空闲的本地 ROS 域中运行。在另一个终端启动 RViz2 时使用相同 ROS 环境和域设置，固定坐标系选 `base_link`，添加 TF 与 `/d6/scan`。

```bash
source /opt/ros/humble/setup.bash
export ROS_LOCALHOST_ONLY=1 ROS_DOMAIN_ID=89
ros2 bag info mock-bag
ros2 bag play mock-bag --loop --rate 0.5 --clock 20 \
  --qos-profile-overrides-path tf-static-playback.yaml
```

共 6 个话题、11 条消息。两个有效期内的 D6 扫描、四条图像、四条相机参数和一条含三个变换的静态 TF。ROS 扫描中的缺测用 NaN 表示，逐束时间间隔与扫描周期保留零值。过期扫描只保留在 JSONL，供离线拒绝测试。按时间做判断的 ROS 节点应在回放时启用 `use_sim_time`。在无控车节点或执行器连接的环境中回放。

`risk-summary.mock.json` 包含一条 20 ms 的新鲜摘要和一条恰好到 100 ms 有效期的过期摘要。外层收发时刻仅属于同一个合成单调时钟的测试上下文。预期为接收新鲜风险摘要、拒绝过期摘要。接收后仍须评估摘要中的危险状态。当前文件是离线用例，RPMsg 编解码和 CPU3 行为由板端验收记录确认。

## 样本版本

仓库归档的 v0.1 来自首轮交接。合成录包、传感输入、车况和校验脚本保留交接包中的字节。两份 Markdown 已更新为仓库内路径，`SHA256SUMS` 记录此副本的校验值。`manifest.json` 的 `repository_base_commit` 表示合成包生成时的基线。生成器未随交接归档，复验直接使用本目录的固定样本。
