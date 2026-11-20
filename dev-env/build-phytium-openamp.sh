#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C
export AARCH64_CROSS_PATH="$HOME/opt/arm-gcc"
sdk="$HOME/work/phytium-free-rtos-sdk"
repo=$(cd -- "$(dirname -- "$0")/.." && pwd)
out="$repo/dev-env/phytium-build"
stage=$(mktemp -d "$HOME/work/openamp-build.XXXXXX")
mkdir -p "$out"
cd "$sdk/example/system/amp/openamp_for_linux"
linux_cc=aarch64-linux-gnu-gcc
bare_cc="$AARCH64_CROSS_PATH/bin/aarch64-none-elf-gcc"
test "$("$linux_cc" -dumpmachine)" = aarch64-linux-gnu
test "$("$bare_cc" -dumpmachine)" = aarch64-none-elf
test "$(git -C "$sdk/standalone" rev-parse HEAD)" = bb89bb6687ca404f3d3a33396c787eac3b822231
"$linux_cc" -Wall -O2 "$repo/Phytium/phytium-inspection/tools/rpmsg/rpmsg_echo_test.c" -o "$stage/rpmsg_echo_test"
{
  make config_pe2204_phytiumpi_aarch64
  make USR_BOOT_DIR="$stage" image
} > "$out/openamp-build.log" 2>&1 || { tail -45 "$out/openamp-build.log"; exit 1; }
cd "$stage"
readelf -h openamp_core0.elf | grep -Eq 'Machine: +AArch64'
readelf -h openamp_core0.elf | grep -Eq 'Entry point address: +0xb0100000'
readelf -SW openamp_core0.elf | grep -E '\.resource_table +PROGBITS'
readelf -lW rpmsg_echo_test | grep -F '/lib/ld-linux-aarch64.so.1'
{
  date -Iseconds
  git -C "$sdk" rev-parse HEAD
  git -C "$sdk/standalone" rev-parse HEAD
  "$linux_cc" --version | head -1
  aarch64-linux-gnu-g++ --version | head -1
  "$bare_cc" --version | head -1
  file rpmsg_echo_test openamp_core0.elf
  stat -c '%n %s bytes' rpmsg_echo_test openamp_core0.elf
  readelf -h openamp_core0.elf
  readelf -lW openamp_core0.elf
  readelf -SW openamp_core0.elf | grep resource_table
  readelf -x .resource_table openamp_core0.elf
  sha256sum rpmsg_echo_test openamp_core0.elf
} > verify.txt
install -m 755 rpmsg_echo_test openamp_core0.elf "$out/"
install -m 644 verify.txt "$out/"
cat verify.txt
