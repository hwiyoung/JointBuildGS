"""Record ranges of the addendum-5 record runs (addendum5_b.json): voxelised union of boxes around the place points (TRAINERR region layout).
  build : addendum5/region/<stem>.json for B0_b10__LoD2 (south wall + long wall), R1rep_b10__LoD2 (lost cluster 1 + kept points within 30 m), B173nb_b10__ALS (edge floater + control)"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum5')
from a5_common import *
from scipy import ndimage

def boxes_of(P, margin, cell=1.):
    k = np.floor(P/cell).astype('i8'); lo = k.min(0); occ = np.zeros(tuple(k.max(0)-lo+1), bool); occ[tuple((k-lo).T)] = True
    lab, n = ndimage.label(ndimage.binary_dilation(occ, iterations=2)); out = []
    for s in ndimage.find_objects(lab):
        b0 = (np.array([s[0].start, s[1].start, s[2].start])+lo)*cell-margin; b1 = (np.array([s[0].stop, s[1].stop, s[2].stop])+lo)*cell+margin
        out.append([float(b0[0]), float(b1[0]), float(b0[1]), float(b1[1]), float(b0[2]), float(b1[2])])
    return out

def write(stem, P, margin, rule, voxel=.25):
    B = boxes_of(P, margin); lo = np.floor(np.min([[b[0], b[2], b[4]] for b in B], 0)); hi = np.ceil(np.max([[b[1], b[3], b[5]] for b in B], 0))
    shp = np.ceil((hi-lo)/voxel).astype(int); occ = np.zeros(tuple(shp), bool); rows = []
    for b in B:
        b = np.asarray(b); i0 = np.floor((b[[0, 2, 4]]-lo)/voxel+1e-9).astype(int); i1 = np.ceil((b[[1, 3, 5]]-lo)/voxel-1e-9).astype(int); occ[i0[0]:i1[0], i0[1]:i1[1], i0[2]:i1[2]] = True
        inb = np.all((P >= b[[0, 2, 4]]) & (P <= b[[1, 3, 5]]), 1); rows.append(list(map(float, b))+[int(inb.sum())])
    d = dict(stem=stem, box_columns=['xmin', 'xmax', 'ymin', 'ymax', 'zmin', 'zmax', 'points'], boxes=rows, voxel_m=voxel, grid_origin=lo.tolist(), grid_shape=shp.tolist(),
             occupied_voxels=int(occ.sum()), occupied_volume_m3=float(occ.sum()*voxel**3), rule=rule, scientific_verdict=None)
    (A5O/'region').mkdir(parents=True, exist_ok=True); dump(A5O/'region'/f'{stem}.json', d); print('REGION', stem, len(rows), d['occupied_volume_m3'], flush=True)

def build():
    c = json.loads((R/'configs/phd/main_trainerr_v1/addendum5_b.json').read_text())['region']
    P = np.concatenate([place_points5('south_wall')['xyz'], place_points5('long_wall')['xyz']]).astype('f8')
    write('B0_b10__LoD2', P, c['margin_m'], 'addendum5_b.json region: south_wall + long_wall GT points, 1 m cells dilated 2, boxes + margin')
    z = loadz(A4O/'ma/R1rep_b10__LoD2.npz'); X1 = z['xyz'][z['cluster_rank'] == 1].astype('f8'); kc = z['kept_xyz'].astype('f8'); ce = X1.mean(0)
    K = kc[np.linalg.norm(kc-ce, axis=1) <= c['r1_lod2_control_radius_m']]
    write('R1rep_b10__LoD2', np.concatenate([X1, K]), c['margin_m'], 'addendum5_b.json region: addendum4 ma cluster 1 lost points + kept points within 30 m of its centre')
    F = np.concatenate([floater_centres('floater'), floater_centres('floater_control')])
    write('B173nb_b10__ALS', F, c['floater_margin_m'], 'addendum5_b.json region: addendum3 ma edge floater face centres + control vertices (20,000 sampled)')

if __name__ == '__main__': build()
