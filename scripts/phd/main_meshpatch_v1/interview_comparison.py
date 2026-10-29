"""Reuse completed comparison rows; explicitly account for resource holds."""
from interview_common import *

def main():
    cfg=config();rows=[];states=[]
    plan=json.loads((D/'tables/mesh_memory_plan.json').read_text());held={r['key']:r for r in plan['rows'] if r['disposition']=='WAIT_RESOURCE_REVIEW'}
    for key in cfg['comparison_targets']:
        p=D/'tables/meshes'/f'{key}.json'
        if not p.exists() or json.loads(p.read_text())['status']!='PASS':
            states.append(dict(key=key,status='WAIT_RESOURCE_REVIEW' if key in held else 'PENDING',reason='메모리 조건으로 보류' if key in held else '정리 전·후 완료 기록 없음'))
            continue
        rec=json.loads(p.read_text());states.append(dict(key=key,status='PASS',receipt=source(p)))
        for stage in ['before','after']:
            rows.extend(dict(key=key,stage=stage,**r) for r in rec[stage])
    anchor=D/'tables/meshes/B173nb_b10__LoD2__imgonly_2dgs_s0.json';x=json.loads(anchor.read_text())
    tests=[]
    for cell,want in [('0~3',44.0),('1',34.6),('2',26.7)]:
        got=next(r['within_tau_pct'] for r in x['before'] if r['cell']==cell)
        tests.append(dict(cell=cell,expected_percent=want,actual_percent=got,pass_check=round(got,1)==want))
    assert all(t['pass_check'] for t in tests)
    write_table('comparison_scores',rows,['기존 B0·B173 완료 줄을 재계산하지 않음. before=지금 채점 메시; after=원본 GeoGS 정리 메시.'])
    dump(IDOC/'checks/comparison.json',dict(status='PASS',checks=tests,source=source(anchor),scientific_verdict=None))
    dump(IDOC/'tables/comparison_status.json',dict(targets=states,scientific_verdict=None))
    lines=['# 비교 방법 · 정리 전과 후','','| 대상 | 상태 |','|---|---|']+[f"| {r['key']} | {r['status']} |" for r in states]
    lines+=['','| 대상 | 전·후 | 칸 | 넓이 m² | τ 안 % | 뜬 면 % | MVS % | 사전 % | 그 밖·면 없음 % |','|---|---|---|---:|---:|---:|---:|---:|---:|']
    def f(x):return '확인 불가' if x is None else f'{x:.2f}'
    for r in rows:lines.append('| '+' | '.join([r['key'],r['stage'],r['cell'],f(r['area_m2'])]+[f(r[k+'_pct']) for k in CATEGORIES])+' |')
    (IDOC/'tables/comparison_scores.md').write_text('\n'.join(lines)+'\n')
    record('comparison',status='PARTIAL' if any(r['status']!='PASS' for r in states) else 'PASS',completed=sum(r['status']=='PASS' for r in states),targets=len(states),held=sum(r['status']=='WAIT_RESOURCE_REVIEW' for r in states))

if __name__=='__main__':main()
