"""PHD-MAIN-JUDGEVIDEO-v1 encode (video image: imageio_ffmpeg's ffmpeg). No new drawing.
  1 B173_판단과정_v1.mp4      the judgment frames (jv_frames.py, frames_all.json order and repeats) at 25 fps: v1: per step 4 fade x 3 + hold 38 = 2.0 s; v2: patches move to their target height in 7 x 3 frames + hold 38 = 2.36 s; result 2.0 s
  2 B173_판단학습과정_v1.mp4  the r6 'input' frame (1.2 s, as in the r6 video) -> the judgment section -> the r6 frames 0 ... 30,000 (1.2 s each, the last 3.0 s)
  both H.264 libx264 -preset veryfast, yuv420p, crf 18, 25 fps constant (the r6 encode rule), via the ffmpeg concat demuxer (durations).
  stills: the last (alpha 1) frame of each step -> stills/B173_판단_<n>_<step>.png (5). scientific_verdict: null"""
import json, shutil, subprocess, hashlib, datetime as dt
from pathlib import Path
import imageio_ffmpeg
OUT = Path('/out'); JD = Path('/jdocs'); R6 = Path('/tl/concept_v2/frames_r6'); ff = imageio_ffmpeg.get_ffmpeg_exe()
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
fr = json.loads((OUT/'frames_all.json').read_text())['frames']
seq = [(f['png'], f['repeat']/25) for f in fr]
def enc(items, name):
    lst = OUT/f'{name}.concat.txt'; L = []
    for p, d in items: L += [f"file '{p}'", f'duration {d:.4f}']
    L.append(f"file '{items[-1][0]}'"); lst.write_text('\n'.join(L)+'\n'); mp4 = OUT/f'{name}.mp4'
    cmd = [ff, '-y', '-hide_banner', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', str(lst), '-vf', 'fps=25,format=yuv420p', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-movflags', '+faststart', str(mp4)]
    subprocess.run(cmd, check=True); pr = [l.strip() for l in subprocess.run([ff, '-hide_banner', '-i', str(mp4)], capture_output=True, text=True).stderr.splitlines() if 'Duration' in l or 'Video:' in l]
    return dict(path=str(mp4), sha256=sha(mp4), bytes=mp4.stat().st_size, expected_seconds=round(sum(d for _, d in items), 3), probe=pr, command=cmd)
rec = dict(at=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), rule=__doc__, ffmpeg=ff, scientific_verdict=None)
rec['judgment'] = enc(seq, 'B173_판단과정_v1')
r6 = sorted(R6.glob('frame_*.png'))
if len(r6) == 12:
    comb = [(str(r6[0]), 1.2)] + seq + [(str(p), 3.0 if i == len(r6)-2 else 1.2) for i, p in enumerate(r6[1:])]
    rec['combined'] = enc(comb, 'B173_판단학습과정_v1'); rec['combined']['r6_frames'] = [dict(png=str(p), sha256=sha(p)) for p in r6]
else: rec['combined'] = f'r6 frames not found ({len(r6)}); only the judgment video'
sd = OUT/'stills'; sd.mkdir(exist_ok=True); st = []
names = {'j1': '1_영상깊이유무', 'j2': '2_변화탐지', 'j3': '3_영상따름', 'j4': '4_영상점검', 'res': '5_판단결과'}
for s_, nm in names.items():
    last = [f for f in fr if f['stage'] == s_][-1]; dst = sd/f'B173_판단_{nm}.png'; shutil.copyfile(last['png'], dst); st.append(dict(png=str(dst), sha256=sha(dst), from_=last['png']))
rec['stills'] = st; (OUT/'video.json').write_text(json.dumps(rec, ensure_ascii=False, indent=2)+'\n'); (JD/'video.json').write_text(json.dumps(rec, ensure_ascii=False, indent=2)+'\n')
print(json.dumps({k: (v['probe'], v['expected_seconds']) if isinstance(v, dict) and 'probe' in v else '' for k, v in rec.items()}, ensure_ascii=False))
