"""Order 5.2 videos: MP4 (H.264, -preset veryfast, 1920x1080, 0.25 s/frame, 1.5 s holds), GIF 1280, panel MP4s.
Runs in jointbuildgs:geogs-da3-3d835ec-v1 (imageio_ffmpeg static ffmpeg 7.0.2); no interpolation."""
import json, os, shutil, subprocess, sys, hashlib
from pathlib import Path
from PIL import Image
O = Path('/tl'); FR = O/'frames'; V = O/'video'; FF = '/opt/conda/lib/python3.11/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2'
FPS = 4; HOLD = 6
def sha(p):
    h = hashlib.sha256(); h.update(Path(p).read_bytes()); return h.hexdigest()
def seq(files, holds, folder, crop=None):
    if folder.exists(): shutil.rmtree(folder)
    folder.mkdir(parents=True); k = 0
    for f, h in zip(files, holds):
        im = Image.open(O/f).convert('RGB')
        if crop: x0, y0, x1, y1 = crop; im = im.crop((x0, y0, x0+((x1-x0)//2)*2, y0+((y1-y0)//2)*2))
        p = folder/f'{k:05d}.png'; im.save(p); k += 1
        for _ in range(HOLD-1 if h else 0): os.link(p, folder/f'{k:05d}.png'); k += 1
    return k
def mp4(folder, out, n):
    subprocess.run([FF, '-y', '-hide_banner', '-loglevel', 'error', '-framerate', str(FPS), '-i', str(folder/'%05d.png'), '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-r', str(FPS), str(out)], check=True)
def main():
    V.mkdir(exist_ok=True); rec = []
    for mode, tag in [('result', '결과판'), ('all', '모든가우시안판')]:
        meta = json.loads((FR/'frames_frames.json').read_text())['frames']; fr = sorted([m for m in meta if m['mode'] == mode], key=lambda m: m['order'])
        files = [m['file'] for m in fr]; holds = [m['hold'] for m in fr]; tmp = O/'tmp/video'/mode; n = seq(files, holds, tmp)
        out = V/f'B173_학습과정_{tag}_v1.mp4'; mp4(tmp, out, n); rec.append(dict(file=out.name, frames=len(files), video_frames=n, seconds=n/FPS, sha256=sha(out)))
        if mode == 'result':
            ims = [Image.open(O/f).convert('RGB') for f in files]; ims = [im.resize((1280, 720), Image.LANCZOS) for im in ims]
            dur = [1500 if h else 250 for h in holds]; g = V/f'B173_학습과정_{tag}_v1.gif'; ims[0].save(g, save_all=True, append_images=ims[1:], duration=dur, loop=0, optimize=False)
            rec.append(dict(file=g.name, frames=len(ims), width=1280, durations_ms='250, hold 1500', sha256=sha(g)))
            for panel in ['surface', 'section']:
                crop = fr[0]['crop'][panel]; tmp2 = O/'tmp/video'/panel; n2 = seq(files, holds, tmp2, crop); out2 = V/f'B173_학습과정_{panel}칸_v1.mp4'; mp4(tmp2, out2, n2)
                rec.append(dict(file=out2.name, crop_px=crop, frames=len(files), video_frames=n2, sha256=sha(out2)))
        print('VIDEO', mode, n, flush=True)
    (V/'video.json').write_text(json.dumps(dict(videos=rec, fps=FPS, hold_frames=HOLD, hold_iterations=[0, 3000, 7000, 15000, 30000], encoder='libx264 -preset veryfast yuv420p (imageio_ffmpeg 7.0.2 static)',
                                                 interpolation=False, scientific_verdict=None), ensure_ascii=False, indent=1))
    shutil.rmtree(O/'tmp/video', ignore_errors=True)
if __name__ == '__main__': main()
