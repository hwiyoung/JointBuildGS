"""Audit inherited exclusion-grid coverage without opening patch outcomes."""
import json
from pathlib import Path
import numpy as np
from tile_points import DT
from analysis_common import O,save_table
from preflight import PH
def main():
    source=PH/'main_design_realchange_survey_v1/PHD-MAIN-DESIGN-REALCHANGE-SURVEY-v1/derived.npz'
    with np.load(source) as z:ny,nx=z['uls'].shape
    parts=[]
    for tile in json.loads((O/'inputs/tiles.json').read_text()):
        p=O/'inputs/points'/tile['id']/'uls.bin';a=np.memmap(p,mode='r',dtype=DT)
        E=a['x']+690953.;N=a['y']+5336071.
        m=(E<690700.)|(E>=690700.+nx*.5)|(N<5335820.)|(N>=5335820.+ny*.5)
        if m.any():parts.append(np.column_stack([a[k][m] for k in ['x','y','z']]))
    unique=np.unique(np.concatenate(parts),axis=0) if parts else np.empty((0,3))
    save_table('참값_범위감사',[dict(exclusion_grid_source=str(source),shape=[ny,nx],
        bounds_epsg25832=[690700.,5335820.,690700.+nx*.5,5335820.+ny*.5],outside_grid_unique_points=len(unique),
        action='Excluded because inherited tree/transient classification is unavailable; never assume these points are clean GT.',
        manual_uls_used=False)],source='Raw nadir points and inherited exclusion-grid bounds only; no patch outcomes')
    print('GT exclusion-grid audit complete; outside source points',len(unique))
if __name__=='__main__':main()
