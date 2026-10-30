"""Inspect names, headers and scope metadata; never load patch measurements."""
import importlib.util
import json
from pathlib import Path
import zipfile
import numpy as np

W = Path('/art/phase-payloads/phd/main_widen0_v2/PHD-MAIN-WIDEN0-v2')
for p in [W/'building_split.json', W/'scope_split.json']:
    q = json.loads(p.read_text())
    print(p.name, 'keys', list(q))
for prior in ['LoD2', 'ALS']:
    files = sorted((W/'patch_values').glob(f'*__{prior}__R1.5.npz'))
    print(prior, 'files', len(files))
    with zipfile.ZipFile(files[0]) as z:
        schemas = {}
        for key in z.namelist():
            with z.open(key) as f:
                version = np.lib.format.read_magic(f)
                shape, order, dtype = np.lib.format._read_array_header(f, version)
                schemas[key] = {'shape': shape, 'fortran': order, 'dtype': str(dtype),
                                'compression': z.getinfo(key).compress_type}
        print(json.dumps({'file': str(files[0]), 'schema': schemas}))
for name in ['ijson', 'shapely', 'matplotlib', 'scipy']:
    print('module', name, bool(importlib.util.find_spec(name)))
print('wall_payload_exists', Path('/art/phase-payloads/phd/main_wallphoto_v1/PHD-MAIN-WALLPHOTO-v1').is_dir())
