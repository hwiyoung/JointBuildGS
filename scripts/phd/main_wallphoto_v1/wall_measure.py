"""Wall-only orchestration; reference group/visibility/curve/decision unchanged."""
import argparse,time
from common import *
from cameras import Cameras,select_photos
from curves import compute
from features import derive

def atomic_npz(path,values):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name('.'+path.stem+'.pending.npz')
    np.savez_compressed(tmp,**values);tmp.replace(path)

def measure(tile,indices,stage,tag,sealed=False):
    base=paths(sealed);full=npz(base/'geometry'/f'{tile}__LoD2.npz')
    g={k:v[indices] for k,v in full.items()};folder=base/'work'/stage;folder.mkdir(exist_ok=True)
    dest=folder/f'{tile}__{tag}.npz'
    if dest.exists() and dest.with_suffix('.json').exists():
        r=load(dest.with_suffix('.json'));assert r['config_sha256']==sha(C/'wallphoto_v1.json');return r
    cam=Cameras();start=time.monotonic();selection=select_photos(g,cam,tile,'LoD2')
    selection_seconds=time.monotonic()-start
    dump(O/'status.json',dict(at=now(),state='CURVES',stage=stage,tile=tile,tag=tag,points=len(indices),selection_seconds=selection_seconds,scientific_verdict=None))
    values,timing=compute(g,selection,'cpu',chunk_points=4096,progress=folder/f'{tile}__{tag}_progress.json')
    feat=derive(values['heights'],values['curve'],g['sigma'],g['mvs_p'],values['texture'],selection['selected_count'])
    values['curve']=values['curve'].astype(np.float16)
    # Camera optical axis in world frame; sign is irrelevant to vertical angle.
    vertical=np.abs(cam.R[:,2,2])>=np.cos(np.deg2rad(15))
    sel=selection['selected_images'];valid=sel>=0
    nadir=(vertical[np.maximum(sel,0)]&valid).sum(1).astype(np.int8)
    azimuth=(np.degrees(np.arctan2(g['normal'][:,0],g['normal'][:,1]))+360)%360
    result={**g,**selection,**values,**feat,'geometry_index':indices,'selected_vertical_count':nadir,'normal_azimuth_deg':azimuth.astype(np.float32)}
    result['point_id']=np.array([f'{"holdout" if sealed else "development"}:{v}' for v in g['point_id']])
    atomic_npz(dest,result)
    receipt=dict(**timing,selection_seconds=selection_seconds,total_seconds=time.monotonic()-start,config_sha256=sha(C/'wallphoto_v1.json'),file_sha256=sha(dest),stage=stage,tile=tile,tag=tag,scientific_verdict=None)
    dump(dest.with_suffix('.json'),receipt)
    print('complete',stage,tile,tag,len(indices),round(receipt['total_seconds'],2),flush=True)
    return receipt

def pilot():
    cfg=load(C/'wallphoto_v1.json');inv=load(O/'inventory.json');fraction=1.
    for bi,b in enumerate(EXAMPLES):
        if bi:
            estimate=load(O/'timing_first_building.json');fraction=estimate['remaining_sampling_fraction']
        candidates=[]
        for f in sorted((O/'geometry').glob('*__LoD2.npz')):
            g=npz(f);ids=np.flatnonzero(g['building']==b)
            candidates += [(f.stem.split('__')[0],int(i)) for i in ids]
        rng=np.random.default_rng(cfg['seed'])
        n=len(candidates);chosen=np.sort(rng.choice(n,max(1,int(np.floor(n*fraction))),replace=False)) if fraction<1 else np.arange(n)
        chosen=[candidates[i] for i in chosen];receipts=[]
        dump(O/'sampling'/f'{b}.json',dict(building=b,total_points=n,measured_points=len(chosen),fraction=len(chosen)/n,seed=cfg['seed'],selection='uniform point sample without replacement, before scores; first building complete',scientific_verdict=None))
        for tile in sorted(set(t for t,_ in chosen)):
            existing=O/'work/pilot'/f'{tile}__{b}.json'
            reuse=existing.exists() and existing.with_suffix('.npz').exists()
            if reuse:assert sha(existing.with_suffix('.npz'))==load(existing)['file_sha256']
            ids=np.array([i for t,i in chosen if t==tile],np.int64);receipts.append(measure(tile,ids,'pilot',b))
            from wall_report import report
            if not reuse:report('pilot')
        if bi==0:
            seconds=sum(r['total_seconds'] for r in receipts);spp=seconds/n
            pilot_n=sum(r['points'] for r in inv['pilot']);full_n=inv['development']['points']+inv['holdout']['points']
            budget=max(0,cfg['wall_task']['pilot_hours_max']*3600-seconds)
            remaining=max(1,pilot_n-n);fraction=min(1.,budget/max(1e-9,spp*remaining))
            timing=dict(at=now(),building=b,points=n,seconds=seconds,cpu_seconds_per_point=spp,pilot_cpu_hours=spp*pilot_n/3600,full_cpu_hours=spp*full_n/3600,full_points_including_sealed=full_n,gpu_hours=None,gpu_reason='GPU not used; no wall benchmark available',remaining_sampling_fraction=fraction,scientific_verdict=None)
            dump(O/'timing_first_building.json',timing);dump(D/'tables/timing_first_building.json',timing)
        dump(O/'status.json',dict(at=now(),state='PILOT_BUILDING_COMPLETE',building=b,buildings_complete=bi+1,scientific_verdict=None))
    dump(O/'pilot_complete.json',dict(at=now(),status='COMPLETE',scientific_verdict=None))

def fallback():
    # Called only if <100 strict projection-control points after pilot scores.
    cfg=load(C/'wallphoto_v1.json');items=[]
    for f in sorted((O/'geometry').glob('*__LoD2.npz')):
        g=npz(f);ids=np.flatnonzero(~np.isin(g['building'],EXAMPLES))
        items.extend((f.stem.split('__')[0],int(i)) for i in ids)
    rng=np.random.default_rng(cfg['seed']);chosen=[items[i] for i in np.sort(rng.choice(len(items),min(1000,len(items)),replace=False))]
    for tile in sorted(set(t for t,_ in chosen)):
        measure(tile,np.array([i for t,i in chosen if t==tile],np.int64),'fallback','random1000')
    dump(O/'fallback_complete.json',dict(at=now(),points=len(chosen),seed=cfg['seed'],scientific_verdict=None))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['pilot','fallback']);a=ap.parse_args()
    assert sha(C/'wallphoto_v1.json')==load(C/'wallphoto_v1.lock.json')['sha256']
    if a.stage=='pilot':pilot()
    else:fallback()
if __name__=='__main__':main()
