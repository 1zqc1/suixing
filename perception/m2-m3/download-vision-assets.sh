#!/usr/bin/env bash
set -eo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
dir="$root/inputs/yolo"
mkdir -p "$dir"

asset() {
  local name="$1" sha="$2" url="$3" temp
  if [[ -f "$dir/$name" ]]; then
    printf '%s  %s\n' "$sha" "$dir/$name" | sha256sum -c -
    return
  fi
  temp=$(mktemp "$dir/.$name.XXXXXX")
  if curl --fail --location --silent --show-error --retry 2 --max-time 180 "$url" --output "$temp" &&
     printf '%s  %s\n' "$sha" "$temp" | sha256sum -c -; then
    mv -- "$temp" "$dir/$name"
  else
    rm -f -- "$temp"
    return 1
  fi
}

asset yolov8n.onnx b2bc52f40e8e1c532427d5bde3575a5d5b571b739fab2c6df443733ed1589cbd \
  https://github.com/ultralytics/assets/releases/download/v8.4.0/yolov8n.onnx
asset bus.jpg c02019c4979c191eb739ddd944445ef408dad5679acab6fd520ef9d434bfbc63 \
  https://raw.githubusercontent.com/ultralytics/ultralytics/v8.3.0/ultralytics/assets/bus.jpg
