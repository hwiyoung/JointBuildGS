"""Read input lineage and availability only; never open per-patch outcome arrays.

Does not create a building split or start measurements. scientific_verdict: null.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import time

import numpy as np

REPO, ART, OUT, DOC = map(Path, ('/repo', '/art', '/out', '/docs'))
PH = ART / 'phase-payloads/phd'
DENSE = ART / 'phase-payloads/p0-audit/data/work/mvs/colmap_dense'
S0 = PH / 'main_stage0_v1/PHD-MAIN-STAGE0-v1'
PREP = PH / 'main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1'
SITES = ['B0_b10', 'B173nb_b10', 'B173_b0', 'R1rep_b10']

def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(4 << 20), b''):
            h.update(b)
    return h.hexdigest()

def dump(p, x):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(x, ensure_ascii=False, indent=2, allow_nan=False) + '\n')

def images(p):
    result = {}
    with p.open('rb') as f:
        count, = struct.unpack('<Q', f.read(8))
        for _ in range(count):
            iid, = struct.unpack('<i', f.read(4))
            q = struct.unpack('<4d', f.read(32))
            t = struct.unpack('<3d', f.read(24))
            cid, = struct.unpack('<i', f.read(4))
            name = bytearray()
            while True:
                c = f.read(1)
                if not c:
                    raise ValueError('truncated image name')
                if c == b'\x00':
                    break
                name.extend(c)
            n, = struct.unpack('<Q', f.read(8))
            f.seek(24 * n, 1)
            result[name.decode()] = dict(id=iid, q=q, t=t, camera_id=cid)
    return result

def main():
    t0 = time.monotonic()
    source = images(DENSE / 'sparse/images.bin')
    source_by_stem = {Path(k).stem: v for k, v in source.items()}
    assert len(source_by_stem) == len(source), 'duplicate stems'
    names = sorted(source)
    available = [n for n in names if (DENSE / 'images' / n).is_file()]
    missing = sorted(set(names) - set(available))
    # Inventory arithmetic only: the final split requires the scoped candidate list.
    global_eval = names[::8]
    global_train = [n for i, n in enumerate(names) if i % 8]
    per_site = []
    for site in SITES:
        folder = S0 / 'fork_inputs/s61' / site
        model = images(folder / 'scene_LoD2/sparse/0/images.bin')
        split = json.loads((folder / 'split.json').read_text())
        diffs = []
        for name, row in model.items():
            if Path(name).stem not in source_by_stem:
                diffs.append(dict(name=name, reason='absent_from_global_model'))
                continue
            src = source_by_stem[Path(name).stem]
            if not (np.allclose(row['q'], src['q'], rtol=0, atol=1e-12)
                    and np.allclose(row['t'], src['t'], rtol=0, atol=1e-12)):
                diffs.append(dict(name=name, max_q_difference=float(np.max(np.abs(np.array(row['q'])-src['q']))),
                                  max_t_difference_m=float(np.max(np.abs(np.array(row['t'])-src['t'])))))
        receipt = PREP / 'mvs' / ('box_' + site) / 'colmap_receipt.json'
        run = json.loads(receipt.read_text()) if receipt.exists() else None
        localtrain = {Path(n).stem for n in split['train']}
        localeval = {Path(n).stem for n in split.get('test', [])}
        geometric = list((PREP / 'mvs' / ('box_' + site) / 'stereo/depth_maps').glob('*.geometric.bin'))
        per_site.append(dict(site=site, pose_count=len(model), pose_differences=diffs,
            split_train=len(localtrain), split_test=len(localeval), geometric_files=len(geometric),
            receipt=run, receipt_path=str(receipt),
            hypothetical_global_train_in_local_test=len(localeval & {Path(n).stem for n in global_train}),
            hypothetical_global_test_in_local_train=len(localtrain & {Path(n).stem for n in global_eval})))
    timed = [x for x in per_site if x['receipt'] and x['receipt']['exit_code'] == 0]
    # Denominator is selected training inputs, not only successful depth outputs.
    seconds = sum(x['receipt']['seconds'] for x in timed)
    inputs = sum(x['split_train'] for x in timed)
    rate = seconds / inputs
    config = json.loads((REPO / 'configs/phd/main_uncert_v1/uncert_v1.json').read_text())
    inventory = []
    raw = ART / 'phase-payloads/p0-audit/data/raw'
    for p in [raw / 'tum2twin/TUM_Downtown_ULS_20241217_nadir.laz'] + sorted((raw / 'als').glob('*.laz')) + sorted((raw / 'lod2').glob('*')):
        inventory.append(dict(path=str(p), exists=p.is_file(), bytes=p.stat().st_size if p.is_file() else None))
    upstream = [REPO / 'configs/phd/main_uncert_v1/uncert_v1.json',
                REPO / 'configs/phd/main_uncert_view_v1/view_v1_1.json',
                REPO / 'configs/phd/main_prep_measure_v1/prep_v5.json',
                DENSE / 'sparse/images.bin', DENSE / 'sparse/cameras.bin',
                PREP / 'step01/ranges.json', PREP / 'step06/box_views.json']
    result = dict(task_id='PHD-MAIN-WIDEN0-v2', scientific_verdict=None,
        made=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
        stage='input_preflight_only_no_patch_outcomes_read',
        name_match='unique exact stem; fork exports .JPG as .jpg; q and t compared directly',
        commit=os.environ['WIDEN_COMMIT'], image_id=os.environ['WIDEN_IMAGE_ID'],
        versions=dict(python=sys.version, numpy=np.__version__),
        global_model=dict(path=str(DENSE / 'sparse'), images=len(names), available_images=len(available), missing_images=missing,
            hypothetical_whole_model_split=dict(train=len(global_train), evaluation=len(global_eval),
                rule='sorted posed images; index % 8 == 0 evaluation; candidate scope not yet frozen')),
        sites=per_site, inputs=inventory,
        mvs_estimate=dict(source_runs=len(timed), selected_images=inputs, seconds=seconds,
            seconds_per_selected_image=rate,
            provisional_all_posed_images_single_gpu_hours=len(names)*rate/3600,
            provisional_global_training_single_gpu_hours=len(global_train)*rate/3600,
            provisional_global_training_two_gpu_ideal_hours=len(global_train)*rate/7200,
            caveat='inventory-scale linear estimate; final spatial scope and replay overhead not yet selected'),
        tau_cm=config['cells']['tau_cm'],
        upstream_sha256={str(p): sha(p) for p in upstream},
        blocking_missing_common_base=bool(missing or any(x['pose_differences'] for x in per_site)),
        seconds_elapsed=time.monotonic()-t0)
    dump(OUT / 'input_preflight.json', result)
    dump(DOC / 'tables/input_preflight.json', result)
    print(json.dumps({k: result[k] for k in ('global_model', 'mvs_estimate', 'blocking_missing_common_base')}, ensure_ascii=False, indent=2))
    for row in per_site:
        print(row['site'], 'poses', row['pose_count'], 'differences', len(row['pose_differences']),
              'train/test', row['split_train'], row['split_test'])

if __name__ == '__main__':
    main()
