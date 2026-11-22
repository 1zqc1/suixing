"""Create and verify the Suixing supplier-reference geometry in millimetres."""

import json
import math
import sys
from itertools import combinations
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ASSETS = ROOT / "tmp" / "rover-v1-supplier"
DEST = HERE / "cad-v1-candidate"
PARTS = DEST / "exchange-parts"
sys.path.insert(0, str(ROOT / "tmp" / "rover-ocp"))

from OCP.BRep import BRep_Builder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.Bnd import Bnd_Box
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer
from OCP.TopoDS import TopoDS_Compound
from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf


def box(origin, size):
    return BRepPrimAPI_MakeBox(gp_Pnt(*origin), *size).Shape()


def cyl(radius, length, position, direction=(0, 1, 0)):
    axis = gp_Ax2(gp_Pnt(*position), gp_Dir(*direction))
    return BRepPrimAPI_MakeCylinder(axis, radius, length).Shape()


def compound(shapes):
    result = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(result)
    for shape in shapes:
        builder.Add(result, shape)
    return result


def cut(shape, tools):
    operation = BRepAlgoAPI_Cut(shape, compound(tools))
    if not operation.IsDone() or operation.Shape().IsNull():
        raise RuntimeError("CAD cut failed")
    return operation.Shape()


def read_step(filename):
    reader = STEPControl_Reader()
    if reader.ReadFile(str(ASSETS / filename)) != IFSelect_RetDone or not reader.TransferRoots():
        raise RuntimeError("Failed to read supplier STEP " + filename)
    return reader.OneShape()


def write_step(shape, path):
    writer = STEPControl_Writer()
    if writer.Transfer(shape, STEPControl_AsIs) != IFSelect_RetDone or writer.Write(str(path)) != IFSelect_RetDone:
        raise RuntimeError(f"STEP export failed: {path}")


def place(shape, rows, datum, location):
    matrix = [(*row, value - sum(a * b for a, b in zip(row, datum)))
              for row, value in zip(rows, location)]
    trsf = gp_Trsf()
    trsf.SetValues(*(value for row in matrix for value in row))
    return BRepBuilderAPI_Transform(shape, trsf, True).Shape()


def turn_about_axle(shape, position, degrees):
    trsf = gp_Trsf()
    trsf.SetRotation(gp_Ax1(gp_Pnt(*position), gp_Dir(1, 0, 0)), math.radians(degrees))
    return BRepBuilderAPI_Transform(shape, trsf, True).Shape()


def bounds(shape):
    result = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, result, False, False)
    return tuple(round(value, 6) for value in result.Get())


def volume_props(shape):
    result = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, result)
    return abs(result.Mass()), result.CentreOfMass().Coord()


def intersections(entries, cross=None):
    pairs = combinations(entries, 2) if cross is None else ((a, b) for a in entries for b in cross)
    result = []
    for a, b in pairs:
        a_box, b_box = a["bounds_mm"], b["bounds_mm"]
        if any(min(a_box[i + 3], b_box[i + 3]) - max(a_box[i], b_box[i]) < 0.0001 for i in range(3)):
            continue
        operation = BRepAlgoAPI_Common(a["shape"], b["shape"])
        if not operation.IsDone():
            raise RuntimeError(f"Interference calculation failed: {a['name']}, {b['name']}")
        overlap, _ = volume_props(operation.Shape())
        if overlap > 0.001:
            result.append([a["name"], b["name"], round(overlap, 6), bounds(operation.Shape())])
    return result


def entry(name, shape, color, mass=None, mass_basis=None, density=None):
    if not BRepCheck_Analyzer(shape).IsValid():
        raise RuntimeError("Invalid geometry: " + name)
    volume, centroid = volume_props(shape)
    if volume <= 0:
        raise RuntimeError("No solid volume: " + name)
    if density is not None:
        mass = volume * density
    return {"name": name, "shape": shape, "color": color, "bounds_mm": bounds(shape),
            "nominal_mass_g": mass, "mass_basis": mass_basis, "centroid_mm": centroid}


