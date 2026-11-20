"""Verify that a built ESP32-S3 speech image fits the configured partitions."""
import hashlib
import json
import os
from pathlib import Path
import re
from struct import unpack_from
import sys

project = Path.cwd()
build = project / "build"
sys.path.insert(0, str(Path(os.environ["IDF_PATH"]) / "components" / "partition_table"))
from gen_esp32part import PartitionTable

config = set((project / "sdkconfig").read_text(encoding="utf-8").splitlines())
required = {
    'CONFIG_IDF_TARGET="esp32s3"',
    "CONFIG_ESPTOOLPY_FLASHSIZE_16MB=y",
    "CONFIG_SPIRAM=y",
    "CONFIG_SPIRAM_MODE_OCT=y",
    "CONFIG_SR_WN_WN9_HIESP=y",
    "CONFIG_SR_MN_CN_MULTINET6_QUANT=y",
}
if missing := required - config:
    raise RuntimeError(f"Missing required SDK settings: {sorted(missing)}")

table = PartitionTable.from_binary((build / "partition_table" / "partition-table.bin").read_bytes())
if max(part.offset + part.size for part in table) > 16 * 1024 * 1024:
    raise RuntimeError("Partition table exceeds 16 MiB")
partitions = {part.name: part for part in table}
flash = json.loads((build / "flasher_args.json").read_text(encoding="utf-8"))["flash_files"]
report = {}
for name, file in (("factory", "suixing_esp_sr_baseline.bin"), ("model", "srmodels/srmodels.bin")):
    entry = partitions[name]
    content = (build / file).read_bytes()
    offsets = {int(address, 0): Path(path).as_posix() for address, path in flash.items()}
    if offsets.get(entry.offset) != file or len(content) > entry.size:
        raise RuntimeError(f"{name} image is too large or mapped to an unexpected offset")
    report[name] = dict(offset=hex(entry.offset), partition_bytes=entry.size,
                        image_bytes=len(content), sha256=hashlib.sha256(content).hexdigest())

models = (build / "srmodels" / "srmodels.bin").read_bytes()
model_count = unpack_from("<I", models)[0]
if not 1 <= model_count <= 64:
    raise RuntimeError("Invalid number of bundled speech models")
position = 4
names = []
for _ in range(model_count):
    name, files = unpack_from("<32sI", models, position)
    names.append(name.rstrip(b"\x00").decode("ascii"))
    position += 36
    for _ in range(files):
        _, offset, length = unpack_from("<32sII", models, position)
        if offset + length > len(models):
            raise RuntimeError(f"Model data extends beyond the binary: {names[-1]}")
        position += 40
if not {"wn9_hiesp", "mn6_cn"}.issubset(names):
    raise RuntimeError(f"Expected WakeNet and MultiNet models, found {names}")
report["models"] = names
compiler_commands = (build / "compile_commands.json").read_text(encoding="utf-8")
idf_version = re.search(r"IDF_VER=[^v ]*(v[\w.+-]+)", compiler_commands)
if not idf_version:
    raise RuntimeError("ESP-IDF version missing from compiler arguments")
report["idf_version"] = idf_version[1]
result = json.dumps(report, indent=2)
(project / "artifact-verification.json").write_text(result + "\n", encoding="utf-8")
print(result)
