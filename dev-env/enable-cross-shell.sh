#!/usr/bin/env bash
set -euo pipefail
test -x "$HOME/opt/arm-gcc/bin/aarch64-none-elf-gcc"
entry='export AARCH64_CROSS_PATH="$HOME/opt/arm-gcc"'
path_line='case ":$PATH:" in *":$AARCH64_CROSS_PATH/bin:"*) ;; *) export PATH="$AARCH64_CROSS_PATH/bin:$PATH" ;; esac'
for line in "$entry" "$path_line"; do
  if ! grep -Fxq "$line" "$HOME/.bashrc"; then printf '\n%s\n' "$line" >> "$HOME/.bashrc"; fi
done
bash -ic 'command -v aarch64-none-elf-gcc && aarch64-none-elf-gcc -dumpmachine && aarch64-linux-gnu-gcc -dumpmachine'
