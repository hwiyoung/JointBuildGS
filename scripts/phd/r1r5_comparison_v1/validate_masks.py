"""Validate every mask against sealed per-view depths and exact training membership."""
import hashlib,json
from pathlib import Path
import numpy as np
root=Path('/run');records=[]
for region in ['R1','R2','R3','R4','R5']:
    folder=root/region/'masks';r=json.loads((folder/'receipt.json').read_text());assert r['status']=='PASS' and r['total_pixels']>0
    inputs=Path('/r1input') if region=='R1' else root/region/'preparation/input'
    split=json.loads((inputs/'scene/split_manifest.json').read_text());names={Path(v['name']).stem for v in split['train']}
    assert {v['name'] for v in r['masks']}==names and len(r['masks'])==len(names)
    count=0;views=0
    for v in r['masks']:
        p=folder/v['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==v['sha256']
        m=np.load(p,allow_pickle=False);name=v['name']+'.npy';pd=np.load(inputs/'prior/raw_depth'/name);md=np.load(inputs/'mvs_rgb/raw_depth'/name)
        assert m.dtype==bool and m.shape==pd.shape==md.shape
        assert np.all(np.isfinite(pd[m])&(pd[m]>0)&np.isfinite(md[m])&(md[m]>pd[m]+1.))
        assert int(m.sum())==v['pixels'];count+=v['pixels'];views+=int(v['pixels']>0)
    assert count==r['total_pixels'] and views==r['contributing_views']
    records.append(dict(region=region,total_pixels=count,contributing_views=views,train=len(names),mask_receipt_sha256=hashlib.sha256((folder/'receipt.json').read_bytes()).hexdigest()))
result=dict(status='PASS',scientific_verdict=None,regions=records,meaning='Mask identity/membership/shape/finite-depth gates verified; not source correctness')
Path('/out/receipt.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
