"""Order section 2.1 only. Stop before cylinder work when a roof cell lacks 5 buildings."""
import csv
import json
import os
from pathlib import Path
import resource
import time
import zipfile

import numpy as np
from lock_config import dump, sha, stamp
from selected_npz import selected, building_ids

C = Path('/cfg'); O = Path('/out'); D = Path('/docs')
def main():
    t0 = time.monotonic()
    cfg = json.loads((C/'judgenum_v1.json').read_text())
    lock = json.loads((C/'judgenum_v1.lock.json').read_text())
    assert sha(C/'judgenum_v1.json') == lock['config_sha256']
    assert os.environ['CUDA_VISIBLE_DEVICES'] == ''
    assert not list(Path('/dev').glob('nvidia*'))
    started = stamp()
    assert started > lock['locked_at']
    wanted = set(cfg['scope']['development'])
    excluded = {r['building'] for r in cfg['scope']['excluded']}
    held = set(cfg['scope']['holdout'])
    assert not (wanted & (excluded|held))
    W = Path(cfg['sources']['widen'])
    (O/'scope_selection').mkdir(exist_ok=True)
    assert not (O/'sample_gate.json').exists(), 'Preserve previous gate receipt'
    totals = []; by_building = []; inputs = []
    for prior in ['LoD2','ALS']:
        parts = []; source_buildings = set()
        files = sorted((W/'patch_values').glob(f'*__{prior}__R1.5.npz'))
        assert len(files)==24, 'Unexpected source partition inventory'
        for p in files:
            meta = json.loads(p.with_suffix('.json').read_text())
            with zipfile.ZipFile(p) as z:
                bids = building_ids(z); source_buildings.update(bids.tolist())
                assert not (set(bids) & held)
                mask = np.isin(bids, sorted(wanted))
                data = {k:selected(z,k,mask) for k in ['patch_id','kind','area','cell','centre']}
                data['building'] = bids[mask]
            assert len(set(data['patch_id'])) == len(data['patch_id'])
            assert np.isfinite(data['area']).all() and np.all(data['area']>0)
            assert np.isin(data['cell'], np.arange(7)).all()
            assert np.isin(data['kind'], [1,2]).all()
            assert np.isfinite(data['centre']).all()
            dest = O/'scope_selection'/p.name
            np.savez_compressed(dest, **data)
            inputs.append({'path':str(p),'source_sha256_from_sidecar':meta['sha256'],
                'selected_rows':len(data['building']),'selected_sha256':sha(dest),
                'selected_path':str(dest),'measurement_rows_decoded_outside_scope':0})
            parts.append(data)
        assert len(source_buildings)==cfg['scope']['source_development_expected'][prior]
        data = {k:np.concatenate([p[k] for p in parts]) for k in parts[0]}
        assert len(set(data['patch_id']))==len(data['patch_id'])
        for kind in [1,2]:
            m = data['kind']==kind
            buildings = sorted(set(data['building'][m]))
            row = {'prior':prior,'kind':kind,'building_count':len(buildings),
                'patch_count':int(m.sum()),'area_m2':float(data['area'][m].sum())}
            for bid in buildings:
                b = m & (data['building']==bid)
                by_building.append({'prior':prior,'kind':kind,'building':bid,
                  'patch_count':int(b.sum()),'area_m2':float(data['area'][b].sum()),
                  **{f'cell{c}_area_m2':float(data['area'][b&(data['cell']==c)].sum()) for c in range(7)}})
            for cell in [1,2]:
                amounts = sorted([(r[f'cell{cell}_area_m2'],r['building']) for r in by_building
                    if r['prior']==prior and r['kind']==kind], key=lambda x:(-x[0],x[1]))
                area = float(data['area'][m&(data['cell']==cell)].sum())
                row[f'cell{cell}_area_m2'] = area
                row[f'cell{cell}_buildings_gt1m2'] = sum(a>1. for a,_ in amounts)
                row[f'cell{cell}_top3_fraction'] = sum(a for a,_ in amounts[:3])/area if area else None
                row[f'cell{cell}_top3_buildings'] = [b for a,b in amounts[:3] if a>0]
            totals.append(row)
        print(prior, 'eligible buildings',len(set(data['building'])), 'patches',len(data['building']),flush=True)
    fails = [{'prior':r['prior'],'cell':c,'buildings_gt1m2':r[f'cell{c}_buildings_gt1m2'],
              'required':5} for r in totals if r['kind']==1 for c in [1,2]
              if r[f'cell{c}_buildings_gt1m2']<5]
    receipt = {'task_id':cfg['task_id'],'status':'STOP_SAMPLE_GATE' if fails else 'PASS_SAMPLE_GATE',
      'scientific_verdict':None,'started_at':started,'finished_at':stamp(),
      'config_sha256':lock['config_sha256'],'rows':totals,'failures':fails,
      'excluded_buildings':cfg['scope']['excluded'],'input_selection':inputs,
      'read_boundary':'IDs and GroundSurface XY for exclusion; no evaluation or holdout measurement rows decoded',
      'gpu_devices':[], 'cuda_visible_devices':os.environ['CUDA_VISIBLE_DEVICES'],
      'nice':os.getpriority(os.PRIO_PROCESS,0),'maxrss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
      'seconds':time.monotonic()-t0,'commit':os.environ['JUDGENUM_COMMIT'],
      'image_id':os.environ['JUDGENUM_IMAGE'],'source':'PHD-MAIN-WIDEN0-v2 frozen patch_values; [이 발주에서 냄]'}
    dump(O/'sample_gate.json',receipt)
    for name,rows in [('sample_counts',totals),('sample_buildings',by_building),('excluded_buildings',cfg['scope']['excluded'])]:
        dump(D/'tables'/f'{name}.json',{'rows':rows,'config_sha256':lock['config_sha256'],
            'source':receipt['source'],'scientific_verdict':None})
        with (D/'tables'/f'{name}.csv').open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader()
            for row in rows: w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,list) else v for k,v in row.items()})
    dump(D/'tables/sample_gate.json',receipt)
    print(json.dumps({'status':receipt['status'],'rows':totals,'failures':fails,'seconds':receipt['seconds']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
