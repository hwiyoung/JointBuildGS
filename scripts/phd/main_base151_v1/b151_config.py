#!/usr/bin/env python3
"""PHD-MAIN-BASE151-v1: write configs/phd/main_base151_v1/base151_v1.json (host, stdlib only) and lock it.

  python3 b151_config.py write      # writes base151_v1.json (refuses if a lock exists)
  python3 b151_config.py lock       # writes base151_v1.lock.json (saved time + sha256), before the first computation
  python3 b151_config.py lock <name>   # lock an addendum configs/phd/main_base151_v1/<name>.json -> <name>.lock.json
scientific_verdict: null
"""
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[3]                      # JointBuildGS-wt-trainunit
C = W / 'configs/phd/main_base151_v1'
ART = W.parent / 'JointBuildGS-artifacts'
PH = ART / 'phase-payloads/phd'
OUT = PH / 'main_base151_v1/PHD-MAIN-BASE151-v1'
TU1 = PH / 'main_trainunit_v1/PHD-MAIN-TRAINUNIT-v1'
TU2 = PH / 'main_trainunit_v1/PHD-MAIN-TRAINUNIT-v2'
SB = PH / 'main_baselines_v1/PHD-MAIN-BASELINES-v1'
SF = PH / 'main_fix_v1/PHD-MAIN-FIX-v1'
SL = PH / 'main_fill_v1/PHD-MAIN-FILL-v1'
GT = PH / 'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'
RS = PH / 'main_rescore_v1/PHD-MAIN-RESCORE-v1'
JC2 = PH / 'main_judgecheck_v2/PHD-MAIN-JUDGECHECK-v2'
KST = dt.timezone(dt.timedelta(hours=9))


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()


def rel(p):
    return str(Path(p).relative_to(ART)) if str(p).startswith(str(ART)) else str(p)


def f(p):
    return dict(path=rel(p), sha256=sha(p))