def rectangular_part(name, origin, size, color, mass, basis="估算"):
    return entry(name, box(origin, size), color, mass, basis)


AXLE_Z = 40
AXLE_Y = 40
CONTACT_X = 138.7
CASTER_Z = -137
DECK_Y = 61
CASTER_HOLES = ((-7, 0), (3.5, -6.062178), (3.5, 6.062178))
CEK_LEFT = -100.55
CEK_BACK = -34.5
CEK_POINTS = tuple((CEK_LEFT + x, CEK_BACK + 119 - from_top)
                   for x in (17.4, 83.7) for from_top in (3.5, 115.4))


def deck_and_mounts():
    mount_holes = [(side * 116.25, 33 + d, 3.4)
                   for side in (-1, 1) for d in (-14.8, 0, 14.8)]
    caster_holes = [(x, CASTER_Z + z, 3.4) for x, z in CASTER_HOLES]
    pilot_data = [{"x_mm": x, "z_mm": z, "diameter_mm": d} for x, z, d in mount_holes + caster_holes]
    # Drill holes for the known drive hardware. Harness passages and strap slots
    # are design dimensions with no procurement dependence.
    cutters = [cyl(d / 2, 9, (x, DECK_Y - 2, z)) for x, z, d in mount_holes + caster_holes]
    cutters.extend(box(origin, size) for origin, size in
                   [((-118, 59, 103), (12, 9, 8)), ((108, 59, 103), (9, 9, 8)),
                    ((101, 59, -68), (14, 9, 10)), ((-55, 59, -110), (22, 9, 4)),
                    ((-55, 59, -58), (22, 9, 4)), ((27, 59, -110), (22, 9, 4)),
                    ((27, 59, -58), (22, 9, 4)), ((-118, 59, 3), (12, 9, 8)),
                    ((108, 59, 3), (9, 9, 8))])
    deck = cut(box((-122, DECK_Y, -160), (244, 4, 320)), cutters)
    result = [entry("Deck-244x320x4", deck, "#8097AA", mass_basis="CAD 铝体积 × 2.70 g/cm³",
                    density=0.00270)]
    for side in (-1, 1):
        x_min = 113 if side == 1 else -119.5
        shim = cut(box((x_min, 58.4, 14.6), (6.5, 2.6, 36.8)),
                   [cyl(1.7, 8, (x, 57, z)) for x, z, _ in mount_holes if x * side > 0])
        result.append(entry("Bracket-Shim-" + ("R" if side == 1 else "L"), shim, "#A6AFB3",
                            mass_basis="CAD 铝体积 × 2.70 g/cm³", density=0.00270))
    # STEP and drawing agree on the ball centre axis and Ø14 mounting pattern.
    # Recess clears the two 0.1-mm-high datum lugs of the vendor STEP.
    recessed_riser = cut(cyl(17, DECK_Y - 28.992, (0, 28.992, CASTER_Z)),
                         [cyl(15.5, 0.29, (0, 28.95, CASTER_Z))])
    riser = cut(recessed_riser,
                [cyl(1.7, 35, (x, 28, CASTER_Z + z)) for x, z in CASTER_HOLES]
                + [cyl(5, 30, (0, 30, CASTER_Z))])
    result.append(entry("Caster-Spacer-32", riser, "#A6AFB3",
                        mass_basis="CAD 铝体积 × 2.70 g/cm³", density=0.00270))
    return result, pilot_data


