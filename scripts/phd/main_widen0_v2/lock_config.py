"""Freeze all choices before spatial counts, building split, or patch outcomes."""
import datetime as dt
import hashlib
import json
from pathlib import Path

R, C, O = Path('/repo'), Path('/cfg'), Path('/out')
up = json.loads((R / 'configs/phd/main_uncert_v1/uncert_v1.json').read_text())
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

cfg = dict(
    task_id='PHD-MAIN-WIDEN0-v2', scientific_verdict=None,
    created_at=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
    frame=dict(crs='EPSG:25832', world_shift_xyz_m=[690953., 5336071., 604.], z_bridge_als_lod2_m=45.7,
               u_axis_angle_degrees_ccw_from_easting=70.0),
    scope=dict(rule='Intersection of observed image-derived MVS XY support, nadir ULS XY support, ALS XY support and raw LoD2 tile coverage. No patch outcome enters selection.',
        coverage_grid_m=0.5, coverage_origin='integer multiple of 0.5 m in EPSG:25832',
        coverage_source='Inherited survey 0.5 m occupancy rasters; verify nadir header and current image geometry remain inside raster bounds; extend from raw inputs if needed.',
        image_support='Existing 937-image MVS used for source coverage inventory only. It contains evaluation images and is not the new training-only MVS or error measurement.',
        building_membership='GroundSurface XY intersects common support. Preserve whole building split; patch centre must be inside common XY support.',
        evaluation_regions=['B0_b10', 'B173nb_b10', 'B173_b0', 'R1rep_b10'],
        exploration_regions=['R1', 'R2', 'R3', 'R4', 'R5', 'SW', 'R3E']),
    split=dict(unit='LoD2 building attribute', forced_development='any GroundSurface intersection with four evaluation ranges or seven exploration ranges',
        other_buildings='sort exact building IDs ascending, numpy default_rng(20261023).choice without replacement',
        holdout_fraction=0.3, holdout_count='floor(0.30 * other_buildings)', seed=20261023,
        patch_assignment='LoD2 owning face; ALS faces from view_v1_1.json faces exactly; no face match excluded',
        seal='all holdout patch outcomes and candidate places only in /out/holdout; no cell areas in reports or either archive',
        permitted_public_holdout=['building_count', 'patch_count', 'area_m2', 'fraction_patches_with_GT', 'sha256']),
    grid=dict(core_m=100., overlap_each_side_m=10., origin_epsg25832_m=[0., 0.],
              ownership='core lower inclusive upper exclusive; overlapping inputs only; do not duplicate patches'),
    tau_m=dict(ALS=0.1266, LoD2=0.2),
    tau_source=dict(ALS='median of B0 12.66, B173nb 14.70, R1 10.34 cm, user order 3.4',
        LoD2='User clarification in this chat on 2026-10-24: use 20 cm; applies to roof-like and wall-like patches.',
        role='Evaluation threshold only; same numeric value as existing LoD2 uncertainty is not a change of its definition',
        historical_tau_cm=up['cells']['tau_cm'], preserve_historical=True),
    patch=dict(cell_m=0.25, source='stage-1 plane/TIN store constructors and outward normals from main_uncert_v1',
        roof_like_max_angle_deg=45., definitions_source='configs/phd/main_uncert_v1/uncert_v1.json',
        faces_source='configs/phd/main_uncert_view_v1/view_v1_1.json faces'),
    definitions=dict(up['defs'], ring_radii_m=[1.5], ring_default_m=1.5),
    ground_truth=dict(source='TUM_Downtown_ULS_20241217_nadir.laz only', manual_uls=False,
        rule='Stage-1 v3 ground-truth point preparation and exclusions, then main_uncert_v1 column/face/plane definitions',
        B0_difference='Previous uncertainty mixed nadir and manual ULS; retain old values as comparison only, never include manual points in this task'),
    mvs=dict(training_only=True, evaluation_rule='2026-09-15 candidate rule; name order index % 8 == 0 is evaluation on the full scoped candidate list',
        variant='a: geometric depth, finite > 0 and confidence > 0',
        image='colmap/colmap@sha256:187ca5ec98e55ed8fbec5f43f9d8f78b7a322b3b7413356634191f7a43c1efcf',
        max_image_size=1024, num_iterations=3, geom_consistency=True, filter=True, cache_size=32,
        source_views=20, gpu_stop_hours=48,
        wait_rule='Wait while any other compute process uses a GPU; record wait duration; GPU for MVS depth only'),
    components=dict(radius_m=0.36, radius_fallback='if median nearest-neighbour spacing < 0.18 or > 0.36 m, use 1.5 * that median; record it',
        groups=['prior', 'building', 'roof_like', 'cell'], minimum_area_m2=1., neighbour_radius_m=1.,
        magnitude_bins_m=[0.5, 1., 2., 4.], signs=['positive', 'negative']),
    cells=dict(order=['both_right', 'prior_wrong', 'image_wrong', 'both_wrong', 'no_mvs_prior_right', 'no_mvs_prior_wrong', 'no_gt'],
        source='User order 4.3', right_inclusive=True,
        prior_error='abs(gt_p)', mvs_error='actual error e from main_uncert_v1, not abs(mvs_p - gt_p)',
        missing_reasons='Retain original face, point-count and plane-fit failure status; never convert missing values to zero'),
    figures=dict(dpi=300, formats=['png', 'pdf', 'json'], north_up=True,
        holdout='grey hatching on scope map only; no holdout outcome plots or photo crops',
        difference_axis_m=[0.01, 10.], difference_axis='log', hist_bins=60,
        signed='outward +, inward -', area_weighted=True,
        representative_cells=['prior_wrong', 'image_wrong', 'both_wrong'], photos_per_cell=20,
        photos_per_building_max=3, photo_margin_m=3., image_rule='largest projected component in a nadir training image; original resolution crop; GT-height outline',
        photo_selection='descending component area; ties building ID then component ID; no cause labels'),
    execution=dict(training=False, gpu='MVS depth only', cpu_nice=19, container_memory_gib=32, process_max_gib=32,
        writable=['configs/phd/main_widen0_v2/', 'scripts/phd/main_widen0_v2/', 'docs/experiments/phd/main_widen0_v2/',
                  'PH/main_widen0_v2/PHD-MAIN-WIDEN0-v2/']),
    amendments=[])
dest = C / 'widen0_v2.json'
if dest.exists():
    raise SystemExit('Existing config: use an explicit amendment, never overwrite a lock.')
dest.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + '\n')
lock = dict(task_id=cfg['task_id'], locked_at=cfg['created_at'], config_sha256=sha(dest),
    before_patch_measurements=True, before_building_split=True, scientific_verdict=None,
    source_sha256={p: sha(R / p) for p in [
        'configs/phd/main_uncert_v1/uncert_v1.json', 'configs/phd/main_uncert_view_v1/view_v1_1.json',
        'configs/phd/main_prep_measure_v1/prep_v5.json', 'docs/experiments/phd/main_widen0_v2/발주문_v2.md']})
(C / 'widen0_v2.lock.json').write_text(json.dumps(lock, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(lock, ensure_ascii=False, indent=2))
