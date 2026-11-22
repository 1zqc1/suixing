"""Generate the V4 assistive rover concept in millimetres (+Y up, +Z forward)."""

import json
import math

import build_supplier_rover as cad
from build_integrated_rover import loft
from OCP.IFSelect import IFSelect_RetDone
from OCP.Quantity import Quantity_Color, Quantity_TOC_sRGB
from OCP.STEPCAFControl import STEPCAFControl_Reader, STEPCAFControl_Writer
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_LabelSequence
from OCP.TDocStd import TDocStd_Document
from OCP.TopLoc import TopLoc_Location
from OCP.XCAFDoc import XCAFDoc_ColorGen, XCAFDoc_DocumentTool

OUTPUT = cad.HERE / "cad-v4-two-drive"
NAME = "Suixing-V4-TwoDrive-HighSensors"
CAMERA_Y = 600.0
SCAN_Y = 655.0
GRIP_Y = 950.0
MAST_Z = 132.0
AXLE_Z = -90.0
CASTER_Z = 154.0

IVORY = "#E1E8EA"
DARK = "#293540"
METAL = "#839BAA"
RUBBER = "#243039"
BLUE = "#246C97"


def part(name, shape, color):
    return cad.entry("V4-" + name, shape, color)


def box(name, point, size, color):
    return part(name, cad.box(point, size), color)


def hull():
    # Component datums and service envelopes, with no invented supplier holes.
    deck = loft((-136, 136, 104, -221, 221, 26), (-136, 136, 110, -221, 221, 26))
    bumper = cad.cut(
        loft((-137, 137, 110, -225, 225, 27), (-137, 137, 140, -225, 225, 27)),
        [loft((-130, 130, 109, -218, 218, 24), (-130, 130, 141, -218, 218, 24))],
    )
    fairing = cad.cut(
        loft((-137, 137, 140, -225, 225, 27), (-137, 137, 172, -225, 225, 27),
             (-116, 116, 242, -194, 196, 34)),
        [loft((-130, 130, 139, -218, 218, 24), (-130, 130, 172, -218, 218, 24),
              (-109, 109, 236, -187, 189, 31))],
    )
    fairing = cad.cut(fairing, [cad.cyl(28, 9, (0, 235, MAST_Z)),
                               *(cad.cyl(18, 10, (side * 92, 235, -150)) for side in (-1, 1))])
    return [
        part("Chassis-Deck-Envelope", deck, METAL),
        part("Perimeter-Bumper-Envelope", bumper, DARK),
        part("Removable-Cover-Envelope", fairing, IVORY),
        box("Battery-Low-Center-Envelope", (-62, 110, -87), (124, 48, 104), "#406285"),
        box("Electronics-Tray-Envelope", (-110, 158, -12), (94, 4, 119), METAL),
        box("CEK8903-Board-Envelope", (-109.55, 162, -12), (93.1, 33, 119), "#36806B"),
        box("Two-Channel-Drive-Envelope", (67, 110, -79), (43, 22, 90), "#A45951"),
    ]


def running_gear():
    parts = []
    sweeps = []
    for side, label in ((-1, "L"), (1, "R")):
        drive_axis = (side, 0, 0)
        outer = cad.cyl(90, 30, (side * 145, 90, AXLE_Z), drive_axis)
        tire = cad.cut(outer, [cad.cyl(63, 32, (side * 144, 90, AXLE_Z), drive_axis)])
        motor = cad.cyl(13.5, 50, (side * 62, 90, AXLE_Z), drive_axis)
        cradle = cad.cut(cad.box((side * 89 - 11, 84, AXLE_Z - 19), (22, 20, 38)), [motor])
        parts.extend([
            part("Rubber-Drive-Tire-" + label, tire, RUBBER),
            part("Drive-Hub-" + label, cad.cyl(63, 28, (side * 145, 90, AXLE_Z), drive_axis), METAL),
            part("Drive-Axle-" + label, cad.cyl(9, 33, (side * 112, 90, AXLE_Z), drive_axis), METAL),
            part("Gearmotor-Envelope-" + label, motor, DARK),
            part("Gearmotor-Cradle-Envelope-" + label, cradle, METAL),
        ])
        x = side * 86
        wheel_z = CASTER_Z - 16
        parts.extend([
            part("Caster-Wheel-" + label, cad.cyl(42, 26, (x - 13, 42, wheel_z), (1, 0, 0)), RUBBER),
            part("Caster-Fork-" + label, cad.compound([
                cad.box((x - 20, 39, wheel_z - 11), (6, 50, 22)),
                cad.box((x + 14, 39, wheel_z - 11), (6, 50, 22)),
                cad.box((x - 20, 89, wheel_z - 13), (40, 6, 40)),
            ]), METAL),
            part("Caster-Pivot-" + label, cad.cyl(14, 9, (x, 95, CASTER_Z)), DARK),
        ])
        sweeps.append(part("Caster-Swivel-Envelope-" + label,
                           cad.cyl(62, 104, (x, 0, CASTER_Z)), DARK))
    return parts, sweeps


