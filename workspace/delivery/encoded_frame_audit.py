#!/usr/bin/env python3
"""Reproducibly extract exact encoded frames at act boundaries and ending for visual QA.

Requires ffmpeg, ffprobe, and Pillow. Output contains objective frame statistics and
an inspection contact sheet; it explicitly does not claim perceptual quality or sync.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MASTER = ROOT / "workspace/renders/newera_ai_agent_intro_master_1080p60.mp4"
DEFAULT_STORYBOARD = ROOT / "workspace/storyboard.json"
DEFAULT_JSON = ROOT / "workspace/delivery/encoded_frame_audit.json"
DEFAULT_CONTACT = ROOT / "workspace/delivery/encoded_frame_audit_contact.png"
THUMB_SIZE = (640, 360)


def run(args: list[str]) -> bytes:
    return subprocess.check_output(args, cwd=ROOT, stderr=subprocess.PIPE)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def get_frame_count(master: Path) -> tuple[int, dict]:
    raw = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
               "stream=width,height,avg_frame_rate,nb_frames,duration", "-of", "json", str(master)])
    stream = json.loads(raw)["streams"][0]
    rate_n, rate_d = map(int, stream["avg_frame_rate"].split("/"))
    duration = float(stream["duration"])
    count = int(stream.get("nb_frames") or round(duration * rate_n / rate_d))
    return count, {"width": stream["width"], "height": stream["height"],
                   "fps": f"{rate_n}/{rate_d}", "duration_sec": duration, "frame_count": count}


def sample_frames(storyboard: dict, frame_count: int) -> list[dict]:
    # Sample the frame before, at, and after each interior scene cut, plus a regular
    # one-second ending hold check. Keep exact encoded frame indices for reproducibility.
    boundaries = [int(x["frame"]) for x in storyboard["actual_scene_boundaries"]]
    positions: set[int] = {0, frame_count - 1}
    for frame in boundaries[1:-1]:
        positions.update((frame - 1, frame, frame + 1))
    ending_start = max(0, frame_count - 1 - 60 * 18)
    positions.update(range(ending_start, frame_count, 60))
    positions.add(frame_count - 1)
    return [{"frame": f, "time_sec": round(f / storyboard["fps"], 6)}
            for f in sorted(positions) if 0 <= f < frame_count]


def describe(img: Image.Image, frame: int, time_sec: float) -> dict:
    gray = img.convert("L")
    hist = gray.histogram()
    pixels = gray.width * gray.height
    mean = sum(i * n for i, n in enumerate(hist)) / pixels

    def percentile(q: float) -> int:
        target = math.ceil(pixels * q)
        total = 0
        for value, count in enumerate(hist):
            total += count
            if total >= target:
                return value
        return 255

    return {"frame": frame, "time_sec": time_sec,
            "thumbnail_dimensions": [img.width, img.height],
            "mean_luma_0_255": round(mean, 3), "p10_luma": percentile(.10),
            "p50_luma": percentile(.50), "p90_luma": percentile(.90),
            "pixels_above_luma_30_pct": round(sum(hist[31:]) / pixels * 100, 4),
            "pixels_above_luma_80_pct": round(sum(hist[81:]) / pixels * 100, 4)}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--master", type=Path, default=DEFAULT_MASTER)
    p.add_argument("--storyboard", type=Path, default=DEFAULT_STORYBOARD)
    p.add_argument("--json", type=Path, default=DEFAULT_JSON)
    p.add_argument("--contact", type=Path, default=DEFAULT_CONTACT)
    args = p.parse_args()
    master = args.master.resolve()
    storyboard_path = args.storyboard.resolve()
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise SystemExit(f"ERROR: required executable not found: {tool}")
    if not master.is_file() or not storyboard_path.is_file():
        raise SystemExit("ERROR: master video or storyboard does not exist")

    before_hash = sha256(master)
    storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
    frame_count, video = get_frame_count(master)
    samples = sample_frames(storyboard, frame_count)
    select_expr = "+".join(f"eq(n\\,{s['frame']})" for s in samples)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.contact.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="newera-frame-audit-") as td:
        pattern = str(Path(td) / "frame_%03d.png")
        run(["ffmpeg", "-hide_banner", "-v", "error", "-i", str(master), "-vf",
             f"select='{select_expr}',scale={THUMB_SIZE[0]}:{THUMB_SIZE[1]}:flags=area",
             "-fps_mode", "vfr", "-compression_level", "3", pattern])
        paths = sorted(Path(td).glob("frame_*.png"))
        if len(paths) != len(samples):
            raise SystemExit(f"ERROR: requested {len(samples)} exact frames, got {len(paths)}")
        images = [Image.open(path).convert("RGB") for path in paths]

    if sha256(master) != before_hash:
        raise SystemExit("ERROR: source master hash changed during read-only audit")

    records = [describe(img, sample["frame"], sample["time_sec"])
               for img, sample in zip(images, samples)]
    columns = 2
    label_h = 34
    rows = math.ceil(len(images) / columns)
    sheet = Image.new("RGB", (columns * THUMB_SIZE[0], rows * (THUMB_SIZE[1] + label_h)), (8, 10, 12))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("DejaVuSansMono.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
    for i, (img, record) in enumerate(zip(images, records)):
        x = (i % columns) * THUMB_SIZE[0]
        y = (i // columns) * (THUMB_SIZE[1] + label_h)
        sheet.paste(img, (x, y))
        draw.text((x + 10, y + THUMB_SIZE[1] + 7),
                  f"{record['time_sec']:7.3f}s  frame {record['frame']:05d}",
                  font=font, fill=(230, 237, 237))
    sheet.save(args.contact, optimize=True)

    report = {
        "schema_version": 1,
        "source": str(master.relative_to(ROOT)) if master.is_relative_to(ROOT) else master.name,
        "source_sha256": before_hash,
        "storyboard": str(storyboard_path.relative_to(ROOT)) if storyboard_path.is_relative_to(ROOT) else storyboard_path.name,
        "video": video,
        "method": "FFmpeg exact frame-index select in one full decode; thumbnails scaled to 640x360; Pillow luma statistics.",
        "samples": records,
        "contact_sheet": str(args.contact.relative_to(ROOT)) if args.contact.is_relative_to(ROOT) else args.contact.name,
        "limitations": ["Pixel statistics and extracted thumbnails do not establish human-perceived legibility, aesthetic quality, or music-to-picture sync.",
                        "Review the contact sheet at full size and listen to the master for subjective QA."],
    }
    args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: exact-frame audit extracted {len(records)} samples from {video['frame_count']} frames; master SHA-256 unchanged")
    print(f"Contact sheet: {args.contact}")
    print(f"Machine-readable report: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
