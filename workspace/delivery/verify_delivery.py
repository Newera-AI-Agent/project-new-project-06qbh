#!/usr/bin/env python3
"""Independent deterministic integrity gate for the NewEra intro delivery package.

Run once with --write-manifest to record verified artifact fingerprints. Thereafter,
run without flags to detect accidental edits, truncation, or substitution. The manifest
is a repository checksum baseline, not a cryptographic signature or proof of authorship.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MASTER = "workspace/renders/newera_ai_agent_intro_master_1080p60.mp4"
REPORT = "workspace/delivery/qc_report.json"
CAPTIONS = "workspace/delivery/newera_intro_captions.vtt"
TRANSCRIPT = "workspace/delivery/newera_intro_transcript.md"
STORY = "workspace/storyboard.json"
BEATS = "workspace/beat_map.json"
FOLEY = "workspace/audio/transition_foley.json"
SOUNDTRACK = "ptasinski - life force (ft. RJ Pasin)_128k.mp3"
MANIFEST = "workspace/delivery/artifact_manifest.json"

# Delivery content plus its reproducibility-critical inputs and handoff documentation.
ARTIFACTS = [
    MASTER, CAPTIONS, TRANSCRIPT, REPORT, STORY, BEATS, FOLEY, SOUNDTRACK,
    "workspace/delivery/README.md", "workspace/delivery/verify_delivery.py",
    "workspace/delivery/generate_accessible_assets.py",
    "workspace/analysis/analyze_audio.py", "workspace/render_intro.py",
    "workspace/audio/synthesize_transition_foley.py",
    "workspace/brand_brief.md", "workspace/manus_analysis.md",
    "workspace/analysis/manus_12s/analysis.json",
    "workspace/analysis/manus_frame_events/analysis.json",
]
STAMP = re.compile(r"^(\d{2,}:\d{2}:\d{2}\.\d{3}) --> (\d{2,}:\d{2}:\d{2}\.\d{3})(?: .*)?$")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def run(args: list[str]) -> str:
    return subprocess.run(args, cwd=ROOT, check=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()


def stamp_sec(stamp: str) -> float:
    h, m, sec = stamp.split(":")
    s, ms = sec.split(".")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def validate_package() -> dict[str, object]:
    paths = {rel: ROOT / rel for rel in ARTIFACTS}
    for rel, path in paths.items():
        require(path.is_file() and path.stat().st_size > 0, f"Missing or empty artifact: {rel}")

    story = json.loads(paths[STORY].read_text(encoding="utf-8"))
    beats = json.loads(paths[BEATS].read_text(encoding="utf-8"))
    report = json.loads(paths[REPORT].read_text(encoding="utf-8"))
    foley = json.loads(paths[FOLEY].read_text(encoding="utf-8"))
    acts = story.get("acts", [])
    require(len(acts) == 5, f"Expected five storyboard acts, got {len(acts)}")
    require(len(beats.get("onsets", [])) == int(beats.get("onset_count", -1)),
            "Beat-map onset_count does not match its event list")
    require(report.get("status") == "PASS" and report.get("master") == MASTER,
            "QC report is not PASS or names a different master")

    probe = json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                            "-of", "json", str(paths[MASTER])]))
    video = next((s for s in probe["streams"] if s.get("codec_type") == "video"), None)
    audio = next((s for s in probe["streams"] if s.get("codec_type") == "audio"), None)
    require(video is not None and audio is not None, "Master must contain video and audio streams")
    vdur, adur = float(video["duration"]), float(audio["duration"])
    fps = float(Fraction(video["avg_frame_rate"]))
    frames = int(video.get("nb_frames", 0))
    delta = abs(vdur - adur)
    require((video["codec_name"], int(video["width"]), int(video["height"]), fps) ==
            ("h264", 1920, 1080, 60.0), "Master is not H.264 1920x1080 at 60 fps")
    require((audio["codec_name"], int(audio["sample_rate"]), int(audio["channels"])) ==
            ("aac", 48000, 2), "Master audio is not AAC 48 kHz stereo")
    require(90 <= vdur <= 180 and delta <= .05 and frames > 0,
            f"Master duration/frame/A-V check failed: {vdur:.6f}s, {frames} frames, delta {delta:.6f}s")

    digest = hashlib.sha256(paths[MASTER].read_bytes()).hexdigest()
    require(report.get("sha256") == digest, "QC SHA-256 does not match the delivered master")
    require(int(report.get("file_bytes", -1)) == paths[MASTER].stat().st_size,
            "QC master file size does not match")
    rv, ra = report.get("video", {}), report.get("audio", {})
    require((rv.get("codec"), rv.get("width"), rv.get("height"), float(rv.get("fps", 0)),
             int(rv.get("frame_count", 0))) == ("h264", 1920, 1080, 60.0, frames),
            "QC video metadata disagrees with ffprobe")
    require((ra.get("codec"), int(ra.get("sample_rate_hz", 0)), int(ra.get("channels", 0))) ==
            ("aac", 48000, 2), "QC audio metadata disagrees with ffprobe")
    require(abs(float(report.get("duration_sec", -1)) - vdur) < .002 and
            abs(float(report.get("av_duration_delta_sec", -1)) - delta) < .002,
            "QC duration metadata disagrees with ffprobe")
    # Decode every packet; metadata alone cannot detect a damaged/truncated stream.
    run(["ffmpeg", "-v", "error", "-i", str(paths[MASTER]), "-f", "null", "-"])
    require("full ffmpeg decode" in report.get("decode", ""), "QC report lacks full-decode evidence")

    # Validate WebVTT syntax, chronology, and that timed cues stay inside the film.
    vtt = paths[CAPTIONS].read_text(encoding="utf-8-sig").splitlines()
    require(bool(vtt) and vtt[0].strip() == "WEBVTT", "Captions lack WEBVTT header")
    cues: list[tuple[float, float]] = []
    for line in vtt:
        if "-->" not in line:
            continue
        match = STAMP.fullmatch(line.strip())
        require(match is not None, f"Invalid WebVTT timestamp line: {line!r}")
        start, end = map(stamp_sec, match.groups())
        require(start < end and end <= vdur + .001, f"Caption cue outside film: {line}")
        cues.append((start, end))
    require(len(cues) >= len(acts) * 2, f"Too few timed caption cues: {len(cues)}")
    require(cues == sorted(cues), "Caption cues are not ordered by time")

    transcript = paths[TRANSCRIPT].read_text(encoding="utf-8")
    for act in acts:
        require(f"## {act['id']} · {act['name']}" in transcript,
                f"Transcript missing storyboard act {act['id']}")
        for phrase in act.get("copy", []):
            require(phrase in transcript, f"Transcript missing on-screen copy: {phrase!r}")
    require("no dialogue" in transcript.lower(), "Transcript must identify that the film has no dialogue")

    boundary_frames = [int(act["start_frame"]) for act in acts[1:]]
    foley_frames = [int(event["frame"]) for event in foley.get("events", [])]
    require(foley_frames == boundary_frames,
            f"Foley peaks {foley_frames} do not equal internal storyboard boundaries {boundary_frames}")
    for act in acts:
        require(0 <= int(act["start_frame"]) < int(act["end_frame"]) <= frames,
                f"Invalid act frame interval: {act.get('id')}")
    require(abs(float(beats["duration_sec"]) - float(foley["duration_sec"])) <= .1,
            "Beat-map and foley source durations disagree")
    require(abs(float(beats["duration_sec"]) - 107.9148) < .1,
            "Unexpected soundtrack analysis duration; review the production mapping")
    require(report.get("companions") == [Path(CAPTIONS).name, Path(TRANSCRIPT).name],
            "QC companion list does not match the accessible deliverables")

    return {
        "schema_version": 1,
        "purpose": "Deterministic SHA-256 baseline for verified master, accessible files and reproduction inputs.",
        "integrity_scope": "Detects accidental changes relative to this checked-in manifest; not a signature or tamper-proof proof of origin.",
        "master_duration_sec": round(vdur, 6),
        "master_video_frames": frames,
        "caption_cue_count": len(cues),
        "storyboard_act_count": len(acts),
        "artifacts": {rel: {"bytes": paths[rel].stat().st_size,
                            "sha256": hashlib.sha256(paths[rel].read_bytes()).hexdigest()}
                      for rel in ARTIFACTS},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-manifest", action="store_true",
                        help="write/update the checksum baseline after structural and full-decode validation")
    args = parser.parse_args()
    try:
        expected = validate_package()
        manifest_path = ROOT / MANIFEST
        if args.write_manifest:
            manifest_path.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
            print(f"PASS: validated package; wrote {MANIFEST} ({len(expected['artifacts'])} SHA-256 entries)")
        else:
            require(manifest_path.is_file(), f"No baseline manifest; first run: python3 {MANIFEST.replace('artifact_manifest.json','verify_delivery.py')} --write-manifest")
            recorded = json.loads(manifest_path.read_text(encoding="utf-8"))
            require(recorded == expected,
                    "Delivery manifest mismatch: an artifact changed or regenerated QC evidence is stale; inspect the diff and deliberately re-baseline only after re-verification")
            print(f"PASS: delivery manifest matches; full MP4 decode, {len(expected['artifacts'])} artifact hashes, "
                  f"{expected['caption_cue_count']} caption cues, {expected['storyboard_act_count']} acts; "
                  f"{expected['master_duration_sec']:.3f}s, {expected['master_video_frames']} frames")
        return 0
    except (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError, StopIteration) as exc:
        detail = getattr(exc, "stderr", "")
        print(f"FAIL: {exc}" + (f"\n{detail}" if detail else ""), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
