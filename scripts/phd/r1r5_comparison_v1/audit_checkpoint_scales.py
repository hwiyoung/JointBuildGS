"""Read completed checkpoint scale distributions without touching active training."""
import json
import hashlib
from pathlib import Path
import numpy as np
from plyfile import PlyData

cfg=json.loads(Path('/out/config.json').read_text());root=Path('/run')/cfg['relative'];rows=[]
for epoch in cfg['iterations']:
    folder=root/'model/jbgs_complete'/('iteration_'+str(epoch));rec=folder/'receipt.json'
    if not rec.exists():continue
    receipt=json.loads(rec.read_text());path=folder/'point_cloud.ply'
    digest=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024**2),b''):digest.update(chunk)
    assert digest.hexdigest()==receipt['ply_sha256']
    v=PlyData.read(path,mmap='r')['vertex'].data
    scale=np.maximum(np.exp(v['scale_0']),np.exp(v['scale_1']));ids=np.argsort(scale)[-5:][::-1]
    rows.append(dict(iteration=epoch,gaussians=len(v),scale_gt50m=int((scale>50).sum()),scale_gt100m=int((scale>100).sum()),
                top=[dict(id=int(i),scale_m=float(scale[i]),xyz=[float(v[k][i]) for k in 'xyz']) for i in ids],ply_sha256=digest.hexdigest()))
    del v,scale
result=dict(status='PASS_SAVED_CHECKPOINT_SCALE_AUDIT',rows=rows,scientific_verdict=None,
            caveat='IDs are local to each checkpoint; no cross-checkpoint primitive identity claim or ray-contribution claim.')
Path('/out/receipt.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
