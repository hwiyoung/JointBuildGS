"""Call the exact official protection function on the saved 8000 PLY."""
import json,sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import torch
from plyfile import PlyData
sys.path.insert(0,'/source')
from train import find_building_mask_from_pcd
name=sys.argv[1];root=Path('/task/conditions')/name;out=root/'analysis';out.mkdir(exist_ok=True)
def xyz(path):
 p=PlyData.read(str(path))['vertex'];return np.column_stack([p[k] for k in ('x','y','z')]).astype(np.float32)
x=xyz(root/'model/point_cloud/iteration_8000/point_cloud.ply');p=xyz('/original_scene/lod2_pcd.ply' if name=='N' else root/'scene/lod2_pcd.ply')
with torch.no_grad():
 result=find_building_mask_from_pcd(SimpleNamespace(get_xyz=torch.from_numpy(x).cuda()),torch.from_numpy(p).cuda(),0.2)
mask=result.cpu().numpy();np.save(out/'native_mask8000.npy',mask)
(out/'native_mask8000_receipt.json').write_text(json.dumps({'function':'train.find_building_mask_from_pcd','threshold_m':.2,'chunk_size':20000,'dtype':'float32 CUDA; original function unchanged','n_total':len(mask),'n_protected':int(mask.sum()),'scientific_verdict':None},indent=2));print('Official mask',int(mask.sum()),'/',len(mask))
