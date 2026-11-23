#!/usr/bin/env bash
set -eo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
logs="$root/results/vision-ros"
mkdir -p "$logs"
source /opt/ros/humble/setup.bash
export ROS_LOCALHOST_ONLY=1 ROS_DOMAIN_ID=90 PYTHONUNBUFFERED=1
export PYTHONPATH="$root/.vision-ros-packages${PYTHONPATH:+:$PYTHONPATH}"
python3 -c 'import cv2, onnxruntime'
cd "$root/ros_ws"
colcon build --packages-select suixing_risk 2>&1 | tee "$logs/colcon.log"
source install/setup.bash
node="$(ros2 pkg prefix suixing_risk)/lib/suixing_risk/semantic_node"
"$node" --ros-args -p "model_path:=$root/inputs/yolo/yolov8n.onnx" \
  -p image_topic:=/suixing/vision_fixture/image -p publish_annotated:=true > "$logs/node.log" 2>&1 &
node_pid=$!
cleanup() {
  kill -INT "$node_pid" 2>/dev/null || true
  sleep 0.5
  kill -KILL "$node_pid" 2>/dev/null || true
  wait "$node_pid" 2>/dev/null || true
}
trap cleanup EXIT
python3 "$root/check_vision_ros.py" "$root/inputs/yolo/bus.jpg" "$logs/detections.json" 2>&1 | tee "$logs/check.log"
