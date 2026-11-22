#!/usr/bin/env python3
"""PHD-MAIN-BASE151-v1 addendum 2 section 2 (preparation only; training is started only when the user says so):
2DGS cell 3, 30,000 iterations, seed 0, the b151_2DGS_s0 cell-3 settings; ONLY the training image list changes.

  python3 b151_add2_retrain.py scene <list.txt> <tag>   # OUT/add2/scenes/<tag>: cameras.bin = cell-3 scene copy; images.bin = the campus records of
                                                        # the listed images + the cell-3 test images; points3D.ply = cell-3 scene copy (same initial
                                                        # points); split.json = {train: list, test: cell-3 test}
  python3 b151_add2_retrain.py check <tag>              # CPU container, the 2DGS image: the official scene reader loads the scene with the split
                                                        # (no training, no GPU)
  python3 b151_add2_retrain.py cmd <tag>                # prints the training command (b151_host.command with the scene of <tag>); not run
  python3 b151_add2_retrain.py train <tag>              # (only after the user's go) the training attempt, then mesh + score of the cell-3 units
Run name a2_2DGS_<tag> (OUT/runs/a2_2DGS_<tag>/cell3). scientific_verdict: null
"""
import json
import shutil
import struct
import subprocess
import sys

import b151_host as H

OUT = H.OUT
TU1 = H.TU1
SC = OUT / 'add2' / 'scenes'
CELL3 = OUT / 'scenes/2DGS/cell3'


def records(p):
    """raw images.bin records keyed by image name (bytes of each record kept as they are)"""
    out = {}
    with open(p, 'rb') as f:
        n = struct.unpack('<Q', f.read(8))[0]
        for _ in range(n):
            start = f.tell()
            f.read(4 + 32 + 24 + 4)
            name = b''
            while (c := f.read(1)) != b'\x00':
                name += c
            n2 = struct.unpack('<Q', f.read(8))[0]
            f.read(24 * n2)
            end = f.tell()
            f.seek(start)
            out[name.decode()] = f.read(end - start)
    return out


def stem(n):
    return n.rsplit('.', 1)[0]


def scene(listfile, tag):
    names = [x.strip() for x in open(listfile) if x.strip()]
    split3 = json.loads((CELL3 / 'split.json').read_text())
    camp = records(TU1 / 'scenes/campus/scene_ALS/sparse/0/images.bin')
    byst = {stem(k): k for k in camp}
    miss = [n for n in names if stem(n) not in byst]
    assert not miss, f'not in the campus images.bin: {miss[:5]} ({len(miss)})'
    test = split3['test']
    clash = sorted(set(map(stem, names)) & set(test))
    assert not clash, f'test images in the training list: {clash[:5]}'
    keep = sorted({byst[stem(n)] for n in names} | {byst[t] for t in test})
    d = SC / tag
    (d / 'sparse/0').mkdir(parents=True, exist_ok=True)
    with open(d / 'sparse/0/images.bin', 'wb') as f:
        f.write(struct.pack('<Q', len(keep)))
        for i, k in enumerate(keep):   # image ids renumbered 1..N in name order, as in the TRAINUNIT cell scenes (only the id differs)
            f.write(struct.pack('<i', i + 1) + camp[k][4:])
    for n in ['sparse/0/cameras.bin', 'sparse/0/points3D.ply']:
        shutil.copyfile(CELL3 / n, d / n)
    # calibration manifest: the campus entries of the kept images (the cell-3 copy lists only the cell-3 images; the first add51 attempts
    # stopped at iteration 0 on that). Entries of images also in the cell-3 manifest must be equal there.
    cc = json.loads((TU1 / 'scenes/campus/scene_ALS/jbgs_calibration.json').read_text())
    c3 = json.loads((CELL3 / 'jbgs_calibration.json').read_text())
    sk = [stem(k) for k in keep]
    assert all(k in cc['images'] for k in sk), 'kept image missing from the campus calibration'
    assert all(cc['images'][k] == v for k, v in c3['images'].items() if k in sk), 'campus and cell-3 calibration differ'
    H.dump(d / 'jbgs_calibration.json', {**{k: v for k, v in c3.items() if k != 'images'}, 'images': {k: cc['images'][k] for k in sk}})
    H.dump(d / 'split.json', dict(train=[stem(n) for n in names], test=test))
    (d / 'images').mkdir(exist_ok=True)
    # check: the records of images that are also in the cell-3 scene are byte-equal there
    old = records(CELL3 / 'sparse/0/images.bin')
    same = [k for k in keep if k in old]
    new = records(d / 'sparse/0/images.bin')
    diff = [k for k in same if old[k] != new[k]]
    rec = dict(at=H.now().isoformat(), tag=tag, list=str(listfile), list_sha256=H.sha(listfile), train=len(names), test=len(test), images_bin_records=len(keep),
               also_in_cell3_scene=len(same), byte_equal_to_cell3_scene_records=len(same) - len(diff), differ=diff[:10],
               added_vs_cell3_train=sorted(set(map(stem, names)) - set(split3['train'])), removed_vs_cell3_train=sorted(set(split3['train']) - set(map(stem, names))),
               copied_from_cell3_scene=['cameras.bin', 'points3D.ply (same initial points)'], calibration='campus jbgs_calibration.json entries of the kept images (equal to the cell-3 entries where both have them)',
               files={n: H.sha(d / n) for n in ['sparse/0/images.bin', 'sparse/0/cameras.bin', 'sparse/0/points3D.ply', 'jbgs_calibration.json', 'split.json']}, scientific_verdict=None)
    H.dump(d / 'scene_receipt.json', rec)
    print('SCENE', tag, rec['train'], rec['test'], rec['images_bin_records'], 'byte_equal', rec['byte_equal_to_cell3_scene_records'], '/', len(same),
          'added', len(rec['added_vs_cell3_train']), 'removed', len(rec['removed_vs_cell3_train']), flush=True)


