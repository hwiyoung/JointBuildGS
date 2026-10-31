"""Independent joins, NumPy medians, conserved area and precision sensitivity."""
from cp2_common import *
AC=module('cp2_photo_validation_analysis','/repo/scripts/phd/main_judgenum_v1/analysis_core.py')

def main():
    assert json.loads((OUT/'photo_dl/complete.json').read_text())['new_images_processed']==0
    checks=[];precision=[]
    for prior in ['ALS','LoD2']:
        parts=[];samples=0
        for newpath in sorted((OUT/'photo_dl/core_points').glob(f'*__{prior}.npz')):
            d=arrays(newpath)
            with np.load(JN/'core_points'/newpath.name) as z:
                for k in ['patch_id','area','cell','building','judgment_after','DL_cm','d_mean_cm']:
                    assert np.array_equal(d[k],z[k],equal_nan=True) if d[k].dtype.kind=='f' else np.array_equal(d[k],z[k]),k
            for pid in sorted(set(d['photo_point_id']))[::max(1,len(set(d['photo_point_id']))//10)]:
                if not pid:continue
                m=d['photo_point_id']==pid
                # Roof and wall point IDs can coincide: keep separate kind identities.
                for kind in set(d['kind'][m]):
                    q=m&(d['kind']==kind);v=d['DL_cm'][q];v=v[np.isfinite(v)]
                    expected=np.median(v)/100 if len(v) else np.nan
                    assert np.allclose(d['point_DL_m'][q],expected,equal_nan=True,rtol=0,atol=1e-12)
                    samples+=1
            parts.append(d)
        d={k:np.concatenate([p[k] for p in parts]) for k in parts[0]}
        result=json.loads((OUT/'photo_dl'/f'{prior}_selection.json').read_text())['groups']
        for group,kind in [('roof',1),('wall',2)]:
            m=d['kind']==kind
            if not m.any():continue
            original=dict(d,photo_judgments=d['old_photo_judgments'])
            replay=dict(d,photo_judgments=d['old_range_replay'])
            index=result[group]['old_choice_index'];pi=index//9
            original_summary=AC.summaries(original,d['judgment_after'],d['d_mean_cm']/100,index,m)[1]
            replay_summary=AC.summaries(replay,d['judgment_after'],d['d_mean_cm']/100,index,m)[1]
            chosen=AC.select(replay,d['judgment_after'],d['d_mean_cm']/100,m)
            changed=m&(d['judgment_after']==1)&(d['old_photo_judgments'][:,pi]!=d['old_range_replay'][:,pi])
            precision.append(dict(prior=prior,group=group,old_choice_index=index,replay_choice_index=chosen['best'],
                original_wrong_area_m2=original_summary['wrong_area_m2'],old_range_replay_wrong_area_m2=replay_summary['wrong_area_m2'],
                difference_m2=replay_summary['wrong_area_m2']-original_summary['wrong_area_m2'],
                changed_at_old_selected_photo_area_m2=float(d['area'][changed].sum())))
            observed=AC.select(d,d['judgment_after'],d['d_mean_cm']/100,m)
            assert observed['best']==result[group]['choice_index']
            assert np.allclose(observed['errors'],result[group]['grid_wrong_area_m2'],rtol=0,atol=1e-8)
        checks.append(dict(prior=prior,patches=len(d['area']),area_m2=float(d['area'].sum()),independent_DL_point_samples=samples,
            original_judgment_after_unchanged=True,new_selection_reproduced=True))
    transition=json.loads((DOC/'tables/photo_834_transition.json').read_text())['rows']
    for rule in {r['rule'] for r in transition}:assert abs(sum(r['area_m2'] for r in transition if r['rule']==rule)-834.4375)<1e-10
    table('photo_precision_sensitivity',precision)
    table('photo_validation',checks,status='PASS_WITH_REPORTED_FLOAT16_LIMITATION')
    print('PHOTO_VALIDATION_PASS',checks,flush=True)

if __name__=='__main__':main()
