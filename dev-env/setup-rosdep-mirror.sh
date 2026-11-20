#!/usr/bin/env bash
set -euo pipefail

mirror=https://mirrors.ustc.edu.cn/rosdistro
temp_list=$(mktemp)
trap 'rm -f -- "$temp_list"' EXIT
curl -4fsSL --retry 2 --connect-timeout 10 --max-time 30 \
  -o "$temp_list" "$mirror/rosdep/sources.list.d/20-default.list"
grep -Eq '^yaml https?://[^[:space:]]+/rosdep/base\.yaml$' "$temp_list"
sed -i 's#https://raw.githubusercontent.com/ros/rosdistro/master#https://mirrors.ustc.edu.cn/rosdistro#g' "$temp_list"
# This Ubuntu environment targets ROS 2 Humble. The legacy ROS 1 Fuerte source
# also requests a hardcoded GitHub file and is unnecessary here.
sed -i '/^gbpdistro[[:space:]]/d' "$temp_list"

install -d -m 755 /etc/ros/rosdep/sources.list.d
install -m 644 "$temp_list" /etc/ros/rosdep/sources.list.d/20-default.list
runuser -u suixing -- env "ROSDISTRO_INDEX_URL=$mirror/index-v4.yaml" rosdep update --rosdistro humble

runuser -u suixing -- bash -c '
  setting="export ROSDISTRO_INDEX_URL=https://mirrors.ustc.edu.cn/rosdistro/index-v4.yaml"
  if ! grep -Fxq "$setting" "$HOME/.bashrc"; then
    printf "\n%s\n" "$setting" >> "$HOME/.bashrc"
  fi
'

dpkg-query -W -f='${binary:Package} ${Version}\n' \
  ros2-apt-source ros-humble-ros-base ros-humble-rosbag2 \
  python3-colcon-common-extensions python3-rosdep cmake ninja-build libopencv-dev
printf 'HUMBLE_INSTALL_OK\n'
