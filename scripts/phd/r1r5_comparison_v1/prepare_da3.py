"""Build train-only balanced DA3 batches from an already sealed regional scene."""
import json
from pathlib import Path
import shutil
import sys
import numpy as np
sys.path.insert(0,'/repo')
from scripts.phd.geogs_p1p2p3_v1.input.prepare import read_pose_metadata,write_colmap
from src.phd.region_view_support_v1 import sha256

root=Path('/input/scene');out=Path('/output');out.mkdir(exist_ok=True)
split=json.loads((root/'split_manifest.json').read_text())
views={v['name']:v for v in split['train']};cameras,poses=read_pose_metadata(root)
groups=np.array_split(np.array(sorted(views)),(len(views)+7)//8)
records=[]
for i,group in enumerate(groups):
    names=group.tolist();centers=np.array([-np.array(views[n]['R']).T@views[n]['t'] for n in names])
    assert len(names)>=3 and np.linalg.matrix_rank(centers-centers.mean(0))>=2
    scene=out/'batches'/f'batch_{i:03d}';(scene/'images').mkdir(parents=True)
    for name in names:
        src=root/'images'/name;assert sha256(src)==views[name]['sha256'];shutil.copyfile(src,scene/'images'/name)
    write_colmap(scene/'sparse/0',cameras,[poses[views[n]['image_id']] for n in names],empty_points=True)
    records.append(dict(batch_id=i,names=names,image_ids=[views[n]['image_id'] for n in names]))
split['da3_batches']=records
(out/'split.json').write_text(json.dumps(split,indent=2))
(out/'receipt.json').write_text(json.dumps(dict(status='PASS',train=len(views),batches=len(records),
    split_sha256=sha256(out/'split.json'),source_split_sha256=sha256(root/'split_manifest.json'),scientific_verdict=None)))
