import argparse, numpy as np, torch
from pathlib import Path
def qn(q):
    q = q / np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-8)
    w,x,y,z = q[:,0],q[:,1],q[:,2],q[:,3]
    n = np.stack([2*(x*z+w*y), 2*(y*z-w*x), 1-2*(x*x+y*y)], axis=1)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-8)
    return n
def write_ply_float32(path, xyz, nxyz, rgb_u8):
    N = len(xyz)
    with open(path, 'wb') as f:
        f.write(b'ply\nformat binary_little_endian 1.0\n')
        f.write(f'element vertex {N}\n'.encode())
        f.write(b'property float x\nproperty float y\nproperty float z\n')
        f.write(b'property float nx\nproperty float ny\nproperty float nz\n')
        f.write(b'property uchar red\nproperty uchar green\nproperty uchar blue\n')
        f.write(b'end_header\n')
        data = np.empty(N, dtype=[('x','<f4'),('y','<f4'),('z','<f4'),('nx','<f4'),('ny','<f4'),('nz','<f4'),('r','u1'),('g','u1'),('b','u1')])
        data['x'],data['y'],data['z'] = xyz[:,0],xyz[:,1],xyz[:,2]
        data['nx'],data['ny'],data['nz'] = nxyz[:,0],nxyz[:,1],nxyz[:,2]
        data['r'],data['g'],data['b'] = rgb_u8[:,0],rgb_u8[:,1],rgb_u8[:,2]
        data.tofile(f)
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ckpt', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--subsample', type=int, default=500000)
    ap.add_argument('--seed', type=int, default=0)
    args = ap.parse_args()
    sd = torch.load(args.ckpt, map_location='cpu', weights_only=False)['state_dict']
    m = sd['means'].numpy().astype(np.float32)
    q = sd['quats'].numpy().astype(np.float32)
    n = qn(q).astype(np.float32)
    N = len(m)
    if args.subsample and args.subsample < N:
        rng = np.random.RandomState(args.seed)
        idx = rng.choice(N, args.subsample, replace=False)
        m = m[idx]; n = n[idx]
        print(f'  subsampled {N} -> {len(m)}')
    rgb = ((n + 1.0) * 0.5 * 255).clip(0, 255).astype(np.uint8)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    write_ply_float32(args.out, m, n, rgb)
    print(f'wrote {len(m):,} float32 prims -> {args.out}')
if __name__ == '__main__':
    main()
