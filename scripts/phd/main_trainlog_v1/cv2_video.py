"""Concept video v2 (first cut): MP4 and GIF from the 12 frames of cv2_frames.py (video image: imageio_ffmpeg's ffmpeg, Pillow). No new drawing.
  MP4  H.264 (libx264 -preset veryfast, yuv420p, crf 18, 25 fps constant), every frame 1.2 s, the last one 3.0 s (ffmpeg concat demuxer durations)
  GIF  1280 px wide (Lanczos), the same order and durations (Pillow per-frame durations 1200 ms / last 3000 ms, adaptive 256-colour palette per frame, loop)
r6 (CV2_VARIANT=r6, 2026-11-13): frames_r6 -> video_r6. Writes concept_v2/video/ (mp4, gif, video.json) and a copy of video.json in docs figures_concept_v2/ (the binaries stay in the payload, as the earlier videos). scientific_verdict: null"""
import os, subprocess, sys
from common import *
from PIL import Image
import imageio_ffmpeg
V2 = O/'concept_v2'; REV = os.environ.get('CV2_CASE_REV', 'v1') if TL_CASE else {'': 'r5', 'r6': 'r6'}[os.environ.get('CV2_VARIANT', '')]; BNAME = SITE.split('_')[0] if TL_CASE else 'B173'; FIGD0 = D if TL_CASE else D/'figures_concept_v2'; FR = V2/f'frames_{REV}'; OUTV = V2/f'video_{REV}'; FIGD = FIGD0; STEP, LAST = 1.2, 3.0   # r2 (2026-11-13): sections show results only; the first cut video/ is kept

def main():
    frames = sorted(FR.glob('frame_*.png')); assert len(frames) == 12, len(frames); OUTV.mkdir(parents=True, exist_ok=True); FIGD.mkdir(parents=True, exist_ok=True)
    lst = OUTV/'concat.txt'; lines = []
    for i, p in enumerate(frames): lines += [f"file '{p}'", f'duration {LAST if i == len(frames)-1 else STEP}']
    lines.append(f"file '{frames[-1]}'"); lst.write_text('\n'.join(lines)+'\n')
    mp4 = OUTV/f'{BNAME}_학습과정_개념동영상_v2_{REV}.mp4'; ff = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ff, '-y', '-hide_banner', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', str(lst), '-vf', 'fps=25,format=yuv420p', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18',
           '-movflags', '+faststart', str(mp4)]
    subprocess.run(cmd, check=True)
    probe = subprocess.run([ff, '-hide_banner', '-i', str(mp4)], capture_output=True, text=True).stderr
    ims = [Image.open(p).convert('RGB').resize((1280, 720), Image.LANCZOS) for p in frames]; pal = [im.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for im in ims]
    gif = OUTV/f'{BNAME}_학습과정_개념동영상_v2_{REV}.gif'
    pal[0].save(gif, save_all=True, append_images=pal[1:], duration=[int(STEP*1000)]*(len(pal)-1)+[int(LAST*1000)], loop=0, optimize=False, disposal=1)
    dur = [l for l in probe.splitlines() if 'Duration' in l or 'Video:' in l]
    rec = dict(at=now(), rule=__doc__, frames=[dict(png=str(p), sha256=sha(p)) for p in frames], mp4=dict(path=str(mp4), sha256=sha(mp4), bytes=mp4.stat().st_size, ffmpeg=ff, command=cmd, probe=dur),
               gif=dict(path=str(gif), sha256=sha(gif), bytes=gif.stat().st_size, width=1280), expected_seconds=STEP*(len(frames)-1)+LAST, scientific_verdict=None)
    dump(OUTV/'video.json', rec); dump(FIGD/f'video_{REV}.json', rec); print('VIDEO', rec['mp4']['bytes'], rec['gif']['bytes'], dur, flush=True)

if __name__ == '__main__': main()
