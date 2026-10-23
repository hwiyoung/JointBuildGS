"""Compare raw source patch grids before any GT/MVS patch outcome is read."""
import json
import numpy as np
from scipy.spatial import cKDTree
from analysis_common import O,save_table,quantiles
from preflight import PH
from distributions import site_masks
S0=PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1'
def main():
    tiles=json.loads((O/'inputs/tiles.json').read_text());rows=[]
    for prior,key in [('LoD2','lod2'),('ALS','als')]:
        parts=[]
        for tile in tiles:
            with np.load(O/'holdout/internal/prior_tiles'/tile['id']/f'{key}_store.npz') as z:c=z['loc_center']
            x0,y0,x1,y1=np.array(tile['core_global'])-[690953.,5336071.,690953.,5336071.]
            m=(c[:,0]>=x0)&(c[:,0]<x1)&(c[:,1]>=y0)&(c[:,1]<y1);parts.append(c[m])
        xyz=np.concatenate(parts);tree=cKDTree(xyz)
        for site in ['B0_b10','B173nb_b10','R1rep_b10']:
            with np.load(S0/'s61/box'/site/prior/'units.npz') as z:c=z['loc_center']
            shift=np.array(json.loads((S0/'s61/box'/site/prior/'summary.json').read_text())['store_frame_shift']);raw=c-shift
            ev=site_masks(c)[site];dist,idx=tree.query(raw[ev],workers=8)
            rows.append(dict(prior=prior,site=site,old_eval_patches=int(ev.sum()),current_core_source_patches=len(xyz),
                exact_raw_centres_1e_5m=int((dist<=1e-5).sum()),near_raw_centres_0_18m=int((dist<=.18).sum()),nearest_raw_distance_m=quantiles(dist),
                old_shift_removed_m=shift.tolist(),scope='Input geometry comparison before building attachment and common-mask export; no patch outcome read'))
        del tree,xyz,parts
    save_table('맞춰보기_원본패치격자',rows,source='S0/s61/box/*/*/units.npz and this task holdout/internal/prior_tiles/*/*_store.npz; input geometry only, no patch outcomes')
    print('raw source patch grid check complete')
if __name__=='__main__':main()
