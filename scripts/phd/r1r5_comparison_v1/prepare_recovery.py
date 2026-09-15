"""Seal an additive recovery; never overwrite a failed or completed payload."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('attempt', type=Path)
    args = parser.parse_args()
    root = args.attempt.resolve()
    previous = json.loads((root/'execution/status.json').read_text())
    assert (previous['state'], previous['region'], previous['job']) == ('FAILED','R2','da3_inference')
    failed = json.loads((root/'R2/da3_inference/result/receipt.json').read_text())
    assert failed['error'] == 'DA3 did not preserve input metric extrinsics after scale alignment'
    assert not (root/'R2/da3').exists()
    assert all(not (root/r/'local_prior0').exists() for r in ['R1','R2','R3','R4','R5'])
    recovery = root / ('recovery_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    recovery.mkdir()
    shutil.copy2(root/'execution/status.json', recovery/'previous_status.json')
    shutil.copy2(root/'execution/failure.json', recovery/'previous_failure.json')
    source = recovery/'source'
    shutil.copytree(root/'execution/source', source)
    here = Path(__file__).resolve().parent
    shutil.copy2(here/'recovery_queue.py', source/'recovery_queue.py')
    shutil.copy2(here/'da3_camera_contract.py', source/'da3/da3_camera_contract.py')
    infer = source/'da3/infer.py'
    text = infer.read_text()
    old = '            if not np.allclose(prediction.extrinsics, extrinsics[:, :3, :], rtol=0, atol=1e-5):\n                raise ValueError("DA3 did not preserve input metric extrinsics after scale alignment")'
    new = '            from da3_camera_contract import validate_camera_return\n            camera_check = validate_camera_return(prediction.extrinsics, extrinsics)'
    assert text.count(old) == 1
    text = text.replace(old, new)
    text = text.replace('input_camera_center_rank=center_rank,',
                        'input_camera_center_rank=center_rank, camera_return_validation=camera_check,')
    infer.write_text(text)
    hashes = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in source.rglob('*') if p.is_file()}
    (recovery/'source_hashes.json').write_text(json.dumps(hashes, indent=2))
    unit = 'jbgs-r1r5-' + recovery.name.replace('_','-')
    plan = dict(task_id='PHD-R1R5-COMPARISON-v1', recovery=str(recovery), unit=unit,
                parent_source=str(root/'execution/source'),
                change='Exact float32 input equality replaces float64 absolute tolerance check only',
                preserved=['model','RGB','poses','batch membership','seed','resolution','all training settings'],
                retry='R2 batch 10 preflight, then full R2 DA3 inference in a new output folder',
                remaining='R2-R5 DA3 refinement/extraction; R1-R5 local prior 0', scientific_verdict=None)
    (recovery/'plan.json').write_text(json.dumps(plan,indent=2))
    (recovery/'launch.json').write_text(json.dumps(['systemd-run','--user','--unit',unit,
        '--property=Type=exec','--property=RemainAfterExit=yes','/usr/bin/python3',
        str(source/'recovery_queue.py'),str(root),str(recovery)],indent=2))
    print(recovery)


if __name__ == '__main__':
    main()
