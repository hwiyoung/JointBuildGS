"""Join the two frozen case ledgers, retaining metric and baseline distinctions."""
import argparse
import csv
import hashlib
import json
import platform
from pathlib import Path

import numpy as np


def read(p):
    return json.loads(Path(p).read_text())


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main(config, out, repository):
    cfg = read(config); art = Path(cfg['artifact_root'])
    old = art / cfg['previous_relative']; new = art / cfg['current_relative']
    out.mkdir(exist_ok=False); bindings = {}
    old_receipt = read(old / 'receipt.json'); old_path = old / 'reviewed_sites.json'
    assert sha(old_path) == old_receipt['artifact_sha256']['reviewed_sites.json']
    complete = read(new / 'completion_receipt.json')
    for name in ['review_config.json', 'inspection/receipt.json', 'review/receipt.json']:
        assert sha(new / name) == complete['artifact_hashes'][name], name
    previous = read(old_path); current = read(new / 'review_config.json')['cases']
    inspected = {x['case']['id']: x for x in read(new / 'inspection/receipt.json')['cases']}
    rows = []
    for c in previous['cases']:
        cid = c['id']; desc = cfg['previous_cases'][cid]
        assert bool(c['recommended']) == (cid in cfg['priority_ids'])
        d = c['median_m']; lo = np.array(c['uvz_min']); hi = lo + c['size']
        rows.append(dict(case_id=cid, origin='20260918_UAS_SITE_REVIEW', region=c['region'], zone=c['zone'],
            name=c.get('title', c['zone_name']), priority=cid in cfg['priority_ids'], baseline=desc['baseline'],
            status=desc['status'], metric='UAS_POINT_TO_NATIVE_TRIANGLE_MEDIAN_M', n=c['n'],
            prior_m=d['prior'], mvs_geogs_m=d['mvs'], da3_geogs_m=d['da3'],
            reason=desc['reason'], weight_hypothesis=desc['hypothesis'],
            location_uvz_min=json.dumps(lo.tolist()), location_uvz_max=json.dumps(hi.tolist()),
            related_case='W011' if cid == 'C03' else '', scientific_verdict=None))
    for cid, desc in current.items():
        c = inspected[cid]['case']; d = c['output_surface']
        rows.append(dict(case_id=cid, origin='20260919_MVS_CONFLICT_REVIEW', region=c['region'], zone=c['zone'],
            name=desc['name'], priority=cid in cfg['priority_ids'], baseline='DA3' if cid == 'W011' else 'MVS',
            status='WEIGHT_HYPOTHESIS_PRIORITY' if cid == 'W019' else desc['status'],
            metric='MVS_POINT_TO_NATIVE_TRIANGLE_MEDIAN_M', n=c['n'],
            prior_m=c['prior_surface']['median'], mvs_geogs_m=d['mvs']['median'], da3_geogs_m=d['da3']['median'],
            reason=desc['note'], weight_hypothesis=cfg['current_hypotheses'][cid],
            location_uvz_min=json.dumps(c['bounds_uvz'][0]), location_uvz_max=json.dumps(c['bounds_uvz'][1]),
            related_case='C03' if cid == 'W011' else '', scientific_verdict=None))
    assert len(rows) == 20 and len({r['case_id'] for r in rows}) == 20
    assert sum(r['priority'] for r in rows) == 6
    assert {r['case_id'] for r in rows if r['priority']} == set(cfg['priority_ids'])
    # C03 and W011 share a roof context, not an evaluation point set or metric.
    c03 = next(c for c in previous['cases'] if c['id'] == 'C03')
    w011 = inspected['W011']['case']
    assert (c03['region'], c03['zone']) == (w011['region'], w011['zone'])
    a = np.load(new / 'result/R2_sample_diagnostic.npz')
    uvz = a['uvz'][w011['sample_indices']]; lo = np.array(c03['uvz_min']); hi = lo + c03['size']
    spatial_link = dict(cases=['C03', 'W011'], same_region_zone=True,
        w011_samples_inside_c03_box=int(((uvz >= lo) & (uvz < hi)).all(1).sum()), w011_samples=len(uvz),
        center_separation_m=float(np.linalg.norm(np.array(c03['center']) - w011['center_uvz'])),
        interpretation='Same roof context and nearby patches. Preserve both IDs; not identical samples, metrics or independent cases.')
    with (out / 'case_ledger.csv').open('w') as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    for p in [config, old / 'receipt.json', old_path, new / 'completion_receipt.json', new / 'review_config.json',
              new / 'inspection/receipt.json', new / 'review/receipt.json', new / 'result/R2_sample_diagnostic.npz',
              *[repository / p for p in cfg['supplemental_reports']]]:
        bindings[str(p)] = sha(p)
    receipt = dict(task_id=cfg['task_id'], status='PASS_CASE_RECONCILIATION', scientific_verdict=None,
        case_records=20, previous_priority_ids=previous['recommended'], current_priority_ids=['W019'],
        priority_case_count=6, priority_ids=cfg['priority_ids'], other_case_records=14,
        confirmed_weight_only_failure_count=0, unique_site_count=None,
        spatial_link=spatial_link, source_bindings=bindings, script_sha256=sha(__file__),
        versions=dict(python=platform.python_version(), numpy=np.__version__),
        file_sha256={'case_ledger.csv': sha(out / 'case_ledger.csv')}, rows=rows,
        limitations=['Case count is not independent building/site count.',
            'C cases score UAS samples; W cases score MVS input samples. Do not rank their numbers together.',
            'Prior-vs-MVS conflict screening omitted stable-prior preservation cases; those remain in the joined ledger.',
            'Weight directions are hypotheses. No intervention, necessity, sufficiency or superiority proof was added.'])
    (out / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
    print(json.dumps({k: receipt[k] for k in ['status', 'case_records', 'priority_case_count', 'spatial_link']}, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--config', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--repository', type=Path, default=Path('/repo')); a = p.parse_args(); main(a.config, a.output, a.repository)
