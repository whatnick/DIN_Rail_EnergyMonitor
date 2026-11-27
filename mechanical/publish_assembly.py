"""Label all poses honestly and publish a decoded GIF/MP4 plus source manifest."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from PIL import Image, ImageDraw, ImageFont, ImageSequence


ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    path.write_bytes((json.dumps(data, indent=2)+"\n").encode())


def save_png(image, path):
    temporary = path.with_suffix(".tmp.png")
    image.save(temporary)
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    args = parser.parse_args()
    output = ROOT / "mechanical" / "renders"
    output.mkdir(parents=True, exist_ok=True)
    report_path = args.cache / "fit-report.json"
    report = json.loads(report_path.read_text())
    render = json.loads((args.frames / "render-manifest.json").read_text())
    if render["report_sha256"] != digest(report_path):
        raise ValueError("Rendered geometry differs from the contact study")
    if len(render["frames"]) != len(report["frames"]):
        raise ValueError("Missing rendered poses")
    bold = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 23)
    normal = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 19)
    small = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 17)
    titles = dict(carrier="1  |  Carrier / S3 attaches beneath metering riser",
                  meter="2  |  Insert combined riser into power PCI socket",
                  tilt="3  |  Rotate the complete three-PCB assembly",
                  insert="4  |  Nominal rear insertion - UNCUT enclosure",
                  seat="5  |  Nominal seating - NOT a clearance proof",
                  plug="6  |  Fit Nano-Fit cable plugs after seating")
    frames, durations = [], []
    for i, (frame, receipt) in enumerate(zip(report["frames"], render["frames"])):
        source = args.frames / receipt["file"]
        if digest(source) != receipt["sha256"]:
            raise ValueError("Changed rendered frame: " + str(i))
        image = Image.open(source).convert("RGB")
        image.load()
        if list(image.size) != render["resolution"]:
            raise ValueError("Unexpected frame resolution")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 1024, 91), fill=(18, 24, 31))
        draw.text((16, 8), "DIN v2.0  |  "+titles[frame["phase"]], font=bold, fill="white")
        draw.text((16, 40), "Power: green  |  Meter: teal (unchanged)  |  Carrier: purple  |  S3/TFT: proxy",
                  font=small, fill=(210, 220, 230))
        draw.text((16, 65), "Tilt %.1f deg  |  Riser %.1f deg (max +/-3)  |  Z %.1f mm" % (
            frame["angle_deg"], frame["riser_deg"], frame["z_mm"]),
                  font=small, fill=(210, 220, 230))
        collision = frame["summed_intersection_mm3"] > report["intersection_threshold_mm3"]
        draw.rectangle((0, 697, 1024, 768), fill=(112, 16, 16) if collision else (18, 24, 31))
        if collision:
            heading = ("FIRST SAMPLED CONTACT" if i == report["first_contact_frame"]
                       else "MODELED CONTACT - nominal motion continues")
            draw.text((16, 704), heading+"  |  %.3f mm3" % frame["summed_intersection_mm3"],
                      font=normal, fill="white")
            if receipt["contact_locator_px"]:
                x, y = receipt["contact_locator_px"]
                draw.ellipse((x-17, y-17, x+17, y+17), outline=(255, 210, 30), width=3)
        else:
            draw.text((16, 704), "Illustrative mating/kinematics; actual socket seating and enclosure cuts unmeasured.",
                      font=small, fill="white")
        draw.text((16, 738), "Red = sampled overlap with uncut CAD. Short headers/S3 are proxies. Not a manufacturing release.",
                  font=small, fill="white")
        duration = 200
        if i in (0, 11, 23, report["first_contact_frame"]):
            duration = 1000
        if i == len(report["frames"])-1:
            duration = 2000
        frames.append(image)
        durations.append(duration)
    montage = Image.new("RGB", (768, 192))
    for i, index in enumerate((0, len(frames)//2, len(frames)-1)):
        montage.paste(frames[index].resize((256, 192)), (i*256, 0))
    palette = montage.quantize(colors=128)
    indexed = [image.resize((768, 576), Image.Resampling.LANCZOS).quantize(
        palette=palette, dither=Image.Dither.NONE)
               for image in frames]
    gif = output / "assembly-insertion.gif"
    indexed[0].save(gif, save_all=True, append_images=indexed[1:], duration=durations,
                    loop=0, disposal=2, optimize=False)
    decoded_duration, decoded_count = 0, 0
    with Image.open(gif) as animation:
        for frame in ImageSequence.Iterator(animation):
            frame.load()
            decoded_duration += frame.info["duration"]
            decoded_count += 1
    if decoded_duration != sum(durations):
        raise ValueError("GIF timing differs from the rendered sequence")
    encoded = args.frames / "encoded"
    encoded.mkdir(exist_ok=True)
    index = 0
    for i, (image, duration) in enumerate(zip(frames, durations)):
        path = encoded / ("frame-%04d.png" % index)
        image.save(path)
        index += 1
        for repeat in range(duration//200-1):
            shutil.copyfile(path, encoded / ("frame-%04d.png" % index))
            index += 1
    video = output / "assembly-insertion.mp4"
    subprocess.run([str(args.ffmpeg), "-y", "-v", "error", "-framerate", "5", "-i",
                    str(encoded / "frame-%04d.png"), "-frames:v", str(index),
                    "-vf", "format=yuv420p", "-c:v", "libx264", "-crf", "22",
                    "-movflags", "+faststart", str(video)], check=True)
    decoded = subprocess.check_output([str(args.ffmpeg), "-v", "error", "-i", str(video),
                                       "-f", "framemd5", "-"])
    if len([line for line in decoded.splitlines() if not line.startswith(b"#")]) != index:
        raise ValueError("Not every MP4 frame decoded")
    save_png(frames[0], output / "exploded.png")
    seated = args.frames / "seated.png"
    if digest(seated) != render["seated_sha256"]:
        raise ValueError("Changed seated render")
    still = Image.open(seated).convert("RGB")
    draw = ImageDraw.Draw(still)
    draw.rectangle((0, 0, 1024, 80), fill=(18, 24, 31))
    draw.text((16, 12), "DIN v2.0  |  Nominal assembled position in DMB-4770", font=bold, fill="white")
    draw.text((16, 47), "S3 Mini Pro / short-header proxies. Seating and actual enclosure cuts require measurement.",
              font=small, fill="white")
    draw.rectangle((0, 720, 1024, 768), fill=(112, 16, 16))
    draw.text((16, 731), "Uncut vendor CAD; this view does not establish collision-free insertion or manufacturing approval.",
              font=small, fill="white")
    save_png(still, output / "seated.png")
    destination = ROOT / "mechanical" / "fit-report.json"
    shutil.copyfile(report_path, destination)
    manifest = dict(
        report_sha256=digest(destination), render_manifest_sha256=digest(args.frames / "render-manifest.json"),
        rendered_poses=len(frames), decoded_gif_frames=decoded_count, decoded_video_frames=index,
        gif_resolution=[768, 576], video_resolution=render["resolution"],
        duration_ms=sum(durations), all_frames_decoded=True,
        publications={path.name: dict(sha256=digest(path), bytes=path.stat().st_size)
                      for path in (gif, video, output / "exploded.png", output / "seated.png")})
    write_json(ROOT / "mechanical" / "publication-manifest.json", manifest)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
