#!/usr/bin/env python3
"""Create auditable 12-second visual/audio batches for the supplied reference film."""
import json, subprocess, tempfile
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.signal import stft, find_peaks
from scipy.io import wavfile
ROOT=Path(__file__).resolve().parents[2]
VIDEO=ROOT/'workspace/reference/manus_intro.mp4'
OUT=ROOT/'workspace/analysis/manus_12s'; OUT.mkdir(parents=True,exist_ok=True)
probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(VIDEO)]))
duration=float(probe['format']['duration'])
with tempfile.TemporaryDirectory(prefix='manus12-') as tmp:
 subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-i',str(VIDEO),'-vf','fps=2/3,scale=480:-2','-q:v','4',f'{tmp}/f_%05d.jpg'],check=True)
 frames=sorted(Path(tmp).glob('f_*.jpg')); sampled=[Image.open(p).convert('RGB').copy() for p in frames]
 wav=Path(tmp)/'audio.wav'
 subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-i',str(VIDEO),'-vn','-ac','1','-ar','22050','-f','wav',str(wav)],check=True)
 sr,audio=wavfile.read(wav); audio=audio.astype(np.float32)
 if audio.size and np.max(np.abs(audio))>0: audio/=np.max(np.abs(audio))
 freqs,times,Z=stft(audio,fs=sr,nperseg=2048,noverlap=1536,boundary=None); power=np.abs(Z)**2
 bands={'low_20_120':(20,120),'mid_250_2500':(250,2500),'high_4000_plus':(4000,11025)}
 summaries=[]
 try: font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',16)
 except OSError: font=ImageFont.load_default()
 for start in np.arange(0,duration,12.0):
  end=min(duration,start+12); ids=[int(round(t/1.5)) for t in np.arange(start,end,1.5)]; ids=[i for i in ids if i<len(sampled)]; tiles=[]
  for i in ids:
   tile=Image.new('RGB',(480,298),(8,9,12)); tile.paste(sampled[i].resize((480,270)),(0,28)); ImageDraw.Draw(tile).text((12,6),f'{i*1.5:06.1f}s',font=font,fill=(225,232,236)); tiles.append(tile)
  cols=2; rows=(len(tiles)+cols-1)//cols; sheet=Image.new('RGB',(cols*480,rows*298),(17,19,23))
  for j,tile in enumerate(tiles): sheet.paste(tile,((j%cols)*480,(j//cols)*298))
  lo=int(start*22050); hi=min(len(audio),int(end*22050)); seg=audio[lo:hi]; rms=float(np.sqrt(np.mean(seg**2))) if len(seg) else 0
  mask=(times>=start)&(times<end); bandmeans={name:float(np.mean(power[(freqs>=rng[0])&(freqs<rng[1])][:,mask])) if mask.any() else 0 for name,rng in bands.items()}
  spec=power[:,mask]; event_times=[]
  if spec.shape[1]>2:
   flux=np.maximum(0,np.diff(np.sqrt(spec+1e-15),axis=1)).sum(axis=0); step=times[1]-times[0]
   peaks,_=find_peaks(flux,distance=max(1,int(.12/step)),prominence=max(float(np.std(flux)*.7),1e-12))
   local_times=times[mask]
   event_times=[round(float(local_times[min(p+1,len(local_times)-1)]),3) for p in peaks]
  deltas=[]
  for a,b in zip(ids,ids[1:]): deltas.append(float(np.abs(np.asarray(sampled[a].resize((120,68)),dtype=np.int16)-np.asarray(sampled[b].resize((120,68)),dtype=np.int16)).mean()/255))
  fname=f'batch_{int(start):03d}_{int(end):03d}.jpg'; sheet.save(OUT/fname,quality=88,optimize=True)
  summaries.append({'start_sec':round(float(start),3),'end_sec':round(float(end),3),'contact_sheet':f'analysis/manus_12s/{fname}','sample_count':len(ids),'sample_interval_sec':1.5,'reference_audio_rms':round(rms,6),'mean_band_power':{k:round(v,10) for k,v in bandmeans.items()},'spectral_flux_events_sec':event_times,'sampled_frame_mean_abs_delta_0_1':round(float(np.mean(deltas)),4) if deltas else 0,'frame_delta_count':len(deltas)})
result={'source':'reference/manus_intro.mp4','duration_sec':round(duration,3),'video_fps':30,'audio_sample_rate_hz':sr,'method':'12-second windows; frames sampled every 1.5 seconds (8 per full window), reference audio decoded and summarized using RMS, coarse STFT band power and spectral-flux novelty. Image delta is low-resolution adjacent-sample pixel difference, not a cut detector.','limitations':'Sparse stills and coarse signal summaries indicate visual/state changes and audio activity; they do not establish exact cut boundaries, motion curves, perceived loudness, semantic contents between samples, or sync tolerance. Spectral-flux events are novelty candidates, not verified musical beats.','batches':summaries}
(OUT/'analysis.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'duration_sec':duration,'batch_count':len(summaries),'output':str(OUT),'sheets':[x['contact_sheet'] for x in summaries]},indent=2))
