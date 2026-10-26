"""Apply only the frozen PSNR and centre-gradient selection rule after all four runs."""
import csv
import json
import shutil
from datetime import datetime,timezone,timedelta
from pathlib import Path
import numpy as np
from inputs import OUT,save,sha

RUNS=['lt_cal_dyn_xthird','lt_cal_dyn_x1','lt_cal_dyn_x3','lt_cal_current']

def main():
    assert not (OUT/'checks/calibration_STOP.json').exists()
    output=OUT/'checks/lambda_selection.json';assert not output.exists()
    rows=[];sources=[]
    for name in RUNS:
        unit=OUT/'runs/B173nb_b10'/(name+'_ALS_s0');p=json.loads((unit/'PASS.json').read_text())
        # Receipts contain host absolute paths; resolve only under this task.
        sub=unit/f"attempt_{p['attempt']}";model=sub/'model'
        m=json.loads((sub/'metrics.json').read_text());r=json.loads((sub/'receipt.json').read_text())
        grad=model/'monitor/losstrain_gradients.jsonl'
        g=[json.loads(line) for line in grad.read_text().splitlines()]
        assert [x['iteration'] for x in g]==list(range(2901,3001))
        rgb=float(np.median([x['values']['rgb']['all_median'] for x in g]))
        depth=float(np.median([x['values']['depth']['all_median'] for x in g]))
        assert np.isfinite(rgb) and np.isfinite(depth)
        row=dict(run=name,multiplier=r['run']['mult'],training_psnr_db=m['training_psnr_mean_db'],
            train_views=len(m['views']),rgb_gradient_median=rgb,depth_gradient_median=depth,
            depth_to_rgb_ratio=depth/rgb if rgb>0 else None,gradient_iterations=len(g),
            compatible_depth_median_sigma=m['compatible_depth_normalized_abs_median'],compatible_pixels=m['compatible_pixels'],
            gpu_peak_total_MiB=r['gpu_peak_total_MiB'],training_command_seconds=r['seconds'],
            iteration_mean_ms=m['iteration_time'].get('mean_ms'),iteration_median_ms=m['iteration_time'].get('median_ms'),
            iteration_time_samples=m['iteration_time'].get('samples'),attempt=p['attempt'],
            source=str(sub),origin='[이 발주에서 냄]')
        rows.append(row);sources.append(dict(path=str(sub),metrics_sha256=sha(sub/'metrics.json'),
            gradients_sha256=sha(grad),receipt_sha256=sha(sub/'receipt.json')))
    baseline=next(x for x in rows if x['run']=='lt_cal_current');default=next(x for x in rows if x['run']=='lt_cal_dyn_x1')
    low=default['depth_gradient_median'] < .1*default['rgb_gradient_median']
    drop=baseline['training_psnr_db']-default['training_psnr_db'];bad=drop>1.
    selected=None if low and bad else .0025*(3 if low else 1/3 if bad else 1)
    result=dict(status='STOP_BOTH_TRIGGERS' if selected is None else 'PASS',selected_lambda=selected,
        low_gradient=low,psnr_drop_db=drop,psnr_drop_above_1_db=bad,rows=rows,sources=sources,
        GT_geometry_used=False,evaluation_metrics_used=False,scientific_verdict=None)
    save(output,result);save('/docs/tables/calibration.json',result)
    with Path('/docs/tables/calibration.csv').open('w') as f:
        w=csv.DictWriter(f,list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    lines=['# 짧은 학습과 세기 선택','',f"상태 {result['status']} · 선택 λ {selected} · scientific_verdict: null",'',
        '| 학습 | PSNR (dB) | 사진 / 깊이 기울기 중앙값 | 깊이/사진 | 반복 평균 (ms) | 최대 GPU (MiB) |',
        '|---|---:|---:|---:|---:|---:|']
    for x in rows:lines.append(f"| {x['run']} | {x['training_psnr_db']:.6f} | {x['rgb_gradient_median']:.9g} / {x['depth_gradient_median']:.9g} | {x['depth_to_rgb_ratio']} | {x['iteration_mean_ms']} | {x['gpu_peak_total_MiB']} |")
    lines+=['',f'기본의 깊이 기울기 < 사진의 10%: {low}. 기본의 PSNR 감소 {drop:.6f} dB, 1 dB 초과: {bad}.',
        '기울기는 반복마다 모든 가우시안 중심의 L2 기울기 중앙값을 구하고 마지막 100회의 중앙값으로 요약했다. PSNR은 모든 학습 영상의 영상별 RGB MSE로 계산했다. 참값 위치와 채점 값은 선택에 사용하지 않았다. 반올림 전 값·표본 수·출처는 JSON/CSV에 있다. [이 발주에서 냄]']
    Path('/docs/tables/calibration.md').write_text('\n'.join(lines)+'\n')
    if selected is None:
        print('STOP: both frozen selection conditions triggered',flush=True);return
    p=Path('/config/losstrain_v1.json');old=p.with_name('losstrain_v1.calibration_frozen.json')
    assert not old.exists();shutil.copyfile(p,old);shutil.copyfile(p.with_suffix('.lock.json'),old.with_suffix('.lock.json'))
    cfg=json.loads(p.read_text());stamp=datetime.now(timezone(timedelta(hours=9))).isoformat()
    cfg['saved_at']=stamp;cfg['status']='PREPARATION_PASS';cfg['lambda_selection']['selected_lambda']=selected
    cfg['execution'].update(training_started=True,short_runs_completed=4)
    cfg['amendments'].append(dict(at=stamp,previous_config=old.name,previous_sha256=sha(old),
        reason='select shared lambda by the frozen rule after four short trainings',selection_sha256=sha(output)))
    save(p,cfg);save(p.with_suffix('.lock.json'),dict(sha256=sha(p),saved_at=stamp,training_started=True,scientific_verdict=None))
    print('lambda selection',result['status'],selected,flush=True)

if __name__=='__main__':main()