def drivetrain():
    motor = read_step("37d-gearmotor-50-70-encoder.step")
    bracket = read_step("Pololu-1995.step")
    hub = read_step("Pololu-1083.step")
    wheel = read_step("pololu-wheel-80x10mm-black.step")
    caster = place(read_step("Pololu-2691.step"), ((1, 0, 0), (0, -1, 0), (0, 0, -1)),
                   (0, 28.992, 0), (0, 0, CASTER_Z))
    result = [entry("Pololu-2691-Rear-Ball", caster, "#414852", 16.5, "厂商")]
    for side, label, spin in ((1, "R", -30), (-1, "L", -150)):
        # Support flat is above the motor. The 7 mm shaft eccentricity is +Z on both sides.
        motor_axes = ((0, 0, side), (-side, 0, 0), (0, -1, 0))
        bracket_axes = ((0, 0, side), (-1, 0, 0), (0, -side, 0))
        source_motor = place(motor, motor_axes, (19.925, 0, 19.925), (side * 113, 40, 33))
        source_bracket = place(bracket, bracket_axes, (3.25, 0, -21.65), (side * 113, 40, 33))
        source_hub = place(hub, ((0, 0, -side), (1, 0, 0), (0, -side, 0)), (0, 0, 0),
                           (side * 133.2, AXLE_Y, AXLE_Z))
        source_wheel = place(wheel, ((-side, 0, 0), (0, 1, 0), (0, 0, -side)), (0, 0, 0),
                             (side * CONTACT_X, AXLE_Y, AXLE_Z))
        axle = (side * CONTACT_X, AXLE_Y, AXLE_Z)
        flange = (side * 135.7, AXLE_Y, AXLE_Z)
        bolt_axes = [(AXLE_Y + 9.525 * math.sin(math.radians(angle)),
                      AXLE_Z + 9.525 * math.cos(math.radians(angle)))
                     for angle in range(0, 360, 60)]
        shim = cut(cyl(12.7, .5, flange, (side, 0, 0)),
                   [cyl(7.9, 2, (side * 135.2, AXLE_Y, AXLE_Z), (side, 0, 0))]
                   + [cyl(1.55, 2, (side * 135.2, y, z), (side, 0, 0)) for y, z in bolt_axes])
        result.extend([
            entry("Pololu-4753-Motor-" + label, source_motor, "#526071", 205, "厂商"),
            entry("Pololu-1995-Bracket-" + label, source_bracket, "#BEC6CA", 14, "厂商"),
            entry("Pololu-1083-Hub-" + label, turn_about_axle(source_hub, axle, spin), "#B8C2CB", 6.8, "厂商"),
            entry("Wheel-Face-Shim-" + label, turn_about_axle(shim, axle, spin), "#A6AFB3",
                  mass_basis="CAD 铝体积 × 2.70 g/cm³", density=0.00270),
            entry("Pololu-1430-Wheel-" + label, turn_about_axle(source_wheel, axle, spin), "#272A2D",
                  19.8447, "厂商 0.7 oz"),
        ])
    return result


