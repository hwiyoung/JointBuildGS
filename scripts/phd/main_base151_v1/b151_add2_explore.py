"""addendum 2 1-1 exploration: per campus image height above the GT of its cell (add1 definition) and tilt; prints histograms. scientific_verdict: null"""
import json, sys
import numpy as np
sys.path.insert(0, '/b151s')
from b151_add1 import colmap_images, TU1, O, in_cell
g = np.load(O / 'gt151_ALS.npz')
camp = colmap_images(TU1 / 'scenes/campus/scene_ALS/sparse/0/images.bin')
sp = json.loads((TU1 / 'scenes/campus/split.json').read_text())
gz = [float(np.median(g['xyz'][in_cell(g['xyz'][:, :2], k), 2])) for k in range(4)]
print('gt z median per cell', gz, 'campus', float(np.median(g['xyz'][:, 2])))
for part in ['train', 'test']:
    H, T = [], []
    for nm in sp[part]:
        R, C = camp[nm]
        k = [k for k in range(4) if in_cell(C[None, :2], k)[0]][0]
        H.append(C[2] - gz[k]); T.append(np.degrees(np.arccos(np.clip(-R[2][2], -1, 1))))
    H, T = np.array(H), np.array(T)
    print(part, len(H))
    print(' height hist 5 m', np.histogram(H, bins=np.arange(0, 90, 5)))
    print(' tilt hist 5 deg', np.histogram(T, bins=np.arange(0, 95, 5)))
    hb, tb = np.arange(0, 90, 10), np.arange(0, 95, 10)
    h2, _, _ = np.histogram2d(H, T, bins=[hb, tb]); print(' 2d (rows height 0..80 by 10, cols tilt 0..90 by 10)\n', h2.astype(int))
