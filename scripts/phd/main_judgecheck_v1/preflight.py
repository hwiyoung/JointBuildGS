"""Lock the supplied order and inspect lineage metadata before measurement.

No holdout measurements, excluded-building values, images, or point coordinates
are decoded by this entry point. NPZ access is restricted to archive names and
array headers. Raw caches are inspected using directory metadata only.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import zipfile

import numpy as np

C = Path('/cfg')
D = Path('/docs')
O = Path('/out')
R = Path('/repo')
PH = Path('/art/phase-payloads/phd')


def now():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(4 << 20), b''):
            h.update(b)
    return h.hexdigest()


def dump(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def schema(p):
    rows = {}
    with zipfile.ZipFile(p) as z:
        for name in z.namelist():
            if not name.endswith('.npy'):
                continue
            with z.open(name) as f:
                v = np.lib.format.read_magic(f)
                shape, order, dtype = np.lib.format._read_array_header(f, v)
            rows[name[:-4]] = dict(shape=shape, fortran=order, dtype=str(dtype))
    return rows


def main():
    jc = R / 'configs/phd/main_judgenum_v1/judgenum_v1.json'
    j = json.loads(jc.read_text())
    order = (C / 'order_v1.txt').read_text()
    sources = dict(j['sources'])
    sources.update(judgenum=str(PH / 'main_judgenum_v1/PHD-MAIN-JUDGENUM-v1'),
                   target=str(PH / 'main_target_v1/PHD-MAIN-TARGET-v1'))
    cfg = dict(
        task_id='PHD-MAIN-JUDGECHECK-v1', stage='가', created_at=now(),
        scientific_verdict=None, source_tag='[이 발주에서 냄]',
        order_sha256=sha(C / 'order_v1.txt'),
        ordered_methods_3_to_8=order[order.index('## 3. 기하 검사'):order.index('## 9. 낼 것')],
        ordered_constraints=order[order.index('## 1. 지킬 것'):order.index('## 2. 결과 전 기대')],
        inherited_definitions=order[order.index('## 부록 C.'):],
        frame=j['frame'], sources=sources,
        scope=dict(development=j['scope']['development'],
                   source_config_sha256=sha(jc),
                   expected_buildings={'LoD2':125, 'ALS':122},
                   holdout_authorized=False, experiment_buildings_authorized=False,
                   kinds={'ALS':[1], 'LoD2':[1,2]}),
        geometry=dict(mvs_radii_m={'ALS_roof':.075, 'LoD2_roof':.075, 'LoD2_wall':.125},
            half_length_m=10, comparison_half_length_m=5,
            outer_face=j['cylinder']['outer_face'],
            als_normal_radii_m=[.5,.75,1,1.5,2], als_normal_min_points=10,
            als_normal_radius_to_roughness_min=25, als_normal_tin_z_window_m=1,
            als_cylinder_radii_m=[.3,.4,.5,.55,.6,.75,1],
            als_radius_count_median_min=20, als_selected_radius_m=None,
            min_points=4, nmad_k=1.4826,
            L='1.96*(sqrt(u_M**2+sigma_P**2+sigma_W**2)+abs(r))',
            sigma_W_m=None, r_m=None,
            sigma_W_min_agree_cores_per_building=100,
            prior_sigma_m={'ALS':'W.u_prior without floor',
                'LoD2_roof':{'1000':.166,'2100':.098,'3100':.223,'3200':.114,'3900':.238,'other':.11},
                'LoD2_wall':.144},
            calibration_z=[1.645,1.96,2.576], tau_m={'ALS':.1266,'LoD2':.2}),
        photos=dict(seed=20261102, agree_sample_count=5000, benchmark_count=200,
            max_views=10, min_views=3, texture_min=5, patch_width_m=.5,
            patch_spacing_m=.02, patch_shape=[25,25],
            plane_min_points=20, plane_cylinder_radius_m=.5,
            plane_d_window_m=.3, plane_refit_nmad=3,
            occlusion_margin_m=.3, incidence_max_degrees=60,
            image_margin_px=20, min_sample_fraction=.5,
            als_sample_support_radius_m=.18, mvs_support_radius_m=.1,
            mvs_support_plane_distance_m=.1,
            threshold_quantile=.05, threshold_reference_quantile=.10,
            t=None, old_delta=.1, old_min_score=.3,
            old_peak_gap_m=.3, cpu_stop_hours=72, gpu_stop_hours=48),
        judgment=dict(default={'ALS':'preserve','LoD2':'correct'},
            regions={'agree':0,'preserve':1,'correct':2,'free_space':3,'missing':4,'unavailable':9},
            reason={'photo_support':0,'photo_refute':1,'default':2,'not_applicable':9}),
        figures=dict(selected_buildings=None, selection='top four roof outside-limit area per prior; tie building ID',
            random_seed=20261102, dpi=300, ortho_grid_m=.05, cell_m=.25,
            component_link_m=.36, component_min_area_m2=1,
            montage_per_reason=4, montage_max_per_building=2,
            crop_margin_m=3, holdout_figures=False,
            source_of_truth='ordered_methods_3_to_8 section 8'),
        execution=dict(training=False,gpu_use='corrected photo arithmetic only',
            nice=19,memory_gib=32,tile_m=100,tile_overlap_m=10,
            allowed_write_paths=['configs/phd/main_judgecheck_v1/',
                'scripts/phd/main_judgecheck_v1/', 'docs/experiments/phd/main_judgecheck_v1/',
                'PH/main_judgecheck_v1/PHD-MAIN-JUDGECHECK-v1/'],
            archive_max_bytes=399000000, stop_after_report_a=True),
        amendments=[])
    config = C / 'judgecheck_v1.json'
    if not config.exists():
        dump(config,cfg)
        dump(C / 'judgecheck_v1.initial.lock.json',dict(at=now(),
            config_sha256=sha(config), order_sha256=sha(C/'order_v1.txt'),
            before_first_calculation=True, scientific_verdict=None))
    else:
        cfg=json.loads(config.read_text())
    report=dict(at=now(), status='METADATA_INSPECTION', scientific_verdict=None,
                config_sha256=sha(config), sources={}, schemas={}, cache_inventory={})
    for name in ['judgenum','widen','roof_photo','wall_photo','target']:
        root=Path(sources[name]);report['sources'][name]=dict(path=str(root),exists=root.is_dir())
    for name,sub,pattern in [('judgenum','inputs','*.npz'),('judgenum','core_points','*.npz'),
                             ('roof_photo','points','*.npz'),('roof_photo','geometry','*__mapping.npz'),
                             ('wall_photo','points','*.npz')]:
        files=sorted((Path(sources[name])/sub).glob(pattern))
        key=name+'/'+sub
        report['schemas'][key]={'file_count':len(files)}
        if files:
            report['schemas'][key].update(example=str(files[0]),schema=schema(files[0]))
    raw=Path(sources['widen'])/'holdout/internal/points'
    # Shared tile caches are listed, never opened here. Their directory name
    # alone does not establish authorization to consume their contents.
    for tile in sorted(raw.iterdir()) if raw.is_dir() else []:
        if tile.is_dir():
            report['cache_inventory'][tile.name]=[dict(name=p.name,bytes=p.stat().st_size)
                for p in sorted(tile.iterdir()) if p.is_file()]
    report['environment']={'commit':os.environ.get('JUDGECHECK_COMMIT'),
                           'image':os.environ.get('JUDGECHECK_IMAGE')}
    report['protected_measurements_decoded']=False
    dump(O/'preflight_metadata.json',report)
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':
    main()