def electronics():
    # Purchased boards lacking stack height or hole diameters use documented
    # outline dimensions and visibly named clearance models.
    board = box((CEK_LEFT, 84, CEK_BACK), (93.1, 1.6, 119))
    ports = [box((CEK_LEFT - 1.4, 85.6, z), (15, height, 15))
             for z, height in ((67, 13.7), (49, 13.7), (29, 16.4), (11, 16.4))]
    heatsink = box((-77, 85.6, 3), (45, 20, 45))
    power_port = box((-26, 85.6, 61), (20, 10.3, 10))
    result = [entry("CEK8903-93p1x119-Board-Reference", compound([board, *ports, heatsink, power_port]),
                    "#1D795D", 125, "质量、堆叠和连接器包络估算，PCB 平面按厂商图")]
    result.append(rectangular_part("CEK8903-Adapter-Undrilled", (-101, 65, -35), (94, 2, 120),
                                   "#779497", 61, "估算，保留 CEK8903 孔位为参考点"))
    # Standoffs as layout reference, with no inferred board or carrier screw size.
    result.append(entry("CEK8903-Standoff-Clearances",
                        compound([cyl(3, 17, (x, 67, z)) for x, z in CEK_POINTS]), "#A9B0B1",
                        6, "几何轴线含下排对齐推定，质量估算"))
    result.extend([
        rectangular_part("STM32-F103-EliteV2-Service-Bay", (7, 73, -26), (110, 19, 121), "#2B6E51", 95),
        rectangular_part("STM32-Removable-Tray", (6, 65, -27), (112, 2, 123), "#7E928C", 75),
        rectangular_part("GensAce-4S-5000mAh-EC5", (-75, 65, -103), (136, 32, 42), "#344F77", 418, "厂商"),
        rectangular_part("G2-2991-Driver-A", (84, 67, -115), (20.32, 15, 33.02), "#913849", 12),
        rectangular_part("G2-2991-Driver-B", (48, 67, -147), (33.02, 15, 20.32), "#913849", 12),
        rectangular_part("12V-Logic-BuckBoost-Bay", (-108, 65, -147), (52, 23, 31), "#9F7138", 50),
        rectangular_part("5V-Logic-2851", (-119, 65, -83), (17.8, 12, 20.3), "#AB8751", 10),
        rectangular_part("Relays-Fuse-EC5-Service-Bay", (-46, 65, -150), (83, 28, 33), "#C77835", 65),
        rectangular_part("ESP32-Antenna-Bay", (92, 65, 112), (23, 9, 34), "#237D80", 14),
        rectangular_part("IMU-Insulated-Mount-Bay", (-7, 65, 98), (22, 5, 22), "#2E94A8", 9),
        rectangular_part("Buzzer-Status-Indicator-Bay", (73, 65, -157), (40, 13, 7), "#B3823A", 10),
        entry("Power-Signal-Partition-Panel", box((7, 65, -54), (113, 22, 2)), "#768894",
              mass_basis="CAD 铝体积 × 2.70 g/cm³", density=0.00270),
        rectangular_part("EStop-Service-Base", (-113, 65, 117), (32, 5, 32), "#DDB138", 8),
        entry("EStop-Red-Head", cyl(14, 18, (-97, 70, 133)), "#D12B36", 24, "估算"),
    ])
    # Camera on a central mast, front ToF and a downward/ground-facing ToF.
    mast = box((-20, 65, 139), (40, 49, 8))
    result.extend([
        entry("Camera-Mast", mast, "#A0ADB6", mass_basis="CAD 铝体积 × 2.70 g/cm³", density=0.00270),
        entry("Arducam-B0201-Optical-Envelope",
              compound([box((-19, 104, 147), (38, 38, 2)),
                        cyl(10, 17, (0, 124, 149), (0, 0, 1))]),
              "#354750", 20, "PCB 38×38 为厂商值，镜头深度与质量估算"),
    ])
    # Ø2.18 holes, 2.5 mm from both end edges, hence a 12.8 mm pin-centre pitch.
    # The 8.8 mm dimension in the vendor drawing identifies the optical centre.
    # Hole coordinates relative
    # to the 12.7 x 17.8 outline are taken from the factory drawing.
    for label, x in (("Forward", -54), ("Down", 54)):
        if label == "Forward":
            board = box((x-6.35, 74, 153), (12.7, 17.8, 2.62))
            holes = [cyl(1.09, 9, (x+3.85, y, 148), (0, 0, 1)) for y in (76.5, 89.3)]
            bracket = box((x-12, 65, 149), (24, 26, 4))
        else:
            board = box((x-6.35, 55, 146), (12.7, 2.62, 17.8))
            holes = [cyl(1.09, 9, (x+3.85, 54, z)) for z in (148.5, 161.3)]
            bracket = box((x-12, 57.62, 143), (24, 3.38, 20))
        result.append(entry("VL53L5CX-3417-" + label, cut(board, holes), "#257B93", 0.5, "厂商"))
        result.append(entry("ToF-Mount-Blank-" + label, cut(bracket, holes), "#849EAA",
                            mass_basis="CAD 铝体积 × 2.70 g/cm³", density=0.00270))
    return result


