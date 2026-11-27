"""Render the source-matched three-PCB assembly and nominal insertion sequence."""

import argparse
import hashlib
import json
from math import radians
from pathlib import Path
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector


ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--cache", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args(sys.argv[sys.argv.index("--")+1:])
args.output.mkdir(parents=True, exist_ok=True)
report_path = args.cache / "fit-report.json"
report = json.loads(report_path.read_text())
config_path = ROOT / "mechanical" / "assembly.json"
if hashlib.sha256(config_path.read_bytes()).hexdigest() != report["config_sha256"]:
    raise ValueError("Assembly configuration changed after the contact study")
config = json.loads(config_path.read_text())
entries = json.loads((args.cache / "meshes.json").read_text())
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = 12
scene.cycles.use_denoising = True
scene.cycles.transparent_max_bounces = 32
scene.render.resolution_x = 1024
scene.render.resolution_y = 768
scene.render.resolution_percentage = 100
scene.world.color = (.3, .3, .3)
scene.view_settings.view_transform = "AgX"


def material(name, color, alpha=1):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    surface = nodes.new("ShaderNodeBsdfPrincipled")
    surface.inputs["Base Color"].default_value = (*color, 1)
    surface.inputs["Roughness"].default_value = .45
    if alpha < 1:
        transparent = nodes.new("ShaderNodeBsdfTransparent")
        mix = nodes.new("ShaderNodeMixShader")
        mix.inputs[0].default_value = alpha
        mat.node_tree.links.new(transparent.outputs[0], mix.inputs[1])
        mat.node_tree.links.new(surface.outputs[0], mix.inputs[2])
        mat.node_tree.links.new(mix.outputs[0], output.inputs[0])
    else:
        mat.node_tree.links.new(surface.outputs[0], output.inputs[0])
    return mat


materials = {
    "body": material("Uncut body", (.68, .73, .79), .12),
    "cover": material("Clear cover assumption", (.6, .8, .9), .10),
    "base": material("Base", (.36, .38, .42)),
    "guard": material("Guard", (.65, .7, .75), .18),
    "power_pcb": material("Power", (.025, .32, .14)),
    "meter_pcb": material("Unchanged meter", (.025, .32, .48)),
    "host_pcb": material("Isolated carrier", (.38, .07, .5)),
    "s3_pcb": material("S3 PCB proxy", (.03, .17, .65)),
    "s3_tft": material("Integrated TFT proxy", (.01, .015, .02)),
    "s3_usb": material("USB proxy", (.65, .7, .75)),
    "component": material("Components", (.19, .21, .24)),
    "plug": material("Nano-Fit plugs", (.9, .84, .67)),
    "contact": material("Actual sampled overlap", (1, 0, 0)),
}


