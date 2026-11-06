from add4_common import *
for c in AC['cases']:
 r=loadz(root_of(c)/'rows.npz');rec=getcase(c);ref=loadz(O/'reference'/c['site']/'dense.npz');s=rec['section'];take=section_mask(r['xyz'],s)
 print(c['id'], 'keys',list(r),'bounds_uv',rec['box_corners_uv'],'row_band_z',np.percentile(r['xyz'][take,2],[0,10,50,90,100]).tolist(),flush=True)
 print('rowband wall',np.unique(r['wall'][take],return_counts=True),'roof normal',np.percentile(abs(r['normal'][take,2]),[0,50,100]),flush=True)
 line=np.array(s['start'])+np.linspace(0,1,17)[:,None]*(np.array(s['end'])-s['start']);rp=ref['xyz'][~ref['wall']];dd,ii=cKDTree(rp[:,:2]).query(line);print('line roof nearest',np.round(dd,2).tolist(),np.round(rp[ii,2],2).tolist(),flush=True)
