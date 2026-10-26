"""8.6: exact per-image averages, original evaluation records, own all-view readouts."""
import csv
import json
from pathlib import Path
from inputs import PH,S1,OUT,SITES,PRIORS,save,sha

def main():
    rows=[]
    for site in SITES:
        for prior in PRIORS:
            roots=[(f'nojudge_{prior}_s0',PH/'main_stage3_v1/PHD-MAIN-STAGE3-v1/runs'/site/f'nojudge_{prior}_s0'),
                *[(f'prop_{prior}_s{i}',S1/'stage1'/site/f'prop_{prior}_s{i}') for i in [0,1]],
                *[(p.name,p) for p in sorted((OUT/'runs'/site).glob('lt_*_'+prior+'_s0')) if (p/'post_PASS.json').exists()]]
            for result,root in roots:
                q=root/'post/quality.json';t=(root/'post/train_quality.json' if result.startswith('lt_') else OUT/'photo'/site/result/'train_quality.json')
                v=json.loads(q.read_text()) if q.exists() else None
                train=json.loads(t.read_text()) if t.exists() else None
                N=len(v['per_view']) if v else 0
                row=dict(site=site,prior=prior,result=result,eval_views=N,
                    eval_psnr_db=sum(x['psnr'] for x in v['per_view'])/N if N else None,
                    eval_ssim=sum(x['ssim'] for x in v['per_view'])/N if N else None,
                    training_views=train['views'] if train else 0,train_psnr_db=train['mean_psnr_db'] if train else None,
                    eval_source=str(q),eval_sha256=sha(q) if q.exists() else None,
                    train_source=str(t) if t.exists() else None,train_sha256=sha(t) if t.exists() else None,
                    unavailable=None if train and v else 'all-training-view readout pending' if v else 'evaluation record absent',
                    origin='[이 발주에서 냄]: existing per-view means recomputed without rounding; training readouts measured separately')
                rows.append(row)
    baseline={(r['site'],r['prior']):r for r in rows if r['result'].startswith('nojudge')}
    for r in rows:
        b=baseline.get((r['site'],r['prior']));r['eval_psnr_minus_nojudge_db']=r['eval_psnr_db']-b['eval_psnr_db'] if b and r['eval_psnr_db'] is not None and b['eval_psnr_db'] is not None else None
    save('/docs/tables/photo.json',dict(rows=rows,scientific_verdict=None))
    with Path('/docs/tables/photo.csv').open('w') as f:
        w=csv.DictWriter(f,list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    lines=['# 사진 지표','','평가 영상은 기존과 같은 목록이다. 저장된 각 영상 값을 평균해 반올림 전 값을 보존했다. 학습 영상은 전체 영상 PSNR의 산술평균이다.','',
        '| 단위 | 사전 | 결과 | 평가 N | PSNR dB | SSIM | 학습 N | 학습 PSNR dB |','|---|---|---|---:|---:|---:|---:|---:|']
    for r in rows:
        fmt=lambda x:'확인 불가' if x is None else f'{x:.5f}'
        lines.append(f"| {r['site']} | {r['prior']} | {r['result']} | {r['eval_views']} | {fmt(r['eval_psnr_db'])} | {fmt(r['eval_ssim'])} | {r['training_views']} | {fmt(r['train_psnr_db'])} |")
    Path('/docs/tables/photo.md').write_text('\n'.join(lines)+'\n');print('photo rows',len(rows),flush=True)

if __name__=='__main__':main()
