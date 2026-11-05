"""Image-only low texture and prior-only edge descriptors for preservation cases."""
import sys,os,io,zipfile,importlib.util
import numpy as np
from PIL import Image
from scipy.spatial import cKDTree
from common import *
from geometry_add1 import views

def cameras(site):
    own=sys.modules.pop('common');paths=sys.path[:]
    folder=R/'scripts/phd/main_finaltrain_v1/inherited_judgeapply';sys.path.insert(0,str(folder));os.environ['FINALTRAIN_SITE']=site
    try:
        spec=importlib.util.spec_from_file_location('gt_texture_cameras',folder/'cameras.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);cam=m.Cameras(site)
    finally:sys.modules['common']=own;sys.path[:]=paths
    return cam

def full_image(cam,j):
    archive=PH.parent/'p0-audit/data/raw/uav/Images.zip'
    with zipfile.ZipFile(archive) as z:
        data=z.read(cam.members[j]);info=z.getinfo(cam.members[j])
    im=Image.open(io.BytesIO(data)).convert('RGB')
    return im,dict(archive=str(archive),member=cam.members[j],crc32=info.CRC,size=info.file_size)

def features(site,prior):
    cfg();stage_lock(2);stem=f'{site}__{prior}';root=O/'scenes'/stem;p=root/'preservation_features.npz'
    if p.exists():return
    row=loadz(root/'rows.npz');cell=loadz(root/'stage1_cells.npz');P=row['xyz'];take=cell['case_id']==2;ids=np.flatnonzero(take);Q=P[ids]
    t=loadz(FT/'targets'/f'{stem}.npz');valid=np.isfinite(t['prior_height_m'])&np.isfinite(t['normal']).all(1)
    pos=t['centre'][valid]+t['prior_height_m'][valid,None]*t['normal'][valid];n=t['normal'][valid]
    from normal_line import tangents
    a,b=tangents(n);tree=cKDTree(t['centre'][valid]);edge=np.zeros(len(pos),bool)
    for direction in [a,-a,b,-b]:
        d,j=tree.query(t['centre'][valid]+.25*direction,workers=4)
        edge|=(d>.125)|(abs(pos[j,2]-pos[:,2])>.5)
    ed=np.zeros(len(P),bool)
    if edge.any():ed[ids]=cKDTree(pos[edge,:2]).query(Q[:,:2],workers=4)[0]<=1
    camera=cameras(site)
    gravity=PH.parent/'p0-audit/data/work/gate_s0/freeze_recovery_v1/P2-GATE-S0-FREEZE-RECOVERY-v1/checkpoints/030-dense_mvs_and_gravity.json'
    up=np.array(json.loads(gravity.read_text())['payload']['gravity']['up']);up/=np.linalg.norm(up)
    threshold_file=R/'docs/evidence/p0-audit/w3-quality-integration/tables/W3_failure_surface_cause_thresholds.csv'
    with threshold_file.open() as f:threshold=float(next(x for x in csv.DictReader(f) if x['threshold']=='texture_gradient_low_max')['value'])
    low=np.zeros(len(P),'i4');seen=low.copy();best=np.full(len(P),-1,'i4');bestcos=np.full(len(P),-1.);images=[]
    for j,name in enumerate(camera.names):
        vec=camera.centres[j]-Q;length=np.linalg.norm(vec,axis=1);cos=vec@up/length;near=cos>=np.cos(np.deg2rad(20.));qq=np.flatnonzero(near)
        if not len(qq):continue
        uv,_,guard=camera.project(Q[qq],j);xy=np.rint(uv).astype('i8');inside=guard&(xy[:,0]>=1)&(xy[:,0]<camera.w-1)&(xy[:,1]>=1)&(xy[:,1]<camera.h-1);qq=qq[inside];xy=xy[inside]
        if not len(qq):continue
        im,rec=full_image(camera,j);gray=np.asarray(im.convert('L'),dtype='f4')/255.;gy,gx=np.gradient(gray);grad=np.hypot(gx[xy[:,1],xy[:,0]],gy[xy[:,1],xy[:,0]])
        ii=ids[qq];seen[ii]+=1;low[ii]+=(grad<threshold).astype('i4');update=cos[qq]>bestcos[ii];best[ii[update]]=j;bestcos[ii[update]]=cos[qq[update]]
        images.append(dict(name=name,**rec,measured_points=len(ii)));del gray,gx,gy,im
        if j%40==0:print('TEXTURE',stem,j,len(camera.names),flush=True)
    texture=(seen>0)&(2*low>=seen);quadrant=np.full(len(P),-1,'i1');quadrant[take]=0;quadrant[take&texture]=1;quadrant[take&ed]=2;quadrant[take&texture&ed]=3
    # Unobserved texture is unavailable, never silently labelled textured.
    quadrant[take&(seen==0)]=-2
    savez(p,preservation=take,textureless=texture,edge=ed,near_nadir_views=seen,low_views=low,best_camera=best,quadrant=quadrant)
    dump(p.with_suffix('.json'),dict(at=now(),site=site,prior=prior,threshold=threshold,threshold_source=str(threshold_file),threshold_sha256=sha(threshold_file),
        gravity_source=str(gravity),gravity_sha256=sha(gravity),prior_edge_patches=int(edge.sum()),
        edge_rule='four tangent neighbours at inherited 0.25m patch pitch; nearest centre within 0.125m else absent; prior Z jump >0.5m; horizontal distance <=1m',
        texture_rule='P0 PIL grayscale/255, np.gradient norm < threshold; training sight within20deg of frozen terrain up; >=half views',
        unavailable_no_near_nadir=int((take&(seen==0)).sum()),images=images,GT_used_to_define_features=False,scientific_verdict=None))
    issue(stem+': 가장자리 이웃은 상속 0.25 m 패치의 접선 네 방향, 중심 0.125 m 내 짝으로 고정; 수직 영상이 없는 점의 무늬는 확인 불가 별도 행.')

def tables(site,prior):
    stem=f'{site}__{prior}';root=O/'scenes'/stem;z=loadz(root/'preservation_features.npz');row=loadz(root/'rows.npz');cell=loadz(root/'stage1_cells.npz');core=loadz(JA/'core_points'/f'{stem}.npz',['photo_code']);owner=row['row_owner'];good=owner>=0
    photo=np.full(len(owner),9,'i1');photo[good]=core['photo_code'][owner[good]];rows=[]
    for name,mask in [('무늬 없음만',z['quadrant']==1),('가장자리만',z['quadrant']==2),('둘 다',z['quadrant']==3),('그 밖',z['quadrant']==0),('무늬 확인 불가',z['quadrant']==-2),('보존 칸 전체',z['preservation'])]:
        n=int(mask.sum());pct=lambda a:100*int((mask&a).sum())/n if n else None
        out=dict(site=site,prior=prior,unit='reference preservation cases',division=name,n_gt=n,small='적음' if n<1000 else '',
            judgment_agreement_pct=pct(cell['judge_original']==0),judgment_preserve_pct=pct(cell['judge_original']==1),judgment_correct_pct=pct(cell['judge_original']==2),judgment_missing_pct=pct(cell['judge_original']==4),judgment_other_pct=pct(~np.isin(cell['judge_original'],[0,1,2,4])),
            photo_support_pct=pct(photo==0),photo_refute_pct=pct(photo==1),photo_unknown_pct=pct(~np.isin(photo,[0,1])),
            photo_supported_preserve_n=int((mask&(photo==0)&(cell['judge_original']==1)).sum()),photo_supported_preserve_pct=pct((photo==0)&(cell['judge_original']==1)))
        for method in ['FINALTRAIN_30000','baseline_30000','judgment_mesh','gt_judgment_mesh','prior','A1','A2']:
            path=root/'distances'/f'{method}.npz'
            if path.exists():s=loadz(path,['row_s'])['row_s'];out[method+'_completeness_pct']=pct(np.isfinite(s)&(abs(s)<=row['row_tau_m']))
            else:out[method+'_completeness_pct']=None
        for m in ['A1','A2']:
            a=out[m+'_completeness_pct'];b=out['gt_judgment_mesh_completeness_pct'];out[m+'_minus_gtmesh_pp']=a-b if a is not None and b is not None else None
        rows.append(out)
    table('stage2/'+stem,rows)
    allmask=z['preservation'];n=int(allmask.sum());dump(D/'tables/stage2'/f'{stem}_summary.json',dict(site=site,prior=prior,n_gt=n,
        textureless_n=int(z['textureless'][allmask].sum()),edge_n=int(z['edge'][allmask].sum()),texture_unavailable_n=int((allmask&(z['near_nadir_views']==0)).sum()),
        photo_supported_preserve_n=rows[-1]['photo_supported_preserve_n'],photo_supported_preserve_pct=rows[-1]['photo_supported_preserve_pct'],scientific_verdict=None))

if __name__=='__main__':
    site,prior=sys.argv[1:3]
    if len(sys.argv)<4:features(site,prior)
    tables(site,prior)