def sensing_mast():
    radar_y = SCAN_Y - 26.9
    carrier = cad.cut(cad.box((-31, CAMERA_Y - 10, MAST_Z + 10), (62, 20, 13)),
                      [cad.cyl(15, 22, (0, CAMERA_Y - 11, MAST_Z))])
    parts = [
        part("Mast-Base-Load-Path", cad.cyl(26, 138, (0, 110, MAST_Z)), METAL),
        part("Front-Mast", cad.cyl(15, radar_y - 8 - 248, (0, 248, MAST_Z)), METAL),
        part("Stereo-Carrier", carrier, METAL),
        box("Stereo-60mm-Housing-Envelope", (-51, CAMERA_Y - 15, MAST_Z + 23), (102, 30, 25), DARK),
        box("D6-Top-Carrier", (-29, radar_y - 8, MAST_Z - 25), (58, 8, 50), METAL),
        box("COIN-D6-Base", (-26.35, radar_y, MAST_Z - 22.6), (52.7, 18, 45.2), DARK),
        part("COIN-D6-Optical-Head", cad.cyl(20.7, 16.4, (0, radar_y + 18, MAST_Z)), RUBBER),
    ]
    for x, label in ((-30, "L"), (30, "R")):
        parts.append(part("Stereo-Lens-" + label,
                          cad.cyl(9, 2, (x, CAMERA_Y, MAST_Z + 48), (0, 0, 1)), BLUE))
    return parts


def handle():
    z_base, z_grip = -150, -384
    bottom = GRIP_Y - 15
    dy, dz = bottom - 242, z_grip - z_base
    span = math.hypot(dy, dz)
    direction = (0, dy / span, dz / span)
    clips = [cad.box((-140, 205, -445), (280, 37, 330)),
             cad.box((-140, bottom, -445), (280, 25, 330))]
    parts = [
        box("Handle-Control-Bridge", (-70, bottom, z_grip - 23), (140, 30, 47), DARK),
        part("Manual-Confirm", cad.cyl(9, 4, (0, GRIP_Y + 15, z_grip)), BLUE),
        part("Physical-EStop", cad.cyl(13, 14, (43, GRIP_Y + 15, z_grip)), "#C13244"),
    ]
    for side, label in ((-1, "L"), (1, "R")):
        x = side * 92
        grip = cad.cyl(19, 76, (side * 70, GRIP_Y, z_grip), (side, 0, 0))
        upright = cad.cyl(13, span + 20, (x, 242 - 10 * direction[1], z_base - 10 * direction[2]), direction)
        upright = cad.cut(cad.cut(upright, clips), [grip])
        parts.extend([
            part("Handle-Base-" + label, cad.cyl(16, 132, (x, 110, z_base)), METAL),
            part("Handle-Upright-" + label, upright, METAL),
            part("Handle-Vibration-Grip-" + label, grip, RUBBER),
        ])
    return parts


