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
    for n in ['sparse/0/cameras.bin', 'sparse/0/points3D.ply', 'jbgs_calibration.json']:
        shutil.copyfile(CELL3 / n, d / n)
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
               copied_from_cell3_scene=['cameras.bin', 'points3D.ply (same initial points)', 'jbgs_calibration.json'],
               files={n: H.sha(d / n) for n in ['sparse/0/images.bin', 'sparse/0/cameras.bin', 'sparse/0/points3D.ply', 'split.json']}, scientific_verdict=None)
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
        raise SystemExit('addendum 2 section 2: training only after the user says so (not wired to run from here yet)')
