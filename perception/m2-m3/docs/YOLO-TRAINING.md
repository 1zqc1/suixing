# M2 车载 YOLOv8n 微调与 ONNX 导出

在有 PyTorch 的开发机上运行训练工具。板端用现有 ONNX Runtime 推理入口。基线仍为 `inputs/yolo/yolov8n.onnx`，新模型由部署者通过 launch 参数选择。

## 数据准备

用独立采集趟次或日期划分训练、验证和测试数据。同一视频的相邻帧留在同一个分区。保留代表性的空路图、低光、逆光、模糊、局部遮挡和低矮障碍。提供类别表、难例约定、标框规范和带采集批次的分区记录。系统对 `person`、`bicycle`、`motorcycle`、`car`、`truck` 和 `bus` 使用各自的语义几何半径。改名或新增类别时要验证关联和几何半径。 [Ultralytics 检测数据集格式](https://docs.ultralytics.com/datasets/detect/)

一个数据集目录的布局如下。

```text
vehicle_dataset/
  dataset.yaml
  images/{train,val,test}/...
  labels/{train,val,test}/...
```

```yaml
path: .
train: images/train
val: images/val
test: images/test
names:
  0: person
  1: bicycle
```

这个类别表是示例。每行框使用 `class_id cx cy width height`，坐标和值均相对于图片尺寸归一化。把 `images/` 替换为 `labels/`、后缀替换为 `.txt` 即为对应标签路径。明确无目标的图用空标签文件。预检也允许缺少标签文件并将其计入背景和缺标签两项，训练前检查这些图是否漏标。三个分区均支持本地目录，`test` 可选。预检拒绝字节完全相同的图片，并验证图像可解码、框未越界及训练集覆盖全部配置类别。相邻帧或重新编码的近似重复需要按采集批次检查。

## 运行

用独立 Python 3.10 或 3.12 环境安装目标设备适用的一对 PyTorch 和 torchvision，再安装本工具的依赖。例如 Linux x86-64 CPU 开发机可以用下面的命令。准备从可信来源取得的本地 `yolov8n.pt`，并记录来源和 SHA-256。 [PyTorch 安装指南](https://pytorch.org/get-started/locally/) · [YOLOv8 模型](https://docs.ultralytics.com/models/yolov8/)

```bash
python3 -m venv .venv-yolo-train
source .venv-yolo-train/bin/activate
python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.5.1 torchvision==0.20.1
python -m pip install -r tools/requirements-yolo-training.txt
export PYTHONPATH="$PWD/ros_ws/src/suixing_risk${PYTHONPATH:+:$PYTHONPATH}"

python tools/yolo_workflow.py audit \
  --data /path/to/vehicle_dataset/dataset.yaml --report dataset-audit.json
python tools/yolo_workflow.py train \
  --data /path/to/vehicle_dataset/dataset.yaml --checkpoint /path/to/yolov8n.pt \
  --output results/yolo-m2-train --epochs 50 --imgsz 640 --batch 8 --device cpu
python tools/yolo_workflow.py export \
  --checkpoint results/yolo-m2-train/train/weights/best.pt \
  --images /path/to/vehicle_dataset/images/test --imgsz 640 \
  --output results/yolo-m2-export
```

训练使用运行目录下的新数据入口，复制标签并为图片建立链接（无法建立链接时复制图片），以免重用原文件夹中的旧标签缓存。训练期间保持源图片版本固定。训练文件夹保存数据预检、解析后的配置、随机种子、依赖版本、输入和输出模型哈希，以及 Ultralytics 的原始训练指标与权重。训练中使用验证集。最终可在独立测试集上评估类别召回率、误检和漏检，再冻结模型。需要为类目保留可发布的最终名称并记录基准模型和数据版本。 [Ultralytics 训练文档](https://docs.ultralytics.com/modes/train/)

导出使用 CPU FP32、固定批量 1 和输入尺寸，使用原始检测输出，由项目的推理节点统一执行 NMS。先用 ONNX checker 校验图，再用生产预处理和解码器分别处理 PyTorch 与 ONNX Runtime 输出。两侧每张图的有效检测必须在同类下逐一匹配。默认框 IoU ≥ 0.99、置信度差 ≤ 0.01，样本中至少有一个匹配检测。报告记录每张图的结果和原始输出最大差值。只有通过时才在新目录生成 `model.onnx` 和 `classes.json`。 [Ultralytics 导出文档](https://docs.ultralytics.com/modes/export/)

在 V3 上用 `perception_risk.launch.py enable_yolo:=true model_path:=...` 对新模型做实采回放，记录感知耗时、漏帧、语义关联率和风险结果。训练验证、数值对照和板端回放各自有独立的验收结果。
