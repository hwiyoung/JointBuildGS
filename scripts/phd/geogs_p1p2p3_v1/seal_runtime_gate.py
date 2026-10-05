"""Verify measured source/runtime prerequisites without exposing UAS."""
import hashlib
import json
from pathlib import Path


def main():
    if not Path('/.dockerenv').exists() or Path('/reference').exists():
        raise RuntimeError('Use isolated reference-free Docker')
    root = Path('/task')
    requirements = {
        'native_example_route_8000_v1/receipt.json':'PASS_NATIVE_8000_ROUTE',
        'native_example_parity_v1/restore_probe_retry_v2/restore_probe.json':'EXACT_PRESTEP_RESTORE_AND_HOOK_PARITY',
        'native_example_parity_v1/restore_probe_retry_v2/one_step_probe.json':'PASS_ONE_NATIVE_STEP'}
    bound = []
    for relative, status in requirements.items():
        content = (root/relative).read_bytes()
        record = json.loads(content)
        if record['status'] != status:
            raise ValueError(f'Required measured gate failed: {relative}')
        bound.append({'path':relative,'sha256':hashlib.sha256(content).hexdigest(),'status':status})
    for region in ('P1','P2','P3'):
        relative = f'inputs/{region}/input_manifest.json'
        content = (root/relative).read_bytes()
        if json.loads(content)['status'] != 'INPUTS_SEALED_FOR_EXECUTION':
            raise ValueError('Unsealed scene input')
        bound.append({'path':relative,'sha256':hashlib.sha256(content).hexdigest()})
    gate = {'status':'REFERENCE_FREE_REGIONAL_EXECUTION_PREREQUISITES_VERIFIED',
        'scientific_verdict':None,'evidence':bound,
        'official_full_30000_example_status_at_gate':'RUNNING_IN_PARALLEL',
        'schedule_deviation':'Actual native8000 render/extraction/metrics route and complete-anchor tests pass before regional training starts; full native30000 continues unchanged',
        'exact_independent_training_trajectory_claim':False,
        'region_specific_gate':'Each branch additionally requires actual regional exact restore/hooks/PLY-render/one-step probe and documented100-step continuation comparison'}
    with (root/'contracts/runtime_gate_v1.json').open('x') as f:
        json.dump(gate,f,indent=2)
    print(json.dumps(gate))


if __name__ == '__main__':
    main()
