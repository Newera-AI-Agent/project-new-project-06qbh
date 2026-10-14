#!/usr/bin/env python3
"""Reproducible DSP analysis for the supplied Life Force track."""
import json, math
from pathlib import Path
import numpy as np
import librosa

ROOT = Path(__file__).resolve().parents[2]
AUDIO = ROOT / 'ptasinski - life force (ft. RJ Pasin)_128k.mp3'
OUT = ROOT / 'workspace' / 'beat_map.json'
y, sr = librosa.load(AUDIO, sr=22050, mono=True)
duration = len(y) / sr
hop = 220  # 10 ms grid; event times subsequently snapped to 60 fps.
S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop))
times = librosa.frames_to_time(np.arange(S.shape[1]), sr=sr, hop_length=hop)
# Positive spectral flux for onsets, plus tempo estimation on the same signal.
on_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop, aggregate=np.mean)
onset_frames = librosa.onset.onset_detect(onset_envelope=on_env, sr=sr, hop_length=hop,
                                          backtrack=False, units='frames')
onset_sec = librosa.frames_to_time(onset_frames, sr=sr, hop_length=hop)
# Beat tracker may return half/double time; report estimate plus robust interval stats.
tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop, units='frames')
if np.ndim(tempo): tempo = float(np.asarray(tempo).reshape(-1)[0])
beat_sec = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop)
# Spectral centroid, rms, and separated mean squared band energy at 10 ms resolution.
freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
power = S ** 2
bands = {'sub_bass_kick_20_120': (20,120), 'guitar_mid_250_2500': (250,2500), 'high_hat_snare_4000_plus':(4000,11025)}
features = {}
for name,(lo,hi) in bands.items():
    idx=(freqs>=lo)&(freqs<hi)
    e=np.mean(power[idx],axis=0) if np.any(idx) else np.zeros(S.shape[1])
    features[name]=e
# Detect salient local peaks from novelty and per-band envelopes. Threshold at robust high percentile,
# with minimum separation ~70 ms to avoid multiple triggers for one hit.
def peaks(values, percentile=78, min_gap_s=0.07):
    smooth=np.convolve(values, np.ones(5)/5, mode='same')
    threshold=np.percentile(smooth, percentile)
    cand=np.where((smooth[1:-1]>=smooth[:-2])&(smooth[1:-1]>smooth[2:])&(smooth[1:-1]>=threshold))[0]+1
    cand=sorted(cand,key=lambda i:smooth[i], reverse=True)
    kept=[]
    gap=int(min_gap_s*sr/hop)
    for i in cand:
        if all(abs(i-j)>=gap for j in kept): kept.append(int(i))
    kept.sort()
    return [{'time_sec':round(float(times[i]),4),'ms':int(round(float(times[i])*1000)),
             'frame_60fps':int(round(float(times[i])*60)), 'strength':round(float(smooth[i]),6)} for i in kept]
onset_events=[]
for t in onset_sec:
    i=min(len(times)-1, max(0, int(round(t*sr/hop))))
    onset_events.append({'time_sec':round(float(t),4),'ms':int(round(float(t)*1000)),
                         'frame_60fps':int(round(float(t)*60)),
                         'sub_bass':round(float(features['sub_bass_kick_20_120'][i]),7),
                         'mid':round(float(features['guitar_mid_250_2500'][i]),7),
                         'high':round(float(features['high_hat_snare_4000_plus'][i]),7)})
# 10 ms normalized feature samples keep the event map auditable without dumping raw audio.
def normalized(x):
    x=np.sqrt(np.maximum(x,0))
    p99=np.percentile(x,99.5) or 1
    return np.clip(x/p99,0,1)
feature_samples=[]
sub=normalized(features['sub_bass_kick_20_120']); mid=normalized(features['guitar_mid_250_2500']); high=normalized(features['high_hat_snare_4000_plus'])
for i in range(0,len(times),5): # 50 ms compact visual-control envelope
    feature_samples.append({'ms':int(round(float(times[i])*1000)),
        'sub':round(float(sub[i]),3),'mid':round(float(mid[i]),3),'high':round(float(high[i]),3)})
# Segment analysis in 5s blocks to guide editorial structure, based on RMS and low-band means.
rms=librosa.feature.rms(y=y,frame_length=2048,hop_length=hop)[0]
blocks=[]
for start in np.arange(0,duration,5):
    mask=(times>=start)&(times<min(start+5,duration))
    if mask.any(): blocks.append({'start_sec':round(float(start),2),'end_sec':round(float(min(start+5,duration)),2),
        'rms':round(float(np.mean(rms[:len(times)][mask])),6),
        'sub_energy':round(float(np.mean(features['sub_bass_kick_20_120'][mask])),8),
        'mid_energy':round(float(np.mean(features['guitar_mid_250_2500'][mask])),8),
        'high_energy':round(float(np.mean(features['high_hat_snare_4000_plus'][mask])),8)})
# Loudness normalization data comes from ffmpeg ebur128 measurement documented separately.
intervals=np.diff(beat_sec)
bpm_from_beats=60/np.median(intervals) if len(intervals) else float(tempo)
result={'source':AUDIO.name,'duration_sec':round(duration,4),'sample_rate_analysis_hz':sr,
 'analysis_hop_ms':10,'video_fps':60,'time_signature_estimate':'4/4 (metrical estimate; verify by listening)',
 'tempo_bpm_librosa':round(float(tempo),3),'beat_interval_bpm':round(float(bpm_from_beats),3),
 'beat_grid':[{'sec':round(float(t),4),'ms':int(round(float(t)*1000)),'frame':int(round(float(t)*60))} for t in beat_sec],
 'onset_count':len(onset_events),'onsets':onset_events,
 'band_peak_events':{k:peaks(v) for k,v in features.items()},
 'band_envelope_50ms':feature_samples,'five_second_structure':blocks,
 'interpretation':'Band peak triggers are relative spectral-energy peaks, not isolated stems. Onset and beat timestamps are analysis estimates quantized to nearest 60fps frame; audition and visual QA remain required.'}
(ROOT/'workspace'/'beat_map.json').write_text(json.dumps(result,indent=2))
print(json.dumps({'duration':duration,'tempo':tempo,'beat_bpm':bpm_from_beats,'onsets':len(onset_events),'beats':len(beat_sec),'out':'workspace/beat_map.json'}))
