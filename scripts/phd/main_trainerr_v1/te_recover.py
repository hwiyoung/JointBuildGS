"""Generalised GTJUDGE recovery_seams.py + recovery_merge.py for a TRAINERR family (TRAINLOG tl_recover.py with the stem as argument) (same rule, any number of same-tile collisions).
Distinct Open3D vertices inside ONE tile that received the same reconstructed edge code are sent to the inherited
exact-coordinate fallback (vcode=-1 in a read-time view). Vertices, colours, faces, TSDF settings, tolerances unchanged.
Run inside the tl_mesh container (shadow /gtjudge)."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_gtjudge_v1')
import numpy as np
from inherited import O, D, Path, json, dump, sha, now, module
import recovery_merge as RM

def diagnose(stem):
    cache = O/'meshes'/stem/'final_work/bounded_merge'; n = (cache/'vcode.bin').stat().st_size//8
    V = np.memmap(cache/'vertices.bin', dtype='f8', mode='r', shape=(n, 3)); C = np.memmap(cache/'colors.bin', dtype='f8', mode='r', shape=(n, 3))
    code = np.memmap(cache/'vcode.bin', dtype='i8', mode='r', shape=(n,)); rep = np.memmap(cache/'representative.bin', dtype='i8', mode='r', shape=(n,)); tile = np.memmap(cache/'tile.bin', dtype='i4', mode='r', shape=(n,))
    bad_codes = set(); counts = dict(coordinates=0, colours=0, within_same_tile=0, across_tiles=0)
    for s in range(0, n, 100000):
        ids = np.arange(s, min(n, s+100000)); ids = ids[code[ids] >= 0]; o = rep[ids]
        bv = (V[ids] != V[o]).any(1); bc = (C[ids] != C[o]).any(1); b = bv | bc; same = tile[ids] == tile[o]
        counts['coordinates'] += int(bv.sum()); counts['colours'] += int(bc.sum()); counts['within_same_tile'] += int((b & same).sum()); counts['across_tiles'] += int((b & ~same).sum())
        bad_codes |= set(code[ids[b]].tolist())
    return n, counts, sorted(bad_codes)

def main(stem_base, family):
    stem = f'{stem_base}__{family}'; wd = O/'meshes'/stem/'final_work'
    if (wd/'merged.json').exists(): print('ALREADY_MERGED'); return
    n, counts, codes = diagnose(stem); rec = dict(at=now(), stem=stem, vertices=n, mismatched_copies=counts, edge_codes=len(codes))
    assert counts['across_tiles'] == 0, 'collision across tiles: not the inherited same-tile case'
    cache = wd/'bounded_merge'; vc = np.memmap(cache/'vcode.bin', dtype='i8', mode='r', shape=(n,)); tv = np.memmap(cache/'tile.bin', dtype='i4', mode='r', shape=(n,)); V = np.memmap(cache/'vertices.bin', dtype='f8', mode='r', shape=(n, 3))
    ids = np.flatnonzero(np.isin(vc, codes)); tiles = np.unique(tv[ids]); layout = json.loads((wd/'plan/layout.json').read_text())
    offsets = {}; off = 0
    for t in layout['tiles']: offsets[t['k']] = off; off += json.loads((wd/'tiles'/f"tile{t['k']}.json").read_text())['kept']['vertices']
    changes = {}; per_tile = []
    for k in tiles.tolist():
        g = ids[tv[ids] == k]
        for c in np.unique(vc[g]): assert len(np.unique(tv[ids[vc[ids] == c]])) == 1
        for s in range(0, n, 200000):
            blk = V[s:s+200000]; other = tv[s:s+200000] != k
            for i in g: assert not (other & (blk == V[i]).all(1)).any(), 'cross-tile exact coordinate match'
        src = wd/'tiles'/f'tile{k}.npz'; local = g-offsets[k]
        with np.load(src) as z: assert (z['V'][local] == V[g]).all() and np.isin(z['vcode'][local], codes).all()
        changes[str(src)] = local; per_tile.append(dict(tile=int(k), vertices=int(len(g)), source_sha256=sha(src)))
    rec.update(tiles=per_tile, rule='GTJUDGE recovery_merge.py identity repair generalised', source_npz_modified=False, vertex_coordinates_modified=False, faces_modified=False, tolerance_changed=False)
    del vc, tv, V
    merger = module('bounded_merge'); merger.np = RM.NumpyView(changes); result = merger.merge(wd, wd/'merged.ply', wd/'merged.json')
    vi = result['tiled']['vertices']; assert vi['copies_with_other_coordinates'] == vi['copies_with_other_colours'] == 0
    for t in per_tile: assert sha(wd/'tiles'/f"tile{t['tile']}.npz") == t['source_sha256']
    result['identity_repair'] = rec; dump(wd/'merged.json', result); rec.update(status='PASS', merged_mesh_sha256=result['mesh_sha256'])
    dump(Path('/te/verification')/f'recovery_merge_{stem}.json', dict(rec, scientific_verdict=None)); print('PASS_IDENTITY_REPAIR', stem, counts, len(ids), flush=True)

if __name__ == '__main__': main(*sys.argv[1:])
