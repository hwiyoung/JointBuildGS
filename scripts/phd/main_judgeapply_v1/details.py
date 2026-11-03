from common import *
for site in cfg()['sites']:
 for prior in cfg()['priors']:
    p=TG/'r7/targets'/f'{site}_{prior}.npz'
    d=loadz(p,['photo_geometry_matched','photo_point_id','in_eval','kind'])
    mask=d['in_eval']&np.isin(d['kind'],cfg()['priors'][prior])
    print(site,prior,'matched',int((mask&d['photo_geometry_matched']).sum()),'mapped',int((mask&(d['photo_point_id']!='')).sum()),'example',d['photo_point_id'][mask&(d['photo_point_id']!='')][:2])
    p=S0/'s61/box'/site/prior/'units.npz'
    with np.load(p) as z:print('units',site,prior,[(k,list(z[k].shape)) for k in z.files if k in ['V','F','tri_surface','loc_extra','loc_center','surf_ext','loc_surface']])
