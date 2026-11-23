#!/usr/bin/env bash
# Re-run every check that does not need a ROS 2 runtime.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$root/ros_ws/src/suixing_risk${PYTHONPATH:+:$PYTHONPATH}"

python3 -m unittest discover -s "$root/tests" -v
python3 -m compileall -q "$root/ros_ws/src/suixing_risk/suixing_risk" \
  "$root/check_m1.py" "$root/check_vision.py" "$root/check_vision_ros.py"
mkdir -p "$root/results/v0.3"
python3 "$root/check_m1.py" "$root/inputs/m1-handoff-v0.1" \
  --output "$root/results/v0.3/acceptance.json"

if python3 -c "import cv2, onnxruntime" 2>/dev/null && [ -f "$root/inputs/yolo/yolov8n.onnx" ]; then
  python3 "$root/check_vision.py" "$root/inputs/yolo/yolov8n.onnx" \
    "$root/inputs/yolo/bus.jpg" --output "$root/results/v0.3/vision"
else
  echo "SKIP vision: install opencv-python-headless onnxruntime and run download-vision-assets.sh"
fi
