"""Apply the inherited image/prior feature definitions to all five case populations."""
from add4_common import *
from preservation import cameras,full_image
from normal_line import tangents

def main(site,prior):
    stem=f'{site}__{prior}';root=O/'scenes'/stem;out=AW/'features'/f'{stem}.npz'
    if out.exists():return
    row=loadz(root/'rows.npz');old=loadz(root/'preservation_features.npz');P=row['xyz'];t=loadz(FT/'targets'/f'{stem}.npz');valid=np.isfinite(t['prior_height_m'])&np.isfinite(t['normal']).all(1)&(np.linalg.norm(t['normal'],axis=1)>0)
    pos=t['centre'][valid]+t['prior_height_m'][valid,None]*t['normal'][valid];n=t['normal'][valid];a,b=tangents(n);tree=cKDTree(t['centre'][valid]);edge=np.zeros(len(pos),bool)
    for direction in [a,-a,b,-b]:
        d,j=tree.query(t['centre'][valid]+.25*direction,workers=2);edge|=(d>.125)|(abs(pos[j,2]-pos[:,2])>.5)
    ed=cKDTree(pos[edge,:2]).query(P[:,:2],workers=2)[0]<=1 if edge.any() else np.zeros(len(P),bool)
    cam=cameras(site);src=root/'preservation_features.json';oldmeta=json.loads(src.read_text());gravity=Path(oldmeta['gravity_source']);up=np.array(json.loads(gravity.read_text())['payload']['gravity']['up']);up/=np.linalg.norm(up);threshold=oldmeta['threshold']
    # Preserve already measured preservation-case image features exactly.
    seen=old['near_nadir_views'].copy();low=old['low_views'].copy();ids=np.flatnonzero(~old['preservation']);Q=P[ids];sources=[]
    for j,name in enumerate(cam.names):
        v=cam.centres[j]-Q;cos=v@up/np.linalg.norm(v,axis=1);qq=np.flatnonzero(cos>=np.cos(np.deg2rad(20.)))
        if not len(qq):continue
        uv,_,guard=cam.project(Q[qq],j);xy=np.rint(uv).astype('i8');good=guard&(xy[:,0]>=1)&(xy[:,0]<cam.w-1)&(xy[:,1]>=1)&(xy[:,1]<cam.h-1);qq=qq[good];xy=xy[good]
        if not len(qq):continue
        im,rec=full_image(cam,j);gray=np.asarray(im.convert('L'),dtype='f4')/255.;gy,gx=np.gradient(gray);grad=np.hypot(gx[xy[:,1],xy[:,0]],gy[xy[:,1],xy[:,0]])
        ii=ids[qq];seen[ii]+=1;low[ii]+=(grad<threshold).astype('i4');sources.append(dict(name=name,**rec));del im,gray,gx,gy
    texture=(seen>0)&(2*low>=seen);quadrant=np.zeros(len(P),'i1');quadrant[texture]=1;quadrant[ed]=2;quadrant[texture&ed]=3;quadrant[seen==0]=-2
    assert np.array_equal(quadrant[old['preservation']],old['quadrant'][old['preservation']])
    savez(out,textureless=texture,edge=ed,near_nadir_views=seen,low_views=low,quadrant=quadrant)
    dump(out.with_suffix('.json'),dict(source=proof(src),source_features=proof(root/'preservation_features.npz'),threshold=threshold,GT_used_to_define_features=False,
        reused_preservation_rows=int(old['preservation'].sum()),new_other_case_rows=len(ids),same_preservation_quadrants=True,images=sources,scientific_verdict=None))
    print('ADD4_FEATURES',stem,len(P),flush=True)
if __name__=='__main__':main(*sys.argv[1:])
