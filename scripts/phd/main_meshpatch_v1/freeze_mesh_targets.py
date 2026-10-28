"""Bind every requested physical mesh before cleanup; never infer a missing run."""
from mesh_common import *
def main():
    p=C/'mesh_targets_v1.json';assert not p.exists(),p
    targets={}
    for site in ['B173nb_b10','B0_b10','R1rep_b10']:
        for group,prior,methods in [('losstrain','ALS',['nojudge_ALS_s0','prop_ALS_s0','lt_fixgt_ALS_s0','lt_dyngt_ALS_s0','lt_dynsoft_ALS_s0','lt_dynnow_ALS_s0'])]+[
            ('stage1',pr,[f'prop_{pr}_s0',f'prop_{pr}_s1','imgonly_s0','imgonly_2dgs_s0','geogs_ALS_fix1' if pr=='ALS' else 'trust_LoD2_fix1']+(['trust_ALS'] if pr=='ALS' else [])) for pr in ['ALS','LoD2']]:
            for res in methods:
                key=f'{site}__{prior}__{res}'
                if key in targets:targets[key]['groups'].append(group);continue
                f,info=resolve(site,prior,res);e=LT/'direct_stage1_v2'/f'{site}__{prior}'/'evaluation.npz';v=e.with_name('values.npz')
                row=dict(key=key,site=site,prior=prior,result=res,groups=[group],mesh=str(f),exists=f.is_file(),evaluation=str(e),values=str(v),**info)
                if site=='R1rep_b10' and res=='lt_fixgt_ALS_s0':row.update(status='UNAVAILABLE_FROZEN_STOP',reason='Previously stopped arm; preserve frozen health status even if partial files exist.')
                elif not f.is_file():row.update(status='UNAVAILABLE',reason='mesh absent')
                elif not e.exists() or not v.exists():row.update(status='UNAVAILABLE',reason='canonical evaluation inputs absent')
                else:
                    row.update(status='READY',bytes=f.stat().st_size,sha256=sha(f),evaluation_sha256=sha(e),values_sha256=sha(v))
                    if 'expected_sha256' in info:assert row['sha256']==info['expected_sha256'],key
                targets[key]=row;print(key,row['status'],flush=True)
    upstream=O/'received/geogs_original/utils/mesh_utils.py'
    cfg=dict(task_id='PHD-MAIN-MESHPATCH-v1',frozen_at=now(),targets=list(targets.values()),source_function=dict(path=str(upstream),sha256=sha(upstream),name='post_process_mesh',kwargs=dict(cluster_to_keep=50)),
        clarification='The logical ours_ALS_s0 placeholder in the initial scope resolves to the existing prop_ALS_s0, as specified by source LOSSTRAIN records; no new result is invented.',
        removed_area_assignment=dict(rule='Triangle centroid -> nearest existing patch in XY within sqrt(2)*0.25 m, matching FLOATDIAG display join radius; restricted to eligible roof patches (normal abs(z)>=cos45). Categories use the BEFORE first-hit classification of that patch. Unmatched, outside-evaluation or wall geometry is separately unavailable, never hidden in other_missing.',
            max_distance_xy_m=2**.5*.25,category_names=CATEGORIES,area='Actual 3D triangle area, not patch area; category assignment is a declared spatial association, not independent truth.'),
        metrics='First-hit code copied unchanged from mesh_score.py. Stage1 spread/completeness functions reused; F1 uses unchanged bsurf, density400/seed0 and cloud.chamfer_pcf. No M3C2 recalculation requested.',
        figures=dict(source='configs/phd/main_floatdiag_v1/geometry_<site>_ALS.json',cameras='All seven frozen cameras per case',colour='Exact FLOATDIAG face_colours',before_after=['nojudge_ALS_s0','lt_dynnow_ALS_s0']),scientific_verdict=None)
    dump(p,cfg);dump(C/'mesh_targets_v1.lock.json',dict(sha256=sha(p),before_first_mesh_cleanup=True,frozen_at=now(),scientific_verdict=None))
    dump(D/'tables/mesh_inventory.json',dict(rows=list(targets.values()),scientific_verdict=None))
if __name__=='__main__':main()
