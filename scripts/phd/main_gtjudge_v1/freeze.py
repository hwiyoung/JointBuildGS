"""Freeze the order verbatim and its parameters before inspection/calculation."""
from common import *

assert not (C / 'gtjudge_v1.json').exists(), 'Already locked'
parent = json.loads((R / 'configs/phd/main_finaltrain_v1/finaltrain_v1.json').read_text())
recount = json.loads((R / 'configs/phd/main_recount_v1/recount_v1.json').read_text())
config = dict(
    task_id='PHD-MAIN-GTJUDGE-v1', created_at=now(), source_commit=os.environ['GTJUDGE_COMMIT'],
    order_sha256=sha(D / 'provenance/order_v1.txt'), scientific_verdict=None,
    crs='EPSG:25832', local_xy_offset_m=recount['local_xy_offset_m'], sites=SITES,
    priors=PRIORS, methods=METHODS, seed=0, iterations=30000,
    normal_line=dict(origin_offsets_m=[[0,0], [.05,0], [-.05,0], [0,.05], [0,-.05]],
        ray_directions=['+n','-n'], nearest_of_all_hits=True, max_length_roof_m=10,
        max_length_wall_m=5, reference_normals='nearest reference triangle face; roofs up, walls outward',
        result_normals='sampled result triangle face aligned to nearest reference face',
        reference_surface_files=None, missing_reference_policy='unavailable; no PCA/LoD/prior/MVS substitution'),
    scoring=dict(tau_source='/repo/docs/experiments/phd/main_release_v1/tables/stage0/tau_values.csv',
        tau_multiplier=1, result_density_m2=400, result_sampling_seed=0,
        result_exclusion='no reference point within Euclidean 1 m',
        bias='median of signed hits', spread='1.4826 * median(abs(s-median(s)))',
        absolute_quantiles=[.5,.683,.95], mean_distance=False,
        failures=['far_hit','no_surface'], nearest_only_comparison=True),
    stage0=dict(cells='RELEASE score_cell_1p0, identical RECOUNT rows', min_cell_points=1000,
        both_correct_required_pct=90, correction_attempts=1,
        fallback='RECOUNT cells only after a measured signal persists after one implementation correction',
        unavailable_is_measured_signal=False),
    majority=dict(expected_judgment={'0':0,'1':2,'2':1,'4':4},
        tie='agreement if both-correct participates; otherwise inherited judgment',
        both_wrong='inherited judgment', no_reference='inherited judgment', outside_eval='inherited judgment',
        agreement_without_u_M='preserve', correction_without_h_M='inherited judgment',
        heights_sigma='exact FINALTRAIN targets.calculate; only judgment changes'),
    stage2=dict(texture='p0-audit 11_survivor_texture_refine.py, fallback roof-gradient lower 20 percent',
        near_nadir_degrees=20, low_texture_view_fraction=.5, edge_height_difference_m=.5,
        edge_horizontal_distance_m=1, component_connectivity_m=.6, samples_per_group=2),
    freespace=dict(mode_default='off', first_iteration=500, last_iteration=30000,
        calibrate_iteration=1000, band_sigma=1.96, judgment='preserve',
        select='not bound to frontmost preserve disc; centre depth < d_target-1.96*sigma_target',
        loss='lambda_fs * mean(selected activated opacity); opacity gradient only',
        calibration='median photo opacity gradient / median unit-loss opacity gradient',
        GT_used_for_lambda=False),
    checkpoints=parent['checkpoints'], health=parent['health'], retry=parent['retry'],
    renderer=parent['renderer'], docker_images=parent['docker_images'],
    unchanged=parent['unchanged'], weights=parent['weights'],
    gpu_queue={'0':[['R1rep_b10','ALS','A1'],['R1rep_b10','ALS','A2'],
                   ['B173nb_b10','ALS','A1'],['B173nb_b10','ALS','A2'],['B0_b10','ALS','A1'],['B0_b10','ALS','A2']],
               '1':[['B173nb_b10','LoD2','A1'],['B173nb_b10','LoD2','A2'],
                   ['R1rep_b10','LoD2','A1'],['R1rep_b10','LoD2','A2'],['B0_b10','LoD2','A1'],['B0_b10','LoD2','A2']]},
    output_paths=['configs/phd/main_gtjudge_v1/','scripts/phd/main_gtjudge_v1/',
        'docs/experiments/phd/main_gtjudge_v1/','PH/main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1/',
        'src/phd/forks/GeoGS-conf-guided-v1-r25/'],
    PH_resolution='../JointBuildGS-artifacts/phase-payloads/phd',
)
dump(C / 'gtjudge_v1.json', config)
record = dict(locked_at=now(), config_sha256=sha(C / 'gtjudge_v1.json'),
              first_calculation_started=False, scientific_verdict=None)
dump(C / 'gtjudge_v1.initial.lock.json', record)
dump(C / 'stage0.initial.lock.json', record)
print('LOCKED', record['config_sha256'])
