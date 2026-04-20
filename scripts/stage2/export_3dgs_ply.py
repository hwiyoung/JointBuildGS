"""2DGS ckpt → 3DGS-format PLY for SuperSplat / gsplat.js / mkkellogg viewer.

2DGS primitives are planar disks (2 scales). We emulate as 3DGS ellipsoids
with a very small third scale (near-zero thickness), producing flat ellipsoids
that render as disks in 3DGS viewers.

Output: standard 3DGS PLY with properties:
  x,y,z + nx,ny,nz + f_dc_0..2 (SH DC) + f_rest_0..44 (SH higher) + opacity
  + scale_0..2 + rot_0..3
"""
import argparse, numpy as np, torch
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ckpt', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--subsample', type=int, default=0)
    ap.add_argument('--third-log-scale', type=float, default=-7.0, help='log scale for flat 3rd axis, e^-7≈0.001m')
    args = ap.parse_args()

    sd = torch.load(args.ckpt, map_location='cpu', weights_only=False)['state_dict']
    means = sd['means'].numpy().astype(np.float32)
    quats = sd['quats'].numpy().astype(np.float32)       # (N,4) w,x,y,z
    log_scales = sd['log_scales'].numpy().astype(np.float32)  # (N,2)
    opacities_raw = sd['opacities_raw'].numpy().astype(np.float32)  # (N,1) or (N,)
    sh0 = sd['sh0'].numpy().astype(np.float32)           # (N,1,3) or (N,3)
    shN = sd['shN'].numpy().astype(np.float32)           # (N,K,3)

    if opacities_raw.ndim == 2: opacities_raw = opacities_raw.squeeze(-1)
    if sh0.ndim == 3 and sh0.shape[1] == 1: sh0 = sh0.squeeze(1)  # (N,3)

    N = len(means)
    if args.subsample and args.subsample < N:
        rng = np.random.RandomState(0)
        idx = rng.choice(N, args.subsample, replace=False)
        means = means[idx]; quats = quats[idx]; log_scales = log_scales[idx]
        opacities_raw = opacities_raw[idx]; sh0 = sh0[idx]; shN = shN[idx]
        print(f'  subsampled {N} -> {len(means)}')
        N = len(means)

    # Normalize quaternions
    quats = quats / np.maximum(np.linalg.norm(quats, axis=1, keepdims=True), 1e-8)

    # Build flat 3rd scale
    scale_0 = log_scales[:, 0]
    scale_1 = log_scales[:, 1]
    scale_2 = np.full(N, args.third_log_scale, dtype=np.float32)

    # Normals from quats (third axis)
    w, x, y, z = quats[:,0], quats[:,1], quats[:,2], quats[:,3]
    nx = 2*(x*z + w*y)
    ny = 2*(y*z - w*x)
    nz = 1 - 2*(x*x + y*y)
    # Normalize
    nn = np.sqrt(nx*nx + ny*ny + nz*nz); nn = np.maximum(nn, 1e-8)
    nx, ny, nz = nx/nn, ny/nn, nz/nn

    # shN layout: INRIA 3DGS uses row-major flattened, (N, K*3) with K = (sh_deg+1)^2 - 1
    # For sh_deg=3: K=15, total f_rest = 45
    # Our shN: (N, K, 3). Need to transpose to (N, 3, K) then flatten? Let's check convention.
    # INRIA format: f_rest stored as K groups of 3 channels, row-major.
    # Standard: [sh_1_r, sh_1_g, sh_1_b, sh_2_r, ...] — which is (N, K, 3) flattened as (N, K*3)
    K = shN.shape[1]
    f_rest = shN.reshape(N, K * 3)  # (N, 45) for sh_deg=3

    # f_dc: just sh0 (first SH coefficient)
    f_dc = sh0  # (N, 3)

    # Build PLY
    dtype_list = [
        ('x', '<f4'), ('y', '<f4'), ('z', '<f4'),
        ('nx', '<f4'), ('ny', '<f4'), ('nz', '<f4'),
        ('f_dc_0', '<f4'), ('f_dc_1', '<f4'), ('f_dc_2', '<f4'),
    ]
    for i in range(K * 3):
        dtype_list.append((f'f_rest_{i}', '<f4'))
    dtype_list += [
        ('opacity', '<f4'),
        ('scale_0', '<f4'), ('scale_1', '<f4'), ('scale_2', '<f4'),
        ('rot_0', '<f4'), ('rot_1', '<f4'), ('rot_2', '<f4'), ('rot_3', '<f4'),
    ]
    data = np.empty(N, dtype=dtype_list)
    data['x'], data['y'], data['z'] = means[:,0], means[:,1], means[:,2]
    data['nx'], data['ny'], data['nz'] = nx, ny, nz
    data['f_dc_0'], data['f_dc_1'], data['f_dc_2'] = f_dc[:,0], f_dc[:,1], f_dc[:,2]
    for i in range(K * 3):
        data[f'f_rest_{i}'] = f_rest[:, i]
    data['opacity'] = opacities_raw
    data['scale_0'], data['scale_1'], data['scale_2'] = scale_0, scale_1, scale_2
    data['rot_0'], data['rot_1'], data['rot_2'], data['rot_3'] = quats[:,0], quats[:,1], quats[:,2], quats[:,3]

    out_path = Path(args.out); out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'wb') as f:
        f.write(b'ply\n')
        f.write(b'format binary_little_endian 1.0\n')
        f.write(f'element vertex {N}\n'.encode())
        for name, _ in dtype_list:
            f.write(f'property float {name}\n'.encode())
        f.write(b'end_header\n')
        data.tofile(f)
    print(f'wrote 3DGS-format PLY: {out_path}  ({N:,} prims, {len(dtype_list)} properties)')

if __name__ == '__main__':
    main()
