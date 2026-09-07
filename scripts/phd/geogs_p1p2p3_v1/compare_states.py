"""Compare native model/Adam and complete trainer states without reference data."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def compare(a, b, prefix='', rows=None):
    rows = [] if rows is None else rows
    if torch.is_tensor(a) or torch.is_tensor(b):
        row = {'path': prefix, 'kind': 'tensor'}
        if not (torch.is_tensor(a) and torch.is_tensor(b)) or a.shape != b.shape or a.dtype != b.dtype:
            row.update(equal=False, shape_or_dtype_mismatch=True)
        else:
            a, b = a.detach().cpu(), b.detach().cpu()
            equal = bool(torch.equal(a, b))
            difference = (a.to(torch.float64) - b.to(torch.float64)).abs()
            row.update(equal=equal, shape=list(a.shape), dtype=str(a.dtype),
                       max_abs=float(difference.max()) if difference.numel() else 0.,
                       mean_abs=float(difference.mean()) if difference.numel() else 0.,
                       finite=bool(torch.isfinite(difference).all()))
        rows.append(row)
    elif isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        if not (isinstance(a, np.ndarray) and isinstance(b, np.ndarray)):
            rows.append({'path': prefix, 'equal': False, 'kind': 'array_type_mismatch'})
        elif a.shape != b.shape or a.dtype != b.dtype:
            rows.append({'path': prefix, 'equal': False, 'kind': 'numpy_array',
                         'shape_or_dtype_mismatch': True, 'left_shape': list(a.shape),
                         'right_shape': list(b.shape), 'left_dtype': str(a.dtype), 'right_dtype': str(b.dtype)})
        else:
            # NumPy's MT19937 RNG state is uint32, unsupported by torch2.1.2's
            # from_numpy. Equality must preserve its actual NumPy dtype/values.
            row = {'path': prefix, 'equal': bool(np.array_equal(a, b)), 'kind': 'numpy_array',
                   'shape': list(a.shape), 'dtype': str(a.dtype)}
            if a.dtype.kind in 'uib':
                # Subtract Python integers before float summary conversion to
                # prevent unsigned wraparound and uint64 precision cancellation.
                difference = np.asarray(np.abs(a.astype(object) - b.astype(object)), dtype=np.float64)
            elif a.dtype.kind in 'fc':
                difference = np.abs(a.astype(np.complex128 if a.dtype.kind == 'c' else np.float64) - b)
            else:
                difference = None
            if difference is not None:
                row.update(max_abs=float(difference.max()) if difference.size else 0.,
                           mean_abs=float(difference.mean()) if difference.size else 0.,
                           finite=bool(np.isfinite(difference).all()))
            rows.append(row)
    elif isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b), key=str):
            if key not in a or key not in b:
                rows.append({'path': f'{prefix}/{key}', 'equal': False, 'kind': 'missing_key'})
            else:
                compare(a[key], b[key], f'{prefix}/{key}', rows)
    elif isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            rows.append({'path': prefix, 'equal': False, 'kind': 'length_mismatch'})
        else:
            for i, (left, right) in enumerate(zip(a, b)):
                compare(left, right, f'{prefix}/{i}', rows)
    else:
        rows.append({'path': prefix, 'equal': bool(a == b), 'kind': 'scalar'})
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--left', type=Path, required=True)
    p.add_argument('--right', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    left, right = [torch.load(path, map_location='cpu') for path in (args.left, args.right)]
    lmodel, liter = (left['model'], left['iteration']) if isinstance(left, dict) else left
    rmodel, riter = (right['model'], right['iteration']) if isinstance(right, dict) else right
    rows = compare(lmodel, rmodel, 'model_optimizer')
    rows += compare(liter, riter, 'iteration')
    if isinstance(left, dict) and isinstance(right, dict):
        for key in ('frozen_mask', 'completed_mask', 'building_freeze_mask', 'runtime', 'rng',
                    'train_order', 'test_order', 'viewpoint_stack', 'optimization', 'implementation_hashes'):
            rows += compare(left[key], right[key], key)
    equal = all(row['equal'] for row in rows)
    receipt = {'status': 'EXACT_PARITY' if equal else 'DIFFERENCES_REQUIRE_REVIEW',
               'scientific_verdict': None, 'left_sha256': sha(args.left), 'right_sha256': sha(args.right),
               'all_equal': equal, 'nonmatching_entries': sum(not row['equal'] for row in rows), 'entries': rows,
               'tolerance_policy': 'No post-hoc tolerance promotion; report exact differences for review'}
    with args.output.open('x') as f:
        json.dump(receipt, f, indent=2, allow_nan=False)
    print(json.dumps({key: receipt[key] for key in ('status', 'all_equal', 'nonmatching_entries')}))
    raise SystemExit(0 if equal else 2)


if __name__ == '__main__':
    main()
