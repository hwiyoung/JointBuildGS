"""Comparable observations and explicit historical missingness; no interpolation."""
import csv,json
from pathlib import Path
from inputs import OUT,save
from runtime_report import records

LABELS=dict(all='전체',initial_prior='초기 사전',initial_image='초기 영상(MVS 계열)',density_born='밀도 제어 생성',
    prior_lineage='사전 계보 전체',image_lineage='영상 계보 전체',prior_gt_correct='사전 계보·참값 맞음',
    prior_gt_incorrect='사전 계보·참값 틀림',prior_gt_unknown='사전 계보·참값 없음')

def main():
    observations=[];saved=[]
    for p in sorted((OUT/'runs').glob('*/*/attempt_*/model/monitor/losstrain_observations_v2.jsonl')):
        unit=p.parents[3];site=unit.parent.name;result=unit.name;attempt=p.parents[2].name
        observations += [dict(site=site,result=result,attempt=attempt,**r) for r in records(p)]
    for p in sorted((OUT/'opacity_saved').glob('*/*/*.json')):saved.append(json.loads(p.read_text()))
    baseline={(r['site'],r['prior'],r['iteration']):r for r in saved if r['result'].startswith('nojudge')}
    rows=[]
    for r in observations:
        prior=r['result'].split('_')[-2]
        # Live observations and saved model states are displayed separately. The
        # historical saved 15k/30k values have their own explicit phase/source.
        b=baseline.get((r['site'],prior,r['iteration']))
        for key in LABELS:
            value=r['groups'].get(key);reference=b['groups'].get(key) if b else None
            rows.append(dict(site=r['site'],prior=prior,result=r['result'],attempt=r['attempt'],iteration=r['iteration'],
                phase=r['observation_phase'],kind=key,count=value['count'] if value else None,
                opacity_median=value['opacity_median'] if value else None,
                nojudge_count=reference['count'] if reference else None,nojudge_opacity_median=reference['opacity_median'] if reference else None,
                nojudge_status='저장 모델' if reference else '기록 없음',train_psnr_legacy5=r['train_psnr_legacy5'],
                nojudge_train_psnr_legacy5=r['nojudge_train_psnr_legacy5'],stop=r['stop']))
    # Inflight fixed has legacy scalar logs; only recover what those logs contain.
    fixed=OUT/'runs/B173nb_b10/lt_fixgt_ALS_s0/attempt_1/model/monitor'
    old=records(fixed/'scalars.jsonl');resets=records(fixed/'losstrain_resets.jsonl')
    resetits={x['iteration'] for x in resets if x['periodic']}
    fixedlegacy=[]
    for r in old:
        it=r['iteration']
        if it%1000 and not any(it-x in [100,500] for x in resetits):continue
        fixedlegacy.append(dict(iteration=it,prior_count=r.get('n_prior'),
            prior_opacity_median=r.get('opacity_q_prior',[None,None])[1],
            note='기존 로그에서 복구; 초기화 직전 밀도 제어 후 값·생성 표식·추가 영상 기록은 없음',source=str(fixed/'scalars.jsonl')))
    save('/docs/tables/monitor_v2_observations.json',dict(observations=observations,rows=rows,saved_models=saved,
        fixed_legacy_observations=fixedlegacy,group_definitions=LABELS,
        prior_gt_definition='initial stage1 cell 0/2/4 correct, 1/3/5 incorrect, 6/unlocated unknown; all lineage descendants',
        image_origin_provenance='existing origin=0: main_stage0_v1/fork_inputs_v6.py reads MVS-folder sparse/points3D.bin (SfM sparse seed); not a new dense-MVS initialization',
        nojudge_retrained=False,scientific_verdict=None))
    if rows:
        with Path('/docs/tables/monitor_v2_observations.csv').open('w') as f:
            w=csv.DictWriter(f,list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    fmt=lambda x:'기록 없음' if x is None else str(x) if isinstance(x,int) else f'{x:.6f}'
    lines=['# 새 중단 기준의 기록','','추가 PSNR은 기존과 같은 다섯 영상이다. 중단 비교는 7,000·15,000·30,000회만 한다. 사전 출신과 참값 칸별 통계는 기록만 한다. 초기 출신 둘과 밀도 제어 생성은 서로 겹치지 않으며, 계보별 표는 생성된 자손도 포함한다.',
        '요청의 MVS 출신은 기존 origin=0 영상 계보로 표시했다. 실제 초기점은 기존 fork_inputs_v6.py가 MVS 폴더의 sparse/points3D.bin에서 읽은 SfM 희소점이다. 초기 입력은 바꾸지 않았다.','',
        '| 단위·판 | 반복·시점 | 구분 | N | 불투명도 중앙값 | nojudge N | nojudge 중앙값 |',
        '|---|---|---|---:|---:|---:|---:|']
    for r in rows:
        lines.append(f"| {r['site']} {r['result']} | {r['iteration']} {r['phase']} | {LABELS[r['kind']]} | {fmt(r['count'])} | {fmt(r['opacity_median'])} | {fmt(r['nojudge_count'])} | {fmt(r['nojudge_opacity_median'])} |")
    lines+=['','## 다섯 영상 PSNR','','| 판 | 반복·시점 | 이번 dB | nojudge dB | 중단 |','|---|---|---:|---:|---|']
    for r in observations:lines.append(f"| {r['result']} | {r['iteration']} {r['observation_phase']} | {fmt(r['train_psnr_legacy5'])} | {fmt(r['nojudge_train_psnr_legacy5'])} | {r['stop'] or '없음'} |")
    lines+=['','## 저장 모델의 통계','','15,000·30,000회 모델을 읽었다. 과거 생성 표식이 없어 초기 사전·초기 영상·밀도 제어 생성의 분리는 ‘기록 없음’이다. 계보별·참값 칸별 통계는 정확한 저장값으로 센다.','',
        '| 단위·판 | 반복 | 구분 | N | 중앙값 | nojudge N | nojudge 중앙값 |','|---|---:|---|---:|---:|---:|---:|']
    for r in saved:
        b=baseline.get((r['site'],r['prior'],r['iteration']))
        for key in LABELS:
            g=r['groups'].get(key,{});bg=b['groups'].get(key,{}) if b else {}
            lines.append(f"| {r['site']} {r['result']} | {r['iteration']} | {LABELS[key]} | {fmt(g.get('count'))} | {fmt(g.get('opacity_median'))} | {fmt(bg.get('count'))} | {fmt(bg.get('opacity_median'))} |")
    Path('/docs/tables/monitor_v2_observations.md').write_text('\n'.join(lines)+'\n')
    print('monitor tables',len(observations),'observations',len(saved),'saved models',flush=True)

if __name__=='__main__':main()
