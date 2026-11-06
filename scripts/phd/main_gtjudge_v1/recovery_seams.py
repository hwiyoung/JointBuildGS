"""Read-only diagnosis of already failed exact tile-seam checks."""
import sys
import numpy as np
from common import O, D, dump, now, sha


def main(site, prior):
    stem = f'{site}__{prior}__fix'
    root = O / 'meshes' / stem / 'final_work'
    cache = root / 'bounded_merge'
    n = (cache / 'vcode.bin').stat().st_size // 8
    vertex = np.memmap(cache / 'vertices.bin', dtype='f8', mode='r', shape=(n, 3))
    color = np.memmap(cache / 'colors.bin', dtype='f8', mode='r', shape=(n, 3))
    code = np.memmap(cache / 'vcode.bin', dtype='i8', mode='r', shape=(n,))
    rep = np.memmap(cache / 'representative.bin', dtype='i8', mode='r', shape=(n,))
    tile = np.memmap(cache / 'tile.bin', dtype='i4', mode='r', shape=(n,))
    counts = dict(coordinates=0, colours=0, within_same_tile=0)
    maximum = dict(coordinates=0., colours=0.)
    examples = []
    for start in range(0, n, 100000):
        ids = np.arange(start, min(n, start + 100000))
        ids = ids[code[ids] >= 0]
        other = rep[ids]
        dv = np.abs(vertex[ids] - vertex[other])
        dc = np.abs(color[ids] - color[other])
        badv, badc = (dv != 0).any(1), (dc != 0).any(1)
        counts['coordinates'] += int(badv.sum())
        counts['colours'] += int(badc.sum())
        counts['within_same_tile'] += int(((badv | badc) & (tile[ids] == tile[other])).sum())
        maximum['coordinates'] = max(maximum['coordinates'], float(dv.max(initial=0)))
        maximum['colours'] = max(maximum['colours'], float(dc.max(initial=0)))
        for j in np.flatnonzero(badv | badc)[:max(0, 12-len(examples))]:
            a, b = int(ids[j]), int(other[j])
            examples.append(dict(vertex=a, representative=b, tiles=[int(tile[a]), int(tile[b])],
                edge_code=int(code[a]), xyz=vertex[[a,b]].tolist(), rgb=color[[a,b]].tolist()))
    record = dict(at=now(), status='EXACT_SEAM_CHECK_FAILED' if any(counts.values()) else 'PASS',
        site=site, prior=prior, vertices=n, mismatched_copies=counts, max_abs_difference=maximum,
        examples=examples, read_only=True, tolerance_changed=False, geometry_changed=False,
        source=str(cache), script_sha256=sha(__file__), scientific_verdict=None)
    dump(D / 'verification' / f'addendum2_recovery_seams_{stem}.json', record)
    print(record, flush=True)


if __name__ == '__main__':
    main(*sys.argv[1:])
