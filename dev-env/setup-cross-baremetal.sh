#!/usr/bin/env bash
set -euo pipefail
name=arm-gnu-toolchain-13.3.rel1-x86_64-aarch64-none-elf
mkdir -p "$HOME/opt" "$HOME/.cache/suixing"
cd "$HOME/.cache/suixing"
digest=7fedf894040580b1db747d06ac5d4263c46e591ffe7695656d1da5accb00a159
if ! echo "$digest  $name.tar.xz" | sha256sum --check --status; then
  curl -fLsS --retry 2 --connect-timeout 20 --speed-time 45 --speed-limit 4096 --max-time 1800 -C - -o "$name.tar.xz" "https://developer.arm.com/-/media/Files/downloads/gnu/13.3.rel1/binrel/$name.tar.xz"
fi
echo "$digest  $name.tar.xz" | sha256sum --check
tar -xJf "$name.tar.xz" -C "$HOME/opt"
if [[ ! -e "$HOME/opt/arm-gcc" ]]; then
  ln -s "$name" "$HOME/opt/arm-gcc"
fi
"$HOME/opt/arm-gcc/bin/aarch64-none-elf-gcc" --version
