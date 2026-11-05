"""Reuse RELEASE cells/RESCORE distances and add exact-label counts and wall checks."""
from common import *
import gc
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
sys.path.insert(0,'/repo')
from src.phd.metrics_v3.surface import MeshScene
scope=dict(np=np,Path=Path,loadz=loadz)
globals().update(source_functions(R/'scripts/phd/main_rescore_v1/figures.py',['read_surface','section_segments','section_points'],scope))
globals().update(source_functions(R/'scripts/phd/main_dist71_v1/dm_common.py',['closest'],dict(np=np)))

def choose_section(xyz,cell,c):
    ids=np.flatnonzero(cell==2)
    if not len(ids):return dict(status='확인 불가',reason='사전 정보만 맞음 참값 행 없음')
    # Exact duplicate coordinates have identical connectivity; weights preserve row counts.
    p,inverse,counts=np.unique(xyz[ids],axis=0,return_inverse=True,return_counts=True)
    pairs=cKDTree(p).query_pairs(c['connectivity_m'],output_type='ndarray')
    graph=coo_matrix((np.ones(len(pairs),np.uint8),(pairs[:,0],pairs[:,1])),shape=(len(p),len(p)))
    nc,lab=connected_components(graph,directed=False)
    sizes=np.bincount(lab,weights=counts);chosen=int(np.argmax(sizes));take=lab==chosen;part=p[take];w=counts[take]
    center=np.average(part,axis=0,weights=w);anchor=part[np.argmin(np.linalg.norm(part-center,axis=1))]
    delta=part[:,:2]-center[:2];cov=(delta*w[:,None]).T@delta/w.sum()
    eigen,vec=np.linalg.eigh(cov);direction=vec[:,-1]
    if direction[np.argmax(abs(direction))]<0:direction=-direction
    if eigen[-1]<1e-12:direction=np.array([1.,0.])
    along=(part[:,:2]-anchor[:2])@direction;lo=float(along.min()-c['section_pad_m']);hi=float(along.max()+c['section_pad_m'])
    return dict(status='PASS',start=(anchor[:2]+lo*direction).tolist(),end=(anchor[:2]+hi*direction).tolist(),
        anchor_xyz=anchor.tolist(),half_width=c['half_width_m'],component_n_gt=int(sizes[chosen]),component_unique_points=int(take.sum()),
        components=int(nc),all_case2_n_gt=len(ids),rule='largest 0.6m-connected component of case-2 XYZ; size in inherited reference rows; weighted principal XY axis',
        direction_xy=direction.tolist(),length_m=hi-lo)

