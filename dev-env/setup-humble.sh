#!/usr/bin/env bash
set -euo pipefail

source /etc/os-release
if [[ "$VERSION_CODENAME" != jammy || "$(dpkg --print-architecture)" != amd64 ]]; then
  printf 'Expected the dedicated Ubuntu Jammy x86_64 environment.\n' >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
network_options=(-o Acquire::Retries=3 -o Acquire::ForceIPv4=true -o Acquire::http::Timeout=25 -o Acquire::https::Timeout=25)
apt_workspace=$(mktemp -d)
mkdir "$apt_workspace/sources"
trap 'rm -f -- "$apt_workspace/source.deb" "$apt_workspace/ubuntu.list" "$apt_workspace/sources/ros2.sources"; rmdir "$apt_workspace/sources" "$apt_workspace"' EXIT
source_options=()

if [[ "${1:-}" == --temporary-mirror ]]; then
  sed -E 's#http://(archive|security)\.ubuntu\.com/ubuntu/#https://mirrors.ustc.edu.cn/ubuntu/#g' \
    /etc/apt/sources.list > "$apt_workspace/ubuntu.list"
  source_options=(-o "Dir::Etc::sourcelist=$apt_workspace/ubuntu.list" \
    -o "Dir::Etc::sourceparts=$apt_workspace/sources" -o APT::Get::List-Cleanup=false)
fi

refresh_apt() {
  apt-get "${network_options[@]}" "${source_options[@]}" \
    -o Acquire::Languages=none -o APT::Update::Error-Mode=any update
}

install_apt() {
  apt-get -y --no-remove --no-install-recommends "${network_options[@]}" "${source_options[@]}" "$@"
}

printf '\n== Developer account ==\n'
if ! id suixing >/dev/null 2>&1; then
  useradd -m -s /bin/bash suixing
fi
id suixing

printf '\n== Official ROS repository ==\n'
if ! dpkg-query -W -f='${Status}\n' ros2-apt-source 2>/dev/null | grep -Fxq 'install ok installed'; then
  release=1.3.0
  source_deb="$apt_workspace/source.deb"
  curl -fsSL --retry 3 --connect-timeout 15 --max-time 90 \
    -o "$source_deb" \
    "https://github.com/ros-infrastructure/ros-apt-source/releases/download/$release/ros2-apt-source_${release}.jammy_all.deb"
  test "$(dpkg-deb -f "$source_deb" Package)" = ros2-apt-source
  dpkg -i "$source_deb"
fi
if [[ "${1:-}" == --temporary-mirror ]]; then
  sed -E 's#^URIs: http://packages\.ros\.org/ros2/ubuntu/?$#URIs: https://mirrors.ustc.edu.cn/ros2/ubuntu/#;s/^Types: deb deb-src$/Types: deb/' \
    /etc/apt/sources.list.d/ros2.sources > "$apt_workspace/sources/ros2.sources"
fi
refresh_apt

printf '\n== Ubuntu dependencies ==\n'
install_apt --only-upgrade install systemd udev

printf '\n== Humble and native development packages ==\n'
install_apt install \
  ros-humble-ros-base ros-humble-rosbag2 \
  python3-colcon-common-extensions python3-rosdep \
  build-essential cmake ninja-build pkg-config libopencv-dev

printf '\n== rosdep setup ==\n'
if [[ ! -e /etc/ros/rosdep/sources.list.d/20-default.list ]]; then
  rosdep init
fi
runuser -l suixing -c 'rosdep update --rosdistro humble'

printf '\n== Installed versions ==\n'
dpkg-query -W -f='${binary:Package} ${Version}\n' \
  ros2-apt-source ros-humble-ros-base ros-humble-rosbag2 \
  python3-colcon-common-extensions python3-rosdep cmake ninja-build libopencv-dev
printf '\nHUMBLE_INSTALL_OK\n'
