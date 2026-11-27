"""Measure host-PCB-only contact sensitivity; shifted connectors are not mated."""

import argparse
import json
from pathlib import Path

import FreeCAD as App
import Part

from build_assembly import ROOT, contact, digest, moved, pose, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--enclosure-step", type=Path, required=True)
    args = parser.parse_args()
    report_path = args.cache / "fit-report.json"
    report = json.loads(report_path.read_text())
    config_path = ROOT / "mechanical" / "assembly.json"
    config = json.loads(config_path.read_text())
    host = args.cache / "host.step"
    if (digest(config_path) != report["config_sha256"]
            or digest(args.enclosure_step) != report["enclosure_sha256"]
            or digest(host) != report["sources"]["host"]["step_sha256"]):
        raise ValueError("Height sensitivity requires the same sources as the motion report")
    frame = report["frames"][report["first_contact_frame"]]
    solids = Part.read(str(args.enclosure_step)).Solids
    normalization = dict(rotation_axis=[1, 0, 0], rotation_deg=180,
                         translation_mm=[-solids[0].BoundBox.XMin,
                                         solids[0].BoundBox.YMax,
                                         solids[1].BoundBox.ZMin])
    body = pose(solids[0], normalization)
    boxes = [face.BoundBox for face in body.Faces]
    for box in boxes:
        box.enlarge(0.000001)
    geometry = Part.read(str(host))
    pcb = max(geometry.Solids, key=lambda solid: solid.BoundBox.XLength*solid.BoundBox.YLength)
    pcb = pose(pcb, config["boards"]["host"])
    samples = []
    for delta in (0, -1, -2):
        shifted = pcb.copy()
        shifted.translate(App.Vector(0, 0, delta))
        overlap = contact(moved(shifted, "host_pcb", frame, config), body, boxes)
        samples.append(dict(host_only_z_shift_mm=delta,
                            host_pcb_body_overlap_mm3=0 if overlap.isNull()
                            else round(overlap.Volume, 6)))
    output = dict(
        motion_report_sha256=digest(report_path), host_step_sha256=digest(host),
        enclosure_sha256=digest(args.enclosure_step),
        pose=dict(angle_deg=frame["angle_deg"], z_mm=frame["z_mm"],
                  riser_deg=frame["riser_deg"]),
        samples=samples,
        limitation=("One-pose host-PCB-only mathematical sensitivity. The host connector, "
                    "components and S3 do not move in this calculation; shifts do not preserve "
                    "mating and are not proposed placements, clearance paths or fit validation."))
    write_json(ROOT / "mechanical" / "height-sensitivity.json", output)
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
