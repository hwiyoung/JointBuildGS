"""Read-only checkpoint timing and gradient availability inspection."""
import numpy as np
import torch
from plyfile import PlyData
from common import *
for row in json.loads((CFG/'cause_r8_lod2.json').read_text())['rows']:
    if not row['gradient_requested'] or not row['checkpoint']:continue
    c=torch.load(row['checkpoint'],map_location='cpu');v=PlyData.read(row['ply'])['vertex'].data
    x=np.column_stack([v[k] for k in ['x','y','z']]);y=c['model'][1].detach().numpy()
    grad=c['model'][8].detach().numpy();denom=c['model'][9].detach().numpy()
    print(row['key'],len(x),len(y),'sameids',np.array_equal(v['init_id'],c['init_id'].numpy()),'xyzsame',np.array_equal(x,y),
          'grad_nonzero',np.count_nonzero(grad),'denom_nonzero',np.count_nonzero(denom),flush=True)
    del c,v,x,y,grad,denom
