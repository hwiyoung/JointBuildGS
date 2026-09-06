"""Config-backed, read-only C stages after the declared B runs complete."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import traceback

from scripts.phd.p2_ab_v2 import c_common_appearance, c_evaluate, c_viewer_build, c_summarize


def main(args):
    config = json.loads(args.config.read_text())
    base = Path(config['artifact_root'])
    b_base = base/'phase-payloads/phd/p2_ab_v2'
    b_roots = [b_base/name for name in config['b_runs']]
    adapter = None
    if 'geometry_adapter_manifest' in config:
        manifest_path = base/config['geometry_adapter_manifest']
        audit_path = base/config['geometry_adapter_audit']
        manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        audit_hash = hashlib.sha256(audit_path.read_bytes()).hexdigest()
        adapter = json.loads(manifest_path.read_text())
        audit = json.loads(audit_path.read_text())
        if audit.get('status') != 'PASS' or not audit.get('checks') or not all(audit['checks'].values()):
            raise ValueError('Required corrected geometry adapter audit did not pass')
    for root in b_roots:
        if not (root/'result.json').is_file():
            raise ValueError(f'Completed B result required: {root}')
        result = json.loads((root/'result.json').read_text())
        if result.get('status') != 'COMPLETED_DEVELOPMENT':
            raise ValueError(f'B completion status mismatch: {root}')
        if 'required_geometry_contract' in config and result.get('geometry_contract') != config['required_geometry_contract']:
            raise ValueError(f'B corrected geometry contract mismatch: {root}')
        if adapter is not None:
            if result.get('geometry_adapter_hashes') != adapter['output_hashes']:
                raise ValueError(f'B adapter fingerprint differs from audited adapter: {root}')
            binding = result.get('geometry_adapter_audit', {})
            if (binding.get('sha256') != audit_hash or binding.get('adapter_manifest_sha256') != manifest_hash
                    or binding.get('cuda_source_hashes') != adapter['output_hashes']
                    or Path(binding.get('path', '')) != audit_path
                    or Path(binding.get('adapter_manifest_path', '')) != manifest_path):
                raise ValueError(f'B adapter audit binding differs from pinned audit: {root}')
            for filename, expected in [('geometry_adapter_audit.json', audit_hash),
                                       ('geometry_adapter_manifest.json', manifest_hash)]:
                if hashlib.sha256((root/filename).read_bytes()).hexdigest() != expected:
                    raise ValueError(f'B copied adapter evidence differs: {root/filename}')
            for filename, expected in adapter['output_hashes'].items():
                path = root/'source_snapshot/gsplat'/filename
                if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                    raise ValueError(f'B saved adapter source bytes differ: {path}')
        if 'expected_arms' in config:
            arms = result['arms']
            names = [a['arm'] for a in arms]
            if len(names) != len(set(names)) or set(names) != set(config['expected_arms'][root.name]):
                raise ValueError(f'B arm membership mismatch: {root}')
            if any(a.get('status') != 'COMPLETED_DEVELOPMENT' for a in arms):
                raise ValueError(f'Incomplete B arm: {root}')
        if 'expected_eval_image_ids' in config:
            views = json.loads((root/'views.json').read_text())['views']
            ids = [v['image_id'] for v in views if v['role']=='eval']
            if len(ids) != len(set(ids)) or set(ids) != set(config['expected_eval_image_ids']):
                raise ValueError(f'Frozen B evaluation-view membership mismatch: {root}')
    options = argparse.Namespace(
        b_root=b_roots, output=args.output, config=args.config, exclude_arm=config['exclude_arms'],
        common=base/config['common'], reference=base/config['reference'],
        prior_anchor=b_base/config['prior_anchor'])
    stage = dict(geometry=c_evaluate.main, appearance=c_common_appearance.main,
                 viewer=c_viewer_build.build, summary=c_summarize.main)[args.stage]
    try:
        stage(options)
    except Exception:
        if args.output.is_dir():
            with (args.output/'FAILED.json').open('x') as f:
                json.dump(dict(stage=args.stage, scientific_verdict=None, traceback=traceback.format_exc()), f, indent=2)
        raise
    finally:
        if args.output.is_dir() and not (args.output/'execution_config.json').exists():
            shutil.copyfile(args.config, args.output/'execution_config.json')
        if args.output.is_dir() and not (args.output/'pipeline_source_snapshot.py').exists():
            shutil.copyfile(__file__, args.output/'pipeline_source_snapshot.py')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--stage', choices=['geometry', 'appearance', 'viewer', 'summary'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args())
