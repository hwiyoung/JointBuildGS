"""Lock all 24 arms and diagnostics before the first optimizer update."""
import json
import os
import random
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from input_audit import bind, sha
from prepare_places import save


def main():
    cfgpath = Path('/config/candpick_v1.json'); assert not cfgpath.exists()
    units, checks = {}, {}
    for unit in ['B173_ALS', 'R1_LoD2', 'B173_LoD2', 'R1_ALS']:
        pre = json.loads((Path('/docs/preflight') / (unit + '_all_views.json')).read_text())
        grad = json.loads((Path('/docs/preflight') / (unit + '_variants.json')).read_text())
        index_path = Path('/out/render_masks') / unit / 'index.json'
        idx = json.loads(index_path.read_text())
        assert pre['actual_support_status'] == 'PASS' and grad['status'] == 'PASS'
        assert pre['tested_views'] == pre['total_train_views'] == len(idx['views'])
        assert len(grad['checks']) == 6 and all(r['status'] == 'PASS' for r in grad['checks'])
        rng = random.Random(0); remaining = []; seq = []; names = [r['name'] for r in idx['views']]
        for _ in range(3000):
            if not remaining: remaining = names.copy()
            seq.append(remaining.pop(rng.randint(0, len(remaining) - 1)))
        scene = Path('/out/scenes') / unit
        bindings = [bind(scene / x) for x in ['background.ply', 'candidate_geometry.npz',
            'initial_right_candidate.npz', 'candidate_color.npy', 'candidate_color_sample_count.npy']]
        bindings += [bind(index_path), bind(index_path.with_name('masks.npz')),
                     bind(Path('/out/places') / (unit + '.npz')),
                     bind(Path('/out/occlusion') / unit / 'points.npz')]
        units[unit] = dict(camera_sequence=seq, train_views=len(names), bindings=bindings,
            first_five_train_psnr_views=idx['psnr_monitor_views'], candidate_error_monitor_views=idx['error_monitor_views'])
        checks[unit] = dict(actual_render_support=pre['actual_support_status'],
            strict_50cm_cell=pre['strict_cell_status'], gradients=grad['status'], tested_views=pre['tested_views'],
            preflight=bind(Path('/docs/preflight') / (unit + '_all_views.json')),
            gradient_preflight=bind(Path('/docs/preflight') / (unit + '_variants.json')))
    impl = ['scripts/phd/main_candpick_v1/' + f for f in ['train_candidates.py', 'train_queue.py',
        'gs_engine.py', 'prepare_render_masks.py', 'rules.py', 'input_audit.py', 'prepare_places.py', 'lock_training.py']]
    impl += ['src/stage2/colmap_io.py', 'src/phd/forks/GeoGS-conf-guided-v1-r18/utils/loss_utils.py']
    cfg = dict(task_id='PHD-MAIN-CANDPICK-v1', locked_at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        commit_at_lock=os.environ.get('CANDPICK_COMMIT'), docker_image=os.environ.get('CANDPICK_IMAGE'),
        places_config_sha256=sha('/config/places_v1.json'), seed=0, iterations=3000, log_every=100,
        snapshot_iterations=[0, 500, 3000],
        loss=dict(L1=.8, one_minus_SSIM=.2, SSIM_window=11, SSIM_sigma=1.5, depth=0., scope='full training photo'),
        learning_rates=dict(opacity=.05, dc=.0025, sh_rest=.0025 / 20),
        learning_rate_sources=['GeoGS-conf-guided-v1-r18/arguments/__init__.py:115-120',
            'GeoGS-conf-guided-v1-r18/scene/gaussian_model.py:170-177'],
        adam=dict(betas=[.9, .999], eps=1e-15, weight_decay=0),
        opacity_initial=dict(right=[.9, .1], wrong=[.1, .9], equal=[.5, .5]),
        trainable=['candidate opacity logits', 'candidate color DC', 'candidate SH rest only in SH3'],
        candidate_SH=dict(sh3=3, sh0=0, high_order_initial=0., sh0_DC_still_learned=True),
        frozen=['all cleaned background values including SH3', 'candidate positions', 'candidate rotations', 'candidate scales'],
        geometry=dict(gaussians_per_candidate=4, tangent_offsets_m=[-.125, .125], inplane_sigma_m=.125),
        densification=False, opacity_reset=False, opacity_prune=False,
        camera_sampling='seed-0 Python Random randint pop without replacement; refill all sorted train views after each epoch; exact sequence stored per case',
        scoring=dict(judgment_column_zero_based=4, delta=.1, minimum_score=.3,
            point_opacity='arithmetic mean of four sigmoid opacities for each candidate', threshold=.5,
            outcome_area_weight='original source patch surface area', occlusion_subset='pooled background occlusion >0.30',
            criteria=dict(group='a', color='sh3', strata=['all', 'front', 'back'], equal_right_only_min=.7,
                wrong_minus_right_min=-.1, both_plus_neither_max=.2, scientific_verdict=None)),
        diagnostics=dict(pixel_mask='fixed union of native candidate splat support at opacity 1 for both candidates, identical for all arms/iterations',
            every_100_candidate_error='pixel-weighted L1/MSE in five prelocked largest-support training views',
            start_end_candidate_error='pixel-weighted L1/MSE in all training views',
            train_psnr='mean per-view PSNR on the first five sorted training photos',
            representative_views='locked from projected area and view direction before optimization'),
        preflight=dict(status='PASS_RENDER_SUPPORT_SCOPE', units=checks,
            interpretation='Trial pixels are the candidate render influence, including native Gaussian tails. The 50cm tangent cell remains the sampling and cleanup unit.',
            decision_author='agent interpretation following user request to proceed; not a separately explicit user mask approval',
            user_steering='이 실험의 목표가 뭔데 왜 그냥 서있는거야?',
            previous_failed_50cm_pixel_mask_retained=True),
        arm_order=[dict(start=s, sh_degree=d) for s, d in [('equal', 3), ('wrong', 3), ('right', 3), ('wrong', 0), ('equal', 0), ('right', 0)]],
        units=units, implementation_sha256={rel: sha(Path('/repo') / rel) for rel in impl},
        resource_recovery='resume exact saved optimizer/parameters/RNG and fixed camera sequence; no sample downscale or algorithm change',
        scientific_verdict=None)
    save(cfgpath, cfg)
    lock = dict(sha256=sha(cfgpath), locked_at=cfg['locked_at'], optimizer_steps_at_lock=0, scientific_verdict=None)
    save(Path('/config/candpick_v1.lock.json'), lock)
    save(Path('/docs/training_lock.json'), lock)
    print(json.dumps(lock))


if __name__ == '__main__': main()
