"""Stop gate from fixed no-GT agreement tests and recorded compute throughput."""
from common import *
from run_measure import selected_geometry
def main():
    rows=[];N=0;K=0;files=[]
    for f in sorted((O/'work/pilot').glob('*.npz')):
        if f.stem.endswith('_selection'):continue
        p=npz(f);m=(p['kind']==1)&(abs(p['mvs_p'])<.05)&(p['raw_u_mvs']<.03)&(p['texture']>=5)&(p['selected_count']>=3)
        # Missing h_max cannot count as a pass.
        k=m&np.isfinite(p['h_max'])&(abs(p['h_max'])<=.100001)
        N+=int(m.sum());K+=int(k.sum());files.append(dict(file=f.name,sha256=sha(f)))
        for b in np.unique(p['building']):
            mm=m&(p['building']==b);kk=k&(p['building']==b)
            rows.append(dict(tile=f.stem.split('__')[0],prior=f.stem.split('__')[1],building=b,eligible_points=int(mm.sum()),within_10cm=int(kk.sum()),fraction=float(kk.sum()/mm.sum()) if mm.any() else None))
    expected=0
    for tile in load(W/'inputs/tiles.json'):
        for prior in ['LoD2','ALS']:
            g,_=selected_geometry('pilot',tile['id'],prior);expected+=int((g['kind']==1).sum())
    counted=0
    for f in files:
        z=npz(O/'work/pilot'/f['file']);counted+=int((z['kind']==1).sum())
    assert counted==expected,(counted,expected)
    benchmark=load(O/'gates/benchmark.json');timing=benchmark['timing']
    # Actual pilot throughput provides a second bound including newly decoded images.
    receipts=[load(O/'work/pilot'/f['file'].replace('.npz','.json')) for f in files]
    pilot_points=sum(r['points'] for r in receipts);pilot_seconds=sum(r['seconds']+r['selection_seconds'] for r in receipts)
    projected=pilot_seconds/max(1,pilot_points)*timing['stage_b_points']/3600
    result=dict(at=now(),eligible_points=N,within_10cm=K,fraction=K/N if N else None,minimum_points_met=N>=100,
      projection_pass=N>=100 and K/N>.5,time_pass=max(projected,timing['gpu_hours'])<=48,benchmark_status=benchmark['status'],
      time_estimate={**timing,'actual_pilot_points':pilot_points,'actual_pilot_seconds_including_view_selection':pilot_seconds,'from_actual_pilot_stage_b_gpu_hours':projected},rows=rows,pilot_files=files,
      visual_gate=load(O/'gates/projection_visual.json') if (O/'gates/projection_visual.json').exists() else dict(status='PENDING'),scientific_verdict=None)
    result['status']='PASS' if result['projection_pass'] and result['time_pass'] and result['visual_gate']['status']=='PASS' else 'STOP'
    dump(O/'gates/pilot.json',result);dump(D/'tables/pilot_projection_gate.json',result)
    print(json.dumps(clean({k:v for k,v in result.items() if k not in ['rows','pilot_files','visual_gate']}),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
