"""Current completion counts and reset+100 observations, preserving old stop reports."""
import csv
import json
from datetime import datetime,timezone,timedelta
from pathlib import Path
from inputs import OUT,save,sha

def records(path):
    if not path.exists():return []
    return [json.loads(s) for s in path.read_text().splitlines() if s.strip()]

def main():
    stamp=datetime.now(timezone(timedelta(hours=9))).isoformat();runs=[];comparisons=[]
    for root in sorted((OUT/'runs').glob('*/*')):
        if not root.is_dir():continue
        attempts=[]
        for p in sorted(root.glob('attempt_*')):
            rec=json.loads((p/'receipt.json').read_text()) if (p/'receipt.json').exists() else None
            command=json.loads((p/'command.json').read_text()) if (p/'command.json').exists() else []
            is_v2='--jbgs_lt_monitor_v2' in command
            v2=records(p/'model/monitor/losstrain_health_v2.jsonl')
            health=v2 or records(p/'model/monitor/losstrain_health.jsonl');last=health[-1] if health else None
            events=records(p/'model/monitor/losstrain_reset_comparison.jsonl')
            comparisons += [dict(site=root.parent.name,result=root.name,attempt=p.name,**x) for x in events]
            stops=[x for x in health if x.get('stop')]
            attempts.append(dict(attempt=p.name,receipt=rec,last_health=last,stops=stops,monitor_policy='v2' if is_v2 else 'historical prior-opacity',
                resets=records(p/'model/monitor/losstrain_resets.jsonl')))
        runs.append(dict(site=root.parent.name,result=root.name,calibration=root.name.startswith('lt_cal_'),
            training_complete=(root/'PASS.json').exists(),training_health_stopped=json.loads((root/'training_health_STOP.json').read_text()) if (root/'training_health_STOP.json').exists() else None,training_no_result=json.loads((root/'training_NO_RESULT.json').read_text()) if (root/'training_NO_RESULT.json').exists() else None,post_complete=(root/'post_PASS.json').exists(),
            measurement_complete=(root/'measure_PASS.json').exists(),attempts=attempts,
            post_attempts=[dict(stage=p.name.split('_attempt_')[0],path=str(p),**json.loads(p.read_text()))
                for p in sorted(root.glob('*_attempt_*_receipt.json'))]))
    completed=[r for r in runs if r['training_complete'] and not r['calibration']]
    stop=OUT/'checks/full_monitor_v2_STOP.json'
    revision=OUT/'checks/monitor_v2/camera_fix/restart_approval.json'
    if revision.exists() and json.loads(revision.read_text())['status']=='AUTHORIZED':stop=OUT/'checks/full_monitor_v2_camera_fix_STOP.json'
    fixed_stop=OUT/'runs/B173nb_b10/lt_fixgt_ALS_s0/STOP_monitor_v2.json'
    if fixed_stop.exists():stop=fixed_stop
    state='STOPPED_PARTIAL' if stop.exists() else 'RUNNING'
    resumed=OUT/'checks/resource_resume_v1'
    if (resumed/'approval.json').exists():
        state_record=json.loads((resumed/'state.json').read_text()) if (resumed/'state.json').exists() else {}
        all_stops=sorted(resumed.glob('*_STOP.json'))
        operational=[p for p in all_stops if json.loads(p.read_text()).get('status')=='OPERATIONAL_ANALYSIS_DELIVERY_HANDOFF']
        current_stops=[p for p in all_stops if p not in operational]
        stop=current_stops[0] if current_stops else resumed/'NO_CURRENT_STOP'
        state='STOPPED_PARTIAL' if current_stops else 'WAITING_FOR_INFLIGHT_TRAINING' if operational else 'COMPLETE' if (resumed/'PASS.json').exists() else 'PARTIAL_NO_RESULT' if (resumed/'PARTIAL_NO_RESULT.json').exists() else state_record.get('status','RUNNING')
    counts=dict(training_health_stopped=sum(r['training_health_stopped'] is not None for r in runs),training_no_result=sum(r['training_no_result'] is not None for r in runs),calibration_complete=sum(r['training_complete'] for r in runs if r['calibration']),
        required_complete=sum(not r['result'].startswith('lt_fixnow') for r in completed),optional_complete=sum(r['result'].startswith('lt_fixnow') for r in completed),
        post_complete=sum(r['post_complete'] for r in runs),measurements_complete=sum(r['measurement_complete'] for r in runs),
        historical_before_grace_stops=2,historical_grace_stops=1,
        post_stopped_attempts=sum(bool(a['exit_code']) for r in runs for a in r['post_attempts']),
        new_stopped_attempts=sum(bool(a['stops']) or bool(a['receipt'] and a['receipt']['exit_code']) for r in runs if not r['calibration'] for a in r['attempts'] if a['monitor_policy']=='v2'))
    counts['core_patch_scored']=sum(
        r['training_complete'] and not r['calibration'] and not r['result'].startswith('lt_fixnow')
        and (OUT/'patch_z'/f"{r['site']}__{r['result'].rsplit('_',2)[1]}__{r['result']}.json").exists()
        for r in runs)
    priority_path=OUT/'checks/analysis_delivery_priority_v1/state.json'
    priority=json.loads(priority_path.read_text()) if priority_path.exists() else None
    data=dict(status=state,at=stamp,counts=counts,runs=runs,reset_comparisons=comparisons,
        stop=json.loads(stop.read_text()) if stop.exists() else None,selected_lambda=.0025,
        analysis_delivery_priority=priority,scientific_verdict=None)
    recovery=OUT/'checks/fixed_post_host_oom'
    if (recovery/'preparation.json').exists():
        data['fixed_post_host_oom_recovery']=dict(
            status='PASS' if (recovery/'PASS.json').exists() else 'STOPPED' if (recovery/'STOP.json').exists() else 'WAITING_OR_RETRYING',
            preparation=json.loads((recovery/'preparation.json').read_text()),
            latest_memory_wait=json.loads((recovery/'memory_wait.json').read_text()) if (recovery/'memory_wait.json').exists() else None)
    save('/docs/tables/runtime.json',data);save(OUT/'checks/runtime.json',data)
    save('/docs/tables/reset_comparisons.json',dict(rows=comparisons,scientific_verdict=None))
    if comparisons:
        with Path('/docs/tables/reset_comparisons.csv').open('w') as f:
            keys=list(dict.fromkeys(k for r in comparisons for k in r));w=csv.DictWriter(f,keys,lineterminator='\n');w.writeheader();w.writerows(comparisons)
    lines=['# 이전 규칙의 초기화 100회 뒤 사전 출신 불투명도','',
        '기록 보존용이다. 당시 사전 출신의 0.05 기준은 이후 사용자 승인으로 폐지되었다. 아래 값은 100회 뒤에 최적화·불투명도 보호를 마치고 밀도 제어·다음 초기화를 하기 전에 읽었다. nojudge도 같은 반복과 관측 시점이다. 새 규칙의 전체 불투명도와 PSNR은 monitor_v2_observations 표에 별도로 기록한다.','',
        '| 단위 | 판 | 반복 | 사전 출신 N | 이번 중앙값 | nojudge 중앙값 | 차 | 상태 |','|---|---|---:|---:|---:|---:|---:|---|']
    for r in comparisons:
        med=r['prior_opacity_median'];fmt=lambda x:'확인 불가' if x is None else f'{x:.9f}'
        lines.append(f"| {r['site']} | {r['result']} | {r['iteration']} | {r['prior_gaussians']} | {fmt(med)} | {fmt(r['nojudge_prior_opacity_median'])} | {fmt(r['difference_from_nojudge'])} | {'중단' if r['stop'] else '통과'} |")
    Path('/docs/tables/reset_comparisons.md').write_text('\n'.join(lines)+'\n')
    progress=f"# PHD-MAIN-LOSSTRAIN-v1\n\n{stamp}: {state}.\n\n짧은 학습 {counts['calibration_complete']}/4. 본 학습 {counts['required_complete']}/24. 선택 {counts['optional_complete']}/6. 후처리 {counts['post_complete']}. 채점 {counts['measurements_complete']}. λ=0.0025. 이전 3,001회 두 건과 9,100회 한 건은 기록 보존. 새 전체 불투명도·PSNR 기준 뒤 중단 시도 {counts['new_stopped_attempts']}건. scientific_verdict: null.\n\n이전 초기화 비교: tables/reset_comparisons.md. 새 관측: tables/monitor_v2_observations.md. 상세 실행 상태: tables/runtime.json.\n"
    progress+=f"\n핵심 패치 채점 완료 {counts['core_patch_scored']}판. 위 채점 수는 추가 지표까지 마친 수이며 서로 구분한다.\n"
    if priority:
        progress+=f"\n8판 우선 전달 상태({priority['at']}): {priority['status']}."
        if priority['status']=='WAITING_FOR_POST_MEMORY':
            progress+=f" 호스트 여유 {priority['available_GiB']:.2f} GiB / 시작 조건 {priority['required_GiB']} GiB."
        progress+='\n'
    Path('/docs/progress.md').write_text(progress);print(state,counts,flush=True)

if __name__=='__main__':main()
