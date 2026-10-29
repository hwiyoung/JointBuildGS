"""Before/after four-value tables, appendix values and honest pending estimates."""
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone


def read(p, default=None):
    return json.loads(p.read_text()) if p.exists() else default


def status(d=Path('/docs'), o=Path('/out'), c=Path('/config')):
    cfg=read(c/'axes_addendum_v1.json')
    if not cfg:
        return None
    rows=[read(p) for p in sorted((d/'tables/axes').glob('*.json'))]
    passed=[r for r in rows if r['status']=='PASS']
    done={r['key'] for r in passed}
    missing=[k for k in cfg['metric_keys'] if k not in {r['key'] for r in rows}]
    first=cfg['stage1_first_keys']
    elapsed=[r['before']['seconds']+r['after']['seconds'] for r in passed]
    estimates={}
    # Execution-only estimate; waiting for the shared resource is explicitly additional.
    baseline=read(o/'axes_dist'/cfg['baseline']['key']/'before/values.json',{})
    mean=sum(elapsed)/len(elapsed) if elapsed else (2*baseline['seconds'] if baseline else None)
    cleanup=[read(p) for p in sorted((d/'tables/meshes').glob('*.json'))]
    completed_cleanup={r['target']['key'] for r in cleanup if r['status']=='PASS'}
    failures=read(d/'tables/runtime_failures.json',{}).get('failures',[])
    known={r['key'] for r in failures}
    queue_log=o/'logs/queue_failures.tsv'
    if queue_log.exists():
        for line in queue_log.read_text().splitlines():
            fields=line.split('\t')
            if len(fields)>=3 and fields[2]=='cleanup_failed' and fields[1] not in known:
                failures.append(dict(key=fields[1],status='FAILED_CLEANUP',failed_at=fields[0],
                    reason='작업 종료 실패. 상세 원인은 아직 확인 불가.',evidence=str(queue_log)))
                known.add(fields[1])
    blocked={r['key']:r for r in failures if r['key'] not in completed_cleanup and r['key'] in missing}
    memory_plan=read(d/'tables/mesh_memory_plan.json',{})
    for r in memory_plan.get('rows',[]):
        if r['disposition']=='WAIT_RESOURCE_REVIEW' and r['key'] not in completed_cleanup and r['key'] in missing:
            blocked[r['key']]=dict(key=r['key'],status='WAIT_RESOURCE_REVIEW',
                estimated_cleanup_peak_gib=r['estimated_cleanup_peak_gib'],
                reason='메시 크기와 관측 최대 사용량에 따른 사전 보류. 같은 조건의 자동 재시도 없음.',
                evidence=str(d/'tables/mesh_memory_plan.json'),previous_failure=blocked.get(r['key']))
    cleanup_times=[r['seconds'] for r in cleanup if r['status']=='PASS']
    cleanup_mean=sum(cleanup_times)/len(cleanup_times) if cleanup_times else None
    target_rows=read(c/'mesh_targets_v1.json')['targets']+cfg['extra_targets']
    unavailable={r['key'] for r in target_rows if r['status'].startswith('UNAVAILABLE')}
    six=read(c/'priority_delivery_v1.json',{}).get('keys',[])
    order=first+sorted(k for k in six if k not in first)+sorted(k for k in cfg['metric_keys'] if k not in first and k not in six)
    remaining=[k for k in order if k in missing]
    clock=datetime.now(timezone(timedelta(hours=9)))
    cumulative=0.
    for k in remaining:
        if k in blocked or k in unavailable:
            estimates[k]=None
            continue
        if k not in unavailable and mean is not None:
            cumulative+=mean+(cleanup_mean or 0 if k not in completed_cleanup else 0)
        estimates[k]=(clock+timedelta(seconds=cumulative)).isoformat() if mean else None
    interview_pending=(c/'interview_addendum_v2.json').exists() and not (o/'interview_v2/cpu_queue_finished.json').exists()
    if interview_pending:estimates={k:None for k in estimates}
    return dict(completed=len(done),required=len(cfg['metric_keys']),stage1_completed=sum(k in done for k in first),
                stage1_required=len(first),unavailable=sum(r['status'].startswith('UNAVAILABLE') for r in rows),
                baseline_status=read(d/'tables/axes_baseline_replay.json',{}).get('status','진행 중'),
                pending=missing,estimate_kst_excluding_resource_wait=estimates,
                blocked=list(blocked.values()),overall_estimate_kst=None if blocked else next((v for v in reversed(list(estimates.values())) if v),None),
                estimate_note=('덧붙임 2의 우선 작업이 삽입되어 기존 전체 평균 기반 개별 시각은 보류. 현재 예상은 interview_v2/진행.md를 따른다. ' if interview_pending else '')+'완료한 전·후 및 메시 정리 시간 평균으로 추정. 미완료 정리는 한 작업분 전부를 포함하고 공유 잠금·메모리 대기는 별도. 실패 후 재개되지 않은 대상과 원본 결과가 없는 대상은 예상 시각 null. 재시도 시간은 다른 대상 예상에 포함하지 않으며, 실패가 남으면 전체 완료 예상은 확인 불가.',
                scientific_verdict=None)


