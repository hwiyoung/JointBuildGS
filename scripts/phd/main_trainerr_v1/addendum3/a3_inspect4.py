"""Input inspection 4 (read-only): which rows of the B173 ALS training initial cloud are image (SfM) points."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum3')
from a3_common import *
SC = Path('/s0/fork_inputs/s61/B173nb_b10')
pc = o3d.io.read_point_cloud(str(SC/'scene_ALS/sparse/0/points3D.ply')); P = np.asarray(pc.points); print('PLY', len(P))
for f in ['seat_ALS.npy', 'als_vertex_index_ALS.npy', 'prior_normal_ALS.npy']:
    a = np.load(SC/f); print(f, a.shape, a.dtype, a[:3], a[-3:], 'neg', int((a < 0).sum()) if a.ndim == 1 else int((~np.isfinite(a)).all(1).sum()))
o = np.load(SC/'scene_ALS/sparse/0/origin.npy'); print('origin', o.shape, o.dtype, np.unique(o, return_counts=True))
with open(SC/'scene_ALS/sparse/0/points3D.ply', 'rb') as f: print(f.read(400))
