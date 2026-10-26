"""Prepare immutable CPU visibility caches while another authorized job uses GPUs."""
import time
from common import *
from cameras import Cameras,select_photos
from run_measure import selected_geometry
def main():
    assert load(O/'gates/pilot.json')['status']=='PASS';cam=Cameras()
    for sealed in [False,True]:
      base=paths(sealed);folder=base/'work/full_preselection';folder.mkdir(exist_ok=True)
      for t in load(W/'inputs/tiles.json'):
       for prior in ['LoD2','ALS']:
        name=f'{t["id"]}__{prior}';dest=folder/f'{name}_selection.npz'
        if dest.exists() or (base/'work/full'/f'{name}_selection.npz').exists():continue
        g,idx=selected_geometry('full',t['id'],prior,sealed)
        if not sealed:
            pilot=base/'work/pilot'/f'{name}.npz'
            if pilot.exists():
                old=npz(pilot);keep=~np.isin(idx,old['geometry_index'][old['kind']==1]);g={k:v[keep] for k,v in g.items()};idx=idx[keep]
        if not len(idx):continue
        start=time.monotonic();selection=select_photos(g,cam,t['id'],prior)
        temporary=dest.with_name('.'+dest.stem+'.pending.npz');np.savez_compressed(temporary,**selection)
        record=dict(points=len(idx),seconds=time.monotonic()-start,config_sha256=sha(C/'photocheck_v1.json'),geometry_sha256=sha(base/'geometry'/f'{name}.npz'),geometry_index_sha256=hashlib.sha256(idx.tobytes()).hexdigest(),environment=env())
        dump(dest.with_suffix('.json'),record);temporary.replace(dest)
        print('full photo selection ready',sealed,name,len(idx),round(record['seconds'],2),flush=True)
if __name__=='__main__':main()
