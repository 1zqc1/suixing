#!/usr/bin/env bash
set -eo pipefail
export DEBIAN_FRONTEND=noninteractive
export LC_ALL=C
source /etc/os-release
test "$VERSION_CODENAME" = jammy
test "$(dpkg --print-architecture)" = amd64
bundle=/home/suixing/suixing-provision
apt_network=(-o Acquire::Retries=3 -o Acquire::ForceIPv4=true -o Acquire::http::Timeout=25 -o Acquire::https::Timeout=25)
if ! dpkg-query -W -f='${Status}' ros2-apt-source 2>/dev/null | grep -q '^install ok installed$'; then
  test "$(dpkg-deb -f "$bundle/ros2-apt-source_1.3.0.jammy_all.deb" Package)" = ros2-apt-source
  dpkg -i "$bundle/ros2-apt-source_1.3.0.jammy_all.deb"
fi

# Mirror the signed Jammy and Humble repositories for repeatable updates from this guest.
sed -i -E 's#https?://(archive\.ubuntu\.com|[a-z]{2}\.archive\.ubuntu\.com|security\.ubuntu\.com)/ubuntu/?#https://mirrors.ustc.edu.cn/ubuntu/#g' /etc/apt/sources.list
if ! grep -Eq '^deb .+ jammy .*\buniverse\b' /etc/apt/sources.list; then
  printf '%s\n' 'deb https://mirrors.ustc.edu.cn/ubuntu/ jammy universe' \
    'deb https://mirrors.ustc.edu.cn/ubuntu/ jammy-updates universe' \
    'deb https://mirrors.ustc.edu.cn/ubuntu/ jammy-security universe' >> /etc/apt/sources.list
fi
sed -i -E 's#^URIs: http(s)?://packages\.ros\.org/ros2/ubuntu/?$#URIs: https://mirrors.ustc.edu.cn/ros2/ubuntu/#;s/^Types: deb deb-src$/Types: deb/' /etc/apt/sources.list.d/ros2.sources
apt-get "${apt_network[@]}" -o Acquire::Languages=none -o APT::Update::Error-Mode=any update

apt-get "${apt_network[@]}" -y --no-remove --no-install-recommends install \
  ubuntu-desktop-minimal open-vm-tools-desktop gnome-screenshot mesa-utils x11-utils \
  language-pack-gnome-zh-hans fonts-noto-cjk \
  python3-colcon-common-extensions python3-rosdep git build-essential \
  cmake ninja-build pkg-config libopencv-dev device-tree-compiler libncurses-dev bison flex dos2unix \
  gcc-aarch64-linux-gnu g++-aarch64-linux-gnu libc6-dev-arm64-cross \
  ros-humble-desktop ros-humble-rosbag2 ros-humble-vision-msgs ros-humble-image-transport \
  ros-humble-diagnostic-updater ros-humble-tf2-tools

# GDM/Xorg works well with SVGA and provides a stable DISPLAY during validation.
sed -i -E 's/^[#[:space:]]*WaylandEnable[[:space:]]*=.*/WaylandEnable=false/' /etc/gdm3/custom.conf
systemctl set-default graphical.target
systemctl enable --now open-vm-tools.service
systemctl enable ssh.service
printf '\nGUEST_PACKAGES_OK\n'
dpkg-query -W -f='${binary:Package} ${Version}\n' \
  ubuntu-desktop-minimal open-vm-tools-desktop ros-humble-desktop ros-humble-rviz2 \
  ros-humble-rosbag2 ros-humble-vision-msgs ros-humble-image-transport \
  ros-humble-diagnostic-updater ros-humble-tf2-tools python3-colcon-common-extensions \
  cmake ninja-build libopencv-dev gcc-aarch64-linux-gnu
