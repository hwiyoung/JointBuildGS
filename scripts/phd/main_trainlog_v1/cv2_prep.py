"""Concept video v2 (first cut, 2026-11-12): the discs (Gaussians) of every frame, building scope only. CPU torch (GPU image without a GPU), no training, no rendering.
  ours  = this run's saved states (RUNM/trainlog/scene/<n>.pt, its own 'inside' = building scope), n in STATES
  comparison runs at their saved iterations (binary PLY read with numpy; building scope = derive_states.scope_mask on the centre):
    nojudge_15000, nojudge_30000 = main_stage3_v1 nojudge_ALS_s0 point_cloud/iteration_<n> (same code, judgment off; RESCORE baseline_30000's run)
    2dgs_7000, 2dgs_30000         = main_baselines_v1 imgonly_2dgs_s0 point_cloud/iteration_<n> (image-only 2DGS)
Saved per disc: centre, activated scale (exp, 2 axes), unit quaternion (w, x, y, z), opacity (sigmoid), colour = SH degree-0 term (0.5 + C0 * f_dc, clipped).
Writes concept_v2/discs/<key>.npz and concept_v2/discs.json only.
scientific_verdict: null"""
import sys, time
from common import *
from derive_states import scope_mask
import torch
STATES = ['0', '100', '300', '1000', '2000', '3000', '5000', '7000', '10000', '15000', '30000']; C0 = 0.28209479177387814
V2 = O/'concept_v2'; OUTD = V2/'discs'
COMP = {'nojudge_15000': PH/f'main_stage3_v1/PHD-MAIN-STAGE3-v1/runs/{SITE}/nojudge_ALS_s0/model/point_cloud/iteration_15000/point_cloud.ply',
        'nojudge_30000': PH/f'main_stage3_v1/PHD-MAIN-STAGE3-v1/runs/{SITE}/nojudge_ALS_s0/model/point_cloud/iteration_30000/point_cloud.ply',
        '2dgs_7000': PH/f'main_baselines_v1/PHD-MAIN-BASELINES-v1/runs/{SITE}/imgonly_2dgs_s0/model/point_cloud/iteration_7000/point_cloud.ply',
        '2dgs_30000': PH/f'main_baselines_v1/PHD-MAIN-BASELINES-v1/runs/{SITE}/imgonly_2dgs_s0/model/point_cloud/iteration_30000/point_cloud.ply'}
if TL_CASE: COMP = {k: v for k, v in COMP.items() if k.startswith('2dgs_')}   # another case (launch.py TL_CASE): image-only 2DGS only
TYPES = {'float': 'f4', 'float32': 'f4', 'double': 'f8', 'uchar': 'u1', 'uint8': 'u1', 'int': 'i4', 'int32': 'i4', 'uint': 'u4', 'short': 'i2', 'ushort': 'u2'}

def read_ply(p):
    with open(p, 'rb') as f:
        props, n = [], None
        while True:
            line = f.readline().decode('ascii').strip()
            if line.startswith('format'): assert 'binary_little_endian' in line, line
            if line.startswith('element vertex'): n = int(line.split()[-1])
            elif line.startswith('element') and n is not None and not props: raise ValueError('vertex element must come first')
            if line.startswith('property') and 'list' not in line: props.append((line.split()[2], '<'+TYPES[line.split()[1]]))
            if line == 'end_header': break
        return np.fromfile(f, dtype=np.dtype(props), count=n)

def save(key, xyz, scale, quat, opacity, rgb, n_all, src):
    q = quat.astype(float); q /= np.linalg.norm(q, axis=1, keepdims=True)
    savez(OUTD/f'{key}.npz', xyz=xyz.astype('f4'), scale=scale.astype('f4'), quat=q.astype('f4'), opacity=opacity.astype('f4'), rgb=np.clip(rgb, 0, 1).astype('f4'))
    return dict(source=str(src), source_sha256=sha(src), n_all=int(n_all), n_scope=int(len(xyz)), opacity_ge_0p5=int((opacity >= .5).sum()))

def main():
    c = cfg(); OUTD.mkdir(parents=True, exist_ok=True); rec = dict(at=now(), rule=__doc__, discs={}, scientific_verdict=None)
    for n in STATES:
        t0 = time.monotonic(); p = RUNM/'trainlog/scene'/f'{n}.pt'; d = torch.load(p, map_location='cpu', weights_only=False); m = d['inside'].numpy()
        r = save(f'ours_{n}', d['xyz'][m].numpy(), np.exp(d['scaling'][m].numpy()), d['rotation'][m].numpy(), 1/(1+np.exp(-d['opacity'][m].numpy().reshape(-1))),
                 .5+C0*d['f_dc'][m].numpy().reshape(int(m.sum()), -1)[:, :3], len(m), p)
        r['seconds'] = round(time.monotonic()-t0, 1); rec['discs'][f'ours_{n}'] = r; print('DISCS', n, r, flush=True); del d
    for key, p in COMP.items():
        t0 = time.monotonic(); v = read_ply(p); xyz = np.c_[v['x'], v['y'], v['z']].astype(float); m = scope_mask(xyz, c)
        sc = np.stack([v[k] for k in v.dtype.names if k.startswith('scale_')], 1); assert sc.shape[1] == 2, sc.shape
        r = save(key, xyz[m], np.exp(sc[m]), np.c_[v['rot_0'], v['rot_1'], v['rot_2'], v['rot_3']][m], 1/(1+np.exp(-v['opacity'][m].astype(float))),
                 .5+C0*np.c_[v['f_dc_0'], v['f_dc_1'], v['f_dc_2']][m], len(v), p)
        r['seconds'] = round(time.monotonic()-t0, 1); rec['discs'][key] = r; print('DISCS', key, r, flush=True); del v
    dump(V2/'discs.json', rec); print('DONE', flush=True)

if __name__ == '__main__': main()
