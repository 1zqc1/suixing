#!/usr/bin/env bash
set -eo pipefail

source /opt/ros/humble/setup.bash
export ROS_LOCALHOST_ONLY=1
export ROS_DOMAIN_ID=89
export PYTHONUNBUFFERED=1

tools_dir=$(cd -- "$(dirname -- "$0")" && pwd)
workspace=$(mktemp -d "$HOME/suixing-ros2-check.XXXXXX")
printf 'Verification workspace: %s\n' "$workspace"
cd "$workspace"
mkdir src
cp -r -- "$tools_dir/tests/suixing_ros_smoke" src/

rosdep check --from-paths src --ignore-src --rosdistro humble
colcon build --executor sequential --cmake-args -GNinja
source install/setup.bash
node="$workspace/install/suixing_ros_smoke/lib/suixing_ros_smoke/message_node"

publisher_pid=
subscriber_pid=
cleanup() {
  for pid in "$publisher_pid" "$subscriber_pid"; do
    if [[ -n "$pid" ]]; then
      kill -TERM "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT

"$node" publish > publish.log 2>&1 &
publisher_pid=$!
timeout 15 "$node" subscribe > live.log 2>&1
grep -Fx 'RECEIVED SUIXING_HUMBLE_SMOKE_42' live.log
printf 'LIVE_PUB_SUB_OK\n'

record_status=0
timeout --signal=INT --kill-after=6 7 ros2 bag record --storage sqlite3 \
  --output "$workspace/suixing-bag" /suixing_smoke > record.log 2>&1 || record_status=$?
if [[ "$record_status" != 0 && "$record_status" != 124 ]]; then
  cat record.log
  exit "$record_status"
fi
kill -TERM "$publisher_pid"
wait "$publisher_pid" || true
publisher_pid=

ros2 bag info "$workspace/suixing-bag"
python3 - "$workspace/suixing-bag/metadata.yaml" <<'PY'
import sys
import yaml

with open(sys.argv[1], encoding="utf-8") as stream:
    metadata = yaml.safe_load(stream)["rosbag2_bagfile_information"]

for topic in metadata["topics_with_message_count"]:
    if topic["topic_metadata"]["name"] == "/suixing_smoke" and topic["message_count"] >= 2:
        print(f"BAG_RECORD_OK {topic['message_count']} messages")
        break
else:
    raise SystemExit("Bag does not contain the expected topic and message count")
PY

timeout 15 "$node" subscribe > replay.log 2>&1 &
subscriber_pid=$!
sleep 1
timeout 12 ros2 bag play "$workspace/suixing-bag" > play.log 2>&1
wait "$subscriber_pid"
subscriber_pid=
grep -Fx 'RECEIVED SUIXING_HUMBLE_SMOKE_42' replay.log
printf 'BAG_REPLAY_OK\n'
printf 'ROS_DISTRO=%s\n' "$ROS_DISTRO"
cmake --version | head -n 1
ninja --version
pkg-config --modversion opencv4
