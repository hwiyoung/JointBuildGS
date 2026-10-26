"""Describe zero-inclusive calibration medians; never reselect strength."""
import json
from pathlib import Path
import numpy as np
from inputs import OUT,save,sha

def main():
    selection=OUT/'checks/lambda_selection.json';original=sha(selection);rows=[]
    for unit in sorted((OUT/'runs/B173nb_b10').glob('lt_cal_*')):
        p=json.loads((unit/'PASS.json').read_text());path=unit/f"attempt_{p['attempt']}/model/monitor/losstrain_gradients.jsonl"
        records=[json.loads(x) for x in path.read_text().splitlines()]
        for term in ['rgb','depth']:
            values=[x['values'][term] for x in records]
            visible=[x['visible_median'] for x in values if x['visible_median'] is not None]
            shares=[x['positive_gaussians']/x['gaussians'] for x in values]
            rows.append(dict(run=unit.name,term=term,iterations=len(values),
                zero_all_median_iterations=sum(x['all_median']==0 for x in values),
                positive_gradient_share_median=float(np.median(shares)),positive_gradient_share_min=float(np.min(shares)),positive_gradient_share_max=float(np.max(shares)),
                visible_gradient_median_of_medians=float(np.median(visible)) if visible else None,
                selection_use=False,source=str(path),source_sha256=sha(path)))
    save('/docs/tables/calibration_gradient_audit.json',dict(rows=rows,selection_sha256=original,
        limitation='zero-inclusive centre-gradient medians are zero for both terms; 0/0 ratio is unavailable; low-gradient condition evaluated as the pre-frozen strict inequality depth < 0.1*rgb. Visible-only summaries are descriptive, not a replacement criterion.',scientific_verdict=None))
    assert sha(selection)==original
    lines=['# 짧은 학습 기울기 기록의 한계','',
        '전체 가우시안(0 포함) 기준 사진·깊이 기울기 중앙값이 모두 0이다. 따라서 두 중앙값의 비율은 확인 불가이고 이 통계로 세기를 구분하지 못했다. 학습 전 잠금에 적은 엄격 부등식 `깊이 < 0.1 × 사진`은 0 < 0이므로 거짓이다. 선택 규칙과 λ는 사후 변경하지 않았다. 아래 보이는 가우시안 통계는 기록용이며 선택에 쓰지 않았다.','',
        '| 실행 | 항 | 양의 기울기 비율 중앙값(%) | 보이는 가우시안 기울기 중앙값 |','|---|---|---:|---:|']
    for r in rows:lines.append(f"| {r['run']} | {r['term']} | {100*r['positive_gradient_share_median']:.4f} | {r['visible_gradient_median_of_medians']} |")
    Path('/docs/tables/calibration_gradient_audit.md').write_text('\n'.join(lines)+'\n')
    print('gradient limitation recorded; selected lambda unchanged',flush=True)

if __name__=='__main__':main()
