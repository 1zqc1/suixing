"""Build V2 removable bodywork, camera module, and interference evidence."""

import json
import math
from pathlib import Path
from shutil import copy2

import build_supplier_rover as base

from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon
from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCone
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

ROOT = Path(__file__).resolve().parent
DEST = ROOT / "cad-v2-integrated"
OUT = DEST / "exchange-parts"
CAM_Y = 109
LENS_FRONT = 153.8
NOSE_FRONT = 159
ARMOR_DENSITY = .00124  # provisional unfilled polymer, g/mm³
AL_DENSITY = .00270
Z_AXIS = (0, 0, 1)
OMIT = {"Deck-244x320x4", "Camera-Mast", "Arducam-B0201-Optical-Envelope"}
DOWNWARD_PARTS = {"VL53L5CX-3417-Down", "ToF-Mount-Blank-Down"}
TRANSLATE = ((1, 0, 0), (0, 1, 0), (0, 0, 1))


def section(min_x, max_x, y, min_z, max_z, clip):
    points = ((min_x+clip, min_z), (max_x-clip, min_z), (max_x, min_z+clip),
              (max_x, max_z-clip), (max_x-clip, max_z), (min_x+clip, max_z),
              (min_x, max_z-clip), (min_x, min_z+clip))
    build = BRepBuilderAPI_MakePolygon()
    for x, z in points:
        build.Add(gp_Pnt(x, y, z))
    build.Close()
    return build.Wire()


def loft(*levels):
    build = BRepOffsetAPI_ThruSections(True, True, 1e-6)
    for level in levels:
        build.AddWire(section(*level))
    build.Build()
    if not build.IsDone():
        raise RuntimeError("Shell loft failed")
    return build.Shape()


def join(a, b):
    operation = BRepAlgoAPI_Fuse(a, b)
    if not operation.IsDone():
        raise RuntimeError("Body union failed")
    return operation.Shape()


def nose_cone(radius, length, start, half_angle=60):
    outer = radius + length * math.tan(math.radians(half_angle))
    axis = gp_Ax2(gp_Pnt(0, CAM_Y, start), gp_Dir(*Z_AXIS))
    return BRepPrimAPI_MakeCone(axis, radius, outer, length).Shape()


def shell():
    outer = loft((-121.3, 121.3, 65, -158, 105, 6),
                 (-121.3, 121.3, 106, -158, 105, 6),
                 (-111, 111, 119, -148, 96, 14))
    inner = loft((-118.9, 118.9, 64, -155.6, 102.6, 4),
                 (-118.9, 118.9, 105, -155.6, 102.6, 4),
                 (-110, 110, 116.6, -147, 94.5, 11))
    body = base.cut(outer, [inner])
    service = [
        base.box((-128, 79, -9), (21, 34, 116)),  # left USB and plug insertion
        base.box((-128, 65.5, 95), (45, 48, 12)), # front-left signal harness
        base.box((-123, 71, -138), (8, 22, 31)),  # regulated power ventilation
        base.box((-119.5, 64, -84), (2, 15, 23)),  # 5 V carrier edge
        base.box((70, 64, -161), (45, 20, 13)),   # status bar and service
        base.box((108, 65.3, 100), (10, 12, 8)),  # sensor wires
        base.box((-8, 64, 102), (24, 9, 5)),     # IMU exit
        base.box((117, 67.5, -116), (8, 21, 48)), # right driver fanout
        base.box((118.5, 64, -54.4), (2, 24, 2.8)), # partition edge
    ]
    service.extend(base.box((-84 + i*8, 113.7, -19), (3.8, 8, 49)) for i in range(8))
    service.extend(base.box((45 + i*8, 113.7, -133), (3.8, 8, 32)) for i in range(6))
    for tool in service:
        body = base.cut(body, [tool])
    return body


