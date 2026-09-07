"""Read-only validation of the supplemental same-anchor native repeat contract."""
import argparse
import hashlib
import json
import os
from pathlib import Path

REPEAT_HELPER_SOURCE = Path(__file__).read_bytes()
REPEAT_HELPER_SHA256 = hashlib.sha256(REPEAT_HELPER_SOURCE).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_contract(contract, cfg, config_sha, layout, layout_sha, region, condition, phase,
                      runtime_image_id, allocator):
    expected = dict(schema='GEOGS_SUPPLEMENTAL_NATIVE_REPEAT_v1', task_id=cfg['task_id'],
                    repeat_id='native_repeat_1', supplemental_only=True,
                    output_directory='native_repeat_allocator_v2', condition_id='D005_Pnative',
                    start_iteration=8000, iterations=30000, seed=0, lambda_lod_anchor=0.005,
                    protection='native', scientific_verdict=None, scientific_config_sha256=config_sha,
                    runtime_layout_sha256=layout_sha, runtime_image_id=runtime_image_id, allocator=allocator,
                    new_seed=False, scientific_controls_changed=False, input_bytes_changed=False,
                    reference_accessed_for_this_decision=False)
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError('Supplemental repeat differs from its frozen native control or runtime contract')
    if (contract['regions'] != ['P1', 'P2', 'P3'] or set(contract['regions']) != set(cfg['regions'])
            or contract['phases'] != ['train', 'render', 'metrics', 'auxiliary']
            or region not in contract['regions'] or condition != 'D005_Pnative' or phase not in contract['phases']):
        raise ValueError('Only the three declared native repetitions and four declared phases are allowed')
    native = next(row for row in cfg['conditions'] if row['id'] == 'D005_Pnative')
    if native['lambda_lod_anchor'] != 0.005 or native['protection'] != 'native' or cfg['seed'] != 0:
        raise ValueError('Primary native scientific controls differ')
    if layout['revision'] != 'allocator_v2' or layout['allocator'] != allocator:
        raise ValueError('The supplemental repeat requires the fixed primary allocator_v2 layout')
    for name in contract['regions']:
        planned = contract['anchors'][name]
        primary = layout['anchors'][name]
        if planned['checkpoint_directory'] != primary['checkpoint_directory']:
            raise ValueError('Repeat checkpoint path differs from the primary common anchor')
        if planned.get('checkpoint_sha256') != primary.get('checkpoint_sha256'):
            raise ValueError('Repeat predeclared checkpoint identity differs from the primary layout')


def load_repeat_binding(config_path, layout_path, region, condition, phase, contract_path='/repeat_contract.json',
                        anchor_root='/anchor', gate_path='/anchor_gate.json', environment=None):
    environment = os.environ if environment is None else environment
    contract_path = Path(contract_path)
    if not contract_path.is_file():
        if environment.get('JBGS_REPEAT_ID') or environment.get('JBGS_REPEAT_CONTRACT_SHA256'):
            raise ValueError('Repeat environment requires the immutable mounted contract')
        return None
    cfg = json.loads(Path(config_path).read_text())
    layout = json.loads(Path(layout_path).read_text())
    contract = json.loads(contract_path.read_text())
    validate_contract(contract, cfg, sha(config_path), layout, sha(layout_path), region, condition, phase,
                      environment['JBGS_RUNTIME_IMAGE_ID'], environment['PYTORCH_CUDA_ALLOC_CONF'])
    digest = sha(contract_path)
    if environment.get('JBGS_REPEAT_ID') != contract['repeat_id'] or environment.get('JBGS_REPEAT_CONTRACT_SHA256') != digest:
        raise ValueError('Repeat identity or contract bytes differ from the launcher binding')
    anchor = json.loads((Path(anchor_root)/'receipt.json').read_text())
    gate = json.loads(Path(gate_path).read_text())
    if (anchor.get('iteration') != 8000 or anchor.get('after_protection_registration') is not True
            or gate.get('status') != 'EXACT_COMMON_ANCHOR_VERIFIED'
            or gate.get('region') != region or gate.get('runtime_layout_sha256') != sha(layout_path)
            or gate.get('checkpoint_sha256') != anchor.get('checkpoint_sha256')):
        raise ValueError('Repeat lacks the exact primary completed anchor and matching runtime gate')
    expected_anchor = contract['anchors'][region].get('checkpoint_sha256')
    if expected_anchor and anchor['checkpoint_sha256'] != expected_anchor:
        raise ValueError('Mounted anchor differs from its immutable supplemental identity')
    return dict(repeat_id=contract['repeat_id'], repeat_contract_sha256=digest, supplemental_only=True,
                repeat_anchor_checkpoint_sha256=anchor['checkpoint_sha256'],
                repeat_anchor_gate_sha256=sha(gate_path), repeat_helper_sha256=REPEAT_HELPER_SHA256)


def validate_primary_readiness(primary_runs, cfg, config_sha, layout_sha):
    checked = 0
    for region in cfg['regions']:
        for condition in cfg['conditions']:
            for phase in ('train', 'render', 'metrics', 'auxiliary'):
                path = Path(primary_runs)/region/condition['id']/(phase+'_receipt.json')
                receipt = json.loads(path.read_text())
                expected = dict(status='PASS', region=region, condition=condition['id'], phase=phase,
                                config_sha256=config_sha, runtime_layout_sha256=layout_sha)
                if any(receipt.get(key) != value for key, value in expected.items()) or receipt.get('repeat_id'):
                    raise ValueError('All primary phases must complete before supplemental scheduling: ' + str(path))
                checked += 1
    return checked


def require_repeat_receipt(receipt, binding):
    for key in ('repeat_id', 'repeat_contract_sha256'):
        expected = binding[key] if binding else None
        if receipt.get(key) != expected:
            raise ValueError('A prerequisite phase belongs to a different primary/repeat identity')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--runtime-layout', type=Path, required=True)
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--primary-runs', type=Path, required=True)
    parser.add_argument('--region', choices=('P1', 'P2', 'P3'), required=True)
    args = parser.parse_args()
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Readiness validation must run in Docker')
    cfg = json.loads(args.config.read_text())
    contract = json.loads(args.contract.read_text())
    layout = json.loads(args.runtime_layout.read_text())
    validate_contract(contract, cfg, sha(args.config), layout, sha(args.runtime_layout), args.region,
                      'D005_Pnative', 'train', os.environ['JBGS_RUNTIME_IMAGE_ID'], contract['allocator'])
    count = validate_primary_readiness(args.primary_runs, cfg, sha(args.config), sha(args.runtime_layout))
    print(json.dumps(dict(status='ALL_PRIMARY_PHASES_COMPLETE_REPEAT_READY', primary_phase_receipts=count,
                         repeat_id=contract['repeat_id'], repeat_contract_sha256=sha(args.contract),
                         region=args.region, scientific_verdict=None)))


if __name__ == '__main__':
    main()
