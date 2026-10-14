# NewEra AI Agent — launch intro production package

This repository contains a finished **107.9-second, 1920×1080, 60 fps** launch intro for NewEra AI Agent, founded by Naman Soni. The master is a rendered H.264/AAC MP4 with the supplied “Life Force” soundtrack and restrained transition foley.

## Master deliverable

- **Video:** [`workspace/renders/newera_ai_agent_intro_master_1080p60.mp4`](workspace/renders/newera_ai_agent_intro_master_1080p60.mp4)
- **Delivery notes, reproduction commands and technical QA:** [`workspace/delivery/README.md`](workspace/delivery/README.md)
- **Captions and visual transcript:** [`workspace/delivery/newera_intro_captions.vtt`](workspace/delivery/newera_intro_captions.vtt), [`workspace/delivery/newera_intro_transcript.md`](workspace/delivery/newera_intro_transcript.md)
- **QC evidence:** [`workspace/delivery/qc_report.json`](workspace/delivery/qc_report.json)

## Production and research sources

- Brand research: [`workspace/brand_brief.md`](workspace/brand_brief.md)
- Five-act frame-accurate production plan: [`workspace/storyboard.json`](workspace/storyboard.json)
- Soundtrack DSP/onset map: [`workspace/beat_map.json`](workspace/beat_map.json), analysis source [`workspace/analysis/analyze_audio.py`](workspace/analysis/analyze_audio.py)
- Original programmatic renderer: [`workspace/render_intro.py`](workspace/render_intro.py)
- Transition foley synthesis: [`workspace/audio/synthesize_transition_foley.py`](workspace/audio/synthesize_transition_foley.py)
- Manus reference investigation and limitations: [`workspace/manus_analysis.md`](workspace/manus_analysis.md), with sampled batch reports under [`workspace/analysis/manus_12s/`](workspace/analysis/manus_12s/) and a reproducible per-frame/audio candidate supplement at [`workspace/analysis/manus_frame_events/`](workspace/analysis/manus_frame_events/).

The 199 MB reference MP4 is retained locally at `workspace/reference/manus_intro.mp4` and intentionally excluded from Git because of GitHub's 100 MB per-file limit. The analysis distinguishes automated candidates from verified edits or perceptual audio-picture sync. Public/commercial use of the supplied music requires appropriate rights and clearance; see delivery notes.
