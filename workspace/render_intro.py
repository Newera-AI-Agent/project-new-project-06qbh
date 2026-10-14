#!/usr/bin/env python3
"""Frame-accurate NewEra launch-film renderer; Pillow draws deterministic 60fps frames to FFmpeg."""
import argparse, json, math, os, subprocess, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
W,H,FPS = 1920,1080,60
BG=(7,7,9); WHITE=(244,244,246); MINT=(183,255,226); TEAL=(53,228,208); BLUE=(108,124,255); MUTED=(113,119,128); PANEL=(17,19,22); LINE=(45,49,55)
FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'; BOLD='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'; MONO='/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'
font=lambda size,bold=False,mono=False: ImageFont.truetype(MONO if mono else (BOLD if bold else FONT),size)

def clamp(x,a=0.,b=1.): return max(a,min(b,x))
def smooth(x):
    x=clamp(x); return x*x*(3-2*x)
def out(x):
    x=clamp(x); return 1-(1-x)**4

def mix(a,b,t): return tuple(int(x+(y-x)*t) for x,y in zip(a,b))
def rounded(draw,box,r,fill,outline=None,width=1):
    draw.rounded_rectangle(tuple(map(int,box)),radius=int(r),fill=fill,outline=outline,width=width)
def spaced(draw,xy,text,f,fill,spacing=0):
    x,y=xy
    for ch in text:
        draw.text((x,y),ch,font=f,fill=fill,anchor='lt')
        x+=draw.textlength(ch,font=f)+spacing
    return x

def centered(draw,xy,text,f,fill,spacing=0):
    width=sum(draw.textlength(c,font=f) for c in text)+max(0,len(text)-1)*spacing
    spaced(draw,(xy[0]-width/2,xy[1]),text,f,fill,spacing)

