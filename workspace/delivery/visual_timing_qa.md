# Encoded-master visual and timing QA

**Artifact reviewed:** `workspace/renders/newera_ai_agent_intro_master_1080p60.mp4`  
**Method:** frame extraction with FFmpeg; image statistics using `workspace/.venv` Pillow; FFmpeg threshold `blackdetect`; checked against the recorded storyboard boundaries. These are objective technical observations, not a substitute for human viewing.

## Findings

- The encoded master is 1920×1080 at 60 fps, 6,475 frames, 107.916667 s. Previously recorded full-decode/QC evidence reports H.264 video, stereo AAC, 12.667 ms stream-duration delta, and successful full decode.
- Boundary samples at frames 924 (15.4 s), 1,802 (30.033 s), 3,600 (60.0 s), and 5,388 (89.8 s) extracted and decoded. The first transition sample is brighter than its preceding frame: mean luma 10.40 at frame 923 and 11.95 at frame 924. At the 15.433–15.500 s samples, the downscaled frame is fully above luma 50, followed at 15.533 s by a return to a dark average of 12.87. This establishes a brief high-contrast inversion/flash in the encoded frames, not its subjective appearance or its perceptual alignment to a musical transient.
- Ending samples at 89.8, 90, 91, 95, 100, 105, 107 and 107.8 s were nonempty, consistently dark graphic frames (full-resolution mean luma about 10.47–10.62; 1.82–1.97% of pixels above luma 30; 1.33–1.38% above 80 in these samples). This differs from a blank/near-uniform black output, but pixel summaries cannot establish the end-card copy's legibility or contrast at viewing size. Storyboard specifies the NewEra name, site and founder credit; visual legibility remains for human confirmation.
- FFmpeg `blackdetect=d=0.08:pix_th=0.08:pic_th=0.98` classified 0–7.283 s and 90.0167–107.9 s, plus scattered opening intervals, as near-black. The threshold is an automated classification, not evidence of accidental dead frames: the sampled end frames retain measurable graphic content, and the opening is storyboarded as a dark minimalist build. No evidence-backed edit is warranted from this detector alone.
- Existing ROI analysis found a small, decaying image response around the 384 recorded onset frames, peaking at frame +2 and decaying by +7. Existing QC gives onset-frame quantization error up to 8.3 ms. These checks establish technical correspondence only; neither proves perceptual ±1-frame sync nor listener-perceived smoothness.

## Disposition and limits

No encoded-master correction was made: the objective checks did not establish a defect, and a speculative visual change could alter the reviewed/baselined package. The contact sheet is available at `.newera/browser/qa_contact.jpg` for a human to inspect. A human review is still required for overall design quality, end-card readability, perceived cut-to-music sync, and subjective foley/music balance. Confirm music/reference rights before public or commercial distribution.

Reproduction: extraction/statistics used FFmpeg seeking and Pillow from `workspace/.venv`; black detection command:

```sh
ffmpeg -hide_banner -v info -i workspace/renders/newera_ai_agent_intro_master_1080p60.mp4 -vf "blackdetect=d=0.08:pix_th=0.08:pic_th=0.98" -an -f null -
```
