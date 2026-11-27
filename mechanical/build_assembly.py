"""Export committed boards and sample an explicitly nominal whole-assembly motion.

Run with FreeCAD's Python. Vendor CAD and intermediate geometry stay in --cache.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import FreeCAD as App
import Mesh
import Part


ROOT = Path(__file__).resolve().parents[1]
METER_COMMIT = "9230d0efbb124c0492c8161200cb30ad9d554fdd"
MOLEX_SHA = "d6869b778b0c0f52e6d0116f89b77f505835ec5169ee50730b6dc643fce282d9"
THRESHOLD = 0.01
MODEL_ALIASES = {
    "${KISYS3DMOD}/Housings_SSOP.3dshapes/SSOP-28_5.3x10.2mm_Pitch0.65mm.wrl":
        r"Package_SO.3dshapes\SSOP-28_5.3x10.2mm_P0.65mm.step",
    "Capacitors_SMD.3dshapes/C_0402.wrl":
        r"Capacitor_SMD.3dshapes\C_0402_1005Metric.step",
    "Capacitors_SMD.3dshapes/C_0603.wrl":
        r"Capacitor_SMD.3dshapes\C_0603_1608Metric.step",
    "${KISYS3DMOD}/Resistors_SMD.3dshapes/R_0402.wrl":
        r"Resistor_SMD.3dshapes\R_0402_1005Metric.step",
    "${KISYS3DMOD}/Inductors_SMD.3dshapes/L_0402.wrl":
        r"Inductor_SMD.3dshapes\L_0402_1005Metric.step",
    "${KISYS3DMOD}/Crystals.3dshapes/Crystal_SMD_5032-2pin_5.0x3.2mm.wrl":
        r"Crystal.3dshapes\Crystal_SMD_5032-2Pin_5.0x3.2mm.step",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    path.write_bytes((json.dumps(data, indent=2) + "\n").encode())


def git(directory, *arguments):
    return subprocess.check_output(["git", "--no-pager", "-C", str(directory), *arguments])


def pose(shape, spec):
    item = shape.copy()
    item.rotate(App.Vector(), App.Vector(*spec["rotation_axis"]), spec["rotation_deg"])
    item.translate(App.Vector(*spec["translation_mm"]))
    return item


def mesh(shape, path):
    points, faces = shape.tessellate(0.10)
    Mesh.Mesh([(points[a], points[b], points[c]) for a, b, c in faces]).write(str(path))
    return {"file": path.name, "sha256": digest(path)}


def contact(shape, enclosure, boxes):
    candidates = []
    for solid in shape.Solids:
        box = solid.BoundBox
        if box.intersect(enclosure.BoundBox) and (
                any(box.intersect(face) for face in boxes)
                or enclosure.isInside(box.Center, 0.000001, True)):
            candidates.append(solid)
    return Part.makeCompound(candidates).common(enclosure) if candidates else Part.Shape()


def intersection_volume(a, b):
    if not a.BoundBox.intersect(b.BoundBox):
        return 0.0
    intersection = a.common(b)
    return 0.0 if intersection.isNull() else round(intersection.Volume, 6)


def unique_connector(exported, dimensions, name):
    candidates = [s for s in exported.Solids if all(
        abs(actual - expected) < 0.02 for actual, expected in zip(
            (s.BoundBox.XLength, s.BoundBox.YLength, s.BoundBox.ZLength), dimensions))]
    if len(candidates) != 1:
        raise ValueError("Expected one " + name + " connector solid")
    return candidates[0]


def trajectory(config):
    outside = config["insertion"]["outside_z_mm"]
    angle = config["insertion"]["approach_angle_deg"]
    flex = config["riser_allowance"]["approach_deg"]
    frames = []

    def add(phase, **changes):
        frame = dict(phase=phase, z_mm=outside, angle_deg=0, riser_deg=0,
                     meter_lift_mm=0, host_lift_mm=0, plugs_present=False,
                     plug_offset_mm=0)
        frame.update(changes)
        if abs(frame["riser_deg"]) > config["riser_allowance"]["maximum_deg"]:
            raise ValueError("Riser allowance exceeded")
        frames.append(frame)

    for i in range(12):
        add("carrier", meter_lift_mm=28, host_lift_mm=28-24*(1-i/11))
    for i in range(12):
        lift = 28 * (1-i/11)
        add("meter", meter_lift_mm=lift, host_lift_mm=lift)
    for i in range(9):
        add("tilt", angle_deg=angle*i/8, riser_deg=flex*i/8)
    for z in range(int(outside), -19, 2):
        add("insert", angle_deg=angle, riser_deg=flex, z_mm=z)
    for i in range(11):
        fraction = 1-i/10
        add("seat", angle_deg=angle*fraction, riser_deg=flex*fraction,
            z_mm=-20*fraction)
    for i in range(10):
        add("plug", z_mm=0, plugs_present=True, plug_offset_mm=24*(1-i/9))
    return frames


def moved(shape, name, frame, config):
    item = shape.copy()
    if name.startswith("plug_"):
        item.translate(App.Vector(frame["plug_offset_mm"], 0, 0))
    if name.startswith(("meter_", "host_", "s3_")):
        lift = frame["meter_lift_mm"] if name.startswith("meter_") else frame["host_lift_mm"]
        item.translate(App.Vector(0, 0, lift))
        allowance = config["riser_allowance"]
        item.rotate(App.Vector(*allowance["pivot_mm"]), App.Vector(*allowance["axis"]),
                    frame["riser_deg"])
    insertion = config["insertion"]
    item.rotate(App.Vector(*insertion["pivot_mm"]), App.Vector(*insertion["tilt_axis"]),
                frame["angle_deg"])
    item.translate(App.Vector(0, 0, frame["z_mm"]))
    return item


def run_cli(cli, arguments, log):
    run = subprocess.run([str(cli), *map(str, arguments)], stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, universal_newlines=True)
    log.write_bytes(run.stdout.encode())
    if run.returncode:
        raise RuntimeError(run.stdout)
    return run.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("cache", "enclosure-step", "molex-step"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--kicad-cli", type=Path,
                        default=Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"))
    parser.add_argument("--models", type=Path,
                        default=Path(r"C:\Program Files\KiCad\10.0\share\kicad\3dmodels"))
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    config_path = ROOT / "mechanical" / "assembly.json"
    config = json.loads(config_path.read_text())
    if digest(args.enclosure_step) != config["enclosure"]["step_sha256"]:
        raise ValueError("Unexpected enclosure STEP")
    if digest(args.molex_step) != MOLEX_SHA:
        raise ValueError("Unexpected supplied Nano-Fit receptacle STEP")
    solids = Part.read(str(args.enclosure_step)).Solids
    if len(solids) != 21:
        raise ValueError("Unexpected Bud assembly structure")
    normalization = dict(rotation_axis=[1, 0, 0], rotation_deg=180,
                         translation_mm=[-solids[0].BoundBox.XMin,
                                         solids[0].BoundBox.YMax,
                                         solids[1].BoundBox.ZMin])
    case = {name: pose(solids[i], normalization) for i, name in enumerate(
        ("body", "base", "cover", "clip", "guard_right", "guard_left"))}
    sources, groups, exports = {}, {}, {}
    substitutions = {}
    for name, spec in config["boards"].items():
        source = ROOT / spec["source"]
        commit = git(source.parent, "rev-parse", "HEAD").decode().strip()
        gitlink = git(ROOT, "ls-files", "--stage", "--",
                      str(source.parent.relative_to(ROOT))).decode().split()
        if len(gitlink) < 2 or gitlink[:2] != ["160000", commit]:
            raise ValueError("Stage the exact committed submodule before export: " + name)
        committed = git(source.parent, "show", "HEAD:" + source.name)
        if committed.replace(b"\r\n", b"\n") != source.read_bytes().replace(b"\r\n", b"\n"):
            raise ValueError("PCB has uncommitted changes: " + name)
        if name == "meter" and commit != METER_COMMIT:
            raise ValueError("Metering board must remain at its original pin")
        sources[name] = dict(source=spec["source"], commit=commit,
                             pcb_sha256=digest(source),
                             committed_pcb_sha256=hashlib.sha256(committed).hexdigest())
        if name != "meter":
            for suffix in (".kicad_sch", ".kicad_pro"):
                electrical = source.with_suffix(suffix)
                blob = git(source.parent, "show", "HEAD:"+electrical.name)
                if blob.replace(b"\r\n", b"\n") != electrical.read_bytes().replace(b"\r\n", b"\n"):
                    raise ValueError("Uncommitted canonical project: " + electrical.name)
            run_cli(args.kicad_cli, [
                "pcb", "drc", "--refill-zones", "--all-track-errors", "--schematic-parity",
                "--format", "json", "--exit-code-violations", "--output",
                args.cache / (name+"-drc.json"), source], args.cache / (name+"-drc.log"))
            run_cli(args.kicad_cli, [
                "sch", "erc", "--format", "json", "--exit-code-violations", "--output",
                args.cache / (name+"-erc.json"), source.with_suffix(".kicad_sch")],
                args.cache / (name+"-erc.log"))
        export_source = source
        if name == "meter":
            changes = {}

            def replace_model(match):
                token = match.group(1)
                old = json.loads(token) if token.startswith('"') else token
                if old in MODEL_ALIASES:
                    target = args.models / MODEL_ALIASES[old]
                elif old.startswith("${KIPRJMOD}"):
                    target = Path(old.replace("${KIPRJMOD}", str(source.parent)))
                else:
                    raise ValueError("Unreviewed legacy meter model: " + old)
                if not target.is_file():
                    raise FileNotFoundError(target)
                changes[old] = dict(path=str(target), sha256=digest(target))
                return "(model " + json.dumps(str(target))

            text = re.sub(r'\(model\s+("(?:\\.|[^"])*"|[^\s()]+)', replace_model,
                          source.read_text())
            export_source = args.cache / "meter-visual.kicad_pcb"
            export_source.write_bytes(text.encode())
            substitutions = changes
        output = args.cache / (name+".step")
        log = run_cli(args.kicad_cli, [
            "pcb", "export", "step", "--force", "--subst-models", "--user-origin",
            "0x0mm", "--output", output, export_source], args.cache / (name+"-export.log"))
        if "Could not add 3D model" in log or "File not found:" in log:
            raise ValueError("Missing exported models: " + name)
        exported = Part.read(str(output))
        pcb = max(exported.Solids, key=lambda s: s.BoundBox.XLength*s.BoundBox.YLength)
        components = [s for s in exported.Solids if not s.isSame(pcb)]
        if name == "host":
            sockets = [s for s in components if
                       abs(s.BoundBox.XLength-2.54) < .02 and
                       abs(s.BoundBox.YLength-20.32) < .02 and
                       abs(s.BoundBox.ZLength-6.6) < .02]
            if len(sockets) != 2:
                raise ValueError("Expected exactly two original full-height socket bodies")
            components = [s for s in components if not any(s.isSame(h) for h in sockets)]
            module = config["module"]
            top = pcb.BoundBox.ZMax
            components += [Part.makeBox(*module["header_size_mm"], App.Vector(x, y, top))
                           for x, y in module["header_xy_mm"]]
            level = top + module["header_size_mm"][2]
            for part in ("pcb", "tft", "usb"):
                x, y = module[part+"_xy_mm"]
                z = level if part == "pcb" else level + module["pcb_size_mm"][2]
                groups["s3_"+part] = pose(Part.makeBox(
                    *module[part+"_size_mm"], App.Vector(x, y, z)), spec)
        groups[name+"_pcb"] = pose(pcb, spec)
        groups[name+"_components"] = pose(Part.makeCompound(components), spec)
        exports[name] = exported
        sources[name]["step_sha256"] = digest(output)
    host_connector = pose(unique_connector(exports["host"], (23, 3.7, 9.2), "host J1"),
                          config["boards"]["host"])
    meter_connector = pose(unique_connector(exports["meter"], (21.5, 4, 6.8), "meter J5"),
                           config["boards"]["meter"])
    meter_pcb = groups["meter_pcb"]
    display = groups["s3_tft"]
    module_pcb = groups["s3_pcb"]
    upper_checks = {
        "carrier_pcb_to_meter_pcb_mm3": intersection_volume(groups["host_pcb"], meter_pcb),
        "s3_pcb_to_meter_pcb_mm3": intersection_volume(module_pcb, meter_pcb),
        "s3_tft_to_meter_pcb_mm3": intersection_volume(display, meter_pcb),
        "s3_usb_to_meter_pcb_mm3": intersection_volume(groups["s3_usb"], meter_pcb),
        "carrier_pcb_to_power_mm3": intersection_volume(
            groups["host_pcb"], Part.makeCompound([groups["power_pcb"],
                                                   groups["power_components"]])),
    }
    if any(value > 0.000001 for value in upper_checks.values()):
        raise ValueError("Lower-display board/component collision: " + json.dumps(upper_checks))
    if (display.BoundBox.ZMax > meter_pcb.BoundBox.ZMax + 0.01
            or module_pcb.BoundBox.XMax >= meter_pcb.BoundBox.XMin):
        raise ValueError("Display must be flush/below the meter and left of the riser")
    upper_alignment = dict(
        meter_pcb_top_z_mm=round(meter_pcb.BoundBox.ZMax, 6),
        carrier_pcb_top_z_mm=round(groups["host_pcb"].BoundBox.ZMax, 6),
        s3_pcb_top_z_mm=round(module_pcb.BoundBox.ZMax, 6),
        tft_top_z_mm=round(display.BoundBox.ZMax, 6),
        usb_top_z_mm=round(groups["s3_usb"].BoundBox.ZMax, 6),
        meter_pcb_left_x_mm=round(meter_pcb.BoundBox.XMin, 6),
        s3_pcb_right_x_mm=round(module_pcb.BoundBox.XMax, 6),
        checked_non_mating_overlaps_mm3=upper_checks,
        host_j1_meter_j5_intersection_mm3=intersection_volume(host_connector, meter_connector),
        connector_row_center_difference_y_mm=round(
            host_connector.BoundBox.Center.y-meter_connector.BoundBox.Center.y, 6),
        connector_note=("Intersections include mated model contacts and potential housing clashes; "
                        "their value does not verify engagement. J1 footprint/model identity and "
                        "the physical connector seat require independent measurement."))
    headers = [s for s in exports["power"].Solids if
               14.5 < s.BoundBox.XLength < 14.8 and
               10.8 < s.BoundBox.YLength < 11.1 and
               12.2 < s.BoundBox.ZLength < 12.5]
    if len(headers) != 2:
        raise ValueError("Expected two original Nano-Fit headers")
    receptacle = Part.read(str(args.molex_step))
    matrix = App.Matrix()
    matrix.A11, matrix.A12, matrix.A13 = 0, 0, -1
    matrix.A21, matrix.A22, matrix.A23 = 1, 0, 0
    matrix.A31, matrix.A32, matrix.A33 = 0, -1, 0
    for i, header in enumerate(sorted(headers, key=lambda s: s.BoundBox.YMin)):
        h = pose(header, config["boards"]["power"]).BoundBox
        plug = receptacle.transformGeometry(matrix)
        p = plug.BoundBox
        plug.translate(App.Vector(h.XMax-1-p.XMin,
                                  (h.YMin+h.YMax-p.YMin-p.YMax)/2, 1.555-p.ZMin))
        groups["plug_"+str(i+1)] = plug
    entries = {name: mesh(shape, args.cache / (name+".stl"))
               for name, shape in {**case, **groups}.items()}
    boxes = [face.BoundBox for face in case["body"].Faces]
    for box in boxes:
        box.enlarge(0.000001)
    frames = trajectory(config)
    first = None
    for i, frame in enumerate(frames):
        hits, volumes = [], {}
        if frame["phase"] not in ("meter", "carrier"):
            for name, shape in groups.items():
                if name.startswith("plug_") and not frame["plugs_present"]:
                    continue
                overlap = contact(moved(shape, name, frame, config), case["body"], boxes)
                if not overlap.isNull() and overlap.Volume > 0.000001:
                    hits.append(overlap)
                    volumes[name] = round(overlap.Volume, 6)
        frame["per_group_intersection_mm3"] = volumes
        frame["summed_intersection_mm3"] = round(sum(volumes.values()), 6)
        if frame["summed_intersection_mm3"] > THRESHOLD and first is None:
            first = i
        if hits:
            frame["contact_mesh"] = mesh(Part.makeCompound(hits),
                                         args.cache / ("contact-%03d.stl" % i))
        print("Frame %d/%d %s: %.6f mm^3" % (
            i+1, len(frames), frame["phase"], frame["summed_intersection_mm3"]), flush=True)
    report = dict(
        revision="2.0", units="mm; intersections in mm^3", sources=sources,
        config_sha256=digest(config_path), enclosure_sha256=digest(args.enclosure_step),
        molex_receptacle_sha256=MOLEX_SHA, meter_visual_model_substitutions=substitutions,
        upper_alignment=upper_alignment,
        intersection_threshold_mm3=THRESHOLD, first_contact_frame=first,
        collision_free_at_samples=first is None, frames=frames,
        statement="Nominal assembly and insertion animation, NOT a verified collision-free path.",
        limitations=[
            "The user reports a fitting cut enclosure; this model is the uncut vendor body.",
            "The motion continues after contact to illustrate the nominal seat; contacts are highlighted.",
            "Meter/carrier mating trajectories and seating datums require physical measurement.",
            "The carrier is attached from below before the combined pair enters the PCI socket; Nano-Fit plugs are absent until after nominal seating.",
            "The lower-left carrier datum is a provisional user-observation-constrained model, not a measured physical connector seat.",
            config["module"]["assumption"], config["riser_allowance"]["assumption"],
            "Two 6.6 mm socket bodies are replaced visually with 2.5 mm proxies; PCB unchanged.",
            "Nano-Fit receptacle seating, J1 model identity and wire bending remain provisional.",
            "Meter package STEP aliases are visual equivalents; the pinned meter PCB is unmodified.",
            "Sampled rigid BRep contacts do not validate continuous motion, tolerances or electrical safety.",
            "ERC/DRC passing is not fabrication, SELV, isolation or mains safety approval."])
    write_json(args.cache / "fit-report.json", report)
    write_json(args.cache / "meshes.json", entries)
    print("Saved %d frames; first modeled contact: %s" % (len(frames), first), flush=True)


if __name__ == "__main__":
    main()
