"""RESCORE section 4.7, evaluated after training using the actual frozen targets."""
from common import *
NAMES={0:'일치',1:'보존',2:'보정',3:'보정(빈 공간)',4:'결측',9:'미판정'}

def measure(site,prior,table):
    stem=f'{site}__{prior}';rs=PH/'main_rescore_v1/PHD-MAIN-RESCORE-v1'
    p=O/'targets'/f'{stem}.npz';full=loadz(p,['source_index','h','sigma','judge_region'])
    core=loadz(JA/'core_points'/f'{stem}.npz',['source_index','patch_id','gt_p','area'])
    cells=loadz(rs/'cells_v2'/f'{stem}.npz',['patch_id','cell_v2','tau_v2_m']);assert np.array_equal(core['patch_id'],cells['patch_id'])
    ix=core['source_index'];h=full['h'][ix];s=full['sigma'][ix];region=full['judge_region'][ix];area=core['area'];cell=cells['cell_v2'];tau=cells['tau_v2_m']
    dist=np.abs(h-core['gt_p']);valid=np.isfinite(dist)&np.isfinite(s)&np.isfinite(tau)&~np.isin(cell,[5,6])
    points_path=O/'rescore/scores'/('ft_'+stem)/'points.npz'
    q=loadz(points_path,['row_distance_m','row_tau_m','row_owner']) if points_path.exists() else None
    owner=q['row_owner'] if q is not None else np.empty(0,dtype=int);owned=owner>=0
    rows=[]
    categories=[('목표 맞음',valid&(dist<=tau)),('목표 틀림 · 참값이 신뢰 구간 안',valid&(dist>tau)&(dist<=1.96*s)),
        ('목표 틀림 · 참값이 신뢰 구간 밖',valid&(dist>tau)&(dist>1.96*s)),('참값 없음',cell==6),
        ('영상 없음 · 사전 정보 틀림',cell==5),('목표 없음',~np.isin(cell,[5,6])&~np.isfinite(h)),
        ('목표 불확실도 없음',~np.isin(cell,[5,6])&np.isfinite(h)&~np.isfinite(s)),
        ('참값 자리 또는 τ 확인 불가',~np.isin(cell,[5,6])&np.isfinite(h)&np.isfinite(s)&(~np.isfinite(core['gt_p'])|~np.isfinite(tau)))]
    coverage=np.zeros(len(area),int)
    for label,mask in categories:coverage+=mask.astype(int)
    assert (coverage==1).all(),np.unique(coverage,return_counts=True)
    for r,label in NAMES.items():
        base=region==r;den=float(area[base].sum())
        for group,mask in categories:
            selected=base&mask;gm=np.zeros(len(owner),bool);gm[owned]=selected[owner[owned]]
            if q is not None:gm&=np.isfinite(q['row_distance_m'])&np.isfinite(q['row_tau_m'])
            n=int(gm.sum());scored=q is not None and group in [x[0] for x in categories[:3]]
            rows.append(dict(site=site,prior=prior,method='본 방법',judge_region=r,region=label,group=group,patches=int(selected.sum()),
                area_m2=float(area[selected].sum()),region_area_m2=den,area_fraction=float(area[selected].sum()/den) if den else None,
                n_gt=n if scored else None,completeness=float((q['row_distance_m'][gm]<=q['row_tau_m'][gm]).mean()) if scored and n else None,
                target_file=str(p),height_column='h',sigma_column='sigma',target_sha256=sha(p),score_points_sha256=sha(points_path) if q is not None else None))
    table('table6_'+stem,rows)
    rt=rs/'targets_v2'/f'{stem}.npz'
    if rt.exists():
        v=loadz(rt,['source_index','target_height_m']);jj=v['source_index'];a=full['h'][jj];b=v['target_height_m'];finite=np.isfinite(a)
        assert np.array_equal(finite,np.isfinite(b));delta=float(np.abs(a[finite]-b[finite]).max()) if finite.any() else 0.;assert delta<=.001
        table('targets_rescore_comparison_'+stem,[dict(site=site,prior=prior,status='PASS',compared=int(finite.sum()),max_height_difference_m=delta,target_sha256=sha(p),rescore_sha256=sha(rt))])
