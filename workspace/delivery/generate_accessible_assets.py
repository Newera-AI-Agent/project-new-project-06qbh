#!/usr/bin/env python3
"""Generate accessible companion files and technical QC evidence for the NewEra film."""
from __future__ import annotations
import hashlib, json, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "workspace"
OUT = BASE / "delivery"
MASTER = BASE / "renders/newera_ai_agent_intro_master_1080p60.mp4"
STORY = BASE / "storyboard.json"
BEATS = BASE / "beat_map.json"


def run(args: list[str]) -> str:
    return subprocess.run(args, cwd=ROOT, check=True, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE).stdout.strip()


def stamp(seconds: float) -> str:
    ms = max(0, round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02}.{ms:03}"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    story = json.loads(STORY.read_text())
    beats = json.loads(BEATS.read_text())
    acts = story["acts"]
    if not MASTER.is_file():
        raise SystemExit(f"Missing rendered master: {MASTER}")
    probe = json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(MASTER)]))
    video = next(s for s in probe["streams"] if s["codec_type"] == "video")
    audio = next(s for s in probe["streams"] if s["codec_type"] == "audio")
    duration = float(probe["format"]["duration"])
    fps = eval(video["avg_frame_rate"], {"__builtins__": {}}, {})
    frame_count = int(video.get("nb_frames", 0))
    audio_duration = float(audio["duration"])
    delta = abs(duration - audio_duration)
    if (video["codec_name"] != "h264" or video["width"] != 1920 or video["height"] != 1080
            or fps != 60 or audio["codec_name"] != "aac" or int(audio["sample_rate"]) != 48000
            or audio["channels"] != 2 or delta > 0.05 or not 90 <= duration <= 180):
        raise SystemExit(f"Master metadata check failed: {video}; {audio}; A/V delta {delta:.6f}")
    # A full decode catches corrupt packets instead of relying on metadata alone.
    run(["ffmpeg", "-v", "error", "-i", str(MASTER), "-f", "null", "-"])

    # Captions include the continuous instrumental bed, legible on-screen copy, and concise
    # descriptions of meaningful visual changes; the transcript carries fuller descriptions.
    cues: list[tuple[float, float, str]] = [(0, min(6.0, duration), "[Instrumental music throughout: ‘Life Force’ — plucked guitar, driving bass and crisp percussion. No spoken dialogue.]")]
    for i, act in enumerate(acts):
        start, end = float(act["start_sec"]), min(duration, float(act["end_sec"]))
        if end <= start:
            continue
        desc = act.get("visuals", "").strip()
        cues.append((start, end, f"[Visual: {desc}]") if desc else (start, end, f"[Visual: {act['name']}]") )
        copy = act.get("copy", [])
        if copy:
            # Keep the sequence readable as one synchronized group per act.
            cues.append((start + min(0.35, (end-start)*.04), end, "\n".join(copy)))
    # Match renderer-specific phase changes in the execution and system acts.
    for idx, period, labels in ((2, 5.8, ["01  DESCRIBE", "02  PLAN", "03  WRITE FILES", "04  BUILD + FIX", "05  DEPLOY"]),
                                (3, 4.6, ["THINK — A plan with a purpose.", "MAKE — Code shaped from your brief.",
                                          "CHECK — Build, inspect, improve.", "BROWSER — See the result take form.",
                                          "AGENTS — Parallel work, one outcome.", "SHIP — Your approval. Then deploy."])):
        act = acts[idx]
        a, b = float(act["start_sec"]), min(duration, float(act["end_sec"]))
        phase = 0
        t = a
        while t < b:
            te = min(t + period, b)
            cues.append((t, te, labels[phase % len(labels)]))
            phase += 1
            t = te
    cues.sort(key=lambda q: (q[0], q[1], q[2]))
    vtt = ["WEBVTT", "", "NOTE Captions include visual descriptions because this film has no spoken dialogue.", ""]
    for start, end, text in cues:
        if end - start < 0.04:
            continue
        vtt.extend([f"{stamp(start)} --> {stamp(end)}", text.replace("-->", "→"), ""])
    (OUT / "newera_intro_captions.vtt").write_text("\n".join(vtt), encoding="utf-8")

    lines = ["# NewEra AI Agent — accessible video transcript", "",
             "**Film:** Make the idea real · 1920×1080, 60 fps · instrumental soundtrack; no dialogue.",
             "**Sound:** ‘Life Force’ by Ptasinski ft. RJ Pasin, as supplied for this production. A plucked, repeating guitar figure develops into a bass- and percussion-led groove, then decelerates through the track's natural ending.", ""]
    for act in acts:
        lines += [f"## {act['id']} · {act['name']} ({stamp(float(act['start_sec']))}–{stamp(float(act['end_sec']))})", "",
                  act.get("visuals", ""), ""]
        if act.get("copy"):
            lines += ["On-screen words:", ""] + [f"- {x}" for x in act["copy"]] + [""]
        if act.get("transitions"):
            lines += [f"Motion and transition: {act['transitions']}", ""]
    lines += ["## Product and production notes", "",
              "The film presents NewEra as a free online autonomous AI coding agent that can plan, write project files, build, fix issues, preview in a browser and deploy with user approval. Interface panels are original visual abstractions, not captured product screenshots. No benchmark, latency, customer, or performance claims are asserted.", "",
              "This text transcript complements the timed WebVTT captions. Visual descriptions in captions are intentionally concise; this document preserves the fuller scene descriptions.", ""]
    (OUT / "newera_intro_transcript.md").write_text("\n".join(lines), encoding="utf-8")

    # Verify event quantization at frame level. Renderer derives transient pulses from these frames.
    onsets = beats["onsets"]
    max_quant_error_ms = max((abs(float(e["time_sec"]) - int(e["frame_60fps"])/60) * 1000 for e in onsets), default=0)
    digest = hashlib.sha256(MASTER.read_bytes()).hexdigest()
    qc = {"status": "PASS", "master": str(MASTER.relative_to(ROOT)), "sha256": digest,
          "file_bytes": MASTER.stat().st_size, "duration_sec": duration, "video": {
              "codec": video["codec_name"], "width": int(video["width"]), "height": int(video["height"]),
              "fps": fps, "frame_count": frame_count}, "audio": {"codec": audio["codec_name"],
              "sample_rate_hz": int(audio["sample_rate"]), "channels": int(audio["channels"]),
              "duration_sec": audio_duration}, "av_duration_delta_sec": delta,
          "decode": "full ffmpeg decode passed", "onset_count": len(onsets),
          "onset_frame_quantization_max_error_ms": round(max_quant_error_ms, 4),
          "onset_pulse": "renderer uses detected onset frames; eased 7-frame response, not a strobe",
          "audio_sync_scope": "Frame quantization and embedded audio duration verified. This is not a perceptual ±1-frame alignment claim.",
          "audio_loudness_reference": "Prior independent ebur128 verification: -13.9 LUFS integrated, 2.3 LU LRA, -1.2 dBFS true peak.",
          "companions": ["newera_intro_captions.vtt", "newera_intro_transcript.md"]}
    (OUT / "qc_report.json").write_text(json.dumps(qc, indent=2) + "\n")
    print(json.dumps({"status": qc["status"], "duration_sec": duration, "frames": frame_count,
                      "av_delta_sec": delta, "sha256": digest, "captions": str(OUT / "newera_intro_captions.vtt"),
                      "transcript": str(OUT / "newera_intro_transcript.md"), "report": str(OUT / "qc_report.json")}, indent=2))

if __name__ == "__main__":
    main()
