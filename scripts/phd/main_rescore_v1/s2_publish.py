"""Stage-2 and combined chapter-7 tables; sealed stage-1 values are read only."""
from common import *
from add3_publish import FAMILIES,NAMES,pct
from publish_tables import CELL_NAMES
BASE=Path('/out');D1=Path('/docs/addendum3_stage1')
SITES2=['B0_b10','R1rep_b10']
def main():
    cfg();combined={k:json.loads((D1/'tables'/f'b173_table{k}.json').read_text())['rows'] for k in range(3,9)};inputs=[];missing=[]
    for site in SITES2:
        rows={k:[] for k in range(3,9)};views=len(json.loads((O/'views'/f'{site}.json').read_text())['views'])
        for prior in ['ALS','LoD2']:
            for family in FAMILIES+(['fusion_mvswalls','judgment_mesh_mvswalls','oracle_mvswalls'] if prior=='ALS' else []):
                key=f'{site}__{prior}__{family}';p=O/'scores'/key/'values.json'
                base=dict(site=site,prior=prior,key=key,method=NAMES[family],mesh_rule='original input surface' if family in ['prior','mvs'] else f'{views} training views, TSDF .05/.25 m, top50, eval crop',source_tag='[이 발주에서 냄]')
                if not p.exists():
                    assert family=='FINALTRAIN_30000',key
                    reason='학습 완료 30,000회 모델 미수신; 학습·중간 판 대체 없음'
                    receipt=PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs'/site/f'ft_{prior}_s0/receipt.json'
                    if receipt.exists():reason='FINALTRAIN 완료 영수증 상태: '+json.loads(receipt.read_text())['status']+'; 채점 가능한 최종 결과 없음, issues.md 참조'
                    base.update(status='확인 불가',reason=reason,source=None,source_sha256=None,surface=None,surface_sha256=None)
                    empty=dict(n_gt=None,n_result=None,completeness=None,accuracy=None,gt_mean_m=None,result_mean_m=None)
                    rows[3].append(dict(base,**empty));missing.append(base)
                    for c in range(5):
                        r=dict(base,cell=c,cell_name=CELL_NAMES[c],**empty);rows[4].append(r);rows[7].append(r)
                    rows[5].append(dict(base,**empty));rows[6].append(base);rows[8].append(dict(base,**empty));continue
                v=json.loads(p.read_text());base.update(status='PASS',source=str(p),source_sha256=sha(p),surface=v['mesh'],surface_sha256=v['mesh_sha256'])
                diag={('n_result_sample_total' if k=='n_result' else k):x for k,x in v['diagnostic'].items()}
                rows[3].append(dict(base,**v['scene'],**diag))
                for c in v['cells']:
                    r=dict(base,**c,cell_name=CELL_NAMES[c['cell']],**diag);rows[4].append(r)
                    if family in ['baseline_30000','judgment_mesh','oracle','FINALTRAIN_30000','judgment_mesh_mvswalls','oracle_mvswalls']:rows[7].append(r)
                rows[5].extend(dict(base,**x) for x in v['offsets']);rows[8].append(dict(base,**v['band']))
                if family in ['prior','mvs']:inputs.append(dict(site=site,prior=prior,family=family,surface=v['mesh'],surface_sha256=v['mesh_sha256'],mode='기존 새 τ·cells_v2·기둥·400점/m² 점수와 점 위치 재사용; 재표본·재거리 계산 없음',score=str(p),score_sha256=sha(p)))
        for p in sorted((D/'tables').glob(f'target_quality_{site}__*.json')):rows[6].extend(json.loads(p.read_text())['rows'])
        for k,rr in rows.items():
            assert all('r8' not in r.get('method','') for r in rr);table(site+'_table'+str(k),rr);combined[k].extend(rr)
        lines=['| 지역 | 사전 정보 | 방법 | 완전성 % | 정확성 % | 참값 거리 cm | 결과 거리 cm |','|---|---|---|---:|---:|---:|---:|']
        for r in rows[3]:lines.append('| '+' | '.join([LABELS[site],r['prior'],r['method'],*[pct(r[k]) for k in ['completeness','accuracy','gt_mean_m','result_mean_m']]])+' |')
        lines+=['','- 표 3~8: `tables/'+site+'_table*.json`, `.csv`, `.md`.','- 본 방법: FINALTRAIN 30,000회. 미수신 모델은 확인 불가; r8 대체 없음.','- scientific_verdict: null.'];(D/(LABELS[site]+'_비교방법_채점.md')).write_text('\n'.join(lines)+'\n')
    for k,rr in combined.items():table('all_regions_table'+str(k),rr)
    table('input_reuse',inputs);table('unavailable',missing)
    progress(f'단계 2·세 지역 합본 표 3~8 생성; 단계 2 장면 46행, 합본 69행. 본 방법 미수신 {len(missing)}행은 확인 불가.')
if __name__=='__main__':main()
