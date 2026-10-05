"""Bind existing ALS/MVS bytes for later evaluation without opening UAS."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if not Path('/.dockerenv').exists() or Path('/reference').exists():
        raise RuntimeError('Freeze source baselines in isolated reference-free Docker')
    target = Path('/task/evaluation_inputs')
    target.mkdir(exist_ok=False)
    rows = []
    for region in ('P1', 'P2', 'P3'):
        source = Path('/baselines')/region/'native.npz'
        with zipfile.ZipFile(source) as archive:
            names = archive.namelist()
            if any('uas' in name.lower() or 'reference' in name.lower() for name in names):
                raise ValueError('Baseline package unexpectedly contains reference-labelled arrays')
            if not {'als_xyz.npy', 'mvs_xyz.npy'} <= set(names):
                raise ValueError('Existing source arrays absent')
        destination = target/region/'native.npz'
        destination.parent.mkdir()
        shutil.copyfile(source, destination)
        if sha(source) != sha(destination):
            raise ValueError('Copied baseline bytes differ')
        rows.append({'region':region,'path':str(destination.relative_to('/task')),
                     'original_relative':f'phase-payloads/phd/wu_vallet_matched_v5/PHD-WU-VALLET-{region}-INPUT-v5/run/common/native.npz',
                     'sha256':sha(destination),'bytes':destination.stat().st_size,'arrays':names,
                     'image_geometry_lineage':'historical common-base OpenMVS fused geometry; all-view production, distinct from Wu selected COLMAP depth mesh'})
    with Path('/task/contracts/evaluation_sources_v1.json').open('x') as f:
        json.dump({'scientific_verdict':None,'status':'BASELINES_FROZEN_BEFORE_REGIONAL_TRAINING',
                   'reference_accessed':False,'baselines':rows},f,indent=2)
    print(json.dumps(rows))


if __name__ == '__main__':
    main()