def design_parts(deck):
    parts = []
    # The cover's rear stays fastened away from both device bays. The forward
    # pair is outside the underside motor hardware.
    cover_holes = [(side*115, z) for side in (-1, 1) for z in (-140, 99)]
    bumper_holes = [(-101, 156), (101, 156)]
    pod_holes = [(-69, 135), (69, 135)]
    mounts = cover_holes + bumper_holes + pod_holes
    tools = [base.cyl(1.7, 10, (x, 59, z)) for x, z in mounts]
    deck = base.cut(deck, tools)
    parts.append(base.entry("Deck-Service-Mounts", deck, "#29303B", density=AL_DENSITY,
                             mass_basis="CAD 铝体积"))

    hood = shell()
    for x, z in cover_holes:
        tab = base.box((109 if x > 0 else -120.2, 65, z-3), (11.2, 3, 6))
        hood = join(hood, tab)
    hood = base.cut(hood, [base.cyl(1.7, 8, (x, 63, z)) for x, z in cover_holes])
    parts.append(base.entry("Lift-Off-Equipment-Cover", hood, "#7694A8", density=ARMOR_DENSITY,
                            mass_basis="CAD 塑料实体估算"))
    # Centre bridge leaves the e-stop untouched and presents the forward ToF
    # behind a large open window. The downward ToF stays on its own saddle.
    rail = loft((-78, 78, 65, 123, 158, 7),
                (-78, 78, 75, 123, 158, 7),
                (-69, 69, 97, 127, 158, 8))
    rail = base.cut(rail, [loft((-64, 64, 64, 125.5, 155.7, 5),
                               (-64, 64, 91, 125.5, 155.7, 5),
                               (-60, 60, 94.3, 129, 155.5, 5))])
    for opening in (base.box((-67.5, 64, 143.5), (29, 33, 19)),
                    base.box((39, 63.5, 141), (30, 7, 21)),
                    base.box((-20, 89, 132), (40, 10, 5)),
                    nose_cone(7.5, 15, LENS_FRONT-.3)):
        rail = base.cut(rail, [opening])
    for x, z in pod_holes:
        pad = base.box((x-4, 65, z-4), (8, 5, 8))
        rail = join(rail, pad)
    rail = base.cut(rail, [base.cyl(1.7, 8, (x, 63, z)) for x, z in pod_holes])
    parts.append(base.entry("Front-Sensor-Bridge", rail, "#7694A8", density=ARMOR_DENSITY,
                            mass_basis="CAD 塑料实体估算"))

    # Compact faceted hood. The rear service pocket goes through the upper
    # shroud, keeping the PCB and cable removable clear of the lens opening.
    pod = loft((-28, 28, 97, 120, 156, 5), (-27, 27, 120, 121, 156, 5),
               (-19, 19, 132, 125, 151, 5))
    inner = base.box((-21, 96, 118), (42, 33, 32))
    pod = base.cut(pod, [inner])
    pod = base.cut(pod, [base.box((-12, 96, 146), (24, 23, 13))])
    pod = base.cut(pod, [nose_cone(8.5, 10, LENS_FRONT-0.2)])
    parts.append(base.entry("Camera-Service-Shroud", pod, "#354352", density=ARMOR_DENSITY,
                            mass_basis="CAD 塑料实体估算"))

    # PCB outline plus recognizable square M12 holder, stepped barrel and glass.
    # The PCB's endoscopic details, PCB mounting-hole diameters, and back
    # connector envelope remain references against the actual camera.
    camera_pcb = base.box((-19, CAM_Y-19, 134.3), (38, 38, 1.6))
    holder = base.box((-9, CAM_Y-9, 135.9), (18, 18, 4))
    barrel = base.cyl(6, 9.1, (0, CAM_Y, 139.9), Z_AXIS)
    ring = base.cut(base.cyl(7, LENS_FRONT-149, (0, CAM_Y, 149), Z_AXIS),
                    [base.cyl(5.5, 6, (0, CAM_Y, 148.8), Z_AXIS)])
    board = base.compound([camera_pcb, holder, barrel, ring])
    parts.append(base.entry("B0201-PCB-and-M12-Carrier", board, "#294349", 19,
                            "厂家外形参考，叠高和质量估算"))
    parts.append(base.entry("B0201-Front-Glass", base.cyl(5.45, .45, (0, CAM_Y, LENS_FRONT-.45), Z_AXIS),
                            "#416678", 1, "外观参考"))
    folded = base.box((-20, 97, 131.3), (40, 28, 3))
    folded = base.cut(folded, [base.box((-16, 102, 130), (32, 17, 5))])
    parts.append(base.entry("Camera-Removable-Carrier", folded, "#879298", density=AL_DENSITY,
                            mass_basis="CAD 铝体积，PCB 固定待实物核对"))

    for label, x in (("L", -101), ("R", 101)):
        side = loft((x-17, x+17, 65, 150, NOSE_FRONT, 3),
                    (x-17, x+17, 72, 150, NOSE_FRONT, 3),
                    (x-12, x+12, 83, 151, NOSE_FRONT, 3))
        side = base.cut(side, [base.cyl(1.7, 22, (x, 64, 156))])
        parts.append(base.entry("Front-Corner-Guard-"+label, side, "#33404B", density=ARMOR_DENSITY,
                                mass_basis="CAD 塑料实体估算"))
    return parts, mounts


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    deck, _ = base.deck_and_mounts()
    parts = [p for p in [*deck, *base.drivetrain(), *base.electronics()] if p["name"] not in OMIT]
    inherited = {p["name"] for p in parts} - DOWNWARD_PARTS
    for i, part in enumerate(parts):
        if part["name"] in DOWNWARD_PARTS:
            moved = base.place(part["shape"], TRANSLATE, (0, 0, 0), (0, 0, -6))
            parts[i] = base.entry(part["name"], moved, part["color"], part["nominal_mass_g"],
                                  part["mass_basis"])
    added, mounts = design_parts(deck[0]["shape"])
    parts.extend(added)
    keepouts = base.routing()
    cone = base.entry("Camera-120deg-Clearance", nose_cone(6.7, 19, LENS_FRONT), "#69E4CD")
    # The front ToF is a wide-angle transmitter/receiver. Reserve the unobstructed
    # straight nominal view and a conservative conical allowance near its face.
    tof_axis = gp_Ax2(gp_Pnt(-52.75, 82.8, 155.62), gp_Dir(*Z_AXIS))
    tof = base.entry("Forward-ToF-View",
                     BRepPrimAPI_MakeCone(tof_axis, 2.5, 13, 16).Shape(), "#69E4CD")
    downward_axis = gp_Ax2(gp_Pnt(55.25, 55, 148.8), gp_Dir(0, -1, 0))
    downward = base.entry("Downward-ToF-View",
                          BRepPrimAPI_MakeCone(downward_axis, 2.5, 13, 16).Shape(), "#69E4CD")
    overlaps = base.intersections(parts)
    contacts = [row for row in overlaps if row[0].startswith("Pololu-4753-Motor-")
                and row[1] == "Pololu-1083-Hub-" + row[0][-1] and row[2] < .01]
    hard = [row for row in overlaps if row not in contacts]
    cables = base.intersections(keepouts, parts)
    optical_volumes = [cone, tof, downward]
    optical = base.intersections(optical_volumes, parts)
    lid = next(p for p in parts if p["name"] == "Lift-Off-Equipment-Cover")
    fixed = [p for p in parts if p is not lid]
    lid_lift = {
        rise: base.intersections([base.entry("Lift-Off Cover", base.place(
            lid["shape"], TRANSLATE, (0, 0, 0), (0, rise, 0)), lid["color"])], fixed)
        for rise in (2, 5, 15, 30, 55)
    }
    print("Solids:", hard, "\nRouting:", cables, "\nSight:", optical, "\nLid lift:", lid_lift, flush=True)
    if hard or cables or optical or any(lid_lift.values()):
        raise RuntimeError("Resolve the listed overlaps before delivery")
    for p in parts:
        source_name = p["name"]
        p["name"] = "V2-" + source_name
        if source_name in inherited:
            copy2(base.PARTS / (source_name + ".step"), OUT / (p["name"] + ".step"))
        else:
            base.write_step(p["shape"], OUT / (p["name"] + ".step"))
    base.write_step(base.compound(p["shape"] for p in parts), DEST / "Suixing-Rover-V2-Integrated.step")
    base.write_step(base.compound(p["shape"] for p in [*keepouts, *optical_volumes]),
                    DEST / "Routing-and-Optical-Overlay.step")
    report = {
        "parts": [{k: v for k, v in p.items() if k != "shape"} for p in parts],
        "inherited": sorted(inherited), "hard_interference_mm3": hard,
        "nominal_shaft_contacts_mm3": contacts, "routing_interference_mm3": cables,
        "optical_interference_mm3": optical, "deck_added_mounts_xz_mm": mounts,
        "lid_lift_interference_at_rises_mm": lid_lift,
        "overall_bbox_mm": base.bounds(base.compound(p["shape"] for p in parts)),
        "lens_setback_from_guards_mm": NOSE_FRONT-LENS_FRONT, "stability": base.stability(parts),
    }
    (DEST / "candidate-geometry.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{len(parts)} parts. Bounds {report['overall_bbox_mm']}. Stability {report['stability']}", flush=True)


if __name__ == "__main__":
    main()
