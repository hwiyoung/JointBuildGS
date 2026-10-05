"""Atomic combined six-condition viewer manifest; no model or training writes."""
from pathlib import Path
import json
import os
from datetime import datetime,timezone


def aggregate(root):
    root=Path(root); manifests=[json.loads((root/r/'manifest.json').read_text()) for r in ['P2','P3']]
    count=sum(m['run_status']['completed'] for m in manifests)
    value=dict(schema='region_weight_comparison_v1',scientific_verdict=None,task_id='PHD-P2P3-REGION-WEIGHT-v1',
        generated_at=datetime.now(timezone.utc).isoformat(),regions=[r for m in manifests for r in m['regions']],
        run_status=dict(completed=count,total=6,queue_status=' / '.join(m['run_status']['queue_status'] for m in manifests),label=f'최종 결과 {count}/6 등록 · 완료되는 조건부터 표시'),
        surface_contract=dict(label='동일 raw RGB TSDF512 · 조건별 30k 최종 결과 · 추출 크기는 대상별 고정',parameters={m['regions'][0]['id']:m['surface_contract']['parameters'] for m in manifests}),
        downloads=[dict(label='P2/P3 실제 수동 영역도',url='/app/manual_regions.html')])
    temp=root/f'manifest.{os.getpid()}.tmp';temp.write_text(json.dumps(value,ensure_ascii=False,indent=2));os.replace(temp,root/'manifest.json')
    return value


if __name__=='__main__':aggregate('/viewer')
