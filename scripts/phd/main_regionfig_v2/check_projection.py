from draw_figures import *

c=load(CFG/'regionfig_v2.json');ex=c['examples'][0];d=data(ex['prior'],ex['building']);g=geometry(ex,d)
ids=g['ids'];poly=g['polys'];edge=np.linalg.norm(poly-np.roll(poly,1,axis=1),axis=2).max(1)
order=np.argsort(edge)[-8:]
cam=cameras(W/'mvs/full/sparse/cameras.bin');pose=poses(W/'mvs/full/sparse/images.bin')[ex['photo']['stem']]
tc=cam[pose['cam']];cc=d['centre']+np.where(np.isfinite(d['gt_p']),d['gt_p'],0)[:,None]*d['normal']
uv,z=project(cc,pose,tc);good=(z>0)&(uv[:,0]>=0)&(uv[:,0]<tc['w'])&(uv[:,1]>=0)&(uv[:,1]<tc['h'])
for i in order:
    k=ids[i];print('edge',edge[i],d['patch_id'][k],'area',d['area'][k],'normal',d['normal'][k], 'good',good[k], 'cameraUV',uv[k], 'xyz',cc[k])
print('bad_training',int((g['inside']&~good).sum()),'large_edges',int((edge>40).sum()),'area_max',float(d['area'].max()),'norm_range',np.nanmin(np.linalg.norm(d['normal'],axis=1)),np.nanmax(np.linalg.norm(d['normal'],axis=1)))
