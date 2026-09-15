"""Create an immutable dtype-corrected copy; preserve all labels and figures."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import time

import numpy as np


def sha(path):
    with Path(path).open('rb') as stream:
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    start = time.monotonic()
    parent = Path('/parent_attempt')
    out = Path('/output')
    original = json.loads((parent/'result/receipt.json').read_text())
    shutil.copytree(parent/'source', out/'parent_source_snapshot')
    shutil.copytree(parent/'result', out/'result', ignore=shutil.ignore_patterns('receipt.json'))
    boolean_keys = ['valid','inside_context','cross_view_conflict','exclusion_veto','candidate_support','boundary']
    repaired = []
    for row in original['views']:
        rel = row['folder'] + '/rgb_masks.npz'
        with np.load(parent/'result'/rel, allow_pickle=False) as data:
            arrays = {key:data[key] for key in data.files}
        dtypes = {}
        for key in boolean_keys:
            values = arrays[key]
            if not np.isin(values,[0,1]).all():
                raise ValueError('Nonboolean values: '+rel+' '+key)
            dtypes[key] = str(values.dtype)
            arrays[key] = values.astype(np.bool_)
        np.savez_compressed(out/'result'/rel, **arrays)
        with np.load(out/'result'/rel, allow_pickle=False) as fixed, np.load(parent/'result'/rel, allow_pickle=False) as old:
            assert set(fixed.files) == set(old.files)
            for key in old.files:
                np.testing.assert_array_equal(fixed[key],old[key])
            assert all(fixed[key].dtype == np.bool_ for key in boolean_keys)
        repaired.append({'path':rel,'from_dtypes':dtypes,'to_dtype':'bool','all_values_identical':True})
    # All figures, manual definitions, native masks, and numerical region values
    # are inherited byte-identically; only the listed RGB NPZ exports change.
    changed_paths = {row['path'] for row in repaired}
    for item in original['outputs']:
        assert sha(parent/'result'/item['path']) == item['sha256']
        if item['path'] not in changed_paths:
            assert sha(out/'result'/item['path']) == item['sha256']
    for name, expected in original['input_hashes'].items():
        assert sha(name) == expected, name
    outputs = [{'path':str(p.relative_to(out/'result')),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted((out/'result').rglob('*')) if p.is_file()]
    result = dict(original)
    result.update({'created_at_utc':datetime.now(timezone.utc).isoformat(),
                   'artifact_revision':'BOOLEAN_EXPORT_FIXED',
                   'derived_from_receipt_sha256':sha(parent/'result/receipt.json'),
                   'derived_from_attempt_name': 'attempt.uCJGq4',
                   'boolean_export_repair':repaired, 'repair_runtime_seconds':time.monotonic()-start,
                   'parent_source_snapshot_sha256':original['source_snapshot_sha256'],
                   'source_snapshot_sha256':{p.name:sha(p) for p in sorted((out/'source').iterdir()) if p.is_file()},
                   'outputs':outputs})
    result['checks'] = {**result['checks'],'boolean_export_dtypes':True,'all_region_values_unchanged':True,'all_figures_byte_identical':True}
    with (out/'result/receipt.json').open('x') as stream:
        json.dump(result,stream,indent=2,ensure_ascii=False,allow_nan=False)
    print(json.dumps({'status':result['status'],'repaired_view_exports':len(repaired),'repair_runtime_seconds':result['repair_runtime_seconds']}),flush=True)


if __name__ == '__main__':
    main()