def spec(tag):
    c = H.cfg()
    s = H.method_spec(c, 'b151_2DGS_s0')
    s['run'] = f'a2_2DGS_{tag}'
    return s


def mounts(tag):
    d = SC / tag
    return [(d, '/scene', 'ro'), (TU1 / 'scenes/campus/images', '/scene/images', 'ro'), (d / 'split.json', '/split.json', 'ro')], ['JBGS_SPLIT_JSON=/split.json']


def cmd(tag, attempt_dir=None, cap=21.5):
    s = spec(tag)
    orig = H.cell_mounts
    H.cell_mounts = lambda sp, k: mounts(tag)
    try:
        return H.command(s, 3, attempt_dir or (OUT / 'runs' / s['run'] / 'cell3' / 'attempt1'), cap)
    finally:
        H.cell_mounts = orig


def check(tag):
    s = spec(tag)
    d = SC / tag
    py = ('import os,sys,json; sys.argv=["x"]; from scene.dataset_readers import sceneLoadTypeCallbacks as S; '
          'i=S["Colmap"]("/scene","images",True); print("CHECK train",len(i.train_cameras),"test",len(i.test_cameras),"points",len(i.point_cloud.points)); '
          'sp=json.load(open("/split.json")); n=lambda c:c.image_name.rsplit(".",1)[0]; '
          'print("CHECK train_equal",sorted(map(n,i.train_cameras))==sorted(sp["train"]),"test_equal",sorted(map(n,i.test_cameras))==sorted(sp["test"]))')
    c = ['docker', 'run', '--rm', '--network', 'none', '--user', '1000:1000', '--cpus', '4', '--memory', '16g', '--name', f'jbgs-b151-a2check-{tag}'.replace('_', '-').lower(),
         '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'JBGS_SPLIT_JSON=/split.json', '-e', 'HOME=/tmp',
         '-v', f'{s["source"]}:/source:ro', '-v', f'{d}:/scene:ro', '-v', f'{TU1 / "scenes/campus/images"}:/scene/images:ro', '-v', f'{d / "split.json"}:/split.json:ro',
         '-w', '/source', '--entrypoint', 'python', s['image'], '-c', py]
    r = subprocess.run(c, capture_output=True, text=True)
    print(r.stdout[-2000:], r.stderr[-2000:], 'RC', r.returncode, flush=True)
    H.dump(d / 'check.json', dict(at=H.now().isoformat(), tag=tag, stdout=r.stdout[-4000:], stderr=r.stderr[-4000:], rc=r.returncode, scientific_verdict=None))


