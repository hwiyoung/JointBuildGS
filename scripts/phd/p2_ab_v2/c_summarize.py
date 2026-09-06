"""Join completed C scores and B degrees of freedom without selecting parameters."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(args):
    config = json.loads(args.config.read_text())
    base = Path(config['artifact_root'])/'phase-payloads/phd/p2_ab_v2'
    geometry_path = base/config['c_geometry_run']/'geometry/evaluation.json'
    appearance_path = base/config['c_appearance_run']/'appearance/appearance.json'
    geometry = json.loads(geometry_path.read_text())
    appearance = json.loads(appearance_path.read_text())
    appearances = {(a['run'], a['arm']): a for a in appearance['arms']}
    inputs = {str(p): sha(p) for p in [args.config, geometry_path, appearance_path]}
    cross = {s['spacing_m']: s for s in geometry['cross_arm_detail']}
    rows = []
    for a in geometry['arms']:
        run, arm = a['run'], a['arm']
        path = base/run/arm/'result.json'
        inputs[str(path)] = sha(path)
        b = json.loads(path.read_text())
        dof = b['fit']['dof']
        app = appearances[(run, arm)]['stages']
        def weighted_surface(field):
            valid = [m for m in b['final_metrics'] if m.get(field) is not None]
            n = sum(m['retained_support']['pixels'] for m in valid)
            return sum(m[field]*m['retained_support']['pixels'] for m in valid)/n if n else None
        row = dict(run=run, arm=arm, initial_gaussians=b['initial_seed_count'], steps=b['fit']['steps'],
                   coarse_displacement_max_m=dof['coarse_displacement_max_m'],
                   detail_displacement_rms_m=dof['detail_displacement_rms_m'],
                   detail_nonzero_count=dof['detail_nonzero_gt1mm_count'],
                   retained_ray_depth_change_mean_m=weighted_surface('surface_depth_abs_change_mean_m'),
                   retained_ray_normal_change_mean_deg=weighted_surface('render_normal_change_mean_deg'))
        for phase in ['initial', 'final']:
            g = a['geometry'][phase]
            row.update({f'{phase}_psnr_db': app[phase]['psnr_db'], f'{phase}_mae': app[phase]['mae'],
                        f'{phase}_presence_fraction': app[phase]['presence_fraction'],
                        f'{phase}_prediction_count': g['prediction_count'],
                        f'{phase}_uas_p90_m': g['prediction_to_reference']['p90_m'],
                        f'{phase}_uas_recall_05': next(x['reference_recall'] for x in g['tolerance_sweep'] if x['tolerance_m']==.5)})
            for s, records in cross.items():
                row[f'{phase}_detail_{s:g}m_common_rmse_m'] = records['arms'][f'{run}/{arm}'][phase]['error_common']['rmse_m']
                row[f'{phase}_detail_{s:g}m_missing_stencils'] = records['arms'][f'{run}/{arm}'][phase]['missing_reference_stencils']
        rows.append(row)
    if len(rows) != len(appearance['arms']):
        raise ValueError('Geometry/appearance arm sets differ')
    if any(sha(p)!=h for p,h in inputs.items()):
        raise RuntimeError('Summary inputs changed')
    args.output.mkdir(parents=True, exist_ok=False)
    with (args.output/'summary.csv').open('x') as f:
        writer=csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    with (args.output/'summary.json').open('x') as f:
        json.dump(dict(scientific_verdict=None, rows=rows,
                       common_detail_denominators=[{k:s[k] for k in ['spacing_m','common_stencils','reference_stencils','excluded_reference_stencils']} for s in geometry['cross_arm_detail']],
                       input_sha256=inputs), f, ensure_ascii=False, allow_nan=False, indent=2)
    shutil.copyfile(__file__, args.output/'source_snapshot.py')
    shutil.copyfile(args.config, args.output/'execution_config.json')
    for r in rows:
        print(json.dumps({k:r[k] for k in ['run','arm','initial_psnr_db','final_psnr_db','initial_uas_p90_m','final_uas_p90_m','final_uas_recall_05','initial_detail_0.5m_common_rmse_m','final_detail_0.5m_common_rmse_m','retained_ray_depth_change_mean_m']}), flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    main(parser.parse_args())
