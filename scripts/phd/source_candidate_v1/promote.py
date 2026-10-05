"""Host-stdlib-only integrity verification, copy and artifact resolver receipt."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(4*1024*1024),b''): digest.update(chunk)
    return digest.hexdigest()
def read(path): return json.loads(Path(path).read_text())


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',default='PHD-SOURCE-CANDIDATE-P1P2P3-v1')
    args=parser.parse_args();repo=Path(__file__).resolve().parents[3]
    backend=repo.parent/'JointBuildGS-artifacts';root=backend/'phase-payloads/phd/source_candidate_v1'/args.run_id
    for receipt_path,field in [(root/'run/method_seal.json','files'),
                               (root/'run/evaluation/evaluation_receipt.json','output_sha256'),
                               (root/'report/report_receipt.json','files')]:
        for name,digest in read(receipt_path)[field].items():
            if sha(receipt_path.parent/name)!=digest: raise ValueError('Changed artifact: '+name)
    fm=read(root/'figures/figure_manifest.json')
    for figure in fm['figures']:
        for record in figure['files']:
            local=root/Path(record['path']).relative_to('/output')
            if sha(local)!=record['sha256']: raise ValueError('Changed figure: '+str(local))
    if len(fm['figures'])!=17: raise ValueError('Incomplete figure collection')
    docs=repo/'docs/experiments/phd/source_candidate_v1';docs.mkdir(parents=True,exist_ok=True)
    for name in ('RESULT_ko_v1.md','analysis.json'):
        target=docs/name
        if target.exists(): raise FileExistsError(target)
        shutil.copy2(root/'report'/name,target)
        if name.endswith('.md'):
            target.write_text(target.read_text().replace('정상 방향','법선 방향'))
    manifests=repo/'artifacts/manifests/phd/source_candidate_v1';manifests.mkdir(parents=True,exist_ok=True)
    payload={}
    for folder in ('run','figures','report'):
        for path in sorted((root/folder).rglob('*')):
            if path.is_file(): payload[str(path.relative_to(backend))]=dict(sha256=sha(path),bytes=path.stat().st_size)
    stage_receipts={stage:read(root/(stage+'_launch.json')) for stage in ('method','evaluation','figures','report')}
    analysis=read(root/'report/analysis.json')
    result=dict(schema='jointbuildgs.source_candidate.technical_result.v1',task_id=analysis['task_id'],
        technical_status='COMPLETED',capability_status='PARTIAL_LOW_COVERAGE',scientific_verdict=None,
        backend='JBGS_ARTIFACT_ROOT',backend_local_path=str(backend),
        root_relative=str(root.relative_to(backend)),created_at=datetime.now(timezone.utc).isoformat(),
        method_seal_sha256=sha(root/'run/method_seal.json'),stages=analysis['stages'],
        package_test_counts=dict(method=27,evaluation=9),figure_count=len(fm['figures']),
        payload=payload,stage_launch_receipts=stage_receipts,
        source_snapshots={stage:sha(root/(stage+'_source/SOURCE_MANIFEST.json')) for stage in stage_receipts},
        failed_attempts=[str(p.relative_to(backend)) for p in sorted((root/'failed_attempts').iterdir())],
        promoted_files={str((docs/name).relative_to(repo)):sha(docs/name) for name in ('RESULT_ko_v1.md','analysis.json')},
        promotion_script_sha256=sha(__file__),
        promoted_editorial_changes=['Korean surface-normal terminology corrected: 정상 방향 to 법선 방향; no numeric/artifact changes.'],
        limitations=['Development evaluation only; shared MVS/image lineage.',
                     'Prior selection in large-discrepancy regions not established.',
                     'Fixed supplied pose/registration and UAS datum uncertainty; no calibrated absolute accuracy.',
                     'No GS training, surface update or scientific verdict in this task.'])
    target=manifests/'technical_result_manifest_v1.json'
    with target.open('x') as stream: json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps(dict(status='VERIFIED_AND_PROMOTED',manifest=str(target),artifacts=len(payload),figures=len(fm['figures']))))


if __name__=='__main__':main()
