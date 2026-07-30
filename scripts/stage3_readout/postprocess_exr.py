"""Convert Blender smoketest EXRs into MatrixCity-compatible dataloader layout.

Blender compositor outputs:
  {prefix}_rgb_0000.png     (RGB uint8)
  {prefix}_depth_0000.exr   (channel 'V', float32)
  {prefix}_normal_0000.exr  (channels 'X','Y','Z', float32, world-frame raw [-1,1])
  {prefix}_sem_0000.exr     (channel 'V', float32 material pass_index)

dataloader (src/stage2/dataloader.py) expects:
  images/{stem}.png
  depth/{stem}.exr        4-channel BGRA, float32, sky sentinel >= 28000
  normal/{stem}.exr       4-channel BGRA, float32, world-frame (n+1)/2 half-range
  semantic/{stem}.png     uint8 single-channel, class 0..3

Writes OpenEXR files with R,G,B,A channel names (cv2 OpenEXR-compatible).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import OpenEXR
import Imath
from PIL import Image as PILImage


FLOAT = Imath.PixelType(Imath.PixelType.FLOAT)


def read_exr(path: Path) -> tuple[dict[str, np.ndarray], tuple[int, int]]:
    f = OpenEXR.InputFile(str(path))
    h = f.header()
    dw = h['dataWindow']
    W = dw.max.x - dw.min.x + 1
    H = dw.max.y - dw.min.y + 1
    out = {}
    for ch in h['channels']:
        raw = f.channel(ch, FLOAT)
        out[ch] = np.frombuffer(raw, dtype=np.float32).reshape(H, W)
    return out, (H, W)


def write_exr_rgba(path: Path, r: np.ndarray, g: np.ndarray,
                   b: np.ndarray, a: np.ndarray):
    """Write a 4-channel RGBA EXR that cv2.imread + IMREAD_UNCHANGED can load."""
    H, W = r.shape
    header = OpenEXR.Header(W, H)
    header['channels'] = {
        'R': Imath.Channel(FLOAT),
        'G': Imath.Channel(FLOAT),
        'B': Imath.Channel(FLOAT),
        'A': Imath.Channel(FLOAT),
    }
    out = OpenEXR.OutputFile(str(path), header)
    out.writePixels({
        'R': r.astype(np.float32).tobytes(),
        'G': g.astype(np.float32).tobytes(),
        'B': b.astype(np.float32).tobytes(),
        'A': a.astype(np.float32).tobytes(),
    })
    out.close()


def process_depth(src: Path, dst: Path):
    """V (float, meters) → RGBA (all channels identical). Sky sentinel preserved."""
    chans, _ = read_exr(src)
    v = chans['V']
    write_exr_rgba(dst, v, v, v, v)


def process_normal(src: Path, dst: Path, c2w: np.ndarray):
    """Blender-world normal XYZ → COLMAP-world normal → (n+1)/2 half-range RGBA.

    Blender OBJ importer default axis map (OBJ Y-up → Blender Z-up):
        OBJ (x, y, z)  →  Blender (x, -z, y)
    Equivalently for normals (same linear transform).

    For a ground face with OBJ normal (0,-1,0), this gives Blender (0, 0, -1).
    Cycles may flip normals to face camera (backface culling) for back-facing
    surfaces; with aerial cameras above the scene, ground/roof/wall faces
    render their outward normals without flip.

    Inverse (Blender-world → OBJ/COLMAP-world):
        nx_cv = nx_bl
        ny_cv = nz_bl
        nz_cv = -ny_bl

    dataloader path (src/stage2/dataloader.py line ~217):
        raw = cv2.imread(path, IMREAD_UNCHANGED)     # (H,W,4) BGRA
        n_enc_rgb = raw[..., :3][..., ::-1]          # BGR reversed → RGB
        n_world_colmap = n_enc_rgb * 2 - 1           # decode half-range
        mask = |n_world_colmap| > 0.5                # valid pixel mask
    So on-disk RGB channels = encoded COLMAP-world (x, y, z).
    For no-hit (sky) pixels, write (0.5, 0.5, 0.5) so decoded = (0,0,0), mag=0 → masked out.
    """
    chans, _ = read_exr(src)
    nx_bl, ny_bl, nz_bl = chans['X'], chans['Y'], chans['Z']
    # Blender-world → COLMAP-world (inverse of OBJ import axis map)
    nx = nx_bl
    ny = nz_bl
    nz = -ny_bl
    norm = np.sqrt(nx * nx + ny * ny + nz * nz)
    valid = norm > 0.5  # Blender no-hit pixels emit near-zero length normals
    nx = np.where(valid, nx / np.maximum(norm, 1e-6), 0.0)
    ny = np.where(valid, ny / np.maximum(norm, 1e-6), 0.0)
    nz = np.where(valid, nz / np.maximum(norm, 1e-6), 0.0)
    # Encode. Invalid → 0.5 so decoded = 0 (fails the mag>0.5 mask in dataloader).
    ex = np.where(valid, (nx + 1) * 0.5, 0.5)
    ey = np.where(valid, (ny + 1) * 0.5, 0.5)
    ez = np.where(valid, (nz + 1) * 0.5, 0.5)
    alpha = valid.astype(np.float32)
    write_exr_rgba(dst, ex, ey, ez, alpha)


def process_semantic(src: Path, dst: Path, color_dst: Path | None = None):
    """V (float pass_index) → PNG uint8 class id. BG=0, Roof=1, Wall=2, Terrain=3.

    Also writes a false-color visualization PNG to `color_dst` for human inspection
    (BG=black, Roof=red, Wall=blue, Terrain=green). Not consumed by dataloader.
    """
    chans, _ = read_exr(src)
    v = chans['V']
    cls = np.round(v).astype(np.uint8)
    cls[cls > 3] = 0
    PILImage.fromarray(cls, mode='L').save(dst)

    if color_dst is not None:
        palette = np.array([
            [0, 0, 0],       # 0 BG       black
            [220, 60, 60],   # 1 Roof     red
            [60, 90, 200],   # 2 Wall     blue
            [90, 160, 90],   # 3 Terrain  green
        ], dtype=np.uint8)
        color = palette[cls]
        PILImage.fromarray(color, mode='RGB').save(color_dst)


def process_view(raw_dir: Path, out_root: Path, name: str):
    rgb_src = raw_dir / f'{name}_rgb_0000.png'
    d_src = raw_dir / f'{name}_depth_0000.exr'
    n_src = raw_dir / f'{name}_normal_0000.exr'
    s_src = raw_dir / f'{name}_sem_0000.exr'
    cam_src = raw_dir / f'{name}_cam.json'
    for p in (rgb_src, d_src, n_src, s_src, cam_src):
        if not p.exists():
            raise FileNotFoundError(f'missing: {p}')
    PILImage.open(rgb_src).save(out_root / 'images' / f'{name}.png')
    c2w = np.array(json.loads(cam_src.read_text())['c2w'])
    process_depth(d_src, out_root / 'depth' / f'{name}.exr')
    process_normal(n_src, out_root / 'normal' / f'{name}.exr', c2w)
    process_semantic(
        s_src,
        out_root / 'semantic' / f'{name}.png',
        color_dst=out_root / 'semantic_color' / f'{name}.png',
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw-dir', default='results/phase2_synthesis/renders_raw',
                    help='Blender raw output directory (or smoke_test for single view)')
    ap.add_argument('--out-root', default='results/phase2_synthesis/dataset')
    ap.add_argument('--view-name', default=None,
                    help='Process only this view name (default: batch all views in --raw-dir)')
    args = ap.parse_args()

    raw_dir = Path(args.raw_dir)
    out_root = Path(args.out_root)

    for sub in ('images', 'depth', 'normal', 'semantic', 'semantic_color'):
        (out_root / sub).mkdir(parents=True, exist_ok=True)

    if args.view_name:
        names = [args.view_name]
    else:
        # Discover view names from *_cam.json files
        names = sorted(p.stem.rsplit('_cam', 1)[0]
                       for p in raw_dir.glob('*_cam.json'))
    print(f'[postprocess] {len(names)} views in {raw_dir}')
    for i, name in enumerate(names):
        process_view(raw_dir, out_root, name)
        if (i + 1) % 10 == 0 or i == 0 or i == len(names) - 1:
            print(f'  [{i+1:3d}/{len(names)}] {name}')
    print(f'[done] wrote to {out_root}/{{images,depth,normal,semantic,semantic_color}}')


if __name__ == '__main__':
    main()
