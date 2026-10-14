#!/usr/bin/env python3
"""Create a restrained, deterministic whoosh at the four beat-mapped act changes.

Each transition starts 180 ms before its exact storyboard frame, swells smoothly,
then decays for 520 ms. It is synthesized noise, not a claim of recorded/generated
foley. Output is 48 kHz stereo PCM, peak-limited to a conservative amplitude.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from scipy.signal import butter, sosfilt
from scipy.io.wavfile import write

ROOT = Path(__file__).resolve().parents[2]
STORY = ROOT / 'workspace/storyboard.json'
BEATS = ROOT / 'workspace/beat_map.json'
OUT = ROOT / 'workspace/audio/transition_foley.wav'
SR = 48_000
FPS = 60
START_LEAD = 0.180
TAIL = 0.520
PEAK = 0.035  # approximately -29.1 dBFS before mix


def main() -> None:
    story = json.loads(STORY.read_text())
    beat = json.loads(BEATS.read_text())
    boundaries = story['actual_scene_boundaries']
    if len(boundaries) != 6:
        raise SystemExit(f'Expected 6 scene boundaries; got {len(boundaries)}')
    # Only internal scene transitions; the opening and ending are not treated as cuts.
    events = []
    onset_frames = {int(o['frame_60fps']) for o in beat['onsets']}
    for b in boundaries[1:-1]:
        frame = int(b['frame'])
        if frame not in onset_frames:
            raise SystemExit(f'Transition frame {frame} is not a beat-map onset')
        events.append(frame)
    total_frames = int(boundaries[-1]['frame'])
    n = int(round(total_frames / FPS * SR))
    mix = np.zeros((n, 2), dtype=np.float64)
    rng = np.random.default_rng(20261014)
    # One reusable band-limited noise bed keeps the timbre consistent, while each
    # overlapping slice receives a deterministic independent section of the signal.
    noise = rng.standard_normal(int((START_LEAD + TAIL + 1) * SR))
    sos = butter(3, [500, 9000], btype='bandpass', fs=SR, output='sos')
    noise = sosfilt(sos, noise)
    noise /= max(np.max(np.abs(noise)), 1e-12)
    fade_n = int(round(START_LEAD * SR))
    tail_n = int(round(TAIL * SR))
    length = fade_n + tail_n
    x = np.arange(length, dtype=np.float64) / SR
    # Raised-cosine swell reaches its peak exactly at the frame boundary, then
    # exponentially decays: smooth, non-linear, with no click or artificial slam.
    env = np.empty(length, dtype=np.float64)
    pre = x < START_LEAD
    env[pre] = 0.5 - 0.5 * np.cos(np.pi * x[pre] / START_LEAD)
    env[~pre] = np.exp(-5.0 * (x[~pre] - START_LEAD) / TAIL)
    # Quiet low-mid body and airy high texture; fixed stereo width, no hard panning.
    mono = noise[:length] * env * PEAK
    left = mono * 0.92
    right = mono * 0.86
    offset = int(round((events[0] / FPS - START_LEAD) * SR))
    for frame in events:
        offset = int(round((frame / FPS - START_LEAD) * SR))
        if offset < 0 or offset + length > n:
            raise SystemExit(f'Foley at frame {frame} exceeds soundtrack bounds')
        mix[offset:offset+length, 0] += left
        mix[offset:offset+length, 1] += right
    peak = float(np.max(np.abs(mix)))
    if peak > 0.95:
        raise SystemExit(f'Unexpected foley peak: {peak}')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    write(OUT, SR, np.round(np.clip(mix, -1, 1) * 32767).astype(np.int16))
    report = {'sample_rate_hz': SR, 'duration_sec': round(n / SR, 6),
              'events': [{'frame': f, 'time_sec': round(f / FPS, 6),
                          'audio_start_sec': round(f / FPS - START_LEAD, 6),
                          'audio_peak_sec': round(f / FPS, 6)} for f in events],
              'synthesis': 'deterministic 500–9000 Hz band-limited noise; raised-cosine swell and exponential decay',
              'peak_linear': round(peak, 6), 'nominal_peak_dbfs': round(20*np.log10(PEAK), 2),
              'note': 'Synthetic transition texture, deliberately subtle; subjective mix review is still recommended.'}
    (ROOT / 'workspace/audio/transition_foley.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
