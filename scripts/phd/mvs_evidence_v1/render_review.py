"""Deliver a reviewed browser UI without changing immutable numerical evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from datetime import datetime, timezone
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use('Agg')
from matplotlib import colormaps


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()


def main():
    if not Path('/.dockerenv').exists():raise RuntimeError('Docker required')
    ap=argparse.ArgumentParser();ap.add_argument('--attempt',type=Path,required=True);ap.add_argument('--review-name',default='review');a=ap.parse_args()
    if Path(a.review_name).name!=a.review_name:raise ValueError('Review name must be a single directory name')
    evidence=a.attempt/'evidence';out=a.attempt/a.review_name;out.mkdir(exist_ok=False)
    receipt=json.loads((evidence/'receipt.json').read_text())
    if receipt['status']!='PASS_OBSERVATION_DIAGNOSTIC':raise ValueError('Numerical evidence not passed')
    for row in receipt['outputs']:
        if sha(evidence/row['path'])!=row['sha256']:raise ValueError('Numerical output changed: '+row['path'])
    data=json.loads((evidence/'manifest.json').read_text());summaries=[]
    for region in data['regions']:
        for camera in region['cameras']:
            arrays_path=evidence/camera['arrays']
            with np.load(arrays_path,allow_pickle=False) as numeric:
                delta=numeric['delta']
                wide=colormaps['PuOr_r']((np.clip(np.nan_to_num(delta),-30,30)+30)/60)
                wide[...,3]=np.isfinite(delta)*.87
                wide_name=camera['id']+'_delta_wide.png'
                Image.fromarray((wide*255).astype('uint8'),'RGBA').save(out/wide_name)
            for key in ('photo','overview','arrays'):
                camera[key]='../evidence/'+camera[key]
            for layer in camera['layers']:
                layer['path']='../evidence/'+layer['path']
                if layer['id']=='validity':layer['legend']=[{'color':color,'label':label} for color,label in [('#9ca3af','둘 다 없음'),('#2563eb','Prior만'),('#d97706','MVS만'),('#7c3aed','둘 다 있음')]]
                else:layer['description']+=' · 표시 범위를 넘으면 색상이 포화됩니다. 표본 선택/원자료에서 실제 값을 확인하세요.'
            camera['layers'].insert(1,dict(id='delta_wide',label='1 · 깊이차 넓은 범위 (±30m)',path=wide_name,
                                         description='Prior − MVS camera-Z. ±5m 지도에서 포화되는 큰 차이를 비교하는 추가 표시. ±30m 밖도 포화되며 변화 판정 아님.',
                                         vmin=-30,vmax=30,units='camera-Z m',cmap='PuOr_r',
                                         legend=[dict(color=matplotlib.colors.to_hex(colormaps['PuOr_r'](v)),label=label) for v,label in [(0.,'≤ −30'),(.5,'0'),(1.,'≥ 30')]]))
            for case in camera['cases']:
                for key in ('figure','profile','patches'):
                    if case.get(key):case[key]='../evidence/'+case[key]
            summaries.append(dict(region=region['id'],camera=camera['id'],name=camera['name'],**camera['summary']))
    (out/'data.js').write_text('window.MVS_EVIDENCE='+json.dumps(data,ensure_ascii=False,allow_nan=False,separators=(',',':'))+';\n')
    template=Path('/repo/src/apps/mvs_evidence_v1/review.html');shutil.copy2(template,out/'index.html')
    (out/'summary.json').write_text(json.dumps(summaries,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    report=['# P1/P2/P3 Prior–MVS 단계별 관측 지도','',
            '`PHD-MVS-EVIDENCE-v1` · `PASS_OBSERVATION_DIAGNOSTIC` · `scientific_verdict: null`','',
            '기존 MVS/PGSR의 봉인 MVS·RGB·카메라·이웃 후보와 부모 GeoGS prior로 계산했다. '+
            '지역별 prior 피복과 카메라 위치 다양성으로 고른 train 3장씩 총 9장이다. '+
            '16픽셀 격자의 관측 진단과 48픽셀 격자의 깊이 비용곡선을 원사진에 겹쳐 표시한다.','',
            '| 지역/시점 | 두 깊이 존재 픽셀 | >0.5m 불일치 픽셀 | 사진 비교 가능한 격자점 | 비용곡선 가능/시도 지점 |',
            '|---|---:|---:|---:|---:|']
    for s in summaries:report.append(f'| {s["camera"]} | {s["both_pixels"]:,} | {s["candidate_counts"]["0.5"]:,} | {s["photo_comparable_points"]:,} / {s["grid_points"]:,} | {s["profile_comparable_points"]:,} / {s["profile_points"]:,} |')
    report+=['','사진 비교 가능은 같은 두 가설의 공통 픽셀/텍스처 지원 이웃이 2개 이상이라는 뜻이다. '+
             '그 이웃에서 실제 가림이 없거나 올바른 대응임을 인증한 값은 아니다. 비용곡선은 두 source의 '+
             '원 patch가 모두 완전하고, 모든 탐색 깊이·두 normal 가설에서 같은 complete patch를 갖는 '+
             '이웃이 2개 이상일 때만 표시한다.','',
             'MVS/평가영상의 독립성과 역사 COLMAP 생성 이웃은 복구되지 않았다. Source 내부 일치와 '+
             'Prior→MVS 호환성은 별도이며 어느 쪽도 독립적인 가시성 정답이 아니다. '+
             '0.5m 및 ZNCC min+.03은 진단 기준이며 변화 문턱/확률 신뢰구간이 아니다. '+
             '비용곡선 폭 0은 깊이 격자 한 점만 남았다는 뜻이다.','',
             '3D/Gaussian 선택·업데이트·학습 가중치는 아직 생성하지 않았다. 우선 각 위치의 '+
             '원사진, 불일치, 관측 지원, 원 patch, 이웃별 비용과 깊이곡선의 일관성을 검토한다.','',
             '브라우저 검증은 별도 QA receipt에 기록한다. 수치 원본은 ../evidence 안의 '+
             '카메라별 arrays.npz/camera.json과 receipt로 보존한다.']
    (out/'REPORT_ko.md').write_text('\n'.join(report)+'\n')
    delivery=dict(task_id='PHD-MVS-EVIDENCE-v1',status='PASS_REVIEW_RENDER',scientific_verdict=None,
                  created_at=datetime.now(timezone.utc).isoformat(),parent_receipt_sha256=sha(evidence/'receipt.json'),
                  template_sha256=sha(template),script_sha256=sha(__file__),
                  outputs=[dict(path=p.name,sha256=sha(p),bytes=p.stat().st_size) for p in sorted(out.iterdir()) if p.is_file()])
    (out/'receipt.json').write_text(json.dumps(delivery,indent=2)+'\n')
    print(json.dumps(dict(status=delivery['status'],out=str(out),cameras=len(summaries))))


if __name__=='__main__':main()
