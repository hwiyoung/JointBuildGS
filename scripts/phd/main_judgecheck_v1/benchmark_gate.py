"""Apply the ordered 200-point linear timing estimator; preserve its limits."""
import json,os,platform,csv
import numpy as np
import scipy,torch
from preflight import C,D,O,Path,sha,dump,now
BASE=O/'r1';P=BASE/'photo_benchmark'

def main():
    sample=json.loads((BASE/'photo_benchmark_selection.json').read_text());prep=json.loads((P/'preparation.json').read_text())
    cpu=json.loads((P/'timing_cpu.json').read_text());gpu=json.loads((P/'timing_cuda.json').read_text())
    assert sample['sample_count']==cpu['points']==gpu['points']==prep['points']==200
    with np.load(P/'scores_cpu.npz') as a,np.load(P/'scores_cuda.npz') as b:
        differences={}
        for name in ['curves','best_score','texture','texture_by_view']:
            x=a[name];y=b[name];assert np.array_equal(np.isfinite(x),np.isfinite(y)),name
            valid=np.isfinite(x);err=float(np.max(abs(x[valid]-y[valid]))) if valid.any() else 0.
            tolerance=2e-4 if name.startswith('texture') else 2e-5
            assert err<tolerance,(name,err);differences[name]=dict(finite_count=int(valid.sum()),max_absolute_difference=err,tolerance=tolerance)
        assert np.array_equal(a['valid_image_count'],b['valid_image_count'])
        assert np.array_equal(a['pyramid_levels'],b['pyramid_levels'])
    n=sample['target_count_lower_bound'];rows=[]
    for device,t,limit in [('cpu',cpu,72),('cuda',gpu,48)]:
        seconds=prep['total_seconds']+t['total_seconds'];hours=seconds/200*n/3600
        rows.append(dict(device=device,points=200,target_count_types_1_2=n,target_type3_pending=True,
            preparation_seconds=prep['total_seconds'],scoring_seconds=t['total_seconds'],
            total_seconds=seconds,seconds_per_point=seconds/200,linear_estimate_hours=hours,limit_hours=limit,
            over_limit=hours>limit,score_only_linear_hours=t['total_seconds']/200*n/3600,
            decoding_only_linear_hours=t['decode_seconds']/200*n/3600,
            arithmetic_only_linear_hours=t['arithmetic_seconds']/200*n/3600))
    stopped=any(r['over_limit'] for r in rows)
    result=dict(at=now(),status='STOP_PHOTO_TIME_ESTIMATE' if stopped else 'PASS_PHOTO_TIME_ESTIMATE_TYPES_1_2',
        ordered_rule='order_v1.txt sections 1.12 and 4.5: random 200-point elapsed time / 200 * target count',
        scope='Development only; timing sample from target types 1/2. Type 3 not yet counted or evaluated.',
        denominator_note='Target count is a lower bound; elapsed-time extrapolation is an estimate, not a proven runtime lower bound.',
        preparation_note='CPU plane fitting, masks, raw tile loading and KD-tree construction, and MVS camera selection are part of corrected photo preparation. Same preparation is used in both modes.',
        amortization_limitation='The prescribed simple multiplication also repeats shared tile/tree and image decoding overhead. Full-area image/tile batching may reduce it. No optimized full-area runtime has been measured; score-only timing excludes required plane/mask/visibility work.',
        gpu_choice='GPU 1, RTX 3090; no other research compute process at launch; desktop encoder left running on GPU 0',
        gpu_wait_for_other_job_seconds=0,own_serial_queue_wait_not_gpu_contention=True,
        rows=rows,parity=dict(status='PASS_CPU_GPU_PHOTO_PARITY',fields=differences,valid_counts_and_levels_equal=True),
        exclusions=dict(label='실험 지역과 사진 점을 공유해 뺀 핵심점',count=73,area_m2=5.442552935831812),
        environment=dict(python=platform.python_version(),numpy=np.__version__,scipy=scipy.__version__,torch=torch.__version__,
            commit=os.environ.get('JUDGECHECK_COMMIT'),image=os.environ.get('JUDGECHECK_IMAGE'),cpu_limit=4,memory_limit_gib=32,nice=19),
        input_sha256={p.name:sha(p) for p in [P/'planes.npz',P/'preparation.json',P/'scores_cpu.npz',P/'scores_cuda.npz',P/'timing_cpu.json',P/'timing_cuda.json']},
        report_a_complete=False,truth_used=False,holdout_values_opened=False,training=False,scientific_verdict=None)
    dump(BASE/'photo_time_gate.json',result);dump(D/'tables/photo_time_gate_reply1.json',result)
    with (D/'tables/photo_time_gate_reply1.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['row_type']+list(rows[0])+['excluded_core_count','excluded_area_m2']);writer.writeheader()
        writer.writerows(dict(row_type='measurement',**r) for r in rows)
        writer.writerow(dict(row_type='excluded_shared_photo_cores',excluded_core_count=73,excluded_area_m2=5.442552935831812))
    dump(C/'photo_time_gate.reply1.lock.json',dict(at=now(),gate_sha256=sha(BASE/'photo_time_gate.json'),
        source_sha256=sha(Path(__file__)),config_sha256=sha(C/'judgecheck_v1.json'),scientific_verdict=None))
    print(json.dumps(dict(status=result['status'],rows=rows,parity=result['parity']),ensure_ascii=False))

if __name__=='__main__':main()
