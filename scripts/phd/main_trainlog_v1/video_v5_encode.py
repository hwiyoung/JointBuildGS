"""Encode video v5 (same timing as v4): 4 fps, 0.25 s per saved state, 1.5 s hold at 0, 3,000 (just before reset), 7,000, 15,000, 30,000; no rotation, no interpolation."""
import json, os, shutil, subprocess, hashlib
from pathlib import Path
from PIL import Image
O = Path('/tl'); V3 = O/'video_v5'; OUT = V3/'video'; FF = '/opt/conda/lib/python3.11/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2'
CROPS = {'입력가우시안메시칸': (0, 326, 1920, 714), '단면칸': (0, 712, 1080, 1032), '감독렌더칸': (0, 56, 1920, 334)}
def sha(p): h = hashlib.sha256(); h.update(Path(p).read_bytes()); return h.hexdigest()
def seq(items, folder, crop=None):
    if folder.exists(): shutil.rmtree(folder)
    folder.mkdir(parents=True); k = 0
    for it in items:
        im = Image.open(V3/it['file']).convert('RGB')
        if crop: im = im.crop((crop[0], crop[1], crop[0]+((crop[2]-crop[0])//2)*2, crop[1]+((crop[3]-crop[1])//2)*2))
        p = folder/f'{k:05d}.png'; im.save(p); k += 1
        for _ in range(5 if it['hold'] else 0): os.link(p, folder/f'{k:05d}.png'); k += 1
    return k
def mp4(folder, out): subprocess.run([FF, '-y', '-hide_banner', '-loglevel', 'error', '-framerate', '4', '-i', str(folder/'%05d.png'), '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-r', '4', str(out)], check=True)
def main():
    OUT.mkdir(exist_ok=True); items = json.loads((V3/'frames.json').read_text())['items']; rec = []; tmp = O/'tmp/video_v5'
    n = seq(items, tmp/'full'); o = OUT/'B173_학습과정_v5.mp4'; mp4(tmp/'full', o); rec.append(dict(file=o.name, frames=len(items), video_frames=n, seconds=n/4, sha256=sha(o)))
    for name, crop in CROPS.items(): n2 = seq(items, tmp/name, crop); o2 = OUT/f'B173_학습과정_{name}_v5.mp4'; mp4(tmp/name, o2); rec.append(dict(file=o2.name, crop_px=crop, video_frames=n2, sha256=sha(o2)))
    ims = [Image.open(V3/it['file']).convert('RGB').resize((1280, 720), Image.LANCZOS) for it in items]; g = OUT/'B173_학습과정_v5.gif'
    ims[0].save(g, save_all=True, append_images=ims[1:], duration=[1500 if it['hold'] else 250 for it in items], loop=0); rec.append(dict(file=g.name, frames=len(ims), width=1280, sha256=sha(g)))
    (OUT/'video.json').write_text(json.dumps(dict(videos=rec, fps=4, hold_s=1.5, interpolation=False, encoder='libx264 -preset veryfast yuv420p, imageio_ffmpeg 7.0.2', scientific_verdict=None), ensure_ascii=False, indent=1))
    shutil.rmtree(tmp, ignore_errors=True); print('VIDEO_V4', rec, flush=True)
if __name__ == '__main__': main()
