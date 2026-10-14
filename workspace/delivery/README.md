# NewEra intro delivery package

## Deliverables

- `../renders/newera_ai_agent_intro_master_1080p60.mp4` — final 107.92-second, 1920×1080, 60 fps H.264/AAC film.
- `newera_intro_captions.vtt` — timed, accessible captions: instrumental-music identification, visual descriptions and rendered on-screen wording. There is no spoken dialogue.
- `newera_intro_transcript.md` — scene-by-scene text transcript with detailed visual descriptions and on-screen copy.
- `qc_report.json` — generated metadata, full-decode and audio/video duration checks, SHA-256, plus honest scope of synchronization verification.
- `generate_accessible_assets.py` — deterministic generator for captions, transcript and the QC report.

## Reproduce

Run all commands from the repository root. Python dependencies are in the ignored `workspace/.venv` environment; the render requires Python, NumPy, Pillow, FFmpeg with `libx264`, and FFprobe. Audio analysis additionally requires the packages used by `workspace/analysis/analyze_audio.py` (including librosa). The supplied soundtrack is the root-level `ptasinski - life force (ft. RJ Pasin)_128k.mp3`.

```bash
# Regenerate beat map from the supplied MP3, then create full-resolution visuals.
workspace/.venv/bin/python workspace/analysis/analyze_audio.py
workspace/.venv/bin/python workspace/render_intro.py \
  --output workspace/renders/newera_ai_agent_intro_visual_1080p60.mp4

# Mux the exact full soundtrack and loudness-normalize to the documented target.
ffmpeg -hide_banner -y \
  -i workspace/renders/newera_ai_agent_intro_visual_1080p60.mp4 \
  -i 'ptasinski - life force (ft. RJ Pasin)_128k.mp3' \
  -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 256k \
  -af 'loudnorm=I=-14:TP=-1:LRA=7' -shortest \
  -movflags +faststart workspace/renders/newera_ai_agent_intro_master_1080p60.mp4

# Rebuild companion assets, verify metadata and decode every audio/video packet.
workspace/.venv/bin/python workspace/delivery/generate_accessible_assets.py
```

The render updates `workspace/storyboard.json` with its actual onset-snapped act boundaries and selected punctuation cues. It uses beat-map onset frames for a seven-frame eased transient response; it does not claim that every detected onset corresponds to a perceptually salient musical hit. The loudness filter can produce small version-dependent differences; the currently delivered master was independently measured at **-13.9 LUFS integrated, 2.3 LU LRA and -1.2 dBFS true peak**.

## Quality / sync evidence and limitations

The generator checks that the actual MP4 has an H.264 1920×1080 60 fps video stream, AAC 48 kHz stereo audio, a 90–180 second duration, and no more than 50 ms audio/video duration mismatch. FFmpeg fully decodes the complete file. The report also records each DSP onset's rounding error to its nearest frame (at most half a frame, apart from floating-point representation) and the SHA-256 of the delivered file. The existing analyzer uses 10 ms DSP hops and quantizes event timestamps to the nearest 60 fps frame.

These are reproducible technical checks, **not** proof of perceptual ±1-frame music-to-picture accuracy: onset detection is an estimate, frequencies are not isolated stems, and listening/judgement is still needed. The reference-video report likewise distinguishes sampled-frame/spectral indicators from verified edits. A full contact sheet exists at `../renders/final_qc/master_contact.jpg`; automated visual review was unavailable in this session, so visual quality remains a human-review item rather than a claimed pass.

## Usage and source notes

NewEra product wording is based on the captured live-site brief. The graphics are original, not extracted from the Manus reference; no Manus branding, footage, or interface is reused. No unsupported benchmark, latency, customer, or performance claims are made. The supplied music is retained as provided for this requested production. Confirm the necessary rights and clearances before public/commercial distribution.


## Final verification record (2026-10-14)

This record reflects checks re-run in the current VM session. Python source compilation passed for the audio/reference analyzers, report writer, renderer and delivery generator. Audio analysis regenerated the beat map from the supplied track: 107.9148 s, estimated 125.284 BPM, 384 onset events and 221 beats. A 300-frame / 5-second render smoke test passed. The delivery generator and full FFmpeg decode passed against the final master.

Verified master: 33,179,757 bytes; SHA-256 `12c005f65eb755ccffebdcd340fa11f29a3b7a600dcd8432bf7376d361fe8fa9`. Probe: H.264 1920×1080, 60 fps, 6,475 frames, 107.916667 s; AAC stereo, 48 kHz, 107.904 s; A/V duration difference 12.667 ms. The generator reports PASS. All 14 reference windows and corresponding contact sheets are present and are described in the analysis report. Production source, beat map, storyboard, master and delivery companions are tracked in the repository; the 199 MB reference MP4 is intentionally ignored to avoid exceeding GitHub's 100 MB single-file limit.

Commands re-run:

```bash
python3 -m py_compile workspace/analysis/analyze_audio.py workspace/analysis/analyze_manus_batches.py workspace/analysis/write_manus_report.py workspace/render_intro.py workspace/delivery/generate_accessible_assets.py
workspace/.venv/bin/python workspace/analysis/analyze_audio.py
workspace/.venv/bin/python workspace/render_intro.py --start 0 --end 300 --output workspace/renders/onset_sync_check_revalidation.mp4
workspace/.venv/bin/python workspace/delivery/generate_accessible_assets.py
ffmpeg -v error -i workspace/renders/newera_ai_agent_intro_master_1080p60.mp4 -f null -
```

The five-second smoke output was removed after verification. Visual/perceptual quality still requires human review; sparse reference analysis is not an exact cut map, and the onset metrics do not establish perceptual frame-accurate synchronization.
