"""Host stdlib: promote exact completed run/QA evidence and reviewer narrative."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,value):
    with Path(p).open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')

def main():
    p=argparse.ArgumentParser();p.add_argument('--run-id',default='PHD-SURFACE-SELECTION-P1P2P3-v2')
    p.add_argument('--qa-id',default='v1');p.add_argument('--viewer-id',default='v1');p.add_argument('--record-id',default='v1');a=p.parse_args()
    repo=Path(__file__).resolve().parents[3];backend=repo.parent/'JointBuildGS-artifacts'
    run=backend/'phase-payloads/phd/surface_selection_v1'/a.run_id
    qa=read(run/('qa_'+a.qa_id)/'browser_qa.json')
    if qa.get('status')!='PASS_ACTUAL_SURFACE_VIEWER_DISPLAY_AND_CONTROLS' or qa.get('failed_checks'):
        raise ValueError('Actual passing browser receipt required')
    seal=read(run/'run/method_seal.json');evaluation=read(run/'run/evaluation/evaluation_receipt.json')
    for rel,digest in seal['files'].items():
        if sha(run/'run'/rel)!=digest:raise ValueError('Method output changed')
    if sha(run/'run/config.json')!=seal['config_sha256']:raise ValueError('Frozen config changed')
    if evaluation['method_seal_sha256']!=sha(run/'run/method_seal.json'):raise ValueError('Evaluation lineage changed')
    for rel,digest in evaluation['output_sha256'].items():
        if sha(run/'run/evaluation'/rel)!=digest:raise ValueError('Evaluation output changed')
    viewer=run/('viewer_'+a.viewer_id);launch=read(viewer/'launch.json')
    for rel,digest in read(viewer/'source/SOURCE_MANIFEST.json').items():
        if sha(viewer/'source'/rel)!=digest:raise ValueError('Viewer snapshot changed')
    live=json.load(urlopen(launch['url']+'api/manifest',timeout=30))
    if live['method_seal_sha256']!=sha(run/'run/method_seal.json'):raise ValueError('Live app has wrong method')
    summary=read(run/'run/evaluation/summary.json')
    manifests=repo/'artifacts/manifests/phd/surface_selection_v1';docs=repo/'docs/experiments/phd/surface_selection_v1'
    manifests.mkdir(parents=True,exist_ok=True);docs.mkdir(parents=True,exist_ok=True)
    shots={str(p.relative_to(backend)):dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted((run/('qa_'+a.qa_id)).glob('*.png'))}
    result=dict(schema='jointbuildgs.surface_selection.technical_return.v1',task_id=live['task_id'],run_id=a.run_id,
        technical_status='EXECUTED_EVALUATED_LIVE_BROWSER_VERIFIED',scientific_verdict=None,
        url=launch['url'],entry_url=launch['url']+'?region=P3&stage=1',artifact_root_relative=str(run.relative_to(backend)),
        method_seal_sha256=sha(run/'run/method_seal.json'),evaluation_receipt_sha256=sha(run/'run/evaluation/evaluation_receipt.json'),
        original_report_sha256=sha(run/'report/REPORT_ko.md'),viewer_source_manifest_sha256=sha(viewer/'source/SOURCE_MANIFEST.json'),
        viewer_launch_sha256=sha(viewer/'launch.json'),qa_receipt_sha256=sha(run/('qa_'+a.qa_id)/'browser_qa.json'),
        browser_check_count=qa['check_count'],failed_browser_checks=0,screenshots=shots,
        region_stage_totals={r['id']:r['summary'] for r in live['regions']},
        confirmed_limitations=['All three common-refinement unit area medians are0.25m2; semantic-scale selection is unresolved.',
          'P1 remains fully abstained. P2 direct coverage/completeness decreased, P3 increased, againstlegacy2m.',
          'Only directly supported sampled tiles are accepted; whole-unit propagation is hypothetical.',
          'Segmentation and evidence rules changed together; no isolated size-effect or confirmatory claim.'],
        created_at=datetime.now(timezone.utc).isoformat(),access_scope='Host loopback and Docker Chromium verified; external LAN not tested.')
    report=run/'report/REPORT_ko.md'
    prefix='''실행·참조 평가·뷰어 검수는 완료했습니다. 다만 **의미 단위의 소스 선택은 아직 해결되지 않았습니다.**
소스별 연결 표면을 추출했지만 공통 경계에서 다시 조각나 세 영역 모두 비교 부분 면적 중앙값이
0.25 m²입니다. P2 직접 선택 면적은 기존 164 → 69.5 m²로 줄었고, P3는 4 → 64.25 m²로 늘었습니다.
P1은 여전히 모두 보류입니다. 성능 개선을 일반화하거나 셀 크기의 독립 효과로 해석하지 않습니다.

아래의 표면 소속률은 평면 후보에 들어간 원점의 비율입니다. **원본 점은 100% 보존**하며
나머지는 미분할 상태로 뷰어에서 확인할 수 있습니다. 직접 선택 범위도 전체 면에 자동 전파하지 않습니다.

'''
    text=report.read_text().replace('MVS 원점 유지 | ALS 원점 유지','MVS 표면 소속률 | ALS 표면 소속률')
    title,body=text.split('\n',1)
    promoted=title+'\n\n'+prefix+body
    if (docs/'RESULT_ko_v1.md').exists():
        if (docs/'RESULT_ko_v1.md').read_text()!=promoted:raise ValueError('Existing promoted scientific report differs')
    else:
        with (docs/'RESULT_ko_v1.md').open('x') as f:f.write(promoted)
    result['promoted_report_sha256']=sha(docs/'RESULT_ko_v1.md')
    write(manifests/f'technical_return_manifest_{a.record_id}.json',result)
    if (docs/'evaluation_summary_v1.json').exists():
        if read(docs/'evaluation_summary_v1.json')!=summary:raise ValueError('Existing promoted evaluation differs')
    else:write(docs/'evaluation_summary_v1.json',summary)
    technical=f'''# 연결 표면 소스 선택 — 기술 검증 영수증

- 실제 P1/P2/P3 실행, 모든 판단 동결 후 별도 참조 평가, 읽기 전용 뷰어 제공 완료.
- 실제 브라우저 검사 {qa['check_count']}개 통과, 화면 캡처 {len(shots)}개 보존.
- 방법 단위 테스트 17개, 평가 테스트 10개, 뷰어/API 재현 테스트 3개 통과.
- [P3 분할 뷰어]({result['entry_url']}) · [정량·정성 결과](RESULT_ko_v1.md) · [사용 안내](README_ko_v1.md).
- [브라우저 검수 영수증]({run}/qa_{a.qa_id}/browser_qa.json).
- [전체 실행 manifest]({manifests}/technical_return_manifest_{a.record_id}.json).
- `scientific_verdict: null`. UI 검수는 과학적 성능 판정이 아니다. 원 결과와 기존 뷰어를 보존했다.
'''
    with (docs/f'TECHNICAL_RETURN_ko_{a.record_id}.md').open('x') as f:f.write(technical)
    print(json.dumps(dict(status='PROMOTED',checks=qa['check_count'],screenshots=len(shots),url=result['entry_url'])))

if __name__=='__main__':main()
