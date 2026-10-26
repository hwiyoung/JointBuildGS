"""Pilot/full driver, resumable per tile. Holdout never enters public point stores."""
import argparse,time
from common import *
from cameras import Cameras,select_photos
from curves import compute
from features import derive

def selected_geometry(stage,tile,prior,sealed=False):
    base=paths(sealed);g=npz(base/'geometry'/f'{tile}__{prior}.npz')
    if stage=='pilot':m=np.array([any(b in EXAMPLES for b in str(v).split(';')) for v in g.get('building_ids',g['building'])],dtype=bool)
    else:m=g['kind']==1
    idx=np.flatnonzero(m);return {k:v[idx] for k,v in g.items()},idx

def main():
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['pilot','full','benchmark']);ap.add_argument('--device',default='cpu',choices=['cpu','cuda']);ap.add_argument('--tile');ap.add_argument('--prior');ap.add_argument('--limit',type=int,default=128);a=ap.parse_args()
    assert sha(C/'photocheck_v1.json')==load(C/'photocheck_v1.lock.json')['sha256']
    if a.stage!='benchmark':assert load(O/'gates/benchmark.json')['status']=='PASS'
    if a.stage=='full':
        gate=load(O/'gates/pilot.json');assert gate['status']=='PASS','full stage requires all passed gates'
    cam=Cameras();tiles=load(W/'inputs/tiles.json')
    for sealed in ([False,True] if a.stage=='full' else [False]):
      base=paths(sealed)
      for tile in [t['id'] for t in tiles if not a.tile or t['id']==a.tile]:
       for prior in ['LoD2','ALS']:
        if a.prior and prior!=a.prior:continue
        stage='pilot' if a.stage=='benchmark' else a.stage;g,idx=selected_geometry(stage,tile,prior,sealed)
        if not len(idx):continue
        name=f'{tile}__{prior}';folder=base/'work'/stage;folder.mkdir(exist_ok=True)
        dest=folder/f'{name}.npz';receipt=folder/f'{name}.json'
        if dest.exists() and receipt.exists() and a.stage!='benchmark':continue
        reused=None
        if a.stage=='full' and not sealed:
            pilot=base/'work/pilot'/f'{name}.npz'
            if pilot.exists():
                oldrec=load(pilot.with_suffix('.json'));assert oldrec['config_sha256']==sha(C/'photocheck_v1.json') or sha(C/'photocheck_v1.json') in oldrec.get('compatible_configuration_sha256',[])
                old=npz(pilot);keep=old['kind']==1;reused={k:v[keep] for k,v in old.items()}
                remaining=~np.isin(idx,reused['geometry_index']);g={k:v[remaining] for k,v in g.items()};idx=idx[remaining]
        selectionfile=folder/f'{name}_selection.npz';st=time.monotonic()
        if selectionfile.exists():selection=npz(selectionfile)
        else:
            selection=select_photos(g,cam,tile,prior) if len(idx) else dict(selected_images=np.empty((0,10),np.int32),eligible_images=np.empty(0,np.int32),selected_count=np.empty(0,np.int8),max_direction_angle_deg=np.empty(0,np.float32),parallax=np.empty(0,np.float32))
            np.savez_compressed(selectionfile,**selection)
            dump(selectionfile.with_suffix('.json'),dict(points=len(idx),seconds=time.monotonic()-st,environment=env(),config_sha256=sha(C/'photocheck_v1.json')))
        if a.stage=='benchmark':
            # Deterministic evenly spread pilot points with >=3 views, no truth filters.
            candidates=np.flatnonzero(selection['selected_count']>=3);ids=candidates[np.linspace(0,len(candidates)-1,min(a.limit,len(candidates)),dtype=int)]
            g={k:v[ids] for k,v in g.items()};selection={k:v[ids] for k,v in selection.items()};idx=idx[ids]
        values,timing=compute(g,selection,a.device,progress=folder/f'{name}_{a.device}_progress.json')
        feat=derive(values['heights'],values['curve'],g['sigma'],g['mvs_p'],values['texture'],selection['selected_count'])
        values['curve']=values['curve'].astype(np.float16)
        result={**g,**selection,**values,**feat,'geometry_index':idx};result['point_id']=np.array([f'{"holdout" if sealed else "development"}:{v}' for v in g['point_id']])
        if a.stage=='benchmark':
            f=O/'benchmark'/f'{name}_{a.device}_{len(idx)}';f.parent.mkdir(exist_ok=True)
            np.savez_compressed(f.with_suffix('.npz'),**result);dump(f.with_suffix('.json'),timing);print('benchmark',clean(timing));return
        if reused is not None:
            assert result.keys()==reused.keys()
            result={k:np.concatenate([reused[k],result[k]]) for k in result};order=np.argsort(result['geometry_index'])
            result={k:v[order] for k,v in result.items()};timing['reused_pilot_points']=len(reused['point_id'])
        np.savez_compressed(dest,**result);dump(receipt,dict(**timing,config_sha256=sha(C/'photocheck_v1.json'),file_sha256=sha(dest),selection_seconds=load(selectionfile.with_suffix('.json'))['seconds']))
        print('complete',a.stage,sealed,name,len(idx),flush=True)
if __name__=='__main__':main()
