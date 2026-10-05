"""Separate exact common-state restoration from later numeric trajectory variation."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_evidence(restore, step, comparison, anchor):
    """Validate restoration separately from data-dependent later CUDA draws.

    The frozen schedule selects cameras with Python RNG, while Gaussian splits
    consume a CUDA normal tensor sized by the selected split population. Later
    CUDA RNG *values* therefore cannot certify the initial restore. Structural
    changes to RNG state still fail; they are not Philox counter evolution.
    """
    if restore['status'] != 'EXACT_PRESTEP_RESTORE_AND_HOOK_PARITY' or step['status'] != 'PASS_ONE_NATIVE_STEP':
        raise ValueError('The common anchor is not verified exactly')
    if anchor['checkpoint_sha256'] != restore['checkpoint_sha256']:
        raise ValueError('The probe restored a different anchor')
    must_match = {'rng', 'iteration', 'train_order', 'test_order', 'viewpoint_stack',
                  'optimization', 'implementation_hashes'}
    cuda_rows = []
    for row in comparison['entries']:
        parts = row['path'].strip('/').split('/')
        cuda_state = parts[:2] == ['rng', 'torch_cuda']
        if cuda_state:
            cuda_rows.append(row)
        if row['equal']:
            continue
        # A same-shape/dtype RNG tensor can differ after a different number of
        # random draws. Missing devices/keys or altered tensor layouts cannot.
        cuda_value_difference = (cuda_state and len(parts) == 3 and parts[2].isdigit()
                                 and row.get('kind') == 'tensor'
                                 and not row.get('shape_or_dtype_mismatch', False))
        if parts[0] in must_match and not cuda_value_difference:
            raise ValueError('Continuation changed required RNG structure, CPU/Python/NumPy RNG, '
                             'iteration, camera order, optimization or source: ' + row['path'])
    differences = [row for row in cuda_rows if not row['equal']]
    return {
        'policy': 'LATER_CUDA_RNG_VALUE_EVOLUTION_IS_DIAGNOSTIC_ONLY',
        'status': 'UNRESOLVED_BRANCH_DYNAMICS' if differences else 'EXACT',
        'all_equal': not differences,
        'compared_entries': len(cuda_rows),
        'nonmatching_entries': differences,
        'cause_established': False,
        'interpretation': ('Later CUDA RNG values differ. Split-selection-dependent random tensor sizes '
                           'can change RNG advancement, but the cause of this difference was not measured.'
                           if differences else 'Later CUDA RNG values match; this does not establish exact model trajectory parity.'),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--region', required=True, choices=('P1', 'P2', 'P3'))
    args = parser.parse_args()
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Docker is required')
    root = Path('/parity')
    restore_path = root/'restore_probe/restore_probe.json'
    step_path = root/'restore_probe/one_step_probe.json'
    continuation_path = root/'continuation_comparison.json'
    restore, step, comparison = [json.loads(path.read_text()) for path in (restore_path, step_path, continuation_path)]
    anchor = json.loads(Path('/anchor_receipt.json').read_text())
    cuda_diagnostic = validate_evidence(restore, step, comparison, anchor)
    gate = {'scientific_verdict':None,'region':args.region,
            'status':'EXACT_COMMON_ANCHOR_VERIFIED',
            'gate_policy':'INITIAL_RESTORE_STRICT_LATER_CUDA_RNG_DIAGNOSTIC_v2',
            'gate_script_sha256':sha(__file__),
            'runtime_layout_sha256':sha('/runtime_layout.json') if Path('/runtime_layout.json').is_file() else None,
            'checkpoint_sha256':anchor['checkpoint_sha256'],
            'restore_probe_sha256':sha(restore_path),'one_step_probe_sha256':sha(step_path),
            'continuation_comparison_sha256':sha(continuation_path),
            'continuation_exact':comparison['all_equal'],
            'continuation_nonmatching_entries':comparison['nonmatching_entries'],
            'continuation_cuda_rng':cuda_diagnostic,
            'interpretation':'exact starting state, protection hooks and same-anchor PLY/render verified; one native step verifies camera order, Adam step increment, finite model/loss and counts, not every updated tensor byte; later numerical divergence remains reported without an exact trajectory parity claim',
            'independent_trajectory_parity_claim':False}
    with (root/'anchor_gate.json').open('x') as f:
        json.dump(gate,f,indent=2)
    print(json.dumps(gate))


if __name__ == '__main__':
    main()
