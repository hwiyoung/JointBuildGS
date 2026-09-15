"""CPU-only reproduction of camera dtype failure and strict replacement checks."""
import json
from pathlib import Path
import numpy as np
from da3_camera_contract import validate_camera_return


root = Path('/run')
rows = []
for region in ['R1', 'R2']:
    files = sorted((root/region/'da3_inference/result/batches').glob('*.npz'))
    errors = []
    for path in files:
        with np.load(path) as values:
            result = validate_camera_return(values['extrinsics'], values['input_extrinsics'])
            errors.append(result['max_float64_conversion_error'])
    rows.append(dict(region=region, checked_batches=len(errors), exact_float32_match=True,
                     max_float64_conversion_error=max(errors)))
split = json.loads((root/'R2/da3_input/split.json').read_text())
views = {v['name']: v for v in split['train']}
batch = split['da3_batches'][10]
original = np.array([np.column_stack([views[n]['R'],views[n]['t']]) for n in batch['names']])
expected = original.astype(np.float32)
assert not np.allclose(expected, original, rtol=0, atol=1e-5)
check = validate_camera_return(expected, original)
wrong = expected.copy()
wrong[0, 0, 3] = np.nextafter(wrong[0, 0, 3], np.float32(np.inf))
invalid = expected.copy()
invalid[0, 0, 3] = np.nan
for bad in [wrong, invalid, expected.astype(np.float16), expected[:-1]]:
    try:
        validate_camera_return(bad, original)
    except ValueError:
        continue
    raise AssertionError('Camera mismatch incorrectly accepted')
receipt = dict(status='PASS', saved_batches=rows, r2_batch10_cast_reproduces_old_failure=True,
               r2_batch10=check, one_float32_step_pose_change_rejected=True,
               nan_dtype_shape_mismatch_rejected=True, scientific_verdict=None)
Path('/output/receipt.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))
