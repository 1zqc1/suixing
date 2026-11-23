#!/usr/bin/env bash
set -euo pipefail
project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
jammy="${SUIXING_JAMMY:-$HOME/suixing-a-m1-v0.1/.jammy}"
vision="$(dirname "$jammy")/.vision-ros-packages"
proot="$jammy/proot/usr/bin/proot-upstream"
test -x "$proot"
test -r "$jammy/rootfs/opt/ros/humble/setup.bash"
test -d "$vision"

exec "$proot" -0 -r "$jammy/rootfs" -b /dev -b /proc -b /sys -b /etc/resolv.conf \
  -b "$project:/work" -b "$vision:/opt/suixing-vision" -w /work \
  /usr/bin/env -i HOME=/root PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  LANG=C.UTF-8 PYTHONPATH=/opt/suixing-vision "$@"
