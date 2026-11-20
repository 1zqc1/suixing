#!/usr/bin/env bash
set -euo pipefail
. /etc/os-release
test "$VERSION_CODENAME" = jammy
tmp=$(mktemp -d)
trap 'rm -f "$tmp/jammy.list"; rmdir "$tmp/empty" "$tmp"' EXIT
mkdir "$tmp/empty"
sed -E 's#http://(archive|security)\.ubuntu\.com/ubuntu/#https://mirrors.ustc.edu.cn/ubuntu/#g' /etc/apt/sources.list > "$tmp/jammy.list"
opts=(-o "Dir::Etc::sourcelist=$tmp/jammy.list" -o "Dir::Etc::sourceparts=$tmp/empty" -o APT::Get::List-Cleanup=false -o Acquire::Retries=2 -o Acquire::https::Timeout=30)
export DEBIAN_FRONTEND=noninteractive
apt-get "${opts[@]}" -y --no-remove --no-install-recommends install gcc-aarch64-linux-gnu g++-aarch64-linux-gnu libc6-dev-arm64-cross make device-tree-compiler libncurses-dev bison flex dos2unix
aarch64-linux-gnu-gcc --version
