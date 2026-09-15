"""Bind the verified photo-overlay release, browser QA, and final review records."""
import argparse
import hashlib
import json
import platform
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy
import PIL


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(attempt, repository):
    def read(name):
        return json.loads((attempt / name).read_text())
    cfg = read('config.json')
    build = read('build_receipt.json')
    publication_name = cfg['publication_name'] + '_publication.json'
    publication = read(publication_name)
    qa = read('qa_v1/receipt.json')
    assert build['status'] == 'PASS_VIEWER_DATA_AND_NATIVE_GEOMETRY'
    assert publication['status'] == 'PASS_LOCAL_VIEWER_PUBLICATION'
    assert publication['build_receipt_sha256'] == sha(attempt / 'build_receipt.json')
    assert qa['status'] == 'PASS' and all(row['pass'] for row in qa['checks'])
    assert qa['url'].split('?')[0] == publication['url']
    has_reaudit = (attempt / 'audit_receipt.json').exists()
    extra_receipts = []
    if has_reaudit:
        audit = read('audit_receipt.json')
        entry = read('entry_link_receipt.json')
        entry_qa = read('qa_entry_v1/receipt.json')
        assert audit['status'] == 'PASS_ALL_20_MVS_CASE_REAUDIT'
        assert entry['status'] == 'PASS_RETAINED_ENTRY_LINKS'
        assert entry_qa['status'] == 'PASS' and all(row['pass'] for row in entry_qa['checks'])
        extra_receipts = ['audit_receipt.json', 'entry_retention_review.json', 'entry_link_receipt.json', 'qa_entry_v1/receipt.json']
    for relative, digest in publication['files'].items():
        assert sha(attempt / 'releases' / cfg['publication_name'] / relative) == digest
    for relative, digest in publication['application_sha256'].items():
        assert sha(repository / 'src/apps/local_weight_sites_v1' / relative) == digest
    for screenshot in qa['screenshots']:
        assert sha(attempt / 'qa_v1' / screenshot['name']) == screenshot['sha256']
    snapshot = attempt / 'completion_sources'
    snapshot.mkdir()
    paths = [p for directory in ['scripts/phd/local_weight_sites_v1', 'src/apps/local_weight_sites_v1',
                                'configs/phd/local_weight_sites_v1', 'docs/experiments/phd/local_weight_sites_v1',
                                'artifacts/manifests/phd/local_weight_sites_v1']
             for p in (repository / directory).iterdir() if p.is_file()]
    bindings = {}
    for path in paths:
        relative = path.relative_to(repository)
        destination = snapshot / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        bindings[str(relative)] = sha(path)
    receipt = dict(status='PASS_MVS_REAUDIT_AND_VIEWER_ENTRY_RECOVERY' if has_reaudit else 'PASS_EXACT_PHOTO_POINT_OVERLAY_AND_REVIEW_REVISION', task_id=cfg['task_id'],
        completed_utc=datetime.now(timezone.utc).isoformat(), scientific_verdict=None,
        url=publication['url']+'?case=C10', retained_cases=20, mvs_primary_review=['C10'],
        da3_primary_review=cfg.get('da3_primary_review',['C03','C04','C05','C06','C07']), facade_correspondence_held=['W019'],
        mvs_secondary_preservation_review=['C05'] if has_reaudit else [],
        photo_views=len(build['photo_projection_checks']), browser_checks=len(qa['checks']),
        http_verified_files=publication['http_sha256_verified_count'], screenshots=len(qa['screenshots']),
        receipt_sha256={name:sha(attempt / name) for name in ['build_receipt.json', publication_name, 'qa_v1/receipt.json']+extra_receipts},
        source_sha256=bindings, versions=dict(python=platform.python_version(), numpy=numpy.__version__, pillow=PIL.__version__),
        runtime_image='sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e',
        browser_image=(attempt / 'qa_v1/image_id.txt').read_text().strip(),
        original_geometry_and_metrics_changed=False, original_release_snapshots_changed=False,
        live_old_entry_html_redirected=has_reaudit, old_entry_bytes_archived=has_reaudit, training_changes=False)
    if has_reaudit:
        receipt.update(mvs_status_counts=audit['status_counts'], entry_browser_checks=len(entry_qa['checks']),
                       connection_scope='Server HTTP and CPU browser verified; user-side port forwarding not directly observable')
    target = attempt / 'completion_receipt.json'
    with target.open('x') as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({key:receipt[key] for key in ['status','photo_views','browser_checks','http_verified_files']}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--attempt', type=Path, required=True)
    parser.add_argument('--repository', type=Path, required=True)
    args = parser.parse_args()
    main(args.attempt, args.repository)