def train(tag, dry=False):
    """one training attempt of cell 3 (b151_host.attempt: the b151 GPU share, host guard and pause rules; one rerun on a stop that is not a
    code error, as in the order 1.9), then the cell-3 units of 4.2 (b151_post42.unit: render -> mesh -> score ALS and LoD2) and the gather.
    --dry: resolve everything (command, units, render / score names) without starting a container."""
    import b151_post42 as P42
    from b151_post41 import render_cmd
    s = spec(tag)
    run = s['run']
    assert (SC / tag / 'scene_receipt.json').exists(), f'no scene {tag}: run scene first'
    units = [u['unit'] for u in json.loads((P42.M / 'units/layout.json').read_text())['units'] if u['cell'] == 3]
    if dry:
        name, c = cmd(tag)
        print('DRY train', name, 'mounts /scene ->', SC / tag)
        print('DRY units', len(units), units)
        print('DRY priors', P42.priors_of(run), 'render', render_cmd('2DGS', f'{units[0]}__ALS__{run}')[-1])
        print('DRY receipt', H.cell_dir(run, 3) / 'receipt.json', 'exists', (H.cell_dir(run, 3) / 'receipt.json').exists())
        return
    orig = H.cell_mounts
    H.cell_mounts = lambda sp, k: mounts(tag)
    try:
        st = H.attempt(s, 3)
        while st == 'PAUSED_SAVED':
            H.wait_launch()
            st = H.attempt(s, 3)
        if st != 'TRAINING_COMPLETE':
            st = H.attempt(s, 3)
    finally:
        H.cell_mounts = orig
    if st != 'TRAINING_COMPLETE':
        print('TRAIN_STOP', st, flush=True)
        return
    ok = {u: P42.unit(run, u) for u in units}
    H.dump(OUT / 'add2' / f'{run}_units.json', dict(at=H.now().isoformat(), run=run, units=ok, scientific_verdict=None))
    if all(ok.values()):
        P42.gather(run)
    print('TRAIN_DONE', run, ok, flush=True)


def post(tag):
    """the cell-3 units of a trained run (b151_post42.unit) and the gather, with the GPU rule changed by the user (2026-11-22 01:1x): a render may
    start while another process is on GPU 1 when GPU 1 has >= 8 GiB free (the render cap stays fraction .25 = 6 GiB, no retry with a larger cap)."""
    import b151_post41 as P41
    import b151_post42 as P42
    run = spec(tag)['run']
    rule = lambda: P41.gpu_free_mib() >= 8 * 1024
    P42.gpu_ready = rule
    units = [u['unit'] for u in json.loads((P42.M / 'units/layout.json').read_text())['units'] if u['cell'] == 3]
    H.dump(OUT / 'add2' / f'{run}_gpu_share.json', dict(at=H.now().isoformat(), run=run, rule='render starts when GPU 1 free >= 8 GiB, other processes allowed',
                                                      render_fraction='.25', decided_by='user 2026-11-22', gpu_apps_at_start=H.gpu_apps(), scientific_verdict=None))
    ok = {u: P42.unit(run, u) for u in units}
    H.dump(OUT / 'add2' / f'{run}_units.json', dict(at=H.now().isoformat(), run=run, units=ok, scientific_verdict=None))
    if all(ok.values()):
        P42.gather(run)
    print('TRAIN_DONE', run, ok, flush=True)


def post_als(tag):
    """2026-11-22: the LoD2 scores stalled twice under the memory pressure of the shared docker slice (see add2/stuck_score_*); the report
    items use ALS only, so: the cell-3 units with the ALS score only (render / mesh / ALS score unchanged), then the ALS gather. The LoD2 unit scores
    and their gather are run afterwards with 'post' (it skips what exists)."""
    import b151_post41 as P41
    import b151_post42 as P42
    run = spec(tag)['run']
    P42.gpu_ready = lambda: P41.gpu_free_mib() >= 8 * 1024
    P42.priors_of = lambda r: ('ALS', ['ALS'])
    units = [u['unit'] for u in json.loads((P42.M / 'units/layout.json').read_text())['units'] if u['cell'] == 3]
    ok = {u: P42.unit(run, u) for u in units}
    H.dump(OUT / 'add2' / f'{run}_units_ALS.json', dict(at=H.now().isoformat(), run=run, units=ok, scientific_verdict=None))
    if all(ok.values()):
        P41.sh(P41.gt_cpu(f'gather-{run}-ALS'.replace('_', '-').lower(), '/b151s/b151_score151.py', 'gather', run, 'ALS', cpus='4', mem='32g'),
               OUT / 'logs' / 'post42' / f'gather_{run}_ALS.log')
    print('ALS_DONE', run, ok, flush=True)


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'scene':
        scene(a[1], a[2])
    elif a[0] == 'check':
        check(a[1])
    elif a[0] == 'cmd':
        name, c = cmd(a[1])
        print(name); print(' '.join(c))
    elif a[0] == 'train':
        train(a[1], dry='--dry' in a)
    elif a[0] == 'post_als':
        post_als(a[1])
    elif a[0] == 'post':
        post(a[1])
