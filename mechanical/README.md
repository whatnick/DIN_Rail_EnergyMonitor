# Canonical v2.0 assembly

`assembly.json` records tool-neutral dimensions, transforms and assumptions.
The active pipeline contains no alternate PCB candidates. Power and carrier
come from the exact committed submodule revisions; the metering repository
remains pinned at `9230d0efbb124c0492c8161200cb30ad9d554fdd`.

The shortened power board uses four R1 mm corners; the carrier uses four
R2 mm corners and retains all four sides of its isolation slot. Connector
datums and electrical routing are preserved. The power R2 trial was rejected
because it reduced the IN2- copper-to-edge clearance.

## What the animation establishes

The carrier attaches from below to the unchanged metering riser; the combined
pair then enters the power-board PCI socket. The complete set is rotated and
inserted from the rear without its Nano-Fit plugs, which are attached only
after seating. Base, clip, guards and cover are removed during insertion.
The separate seated image restores those enclosure pieces illustratively.
Mating trajectories are explanatory, not verified connector engagement paths.

The controller is an installed LOLIN S3 Mini Pro module with integrated TFT,
not a redesigned fourth PCB. Its 25.4 x 34.3 mm outline is represented by
bounding geometry. PCB thickness, display/USB height, underside parts and
the 2.5 mm seated header gap need measurement. Two exported 6.6 mm socket
bodies are replaced **only in the visualization** by shorter proxies.
The inherited carrier pinout has not been qualified for S3 electrical use.
Following the user's physical observation, the carrier and module are
shifted together 4.5 mm left and 7.075 mm down from the earlier provisional
assembly. With the assumed 2.5 mm short-header gap and 2 mm TFT proxy, the
TFT top is flush with the metering PCB top and the module lies to its left.
These dimensions are an illustrative starting datum, not measurements;
the taller USB proxy may project above the meter. No PCB is modified.
Meter and carrier datums, connector seating and the assumed short-header
gap still require physical measurement.
Molex specifies 3.95 mm mated height for the 53290/52418 family, but the
connector pair mounts perpendicular boards; do not subtract that dimension
from the assembly's vertical height without a verified mating drawing and
PCB reference planes.
Carrier J1's schematic/STEP specify **53290-1080** while its footprint is
named for **53253-1070** (Micro-Latch); the meter uses **52418-1010**.
The 53290 drawing identifies the 52418 series as its mate, but the footprint,
model offsets, installed parts and pin engagement have not been reconciled.
This mismatch prevents treating the rendered connector seat as authoritative.
[53290 drawing](https://docs.rs-online.com/9e1e/0900766b80f757d7.pdf)

The prior higher datum allowed the carrier and meter PCB solids to overlap.
The lower-left model eliminates that modeled PCB-to-PCB intersection. The
two inherited connector solids still intersect slightly; some may represent
intended mating contacts, but model offsets and the actual mating parts are
unverified. Do not treat this geometry as a connector fit approval.

At the 20-degree / -28 mm sample with -3 degrees of riser allowance, the
earlier carrier/body overlap was 1.952 mm^3; the adjusted carrier has no
overlap at that sample. The unchanged metering PCB still overlaps the
uncut body by 0.041 mm^3, and later poses have additional contacts. This is
not a collision-free insertion or a comparison against the actual cut enclosure.

The meter/carrier/module group is allowed up to 3 degrees of rigid rotation
about the riser datum. At a 31 mm lever arm this corresponds to approximately
1.62 mm lateral travel. This is not a strain, solder-joint, socket-retention
or fatigue model. The illustrated allowance returns to zero at the nominal seat.

**The animation is not a clear-path result.** It continues after the first
sampled intersection so the complete nominal motion can be understood.
Red geometry denotes computed BRep overlap with the uncut enclosure body;
yellow rings locate contacts. Volumes are sums across groups, not a Boolean
union or a clearance-distance measurement. Samples are not a continuous sweep.
The user reports a fitting enclosure with bottom cuts; no guessed cuts have
been subtracted from the vendor CAD.

`fit-report.json` records every sampled pose, first contact, per-group overlap,
source commits/PCB hashes, vendor-model hashes and legacy meter model aliases.
Enclosure checks are skipped during the outside `carrier` and `meter`
mating phases; their zero overlap values are placeholders, not clearance tests.
`publication-manifest.json` records checksums, media sizes, timing and successful
decoding of every GIF/MP4 frame.

## Reproduce on Windows

Requirements: KiCad 10 with its standard STEP library, FreeCAD Python with
`Part`/`Mesh`, Blender, normal Python with Pillow, and FFmpeg. Tools are not
downloaded automatically. Keep generated geometry outside the repository.

Obtain the enclosure STEP from the manufacturer link in `assembly.json` and
the supplied Molex `1053081208` receptacle STEP. The pipeline requires their
reviewed SHA-256 hashes and does not redistribute either vendor asset.
Do not silently substitute a different vendor file.

Initialize the pinned submodules. If intentionally changing their revisions,
validate/commit the board repositories and stage the corresponding parent
gitlinks before exporting. The exporter rejects uncommitted PCB changes or
an unexpected metering revision and runs fresh ERC/DRC/parity checks on the
two updated canonical projects.

```powershell
git submodule update --init --recursive
$cache = "$env:TEMP\din-v2-assembly"
$frames = "$env:TEMP\din-v2-frames"
& 'C:\Program Files\FreeCAD 0.19\bin\python.exe' -B .\mechanical\build_assembly.py `
  --cache $cache --enclosure-step 'C:\CAD\hbdmb4770.step' `
  --molex-step 'C:\CAD\1053081208-user.stp'
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' -b --threads 4 `
  --python .\mechanical\render_assembly.py -- --cache $cache --output $frames
python -B .\mechanical\publish_assembly.py --cache $cache --frames $frames `
  --ffmpeg 'C:\Tools\ffmpeg.exe'
```

Only the old metering board's model references are rebased in a cache copy:
legacy SSOP, 0402/0603 passives and crystal models use current KiCad package
equivalents. Its local Molex model is resolved from the unchanged submodule.
PCB geometry, footprints, electrical files and submodule pin are not edited.
Package equivalents are visual proxies, not verified manufacturer models.

## Remaining physical and safety gates

Measure the actual enclosure cuts, socket seating, S3 underside clearances
and assembled stack height with a vernier. Verify Nano-Fit receptacle
engagement, J1 part/model identity and wire bending/retention. The power
board's manually soldered insulated sense link also needs physical validation.
Keep all CT burden branches permanent while servicing sense connections.

Configured ERC/DRC/parity passes are electrical-CAD checks, **not** isolation,
SELV, mains safety, mechanical fit or manufacturing approval. The existing
power circuit must not be treated as an approved SELV design.

## Fit-improvement priorities

1. Measure the PCI depth, carrier connector seat, short-header gap and actual
   cut enclosure. Re-model the seated stack before changing a PCB.
2. Examine carrier edges near the first contact and trim only after checking
   copper-to-edge, connector support, isolation slot and creepage.
3. If power-board space is the remaining constraint, investigate 0402 burden
   packages as an optimization, not a direct height fix. Each 2.4 ohm burden
   dissipates about 6 mW at 50 mA RMS; verify overload, pulse rating,
   derating, precision and solderability before changing the current 0603
   parts or rerouting. Keep every CT burden permanently connected.
4. Consider connector placement or a measured enclosure cut only after
   checking the plug mating direction, cable bend and retention. Keep the
   present Nano-Fit system where practical.
