"""Export pinned PCBs, normalize Bud CAD, test fit, and tessellate for rendering.

Run with FreeCAD's bundled Python. Vendor CAD stays in a local cache, not Git.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

import FreeCAD as App
import Mesh
import Part


ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "mechanical" / "assembly.json").read_text())
TOLERANCE_MM3 = 0.01


def posed(shape, spec):
    result = shape.copy()
    result.rotate(App.Vector(), App.Vector(*spec["rotation_axis"]), spec["rotation_deg"])
    result.translate(App.Vector(*spec["translation_mm"]))
    return result


def intersect(a, b):
    if not a.BoundBox.intersect(b.BoundBox):
        return 0.0
    return round(a.common(b).Volume, 6)


def bounds(shape):
    box = shape.BoundBox
    return {"min": [box.XMin, box.YMin, box.ZMin],
            "max": [box.XMax, box.YMax, box.ZMax]}


def export_mesh(shape, path):
    vertices, faces = shape.tessellate(0.08)
    mesh = Mesh.Mesh([(vertices[a], vertices[b], vertices[c]) for a, b, c in faces])
    mesh.write(str(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--kicad-cli", default=r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
    parser.add_argument("--power-source", type=Path)
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    vendor = args.cache / "hbdmb4770.step"
    if not vendor.exists():
        urllib.request.urlretrieve(CONFIG["enclosure"]["step_url"], str(vendor))
    digest = hashlib.sha256(vendor.read_bytes()).hexdigest()
    if digest != CONFIG["enclosure"]["step_sha256"]:
        raise ValueError("Vendor STEP hash mismatch; review the source before using new geometry")
    vendor_solids = Part.read(str(vendor)).Solids
    if len(vendor_solids) != 21:
        raise ValueError("Unexpected Bud STEP structure")
    body, base = vendor_solids[:2]
    normalization = {
        "rotation_axis": [1, 0, 0], "rotation_deg": 180,
        "translation_mm": [-body.BoundBox.XMin, body.BoundBox.YMax, base.BoundBox.ZMin],
    }
    case_names = ["body", "base", "cover", "clip", "guard_right", "guard_left"]
    case = {name: posed(vendor_solids[i], normalization)
            for i, name in enumerate(case_names)}
    boards = {}
    sources = {}
    missing_models = {}
    for name, spec in CONFIG["boards"].items():
        source = args.power_source if name == "power" and args.power_source else ROOT / spec["source"]
        output = args.cache / (name + ".step")
        command = [args.kicad_cli, "pcb", "export", "step", "--force", "--subst-models",
                   "--user-origin", "0x0mm", "--output", str(output), str(source)]
        run = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        (args.cache / (name + "-export.log")).write_text(run.stdout)
        if run.returncode:
            raise RuntimeError(run.stdout)
        boards[name] = posed(Part.read(str(output)), spec)
        sources[name] = {
            "pcb_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "repository_commit": subprocess.check_output(
                ["git", "-C", str(source.parent), "rev-parse", "HEAD"], text=True).strip(),
        }
        missing_models[name] = [line for line in run.stdout.splitlines()
                                if "Could not add 3D model" in line or "File not found:" in line]
    # This asset is an empty STEP in the pinned host repository, even though export exits successfully.
    host_asset = ROOT / "KiCAD_PCBs" / "din_isolated_SPI" / "3dmodels" / "wemos_d1_mini_pro_board.step"
    wemos_missing = not Part.read(str(host_asset)).Solids
    display = Part.makeBox(*CONFIG["display_reservation"]["size_mm"],
                           App.Vector(*CONFIG["display_reservation"]["origin_mm"]))
    collisions = {
        name: {part: intersect(board, shape) for part, shape in case.items()}
        for name, board in boards.items()
    }
    board_pairs = {a + ":" + b: intersect(boards[a], boards[b])
                   for a, b in [("power", "meter"), ("power", "host"), ("meter", "host")]}
    reservation_collisions = {name: intersect(display, shape) for name, shape in case.items()}
    print("Static board/enclosure intersections: " + json.dumps(collisions), flush=True)
    lower = Part.makeCompound([boards["power"], boards["meter"]])
    settings = CONFIG["insertion"]
    paths = []
    for angle in settings["candidate_angles_deg"]:
        frames = []
        # Translate towards the open rear, then progressively untilt into the seat.
        for offset in range(-80, -19, settings["translation_step_mm"]):
            frames.append((float(angle), float(offset)))
        steps = max(20, int(angle / settings["angular_step_deg"]))
        for step in range(steps + 1):
            fraction = step / steps
            frames.append((angle * (1 - fraction), -20 * (1 - fraction)))
        hits = []
        for index, (tilt, offset) in enumerate(frames):
            shape = lower.copy()
            shape.rotate(App.Vector(*settings["pivot_mm"]),
                         App.Vector(*settings["tilt_axis"]), tilt)
            shape.translate(App.Vector(0, 0, offset))
            volume = intersect(shape, case["body"])
            if volume > TOLERANCE_MM3:
                hits.append({"frame": index, "angle_deg": tilt, "z_offset_mm": offset,
                             "intersection_mm3": volume})
                break
        paths.append({"initial_angle_deg": angle, "samples": len(frames),
                      "samples_checked": index + 1,
                      "clear_at_samples": not hits, "collision_count": len(hits),
                      "first_collision": hits[0] if hits else None})
        print("Insertion candidate: " + json.dumps(paths[-1]), flush=True)
    report = {
        "revision": CONFIG["revision"], "sources": sources, "vendor_sha256": digest,
        "units": "mm; intersections in mm^3", "intersection_threshold_mm3": TOLERANCE_MM3,
        "bounds": {name: bounds(shape) for name, shape in {**case, **boards}.items()},
        "board_to_enclosure_intersections_mm3": collisions,
        "board_to_board_intersections_mm3": board_pairs,
        "display_reservation_to_enclosure_mm3": reservation_collisions,
        "rear_insertion_paths": paths, "missing_export_models": missing_models,
        "empty_wemos_step": wemos_missing,
        "release_gate": "BLOCKED: missing host/display/mated-cable models, provisional seating datums, and legacy electrical safety/DRC review",
        "limitations": [
            "DMB-4770 inferred from exact manufacturer board-A dimensions; confirm physical enclosure marking.",
            "Only rigid sampled positions are tested; flexing latches, tolerances and cable bends are not simulated.",
            "Standard cover geometry represents the clear-cover shape; transparency is illustrative.",
            "Intersections at mating connectors require per-part review, not automatic dismissal.",
            "Display is a reserved envelope, not a sourced display model.",
            "Legacy base still has direct-mains circuits; v2.0-fit is not an approved SELV design.",
            "Power J1 footprint and supplied Phoenix STEP part identity/alignment disagree; resolve before changing its placement.",
            "Power prototype has three unconnected CT items and a starved GNDA thermal; not for fabrication."
        ],
    }
    mesh_info = []
    for name, shape in {**case, **boards, "display_reservation": display}.items():
        mesh_path = args.cache / (name + ".stl")
        export_mesh(shape, mesh_path)
        mesh_info.append({"name": name, "file": str(mesh_path)})
    (args.cache / "meshes.json").write_text(json.dumps(mesh_info, indent=2))
    (ROOT / "mechanical" / "fit-report.json").write_text(json.dumps(report, indent=2) + "\n")
    document = App.newDocument("DIN_v2_fit")
    for name, shape in {**case, **boards, "display_reservation": display}.items():
        obj = document.addObject("PartDesign::Feature", name)
        obj.Shape = shape
    document.recompute()
    document.saveAs(str(args.cache / "DIN_v2_fit.FCStd"))
    print(json.dumps({"static_intersections_mm3": collisions, "insertion": paths,
                      "release_gate": report["release_gate"]}, indent=2))


if __name__ == "__main__":
    main()
