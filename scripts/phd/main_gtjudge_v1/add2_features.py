"""Reuse the locked feature implementation; reject undefined prior normals explicitly."""
import sys,types
from add2_common import *

def module(mask=None):
    src=R/'scripts/phd/main_gtjudge_v1/preservation.py';code=src.read_text()
    old="valid=np.isfinite(t['prior_height_m'])&np.isfinite(t['normal']).all(1)"
    assert code.count(old)==1;code=code.replace(old,old+"&(np.linalg.norm(t['normal'],axis=1)>0)")
    if mask is not None:
        code=code.replace("p=root/'preservation_features.npz'","p=root/'addendum2_comparison_features.npz'")
        code=code.replace("take=cell['case_id']==2","take=measurement_mask")
    m=types.ModuleType('add2_inherited_features');m.__file__=str(src);m.measurement_mask=mask;exec(compile(code,str(src),'exec'),m.__dict__);return m

def main(site,prior):
    config2();stem=f'{site}__{prior}';root=O/'scenes'/stem
    if not (root/'preservation_features.npz').exists():
        t=loadz(FT/'targets'/f'{stem}.npz',['normal','prior_height_m']);bad=np.isfinite(t['prior_height_m'])&np.isfinite(t['normal']).all(1)&(np.linalg.norm(t['normal'],axis=1)==0)
        issue(stem+f': 단계2 사전 정보 법선 길이 0인 {int(bad.sum())}패치를 가장자리 면 구성에서 제외. FINALTRAIN의 유효 법선 조건(길이>0)을 그대로 적용; 참값 법선과 학습 파일은 변경하지 않음.')
        m=module();m.features(site,prior);m.tables(site,prior)
        import figures
        if not (D/'figures'/f'{stem}_stage2_textureless1.png').exists():figures.preservation_samples(site,prior)
    labels=loadz(root/'stage1_cells.npz',['case_id'])['case_id'];rng=np.random.default_rng(20261105);samples={}
    for case in ['all',0,1,2,4,3]:
        ids=np.arange(len(labels)) if case=='all' else np.flatnonzero(labels==case)
        samples[str(case)]=np.sort(rng.choice(ids,50000,replace=False)) if len(ids)>50000 else ids
    sampled=np.unique(np.concatenate(list(samples.values())));mask=np.zeros(len(labels),bool);mask[sampled]=True
    m=module(mask);m.features(site,prior);z=loadz(root/'addendum2_comparison_features.npz');savez(root/'addendum2_comparison_samples.npz',**samples)
    rows=[]
    for case,ids in samples.items():
        n=len(ids);q=z['quadrant'][ids];population=len(labels) if case=='all' else int((labels==int(case)).sum());pct=lambda k:float(100*np.mean(q==k)) if n else None
        rows.append(dict(site=site,prior=prior,case_id=case,population_n=population,sample_n=n,seed=20261105,textureless_only_pct=pct(1),edge_only_pct=pct(2),both_pct=pct(3),other_pct=pct(0),texture_unknown_pct=pct(-2),textureless_pct=float(100*np.mean(z['textureless'][ids])) if n else None,edge_pct=float(100*np.mean(z['edge'][ids])) if n else None))
    table('addendum2/feature_comparison_'+stem,rows)
    dump(D/'tables/addendum2'/f'{stem}_feature_provenance.json',dict(at=now(),base_script_sha256=sha(R/'scripts/phd/main_gtjudge_v1/preservation.py'),adapter_sha256=sha(__file__),sample_file_sha256=sha(root/'addendum2_comparison_samples.npz'),original_four_scene_features_reused=True,scientific_verdict=None));print('FEATURE_COMPARISON_DONE',stem,flush=True)
if __name__=='__main__':main(*sys.argv[1:])
