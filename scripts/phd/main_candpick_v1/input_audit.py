"""Bounded inventory before source resolution; never locks places or trains.

Reads development-only photo points. Sealed photo payloads are not opened.
Records the exact available baseline and schema instead of substituting v1 for v2.
"""
import hashlib
import importlib.metadata
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

PH = Path('/art/phase-payloads/phd')
PC = PH / 'main_photocheck_v1/PHD-MAIN-PHOTOCHECK-v1'
S0 = PH / 'main_stage0_v1/PHD-MAIN-STAGE0-v1'
S3 = PH / 'main_stage3_v1/PHD-MAIN-STAGE3-v1'
DOC = Path('/docs')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(4 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def bind(path):
    return dict(path=str(path), bytes=path.stat().st_size, sha256=sha(path))


def schema(path):
    with np.load(path, allow_pickle=False) as z:
        return {k: dict(dtype=str(z[k].dtype), shape=list(z[k].shape)) for k in z.files}


def main():
    report = dict(task_id='PHD-MAIN-CANDPICK-v1',
                  at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
                  stage='input_inventory_only', optimizer_steps=0,
                  source_status='AWAITING_PHOTOCHECK_V2_IDENTITY',
                  scientific_verdict=None, commit=os.environ.get('CANDPICK_COMMIT'),
                  docker_image=os.environ.get('CANDPICK_IMAGE'),
                  script_sha256=sha(__file__), baselines=[], photo_files=[], schemas={})
    report['versions'] = {}
    for name in ['numpy', 'scipy', 'torch', 'gsplat', 'plyfile', 'open3d']:
        try:
            report['versions'][name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            report['versions'][name] = None
    for site in ['B173nb_b10', 'R1rep_b10']:
        initial = S0 / 'fork_inputs/s61' / site
        split_file = initial / 'split.json'
        split = json.loads(split_file.read_text())
        for prior in ['ALS', 'LoD2']:
            model = S3 / 'runs' / site / f'nojudge_{prior}_s0/model'
            ply = model / 'point_cloud/iteration_30000/point_cloud.ply'
            with ply.open('rb') as f:
                header = []
                for _ in range(256):
                    line = f.readline().decode('ascii').strip()
                    header.append(line)
                    if line == 'end_header':
                        break
                else:
                    raise ValueError(f'PLY header did not terminate: {ply}')
            row = dict(site=site, prior=prior, iteration=30000, fallback=False,
                       checkpoint=bind(ply), header=header, split=bind(split_file),
                       split_sizes={k: len(v) for k, v in split.items() if isinstance(v, list)},
                       model_args=(model / 'cfg_args').read_text() if (model / 'cfg_args').exists() else None)
            for rel in ['dump/iteration_30000/gaussians.npz',
                        'jbgs_complete/iteration_30000/checkpoint.pth']:
                p = model / rel
                row[rel] = dict(exists=p.exists(), bytes=p.stat().st_size if p.exists() else None)
            report['baselines'].append(row)
            for p in [initial / f'store_{prior}.npz',
                      PH / 'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/direct_stage1_v2' /
                      f'{site}__{prior}/evaluation.npz']:
                report['schemas'][str(p)] = schema(p)
            info = initial / 'fork_inputs.json'
            report.setdefault('fork_inputs', {})[site] = json.loads(info.read_text())
            print('baseline', site, prior, row['checkpoint']['bytes'], flush=True)
    for p in sorted((PC / 'points').glob('*.npz')):
        with np.load(p, allow_pickle=False) as z:
            assert not z['holdout'].any(), 'sealed data in development points'
            ids = z['point_id']
            assert len(np.unique(ids)) == len(ids), 'duplicate point ID'
            row = dict(**bind(p), points=len(ids), roof_points=int((z['kind'] == 1).sum()),
                       judgment_shape=list(z['judgment'].shape),
                       finite_mvs=int(np.isfinite(z['mvs_p']).sum()))
        report['photo_files'].append(row)
    for prior in ['ALS', 'LoD2']:
        p = next((PC / 'points').glob(f'*__{prior}.npz'))
        report['schemas'][str(p)] = schema(p)
        tile = p.stem.split('__')[0]
        for q in [PC / 'geometry' / f'{tile}__{prior}__mapping.npz',
                  PH / 'main_widen0_v2/PHD-MAIN-WIDEN0-v2/patch_values' /
                  f'{tile}__{prior}__R1.5.npz']:
            report['schemas'][str(q)] = schema(q)
    config = Path('/repo/configs/phd/main_photocheck_v1/photocheck_v1.json')
    data = json.loads(config.read_text())
    report['available_photo_config'] = dict(**bind(config), judgments=data['judgments'],
                                          points=data['points'])
    report['photo_v2_named_paths_exist'] = {
        str(p): p.exists() for p in [PH / 'main_photocheck_v2',
        Path('/repo/configs/phd/main_photocheck_v2'),
        Path('/repo/scripts/phd/main_photocheck_v2')]}
    report['prune_support'] = []
    for site in ['B173nb_b10', 'R1rep_b10']:
        p = PH / 'main_farpull_v1/PHD-MAIN-FARPULL-v1/evidence_prune_v1' / site / 'support.json'
        report['prune_support'].append(dict(site=site, prior='ALS', exists=p.exists(),
            source=bind(p) if p.exists() else None,
            metadata=json.loads(p.read_text()) if p.exists() else None))
    target = DOC / 'input_audit_v1.json'
    assert not target.exists(), 'preserve previous audit'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print('inventory complete', len(report['baselines']), 'baselines,',
          sum(r['points'] for r in report['photo_files']), 'available v1 development points')


if __name__ == '__main__':
    main()
