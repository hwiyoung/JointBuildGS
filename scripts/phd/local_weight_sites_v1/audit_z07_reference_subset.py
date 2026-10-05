"""Stratify frozen C10 distances; upper-layer membership is not visibility truth."""
import argparse
import csv
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def read(path):
    return Path(path).read_text()


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main(config, output):
    cfg = json.loads(read(config))
    output.mkdir(exist_ok=False)
    bindings = {}

    def bind(path, expected=None):
        actual = sha(path)
        if expected is not None and actual != expected:
            raise ValueError(f'Frozen source hash mismatch: {path}')
        bindings[str(path)] = actual
        return path

    root = Path(cfg['artifact_root']) / cfg['attempt_relative']
    uas = root / cfg['uas_folder']
    failure = root / cfg['failure_folder']
    sites = root / cfg['sites_folder']
    failure_receipt = json.loads(read(bind(failure / 'receipt.json')))
    census = json.loads(read(bind(failure / 'census.json', failure_receipt['files']['census.json'])))
    original = json.loads(read(bind(failure / 'case.json', failure_receipt['files']['case.json'])))['case']
    sites_receipt = json.loads(read(bind(sites / 'receipt.json')))
    cases = json.loads(read(bind(sites / 'reviewed_sites.json', sites_receipt['artifact_sha256']['reviewed_sites.json'])))
    layers = json.loads(read(bind(sites / 'reference_layer_audit.json', sites_receipt['artifact_sha256']['reference_layer_audit.json'])))
    case = next(c for c in cases['cases'] if c['id'] == cfg['case_id'])
    layer = next(c for c in layers['cases'] if c['id'] == cfg['case_id'])
    assert case['region'] == cfg['region'] and case['zone'] == cfg['zone']
    prefix = cfg['region']
    frozen_hashes = census['regions'][prefix]['inputs_sha256']
    for name, digest in frozen_hashes.items():
        bind(uas / name, digest)
    with np.load(uas / f'{prefix}_reference.npz') as reference:
        xyz = reference['xyz']
    with np.load(uas / f'{prefix}_uas_distances.npz') as frozen:
        ds = {b: frozen[b] for b in ['mvs', 'da3', 'local_prior0']}
    ds['prior'] = np.load(uas / f'{prefix}_uas_to_prior.npy')
    assert all(len(d) == len(xyz) for d in ds.values())
    theta = np.deg2rad(cfg['object_axis_angle_degrees'])
    basis = np.array([[np.cos(theta), np.sin(theta)], [np.sin(theta), -np.cos(theta)]])
    uvz = np.column_stack([xyz[:, :2] @ basis.T, xyz[:, 2]])
    lo = np.array(case['uvz_min'])
    hi = lo + case['size']
    selected = ((uvz >= lo) & (uvz < hi)).all(1)
    ids = np.flatnonzero(selected)
    assert len(ids) == case['n'] == cfg['expected_original_n'] == original['n']
    _, inverse = np.unique(np.floor(uvz[:, :2] / cfg['upper_xy_cell_m']).astype(np.int32), axis=0, return_inverse=True)
    top = np.full(inverse.max() + 1, -np.inf)
    np.maximum.at(top, inverse, uvz[:, 2])
    gap = top[inverse[ids]] - uvz[ids, 2]
    upper = gap <= cfg['upper_gap_m']
    assert int(upper.sum()) == cfg['expected_upper_n']
    np.testing.assert_allclose(upper.mean(), layer['fraction_within_05m_of_upper_sample'], atol=1e-12, rtol=0)
    near_far = (ds['prior'][ids] <= cfg['prior_near_m']) & (ds['mvs'][ids] > cfg['baseline_far_m'])
    assert int(near_far.sum()) == cfg['expected_original_prior_near_baseline_far'] == original['counts']['prior_near_baseline_far']
    for b, field in [('prior', 'median_prior_distance'), ('mvs', 'median_baseline_distance'),
                     ('da3', 'median_da3_distance'), ('local_prior0', 'median_release_distance')]:
        np.testing.assert_allclose(np.median(ds[b][ids]), original[field], rtol=0, atol=1e-9)
        np.testing.assert_allclose(np.median(ds[b][ids]), case['median_m'][b], rtol=0, atol=1e-9)
    cohorts = {}
    for label, mask in [('all_original', np.ones(len(ids), dtype=bool)), ('near_upper_sample', upper), ('below_upper_sample', ~upper)]:
        subset = ids[mask]
        cohorts[label] = dict(n=len(subset), prior_near_baseline_far=int(near_far[mask].sum()),
            median_m={b: float(np.median(d[subset])) for b, d in ds.items()})
    lower_bound = max(0, int(near_far.sum() + upper.sum() - len(ids)))
    assert cohorts['near_upper_sample']['prior_near_baseline_far'] >= lower_bound
    with (output / 'samples.csv').open('w') as stream:
        writer = csv.writer(stream)
        writer.writerow(['reference_row', 'u', 'v', 'local_z', 'upper_gap_m', 'near_upper_sample',
                         'prior_near_baseline_far', 'prior_m', 'mvs_m', 'da3_m', 'local_prior0_m'])
        for j, row in enumerate(ids):
            writer.writerow([row, *uvz[row], gap[j], bool(upper[j]), bool(near_far[j]),
                             *[ds[b][row] for b in ['prior', 'mvs', 'da3', 'local_prior0']]])
    receipt = dict(task_id=cfg['task_id'], status='PASS_FROZEN_REFERENCE_SUBSET_AUDIT', scientific_verdict=None,
        timestamp_utc=datetime.now(timezone.utc).isoformat(), case_id=cfg['case_id'],
        metric=cfg['metric'], crs=cfg['crs'], reference_role=cfg['reference_role'],
        selection=dict(uvz_min=lo.tolist(), uvz_max=hi.tolist()), cohorts=cohorts,
        aggregate_intersection_lower_bound=lower_bound,
        original_and_upper_counts_reproduced=True, original_medians_reproduced=True,
        source_bindings=bindings, config_sha256=sha(config), script_sha256=sha(__file__),
        versions=dict(python=platform.python_version(), numpy=np.__version__, docker_image=cfg['docker_image']),
        git_commit=read(config.parent / 'git_commit.txt').strip(), training_changes=False,
        output_sha256={'samples.csv': sha(output / 'samples.csv')},
        limitations=['Upper sampled height is a correspondence clue, not semantic roof truth or camera visibility.',
                     'Frozen one-way distances are stratified; geometry and original reference rows are unchanged.',
                     'Inherited CRS and unclassified UAS limitations remain.',
                     'This does not isolate weight causality or establish local-weight recovery or global-weight insufficiency.'])
    (output / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(status=receipt['status'], cohorts=cohorts), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    main(args.config, args.output)