def load(entry, name):
    path = args.cache / entry["file"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
        raise ValueError("Changed mesh: " + name)
    bpy.ops.wm.stl_import(filepath=str(path))
    obj = bpy.context.object
    key = name if name in materials else (
        "guard" if name.startswith("guard") else
        "plug" if name.startswith("plug") else "component")
    obj.data.materials.append(materials[key])
    return obj


objects = {name: load(entry, name) for name, entry in entries.items()}
case_names = {"body", "base", "cover", "clip", "guard_left", "guard_right"}
contacts = {}
for i, frame in enumerate(report["frames"]):
    if "contact_mesh" in frame:
        contacts[i] = load(frame["contact_mesh"], "contact")
        contacts[i].hide_render = True
bpy.ops.object.camera_add()
camera = bpy.context.object
camera.data.type = "ORTHO"
scene.camera = camera
for location, energy, size in (
        ((40, -60, 130), 200000, 100),
        ((110, 70, 65), 150000, 100),
        ((-40, 35, -30), 180000, 90)):
    bpy.ops.object.light_add(type="AREA", location=location)
    light = bpy.context.object
    light.data.energy = energy
    light.data.shape = "DISK"
    light.data.size = size
    light.rotation_euler = (Vector((45, 18, -20))-light.location).to_track_quat("-Z", "Y").to_euler()


def rotation(spec, angle):
    pivot = Vector(spec["pivot_mm"])
    return Matrix.Translation(pivot) @ Matrix.Rotation(
        radians(angle), 4, Vector(spec.get("axis", spec.get("tilt_axis")))) @ Matrix.Translation(-pivot)


def transform(name, frame):
    matrix = Matrix.Translation((0, 0, frame["z_mm"])) @ rotation(
        config["insertion"], frame["angle_deg"])
    if name.startswith("plug_"):
        matrix = matrix @ Matrix.Translation((frame["plug_offset_mm"], 0, 0))
    if name.startswith(("meter_", "host_", "s3_")):
        lift = frame["meter_lift_mm"] if name.startswith("meter_") else frame["host_lift_mm"]
        matrix = matrix @ rotation(config["riser_allowance"], frame["riser_deg"]) @ Matrix.Translation(
            (0, 0, lift))
    return matrix


def setup(frame, closed=False):
    for obj in contacts.values():
        obj.hide_render = True
    for name, obj in objects.items():
        if name in case_names:
            obj.hide_render = frame["phase"] in ("meter", "carrier") or (
                not closed and name != "body")
            obj.matrix_world = Matrix.Identity(4)
        else:
            obj.matrix_world = transform(name, frame)
            obj.hide_render = name.startswith("plug_") and not frame["plugs_present"]
    bpy.context.view_layer.update()


def corners():
    return [obj.matrix_world @ Vector(point) for obj in objects.values()
            if not obj.hide_render for point in obj.bound_box]


def aim(points):
    low = Vector(tuple(min(p[i] for p in points) for i in range(3)))
    high = Vector(tuple(max(p[i] for p in points) for i in range(3)))
    center = (low+high)/2
    direction = Vector((100, -138, 87)).normalized()
    camera.location = center + direction*320
    camera.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()
    inverse = camera.rotation_euler.to_matrix().transposed()
    projected = [inverse @ (point-center) for point in points]
    xmin, xmax = min(p.x for p in projected), max(p.x for p in projected)
    ymin, ymax = min(p.y for p in projected), max(p.y for p in projected)
    camera.location += camera.rotation_euler.to_matrix() @ Vector(((xmin+xmax)/2, (ymin+ymax)/2, 0))
    camera.data.ortho_scale = max(xmax-xmin, (ymax-ymin)*4/3)*1.32
    bpy.context.view_layer.update()


phase_points = {"assembly": [], "insertion": []}
for frame in report["frames"]:
    setup(frame)
    phase_points["assembly" if frame["phase"] in ("meter", "carrier") else "insertion"].extend(corners())
receipts = []
for i, frame in enumerate(report["frames"]):
    setup(frame)
    aim(phase_points["assembly" if frame["phase"] in ("meter", "carrier") else "insertion"])
    locator = None
    if i in contacts:
        obj = contacts[i]
        obj.hide_render = False
        center = sum((Vector(p) for p in obj.bound_box), Vector())/8
        point = world_to_camera_view(scene, camera, center)
        locator = [round(point.x*1024), round((1-point.y)*768)]
    output = args.output / ("frame-%03d.png" % i)
    scene.render.filepath = str(output)
    bpy.ops.render.render(write_still=True)
    receipts.append(dict(file=output.name, sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                         contact_locator_px=locator))
setup(report["frames"][-1], closed=True)
aim(corners())
scene.render.filepath = str(args.output / "seated.png")
bpy.ops.render.render(write_still=True)
receipt = dict(report_sha256=hashlib.sha256(report_path.read_bytes()).hexdigest(),
               resolution=[1024, 768], frames=receipts,
               seated_sha256=hashlib.sha256((args.output / "seated.png").read_bytes()).hexdigest())
(args.output / "render-manifest.json").write_bytes((json.dumps(receipt, indent=2)+"\n").encode())
