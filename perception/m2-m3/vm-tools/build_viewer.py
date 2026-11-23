"""Build a self-contained read-only viewer from a Suixing project and its reports."""

import argparse
import base64
import json
from pathlib import Path


SOURCE_FILES = {
    "simulate_avoidance.py": "仿真场景、传感器与闭环运动",
    "avoidance.py": "避障方向选择",
    "geometry.py": "扫掠区域与风险分级",
    "freespace.py": "双目自由空间证据",
    "tracker.py": "障碍跟踪",
    "perception.py": "激光与双目处理",
    "semantic.py": "YOLOv8 与图像识别",
    "semantic_geometry.py": "检测框与深度关联",
    "protocol.py": "风险摘要序列化",
    "ros_node.py": "ROS 2 风险节点",
    "semantic_ros.py": "ROS 2 语义识别节点",
}


def read_json(path, fallback):
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else fallback


def build(project, results, output):
    package = project / "ros_ws/src/suixing_risk/suixing_risk"
    if not package.is_dir():
        raise ValueError(f"package directory missing: {package}")
    files = [
        {"path": path.relative_to(project).as_posix(), "name": path.name,
         "description": description, "text": path.read_text(encoding="utf-8")}
        for name, description in SOURCE_FILES.items()
        if (path := package / name).is_file()
    ]
    for name, description in [
        ("run-all.sh", "非 ROS 测试与仿真入口"),
        ("run-jammy.sh", "Humble 构建与录包回放"),
        ("run-vision-ros.sh", "Humble 图像识别验收"),
        ("vm-tools/verify-humble.sh", "虚拟机 Humble 验收入口"),
        ("vm-tools/run-in-humble.sh", "虚拟机 Humble 环境命令"),
        ("docs/EVIDENCE.md", "交付版本的证据和待验证项"),
    ]:
        if (path := project / name).is_file():
            files.append({"path": name, "name": path.name, "description": description,
                          "text": path.read_text(encoding="utf-8")})

    image_path = results / "bus-detections.jpg"
    image = ""
    if image_path.is_file():
        image = "data:image/jpeg;base64," + base64.b64encode(image_path.read_bytes()).decode("ascii")
    payload = {
        "project": project.name,
        "reports": str(results),
        "scenarios": read_json(results / "avoidance.json", []),
        "detections": read_json(results / "detections.json", {}).get("detections", []),
        "image": image,
        "files": files,
    }
    template = Path(__file__).with_name("viewer.html").read_text(encoding="utf-8")
    data = json.dumps(payload, ensure_ascii=False).replace("<", r"\u003c").replace(">", r"\u003e")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(template.replace("<!-- SUX_DATA -->", data, 1), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--results", type=Path, help="directory that contains the fresh vision reports")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    project = args.project.resolve()
    build(project, (args.results or project / "results/v0.3/vision").resolve(),
          args.output.resolve())
    print(args.output.resolve())


if __name__ == "__main__":
    main()
