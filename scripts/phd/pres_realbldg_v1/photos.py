"""Reuse inherited FULL_OPENCV projection and full-resolution low texture."""
from common import *
import struct,cv2
from PIL import Image
import io
from scipy.spatial import cKDTree

scope=dict(np=np,struct=struct,json=json,zipfile=zipfile,cv2=cv2,Path=Path,W=W,RAW=RAW)
scope.update(inherit(R/'scripts/phd/main_judgecheck_v1/photo_cameras.py',['poses','rotation','read_depth','Cameras'],scope))
BaseCameras=scope['Cameras']
regional=dict(scope,BaseCameras=BaseCameras,S0=S0)
RegionalCameras=inherit(R/'scripts/phd/main_judgeapply_v1/cameras.py',['Cameras'],regional)['Cameras']
def cameras(site):return BaseCameras() if site=='outside' else RegionalCameras(site)
def full_rgb(cam,j,archive):
    return Image.open(io.BytesIO(archive.read(cam.members[j]))).convert('RGB')
def texture():
    cfg();blds=json.loads((O/'buildings.json').read_text());jobs=[]
    for p in sorted((O/'data').glob('*.npz')):
        if (O/'texture'/p.name).exists():continue
        site=p.stem.split('__')[0];d=loadz(p,['xyz','case','kind','building','texture','texture_seen']);z=loadz(O/'zones'/p.name,['interior','in_experiment'])
        eligible=z['interior']&np.isin(d['case'],[0,2])&np.isin(d['building'],list(blds))&(d['texture']<0)
        if site=='outside':eligible&=~z['in_experiment']
        ix=np.flatnonzero(eligible);P=d['xyz'][ix];cam=cameras(site)
        jobs.append(dict(stem=p.stem,ix=ix,P=P,tree=cKDTree(P[:,:2]),cam=cam,seen=np.zeros(len(P),'i4'),low=np.zeros(len(P),'i4'),prior_texture=d['texture'],prior_seen=d['texture_seen']))
    if not jobs:return
    gravity=RAW/'work/gate_s0/freeze_recovery_v1/P2-GATE-S0-FREEZE-RECOVERY-v1/checkpoints/030-dense_mvs_and_gravity.json'
    up=np.asarray(json.loads(gravity.read_text())['payload']['gravity']['up']);up/=np.linalg.norm(up)
    threshold_file=R/'docs/evidence/p0-audit/w3-quality-integration/tables/W3_failure_surface_cause_thresholds.csv'
    with threshold_file.open() as f:threshold=float(next(x for x in csv.DictReader(f) if x['threshold']=='texture_gradient_low_max')['value'])
    mapping={}
    for k,g in enumerate(jobs):
        for j,member in enumerate(g['cam'].members):mapping.setdefault(member,[]).append((k,j))
    archive=zipfile.ZipFile(RAW/'raw/uav/Images.zip');used=[]
    for num,(member,pairs) in enumerate(mapping.items()):
        selections=[]
        for k,j in pairs:
            g=jobs[k];P=g['P'];cam=g['cam']
            if not len(P):continue
            c=cam.centres[j];cone=np.deg2rad(20)+np.arccos(np.clip(up[2],-1,1));rad=max(0,c[2]-P[:,2].min())*np.tan(cone)+1e-6 if cone<np.pi/2 else np.inf
            ii=np.asarray(g['tree'].query_ball_point(c[:2],rad),int)
            if not len(ii):continue
            v=c-P[ii];near=(v@up/np.linalg.norm(v,axis=1))>=np.cos(np.deg2rad(20));ii=ii[near]
            if not len(ii):continue
            uv,_,guard=cam.project(P[ii],j);xy=np.rint(uv).astype('i8');good=guard&(xy[:,0]>=1)&(xy[:,0]<cam.w-1)&(xy[:,1]>=1)&(xy[:,1]<cam.h-1);ii=ii[good];xy=xy[good]
            if len(ii):selections.append((k,ii,xy))
        if not selections:continue
        im=Image.open(io.BytesIO(archive.read(member))).convert('L');gray=np.asarray(im,dtype='f4')/255.
        # Identical central np.gradient stencil at interior pixels, without
        # allocating full-size gradient images for unrelated pixels.
        for k,ii,xy in selections:
            x,y=xy.T;gx=(gray[y,x+1]-gray[y,x-1])*.5;gy=(gray[y+1,x]-gray[y-1,x])*.5
            jobs[k]['seen'][ii]+=1;jobs[k]['low'][ii]+=(np.hypot(gx,gy)<threshold)
        inf=archive.getinfo(member);used.append(dict(member=member,crc32=inf.CRC,bytes=inf.file_size));del gray,im
        if num%40==0:print('TEXTURE_IMAGE',num,'/',len(mapping),'used',len(used),flush=True)
    for g in jobs:
        seen=g['seen'];ix=g['ix'];v=g['prior_texture'];v[ix[seen>0]]=(2*g['low'][seen>0]>=seen[seen>0]).astype('i1');ss=g['prior_seen'];ss[ix]=seen
        savez(O/'texture'/f"{g['stem']}.npz",texture=v,seen=ss)
        print('TEXTURE_DONE',g['stem'],'new_points',len(ix),'unseen',int((seen==0).sum()),flush=True)
    dump(O/'texture/provenance.json',dict(at=now(),threshold=threshold,threshold_source=source(threshold_file),gravity_source=source(gravity),images=used,scientific_verdict=None))
if __name__=='__main__':texture()
