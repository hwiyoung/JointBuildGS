"""Lock task scope and exact input bytes before segmentation or rescoring."""
import hashlib,json
from pathlib import Path
from datetime import datetime,timezone,timedelta
PH=Path('/ph'); O=Path('/out'); R=Path('/repo'); C=Path('/config')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(2**20),b''):h.update(b)
    return h.hexdigest()
W=PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2'
S=PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1'
files=sorted((W/'patch_values').glob('*__*__R1.5.npz'))
files+=sorted((S/'regions_v3').glob('regions_ext_v3_*.npz'))
files+=sorted(p for p in (O/'received').rglob('*') if p.is_file())
files+=[R/'configs/phd/main_widen0_v2/widen0_v2.json',PH/'main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1/step01/ranges.json',PH/'main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1/step06/boxes_v1.json']
manifest=[dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)) for p in files]
cfg=dict(task_id='PHD-MAIN-MESHPATCH-v1',scientific_verdict=None,training=False,device='CPU',crs='EPSG:25832',
    priority=['task3','task1','task2_losstrain','task2_stage1'],
    requested_order_override='User explicitly requests task 3 first; supersedes attachment addendum order.',
    source_scope='All public patch_values; 24 files per prior, 21 nonempty tiles and 3 empty. Sealed holdout directory is excluded.',
    frame=json.loads((R/'configs/phd/main_widen0_v2/widen0_v2.json').read_text())['frame'],
    patches=dict(order='sorted NPZ filename then original row order',preserve=['patch_id','centre','normal','area','building','roof_type','kind','roof_like','face_ext','cell'],
        numerical_prep='Exact scripts_v1/prep.py conversion: non-centre float64 -> float32 only for track-A calculation; exported source columns retain original precision.'),
    mvs_segmentation=dict(source='received/track_a_v3/scripts/roofer_like.py and planeseg.py',key='roofer_def',graph_radius_m=.36,curvature_k=16,curvature_percentile=90,normal_dot=.75,plane_distance_m=.3,min_plane_points=15,
        exact_source_note='Actual attached graph/curvature/seed/leftover rules govern; no replacement with a generic k15 implementation.',
        no_mvs_export=-1,keep_raw_analysis_unit=True,
        types='Apply elem_types.py thresholds and precedence to roofer_def. Also reproduce original mvsshape_10 and its types in separate columns.',
        checks=['faces_per100','area_in_faces_ge1m2','roofwall_join','mix_face','split_face','cases'],
        benchmark='results/{prior}_evalseg.json roofer_def and mvsshape_10',ratio_tolerance_pp=.5,face_count_tolerance=0),
    regions=dict(codes=[2,3,4,5,11,12,13,14],source='S1/regions_v3/code_ext_v3',
        rule='Transfer only proven matching source patches; source code 0/-1 or missing input stays unavailable. Do not infer seeing-photo count from mvs_a_views.',
        identity_gate='same original surface geometry and patch support; distance alone cannot establish identity',
        missing_visibility='No new visibility calculation without user authorization; quantify unavailable area.',
        comparison_tolerance_pp=.5,overlap='Separate per-evaluation-region columns; combined field only if available labels agree.',
        exploration_names=['R1','R2','R3','R4','R5','B0','SW','R3E']),
    mesh=dict(function='GeoGS original post_process_mesh',cluster_to_keep=50,min_triangles=50,whole_unit_before_crop=True,
        targets_losstrain=dict(sites=['B0_b10','B173nb_b10','R1rep_b10'],prior='ALS',runs=['nojudge_ALS_s0','ours_ALS_s0','lt_fixgt_ALS_s0','lt_dyngt_ALS_s0','lt_dynsoft_ALS_s0','lt_dynnow_ALS_s0']),
        targets_stage1='Both ours seeds, image-only, 2DGS, GeoGS (fixed GeoGS for LoD2), trust-prior for ALS; six units; frozen or absent runs remain unavailable.',
        resource_gate='Shared LOSSTRAIN TSDF lock; MemAvailable >=56 GiB for 60s; container max40GiB/8CPUs; no GPU'),
    schedule_kst=['2026-10-28T23:00:00+09:00','2026-10-29T09:00:00+09:00','2026-10-29T14:00:00+09:00','2026-10-29T18:00:00+09:00','2026-10-30T09:30:00+09:00'],
    final_target_kst='2026-10-30T12:00:00+09:00',inputs=manifest)
dest=C/'meshpatch_v1.json'
assert not dest.exists(),'configuration already frozen; preserve it'
dest.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n')
(C/'meshpatch_v1.lock.json').write_text(json.dumps(dict(task_id=cfg['task_id'],frozen_at=datetime.now(timezone(timedelta(hours=9))).isoformat(),sha256=sha(dest),before_first_calculation=True,scientific_verdict=None),indent=2)+'\n')
print('FROZEN',sha(dest),'inputs',len(manifest))
