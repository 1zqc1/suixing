#!/usr/bin/env bash
set -eo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
bundle="$root/inputs/m1-handoff-v0.1"
logs="$root/results/jammy"
mkdir -p "$logs"

. /etc/os-release
printf 'OS: %s\nArchitecture: %s\n' "$PRETTY_NAME" "$(uname -m)" | tee "$logs/environment.log"
if [[ ! -r /opt/ros/humble/setup.bash ]]; then
  printf '%s\n' 'ROS 2 Humble is required in this guest or Jammy container.' >&2
  exit 2
fi
source /opt/ros/humble/setup.bash
export ROS_LOCALHOST_ONLY=1 ROS_DOMAIN_ID=89 PYTHONUNBUFFERED=1

cd "$root/ros_ws"
colcon build --packages-select suixing_risk 2>&1 | tee "$logs/colcon.log"
source install/setup.bash
python3 "$root/check_m1.py" "$bundle" --output "$logs/acceptance.json" 2>&1 | tee "$logs/check.log"
ros2 bag info "$bundle/mock-bag" | tee "$logs/bag-info.log"

node_pid=''
echo_pid=''
bag_pid=''
cleanup() {
  for pid in "$bag_pid" "$echo_pid" "$node_pid"; do
    if [[ -n $pid ]]; then kill -INT "$pid" 2>/dev/null || true; fi
  done
  sleep 0.5
  for pid in "$bag_pid" "$echo_pid" "$node_pid"; do
    if [[ -n $pid ]]; then
      kill -KILL "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT
node_executable="$(ros2 pkg prefix suixing_risk)/lib/suixing_risk/risk_node"
"$node_executable" --ros-args -p use_sim_time:=true > "$logs/node.log" 2>&1 &
node_pid=$!
ros2 topic echo /suixing/risk_summary std_msgs/msg/String --full-length --no-daemon > "$logs/risk-topic.log" 2>&1 &
echo_pid=$!
sleep 3
ros2 bag play "$bundle/mock-bag" --loop --rate 0.5 --clock 20 \
  --qos-profile-overrides-path "$bundle/tf-static-playback.yaml" > "$logs/bag-play.log" 2>&1 &
bag_pid=$!

for attempt in {1..20}; do
  if grep -Eq '"source_age_ms": [0-9]+(\.[0-9]+)?' "$logs/risk-topic.log" &&
     grep -q 'D6 frame accepted' "$logs/node.log" &&
     grep -q 'Stereo pair accepted.*median disparity 4.0 px' "$logs/node.log"; then
    printf '%s\n' 'PASS Humble live playback accepted D6 and stereo and published RiskSummary' | tee "$logs/ros-playback-status.log"
    exit 0
  fi
  kill -0 "$node_pid" "$bag_pid" 2>/dev/null || break
  sleep 1
done
printf '%s\n' "Live playback produced no age-stamped RiskSummary. See $logs." >&2
exit 1
