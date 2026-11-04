from common import *
from plyfile import PlyData
FT=PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1';site='B173nb_b10'
for prior in ['ALS','LoD2']:
 for name,p in [('target',FT/'targets'/f'{site}__{prior}.npz'),('seeds',FT/'stage1'/f'{site}__{prior}'/'seeds.npz'),('snapshot',FT/'runs'/site/f'ft_{prior}_s0/attempt1/model/target_monitor/snapshot_30000.npz')]:
  if p.exists():
   with np.load(p) as z:print(prior,name,{k:str(z[k].shape) for k in z.files})
  else:print('MISSING',p)
 p=FT/'runs'/site/f'ft_{prior}_s0/attempt1/model/point_cloud/iteration_30000/point_cloud.ply';p=PlyData.read(p);print('PLY',prior,p['vertex'].data.dtype.names)
print('ALS kind',np.unique(loadz(JA/'core_points'/f'{site}__ALS.npz',['kind'])['kind'],return_counts=True))
print('FTstage1',list((FT/'stage1').glob('*B173*')))
