"""Encode video v2 (jointbuildgs:geogs-da3-3d835ec-v1, imageio_ffmpeg 7.0.2). 12 fps: normal frame 3 copies (0.25 s),
hold frame 6 copies (0.5 s) then 23 rotation frames (1/12 s each). GIF 1280 without rotation (holds 1.5 s). Panel MP4s: E+F row, G section."""
import json, os, shutil, subprocess, hashlib
from pathlib import Path
from PIL import Image
O = Path('/tl'); V2 = O/'video_v2'; OUT = V2/'video'; FF = '/opt/conda/lib/python3.11/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2'; FPS = 12
CROPS = {'EF칸': (0, 326, 1920, 714), 'G칸': (0, 712, 880, 1032)}
def sha(p): h = hashlib.sha256(); h.update(Path(p).read_bytes()); return h.hexdigest()
def seq(items, folder, crop=None):
    if folder.exists(): shutil.rmtree(folder)
    folder.mkdir(parents=True); k = 0
    for it in items:
        im = Image.open(V2/it['file']).convert('RGB')
        if crop: im = im.crop(crop)
        p = folder/f'{k:05d}.png'; im.save(p); k += 1
        n = 6 if it['hold'] else (1 if it['kind'] == 'rotation' else 3)
        for _ in range(n-1): os.link(p, folder/f'{k:05d}.png'); k += 1
    return k
def mp4(folder, out):
    subprocess.run([FF, '-y', '-hide_banner', '-loglevel', 'error', '-framerate', str(FPS), '-i', str(folder/'%05d.png'), '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-r', str(FPS), str(out)], check=True)
def main():
    OUT.mkdir(exist_ok=True); items = json.loads((V2/'frames.json').read_text())['items']; rec = []
    for it in items: assert (V2/it['file']).exists(), it['file']
    tmp = O/'tmp/video_v2'; n = seq(items, tmp/'full'); out = OUT/'B173_학습과정_v2.mp4'; mp4(tmp/'full', out); rec.append(dict(file=out.name, frames=len(items), video_frames=n, seconds=n/FPS, sha256=sha(out)))
    for name, crop in CROPS.items():
        c = (crop[0], crop[1], crop[0]+((crop[2]-crop[0])//2)*2, crop[1]+((crop[3]-crop[1])//2)*2); n2 = seq(items, tmp/name, c); o2 = OUT/f'B173_학습과정_{name}_v2.mp4'; mp4(tmp/name, o2)
        rec.append(dict(file=o2.name, crop_px=c, video_frames=n2, sha256=sha(o2)))
    normal = [it for it in items if it['kind'] == 'normal']; ims = [Image.open(V2/it['file']).convert('RGB').resize((1280, 720), Image.LANCZOS) for it in normal]
    g = OUT/'B173_학습과정_v2.gif'; ims[0].save(g, save_all=True, append_images=ims[1:], duration=[1500 if it['hold'] else 250 for it in normal], loop=0); rec.append(dict(file=g.name, frames=len(ims), width=1280, sha256=sha(g)))
    (OUT/'video.json').write_text(json.dumps(dict(videos=rec, fps=FPS, timing='normal 0.25 s; hold 0.5 s still then 23 rotation frames at 1/12 s; GIF: no rotation, hold 1.5 s', interpolation=False,
        encoder='libx264 -preset veryfast yuv420p, imageio_ffmpeg 7.0.2', scientific_verdict=None), ensure_ascii=False, indent=1)); shutil.rmtree(tmp, ignore_errors=True); print('VIDEO_V2', rec, flush=True)
if __name__ == '__main__': main()