def main(site,prior):
    config=cfg();stem=f'{site}__{prior}';out=O/'scenes'/stem
    if (out/'complete.json').exists():print('REUSE_COMPLETE',stem);return
    out.mkdir(parents=True,exist_ok=True)
    if not (O/'first_calculation.json').exists():
        assert (D/'provenance/inputs.lock.json').exists()
        import scipy
        dump(O/'first_calculation.json',dict(at=now(),config_sha256=sha(C/'recount_v1.json'),python=sys.version,numpy=np.__version__,scipy=scipy.__version__,image=os.environ['RECOUNT_IMAGE'],scientific_verdict=None))
    start=time.monotonic();z=loadz(cells_path(site,prior));lab=z['score_cell_1p0'];own=z['row_owner'];xyz=z['xyz'];tau=z['row_tau_m'];good=own>=0
    core=loadz(JA/'core_points'/f'{stem}.npz',['source_index','patch_id','centre','normal'])
    target=loadz(FT/'targets'/f'{stem}.npz',['patch_id','judge_region','target_height_m'])
    ix=core['source_index'];assert np.array_equal(target['patch_id'][ix],core['patch_id'])
    region=target['judge_region'][ix];assert set(np.unique(region))<=set(REGIONS)
    judge=np.full(len(own),-1,np.int8);judge[good]=region[own[good]]
    rows=loadz(S1/'defs'/site/f'rows_{prior}.npz',['kind','thin']);kind=rows['kind'][rows['thin'].astype(bool)];assert len(kind)==len(lab)
    tr=next(r for r in readcsv(config['tau_source']) if r['site']==site and r['prior']==prior)
    expected_tau=np.where(kind==2,float(tr['wall_tau_m']),float(tr['roof_tau_m']))
    assert np.isfinite(tau[good]).all()
    assert np.array_equal(tau[np.isfinite(tau)],expected_tau[np.isfinite(tau)])
    expected=np.full(len(lab),-99,np.int8)
    for k,r in EXPECTED.items():expected[lab==k]=r
    eligible=good&np.isin(lab,list(EXPECTED));correct=eligible&(judge==expected)
    summary=[];confusion=[];consistency=[]
    for k in config['case_ids']:
        mask=good&(lab==k);n=int(mask.sum());num=int((mask&correct).sum())
        row=dict(site=site,prior=prior,cell_basis='score',case_id=k,case_name=CASES[k],n_gt=n,small='적음' if n<1000 else '',expected_judgment=REGIONS.get(EXPECTED.get(k),'없음'),accuracy_pct=pct(num,n) if k in EXPECTED else None)
        total=0.
        for r,name in REGIONS.items():
            count=int((mask&(judge==r)).sum());fraction=pct(count,n)
            row[name+'_n']=count;row[name+'_pct']=fraction;total+=fraction or 0.
        confusion.append(row)
        if n:assert abs(total-100)<1e-9
        for rule,pred in [('본 방법',None),('늘 보존',1),('늘 보정',2)]:
            cn=num if pred is None else n*int(EXPECTED.get(k)==pred)
            summary.append(dict(site=site,prior=prior,cell_basis='score',rule=rule,case_id=k,case_name=CASES[k],n_gt=n,small=row['small'],n_correct=cn if k in EXPECTED else None,accuracy_pct=pct(cn,n) if k in EXPECTED else None,status='둘 다 틀림: 셈 제외' if k==3 else 'PASS' if n else '확인 불가: 참값 점 없음'))
    for rule,pred in [('본 방법',None),('늘 보존',1),('늘 보정',2)]:
        n=int(eligible.sum());cn=int(correct.sum()) if pred is None else int((eligible&(expected==pred)).sum())
        summary.append(dict(site=site,prior=prior,cell_basis='score',rule=rule,case_id='all',case_name='전체(둘 다 틀림 제외)',n_gt=n,small='적음' if n<1000 else '',n_correct=cn,accuracy_pct=pct(cn,n),status='PASS' if n else '확인 불가: 참값 점 없음'))
    table(stem+'/judgment_matrix',confusion);table(stem+'/judgment_summary',summary)
    headers=['경우 (참값 채점 기준)','참값 점 수']+[name+' 점 수 (행 %)' for name in REGIONS.values()]+['맞음 %']
    lines=['# '+LABELS[site]+' '+prior+' · 경우 × 판단','', '경우: RELEASE 참값 점별 칸. 판단: FINALTRAIN 꼬리표. 둘 다 틀림은 맞음 계산에서 제외.','', '| '+' | '.join(headers)+' |','|'+'---|'*len(headers)]
    for r in confusion:
        vals=[r['case_name']+(' · 적음' if r['small'] else ''),str(r['n_gt'])]
        vals += [f"{r[name+'_n']} ({r[name+'_pct']:.6f}%)" if r[name+'_pct'] is not None else '0 (확인 불가)' for name in REGIONS.values()]
        vals += [f"{r['accuracy_pct']:.6f}" if r['accuracy_pct'] is not None else '셈 제외' if r['case_id']==3 else '확인 불가']
        lines.append('| '+' | '.join(vals)+' |')
    (D/'tables'/stem/'judgment_matrix.md').write_text('\n'.join(lines)+'\n')
    figure_scene=[site,prior] in config['figures']['scenes']
    section=choose_section(xyz,lab,config['figures']) if figure_scene else None
    if section:
        dump(out/'section.json',section)
        if section['status']=='PASS':
            target_xyz=core['centre']+target['target_height_m'][ix,None]*core['normal']
            target_xyz=target_xyz[np.isfinite(target_xyz).all(1)]
            savez(out/'section_points.npz',gt=section_points(xyz,section),target=section_points(target_xyz,section))
        else:issue(stem+' 단면 확인 불가: '+section['reason'])
    release_rows=[r for r in readcsv(config['table4_source']) if r['site']==site and r['prior']==prior and r['cell_basis']=='score' and float(r['tau_multiplier'])==1]
    split=[];offsets=[];walls=[];sensitivity=[];unassigned=None
    wall=(kind==2);print('SCENE',stem,'rows',len(lab),'wall',int(wall.sum()),flush=True)
    for method in METHODS:
        score=score_dir(site,prior,method);v=json.loads((score/'values.json').read_text())
        data=loadz(score/'points.npz',['row_distance_m','row_tau_m','row_owner']+(['scene_owner'] if method=='FINALTRAIN_30000' else []))
        assert np.array_equal(data['row_owner'],own)
        assert np.array_equal(data['row_tau_m'][good],tau[good],equal_nan=True)
        passed=data['row_distance_m']<=data['row_tau_m']
        if method=='FINALTRAIN_30000':
            savez(out/'reference_rows.npz',xyz=xyz,case_id=lab,judge_region=judge,eligible=eligible,judgment_correct=correct,result_pass=passed,row_kind=kind,row_owner=own)
            unassigned=dict(site=site,prior=prior,reference_rows=len(own),row_owner_missing=int((~good).sum()),prior_surface_absent_rows=int((lab==-1).sum()),
                prior_surface_absent_assigned_rows=int((good&(lab==-1)).sum()),both_wrong_rows=int((lab==3).sum()),
                judgment_denominator_rows=int(eligible.sum()),scene_reference_points=len(data['scene_owner']),scene_owner_missing=int((data['scene_owner']<0).sum()),
                scene_count_note='scorer scene_owner is inherited scene population; it is separate from table4 thin reference-row counts')
        for k in CASES:
            m=lab==k;n=int(m.sum());row=next(r for r in release_rows if r['method']==method and int(r['cell'])==k)
            comp=float(passed[m].mean()) if n else None;old=float(row['completeness']) if row['completeness'] else None
            delta=abs(comp-old)*100 if n else None
            assert n==int(row['n_gt']);assert delta is None or delta<=config.get('match_tolerance_pp',.1)
            consistency.append(dict(site=site,prior=prior,method=method,case_id=k,n_gt=n,release_n_gt=int(row['n_gt']),recount_completeness=comp,release_completeness=old,delta_pp=delta,status='PASS'))
        if method in ['FINALTRAIN_30000','baseline_30000','judgment_mesh']:
            for k in EXPECTED:
                for ok in [True,False]:
                    m=eligible&(lab==k)&(correct==ok);n=int(m.sum())
                    split.append(dict(site=site,prior=prior,cell_basis='score',case_id=k,case_name=CASES[k],judgment_result='맞음' if ok else '틀림',method=method,method_name=NAMES[method],n_gt=n,n_within_tau=int(passed[m].sum()),completeness_pct=pct(passed[m].sum(),n),small='적음' if n<1000 else ''))
        if method in config['offsets']['methods']:
            for k,field in [(1,'prior_distance_m'),(2,'mvs_distance_m')]:
                distance=z[field]
                for lo,hi in zip([0.,.5,1.,2.,4.],[.5,1.,2.,4.,np.inf]):
                    m=(lab==k)&((distance>lo) if lo==4 else (distance>=lo))&((distance<=hi) if hi==4 else (distance<hi) if np.isfinite(hi) else (distance<=hi))
                    n=int(m.sum());offsets.append(dict(site=site,prior=prior,cell_basis='score',case_id=k,case_name=CASES[k],distance_source=field,lower_m=lo,upper_m=None if not np.isfinite(hi) else hi,lower_inclusive=lo!=4,upper_inclusive=hi==4 or not np.isfinite(hi),method=method,method_name=NAMES[method],n_gt=n,n_within_tau=int(passed[m].sum()),completeness_pct=pct(passed[m].sum(),n),small='적음' if n<1000 else '',nonfinite_distance_rows=int((m&~np.isfinite(distance)).sum())))
        wallids=np.flatnonzero(wall&passed);cache=out/(method+'_wall_3d.npz');secfile=out/(method+'_section.npz')
        need_wall=len(wallids)>0 and not cache.exists()
        need_section=figure_scene and section['status']=='PASS' and method in ['prior','mvs','FINALTRAIN_30000','baseline_30000'] and not secfile.exists()
        if need_wall or need_section:
            V,F=read_surface(v['mesh'])
            if need_wall:
                scene=MeshScene(V,F);q,d3=closest(scene,xyz[wallids]);savez(cache,row_index=wallids,distance_3d_m=d3,nearest_xyz=q);del scene,q,d3;gc.collect()
            if need_section:savez(secfile,segments=section_segments(V,F,section))
            del V,F;gc.collect()
        far=np.zeros(len(lab),bool)
        if len(wallids):
            w=loadz(cache);assert np.array_equal(w['row_index'],wallids);far[wallids]=w['distance_3d_m']>1.
        for k in CASES:
            m=lab==k;wm=m&wall;pm=wm&passed;n=int(m.sum());nw=int(wm.sum());npas=int(pm.sum());nf=int((m&far).sum())
            ratio=pct(nf,npas);qualify=k in config['case_ids'] and n>=1000
            walls.append(dict(site=site,prior=prior,cell_basis='score',case_id=k,case_name=CASES[k],method=method,method_name=NAMES[method],n_gt=n,n_wall=nw,n_wall_within_tau=npas,n_wall_within_tau_farther_1m=nf,farther_1m_pct=ratio,small='적음' if n<1000 else '',trigger_eligible=qualify,exceeds_2pct=bool(qualify and ratio is not None and ratio>2),wall_n_at_least_1000=nw>=1000,status='PASS' if npas else '해당 없음: 벽 τ 안 점 없음'))
            sensitivity.append(dict(site=site,prior=prior,cell_basis='score',case_id=k,case_name=CASES[k],method=method,method_name=NAMES[method],n_gt=n,n_wall=nw,n_pass=int((m&passed).sum()),n_removed_by_3d=nf,completeness_original_pct=pct((m&passed).sum(),n),completeness_wall_3d_1m_pct=pct((m&passed&~far).sum(),n),wall_completeness_original_pct=pct(npas,nw),wall_completeness_3d_1m_pct=pct(npas-nf,nw),small='적음' if n<1000 else ''))
        print('METHOD_COMPLETE',stem,method,'wall accepted',len(wallids),flush=True)
        del data;gc.collect()
    for name,values in [('reproduction',consistency),('result_by_judgment',split),('offset_bins',offsets),('wall_check',walls),('wall_sensitivity_candidate',sensitivity),('unassigned',[unassigned])]:table(stem+'/'+name,values)
    dump(out/'complete.json',dict(at=now(),seconds=time.monotonic()-start,status='PASS',scientific_verdict=None))
    print('SCENE_COMPLETE',stem,flush=True)

if __name__=='__main__':main(*sys.argv[1:])
