# YOLOv8 验收资源

| 文件 | 来源及 SHA-256 |
|---|---|
| `yolov8n.onnx` | `b2bc52f40e8e1c532427d5bde3575a5d5b571b739fab2c6df443733ed1589cbd` · [Ultralytics Assets v8.4.0](https://github.com/ultralytics/assets/releases/download/v8.4.0/yolov8n.onnx) |
| `bus.jpg` | `c02019c4979c191eb739ddd944445ef408dad5679acab6fd520ef9d434bfbc63` · [Ultralytics v8.3.0 公开样例](https://raw.githubusercontent.com/ultralytics/ultralytics/v8.3.0/ultralytics/assets/bus.jpg) |

项目根目录的 `download-vision-assets.sh` 会下载缺失文件并验证 SHA-256。`run-vision-sim.sh` 会调用该脚本。模型来自上游已导出的 ONNX，CPU 推理依赖见项目根目录的 `requirements-vision.txt`。团队提交或发布模型时使用上游对应授权条款。 [YOLOv8 文档](https://docs.ultralytics.com/models/yolov8/) · [Ultralytics 许可](https://www.ultralytics.com/license)
