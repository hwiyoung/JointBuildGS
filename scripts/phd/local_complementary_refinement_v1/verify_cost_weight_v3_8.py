#!/usr/bin/env python3
"""Persist an isolated CPU algebra receipt; never read scenes or start training."""
import argparse
import hashlib
import json
import platform
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--image', required=True)
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    assert cfg['training_execution_enabled'] is False
    assert cfg['scientific_verdict'] is None
    assert cfg['evidence']['observation_gate_provider'] is None
    assert cfg['docker_image'] == args.image
    assert [cfg['evidence'][key] for key in (
        'ramp_support_full_cost', 'ramp_neutral_cost', 'ramp_refutation_full_cost'
    )] == [.1, .3, .5], 'This verifier binds the fixed v3.8 algebra only.'
    args.output.mkdir(parents=True, exist_ok=False)
    suite = unittest.defaultTestLoader.loadTestsFromName(
        'tests.phd.local_complementary_refinement_v1.test_source_weight_v3_8'
    )
    with (args.output / 'tests.log').open('w') as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    import numpy as np
    paths = [args.config.resolve(), ROOT / cfg['runtime_source'],
             ROOT / cfg['test_source'], Path(__file__).resolve()]
    receipt = {
        'task_id': cfg['task_id'],
        'status': 'PASS_ALGEBRA_ONLY' if result.wasSuccessful() else 'FAIL_ALGEBRA',
        'scientific_verdict': None,
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'commit': args.commit,
        'source_state': 'additive_uncommitted_files_bound_by_sha256',
        'docker_image': args.image,
        'python': platform.python_version(), 'numpy': np.__version__,
        'resources': cfg['resources'],
        'tests_run': result.testsRun,
        'failures': len(result.failures), 'errors': len(result.errors),
        'scene_inputs_read': False, 'gt_read': False,
        'training_executed': False, 'observation_gate_validated': False,
        'gaussian_update_validated': False,
        'inputs_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        'test_log_sha256': hashlib.sha256((args.output / 'tests.log').read_bytes()).hexdigest(),
        'argv': sys.argv,
    }
    (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({key: receipt[key] for key in ('status','tests_run','failures','errors')}))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
