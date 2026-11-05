"""Lock configuration and exact existing inputs before any new numerical work."""
from common import *
assert not (C/'recount_v1.json').exists(), 'Already frozen'
config=dict(task_id='PHD-MAIN-RECOUNT-v1',created_at=now(),source_commit=os.environ['RECOUNT_COMMIT'],
    scientific_verdict=None,crs='EPSG:25832',local_xy_offset_m=[690953.,5336071.],
    sites=SITES,priors=PRIORS,methods=METHODS,case_ids=list(CASES)[:-1],judgment_ids=list(REGIONS),
    cases=CASES,judgments=REGIONS,exact_expected=EXPECTED,small_n=1000,tau_multiplier=1,
    table4_source='/repo/docs/experiments/phd/main_release_v1/tables/stage0/table4_all.csv',
    tau_source='/repo/docs/experiments/phd/main_release_v1/tables/stage0/tau_values.csv',
    cell_basis='score',cells='saved RELEASE score_cell_1p0; no reconstruction',
    unit='inherited RESCORE thin reference rows, unchanged multiplicity and row_owner',
    judgment_join='FINALTRAIN judge_region[JA source_index][row_owner]; assert exact patch_id',
    denominator='assigned rows in cases 0,1,2,4; all six judgment labels included; case 3 and -1 counts separate',
    best_excludes=['prior','mvs','judgment_mesh'],summary_cases=[0,1,2,4,3],
    summary_metrics=['completeness','accuracy'],summary_small_cells_excluded=True,gap='eligible best minus method, percentage points; not clamped',
    offsets=dict(edges_m=[0,.5,1,2,4,None],intervals=['[0,0.5)','[0.5,1)','[1,2)','[2,4]','(4,inf]'],
        methods=['prior','mvs','fusion','baseline_30000','GeoGS_30000','judgment_mesh','FINALTRAIN_30000'],
        distance='saved RELEASE prior_distance_m for case 1, mvs_distance_m for case 2'),
    wall=dict(kind_source='S1 defs rows_PRIOR.npz kind[thin]',
        nearest_point='nearest point on exact scored result triangle surface, inherited closest()',
        distance_3d_m=1.,trigger_pct=2.,trigger_min_n_gt=1000,
        ratio_denominator='wall reference rows accepted by original tau',
        scope='all five cases and all nine methods; unassigned separate',
        sensitivity='if any qualifying cell exceeds 2%, add d3d<=1 m to walls only; original scores unchanged'),
    figures=dict(scenes=[['B173nb_b10','ALS'],['B173nb_b10','LoD2'],['R1rep_b10','ALS']],
        maps='three top XY reference-row maps per scene; case, exact judgment correctness, FINALTRAIN within tau',
        section='one per scene through largest case-2 0.6m-connected reference-point component; count-weighted major XY axis; anchor is member nearest centroid',
        connectivity_m=.6,half_width_m=.6,section_pad_m=2.,
        section_geometry='reuse RESCORE exact triangle-plane intersection; target centre+height*normal; no rendering',
        map_colors={'0':'#92948d','1':'#0072B2','2':'#D55E00','4':'#CC79A7','3':'#332c50','-1':'#dddddd'},
        status_colors={'correct':'#66645e','wrong':'#0072B2','excluded':'#dddddd'}),
    execution=dict(image=os.environ['RECOUNT_IMAGE'],cpu_only=True,nice=19,cpus=6,memory_gib=32,training=False,render=False,mesh_generation=False),
    output_paths=['configs/phd/main_recount_v1/','scripts/phd/main_recount_v1/','docs/experiments/phd/main_recount_v1/',
                  'PH/main_recount_v1/PHD-MAIN-RECOUNT-v1/'],
    PH_resolution='/art/phase-payloads/phd = ../JointBuildGS-artifacts/phase-payloads/phd',
    checks=['precalculation_lock','RELEASE_match_within_0.1pp','exact_judgment','row_percent_sums_100','no_training_render_mesh','writes_in_scope'])
dump(C/'recount_v1.json',config)
dump(C/'recount_v1.initial.lock.json',dict(locked_at=now(),config_sha256=sha(C/'recount_v1.json'),first_calculation_started=False,scientific_verdict=None))
sources=set([Path(config['table4_source']),Path(config['tau_source']),D/'provenance/order_v1.txt'])
for rel in ['scripts/phd/main_release_v1/stage0.py','scripts/phd/main_rescore_v1/score_mesh.py','scripts/phd/main_rescore_v1/geometry.py','scripts/phd/main_rescore_v1/metrics.py','scripts/phd/main_rescore_v1/surface_tau.py','scripts/phd/main_rescore_v1/target_quality.py','scripts/phd/main_rescore_v1/figures.py','scripts/phd/main_rescore_v1/choose_places.py','scripts/phd/main_dist71_v1/dm_common.py','src/phd/metrics_v3/surface.py','configs/phd/main_rescore_v1/rescore_v1.json','configs/phd/main_finaltrain_v1/finaltrain_v1.json','configs/phd/main_release_v1/release_v1.json']:
    sources.add(R/rel)
meshes={}
for site in SITES:
    for prior in PRIORS:
        stem=f'{site}__{prior}'
        sources.update([cells_path(site,prior),FT/'targets'/f'{stem}.npz',JA/'core_points'/f'{stem}.npz',S1/'defs'/site/f'rows_{prior}.npz'])
        for method in METHODS:
            root=score_dir(site,prior,method);sources.update([root/'points.npz',root/'values.json'])
            value=json.loads((root/'values.json').read_text());mesh=Path(value['mesh']);sources.add(mesh);meshes[str(mesh)]=value['mesh_sha256']
rows=[]
for p in sorted(sources):
    h=sha(p)
    if str(p) in meshes:assert h==meshes[str(p)],f'Mesh changed: {p}'
    rows.append(dict(path=str(p),bytes=p.stat().st_size,sha256=h))
    print('LOCK_INPUT',p,flush=True)
dump(D/'provenance/inputs.lock.json',dict(at=now(),sources=rows,scientific_verdict=None))
(D/'issues.md').write_text('# 실행 기록과 정의 적용\n\n'
'- 발주문의 PH는 저장소 manifest에 따라 외부 phase-payloads/phd로 해석했다. 재실행 경로 문서의 실제 위치는 docs/experiments/phd/main_rescore_v1/addendum3_stage1/재실행_경로.md다.\n'
'- RELEASE의 저장된 참값 행, 기둥 소속, score_cell_1p0를 그대로 쓴다. 물리 점의 재중복 제거를 하지 않는다. 경우 -1(사전 정보 면 없음)과 미소속은 별도 수로 남긴다.\n'
'- RELEASE 경우 4는 MVS 기둥 면 없음이면서 사전 정보가 τ 안인 행이다. MVS 면 없음·사전 정보 τ 밖은 원래 경우 3 그대로 유지한다.\n'
'- 3차원 벽 거리는 원 채점기의 최근접 삼각형 표면점 정의를 따르며, 저장되지 않은 경우에만 계산한다. 샘플 점/정점으로 대체하지 않는다.\n'
'- 최대 차이 요약은 요청된 다섯 경우의 n_gt≥1,000 칸을 쓴다. 완전성과 정확성을 각각 저장하고 보고서 앞에는 완전성을 제시한다.\n'
'- 단면은 기존 0.6 m 연결·폭 규칙을 참값 점에 적용하고 가장 큰 모임의 주축을 사용한다. 결과값으로 위치를 고르지 않는다.\n')
print('FROZEN',sha(C/'recount_v1.json'),len(rows),flush=True)
