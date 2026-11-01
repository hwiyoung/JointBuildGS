"""Validate actual periodic health and memory records from both independent arms."""
from common import *

def read(p):return json.loads(p.read_text())

def main():
    expected={f'tg_B173nb_b10_{p}_s0_r8' for p in ['ALS','LoD2']}
    assert {p.name for p in (OUT/'r8/runs').iterdir() if p.is_dir()}==expected
    rows=[]
    for prior in ['ALS','LoD2']:
        root=OUT/'r8/runs'/f'tg_B173nb_b10_{prior}_s0_r8'
        mon=root/'model/target_monitor'
        curve=[json.loads(x) for x in (mon/'curve.jsonl').read_text().splitlines()]
        memory=[json.loads(x) for x in (mon/'memory_1000.jsonl').read_text().splitlines()]
        expected_steps=[r['iteration'] for r in curve if r['iteration']%1000==0]
        assert [r['iteration'] for r in memory]==expected_steps
        by_step={r['iteration']:r for r in curve}
        for r in curve:
            assert sum(r['tags'].values())==r['gaussians']
            last=r['last_opacity_reset'];grace=last>=0 and 0<=r['iteration']-last<=500
            assert grace==r['opacity_check_skipped_reset_grace']
        for r in memory:
            c=by_step[r['iteration']]
            assert r['gaussians']==c['gaussians'] and r['tags']==c['tags']
            assert r['allocated_bytes']<=r['peak_allocated_bytes'] and r['reserved_bytes']<=r['peak_reserved_bytes']
            if r['iteration']>=7000:
                assert r['count_at_6000']==by_step[6000]['gaussians']
                if r['gaussians']>3*r['count_at_6000']:
                    assert read(mon/'STOP.json')['reason']=='count_gt_3x_6000'
                    assert (OUT/'r8'/f'STOP_{prior}.json').exists()
        receipt=root/'receipt.json'
        if receipt.exists() and read(receipt)['status']=='TRAINING_COMPLETE_30000':assert expected_steps==list(range(1000,30001,1000))
        rows.append(dict(prior=prior,last_iteration=curve[-1]['iteration'],memory_steps=expected_steps,count_reference=by_step.get(6000,{}).get('gaussians'),stop_exists=(OUT/'r8'/f'STOP_{prior}.json').exists()))
    result=dict(at=stamp(),status='PASS_ACTUAL_HEALTH_RECORDS',rows=rows,other_six='NOT_STARTED',scientific_verdict=None)
    dump(OUT/'r8/verification/health_records.json',result)
    print(result['status'],flush=True)

if __name__=='__main__':main()
