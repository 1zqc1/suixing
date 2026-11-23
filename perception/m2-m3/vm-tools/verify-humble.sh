#!/usr/bin/env bash
set -eo pipefail
root=/work
logs="$root/results/vm-review"
bundle="$root/inputs/m1-handoff-v0.1"
mkdir -p "$logs"
source /opt/ros/humble/setup.bash
export ROS_LOCALHOST_ONLY=1 ROS_DOMAIN_ID=92 PYTHONUNBUFFERED=1
python3 -c 'import cv2, onnxruntime; from vision_msgs.msg import Detection2DArray'
cd "$root/ros_ws"
colcon build --packages-select suixing_risk 2>&1 | tee "$logs/colcon.log"
source install/setup.bash
install_dir="$(ros2 pkg prefix suixing_risk)/lib/suixing_risk"

pids=()
cleanup() {
  for pid in "${pids[@]}"; do kill -INT "$pid" 2>/dev/null || true; done
  sleep 0.5
  for pid in "${pids[@]}"; do
    kill -KILL "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT
"$install_dir/risk_node" --ros-args -p use_sim_time:=true -p publish_wire_frame:=true \
  -p semantic_association:=true > "$logs/risk-node.log" 2>&1 &
pids+=("$!")
"$install_dir/semantic_node" --ros-args -p "model_path:=$root/inputs/yolo/yolov8n.onnx" \
  -p image_topic:=/suixing/vision_fixture/image > "$logs/semantic-node.log" 2>&1 &
pids+=("$!")
sleep 2
ros2 bag play "$bundle/mock-bag" --loop --rate 0.5 --clock 20 \
  --qos-profile-overrides-path "$bundle/tf-static-playback.yaml" > "$logs/bag-play.log" 2>&1 &
pids+=("$!")
python3 "$root/vm-tools/check-humble.py" "$root/inputs/yolo/bus.jpg" "$logs/humble-interfaces.json" \
  2>&1 | tee "$logs/humble-check.log"