def flat(block):
    g=block.get('gt',{});r=block.get('res',{}).get('E',{})
    return dict(R_tau=g.get('R_tau'),P_tau=r.get('P_tau'),gt_mean_cm=g.get('mean'),res_mean_cm=r.get('mean'),
                gt_median_cm=g.get('med'),gt_over4tau=g.get('out4'),gt_over1m=g.get('far1'),n_gt=g.get('n_gt',0),
                n_res=r.get('n',0),n_res_all=block.get('res',{}).get('n_res_all',0),excluded_res=r.get('excluded',0),excluded_share=r.get('excluded_share'),status=block.get('status'))


def main():
    from mesh_common import dump
    d=Path('/docs');s=status()
    if s is None:return
    rows=[]
    for p in sorted((d/'tables/axes').glob('*.json')):
        r=read(p)
        if r['status']!='PASS':continue
        for family in ['losstrain_cells_0_to_5','axes71_cells','axes']:
            for group,b in r['before']['values'][family].items():
                a=r['after']['values'][family][group]
                if family=='axes':
                    for i,x in b.items():
                        y=a[i]
                        def f(v):
                            return dict(R_tau=v.get('R_tau'),P_tau=v.get('P_tau'),gt_mean_cm=v.get('mean'),res_mean_cm=v.get('res_mean'),
                                        gt_median_cm=v.get('med'),gt_over4tau=v.get('out4'),gt_over1m=v.get('far1'),
                                        n_gt=v.get('n_gt',0),n_res=v.get('n_res',0),n_res_all=v.get('n_res_all',0),excluded_res=v.get('excluded_res',0),excluded_share=v.get('excluded_share'),status=v['status'])
                        rows.append(dict(key=r['key'],family=family,group=group,bin=i,label=x['label'],before=f(x),after=f(y)))
                else:
                    rows.append(dict(key=r['key'],family=family,group=group,before=flat(b),after=flat(a)))
    dump(d/'tables/axes_comparison.json',dict(status=s,rows=rows,units='shares 0..1; distances cm, uncapped',scientific_verdict=None))
    dump(d/'tables/axes_progress.json',s)
    # Match the FARPULL four-value column names/units for a direct combined table.
    common=[]
    scale=lambda value,factor:None if value is None else value*factor
    for row in rows:
        if row['family']=='axes71_cells':continue
        site,prior,result=row['key'].split('__')
        for stage,variant in [('before','GeoGS_before'),('after','GeoGS_clean')]:
            x=row[stage]
            common.append(dict(site=site,prior=prior,result=result,mesh_variant=variant,result_type='mesh',result_count='E',means_uncapped=True,
                group='cell' if row['family']=='losstrain_cells_0_to_5' else row['group'],
                subset='cell_'+row['group'] if row['family']=='losstrain_cells_0_to_5' else row['label'],
                R_tau_pct=scale(x.get('R_tau'),100),P_tau_pct=scale(x.get('P_tau'),100),
                gt_mean_m=scale(x.get('gt_mean_cm'),.01),result_mean_m=scale(x.get('res_mean_cm'),.01),
                gt_median_m=scale(x.get('gt_median_cm'),.01),gt_over_4tau_pct=scale(x.get('gt_over4tau'),100),gt_over_1m_pct=scale(x.get('gt_over1m'),100),
                n_gt=x['n_gt'],n_result_all=x['n_res_all'],n_result_counted=x['n_res'],result_excluded_pct=scale(x.get('excluded_share'),100),
                patch_within_tau_pct=None,scientific_verdict=None))
    dump(d/'tables/axes_four_values.json',dict(rows=common,units='m and percent; same column names as FARPULL four-value table',scientific_verdict=None))
    columns=['site','prior','result','mesh_variant','group','subset','R_tau_pct','P_tau_pct','gt_mean_m','result_mean_m','gt_median_m','gt_over_4tau_pct','gt_over_1m_pct']
    common_md=['# 메시 정리 전·후 네 값 — 공통 단위','', '[이 발주에서 냄] 거리 m, 비율 %. 평균 상한 없음. FARPULL과 같은 열 이름·단위. 두 작업의 원본 결과는 바꾸지 않는다.','',
               '| '+' | '.join(columns)+' |','|'+'|'.join(['---']*len(columns))+'|']
    for r in common:
        common_md.append('| '+' | '.join('확인 불가' if r.get(k) is None else f'{r[k]:.6g}' if isinstance(r[k],float) else str(r[k]) for k in columns)+' |')
    (d/'tables/axes_four_values.md').write_text('\n'.join(common_md)+'\n')
    fmt=lambda x:'확인 불가' if x is None else f'{x:.6f}'
    lines=['# AXES71-v2 네 값: 메시 정리 전·후','', '[이 발주에서 냄] 평균 거리에는 상한이 없다. 결과 기준은 셈 마(법선 거리, 옆 거리 0.5 m 이내)이다.',
           '칸 0~5는 LOSSTRAIN의 원래 숫자 칸이다. AXES71 세부 칸은 이름으로 별도 제공하며, 가상 시점 전용 칸은 확인 불가로 유지한다.',
           '거리 단위 cm, R·P와 부록 비율은 0~1. 모든 칸·축 구간의 부록 값과 표본 수·제외 수는 같은 이름의 JSON과 대상별 tables/axes/에 있다.','',
           f"완료 {s['completed']}/{s['required']}, 우선 비교 방법 {s['stage1_completed']}/{s['stage1_required']}. 옛 결과 재계산: {s['baseline_status']}.",'',
           '| 대상 | 구분 | 칸/구간 | 정리 | R(τ) | P(τ) | 참값 평균 cm | 결과 평균 cm | 참값 중앙값 cm | 4τ 초과 | 1 m 초과 |',
           '|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for row in rows:
        for stage,name in [('before','전'),('after','후')]:
            x=row[stage]; label=row['group']+(' '+row['label'] if 'label' in row else '')
            lines.append('| '+' | '.join([row['key'],row['family'],label,name]+[fmt(x.get(k)) for k in ['R_tau','P_tau','gt_mean_cm','res_mean_cm','gt_median_cm','gt_over4tau','gt_over1m']])+' |')
    (d/'tables/axes_comparison.md').write_text('\n'.join(lines)+'\n')
    text=f"\n추가 지표: AXES71-v2 네 값과 부록은 {s['completed']}/{s['required']}개 완료. 우선 비교 방법 {s['stage1_completed']}/{s['stage1_required']}개. 옛 정리 전 결과 대조 {s['baseline_status']}. `tables/axes_comparison.md`에 전·후를 나란히 기록한다.\n"
    if s['blocked']:
        text+=f"\n메시 정리 실패·자원 보류 {len(s['blocked'])}개는 미완료다. `tables/axes_progress.json`과 `tables/mesh_memory_plan.json`에 대상·원인·근거를 기록했다. 재개 시각과 전체 완료 예상은 확인 불가이며, 처리 가능한 대상은 계속 진행한다.\n"
    for name in ['progress.md','메시정리와패치표_보고_v1.md']:
        p=d/name
        if p.exists():p.write_text(p.read_text()+text)


if __name__=='__main__':main()
