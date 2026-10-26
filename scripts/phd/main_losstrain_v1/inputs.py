"""Verify and extract supplied data. Never execute the supplied build script."""
import hashlib
import json
import stat
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
import numpy as np

OUT = Path('/out')
PH = Path('/ph')
S0 = PH / 'main_stage0_v1/PHD-MAIN-STAGE0-v1'
S1 = PH / 'main_stage1_v1/PHD-MAIN-STAGE1-v1'
W = PH / 'main_widen0_v2/PHD-MAIN-WIDEN0-v2'
SITES = ['B0_b10', 'B173nb_b10', 'R1rep_b10']
PRIORS = ['LoD2', 'ALS']

def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(2**20), b''):
            h.update(b)
    return h.hexdigest()

def save(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n')

def extract():
    expected = ['2ed12e8146bbeea9', 'd58822d1a4a7e30e', 'c556c1468379cc68', '64574d029ca0c2e9']
    receipts, names = [], set()
    # Verify every archive before writing the first member.
    for i, prefix in enumerate(expected, 1):
        p = Path('/attachments') / f'학습시험_패치값_v1_part{i}of4.zip'
        digest = sha(p)
        assert digest.startswith(prefix), f'ARCHIVE_HASH_STOP: {p}'
        with zipfile.ZipFile(p) as z:
            assert z.testzip() is None, f'ARCHIVE_CRC_STOP: {p}'
            for info in z.infolist():
                n = PurePosixPath(info.filename)
                assert not n.is_absolute() and '..' not in n.parts and n.parts[0] == 'vfile_v1'
                assert not stat.S_ISLNK(info.external_attr >> 16)
                assert info.filename not in names, f'duplicate archive member: {info.filename}'
                names.add(info.filename)
        receipts.append(dict(name=p.name, sha256=digest, bytes=p.stat().st_size, crc='PASS'))
    assert sum(n.endswith('.npz') for n in names) == 48
    for row in receipts:
        with zipfile.ZipFile(Path('/attachments') / row['name']) as z:
            for info in z.infolist():
                dest = OUT / info.filename
                if info.is_dir():
                    dest.mkdir(parents=True, exist_ok=True)
                    continue
                data = z.read(info)
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    assert dest.read_bytes() == data, f'refuse overwrite: {dest}'
                else:
                    dest.write_bytes(data)
    save(OUT / 'checks/archive_receipt.json', dict(task_id='PHD-MAIN-LOSSTRAIN-v1',
         time=datetime.now().astimezone().isoformat(), archives=receipts,
         members=[dict(path=n, sha256=sha(OUT/n)) for n in sorted(names) if (OUT/n).is_file()],
         scientific_verdict=None))
    paths = [next((OUT/'vfile_v1').glob('*LoD2*')), next((W/'patch_values').glob('*LoD2*R1.5.npz')),
             S0/'fork_inputs/s61/B173nb_b10/store_ALS.npz',
             S1/'regions_v3/regions_ext_v3_B173nb_b10_ALS.npz']
    for p in paths:
        with np.load(p, allow_pickle=False) as z:
            print(str(p), {k: [str(z[k].dtype), list(z[k].shape)] for k in z.files})
    print('archives PASS; 48 NPZ; supplied code retained as data only')

if __name__ == '__main__':
    extract()
