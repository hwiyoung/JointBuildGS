"""Check that frozen tile halos contain the complete inherited column/ring support."""
import json
from pathlib import Path
import numpy as np
from preflight import dump,sha
O=Path('/out');rows=[]
cfg=json.loads(Path('/cfg/widen0_v2.json').read_text());defs=cfg['definitions']
for tile in json.loads((O/'inputs/tiles.json').read_text()):
    rect=np.array(tile['buffer_global'])-[690953.,5336071.,690953.,5336071.]
    for prior in ['LoD2','ALS']:
        f=O/'holdout/internal/patch_geometry'/f'{tile["id"]}_{prior}.npz'
        with np.load(f) as z:
            c=z['centre'];n=z['normal'];h=np.where(z['roof_like'],defs['column_half_m']['roof'],defs['column_half_m']['wall'])
            # A face centre lies within H. Its slab extends by slab_half and
            # its ring by R in the tangent plane; this bounds exact filters,
            # rather than the deliberately oversized k-d-tree search balls.
            radius=(h[:,None]+defs['slab_half_m'])*np.abs(n[:,:2])+1.5*np.sqrt(np.maximum(0,1-n[:,:2]**2))
            frames=[('gt_and_mvs',c)]
            if prior=='ALS':frames.append(('shifted_als_source',c-z['frame_shift']))
            for frame,p in frames:
                margin=np.minimum(p[:,:2]-radius-rect[:2],rect[2:]-(p[:,:2]+radius))
                assert np.all(margin>=0),(tile['id'],prior,frame)
                rows.append(dict(tile=tile['id'],prior=prior,frame=frame,patches=len(c),
                    minimum_support_margin_m=float(margin.min()) if len(c) else None))
detail=O/'holdout/internal/diagnostics/buffer_support.json'
dump(detail,dict(rows=rows,scientific_verdict=None))
result=dict(status='PASS',check='All exact column/slab/ring supports fit within frozen 10 m source halos after registration.',
    detail_sha256=sha(detail),scientific_verdict=None)
dump(O/'gates/buffer_support.json',result);dump('/docs/tables/구역_겹침_검사.json',result)
print('all tile column/ring support bounds fit within source halos: PASS')