def routing():
    return [
        rectangular_part("USB-Unplug-Aisle", (-130, 86, -3), (27.5, 22, 110), "#3C9ED4", None),
        rectangular_part("J34-Rear-Access", (-66, 86, -60), (24, 20, 25), "#3C9ED4", None),
        rectangular_part("Sensor-Loom-Front", (-120, 68, 98), (36, 14, 17), "#319BBA", None),
        rectangular_part("Pulse-Power-Underside", (99, 49, -69), (19, 9, 78), "#DE792E", None),
        rectangular_part("Motor-Power-Crossing", (-106, 48, -52), (205, 8, 10), "#DE792E", None),
        rectangular_part("Left-Motor-Fanout", (-118, 49, -52), (12, 9, 61), "#DE792E", None),
        rectangular_part("Right-Driver-Fanout", (107, 68, -115), (13, 18, 46), "#DE792E", None),
        rectangular_part("Battery-EC5-Service", (61, 67, -102), (22, 25, 26), "#DE792E", None),
    ]


def stability(entries):
    masses = [e for e in entries if e["nominal_mass_g"] is not None]
    total = sum(e["nominal_mass_g"] for e in masses)
    cx, height, cz = [sum(e["nominal_mass_g"] * e["centroid_mm"][axis] for e in masses) / total
                     for axis in range(3)]
    length = AXLE_Z - CASTER_Z
    hyp = math.hypot(CONTACT_X, length)
    margins = [AXLE_Z-cz, (CONTACT_X*(cz-CASTER_Z)+length*cx)/hyp,
               (CONTACT_X*(cz-CASTER_Z)-length*cx)/hyp]
    return {
        "status": "nominal_estimate_from_supplier_and_assumed_masses",
        "contact_points_xz_mm": [[-CONTACT_X, AXLE_Z], [CONTACT_X, AXLE_Z], [0, CASTER_Z]],
        "total_mass_kg": total / 1000,
        "cg_xyz_mm": [cx, height, cz],
        "signed_margins_front_left_right_mm": margins,
        "ideal_edge_angles_deg": [math.degrees(math.atan2(distance, height)) for distance in margins],
        "nominal_caster_load_kg_equivalent": total / 1000 * (AXLE_Z-cz) / length,
        "level_quasistatic_acceleration_limit_g_normal_to_each_edge": [d / height for d in margins],
    }


def main():
    PARTS.mkdir(parents=True, exist_ok=True)
    deck, holes = deck_and_mounts()
    parts = [*deck, *drivetrain(), *electronics()]
    corridors = routing()
    overlap = intersections(parts)
    shaft_fit = [row for row in overlap if row[0].startswith("Pololu-4753-Motor-")
                 and row[1] == "Pololu-1083-Hub-" + row[0][-1] and row[2] < 0.01]
    hard_overlap = [row for row in overlap if row not in shaft_fit]
    routing_overlap = intersections(corridors, parts)
    print("CAD solids overlaps:", hard_overlap, "\nNominal shaft-fit contact:", shaft_fit,
          "\nRouting overlaps:", routing_overlap, flush=True)
    if hard_overlap or routing_overlap:
        raise RuntimeError("Resolve the listed overlaps before producing candidate files")
    for part in parts:
        write_step(part["shape"], PARTS / (part["name"] + ".step"))
    write_step(compound(x["shape"] for x in parts), DEST / "OCCT-Candidate-Geometry.step")
    write_step(compound(x["shape"] for x in corridors), DEST / "Routing-Clearance-Overlay.step")
    record = {
        "parts": [{key: value for key, value in part.items() if key != "shape"} for part in parts],
        "routing": [{key: value for key, value in part.items() if key != "shape"} for part in corridors],
        "interference_mm3": hard_overlap, "nominal_fit_contact_mm3": shaft_fit,
        "routing_interference_mm3": routing_overlap,
        "deck_drilled_holes_xz_mm": holes, "cek_reference_axes_xz_mm": CEK_POINTS,
        "bounds_mm": bounds(compound(x["shape"] for x in parts)),
        "static_stability": stability(parts),
    }
    (DEST / "candidate-geometry.json").write_text(json.dumps(record, indent=2, ensure_ascii=False),
                                                  encoding="utf-8")
    print(json.dumps(record["static_stability"], indent=2), flush=True)


if __name__ == "__main__":
    main()
