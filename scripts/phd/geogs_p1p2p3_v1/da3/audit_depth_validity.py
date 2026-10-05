"""Read-only all-map validity and exact official cubic-resize audit, in Docker."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stats(array):
    finite = np.isfinite(array)
    values = array[finite]
    return dict(pixels=int(array.size), finite=int(finite.sum()),
                negative=int((finite & (array < 0)).sum()),
                zero=int((finite & (array == 0)).sum()),
                positive=int((finite & (array > 0)).sum()),
                nonfinite=int((~finite).sum()),
                finite_min=float(values.min()) if values.size else None,
                finite_max=float(values.max()) if values.size else None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Docker execution required')
    if any(args.output.iterdir()):
        raise FileExistsError('Use a new empty audit output directory')
    rows, regions = [], {}
    for region in ('P1', 'P2', 'P3'):
        folder = args.inputs / region
        receipt = json.loads((folder / 'receipt.json').read_text())
        expected = {Path(item['name']).stem for item in receipt['images']}
        for subfolder in ('raw_depth', 'raw_depth_inference'):
            if {path.stem for path in (folder / subfolder).glob('*.npy')} != expected:
                raise ValueError(f'{region}: depth membership mismatch')
        region_rows = []
        for item in receipt['images']:
            filename = Path(item['name']).stem + '.npy'
            arrays = {}
            row = dict(region=region, name=item['name'], image_id=item['image_id'],
                       camera_id=item['camera_id'], batch_id=item['batch_id'])
            for subfolder, label in (('raw_depth', 'upsampled'), ('raw_depth_inference', 'native')):
                rel = f'{subfolder}/{filename}'
                path = folder / rel
                if sha(path) != item['files'][rel]['sha256']:
                    raise ValueError(f'{region}/{rel}: immutable input hash mismatch')
                array = np.load(path, allow_pickle=False)
                if array.dtype != np.float32 or array.ndim != 2:
                    raise ValueError('Expected float32 HxW depth')
                arrays[label] = array
                row[f'{label}_sha256'] = sha(path)
                row.update({f'{label}_{k}': v for k, v in stats(array).items()})
            native, up = arrays['native'], arrays['upsampled']
            reproduced = cv2.resize(native, (up.shape[1], up.shape[0]), interpolation=cv2.INTER_CUBIC)
            row['exact_cubic_array_match'] = bool(np.array_equal(up, reproduced, equal_nan=True))
            row['exact_cubic_byte_match'] = up.tobytes() == reproduced.tobytes()
            row['cubic_mismatched_pixels'] = int((~((up == reproduced) | (np.isnan(up) & np.isnan(reproduced)))).sum())
            row['negative_origin'] = ('native_negative_present' if row['native_negative'] else
                                      'cubic_overshoot' if row['upsampled_negative'] and row['exact_cubic_byte_match'] else
                                      'no_negative' if not row['upsampled_negative'] else 'unresolved')
            region_rows.append(row)
            rows.append(row)
        summary = dict(maps=len(region_rows), receipt_sha256=sha(folder / 'receipt.json'),
                       model_revision=receipt['model_revision'], source_commit=receipt['source_commit'],
                       official_script_sha256=receipt['official_script_sha256'],
                       negative_maps=sum(bool(row['upsampled_negative']) for row in region_rows),
                       native_negative_maps=sum(bool(row['native_negative']) for row in region_rows),
                       all_exact_cubic_array_match=all(row['exact_cubic_array_match'] for row in region_rows),
                       all_exact_cubic_byte_match=all(row['exact_cubic_byte_match'] for row in region_rows))
        for label in ('native', 'upsampled'):
            for key in ('pixels', 'finite', 'negative', 'zero', 'positive', 'nonfinite'):
                summary[f'{label}_{key}'] = sum(row[f'{label}_{key}'] for row in region_rows)
            summary[f'{label}_finite_min'] = min(row[f'{label}_finite_min'] for row in region_rows if row[f'{label}_finite_min'] is not None)
            summary[f'{label}_finite_max'] = max(row[f'{label}_finite_max'] for row in region_rows if row[f'{label}_finite_max'] is not None)
        regions[region] = summary
        print(json.dumps(dict(region=region, **summary)), flush=True)
    with (args.output / 'per_image.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    result = dict(schema='jointbuildgs.geogs.da3.depth_validity_audit.v1', scientific_verdict=None,
                  status='PASS_EXACT_CUBIC_AUDIT' if all(row['exact_cubic_byte_match'] for row in rows) else 'FAIL_CUBIC_MISMATCH',
                  regions=regions, opencv_version=cv2.__version__, numpy_version=np.__version__,
                  script_sha256=sha(Path(__file__)), source_pixels_changed=False,
                  references_accessed=False, evaluation_rgb_accessed=False,
                  invalid_depth_handling='Native compute_depth_loss retains only finite and strictly positive target depth; original arrays remain unmodified.',
                  method='Recompute original GeoGS INTER_CUBIC from each stored native float32 map; compare all values and bytes. No inference or scoring.',
                  per_image_csv_sha256=sha(args.output / 'per_image.csv'))
    (args.output / 'summary.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
