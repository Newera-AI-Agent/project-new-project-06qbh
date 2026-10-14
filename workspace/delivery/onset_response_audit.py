#!/usr/bin/env python3
"""Measure encoded-picture response around beat-map onset frames.

This is a reproducible signal audit, not a perceptual or causal sync test. It
extracts small grayscale frames at exact indices and compares a fixed central ROI
with the frame immediately before each onset. Nearby onsets can overlap.
Requires ffmpeg, ffprobe, and NumPy from the project analysis environment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
MASTER = ROOT / "workspace/renders/newera_ai_agent_intro_master_1080p60.mp4"
BEATS = ROOT / "workspace/beat_map.json"
OUTPUT = ROOT / "workspace/delivery/onset_response_audit.json"
WIDTH, HEIGHT = 160, 90
FRAME_BYTES = WIDTH * HEIGHT
MAX_OFFSET = 8


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def ffmpeg_frames(master: Path, frame_indices: list[int]) -> dict[int, np.ndarray]:
    """Decode exact requested indices as 160x90 grayscale arrays."""
    if not frame_indices:
        return {}
    expr = "+".join(f"eq(n\\,{n})" for n in frame_indices)
    cmd = ["ffmpeg", "-hide_banner", "-v", "error", "-i", str(master),
           "-vf", f"select='{expr}',scale={WIDTH}:{HEIGHT}:flags=area,format=gray",
           "-fps_mode", "vfr", "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"]
    proc = subprocess.run(cmd, cwd=ROOT, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE)
    expected = len(frame_indices) * FRAME_BYTES
    if len(proc.stdout) != expected:
        raise RuntimeError(f"FFmpeg returned {len(proc.stdout)} bytes; expected {expected} "
                           f"for {len(frame_indices)} exact frames")
    return {n: np.frombuffer(proc.stdout[i * FRAME_BYTES:(i + 1) * FRAME_BYTES],
                             dtype=np.uint8).reshape(HEIGHT, WIDTH)
            for i, n in enumerate(frame_indices)}


def frame_response(frames: dict[int, np.ndarray], onset: int,
                   roi: tuple[slice, slice]) -> dict[int, float]:
    """Per-frame mean absolute ROI luma change for offsets 0..MAX_OFFSET."""
    return {d: float(np.abs(frames[onset + d][roi].astype(np.int16) -
                              frames[onset + d - 1][roi].astype(np.int16)).mean())
            for d in range(MAX_OFFSET + 1)}


def summarize(values: list[float]) -> dict[str, float]:
    arr = np.asarray(values, dtype=np.float64)
    return {"mean_abs_luma_delta_0_255": round(float(arr.mean()), 5),
            "median_abs_luma_delta_0_255": round(float(np.median(arr)), 5)}


def measure(master: Path, beat_path: Path, output: Path) -> dict:
    beats = json.loads(beat_path.read_text(encoding="utf-8"))
    events = beats.get("onsets", [])
    onset_frames = sorted({int(e["frame_60fps"]) for e in events})
    if not onset_frames:
        raise ValueError("Beat map contains no onset frames")
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=width,height,avg_frame_rate,nb_frames",
                            "-of", "json", str(master)], cwd=ROOT, check=True,
                           stdout=subprocess.PIPE)
    stream = json.loads(probe.stdout)["streams"][0]
    frame_count = int(stream["nb_frames"])
    if stream["avg_frame_rate"] != "60/1":
        raise ValueError(f"Expected 60 fps master, got {stream['avg_frame_rate']}")
    events = [f for f in onset_frames if 1 <= f and f + MAX_OFFSET < frame_count]
    selected = sorted({f + d for f in events for d in range(-1, MAX_OFFSET + 1)})
    frames = ffmpeg_frames(master, selected)
    # Fixed central ROI: x=25–75%, y=20–80% of the downsampled luma frame.
    roi = (slice(18, 72), slice(40, 120))
    all_deltas: dict[int, list[float]] = {d: [] for d in range(MAX_OFFSET + 1)}
    isolated_deltas: dict[int, list[float]] = {d: [] for d in range(MAX_OFFSET + 1)}
    rows = []
    for f in events:
        # Measure the change occurring on each frame, not cumulative displacement
        # from the pre-onset image. This makes the offset curve a per-frame
        # activity profile rather than a growing distance-from-baseline curve.
        response = frame_response(frames, f, roi)
        isolated = not any(0 < abs(other - f) <= MAX_OFFSET
                           for other in events)
        for d, value in response.items():
            all_deltas[d].append(value)
            if isolated:
                isolated_deltas[d].append(value)
        rows.append({"onset_frame": f, "onset_ms": round(f * 1000 / 60, 3),
                     "isolated_from_neighbor_onsets_within_8_frames": isolated,
                     "roi_mean_abs_luma_delta_from_previous_frame": {
                         str(d): round(v, 5) for d, v in response.items()}})

    def curve(series: dict[int, list[float]]) -> list[dict]:
        return [{"offset_frames": d, "offset_ms": round(d * 1000 / 60, 3),
                 "events": len(series[d]), **summarize(series[d])}
                for d in range(MAX_OFFSET + 1) if series[d]]

    report = {
        "schema_version": 1,
        "source_video": str(master.relative_to(ROOT)) if master.is_relative_to(ROOT) else master.name,
        "source_video_sha256": digest(master),
        "source_beat_map": str(beat_path.relative_to(ROOT)) if beat_path.is_relative_to(ROOT) else beat_path.name,
        "source_onset_count": len(beats["onsets"]),
        "unique_valid_onset_frames": len(events),
        "video": {k: stream[k] for k in ("width", "height", "avg_frame_rate", "nb_frames")},
        "method": {
            "decode": "FFmpeg select by exact decoded frame index, scale to 160x90, grayscale",
            "roi": "central 50% width x central 60% height (80x54 pixels after scaling)",
            "baseline": "for each offset, compare that encoded frame to the immediately preceding encoded frame",
            "response": "mean absolute per-pixel luma difference between consecutive frames at each offset",
            "isolated_rule": "no other valid onset within 8 frames before or after",
        },
        "all_onsets_response_curve": curve(all_deltas),
        "isolated_onsets_response_curve": curve(isolated_deltas),
        "event_measurements": rows,
        "limitations": [
            "This is a descriptive image-change association, not proof that audio caused the visual change or that a viewer perceives sync.",
            "The fixed ROI can miss changes outside its bounds; camera/scene movement and overlapping onset responses affect measurements.",
            "Luma deltas do not assess legibility, design quality, motion smoothness, or ±1-frame perceptual alignment.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", type=Path, default=MASTER)
    parser.add_argument("--beat-map", type=Path, default=BEATS)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise SystemExit(f"ERROR: required executable not found: {tool}")
    before = digest(args.master)
    result = measure(args.master.resolve(), args.beat_map.resolve(), args.output.resolve())
    if digest(args.master) != before:
        raise SystemExit("ERROR: source video changed during read-only audit")
    print(f"PASS: measured {result['unique_valid_onset_frames']} onset frames; master SHA-256 unchanged")
    for key in ("all_onsets_response_curve", "isolated_onsets_response_curve"):
        print(key)
        for point in result[key]:
            print(f"  +{point['offset_frames']}f: mean={point['mean_abs_luma_delta_0_255']:.5f}, "
                  f"median={point['median_abs_luma_delta_0_255']:.5f} ({point['events']} events)")
    print(f"JSON: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
