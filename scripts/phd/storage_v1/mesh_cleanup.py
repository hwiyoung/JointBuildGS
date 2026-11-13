#!/usr/bin/env python3
"""PHD-STORAGE-v1 mesh cleanup: after a mesh has been scored, remove its regenerable intermediates.

Usage:
  python3 -I mesh_cleanup.py RUN_DIR [--metrics FILE ...] [--dry-run]

RUN_DIR is one mesh folder (for example .../meshes/<key>, holding final.json, final.ply, final_work/).
Order of work:
  1. Every metrics json must exist and parse. Default: RUN_DIR/final.json. If it has "status", it must be
     "PASS"; if it has "mesh_sha256" and RUN_DIR/final.ply exists, the ply must match. Otherwise nothing is
     removed and RUN_DIR/storage_cleanup.json records why.
  2. Inside RUN_DIR only, remove exactly these kinds (regular files, one hard link, not symlinks):
       TSDF tiles            **/tiles/tile<k>.npz          (tile<k>.json stays)
       mesh merge temporary  **/bounded_merge/*.bin
       mesh input arrays     **/inputs/depth_masked.npy, **/inputs/rgb.npy   (meta.json, cams.npz stay)
     Scored mesh, final ply, metrics, configs and figures are never touched.
  3. Removed paths and sizes go to RUN_DIR/storage_cleanup.json.
--dry-run lists what would be removed (stdout, tab separated) and writes nothing.
"""
import argparse
import hashlib
import json
import os
import re
import stat
import sys
import time
from pathlib import Path

KINDS = (
    ('tsdf_tile', re.compile(r'(^|/)tiles/tile\d+\.npz$')),
    ('merge_temp', re.compile(r'(^|/)bounded_merge/[^/]+\.bin$')),
    ('mesh_input', re.compile(r'(^|/)inputs/(depth_masked|rgb)\.npy$')),
)


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def check_metrics(run, metrics):
    for m in metrics:
        try:
            doc = json.loads(Path(m).read_text())
        except (OSError, ValueError) as e:
            return f'metrics unreadable: {m}: {e}'
        if not isinstance(doc, dict):
            return f'metrics is not an object: {m}'
        if 'status' in doc and doc['status'] != 'PASS':
            return f'metrics status is {doc["status"]!r}: {m}'
        ply = run / 'final.ply'
        if doc.get('mesh_sha256') and ply.is_file() and sha256(ply) != doc['mesh_sha256']:
            return f'final.ply sha256 differs from {m}'
    return None


def candidates(run):
    for dirpath, dirnames, filenames in os.walk(run, followlinks=False):
        for name in filenames:
            p = Path(dirpath) / name
            rel = p.relative_to(run).as_posix()
            kind = next((k for k, rx in KINDS if rx.search(rel)), None)
            if kind:
                yield kind, p, rel


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('run_dir')
    ap.add_argument('--metrics', nargs='+', help='metrics json files (default RUN_DIR/final.json)')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    run = Path(a.run_dir).resolve()
    if not run.is_dir():
        sys.exit(f'not a directory: {run}')
    metrics = [Path(m).resolve() for m in (a.metrics or [run / 'final.json'])]
    record = dict(schema='PHD_STORAGE_MESH_CLEANUP_v1', run_dir=str(run), metrics=[str(m) for m in metrics],
                  dry_run=a.dry_run, at=time.strftime('%Y-%m-%dT%H:%M:%S%z'), removed=[], kept_unsafe=[])
    why = check_metrics(run, metrics)
    if why:
        record.update(status='SKIP', reason=why)
        print(f'SKIP\t{why}')
        if not a.dry_run:
            (run / 'storage_cleanup.json').write_text(json.dumps(record, indent=2, ensure_ascii=False))
        return 1
    total = 0
    for kind, p, rel in candidates(run):
        st = os.lstat(p)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            record['kept_unsafe'].append(dict(path=rel, reason='not a single-link regular file'))
            continue
        size = st.st_blocks * 512
        if a.dry_run:
            print(f'{kind}\t{size}\t{rel}')
        else:
            p.unlink()
        record['removed'].append(dict(kind=kind, path=rel, bytes=size))
        total += size
    record.update(status='DRY_RUN' if a.dry_run else 'DONE', removed_bytes=total)
    print(f'{record["status"]}\t{len(record["removed"])} files\t{total / 2**30:.2f} GiB')
    if not a.dry_run:
        (run / 'storage_cleanup.json').write_text(json.dumps(record, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
