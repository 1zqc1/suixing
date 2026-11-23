#!/usr/bin/env bash
set -eo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
bash "$root/download-vision-assets.sh"
if [[ ! -x "$root/.vision-venv/bin/python" ]]; then
  python3 -m venv "$root/.vision-venv"
fi
python="$root/.vision-venv/bin/python"
if ! "$python" -c 'import cv2, onnxruntime, numpy' >/dev/null 2>&1; then
  PIP_CACHE_DIR="$root/.semantic-work/pip-cache" "$python" -m pip install -r "$root/requirements-vision.txt"
fi
export PYTHONPATH="$root/ros_ws/src/suixing_risk"
mkdir -p "$root/results/vision"
"$python" "$root/check_vision.py" "$root/inputs/yolo/yolov8n.onnx" "$root/inputs/yolo/bus.jpg" \
  --output "$root/results/vision" | tee "$root/results/vision/check.log"
