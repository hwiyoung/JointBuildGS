"""Validate served R1 mesh buffers and preserve the previous crop comparison."""
import hashlib
import json
from pathlib import Path
import re
import urllib.request

import numpy as np


def read_url(path):
    with urllib.request.urlopen(cfg['base_url'] + path, timeout=60) as response:
        return response.read()


def mesh_stats(metadata, data):
    assert len(data) == metadata['bytes']
    assert hashlib.sha256(data).hexdigest() == metadata['sha256']
    xyz = np.frombuffer(data, dtype=metadata['dtype']).reshape(metadata['shape'])
    assert np.isfinite(xyz).all()
    crop = np.array(cfg['expected_crop'])
    assert np.all(xyz >= crop[0] - 1e-4) and np.all(xyz <= crop[1] + 1e-4)
    box = np.array(cfg['floater_box'])
    selected = xyz[((xyz >= box[0]) & (xyz <= box[1])).all(axis=1)]
    selected = selected[np.lexsort(selected.T[::-1])]
    return dict(vertices=len(xyz), z_min=float(xyz[:, 2].min()),
                z_max=float(xyz[:, 2].max()),
                above_old_cutoff=int((xyz[:, 2] > cfg['old_max_z'] + 1e-4).sum()),
                floater_box_vertices=len(selected),
                floater_box_xyz_sha256=hashlib.sha256(selected.tobytes()).hexdigest(),
                served_sha256=metadata['sha256'], url=metadata['url'])


cfg = json.loads(Path('/config.json').read_text())
out = Path('/out')
manifest_bytes = read_url('/data/manifest.json')
manifest = json.loads(manifest_bytes)
region = next(r for r in manifest['regions'] if r['id'] == 'R1')
assert region['display_crop_bounds'] == dict(min=cfg['expected_crop'][0], max=cfg['expected_crop'][1])
rows = {}
for name in ['refinement_mesh', 'da3_mesh', 'local_prior0_mesh']:
    candidate = next(c for c in region['candidates'] if c['id'] == name)
    assert candidate['status'] == 'available'
    metadata = candidate['mesh']['xyz']
    rows[name] = mesh_stats(metadata, read_url(metadata['url']))
    if name != 'refinement_mesh':
        assert '_crop_' in metadata['url']
        old_base = re.sub(r'_crop_[0-9a-f]{12}', '', metadata['url']).rsplit('/', 1)[0]
        old_export = json.loads(read_url(old_base + '/export.json'))
        old_metadata = old_export['mesh']['xyz']
        old_metadata['url'] = old_base + '/' + old_metadata['url']
        rows[name + '_v4'] = mesh_stats(old_metadata, read_url(old_metadata['url']))
        assert rows[name + '_v4']['z_max'] <= cfg['old_max_z'] + 1e-4

assert rows['refinement_mesh']['z_max'] > 70
assert rows['local_prior0_mesh']['z_max'] > 70
assert rows['local_prior0_mesh']['above_old_cutoff'] > 500000
assert rows['local_prior0_mesh']['floater_box_vertices'] > 0
assert rows['local_prior0_mesh']['floater_box_xyz_sha256'] == rows['local_prior0_mesh_v4']['floater_box_xyz_sha256']
(out / 'served_manifest.json').write_bytes(manifest_bytes)
receipt = dict(status='PASS_HTTP_GEOMETRY_CROP_VALIDATION', scientific_verdict=None,
               config=cfg, manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
               display_crop_bounds=region['display_crop_bounds'], meshes=rows,
               browser_visual_check=False, raw_training_or_mesh_changed=False)
(out / 'receipt.json').write_text(json.dumps(receipt, indent=2))
print(json.dumps(receipt))
