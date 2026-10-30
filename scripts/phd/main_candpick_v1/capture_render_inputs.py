"""Record the exact photo/camera/derived inputs used by the nontraining checks."""
import importlib.metadata
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0, '/repo')
from gs_engine import cameras
from input_audit import bind, sha
from prepare_places import save


def main():
    target = Path('/docs/render_inputs_v1.json'); assert not target.exists()
    cache, units = {}, {}
    for unit in ['B173_ALS', 'R1_LoD2', 'B173_LoD2', 'R1_ALS']:
        rows = []
        for c in cameras(unit):
            p = c['path']; key = str(p.resolve())
            if key not in cache: cache[key] = bind(p.resolve())
            rows.append(dict(name=c['name'], source=cache[key], K=c['K'].tolist(),
                             world_to_camera=c['E'].tolist(), width=c['width'], height=c['height']))
        root = Path('/out/scenes') / unit
        files = {name: bind(root / name) for name in ['background.ply', 'candidate_geometry.npz',
            'initial_right_candidate.npz', 'candidate_color.npy', 'candidate_color_sample_count.npy']}
        scene = json.loads((root / 'scene.json').read_text())
        assert files['background.ply']['sha256'] == scene['background']['sha256']
        assert files['candidate_geometry.npz']['sha256'] == scene['geometry']['sha256']
        units[unit] = dict(training_views=rows, derived=files)
    report = dict(task_id='PHD-MAIN-CANDPICK-v1', at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        role='post-check input inventory; not the pre-training candpick_v1 configuration lock',
        commit=os.environ.get('CANDPICK_COMMIT'), docker_image=os.environ.get('CANDPICK_IMAGE'),
        versions={k: importlib.metadata.version(k) for k in ['numpy', 'scipy', 'torch', 'gsplat', 'plyfile']},
        renderer=dict(function='gsplat.rasterization_2dgs', packed=False, render_mode='RGB',
            near_plane=.01, background_color='black', antialiasing='native 2DGS pixel filter',
            baseline_SH=3, candidate_inplane_sigma_m=.125, candidate_third_scale_m=1e-8,
            original_to_gsplat_principal_point_shift_px=.5),
        units=units, unique_photo_files=len(cache), optimizer_steps=0, scientific_verdict=None,
        implementation={str(p.relative_to('/repo')): sha(p) for p in [
            Path('/repo/scripts/phd/main_candpick_v1/gs_engine.py'),
            Path('/repo/src/stage2/colmap_io.py'),
            Path('/repo/src/phd/forks/GeoGS-conf-guided-v1-r18/utils/loss_utils.py')]})
    save(target, report)
    print('Captured', len(cache), 'unique training photos and four derived scenes; no optimizer.')


if __name__ == '__main__': main()
