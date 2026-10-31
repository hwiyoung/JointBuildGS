"""Gate 2.8: verify exact UNCERT patch lineage before deriving any target."""
import os
import time
import numpy as np
from scipy.spatial import cKDTree
from common import *


def main():
    started = stamp(); t0 = time.monotonic()
    cfg, lock = locked(); rows = []; failures = []
    tol = cfg['uncertainty']['coordinate_tolerance_m']
    for site in cfg['sites']:
        for prior in cfg['priors']:
            rp = S1 / 'regions_v3' / f'regions_ext_v3_{site}_{prior}.npz'
            up = UN / 'patch_values' / f'{site}__{prior}__R1.5.npz'
            direct = up.exists()
            parent = site if direct else cfg['uncertainty']['parent_candidate'].get(site)
            if parent:
                up = UN / 'patch_values' / f'{parent}__{prior}__R1.5.npz'
            with np.load(rp) as z:
                r = {k: z[k] for k in ['centre','area','kind','surf_ext','frame_shift','in_eval']}
            row = {'site': site, 'prior': prior, 'patches': len(r['area']),
                'total_area_m2': float(r['area'].sum()), 'region_path': str(rp), 'region_sha256': sha(rp),
                'uncertainty_path': str(up), 'direct_source_exists': direct,
                'source_site': parent, 'frame_shift': r['frame_shift'].tolist(),
                'source_tag': '[이 발주에서 냄]'}
            if not up.exists():
                row.update(status='STOP_STAGE0_UNCERTAINTY_JOIN', reason='No source file', matched_patches=0)
                failures.append({'site': site,'prior': prior,'gate': row['status'],'reason': row['reason']})
                rows.append(row); continue
            with np.load(up) as z:
                u = {k: z[k] for k in ['centre','normal','area','kind','surf','u_prior','roof_type','mvs_a_status','mvs_a_u','mvs_a_a','mvs_a_s']}
            row['uncertainty_sha256'] = sha(up)
            row['source_patches'] = len(u['area'])
            prp = S1 / 'regions_v3' / f'regions_ext_v3_{parent}_{prior}.npz'
            with np.load(prp) as z:
                pshift = z['frame_shift']
            row['source_frame_shift'] = pshift.tolist()
            same_order = len(r['area']) == len(u['area']) and np.array_equal(r['centre'], u['centre'])
            if same_order:
                ix = np.arange(len(r['area'])); distance = np.zeros(len(ix)); unique = np.ones(len(ix), bool)
            else:
                distances, indices = cKDTree(u['centre']).query(r['centre'], k=2, workers=1)
                distance, ix = distances[:,0], indices[:,0]
                unique = distances[:,1] > tol
            matched = (distance <= tol) & unique
            matched &= r['kind'] == u['kind'][ix]
            matched &= np.isclose(r['area'],u['area'][ix],rtol=0,atol=tol)
            # Direct arrays have immutable matching surface IDs. Parent IDs may be local indices.
            if direct:
                matched &= r['surf_ext'] == u['surf'][ix]
            row.update(same_order=same_order, matched_patches=int(matched.sum()),
                unmatched_patches=int((~matched).sum()),
                matched_area_m2=float(r['area'][matched].sum()),
                unmatched_area_m2=float(r['area'][~matched].sum()),
                nearest_distance_m_quantiles=np.quantile(distance,[0,.5,.95,1]).tolist())
            # Repeated ownership or a different camera/depth population cannot borrow u.
            lineage_ok = direct
            if not direct:
                split_paths = [S0 / 'fork_inputs/s61' / s / 'split.json' for s in [site,parent]]
                splits = [json.loads(p.read_text()) if p.exists() else None for p in split_paths]
                row['mvs_split_files'] = [{'path':str(p),'sha256':sha(p) if p.exists() else None} for p in split_paths]
                row['mvs_train_membership_equal'] = all(s is not None for s in splits) and splits[0].get('train') == splits[1].get('train')
                # Only identical population plus exact patches permits a later byte-level map audit.
                lineage_ok = False
                row['mvs_source_identity'] = 'not established for separate experimental unit'
                # Diagnostic registration removal is not an approved numerical transfer.
                raw_src = u['centre'] - pshift
                raw_dst = r['centre'] - r['frame_shift']
                raw_distance,_ = cKDTree(raw_src).query(raw_dst,k=1,workers=1)
                row['unregistered_nearest_distance_m_quantiles'] = np.quantile(raw_distance,[0,.5,.95,1]).tolist()
                row['unregistered_exact_centres'] = int((raw_distance <= tol).sum())
            all_joined = bool(matched.all()) and lineage_ok
            if all_joined:
                # No GT fields are loaded. These only inventory inherited missingness.
                sigma = np.sqrt(u['u_prior'][ix]**2 + .0275**2)
                if prior == 'LoD2':
                    sigmas = cfg['detection']['prior_sigma']['LoD2_roof']
                    sigma = np.array([sigmas.get(str(k),sigmas['other']) for k in u['roof_type'][ix]])
                    sigma[r['kind']==2] = cfg['detection']['prior_sigma']['LoD2_wall']
                normal = u['normal'][ix]
                valid_normal = np.isfinite(normal).all(axis=1)&(np.abs(np.linalg.norm(normal,axis=1)-1)<1e-6)
                unavailable = ~valid_normal | ~np.isfinite(sigma)
                frac = float(r['area'][unavailable].sum()/r['area'].sum())
                row.update(unavailable_patches=int(unavailable.sum()),
                    unavailable_area_m2=float(r['area'][unavailable].sum()),unavailable_area_fraction=frac,
                    missing_mvs_u_area_m2=float(r['area'][~np.isfinite(u['mvs_a_u'][ix])].sum()))
                row['status'] = 'STOP_STAGE0_UNAVAILABLE_AREA' if frac>.1 else 'PASS_INPUT_JOIN'
                if frac>.1:
                    row['reason'] = 'Missing normal or prior sigma covers more than 10 percent of unit area'
            else:
                row['status'] = 'STOP_STAGE0_UNCERTAINTY_JOIN'
                row['reason'] = 'No exact full patch mapping to inherited ring uncertainty with the same MVS source'
            if row['status'].startswith('STOP'):
                failures.append({'site':site,'prior':prior,'gate':row['status'],'reason':row['reason']})
            # Save diagnostic-only membership; never export these as target or u maps.
            np.savez_compressed(OUT/'input_audit'/f'{site}_{prior}.npz',
                centre=r['centre'],area=r['area'],in_eval=r['in_eval'],matched=matched,nearest_distance=distance)
            rows.append(row)
            print(site,prior,row['status'],row['matched_patches'],'/',row['patches'],flush=True)
    result = {'task_id':cfg['task_id'],'status':'STOP_STAGE0' if failures else 'PASS_STAGE0_INPUTS',
        'started_at':started,'finished_at':stamp(),'seconds':time.monotonic()-t0,
        'config_sha256':lock['config_sha256'],'source_commit':os.environ['TARGET_COMMIT'],
        'image_id':os.environ['TARGET_IMAGE'],'rows':rows,'failures':failures,
        'holdout_accuracy_opened':False,'T2_computed':False,'targets_generated':False,'training_started':False,
        'scientific_verdict':None,'source_tag':'[이 발주에서 냄]'}
    dump(OUT/'input_audit.json',result);dump(DOC/'tables/input_audit.json',result)
    print(result['status'],flush=True)


if __name__ == '__main__':
    (OUT/'input_audit').mkdir(exist_ok=True)
    main()
