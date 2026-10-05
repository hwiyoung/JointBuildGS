"""Read-only camera/target audit of six pre-existing illustrative reference tiles."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import sys
import time

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from PIL import Image


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def cameras(root, bind):
    intr, result = {}, {}
    for line in bind(root/'scene/train_sparse_txt/cameras.txt').read_text().splitlines():
        t = line.split()
        if not t or t[0].startswith('#'):
            continue
        require(t[1] == 'PINHOLE' and len(t) == 8, 'Unexpected camera model')
        intr[t[0]] = (int(t[2]), int(t[3]), np.asarray(t[4:8], float))
    for line in bind(root/'scene/train_sparse_txt/images.txt').read_text().splitlines():
        t = line.split()
        if len(t) < 10 or not t[9].lower().endswith('.jpg'):
            continue
        w, x, y, z = map(float, t[1:5])
        R = np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                      [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                      [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
        require(np.allclose(R.T@R, np.eye(3), atol=1e-8), 'Non-orthogonal camera')
        W, H, K = intr[t[8]]
        result[t[9]] = dict(W=W, H=H, K=K, R=R, t=np.asarray(t[5:8], float),
                            image_id=int(t[0]), camera_id=int(t[8]))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['parent', 'binding', 'config', 'output', 'launcher']:
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    require(Path('/.dockerenv').exists(), 'Docker required')
    out = args.output/('attempt_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'))
    out.mkdir(parents=True, exist_ok=False)
    started = time.time()
    inputs, results = {}, []

    def bind(path, expected=None):
        value = sha(path)
        require(expected is None or expected == value, 'Digest differs: '+str(path))
        inputs[str(path)] = dict(path=str(path), sha256=value, bytes=path.stat().st_size)
        return path

    for source in [Path(__file__), args.config, args.launcher]:
        bind(source)
        shutil.copyfile(source, out/source.name)
    try:
        cfg = read(bind(args.config))
        binding = read(bind(args.binding))
        require(cfg['scientific_verdict'] is binding['scientific_verdict'] is None, 'Verdict forbidden')
        require(cfg['reference_use'] == 'evaluation_only' and cfg['main_training_policy_modified'] is False, 'Boundary differs')
        spatial = args.parent/'evaluation/da3_refinement_spatial_v1'
        sr = read(bind(spatial/'receipt.json'))
        historical = read(bind(spatial/'strict_correspondence_v1/config.json'))
        require(historical['representative_tile_size_m'] == 2, 'Historical tile size differs')
        historical_rows = list(csv.DictReader(bind(spatial/'strict_correspondence_v1/representative_tiles.csv').open()))
        for region in sorted({c['region'] for c in cfg['cases']}):
            root = args.parent/'inputs'/region
            manifest = read(bind(root/'input_manifest.json', binding['regions'][region]['manifest']['sha256']))
            seals = {r['path']: r['sha256'] for r in manifest['files']}

            def sealed(path):
                key = str(path.relative_to(root))
                require(key in seals, 'Unsealed input: '+key)
                return bind(path, seals[key])

            views = cameras(root, sealed)
            pp = bind(spatial/(region+'.paired.npz'), sr['outputs'][region+'.paired.npz']['sha256'])
            with np.load(pp, allow_pickle=False) as archive:
                keys = ['reference_points', 'reference_original_indices', 'reference_to_anchor_distance',
                        'strict_target_world_z_error_median', 'strict_per_view_target_world_z_error',
                        'strict_per_view_camera_z_error', 'selected_view_names']
                a = {k: archive[k] for k in keys}
            points, ids = a['reference_points'], a['reference_original_indices']
            e, d0 = a['strict_target_world_z_error_median'], a['reference_to_anchor_distance']
            require(len(np.unique(ids)) == len(ids) and np.isfinite(points).all(), 'Reference identity invalid')
            for case in [c for c in cfg['cases'] if c['region'] == region]:
                expected_case = {k: case[k] for k in ['id', 'region', 'cohort', 'initial']}
                require(expected_case in historical['representative_cases'], 'Historical case identity differs')
                mask = np.isfinite(e)
                mask &= e > 1 if case['cohort'] == 'above1' else (e < -1 if case['cohort'] == 'below1' else np.abs(e) <= .5)
                mask &= d0 < .5 if case['initial'] == 'near' else d0 >= .5
                tiles, inv, counts = np.unique(np.floor(points[mask, :2]/2).astype(int), axis=0, return_inverse=True, return_counts=True)
                winner = int(np.argmax(counts))
                chosen = np.flatnonzero(mask)[inv == winner]
                lower = tiles[winner]*2
                require(lower.tolist() == case['xy_lower_m'] and len(chosen) == case['expected_reference_count'], 'Historical cohort selection differs')
                old_rows = [r for r in historical_rows if r['case_id'] == case['id']]
                require(len(old_rows) == 6 and all(int(r['reference_count']) == len(chosen) and
                        float(r['x_min_m']) == lower[0] and float(r['y_min_m']) == lower[1] for r in old_rows), 'Historical CSV membership differs')
                names = a['selected_view_names'].tolist()
                coverage = np.isfinite(a['strict_per_view_target_world_z_error'][:, chosen]).sum(axis=1)
                vi = sorted(range(len(names)), key=lambda i: (-int(coverage[i]), names[i]))[0]
                name, c = names[vi], views[names[vi]]
                visible = np.isfinite(a['strict_per_view_target_world_z_error'][vi, chosen])
                selected = chosen[visible]
                require(len(selected) > 0, 'No supported camera')
                q = points[selected].astype(float)
                X = q@c['R'].T+c['t']; z = X[:, 2]
                fx, fy, cx, cy = c['K']; u = fx*X[:, 0]/z+cx; v = fy*X[:, 1]/z+cy
                require(np.all(z > 0) and np.all((u >= 0)&(u < c['W'])&(v >= 0)&(v < c['H'])), 'Projection escaped image')
                px = np.clip(np.rint(u).astype(int), 0, c['W']-1); py = np.clip(np.rint(v).astype(int), 0, c['H']-1)
                stem = Path(name).stem
                D = np.load(sealed(root/'da3/raw_depth'/(stem+'.npy')), allow_pickle=False)
                P = np.load(sealed(root/'prior/raw_depth'/(stem+'.npy')), allow_pickle=False)
                require(D.shape == P.shape == (c['H'], c['W']), 'Target shape differs')
                target, prior = D[py, px], P[py, px]
                require(np.isfinite(target).all() and np.all(target > 0), 'Invalid selected target')
                C = -c['R'].T@c['t']; world_direction_z = (q[:, 2]-C[2])/z
                ez = (target-z)*world_direction_z
                tol = cfg['stored_residual_absolute_tolerance_m']
                require(np.allclose(ez, a['strict_per_view_target_world_z_error'][vi, selected], atol=tol, rtol=0), 'Stored world-Z residual differs')
                require(np.allclose(target-z, a['strict_per_view_camera_z_error'][vi, selected], atol=tol, rtol=0), 'Stored camera-Z residual differs')
                ray = np.c_[(u-cx)/fx, (v-cy)/fy, np.ones(len(u))]@c['R']
                require(np.allclose(C+ray*z[:, None], q, atol=1e-8, rtol=0), 'Camera inverse projection differs')
                photo = np.asarray(Image.open(sealed(root/'scene/images'/name)).convert('RGB'))
                require(photo.shape == (c['H'], c['W'], 3), 'Photo dimensions differ')
                pad = cfg['crop_padding_px']
                bbox = [max(0, int(np.floor(u.min()))-pad), max(0, int(np.floor(v.min()))-pad),
                        min(c['W'], int(np.ceil(u.max()))+pad+1), min(c['H'], int(np.ceil(v.max()))+pad+1)]
                x0,y0,x1,y1 = bbox; crop = photo[y0:y1, x0:x1]
                prefix = case['id']+'_'+region
                Image.fromarray(crop).save(out/(prefix+'_native_crop.png'))
                require(np.array_equal(np.asarray(Image.open(out/(prefix+'_native_crop.png'))), crop), 'Saved native crop differs')
                np.savez_compressed(out/(prefix+'_points.npz'), original_ids=ids[chosen], paired_indices=chosen,
                    reference_points=points[chosen], selected_view_original_ids=ids[selected], selected_view_paired_indices=selected,
                    u=u, v=v, rounded_x=px, rounded_y=py, reference_camera_z=z, da3_camera_z=target,
                    prior_camera_z=prior, da3_world_z_error=ez)
                with (out/(prefix+'_pixels.csv')).open('w', newline='') as stream:
                    writer = csv.writer(stream); writer.writerow(['original_reference_id','u','v','rounded_x','rounded_y','reference_camera_z_m','da3_camera_z_m','prior_camera_z_m','da3_world_z_error_m'])
                    writer.writerows(zip(ids[selected].tolist(),u.tolist(),v.tolist(),px.tolist(),py.tolist(),z.tolist(),target.tolist(),prior.tolist(),ez.tolist()))
                fig, ax = plt.subplots(2, 2, figsize=(12, 10), constrained_layout=True)
                fig.suptitle(f"Historical case {case['id']} | {region} | {name}\nFixed cohort N={len(chosen)}; selected-view strict support N={len(selected)}", fontsize=13)
                ax[0,0].imshow(photo); ax[0,0].add_patch(Rectangle((x0,y0),x1-x0,y1-y0,fill=False,edgecolor='#e00070',lw=1.5))
                ax[0,0].set_title('Actual training photo; box shows native crop')
                ax[0,1].imshow(crop, extent=[x0,x1,y1,y0], interpolation='nearest')
                ax[0,1].scatter(u,v,s=3,facecolors='none',edgecolors='#e00070',linewidths=.3)
                ax[0,1].set_title('Actual pixels + exact reference projection\nProjection alone does not certify visibility')
                for aa in ax[0]:
                    aa.set_xlabel('Image column'); aa.set_ylabel('Image row')
                prior_valid = np.isfinite(prior)&(prior > 0)
                ax[1,0].scatter(u,z,s=6,c='#242424',label='Observed UAS camera Z')
                ax[1,0].scatter(u,target,s=6,c='#d97706',label='Unmodified DA3 camera Z')
                ax[1,0].scatter(u[prior_valid],prior[prior_valid],s=5,c='#2876ae',label='Unmodified prior camera Z')
                ax[1,0].set(xlabel='Projected image column (multiple rows)',ylabel='Camera Z (m)',title='Same selected-view reference points; no scale fit')
                ax[1,0].legend(fontsize=8)
                ax[1,1].hist(ez,bins=25,color='#8a4b94',alpha=.85)
                ax[1,1].axvline(0,c='black',lw=1);ax[1,1].set(xlabel='DA3 target minus reference world Z (m)',ylabel='Reference points',title='Selected view residual; evaluation-only reference\nNot a DA3-only causal effect')
                fig.savefig(out/(prefix+'_photo_targets.png'),dpi=150);plt.close(fig)
                result = dict(**case, photo=name, image_id=c['image_id'], camera_id=c['camera_id'], selected_view_index=vi,
                    selected_view_reference_count=len(selected), photo_shape=list(photo.shape), crop_bbox=bbox,
                    all_case_median_target_world_z_error_m=float(np.median(e[chosen])),
                    selected_view_median_target_world_z_error_m=float(np.median(ez)),
                    selected_view_median_camera_z_error_m=float(np.median(target-z)),
                    selected_view_prior_valid_count=int(prior_valid.sum()), stored_residual_recomputed=True,
                    exact_native_crop_roundtrip=True, manual_photo_visibility_review='PENDING_SEPARATE',
                    selection_uses_lc_outcomes=False, scientific_verdict=None)
                results.append(result);print(json.dumps(result),flush=True)
        outputs = [dict(path=p.name,bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(out.iterdir()) if p.is_file()]
        receipt = dict(schema='jbgs.local_photo_target_audit.v2',status='PASS_REUSED_CASES_AND_NATIVE_TARGET_RECOMPUTATION',
            scientific_verdict=None, cases=results,inputs=list(inputs.values()),outputs=outputs,config=cfg,
            command=sys.argv,wall_seconds=time.time()-started,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            versions=dict(python=platform.python_version(),numpy=np.__version__,matplotlib=matplotlib.__version__),
            runtime=dict(image_id=os.environ['JBGS_RUNTIME_IMAGE_ID'],cpu_max=Path('/sys/fs/cgroup/cpu.max').read_text().strip(),
                         memory_max=Path('/sys/fs/cgroup/memory.max').read_text().strip()),
            reference_used_for_training_or_parameter_selection=False, model_outputs_read=False,
            limitations=['Historical posthoc illustrative cases, not population samples.',
                         'Photo visibility needs separate manual review; regional UAS cannot exclude every external occluder.',
                         'Inherited camera, CRS and vertical-datum uncertainty remain; no reference-based correction.',
                         'DA3 sample uses inherited nearest raster convention; prior carries inherited half-pixel ray convention.'])
        (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        print(json.dumps(dict(status=receipt['status'],output=str(out),scientific_verdict=None)))
    except Exception as exc:
        (out/'failure.json').write_text(json.dumps(dict(status='FAIL',error=repr(exc),inputs=list(inputs.values()),
            scientific_verdict=None,wall_seconds=time.time()-started),indent=2)+'\n')
        raise


if __name__ == '__main__':
    main()