def create_background():
    # Soft radial lift and fine architectural dot field: one reusable static layer.
    yy,xx=np.mgrid[0:H:2,0:W:2]
    dx=(xx-W*.52)/(W*.72); dy=(yy-H*.43)/(H*.82)
    glow=np.exp(-(dx*dx+dy*dy)*3.5)
    arr=np.empty((H//2,W//2,3),dtype=np.uint8)
    for c,base in enumerate(BG): arr[:,:,c]=np.clip(base+glow*(3 if c==0 else 4 if c==1 else 5),0,255)
    im=Image.fromarray(arr,'RGB').resize((W,H),Image.Resampling.BILINEAR)
    d=ImageDraw.Draw(im,'RGBA')
    for x in range(64,W,32):
        for y in range(52,H,32): d.ellipse((x,y,x+1,y+1),fill=(190,205,205,13))
    d.line((88,70,1832,70),fill=(120,140,145,23),width=1)
    d.line((88,1010,1832,1010),fill=(120,140,145,23),width=1)
    return im

BG_LAYER=create_background()

def draw_hud(d,t,scene,energy=0):
    f=font(17,mono=True)
    d.text((90,34),'NEWERA  /  AUTONOMOUS BUILD SYSTEM',font=f,fill=(133,146,148,210))
    right=f'{int(t//60):02d}:{int(t%60):02d}   /   {scene:02d}'
    d.text((1830,34),right,font=f,fill=(133,146,148,210),anchor='rt')
    # Short responsive waveform, low amplitude, anchored below safe title region.
    mid=H-42
    for i in range(48):
        amp=3+energy*(3+((i*17+int(t*11))%9))
        x=850+i*5
        d.line((x,mid-amp,x,mid+amp),fill=(53,228,208,100 if i%4 else 175),width=2)
    d.text((90,H-63),'IDEA  →  PLAN  →  BUILD  →  SHIP',font=font(16,mono=True),fill=(111,120,124,210))
    d.text((1830,H-63),'60 FPS  •  HUMAN-APPROVED',font=font(16,mono=True),fill=(111,120,124,210),anchor='rt')

def draw_core(d,cx,cy,r,t,energy=0,solid=False):
    pulse=1+0.035*math.sin(t*math.pi*2*2.08)+0.045*energy
    r*=pulse
    for j in range(4):
        rr=r*(1+j*.22)
        a=max(15,95-j*19)
        d.ellipse((cx-rr,cy-rr,cx+rr,cy+rr),outline=(*TEAL,a),width=max(1,3-j//2))
    # A precise, non-cliché orbital mark built from arcs and a central square.
    d.arc((cx-r*1.2,cy-r*1.2,cx+r*1.2,cy+r*1.2),start=(t*58)%360,end=(t*58)%360+230,fill=(*MINT,230),width=4)
    d.rounded_rectangle((cx-r*.24,cy-r*.24,cx+r*.24,cy+r*.24),radius=int(r*.08),fill=(*MINT,245))
    d.ellipse((cx-r*.065,cy-r*.065,cx+r*.065,cy+r*.065),fill=BG)
    for i in range(8):
        a=t*.45+i*math.pi/4
        x=cx+math.cos(a)*r*1.48; y=cy+math.sin(a)*r*1.48
        d.ellipse((x-3,y-3,x+3,y+3),fill=(*TEAL,180))

def scene_label(d,kicker,title,subtitle,t,local,accent=TEAL):
    p=out(local/.38)
    y=430+(1-p)*50
    d.text((960, y-72),kicker.upper(),font=font(20,mono=True),fill=(*accent,int(210*p)),anchor='mm')
    centered(d,(960,y),title,font(88,True),(*WHITE,int(255*p)),-2.4)
    if subtitle:
        centered(d,(960,y+116),subtitle,font(29),(*MUTED,int(255*p)))

def card(d,box,title,body,tag,t,active=True):
    x1,y1,x2,y2=box
    rounded(d,box,18,PANEL,LINE,2)
    d.text((x1+28,y1+23),tag.upper(),font=font(15,mono=True),fill=TEAL if active else MUTED)
    d.text((x1+28,y1+65),title,font=font(29,True),fill=WHITE)
    d.multiline_text((x1+28,y1+110),body,font=font(19),fill=(157,165,169),spacing=10)
    # State marker is functional, quiet and consistent.
    d.ellipse((x2-33,y1+27,x2-21,y1+39),fill=TEAL if active else (74,80,84))

def make_frames(start,end,preview=None):
    beat=json.loads((ROOT/'workspace/beat_map.json').read_text())
    duration=beat['duration_sec']; ons=beat['onsets']; env=beat['band_envelope_50ms']
    raw_bounds=[0,15,30,60,90,duration]
    # Snap act changes to actual detected onsets and expose the exact frame map in the storyboard.
    bounds=[0]
    for sec in raw_bounds[1:-1]:
        e=min(ons,key=lambda q:abs(q['time_sec']-sec))
        bounds.append(int(e['frame_60fps']))
    bounds.append(int(round(duration*FPS)))
    boundaries=[f/FPS for f in bounds]
    storyboard=json.loads((ROOT/'workspace/storyboard.json').read_text())
    storyboard['actual_scene_boundaries']=[{'sec':round(s,4),'frame':f,'nearest_onset_ms':None if i in (0,len(bounds)-1) else ons[min(range(len(ons)),key=lambda j:abs(ons[j]['frame_60fps']-f))]['ms']} for i,(s,f) in enumerate(zip(boundaries,bounds))]
    for i,act in enumerate(storyboard['acts']):
        act['start_sec']=round(boundaries[i],4); act['end_sec']=round(boundaries[i+1],4)
        act['start_frame']=bounds[i]; act['end_frame']=bounds[i+1]
    # Editorial punctuation uses salient low/mid/high-band peaks, with a minimum gap to protect legibility.
    peaks=[]
    for name,events in beat['band_peak_events'].items():
        for e in events:
            if e['time_sec']>.5 and e['time_sec']<duration-.5: peaks.append((e['frame_60fps'],name,e['strength']))
    peaks.sort(key=lambda q:q[0]); selected=[]
    for fr,name,strength in peaks:
        if all(abs(fr-x[0])>34 for x in selected): selected.append((fr,name,strength))
    storyboard['selected_punctuation_cues']=[{'frame':f,'ms':round(f*1000/FPS),'band':n,'relative_strength':s} for f,n,s in selected]
    (ROOT/'workspace/storyboard.json').write_text(json.dumps(storyboard,indent=2)+'\n')
    onset_frames={int(e['frame_60fps']) for e in ons}
    total=int(round(duration*FPS)); end=min(total,end if end is not None else total)
    cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-an','-c:v','libx264','-preset','ultrafast','-crf','17','-pix_fmt','yuv420p','-movflags','+faststart',str(preview or ROOT/'workspace/renders/visual_only.mp4')]
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE)
    frames=0
    for frame in range(start,end):
        t=frame/FPS; scene=max(0,min(4,next((i for i in range(5) if bounds[i]<=frame<bounds[i+1]),4)))
        local=t-boundaries[scene]; length=boundaries[scene+1]-boundaries[scene]
        env_i=min(len(env)-1,max(0,int(t*20)))
        e=env[env_i]; energy=max(e['sub'],e['mid'],e['high'])
        im=BG_LAYER.copy(); d=ImageDraw.Draw(im,'RGBA')
        # Transient response: 7-frame eased envelope; no full-frame strobing.
        punch=max((1-(frame-hit)/7 for hit in onset_frames if 0<=frame-hit<7),default=0.0)
        punch=out(punch)*.055
        # Layered corner registration marks establish a designed frame; transients briefly energize them.
        mark_alpha=int(100+125*min(1,punch/.055))
        mark_len=28+int(8*min(1,punch/.055))
        for x,sgn in ((90,1),(1830,-1)):
            d.line((x,91,x+sgn*mark_len,91),fill=(89,106,109,mark_alpha),width=2)
            d.line((x,91,x,119+int(4*min(1,punch/.055))),fill=(89,106,109,mark_alpha),width=2)
        if scene==0:
            # Point → axes → frame → idea, keyed to the opening pluck rhythm.
            cx,cy=960,470; progress=clamp(local/8.8)
            if progress>.03:
                q=out((progress-.03)/.25); d.line((cx-390,cy,cx-390+780*q,cy),fill=(*TEAL,210),width=2)
            if progress>.24:
                q=out((progress-.24)/.22); d.line((cx,cy-245,cx,cy-245+490*q),fill=(*TEAL,190),width=2)
            if progress>.43:
                q=out((progress-.43)/.2); d.rounded_rectangle((cx-410,cy-175,cx+410,cy+175),radius=12,outline=(*MINT,int(180*q)),width=2)
            draw_core(d,cx,cy,40+70*out((progress-.07)/.55),t,energy+punch)
            if local>3.1:
                p=out((local-3.1)/.45)
                centered(d,(960,cy+245),'A PROMPT STARTS IT.',font(50,True),(*WHITE,int(255*p)),-1.2)
            if local>7.1:
                p=out((local-7.1)/.38)
                centered(d,(960,cy+326),'AN AGENT CARRIES IT THROUGH.',font(25,mono=True),(*MINT,int(240*p)),1.5)
            d.text((960,875),'ONE IDEA  /  A WHOLE BUILD',font=font(18,mono=True),fill=(155,169,171,220),anchor='mm')
        elif scene==1:
            # Onset-aligned high-contrast launch title; core settles into the custom orbital mark.
            if local<.12 and local>0:
                d.rectangle((0,0,W,H),fill=(244,244,246,75))
            draw_core(d,960,400,116,t,energy+punch)
            p=out((local-.2)/.42)
            centered(d,(960,610),'NEWERA',font(116,True),(*WHITE,int(255*p)),-5)
            centered(d,(960,730),'AI AGENT',font(33,mono=True),(*MINT,int(255*p)),5)
            centered(d,(960,798),'FROM AN IDEA TO A WORKING APP.',font(29),(*MINT,int(255*out((local-.8)/.4))))
            if local>7.8:
                card(d,(595,850,1325,966),'Your next build starts here','Describe what you want to make.','NEW PROJECT',t,True)
        elif scene==2:
            # Product workflow: a readable original interface metaphor, not fake product screenshots.
            phase=int(local/5.8)%5; step=['01  DESCRIBE','02  PLAN','03  WRITE FILES','04  BUILD + FIX','05  DEPLOY'][phase]
            scene_label(d,'THE WHOLE LOOP',step, ['Start with a plain-language app idea.','Turn intent into a clear plan.','Create the project, file by file.','Build. Read the error. Fix. Repeat.','Push only with your approval.'][phase],t,local%5.8)
            x0=365; y0=625; widths=[220,220,270,245,225]; gap=25
            for i,(label,wid) in enumerate(zip(['IDEA','PLAN','FILES','BUILD','SHIP'],widths)):
                x=x0+sum(widths[:i])+gap*i
                active=i<=phase
                rounded(d,(x,y0,x+wid,y0+108),15,(20,24,27) if active else (12,14,17),(*TEAL,170) if i==phase else (55,62,66,180),2)
                centered(d,(x+wid/2,y0+34),f'{i+1:02d}',font(16,mono=True),TEAL if active else MUTED)
                centered(d,(x+wid/2,y0+70),label,font(21,True),WHITE if active else (111,119,123))
                if i<4:
                    yy=y0+54; d.line((x+wid+4,yy,x+wid+gap-4,yy),fill=(*MINT,180 if i<phase else 55),width=2)
            card(d,(540,790,1380,955),['Describe your app','A plan takes shape','Project files come together','The build is checked and repaired','Your approval comes first'][phase],['A simple idea becomes a build brief.','Tasks break into clear, reviewable steps.','An autonomous agent writes the app.','A failed build guides the next fix.','GitHub push and deployment are consent-gated.'][phase],step,t,True)
            d.text((960,985),'NO LOGIN REQUIRED  •  FREE ONLINE WORKFLOW',font=font(16,mono=True),fill=(129,138,141),anchor='mm')
        elif scene==3:
            # Modular bento panels bloom in on the groove; impact words punctuate the sections.
            phase=int(local/4.6)%6; captions=[('THINK','A plan with a purpose.'),('MAKE','Code shaped from your brief.'),('CHECK','Build, inspect, improve.'),('BROWSER','See the result take form.'),('AGENTS','Parallel work, one outcome.'),('SHIP','Your approval. Then deploy.')]
            cards=[(260,365,940,610),(980,365,1660,610),(260,635,720,835),(760,635,1210,835),(1250,635,1660,835)]
            for i,box in enumerate(cards):
                x1,y1,x2,y2=box; a=out((local-i*.16)/.5)
                rounded(d,box,17,(17,19,22),(*TEAL,int(40+125*a)) if i==phase%5 else (43,48,53),2)
                if i==0:
                    spaced(d,(x1+29,y1+25),'LIVE WORKFLOW',font(15,mono=True),TEAL,1)
                    d.text((x1+29,y1+73),'A system, not a prompt.',font=font(34,True),fill=WHITE)
                    # node graph
                    pts=[(x1+65,y1+165),(x1+225,y1+135),(x1+385,y1+180),(x1+560,y1+135)]
                    for a1,b1 in zip(pts,pts[1:]): d.line((*a1,*b1),fill=(64,101,98,200),width=3)
                    for j,(xx,yy) in enumerate(pts):
                        d.ellipse((xx-9,yy-9,xx+9,yy+9),fill=TEAL if j<=phase%5 else (77,92,93))
                elif i==1:
                    spaced(d,(x1+27,y1+24),'BUILD / STATUS',font(15,mono=True),TEAL,1)
                    d.text((x1+27,y1+67),'Checks, then fixes.',font=font(31,True),fill=WHITE)
                    for j in range(4):
                        yy=y1+132+j*23; d.ellipse((x1+31,yy,x1+42,yy+11),fill=TEAL if j<phase%5 else (67,73,78))
                        d.rounded_rectangle((x1+58,yy+2,x1+330,yy+8),radius=3,fill=(69,79,79) if j<phase%5 else (40,45,49))
                        d.text((x1+350,yy-6),['plan','write','build','repair'][j],font=font(16,mono=True),fill=(181,190,193))
                else:
                    title,body=[('PLAN','Break down'),('CODE','Write files'),('BROWSER','Preview'),('SHIP','With consent')][i-2]
                    d.text((x1+24,y1+24),title,font=font(14,mono=True),fill=TEAL)
                    d.text((x1+24,y1+74),body,font=font(24,True),fill=WHITE)
                    d.line((x1+24,y2-30,x2-24,y2-30),fill=(57,66,68),width=2)
                    d.ellipse((x2-48,y1+22,x2-34,y1+36),fill=TEAL if phase>=i-2 else (77,84,88))
            impact,bdy=captions[phase]
            p=out((local%4.6)/.3)
            centered(d,(960,235),impact,font(75,True),(*WHITE,int(248*p)),-3)
            centered(d,(960,327),bdy,font(22,mono=True),(*MINT,int(245*p)),.8)
            d.text((960,900),'PLAN   /   BUILD   /   VERIFY   /   DEPLOY',font=font(18,mono=True),fill=(153,166,168),anchor='mm')
        else:
            # Graphic elements fold inward and decelerate into a generous, iconic end-card.
            remain=length-local; settle=out(local/2.3)
            cx,cy=960,407
            draw_core(d,cx,cy,112*(1-.12*settle),t,energy*.4)
            radius=370*(1-out(local/2.6))
            for i in range(4):
                a=t*.14+i*math.pi/2
                x=cx+math.cos(a)*radius; y=cy+math.sin(a)*radius
                d.rounded_rectangle((x-14,y-14,x+14,y+14),radius=5,outline=(*TEAL,130),width=2)
            p=out((local-.5)/.5)
            centered(d,(960,622),'NewEra AI Agent',font(74,True),(*WHITE,int(255*p)),-2.3)
            centered(d,(960,727),'newera.namansoni.in',font(29,mono=True),(*MINT,int(255*out((local-1.0)/.5))),1.1)
            centered(d,(960,812),'BUILT BY NAMAN SONI',font(17,mono=True),(*MUTED,int(245*out((local-1.7)/.5))),2)
            d.line((760,875,1160,875),fill=(*TEAL,int(145*settle)),width=2)
        # Fading scene seam via geometry/hud, not a dead black gap.
        draw_hud(d,t,scene+1,energy)
        if preview and frames==0: im.save(str(preview).replace('.mp4','.png'))
        proc.stdin.write(im.tobytes()); frames+=1
        if frames%300==0: print(f'frame {frame}/{end} ({frame/FPS:.1f}s)',file=sys.stderr,flush=True)
    proc.stdin.close(); rc=proc.wait()
    if rc: raise SystemExit(f'ffmpeg exited {rc}')
    print(f'Rendered {frames} frames [{start}, {end}) at {FPS} fps',file=sys.stderr)

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--start',type=int,default=0); ap.add_argument('--end',type=int); ap.add_argument('--output'); a=ap.parse_args()
    outpath=Path(a.output) if a.output else ROOT/'workspace/renders/visual_only.mp4'
    make_frames(a.start,a.end,outpath)
