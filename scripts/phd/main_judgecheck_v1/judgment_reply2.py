"""Honest per-core judgments first; reference-only ablation in a separate function."""
import json,sys
import numpy as np
from preflight import C,O,Path,sha,dump,now
from geometry import loadz,savez
BASE=O/'r2';INPUT=O/'r1';GROUPS=[('ALS',1),('LoD2',1),('LoD2',2)]
VARIANTS=['new_clipped','new_unclipped','new_oldphoto','old_rule','always_prior','always_mvs']
ARMS=['main','all_oracle','geometry_oracle','cause_oracle','always_mix','always_prior','always_mvs','default_only','oldphoto']
def judge(g,photos,prior,free):
    N=len(g['n']);out=np.full(N,9,np.int8);reason=np.full(N,9,np.int8)
    valid=np.isfinite(g['prior_height_m'])&np.isfinite(g['normal']).all(1)
    missing=valid&(g['n']<4);inside=valid&(g['geometry']==0);outside=valid&(g['geometry']==1)
    out[missing]=4;out[missing&free]=3;out[inside]=0
    out[outside]=1 if prior=='ALS' else 2;reason[outside]=2
    out[outside&(photos==0)]=1;reason[outside&(photos==0)]=0;out[outside&(photos==1)]=2;reason[outside&(photos==1)]=1
    return out,reason

def ablations(g,regions,photos,gt,cell,prior):
    N=len(g['n']);arms=np.tile(regions[0],(9,1));known=np.isin(cell,np.arange(6))&(g['geometry']!=9)&np.isfinite(g['prior_height_m']);present=known&(g['n']>=4)
    agree=(cell==0);better_m=abs(g['mvs_mean_m']-gt)<abs(g['prior_height_m']-gt);oracle=np.where(better_m,2,1).astype(np.int8)
    default=np.where(photos==0,1,np.where(photos==1,2,1 if prior=='ALS' else 2)).astype(np.int8)
    arms[1,present]=np.where(agree[present],0,oracle[present]);arms[2,present]=np.where(agree[present],0,default[present]);arms[3,present&(g['geometry']==1)]=oracle[present&(g['geometry']==1)]
    arms[4,present]=0;arms[5]=regions[4];arms[6]=regions[5];arms[7,(g['geometry']==1)&known]=1 if prior=='ALS' else 2;arms[8]=regions[2]
    denM=g['u_mvs']**2+g['sigma_W_m']**2;denP=g['sigma_P_m']**2;zero=(denM==0)|(denP==0)
    with np.errstate(divide='ignore',invalid='ignore'):mixed=(g['mvs_mean_m']*denP+g['prior_height_m']*denM)/(denP+denM)
    mixed[zero]=g['mvs_mean_m'][zero];heights=np.full((9,N),np.nan)
    for i,reg in enumerate(arms):
        heights[i,reg==0]=mixed[reg==0];heights[i,np.isin(reg,[1,4])]=g['prior_height_m'][np.isin(reg,[1,4])];heights[i,reg==2]=g['mvs_mean_m'][reg==2]
    return arms,heights,zero,int((present&(abs(g['mvs_mean_m']-gt)==abs(g['prior_height_m']-gt))).sum())

def main(group):
    prior,kind=GROUPS[group];lock=C/f'judgment.{prior}_{kind}.reply2.lock.json';dump(lock,dict(at=now(),source_sha256=sha(Path(__file__)),variants=VARIANTS,ablation_arms=ARMS,
        geometry_unavailable='n>=4 missing u_M remains 9 in every arm; report uncountable area',oracle_tie='choose prior, tie count reported',scientific_verdict=None))
    files=[]
    for p in sorted((INPUT/'geometry').glob(f'*__{prior}.npz')):
        tile=p.stem.split('__')[0];allg=loadz(p);ix=np.flatnonzero(allg['kind']==kind);g={k:v[ix] for k,v in allg.items()};photo=loadz(BASE/'photo_points'/f'{tile}__{prior}__{kind}.npz');lookup={v:i for i,v in enumerate(photo['point_id'])};owners=np.array([lookup[v] for v in g['photo_point_id']])
        oldphoto=photo['old_code'][owners];unified=np.select([oldphoto==2,oldphoto==3,oldphoto==4],[8,6,7],default=oldphoto).astype('i1')
        codes=np.vstack([photo['new_code'][:,owners],unified]);s=loadz(BASE/'sight'/p.name);assert np.array_equal(s['patch_id'],allg['patch_id']);free=s['free10'][ix]
        result=[judge(g,v,prior,free) for v in codes];regions=np.vstack([v[0] for v in result]);reasons=np.vstack([v[1] for v in result])
        old=loadz(BASE/'old_rule'/p.name);assert np.array_equal(old['patch_id'],allg['patch_id']);oldcode=old['region'][ix];oldreg=np.full(len(ix),9,np.int8)
        for a,b in [(0,4),(1,0),(2,1),(3,2),(4,2),(5,3)]:oldreg[oldcode==a]=b
        invalid=~np.isfinite(g['prior_height_m'])|~np.isfinite(g['normal']).all(1);oldreg[invalid]=9
        pp=regions[0].copy();mm=pp.copy();pp[g['geometry']==1]=1;mm[g['geometry']==1]=2;pp[invalid]=9;mm[invalid]=9
        regions=np.vstack([regions,oldreg,pp,mm])
        reasons=np.vstack([reasons,np.full((3,len(ix)),9,np.int8)])
        # The honest outputs above do not access the reference file.
        truth=loadz(BASE/'truth'/p.name);assert np.array_equal(truth['patch_id'],allg['patch_id']);gt=truth['gt_p'][ix];cell=truth['cell'][ix]
        arms,height,zero,ties=ablations(g,regions,codes[0],gt,cell,prior)
        keep=['patch_id','photo_point_id','building','centre','normal','kind','area','surf','roof_type','u_mvs','sigma_P_m','sigma_W_m','r_m','prior_height_m','mvs_mean_m','mvs_median_m','mvs_sd_m','prior_n','d_m','L_m','n','n5','geometry','normal_rule_met','normal_radius_m']
        out={k:g[k] for k in keep};out.update(photo_code=codes,region=regions,reason=reasons,old_region_source=oldcode,old_limit_m=old['limit_m'][ix],
            prior=np.full(len(ix),prior),split=np.full(len(ix),'development'),old_photo_code=oldphoto,new_photo_code=codes[:2],
            free10=free,free5=s['free5'][ix],sight_votes=s['votes'][ix],sight_unavailable=s['sight_unavailable'][ix],gt_p=gt,gt_status=truth['gt_status'][ix],cell=cell,old_cell=truth['old_cell'][ix],
            arm_region=arms,arm_height_m=height,zero_weight_denominator=zero,photo_computed=photo['computed'][owners],mvs_normal_angle_deg=photo['mvs_normal_angle_deg'][owners],mvs_plane_available=photo['available'][owners,1])
        dest=BASE/'core_points'/f'{tile}__{prior}__{kind}.npz';savez(dest,**out);files.append(dict(path=str(dest),sha256=sha(dest),count=len(ix),oracle_ties=ties))
    dump(BASE/'core_points'/f'{prior}_{kind}.complete.json',dict(at=now(),files=files,scientific_verdict=None));print('JUDGMENT_COMPLETE',prior,kind,sum(v['count'] for v in files),flush=True)
if __name__=='__main__':main(int(sys.argv[1]))
