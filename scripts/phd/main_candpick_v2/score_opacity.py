"""Original four outcomes plus predeclared relative-opacity and coverage statistics."""
from cp2_common import *

def main():
    cfg=config();rows=[];curves=[];status=[];normal_rows=[]
    for unit in UNITS:
        d=arrays(CP1/'places'/(unit+'.npz'));ix=np.arange(len(d['area']));ri=(d['right']=='image').astype(int)
        fi=(d['mvs_p']>0).astype(int)
        for variant in ['v1','a','b','c','d']:
            for start in ['equal','right']:
                baseline=variant=='v1';arm=f'cp_{start}_sh3_{unit}' if baseline else f'cp2_{variant}_{start}_{unit}'
                source=(CP1 if baseline else OUT)/'runs'/arm
                if not (source/'complete.json').exists():
                    status.append(dict(arm=arm,status='UNAVAILABLE_NO_COMPLETE_TRAINING'));continue
                receipt=json.loads((source/'complete.json').read_text());end=receipt['iterations']
                assert sha(source/f'candidate_{end}.npz')==receipt['final_candidate_sha256']
                with np.load(source/f'candidate_{end}.npz') as z:
                    pair=z['opacity'].reshape(-1,2,4).mean(2) if baseline else z['opacity_pair'].mean(2)
                right=pair[ix,ri];wrong=pair[ix,1-ri];diff=right-wrong;both=1-(1-right)*(1-wrong)
                flags=dict(right_only=(right>=.5)&(wrong<.5),wrong_only=(right<.5)&(wrong>=.5),
                    both=(right>=.5)&(wrong>=.5),neither=(right<.5)&(wrong<.5),right_darker=diff>.2,wrong_darker=diff<-.2,
                    relative_tie=(diff>=-.2)&(diff<=.2))
                for group in ['a','b','c']:
                    for side in ['all','front','back']:
                        m=d['group']==group
                        if side!='all':m&=d['side']==side
                        area=float(d['area'][m].sum());r=dict(arm=arm,unit=unit,variant=variant,start=start,group=group,side=side,
                            points=int(m.sum()),area_m2=area,
                            mean_right_minus_wrong=float(diff[m].mean()) if m.any() else None,
                            front_opacity_median=float(np.median(pair[ix,fi][m])) if m.any() else None,
                            back_opacity_median=float(np.median(pair[ix,1-fi][m])) if m.any() else None,
                            combined_coverage_median=float(np.median(both[m])) if m.any() else None)
                        for label,q in flags.items():
                            a=float(d['area'][m&q].sum());r[label+'_area_m2']=a;r[label+'_fraction']=a/area if area else None
                        rows.append(r)
                for line in (source/'metrics.jsonl').read_text().splitlines():
                    log=json.loads(line)
                    for q in log['opacity']:curves.append(dict(arm=arm,unit=unit,variant=variant,start=start,iteration=log['iteration'],**q))
                status.append(dict(arm=arm,status='COMPLETE',iterations=end,seconds=receipt['elapsed_seconds'],
                    trainable_background_gaussians=receipt.get('trainable_background_gaussians',0)))
                if variant=='c':
                    with np.load(source/'normal_displacement.npz') as z:displacement=z['normal_displacement_m']
                    for ci,label in enumerate(['prior','image']):
                        q=np.quantile(displacement[:,ci,:],[0,.05,.25,.5,.75,.95,1])
                        normal_rows.append(dict(arm=arm,unit=unit,start=start,candidate=label,
                            **dict(zip(['min_m','p05_m','p25_m','median_m','p75_m','p95_m','max_m'],q))))
    baselines={(r['unit'],r['start'],r['group'],r['side']):r for r in rows if r['variant']=='v1'}
    for r in rows:
        b=baselines[r['unit'],r['start'],r['group'],r['side']]
        for k in ['right_darker_fraction','right_only_fraction','combined_coverage_median']:
            r[k+'_minus_v1']=r[k]-b[k] if r[k] is not None and b[k] is not None else None
    table('opacity_outcomes',rows);table('opacity_curves',curves);table('training_status',status);table('normal_displacement_distribution',normal_rows)
    depth=[]
    for p in sorted((OUT/'depth').glob('*/complete.json')):depth+=json.loads(p.read_text())['rows']
    table('depth_outcomes',depth)
    from update_progress import main as update_progress
    update_progress()
    print('scored',len(status),'planned/baseline arms;',len(depth),'depth rows',flush=True)

if __name__=='__main__':main()
