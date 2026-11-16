# DIN v2.0 mechanical fit

This is a source-based **engineering fit study**, not a release approval.
The parent pins the changed power board while leaving unchanged metering and
host submodule revisions explicit. No vendor enclosure CAD is redistributed.
It selects the separate **experimental** v2.0-fit layout, not the unchanged
legacy production PCB. Three unrouted CT connections block fabrication.

## Reproduce

Initialize the three submodules named in `assembly.json`. Use KiCad 10 CLI,
FreeCAD with its bundled Python, and Blender. On the development Windows machine:

```powershell
$cache = Join-Path $env:TEMP "din-v2-fit"
& "C:\Program Files\FreeCAD 0.19\bin\python.exe" .\mechanical\build_assembly.py --cache $cache
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --background --python .\mechanical\render_assembly.py -- --cache $cache --output .\mechanical\renders
```

The first command downloads the manufacturer STEP into the cache and checks its
SHA-256 before normalizing it. It exports the pinned PCB files, logs missing
models, performs solid-intersection tests, writes `fit-report.json`, and saves
an editable FreeCAD assembly in the cache. The second produces actual CAD
renders and saves a Blender scene there. Keep the cache out of Git.
FreeCAD/Blender files and rendered images are derived artifacts; the reconstruction
interface is the dimensioned manifest plus pinned board sources.

## Datums and limits

Bud's [DMB-4770 product page](https://www.budind.com/product/general-use-boxes/din-rail-mount-multi-board-box-series/dmb-4770/)
links the [two-sheet drawing](https://www.budind.com/wp-content/uploads/2019/01/hb4770.pdf)
and STEP source. Board A is 86.9 x 32.8 x 1.6 mm; boards B/C are nominally
58.7 x 32.5 mm and 42 x 32 mm. The legacy architecture uses **a vertical riser**,
not three boards occupying those three horizontal rails.

The vendor assembly includes reference PCBs and terminal blocks. These are
excluded when inserting the project's own boards; the body, base, cover, clip
and two guards remain. Coordinates use the base-PCB underside as Z=0, X along
the 90.2 mm enclosure length, and Y across its 36.3 mm width. The vendor's large
STEP coordinate offset is normalized, not approximated with a rectangular box.

The power PCB is anchored to Bud's board-A position. The metering plane and
host height are **candidate mating transforms**: measure socket insertion
depth, row alignment and installed header height before accepting them.
The host's 11.43 x 2.032 mm isolation slot remains intact. The legacy Wemos STEP
is empty, and no complete display/headers/cable-bend model has been specified.
Their omission is a blocker, not evidence that they fit.

The supplied J1 Phoenix STEP appears to represent a different terminal family
from the footprint identification. Verify the fitted part number and model
alignment before moving J1 or claiming that its enclosure collisions are real
hardware interference. Do not shift a mismatched model merely to hide overlap.

Static tests report overlap volume for each board against every enclosure part,
and between boards. Rear insertion tests sample power plus metering at 0/10/20/30
degrees, 2 mm translation increments and at most 1 degree rotation increments.
A sampled clear path is **not** a continuous swept-volume or tolerance proof.
Connector contact geometry, latch flex, wiring bend radius, guards and field
access must be reviewed separately. Never call a colliding candidate "fits".

## Release gates

Confirm the physical enclosure's part number and clear-cover variant. Resolve
reported solid intersections and check a physical dry-fit with all mating plugs,
Wemos/header stack, selected display, battery and wires. Check installation and
removal with the base/guards detached, not just the final assembled pose.

The v2.0-fit power-board change addresses connector overhang; it does not convert
the old mains circuit to the parent roadmap's SELV developer architecture.
Preserve voltage/current conditioning, GNDA/GNDPWR separation, and the host's
isolation slot. Fresh-zone PCB DRC, safety separation, keyed legacy-riser
compatibility and the dedicated SELV electrical redesign remain independent gates
under [whatnick/DIN_Rail_EnergyMonitor#2](https://github.com/whatnick/DIN_Rail_EnergyMonitor/issues/2)
and [whatnick/DIN_Rail_EnergyMonitor#3](https://github.com/whatnick/DIN_Rail_EnergyMonitor/issues/3).
