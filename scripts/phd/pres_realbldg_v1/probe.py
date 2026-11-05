from common import *
from preflight import schema
first_calculation()
for site in cfg()['sites']:
    for prior in ['LoD2','ALS']:
        p=JA/'core_points'/f'{site}__{prior}.npz';z=loadz(p,['building','centre','kind','surf','normal','prior_height_m'])
        print(site,prior,'bounds',z['centre'].min(0),z['centre'].max(0),'buildings',np.unique(z['building']).tolist(),'kind',np.unique(z['kind'],return_counts=True),'face53',int((z['surf']==53).sum()))
        rs=G/'scenes'/f'{site}__{prior}'/'distances/prior.json'
        v=json.loads(rs.read_text());print('MESH',v['mesh'])
print('building records',len(json.loads((W/'inputs/lod2_buildings.json').read_text())))
print('scope regions',json.loads((W/'scope_split.json').read_text())['regions'].keys())
print('surface53',json.loads((DR/'s02_box/B173nb_b10/lod2_surfaces.json').read_text())['surfaces'][53])
p=next((W/'patch_values').glob('*LoD2*R1.5.npz'));z=loadz(p,['centre','normal','building','kind','area','gt_p','cell']);print('OUTSIDE',p.name,len(z['cell']),np.unique(z['cell'],return_counts=True))
print('wall photos schema candidates')
for folder in ['main_wallphoto_v1/PHD-MAIN-WALLPHOTO-v1','main_wallphoto_v1/PHD-MAIN-WALLPHOTO-v1/r2','main_judgeapply_v1/PHD-MAIN-JUDGEAPPLY-v1']:
    root=PH/folder
    paths=list(root.glob('**/*photo*.npz'))[:2]
    for p in paths: print(p,schema(p))