def write():
    assert not (C / 'base151_v1.lock.json').exists(), 'locked already'
    cells = json.loads((TU1 / 'cells/cells.json').read_text())
    cell_rows = []
    for c in cells['cells']:
        k = c['id']
        sc = TU1 / 'scenes' / f'cell{k}'
        cell_rows.append(dict(
            id=k, original_min=c['original_min'], original_max=c['original_max'], expanded_min=c['expanded_min'], expanded_max=c['expanded_max'],
            projection_box_min=c['projection_box_min'], projection_box_max=c['projection_box_max'], train_images=len(c['images']),
            test_images_candidates=len(c.get('test_images', [])), split=f(sc / 'split.json'),
            sparse={n: f(sc / 'scene_ALS/sparse/0' / n) for n in ['cameras.bin', 'images.bin', 'points3D.ply', 'origin.npy']},
            calibration=f(sc / 'scene_ALS/jbgs_calibration.json'),
            run_of_trainunit=f'TRAINUNIT-v1 runs/ef/cellsef_ALS_s0_cell{k}'))
    cfg = dict(
        task_id='PHD-MAIN-BASE151-v1', scientific_verdict=None,
        order='docs/experiments/phd/main_base151_v1/비교방법151_발주문_v1.md',
        order_sha256=sha(W / 'docs/experiments/phd/main_base151_v1/비교방법151_발주문_v1.md'),
        worktree='JointBuildGS-wt-trainunit', branch='exp/train-unit-v1',
        roots=dict(artifacts='JointBuildGS-artifacts (paths below are relative to it)', out=rel(OUT), delivery=rel(PH / 'delivery'),
                   trainunit_v1=rel(TU1), trainunit_v2=rel(TU2), baselines=rel(SB), fix=rel(SF), fill=rel(SL), gtjudge=rel(GT), rescore=rel(RS),
                   judgecheck_v2=rel(JC2)),
        cells=dict(rule='TRAINUNIT 넷 판(cellsef_ALS_s0): VastGaussian 2 x 2, edges expanded 20 %, camera selection (centre in expanded cell, '
                        'or >= 25 % image coverage of the expanded-cell box) - read only, never recomputed',
                   file=f(TU1 / 'cells/cells.json'), campus_images=dict(path=rel(TU1 / 'scenes/campus/images'), count=len(os.listdir(TU1 / 'scenes/campus/images')),
                                                                       receipt=f(TU1 / 'scenes/campus/scene_receipt.json')),
                   campus_split=f(TU1 / 'scenes/campus/split.json'), per_cell=cell_rows,
                   test_images_rule='campus WIDEN0 evaluation images that are in the cell test_images list (tu_campus.unit_members), = TRAINUNIT split.json'),
        runs=[dict(name='b151_2DGS_s0', method='2DGS', prior=None, cells=[0, 1, 2, 3]),
              dict(name='b151_GeoGS_ALS_s0', method='GeoGS', prior='ALS', cells=[0, 1, 2, 3]),
              dict(name='b151_GeoGS_LoD2_s0', method='GeoGS', prior='LoD2', cells=[0, 1, 2, 3]),
              dict(name='b151_CDGS_ALS_s0', method='CDGS', prior='ALS', cells=[0, 1, 2, 3]),
              dict(name='b151_CDGS_LoD2_s0', method='CDGS', prior='LoD2', cells=[0, 1, 2, 3]),
              dict(name='b151_LGDM_ALS', method='LGDM', prior='ALS', cells=None),
              dict(name='b151_LGDM_LoD2', method='LGDM', prior='LoD2', cells=None)],
        training_order=['b151_2DGS_s0', 'b151_GeoGS_ALS_s0', 'b151_GeoGS_LoD2_s0', 'b151_CDGS_ALS_s0', 'b151_CDGS_LoD2_s0'],
        cell_order=[0, 1, 2, 3], iterations=30000, seed=0,
        priors_rule='previous work ran GeoGS (ALS: geogs_ALS_fix1, LoD2: trust_LoD2_fix1), CDGS variant (cdgsnofit_ALS_s0, cdgsnofit_LoD2_s0) and '
                    'LGDM (mvsfuse_ALS, mvsfuse_LoD2) with both priors -> both priors here',
        methods={
            '2DGS': dict(
                previous_runs=[rel(SB / 'runs' / s / 'imgonly_2dgs_s0') for s in ['B0_b10', 'B173nb_b10', 'R1rep_b10']],
                source=dict(path=rel(SB / 'sources/2d-gaussian-splatting-adapters-v1'), train_py=f(SB / 'sources/2d-gaussian-splatting-adapters-v1/train.py'),
                            gaussian_model=f(SB / 'sources/2d-gaussian-splatting-adapters-v1/scene/gaussian_model.py'),
                            dataset_readers=f(SB / 'sources/2d-gaussian-splatting-adapters-v1/scene/dataset_readers.py'),
                            official='github.com/hbb1/2d-gaussian-splatting f3e3b9fa67bbd1c75e05167ff37391d8dab2a678'),
                image='jointbuildgs:2dgs-official-f3e3b9f-v1-b151',
                image_note='the original jointbuildgs:2dgs-official-f3e3b9f-v1 is no longer on the host; rebuilt from the repository Dockerfile.2dgs-official-v1 '
                           '(same build context SB/sources/2d-gaussian-splatting) on base jointbuildgs:geogs-official-db40c95-compat-v1 because the original base '
                           'jointbuildgs:geogs-official-db40c95-v1 is gone too (compat = that base + matplotlib 3.9.2 + LD_PRELOAD/LD_LIBRARY_PATH)',
                gaussian='2D (two scale columns, scene/gaussian_model.py create_from_pcd repeat(1, 2))',
                train_args=['train.py', '-s', '/scene', '-m', '/o/model', '--eval', '-r', '1', '--data_device', 'cpu'],
                env=dict(JBGS_SPLIT_JSON='/split.json', PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True'),
                defaults='iterations 30000, densify 500..15000 every 100, opacity reset 3000 (arguments/__init__.py, not passed)',
                scene_rule='SB twodgs/prep_scenes_2dgs.py rule on the TRAINUNIT cell scene: sparse/0 cameras.bin, images.bin and jbgs_calibration.json '
                           'byte copies of TU1 scenes/cell<k>/scene_ALS; points3D.ply = only its origin-0 rows (SfM points of the expanded cell; the '
                           'prior rows never enter 2DGS); images = TU1 campus images (same bytes as the fork site images); split = TU1 scenes/cell<k>/split.json',
                docker=dict(cpus='16', memory='48g', shm_size='8g', note='previous 46g / 16 CPUs per site; 48g = the TRAINUNIT cell limit')),
            'GeoGS': dict(
                previous_runs=dict(ALS=[rel(SB / 'runs' / s / 'geogs_ALS_fix1') for s in ['B0_b10', 'B173nb_b10', 'R1rep_b10']],
                                   LoD2=[rel(SF / 'runs' / s / 'trust_LoD2_fix1') for s in ['B0_b10', 'B173nb_b10', 'R1rep_b10']]),
                source=dict(path=rel(SF / 'geogs/source/GeoGS-official-adapters-v1-fix1'), train_py=f(SF / 'geogs/source/GeoGS-official-adapters-v1-fix1/train.py'),
                            gaussian_model=f(SF / 'geogs/source/GeoGS-official-adapters-v1-fix1/scene/gaussian_model.py')),
                image='jointbuildgs:geogs-official-db40c95-compat-v1', gaussian='2D (scene/gaussian_model.py repeat(1, 2))',
                train_args=['train.py', '-s', '/scene', '-m', '/o/model', '--lod_depth_path', '/scene/lod2_prior', '--da_depth_path', '/scene/da3_prior',
                            '--lod2_pcd_path', '/scene/lod2_pcd.ply', '--eval', '--lod_init', '--freeze_onlybldg', '--protect_bldg', '--dynamic_depth_weight',
                            '-r', '1', '--port', '0', '--iterations', '30000', '--stage_switch_iter', '8000', '--lambda_lod_init', '0.08', '--lambda_lod_anchor', '0.005'],
                inputs_rule='configs/phd/main_base151_v1/inputs_GeoGS.json (locked before its first input computation): the stage-1/FIX/BASELINES '
                            'scene rules (prior depth maps, DA3 depth consec12, protection cloud, initial points) with the cell as the region'),
            'CDGS': dict(
                previous_runs=dict(ALS=[rel(SL / 'runs' / s / 'cdgsnofit_ALS_s0') for s in ['B0_b10', 'B173nb_b10', 'R1rep_b10']],
                                   LoD2=[rel(SL / 'runs' / s / 'cdgsnofit_LoD2_s0') for s in ['B0_b10', 'B173nb_b10', 'R1rep_b10']]),
                source=dict(path=rel(SL / 'sources/cdgs-release-adapters-v3')),
                image='jointbuildgs:cdgs-official-db853c1-v1-b151',
                image_note='the original jointbuildgs:cdgs-official-db853c1-v1 is no longer on the host; rebuilt from the repository Dockerfile.cdgs-official-v1 '
                           'with every pip install constrained to the original freeze (configs/phd/main_base151_v1/docker/)',
                gaussian='3D (three scale columns)',
                inputs_rule='configs/phd/main_base151_v1/inputs_CDGS.json (locked before its first input computation): the FILL cdgsnofit scene rule '
                            '(prior depth per view) with the cell as the region'),
            'LGDM': dict(
                previous_runs=dict(ALS=[rel(SB / 'runs' / s / 'mvsfuse_ALS') for s in ['B0_b10', 'B173nb_b10', 'R1rep_b10']],
                                   LoD2=[rel(SB / 'runs' / s / 'mvsfuse_LoD2') for s in ['B0_b10', 'B173nb_b10', 'R1rep_b10']]),
                training=None, threshold_m=2.0,
                inputs_rule='configs/phd/main_base151_v1/inputs_LGDM.json (locked before its first computation): the BASELINES mvsfuse rule over the campus; '
                            'MVS = the JUDGECHECK-v2 base-value campus MVS (WIDEN0 819 images)')},
        filter=dict(
            threshold=0.01, comparison='<= (the TRAINUNIT code tu_train_entry.install_elongation_filter; the order text says "smaller than"; equality has measure zero)',
            flat_2D='axis ratio = min(scale) / max(scale) over the two scale columns; rows with ratio <= 0.01 get xyz_gradient_accum = 0 right before the '
                    'unchanged densify_and_prune, so neither densify_and_clone nor densify_and_split selects them (same code as TRAINUNIT)',
            volumetric_3D='axis ratio = (second largest scale) / (largest scale) over the three scale columns; rows with ratio <= 0.01 get '
                          'xyz_gradient_accum = 0 right before the unchanged densify_and_prune (order 1.7: needles, long in one direction only)',
            where='scripts/phd/main_base151_v1/b151_entry.py install_filter (monkey patch of GaussianModel.densify_and_prune; method files unchanged)',
            source='CityGaussianV2 elongation filter (Linketic/CityGaussian 3041bf5a, axis_ratio_threshold 0.01)'),
        gpu=dict(device=1, one_cell_at_a_time=True,
                 cap_rule='JBGS_GPU_CAP_GIB = (free memory of GPU 1 right before the launch, nvidia-smi) - 2 GiB; set with torch.cuda.set_per_process_memory_fraction; '
                          'recorded per attempt (order 1.2; no fixed value)',
                 start_rule='launch only when GPU 1 has >= 12 GiB free (another task may use GPU 1; it keeps priority through share_rule) and host MemAvailable >= 45 GB',
                 share_rule='TRAINUNIT-v2 rule: GPU 1 free < 1.5 GiB -> STOP file -> the entry saves a checkpoint at the next multiple of 100 and exits; '
                            'free < 0.75 GiB -> kill; a paused cell resumes from its checkpoint (--start_checkpoint) when GPU 1 is free again (not a stop under 1.9)',
                 host_guard='host MemAvailable < 20 GB -> kill this task\'s training container (memory snapshot recorded); post-processing containers of this task '
                            'are stopped first at < 25 GB',
                 explosion_guard='TRAINUNIT-v2 cell rule: gaussian count > 3 x the count at iteration 6,000 is recorded (health_override.jsonl), training '
                                 'continues; the per-process CUDA cap keeps an explosion inside this run',
                 no_new_cell_after='2026-11-24T00:00:00+09:00'),
        records=dict(every=1000, fields=['gaussians', 'elong_lt_001', 'elong_lt_01', 'elong quantiles', 'VmRSS/VmHWM', 'cgroup memory.current/peak',
                                         'cuda allocated/reserved now and peak'], iteration_500='seconds per iteration from 1 to 500 (time_check_500.json)',
                     psnr='train/test PSNR of the method train.py training_report at its test iterations (log), plus the test-view PSNR of the final model'),
        merge='after all four cells: keep Gaussians whose xy is in the original (unexpanded) cell [min, max); concatenate the four iteration-30000 '
              'point_cloud.ply files (TRAINUNIT tu_postcpu.merge rule)',
        membership=dict(rule='building footprint centroid cell (TRAINUNIT-v2 table, 154 buildings; the 151 in-scope buildings of JUDGECHECK-v2 are taken from it)',
                        table=f(W / 'docs/experiments/phd/main_trainunit_v1/v2/tables/building_membership.csv')),
        scoring={
            '4.1': dict(sites=['B0_b10', 'R1rep_b10', 'B173nb_b10'],
                        crop='merged model, gaussians inside the GTJUDGE views/<site>.json box (tu_postcpu.crop)',
                        render='RESCORE scripts/phd/main_rescore_v1/render_model.py with the method\'s own renderer and image (depth = surf_depth for 2D '
                               'methods, depth for CDGS) at the GTJUDGE views/<site>.json view list (the building-unit scene list: B0 243 ...)',
                        mesh='GTJUDGE mesh_job.py prepare / plan / tile / merge / finish (streamed TSDF voxel 0.05 m, trunc 0.25 m, bounded cleanup) = '
                             'the TRAINUNIT-v2 mesh rule',
                        scorer='GTJUDGE score_new.py (normal-line distance, cylinder accuracy samples) and add2_scores.metric_rows (section 3.4 accuracy rule)',
                        previous='GTJUDGE scenes/<site>__<prior>/distances/{2DGS_30000, GeoGS_30000, CDGS_30000, fusion}.npz through the same metric_rows; '
                                 'their meshes are RESCORE addendum3 primary.ply (the method\'s own TSDF + cleanup), recorded as a mesh difference'),
            '4.2': dict(gt='JUDGECHECK-v2 analysis/gt_<prior>.npz: paired GT points of the 151 in-scope buildings with case (0 both, 1 image only, 2 prior only, '
                           '4 image missing; 3 = outside the four cases) and tau',
                        mesh='per cell from that cell\'s own model, rendered at that cell\'s training images with the method\'s renderer, the same TSDF '
                             'voxel/trunc and cleanup rule, kept inside the original cell; a building is scored on the mesh of its cell',
                        distance='GTJUDGE normal_line.measure (point + four 5 cm tangent offsets, +-n, roof 10 m / wall 5 m)',
                        completeness='|s| <= tau of the GT point; no surface = not within',
                        accuracy='GTJUDGE section 3.4 rule: mesh samples 400 / m2, eligible within 1 m of the GT points, cylinder distance, the tau and case '
                                 'of the assigned GT point; ALS: samples with |n_z| < 0.5 excluded',
                        details='configs/phd/main_base151_v1/score151.json, locked before the first 151-building scoring',
                        small_n=200, two_groups='three evaluation regions (experiment buildings of JUDGECHECK-v2) vs the rest'),
        },
        rerun_rule='order 1.9: a stop is checked first (table 3.3); a setting/code error is fixed and rerun; otherwise one rerun with the same setting, '
                   'a second stop is final (결과 없음)',
    )
    (C / 'base151_v1.json').write_text(json.dumps(cfg, ensure_ascii=False, indent=1) + '\n')
    print('WROTE', C / 'base151_v1.json', sha(C / 'base151_v1.json'))


def lock(name='base151_v1'):
    p = C / f'{name}.json'
    lk = C / f'{name}.lock.json'
    assert not lk.exists(), f'{lk} exists'
    st = p.stat()
    rec = dict(file=str(p.relative_to(W)), saved_at=dt.datetime.fromtimestamp(st.st_mtime, KST).isoformat(), config_sha256=sha(p),
               locked_at=dt.datetime.now(KST).isoformat(), bytes=st.st_size, note='locked before the first computation it governs', scientific_verdict=None)
    lk.write_text(json.dumps(rec, ensure_ascii=False, indent=1) + '\n')
    print('LOCKED', lk, rec['config_sha256'])


if __name__ == '__main__':
    if sys.argv[1] == 'write':
        write()
    elif sys.argv[1] == 'lock':
        lock(*sys.argv[2:])
