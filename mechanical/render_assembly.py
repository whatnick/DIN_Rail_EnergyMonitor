"""Render FreeCAD-tessellated assembly geometry with Blender in background."""

import argparse
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector


parser = argparse.ArgumentParser()
parser.add_argument("--cache", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--views", nargs="+", default=["assembly", "exploded", "rear-insertion-study"],
                    choices=["assembly", "exploded", "rear-insertion-study"])
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
args.output.mkdir(parents=True, exist_ok=True)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = 48
scene.render.resolution_x = 1500
scene.render.resolution_y = 1050
scene.render.resolution_percentage = 100
scene.world.color = (0.3, 0.3, 0.3)
scene.view_settings.view_transform = "AgX"


def material(name, color, alpha=1):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    surface = nodes.new("ShaderNodeBsdfPrincipled")
    surface.inputs["Base Color"].default_value = (*color, 1)
    surface.inputs["Roughness"].default_value = 0.35
    if alpha < 1:
        transparent = nodes.new("ShaderNodeBsdfTransparent")
        mix = nodes.new("ShaderNodeMixShader")
        mix.inputs[0].default_value = alpha
        mat.node_tree.links.new(transparent.outputs[0], mix.inputs[1])
        mat.node_tree.links.new(surface.outputs[0], mix.inputs[2])
        mat.node_tree.links.new(mix.outputs[0], out.inputs[0])
    else:
        mat.node_tree.links.new(surface.outputs[0], out.inputs[0])
    return mat


materials = {
    "body": material("Ghosted manufacturer body", (0.64, 0.69, 0.74), 0.16),
    "base": material("Base", (0.47, 0.5, 0.55)),
    "cover": material("Clear-cover representative", (0.55, 0.78, 0.9), 0.12),
    "clip": material("Rail clip", (0.12, 0.14, 0.18)),
    "guard_right": material("Terminal guards", (0.75, 0.77, 0.8), 0.25),
    "power": material("Power board", (0.025, 0.27, 0.14)),
    "meter": material("Metering riser", (0.025, 0.3, 0.45)),
    "host": material("Host/display carrier", (0.25, 0.08, 0.43)),
    "display_reservation": material("UNSPECIFIED display keep-out", (0.95, 0.48, 0.04), 0.5),
}
objects = {}
for entry in json.loads((args.cache / "meshes.json").read_text()):
    bpy.ops.wm.stl_import(filepath=entry["file"])
    obj = bpy.context.object
    obj.name = entry["name"]
    obj.data.materials.append(materials.get(obj.name, materials["guard_right"]))
    objects[obj.name] = obj

bpy.ops.object.camera_add(location=(145, -120, 110))
camera = bpy.context.object
camera.rotation_euler = (Vector((45.1, 18.15, 23)) - camera.location).to_track_quat("-Z", "Y").to_euler()
camera.data.type = "ORTHO"
camera.data.ortho_scale = 140
scene.camera = camera
for location, energy, size in [((40, -60, 150), 180000, 100),
                               ((110, 70, 100), 140000, 80),
                               ((-40, 35, 70), 100000, 70)]:
    bpy.ops.object.light_add(type="AREA", location=location)
    light = bpy.context.object
    light.data.energy = energy
    light.data.shape = "DISK"
    light.data.size = size
    light.rotation_euler = (Vector((45, 18, 20)) - light.location).to_track_quat("-Z", "Y").to_euler()


def render(name):
    if name not in args.views:
        return
    bpy.context.view_layer.update()
    corners = [
        obj.matrix_world @ Vector(corner)
        for obj in objects.values() if not obj.hide_render
        for corner in obj.bound_box
    ]
    low = Vector(tuple(min(p[i] for p in corners) for i in range(3)))
    high = Vector(tuple(max(p[i] for p in corners) for i in range(3)))
    center = (low + high) / 2
    direction = Vector((100, -138, 87)).normalized()
    camera.location = center + direction * 240
    camera.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()
    inverse_rotation = camera.rotation_euler.to_matrix().transposed()
    projected = [inverse_rotation @ (p - center) for p in corners]
    width = max(p.x for p in projected) - min(p.x for p in projected)
    height = max(p.y for p in projected) - min(p.y for p in projected)
    screen_mid = Vector(((max(p.x for p in projected) + min(p.x for p in projected)) / 2,
                         (max(p.y for p in projected) + min(p.y for p in projected)) / 2, 0))
    camera.location += camera.rotation_euler.to_matrix() @ screen_mid
    camera.data.sensor_fit = "HORIZONTAL"
    camera.data.ortho_scale = max(width, height * 1500 / 1050) * 1.12
    bpy.context.view_layer.update()
    from bpy_extras.object_utils import world_to_camera_view
    framed = [world_to_camera_view(scene, camera, point) for point in corners]
    if any(not (0 < p.x < 1 and 0 < p.y < 1) for p in framed):
        raise RuntimeError(f"{name}: assembly bounds extend outside the camera frame")
    scene.render.filepath = str(args.output / (name + ".png"))
    bpy.ops.render.render(write_still=True)


render("assembly")
offsets = {
    "base": (0, 0, -25), "clip": (-15, 0, -30), "cover": (0, 0, 50),
    "guard_left": (-25, 0, 5), "guard_right": (25, 0, 5),
    "meter": (15, 0, 12), "host": (0, 0, 25), "display_reservation": (0, 0, 35),
}
for name, offset in offsets.items():
    objects[name].location += Vector(offset)
camera.data.ortho_scale = 185
render("exploded")
for name, offset in offsets.items():
    objects[name].location -= Vector(offset)
for name in ["base", "clip", "cover", "guard_left", "guard_right", "host", "display_reservation"]:
    objects[name].hide_render = True
pivot = Vector((45.1, 18.15, 1.6))
from mathutils import Matrix
from math import radians
rotation = Matrix.Translation(pivot) @ Matrix.Rotation(radians(20), 4, "Y") @ Matrix.Translation(-pivot)
for name in ["power", "meter"]:
    objects[name].matrix_world = Matrix.Translation(Vector((0, 0, -20))) @ rotation @ objects[name].matrix_world
camera.data.ortho_scale = 145
render("rear-insertion-study")
bpy.ops.wm.save_as_mainfile(filepath=str(args.cache / "DIN_v2_fit.blend"))
