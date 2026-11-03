"""Frozen TARGET r7 visibility rule on the retained new 5m/10m missing cores."""
import ast,json,zipfile,warnings,sys,time
import numpy as np
from scipy.spatial import cKDTree
from preflight import C,D,O,R,Path,sha,dump,now
from geometry import loadz,savez
from selected_npz import selected
from prepare import array
from photo_cameras import Cameras,W,read_depth
BASE=O/'r2';INPUT=O/'r1'

def inherit(path,name,scope):
    tree=ast.parse(path.read_text());node=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),scope);return scope[name]

def read_selected(path,ids,keys):
    with zipfile.ZipFile(path) as z:
        allids=array(z,'patch_id');m=np.isin(allids,ids);lookup={p:i for i,p in enumerate(allids[m])};ix=np.array([lookup[p] for p in ids])
        return {k:selected(z,k,m)[ix] for k in keys},np.flatnonzero(m)[ix]

def main(prior):
    started=time.monotonic();cfg=json.loads((C/'judgecheck_v1.json').read_text());target=Path(cfg['sources']['target']);sources=[R/'scripts/phd/main_target_v1'/n for n in ['disappearance_r7.py','disappearance_core_r7.py']]
    scope=dict(np=np,cKDTree=cKDTree,warnings=warnings,sha=sha);inherit(sources[0],'nearest',scope);test=inherit(sources[1],'test_groups',scope)
    lock=C/f'sight.{prior}.reply2.lock.json'
    if lock.exists():
        previous=C/'revisions/r2'/f'sight.{prior}.before_missing_donor_guard.json'
        if not previous.exists():previous.write_bytes(lock.read_bytes())
    dump(lock,dict(at=now(),source_sha256={str(p):sha(p) for p in sources+[Path(__file__)]},
        rule='exact inherited test_groups and nearest functions; old u/donor/margin rules; test union of n5<4 and n10<4; retained cores only including donors',truth_read=False,scientific_verdict=None))
    parts=[];offsets=[];n=0;binding={}
    for p in sorted((INPUT/'geometry').glob(f'*__{prior}.npz')):
        g=loadz(p);oldpath=target/'r2/stage0/development'/p.name
        d,source_ix=read_selected(oldpath,g['patch_id'],['region','u','u_replaced','sigma_p','area','kind','any_replaced','building','DL'])
        oldreg=d['region'].copy();oldr7=target/'r7/stage0/development'/p.name
        with zipfile.ZipFile(oldr7) as z:
            with z.open('disappeared.npy') as f:
                ver=np.lib.format.read_magic(f);shape,_,_=np.lib.format._read_array_header(f,ver)
            mask=np.zeros(shape[0],bool);mask[source_ix]=True;ix=np.argsort(np.argsort(source_ix));gone=selected(z,'disappeared',mask)[ix]
        oldreg[gone]=5
        savez(BASE/'old_rule'/p.name,patch_id=g['patch_id'],region=oldreg,limit_m=d.pop('DL'))
        d['region']=np.where((g['n']<4)|(g['n5']<4),0,1).astype('i1');d['centre']=g['centre'];d['in_eval']=np.ones(len(oldreg),bool)
        d['n10']=g['n'];d['n5']=g['n5'];d['patch_id']=g['patch_id'];parts.append(d);offsets.append((p.name,n,n+len(oldreg)));n+=len(oldreg);binding[str(oldpath)]=sha(oldpath)
    d={k:np.concatenate([p[k] for p in parts]) for k in parts[0]};del parts
    units,d['unit']=np.unique(d.pop('building'),return_inverse=True)
    donors=np.isfinite(d['u'])&~d['u_replaced'];bad_units=[i for i in np.unique(d['unit'][d['region']==0]) if not donors[d['unit']==i].any()]
    unavailable=(d['region']==0)&np.isin(d['unit'],bad_units);d['region'][unavailable]=1
    if unavailable.any():
        failure=dict(at=now(),status='PARTIAL_NO_ORIGINAL_U_DONORS',prior=prior,buildings=units[bad_units].tolist(),count=int(unavailable.sum()),area_m2=float(d['area'][unavailable].sum()),
            action='No donor substitution; these sight tests remain unavailable and cannot establish free space. Exact r7 test runs on remaining buildings.',scientific_verdict=None)
        dump(BASE/'sight'/f'{prior}.missing_donors.json',failure)
        with (D/'issues.md').open('a') as f:f.write(f"\n- {now()}: 시선 검사 {prior}: NO_ORIGINAL_U_DONORS, {failure['count']}개 / {failure['area_m2']} m². 실패 기록 보존. 해당 건물 검사는 확인 불가, 나머지는 같은 r7 규칙으로 계속.\n")
    cam=Cameras();cameras=[dict(name=name,W=1024,H=741,K=cam.K,W2C=cam.M[j]) for j,name in enumerate(cam.names)]
    def read(name):
        p=W/'mvs/full/stereo/depth_maps'/f'{name}.geometric.bin'
        if not p.exists():return np.full((741,1024),np.nan,'f4'),np.zeros((741,1024),'u1'),[]
        v=read_depth(p);return v,(np.isfinite(v)&(v>0)).astype('u1'),[p]
    result,record=test(d,cameras,read)
    for name,l,r in offsets:
        out={k:v[l:r] for k,v in result.items()};out['patch_id']=d['patch_id'][l:r];out['sight_unavailable']=unavailable[l:r];out['free10']=out['disappeared']&(d['n10'][l:r]<4);out['free5']=out['disappeared']&(d['n5'][l:r]<4);savez(BASE/'sight'/name,**out)
    record.update(at=now(),prior=prior,cores=n,seconds=time.monotonic()-started,source_files=binding,excluded_count=73,excluded_area_m2=5.442552935831812,scientific_verdict=None)
    dump(BASE/'sight'/f'{prior}.complete.json',record);print('SIGHT_COMPLETE',prior,record['seconds'],flush=True)
if __name__=='__main__':main(sys.argv[1])
