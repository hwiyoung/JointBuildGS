"""Host stdlib only: verify runtime/QA receipts and record the live viewer."""
from datetime import datetime,timezone
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--viewer-id',default='PHD-SOURCE-CANDIDATE-VIEWER-v1')
    parser.add_argument('--qa-id',default='qa-v1');args=parser.parse_args()
    repo=Path(__file__).resolve().parents[3];backend=repo.parent/'JointBuildGS-artifacts'
    run=backend/'phase-payloads/phd/source_candidate_viewer_v1'/args.viewer_id
    launch=read(run/'launch.json');qa=read(run/'browser_qa'/args.qa_id/'browser_qa.json')
    if qa['status']!='PASS_ACTUAL_VIEWER_DISPLAY_AND_CONTROLS' or qa['failed_checks']:
        raise ValueError('Passing actual browser evidence required')
    ledger=read(run/'source/SOURCE_MANIFEST.json')
    for rel,digest in ledger.items():
        if sha(run/'source'/rel)!=digest:raise ValueError('Source snapshot changed: '+rel)
    live=json.load(urlopen(launch['url']+'api/manifest',timeout=20))
    if live['method_seal_sha256']!=launch['source_method_seal_sha256']:
        raise ValueError('Live viewer does not match source method')
    root=backend/launch['config']['source_run']
    method=read(root/'run/method_seal.json')
    for rel,digest in method['files'].items():
        if sha(root/'run'/rel)!=digest:raise ValueError('Scientific method output changed: '+rel)
    screenshots={str(p.relative_to(backend)):dict(sha256=sha(p),bytes=p.stat().st_size)
                 for p in sorted((run/'browser_qa'/args.qa_id).glob('*.png'))}
    result=dict(schema='jointbuildgs.source_candidate.viewer_result.v1',task_id=launch['config']['task_id'],
        technical_status='LIVE_AND_BROWSER_VERIFIED',scientific_verdict=None,
        viewer_id=args.viewer_id,qa_id=args.qa_id,url=launch['url'],photo_entry_url=launch['url']+'?region=P2&stage=2&cell=5',
        artifact_root_relative=str(run.relative_to(backend)),backend_local_path=str(backend),
        created_at=datetime.now(timezone.utc).isoformat(),
        method_seal_sha256=launch['source_method_seal_sha256'],
        source_manifest_sha256=sha(run/'source/SOURCE_MANIFEST.json'),snapshot_file_count=len(ledger),
        launch_sha256=sha(run/'launch.json'),browser_qa_sha256=sha(run/'browser_qa'/args.qa_id/'browser_qa.json'),
        browser_checks=qa['check_count'],failed_checks=0,screenshots=screenshots,
        method_output_hashes_unchanged=True,read_only_mounts=launch['mounts'],
        region_totals={r['id']:r['summary']['decision'] for r in live['regions']},
        accessibility_scope='Loopback URL tested from host and dedicated Docker Chromium; external LAN not claimed.')
    folder=repo/'artifacts/manifests/phd/source_candidate_viewer_v1';folder.mkdir(parents=True,exist_ok=True)
    manifest=folder/'technical_result_manifest_v1.json'
    with manifest.open('x') as stream:json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    doc=repo/'docs/experiments/phd/source_candidate_viewer_v1/TECHNICAL_RETURN_ko_v1.md'
    text=f'''# P1/P2/P3 단계별 뷰어 — 기술 검증 결과

- 상태: 실행 및 실제 브라우저 검증 완료. `scientific_verdict: null`.
- [큰 원본 사진부터 열기]({result['photo_entry_url']}) · [첫 단계부터 열기]({result['url']}).
- 영역별 후보 입력·관측 평가·소스 판단, 전체 셀 탐색, 원본 사진 확대/이동/큰 보기,
  영상쌍·패치 변경, 실제 점군 3D 회전/이동/확대·소스 토글을 제공한다.
- 브라우저 검사 **{qa['check_count']}개 통과**, 화면 캡처 **{len(screenshots)}개**를 보존했다.
- P1/P2/P3 × 3단계와 대표·오판·관측 부재 사례를 확인했다.
  1600/1024/768 px 화면과 빠른 영역 전환도 점검했다.
- 고정 method 파일 해시를 재검사했으며 원 연구 결과는 바뀌지 않았다.
- 서버는 기존 뷰어와 별도로 127.0.0.1:8903에서 실행한다.
  검증 범위는 이 컴퓨터의 브라우저와 Docker Chromium이다.

원본 사진은 보존된 1400×1013 JPG이고, 검사 패치의 확대는 원영상 복원 또는
새로운 영상 세부의 생성이 아니다. 소스 선택·기하 정확도·GS 성능은 재평가하지 않았다.

- [사용·재현 안내](README_ko_v1.md)
- [실행 및 검증 이슈](ISSUES_ko_v1.md)
- [검증 receipt]({run}/browser_qa/{args.qa_id}/browser_qa.json)
- [artifact manifest]({manifest})
'''
    with doc.open('x') as stream:stream.write(text)
    print(json.dumps(dict(status='RECORDED',url=result['photo_entry_url'],checks=qa['check_count'],screenshots=len(screenshots),manifest=str(manifest))))


if __name__=='__main__':main()
