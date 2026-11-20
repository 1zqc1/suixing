#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/humble/setup.bash
export ROS_LOCALHOST_ONLY=1
export ROS_DOMAIN_ID=89
bundle="$HOME/suixing-provision"
cat > "$bundle/suixing.rviz" <<'RVIZ'
Panels:
  - Class: rviz_common/Displays
    Name: Displays
Visualization Manager:
  Class: ""
  Displays:
    - Class: rviz_default_plugins/Grid
      Enabled: true
      Name: Ground grid
      Plane Cell Count: 20
      Reference Frame: map
      Value: true
    - Class: rviz_default_plugins/TF
      Enabled: true
      Frame Timeout: 15
      Name: Suixing TF
      Show Arrows: true
      Show Axes: true
      Show Names: true
      Value: true
  Enabled: true
  Global Options:
    Background Color: 36; 41; 49
    Fixed Frame: map
    Frame Rate: 30
  Name: root
  Tools:
    - Class: rviz_default_plugins/Interact
    - Class: rviz_default_plugins/MoveCamera
  Views:
    Current:
      Class: rviz_default_plugins/Orbit
      Distance: 9
      Focal Point: {X: 0.5, Y: 0, Z: 0}
      Name: Current View
      Pitch: 0.65
      Yaw: 0.78
Window Geometry:
  Height: 700
  Width: 1050
RVIZ
ros2 run tf2_ros static_transform_publisher --x 1 --frame-id map --child-frame-id base_link > "$bundle/rviz-tf.log" 2>&1 &
tf_pid=$!
trap 'kill "$tf_pid" 2>/dev/null || true' EXIT
rviz2 -d "$bundle/suixing.rviz"
