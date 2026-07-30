"""Write COLMAP sparse/0/ binary files from per-view camera JSONs + scene OBJ.

Output:
  {dataset}/sparse/0/cameras.bin   (PINHOLE model, one per view)
  {dataset}/sparse/0/images.bin    (qvec, tvec, camera_id, name, [] for points2d)
  {dataset}/sparse/0/points3D.bin  (surface-sampled init points + per-face color)
"""
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

import numpy as np
import trimesh


PINHOLE_MODEL_ID = 1          # PINHOLE in COLMAP
INIT_POINTS = 100_000


def rotmat_to_qvec(R: np.ndarray) -> np.ndarray:
    """COLMAP quaternion ordering (w, x, y, z) from a rotation matrix."""
    Kmat = np.array([
        [R[0, 0] - R[1, 1] - R[2, 2], 0, 0, 0],
        [R[0, 1] + R[1, 0], R[1, 1] - R[0, 0] - R[2, 2], 0, 0],
        [R[0, 2] + R[2, 0], R[1, 2] + R[2, 1], R[2, 2] - R[0, 0] - R[1, 1], 0],
        [R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1], R[0, 0] + R[1, 1] + R[2, 2]],
    ]) / 3.0
    eigvals, eigvecs = np.linalg.eigh(Kmat)
    q = eigvecs[[3, 0, 1, 2], np.argmax(eigvals)]
    if q[0] < 0:
        q = -q
    return q


def write_cameras_bin(path: Path, cams: list[dict]):
    with open(path, 'wb') as f:
        f.write(struct.pack('<Q', len(cams)))
        for c in cams:
            # int cam_id, int model_id, uint64 W, uint64 H, 4 params (fx, fy, cx, cy)
            f.write(struct.pack('<iiQQ', c['id'], PINHOLE_MODEL_ID, c['W'], c['H']))
            f.write(struct.pack('<dddd', c['fx'], c['fy'], c['cx'], c['cy']))


def write_images_bin(path: Path, imgs: list[dict]):
    with open(path, 'wb') as f:
        f.write(struct.pack('<Q', len(imgs)))
        for im in imgs:
            f.write(struct.pack('<I', im['id']))
            f.write(struct.pack('<dddd', *im['qvec']))
            f.write(struct.pack('<ddd', *im['tvec']))
            f.write(struct.pack('<I', im['camera_id']))
            f.write(im['name'].encode() + b'\x00')
            f.write(struct.pack('<Q', 0))  # num_points2D = 0


def write_points3d_bin(path: Path, xyz: np.ndarray, rgb: np.ndarray):
    n = len(xyz)
    with open(path, 'wb') as f:
        f.write(struct.pack('<Q', n))
        for i in range(n):
            f.write(struct.pack('<Q', i + 1))                 # point3D_id
            f.write(struct.pack('<ddd', *xyz[i]))
            r, g, b = (int(v) for v in np.clip(rgb[i], 0, 255))
            f.write(struct.pack('<BBB', r, g, b))
            f.write(struct.pack('<d', 0.0))                   # error
            f.write(struct.pack('<Q', 0))                     # track_length = 0


def sample_init_points(obj_path: Path, n_points: int):
    """Sample n_points from the OBJ scene surface with per-face material colors.

    OBJ coords are already COLMAP-frame (-Y up), which matches dataloader convention.
    """
    scene = trimesh.load(obj_path, force='scene', process=False)
    # Material color mapping (matches compose_scene.py)
    material_rgb = {
        'Roof':    np.array([220, 60, 60]),
        'Wall':    np.array([60, 80, 200]),
        'Ground':  np.array([90, 160, 90]),
        'Terrain': np.array([130, 140, 120]),
    }
    all_xyz = []
    all_rgb = []
    # Distribute point budget across geometries by surface area
    geoms = list(scene.geometry.items())
    areas = np.array([g.area for _, g in geoms])
    weights = areas / areas.sum()
    counts = np.maximum((weights * n_points).astype(int), 1)
    for (name, geom), cnt in zip(geoms, counts):
        pts, _face_idx = trimesh.sample.sample_surface(geom, cnt)
        mat_name = 'Terrain'
        for key in material_rgb:
            if key.lower() in name.lower():
                mat_name = key
                break
        all_xyz.append(pts)
        all_rgb.append(np.tile(material_rgb[mat_name], (cnt, 1)))
    xyz = np.concatenate(all_xyz, axis=0)
    rgb = np.concatenate(all_rgb, axis=0)
    return xyz.astype(np.float64), rgb.astype(np.float64)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw-dir', default='results/phase2_synthesis/renders_raw')
    ap.add_argument('--dataset', default='results/phase2_synthesis/dataset')
    ap.add_argument('--obj', default='results/phase2_synthesis/scene.obj')
    ap.add_argument('--n-points', type=int, default=INIT_POINTS)
    args = ap.parse_args()

    raw_dir = Path(args.raw_dir)
    dataset = Path(args.dataset)
    sparse_dir = dataset / 'sparse' / '0'
    sparse_dir.mkdir(parents=True, exist_ok=True)

    view_names = sorted(p.stem.rsplit('_cam', 1)[0] for p in raw_dir.glob('*_cam.json'))
    print(f'[export-colmap] {len(view_names)} views')

    cameras = []
    images = []
    for i, name in enumerate(view_names, start=1):
        pose = json.loads((raw_dir / f'{name}_cam.json').read_text())
        w2c = np.array(pose['w2c'])
        R = w2c[:3, :3]
        t = w2c[:3, 3]
        qvec = rotmat_to_qvec(R)
        cameras.append({
            'id': i, 'W': int(pose['W']), 'H': int(pose['H']),
            'fx': float(pose['fx']), 'fy': float(pose['fy']),
            'cx': float(pose['cx']), 'cy': float(pose['cy']),
        })
        images.append({
            'id': i, 'camera_id': i,
            'qvec': qvec.tolist(),
            'tvec': t.tolist(),
            'name': f'{name}.png',
        })

    write_cameras_bin(sparse_dir / 'cameras.bin', cameras)
    write_images_bin(sparse_dir / 'images.bin', images)
    print(f'  cameras.bin  ({len(cameras)} cams)')
    print(f'  images.bin   ({len(images)} imgs)')

    xyz, rgb = sample_init_points(Path(args.obj), args.n_points)
    write_points3d_bin(sparse_dir / 'points3D.bin', xyz, rgb)
    print(f'  points3D.bin ({len(xyz)} pts)')

    print(f'[done] wrote {sparse_dir}/')


if __name__ == '__main__':
    main()
