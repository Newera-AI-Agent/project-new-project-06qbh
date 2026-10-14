#!/usr/bin/env python3
"""Extract per-frame scene-change candidates and dense reference-audio events.

All detections are signal-level candidates, not human-verified editorial cuts,
musical beats, perceptual sync measurements, or semantic video annotations.
Requires FFmpeg/FFprobe, NumPy, SciPy; writes a compact JSON summary plus CSVs.
"""
import csv
import json
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import find_peaks, stft

ROOT = Path(__file__).resolve().parents[2]
VIDEO = ROOT / 'workspace/reference/manus_intro.mp4'
OUT = ROOT / 'workspace/analysis/manus_frame_events'
OUT.mkdir(parents=True, exist_ok=True)
THRESHOLDS = (5, 10, 15, 20)
WINDOW_SEC = 12.0
AUDIO_RATE = 22050
HOP = 441  # 20 ms at 22.05 kHz


def run(args):
    return subprocess.check_output(args, text=True, stderr=subprocess.PIPE)


def main():
    probe = json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(VIDEO)]))
    vs = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    duration = float(probe['format']['duration'])
    fps = float(eval(vs['avg_frame_rate']))
    with tempfile.TemporaryDirectory(prefix='newera-ref-events-') as td:
        metadata = Path(td) / 'scene_metadata.txt'
        wav = Path(td) / 'audio.wav'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', str(VIDEO),
                        '-vf', 'scdet=threshold=0,metadata=print:file=' + str(metadata),
                        '-an', '-f', 'null', '-'], check=True)
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', str(VIDEO),
                        '-vn', '-ac', '1', '-ar', str(AUDIO_RATE), '-f', 'wav', str(wav)], check=True)
        raw = metadata.read_text(errors='replace')
        frames = []
        current = None
        for line in raw.splitlines():
            if line.startswith('frame:'):
                if current is not None:
                    frames.append(current)
                m = re.match(r'frame:(\d+)\s+pts:(\S+)\s+pts_time:(\S+)', line)
                if m:
                    current = {'frame': int(m.group(1)), 'pts': int(m.group(2)), 'time_sec': float(m.group(3))}
            elif current is not None:
                m = re.match(r'lavfi\.scd\.(mafd|score|time)=([\d.eE+-]+)', line.strip())
                if m:
                    current[m.group(1)] = float(m.group(2))
        if current is not None:
            frames.append(current)
        if not frames or any('score' not in f for f in frames):
            raise RuntimeError(f'Could not parse complete scdet metadata; parsed {len(frames)} frames')
        frame_csv = OUT / 'per_frame_scene_scores.csv'
        with frame_csv.open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['frame', 'pts', 'time_sec', 'score', 'mafd', 'scdet_time_sec'])
            w.writeheader()
            for row in frames:
                w.writerow({'frame': row['frame'], 'pts': row['pts'], 'time_sec': row['time_sec'],
                            'score': row['score'], 'mafd': row.get('mafd', ''),
                            'scdet_time_sec': row.get('time', '')})

        scores = np.asarray([x['score'] for x in frames])
        candidate_counts = {}
        threshold_events = {}
        for th in THRESHOLDS:
            indices = np.flatnonzero(scores >= th)
            threshold_events[str(th)] = [
                {'frame': frames[i]['frame'], 'time_sec': round(frames[i]['time_sec'], 6),
                 'score': round(float(scores[i]), 4)} for i in indices
            ]
            candidate_counts[str(th)] = len(indices)
        # Local maxima with a 3-frame minimum gap; retain scores >= 5 only.
        peak_idx, peak_props = find_peaks(scores, height=5, distance=3, prominence=3)
        local_peaks = [
            {'frame': frames[i]['frame'], 'time_sec': round(frames[i]['time_sec'], 6),
             'score': round(float(scores[i]), 4), 'prominence': round(float(p), 4)}
            for i, p in zip(peak_idx, peak_props['prominences'])
        ]
        windows = []
        for start in np.arange(0, duration, WINDOW_SEC):
            end = min(duration, start + WINDOW_SEC)
            sel = [x for x in frames if start <= x['time_sec'] < end]
            windows.append({'start_sec': round(float(start), 3), 'end_sec': round(float(end), 3),
                            'frames': len(sel),
                            'mean_score': round(float(np.mean([x['score'] for x in sel])), 5) if sel else 0,
                            'max_score': round(float(max((x['score'] for x in sel), default=0)), 5),
                            'candidate_counts_by_threshold': {
                                str(th): sum(x['score'] >= th for x in sel) for th in THRESHOLDS}})

        sr, audio = wavfile.read(wav)
        audio = audio.astype(np.float32)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        peak = float(np.max(np.abs(audio))) if audio.size else 0
        if peak:
            audio /= peak
        freqs, times, z = stft(audio, fs=sr, nperseg=2048, noverlap=2048-HOP,
                               boundary=None, padded=False)
        mag = np.abs(z)
        bands = {'sub_bass_kick_20_120': (20, 120), 'low_mid_120_250': (120, 250),
                 'guitar_mid_250_2500': (250, 2500), 'high_4000_plus': (4000, sr/2)}
        band_energy = {}
        for name, (lo, hi) in bands.items():
            mask = (freqs >= lo) & (freqs < hi)
            band_energy[name] = np.mean(mag[mask] ** 2, axis=0) if np.any(mask) else np.zeros(len(times))
        # Positive spectral flux + per-band energy peaks are novelty cues, not beats.
        flux = np.maximum(0, np.diff(mag, axis=1)).sum(axis=0)
        flux_times = times[1:]
        flux_threshold = max(float(np.mean(flux) + 2.5 * np.std(flux)), 1e-10)
        flux_peaks, _ = find_peaks(flux, height=flux_threshold, distance=max(1, round(.10*sr/HOP)), prominence=float(np.std(flux)))
        audio_csv = OUT / 'audio_features_20ms.csv'
        with audio_csv.open('w', newline='') as f:
            names = ['time_sec', 'rms_20ms', 'spectral_flux'] + [k + '_power' for k in bands]
            w = csv.writer(f); w.writerow(names)
            # Local RMS over the corresponding 20-ms analysis hop.
            for j, t in enumerate(times):
                lo = max(0, int(t*sr)-HOP//2); hi = min(len(audio), lo+HOP)
                rms = float(np.sqrt(np.mean(audio[lo:hi]**2))) if hi > lo else 0
                fx = float(flux[j-1]) if 0 < j <= len(flux) else 0
                w.writerow([f'{t:.6f}', f'{rms:.8g}', f'{fx:.8g}'] + [f'{v[j]:.8g}' for v in band_energy.values()])
        audio_events = []
        for j in flux_peaks:
            i = int(j + 1)
            audio_events.append({'time_sec': round(float(flux_times[j]), 6),
                                 'frame_30fps_nearest': int(round(float(flux_times[j])*fps)),
                                 'spectral_flux': round(float(flux[j]), 8),
                                 'band_power': {k: round(float(v[i]), 10) for k, v in band_energy.items()}})
        summary = {
            'source': 'reference/manus_intro.mp4', 'duration_sec': round(duration, 6),
            'video': {'fps': fps, 'frames': len(frames), 'dimensions': [int(vs['width']), int(vs['height'])]},
            'method': 'FFmpeg scdet threshold=0 metadata captured for every decoded video frame; mono audio decoded at 22050 Hz and analyzed by 2048-point STFT with 441-sample (20 ms) hop. Per-frame scene scores, thresholds, local peak candidates, windows and audio feature CSV are reproducible.',
            'scene_change_candidate_counts_by_score_threshold': candidate_counts,
            'scene_change_threshold_events': threshold_events,
            'local_scene_score_peaks_height_5_distance_3_frames_prominence_3': local_peaks,
            'window_sec': WINDOW_SEC, 'windows': windows,
            'audio': {'sample_rate_hz': sr, 'analysis_hop_ms': 1000*HOP/sr,
                      'spectral_flux_global_candidate_threshold_mean_plus_2_5sd': flux_threshold,
                      'spectral_flux_peak_candidates': audio_events,
                      'band_power_measurements': list(bands.keys()),
                      'features_csv': 'analysis/manus_frame_events/audio_features_20ms.csv'},
            'per_frame_csv': 'analysis/manus_frame_events/per_frame_scene_scores.csv',
            'limitations': 'scdet scores respond to image changes and can include hard cuts, flashes, motion, dissolves, compression, or other changes; threshold events and local maxima are candidates only, not verified editorial cuts. Audio spectral-flux candidates and band powers do not identify instruments, musical beats, loudness perception, separated stems, or picture-to-audio sync. Frame/audio event correlation is intentionally not asserted. Inspect source/contact sheets and audition manually for semantic or perceptual claims.'}
        (OUT / 'analysis.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps({'video_frames': len(frames), 'duration_sec': duration,
                          'candidate_counts': candidate_counts,
                          'local_score_peaks': len(local_peaks),
                          'audio_flux_candidates': len(audio_events),
                          'outputs': [str(OUT/'analysis.json'), str(frame_csv), str(audio_csv)]}, indent=2))


if __name__ == '__main__':
    main()