def write_assembly_step(target, parts, expected_bounds):
    document = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    colors = XCAFDoc_DocumentTool.ColorTool_s(document.Main())
    assembly = shapes.NewShape()
    TDataStd_Name.Set_s(assembly, TCollection_ExtendedString(NAME))
    for p in parts:
        label = shapes.AddShape(p["shape"], False)
        component = shapes.AddComponent(assembly, label, TopLoc_Location())
        name = TCollection_ExtendedString(p["name"])
        TDataStd_Name.Set_s(label, name)
        TDataStd_Name.Set_s(component, name)
        rgb = [int(p["color"][index:index + 2], 16) / 255 for index in (1, 3, 5)]
        colors.SetColor(label, Quantity_Color(*rgb, Quantity_TOC_sRGB), XCAFDoc_ColorGen)
    shapes.UpdateAssemblies()
    writer = STEPCAFControl_Writer()
    if not writer.Transfer(document) or writer.Write(str(target)) != IFSelect_RetDone:
        raise RuntimeError("Assembly STEP export failed")

    reader = STEPCAFControl_Reader()
    reopened = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    if reader.ReadFile(str(target)) != IFSelect_RetDone or not reader.Transfer(reopened):
        raise RuntimeError("Assembly STEP reopen failed")
    reopened_tool = XCAFDoc_DocumentTool.ShapeTool_s(reopened.Main())
    roots, components = TDF_LabelSequence(), TDF_LabelSequence()
    reopened_tool.GetFreeShapes(roots)
    if roots.Length() != 1 or not reopened_tool.GetComponents_s(roots.Value(1), components):
        raise RuntimeError("STEP assembly hierarchy missing")
    shape = reopened_tool.GetShape_s(roots.Value(1))
    if (components.Length() != len(parts) or not cad.BRepCheck_Analyzer(shape).IsValid()
            or any(abs(a - b) > 0.01 for a, b in zip(expected_bounds, cad.bounds(shape)))):
        raise RuntimeError("STEP assembly round-trip mismatch")
    return components.Length()


def build():
    exchange = OUTPUT / "exchange-parts"
    exchange.mkdir(parents=True, exist_ok=True)
    base = hull()
    wheels, sweeps = running_gear()
    parts = base + wheels + sensing_mast() + handle()
    body = cad.compound(p["shape"] for p in parts)
    scan = cad.cut(cad.cyl(880, 0.5, (0, SCAN_Y - 0.25, MAST_Z)),
                   [cad.cyl(21, 1, (0, SCAN_Y - 0.5, MAST_Z))])
    shadows = cad.intersections([part("Scan-Test", scan, BLUE)], parts)
    rear_sectors = {}
    for _, name, _, (xmin, _, zmin, xmax, _, zmax) in shadows:
        if not name.startswith("V4-Handle-Upright-") or zmax >= MAST_Z:
            raise RuntimeError(f"Unexpected scan obstruction: {name}")
        angles = [math.degrees(math.atan2(x, z - MAST_Z))
                  for x in (xmin, xmax) for z in (zmin, zmax)]
        rear_sectors[name] = [math.floor(min(angles)), math.ceil(max(angles))]
    checks = {
        "static_intersections": cad.intersections(parts),
        "caster_sweep_intersections": cad.intersections(
            sweeps, [p for p in parts if not p["name"].startswith("V4-Caster-")]),
    }
    if any(checks.values()):
        raise RuntimeError(checks)
    for p in parts:
        cad.write_step(p["shape"], exchange / (p["name"] + ".step"))
    bounds = cad.bounds(body)
    component_count = write_assembly_step(OUTPUT / (NAME + ".step"), parts, bounds)
    report = {
        "parts": [{k: v for k, v in p.items() if k != "shape"} for p in parts],
        "overall_bounds_mm": bounds,
        "chassis_length_width_mm": [450, 350],
        "drive_track_mm": 320,
        "drive_tire_diameter_mm": 180,
        "caster_diameter_mm": 84,
        "caster_pivot_to_drive_axle_mm": CASTER_Z - AXLE_Z,
        "camera_center_height_mm": CAMERA_Y,
        "stereo_baseline_mm": 60,
        "lidar_scan_height_mm": SCAN_Y,
        "rear_scan_shadow_sectors_deg": rear_sectors,
        "grip_center_height_mm": GRIP_Y,
        "step_reloaded_valid": True,
        "step_reloaded_components": component_count,
        **checks,
    }
    (OUTPUT / "candidate-geometry.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "parts"}, indent=2))


if __name__ == "__main__":
    build()
