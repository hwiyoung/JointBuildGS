"""Freeze the complete supplied order and the first stage's rules before arithmetic."""
import os
from common import *


def main():
    assert not (CFG / 'target_v1.json').exists(), 'Never overwrite a frozen configuration'
    jn = json.loads((REPO / 'configs/phd/main_judgenum_v1/judgenum_v1.json').read_text())
    radius = json.loads((JN / 'stage_a_complete.json').read_text())['chosen_radius']
    order = (CFG / 'order_v1.txt').read_text()
    c = {
        'task_id': 'PHD-MAIN-TARGET-v1', 'scientific_verdict': None,
        'created_at': stamp(), 'source_tag': '[이 발주에서 냄]',
        'authoritative_order_sha256': sha(CFG / 'order_v1.txt'),
        'ordered_methods_and_figures': order,
        'sites': ['B0_b10', 'B173nb_b10', 'B173_b0', 'R1rep_b10'],
        'priors': ['ALS', 'LoD2'], 'crs': 'EPSG:25832', 'frame': jn['frame'],
        'scope': 'Every prior patch, evaluation area and the stored outer band',
        'uncertainty': {'ring_m': 1.5, 'data': 'mvs_a', 'u': 'sqrt(a*a+s_ring*s_ring)',
            'missing_value_fallback': 'a if finite else 0, with explicit status and area',
            'missing_patch_join': 'STOP_STAGE0_UNCERTAINTY_JOIN; never use a-only in its place',
            'join': 'Direct region identity; otherwise identical centre, kind, area, normal and MVS lineage',
            'coordinate_tolerance_m': 1e-8, 'parent_candidate': {'B173_b0': 'B173nb_b10'}},
        'cylinder': jn['cylinder'], 'inherited_radius': radius,
        'detection': {'z': 1.96, 'floor_m': .0275, 'min_mvs_points': 4,
            'formula': '1.96*sqrt(s_sample**2/n+u**2+0.0275**2+sigma_p**2)',
            'prior_sigma': jn['detection']['prior_sigma'], 'sensitivity': 'replace u by a; diagnostics only'},
        'mixture': {'source': 'JUDGENUM development ALS roofs; abs(d)>new DL; no GT cells',
            'variable': 'log10(abs(d))', 'weights': 'patch area', 'components': 2,
            'initial_mean_quantiles': [.25, .85], 'iterations': 500,
            'initial_weights': [.5, .5], 'initial_variance': 'area-weighted total variance for each component',
            'variance_floor_log10_squared': 1e-12,
            'T2': 'first crossing above smaller mean where larger-mean posterior becomes larger',
            'stop_large_component_area_below': .05, 'stop_if_no_crossing': True,
            'shared_across_priors_and_surface_kinds': True, 'reference_a_only_T2_m': .855},
        'photo': {'delta': .1, 's_min': .3, 'candidate_number': 4,
            'support_m': 'median patch DL for the photo point', 'missing': 'unknown',
            'source': 'stored PHOTOCHECK curves; CANDPICK-v2 support replay'},
        'regions': {'unavailable': 'missing normal or prior sigma; no target',
            'unobserved': 'n<4', 'agreement': 'abs(d)<=DL',
            'correction': 'abs(d)>DL and (abs(d)>T2 or photo==1)',
            'preservation': 'remaining significant differences', 'minimum_area': None},
        'targets': {'sigma_M': 'sqrt(u*u+0.0275**2)',
            'agreement_h': '(d/sigma_M**2)/(1/sigma_M**2+1/sigma_P**2)',
            'agreement_sigma': '1/sqrt(1/sigma_M**2+1/sigma_P**2)',
            'preservation_and_unobserved': 'h=0; sigma=sigma_P',
            'correction': 'h=d; sigma=sigma_M', 'band_sigma': 1.96},
        'holdout': {'source': 'exact JUDGENUM frozen membership',
            'open_only_after_stage0_input_gates': True,
            'private_output': 'holdout/', 'public': ['count', 'area_m2', 'fraction']},
        'representatives': [
            {'name': 'B173 날개', 'site': 'B173nb_b10', 'priors': ['ALS', 'LoD2'], 'rule': 'reuse prior place files'},
            {'name': 'R1 계단 지붕', 'site': 'R1rep_b10', 'priors': ['LoD2'], 'rule': 'reuse prior place files'},
            {'name': 'B0 단순화 지붕', 'site': 'B0_b10', 'priors': ['LoD2'], 'rule': 'reuse prior place files'},
            {'name': '판단이 틀린 보존 자리', 'rule': 'largest connected LoD2 roof preservation component in cell 1; radius .36m, ties site then patch index; display only'}],
        'figure_views': {'rule': 'freeze exact prior place and camera coordinates before stage1; no rendered-result selection',
            'views_per_mesh': 3, 'colors': {'prior': 'orange', 'mvs': 'blue', 'gt': 'black', 'target': 'gray'},
            'require_same_views_and_color_ranges': True, 'json_sidecars': True},
        'training': {'base_candidate': 'GeoGS-conf-guided-v1-r18', 'new_fork': 'GeoGS-conf-guided-v1-r19',
            'seed': 0, 'iterations': 30000, 'switch': '--jbgs_target on',
            'pilot_iterations': 7000, 'pilot_sites': ['B173nb_b10'],
            'require_new_stage1_lock_before_training': True,
            'disabled': ['mixture_likelihood','far_tether','unsupported_pruning','free_space','multiview','appearance','conditional_gradient_guard','borrowed_judgment','old_judgment_weighted_depth']},
        'stops': {'stage0': ['mixture_not_separated', 'unavailable_area_fraction_gt_0.10', 'uncertainty_join_failed'],
            'stage1': {'nan': False, 'opacity_median_min': .05, 'count_growth_max': 3., 'target_follow_min': .8, 'floater_max': .05},
            'stage2': ['execution_error','nan','opacity_below_0.05','oom'], 'automatic_retry': False},
        'stage_status': 'INPUT_PREFLIGHT_ONLY', 'amendments': []}
    dump(CFG / 'target_v1.json', c)
    inputs = [REPO / 'configs/phd/main_uncert_v1/uncert_v1.json',
              REPO / 'configs/phd/main_judgenum_v1/judgenum_v1.json', JN / 'stage_a_complete.json']
    dump(CFG / 'target_v1.stage0.lock.json', {'at': stamp(), 'stage': 0,
        'config_sha256': sha(CFG / 'target_v1.json'), 'order_sha256': sha(CFG / 'order_v1.txt'),
        'source_commit': os.environ['TARGET_COMMIT'], 'image_id': os.environ['TARGET_IMAGE'],
        'inputs': [{'path': str(p), 'sha256': sha(p)} for p in inputs],
        'script_hashes': {p.name: sha(p) for p in sorted(Path(__file__).parent.glob('*')) if p.is_file()},
        'pre_computation': True, 'scientific_verdict': None})
    print('STAGE0_CONFIG_LOCKED', sha(CFG / 'target_v1.json'), flush=True)


if __name__ == '__main__':
    main()
