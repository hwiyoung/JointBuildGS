"""Existing virtual meshes: reproduce the wall baseline, then count new arms."""
import argparse,sys,gc
import open3d as o3d
from interview_common import *
from interview_meshio import crop,mapped
from mesh_worker import first_hit
sys.path.insert(0,'/repo')
from src.phd.metrics_v3.surface import MeshScene

def virtual_path(site,prefix):
    mp=model(site,'LoD2',prefix);root=mp.parent if prefix=='nojudge' else mp.parent.parent
    old=root/'gpu/virtual/mesh_virtual.ply'
    return old if old.exists() else IOUT/'virtual'/site/f'{prefix}_LoD2_s0/mesh_virtual.ply'

def baseline():
    reference=json.loads((R/'docs/experiments/phd/main_baselines_v1/figures/wall_presence.json').read_text())['units']['B173nb_b10/LoD2']
    with np.load(S1/'defs/B173nb_b10/unseen.npz') as f:points=f['centre'].astype(float);face=f['surf_ext']==53;good=face&(f['label_inferred']==0)
    w=json.loads((S1/'defs/fig_views_v1.json').read_text())['sites']['B173nb_b10']['unseen_face']
    assert int(w['surf_ext'])==53
    reg=(np.array(w['centre']),np.array(w['t']),np.array(w['normal']),w['s_range'][0]-1.5,w['s_range'][1]+1.5,1.5,w['z_range'][0]-1.5,w['z_range'][1]+1.5)
    keep=frozen_function(R/'scripts/phd/main_baselines_v1/figs_bl.py','_keep',dict(np=np));checks=[]
    for seed in [0,1]:
        result=f'prop_LoD2_s{seed}';path=PH/'metrics_fix_v1/PHD-MAIN-METRICS-FIX-v1/virtual/option2'/f'b{seed+1}_LoD2/mesh_virtual.ply'
        vm,fm=mapped(path);V=np.stack([vm[k].astype(float) for k in ['x','y','z']],axis=1);kv=keep(V,reg);parts=[]
        for st in range(0,len(fm),200000):
            ids=fm['indices'][st:st+200000];parts.append(np.asarray(ids[kv[ids].any(1)],np.int64))
        F=np.concatenate(parts);u,inv=np.unique(F,return_inverse=True);scene=MeshScene(V[u],inv.reshape(-1,3))
        d=scene.distance(points);present=int((d[good]<=.25).sum());want=reference['results'][result]
        checks.append(dict(result=result,patches=int(good.sum()),present=present,expected_present=want['present'],pct=100*present/int(good.sum()),pass_check=present==want['present'],mesh=source(path)))
        del vm,fm,V,F,scene;gc.collect()
    mean=float(np.mean([x['pct'] for x in checks]));ok=all(x['pass_check'] for x in checks) and round(mean,1)==92.3
    dump(IDOC/'checks/virtual_baseline.json',dict(status='PASS' if ok else 'STOP_BASELINE_MISMATCH',checks=checks,mean_pct=mean,expected_display_pct=92.3,
        definition='B173 LoD2 face 53, label_inferred 0, same original baseline wall crop and Euclidean MeshScene.distance, two-seed mean',scientific_verdict=None))
    assert ok,'wall baseline mismatch: new virtual measurements must wait'
    record('virtual-baseline',mean_pct=mean,checks=checks)

def measure(site,prefix):
    job=f'virtual-{SHORT[site].lower()}-{prefix}';check=IDOC/'checks/virtual_baseline.json'
    assert check.exists() and json.loads(check.read_text())['status']=='PASS'
    path=virtual_path(site,prefix)
    if not path.exists():record(job,status='PENDING_GPU',reason='가상 시점 메시 없음. GPU 학습 완료와 자원 입장 뒤 생성 대기.');return
    e,v,base=evaluation(site,'LoD2');result=f'{prefix}_LoD2_s0';train,zp=patch_values(site,'LoD2',result,e)
    rp=S1/'regions_v3'/f'regions_ext_v3_{site}_LoD2.npz'
    with np.load(rp) as f:
        assert np.array_equal(f['centre'],e['centre']);wall=f['in_eval']&(f['kind']==2)&np.isin(f['code_ext_v3'],[5,14]);code=f['code_ext_v3']
    rows=[];ids=np.flatnonzero(wall)
    if len(ids):
        mesh=crop(path,e['centre'][ids].min(0)-.6,e['centre'][ids].max(0)+.6,intersect=True)
        d=MeshScene(np.asarray(mesh.vertices),np.asarray(mesh.triangles)).distance(e['centre'][ids]) if len(mesh.triangles) else np.full(len(ids),np.inf)
        for group,mask in [('전체',np.ones(len(ids),bool)),('기존 코드 5',code[ids]==5),('기존 코드 14',code[ids]==14)]:
            den=float(e['area'][ids[mask]].sum())
            for threshold in [.25,.5]:
                yes=mask&(d<=threshold);area=float(e['area'][ids[yes]].sum())
                rows.append(dict(site=site,result=result,group=group,threshold_m=threshold,patches=int(mask.sum()),area_m2=den,wall_present_area_m2=area,wall_present_pct=100*area/den if den else None))
        del mesh;gc.collect()
    want=eligible(e)&np.isin(e['cell'],[2,4])&train['no_surface'];ii=np.flatnonzero(want);newrows=[]
    if len(ii):
        dm=np.nan_to_num(e['p_mvs'][ii],nan=0.);dg=np.nan_to_num(e['p_gt'][ii],nan=0.)
        a=e['centre'][ii]+np.maximum(6.,np.maximum(dm+.5,dg+.5))[:,None]*e['normal'][ii]
        b=e['centre'][ii]+np.minimum(-6.,np.minimum(dm-.5,dg-.5))[:,None]*e['normal'][ii]
        mesh=crop(path,np.minimum(a.min(0),b.min(0))-.01,np.maximum(a.max(0),b.max(0))+.01,intersect=True)
        ev=dict(e);ev['scoring_allowed']=e['scoring_allowed']&want;new=first_hit(mesh,ev,v)
        for cell in [2,4]:newrows.append(summary(e,new,want&(e['cell']==cell),site=site,result=result,cell=cell))
        dest=IOUT/'virtual_scores';dest.mkdir(exist_ok=True,parents=True)
        np.savez_compressed(dest/f'{site}__{result}.npz',**new)
    write_table(job+'_walls',rows,['기존 영역 v3의 비가시 벽: kind=2, code=5/14, in_eval. 새 가시성 계산 없음.'])
    write_table(job+'_missing_reclassified',newrows,['원래 학습 시점 메시에서 면 없음이던 같은 패치. 분류 함수·분모를 바꾸지 않음.'])
    dump(IDOC/'checks'/(job+'.json'),dict(status='PASS',sources=[source(path),source(zp),source(rp)],scientific_verdict=None))
    record(job,wall_patches=len(ids),no_surface_patches=len(ii),mesh=str(path))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('site');ap.add_argument('prefix',nargs='?');a=ap.parse_args();config()
    if a.site=='baseline':baseline()
    else:measure(a.site,a.prefix)

if __name__=='__main__':main()
