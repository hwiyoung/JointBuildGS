"""Keep distinct Open3D vertices when reconstructed edge identity is ambiguous.

Only the two diagnosed same-tile collisions enter the inherited exact-coordinate
fallback. Vertices, colors, faces, TSDF settings and seam tolerances stay unchanged.
"""
import sys
import numpy as np
from inherited import O, D, Path, json, dump, sha, now, module


class TileView:
    def __init__(self, source, indices):
        self.source, self.indices = source, indices

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.source.close()

    def __contains__(self, key):
        return key in self.source

    def __getitem__(self, key):
        value = self.source[key]
        if key == 'vcode':
            value[self.indices] = -1
        return value


class NumpyView:
    def __init__(self, changes):
        self.changes = changes

    def __getattr__(self, name):
        return getattr(np, name)

    def load(self, path, *args, **kwargs):
        source = np.load(path, *args, **kwargs)
        indices = self.changes.get(str(Path(path)))
        return TileView(source, indices) if indices is not None else source


def main(site, prior):
    stem = f'{site}__{prior}__fix'
    wd = O/'meshes'/stem/'final_work'
    if (wd/'merged.json').exists():
        return
    evidence = D/'verification'/f'addendum2_recovery_seams_{stem}.json'
    diagnosis = json.loads(evidence.read_text())
    assert diagnosis['status'] == 'EXACT_SEAM_CHECK_FAILED'
    mismatch = diagnosis['mismatched_copies']
    assert mismatch['coordinates'] == mismatch['within_same_tile'] == 1
    cache = wd/'bounded_merge'
    n = diagnosis['vertices']
    vc = np.memmap(cache/'vcode.bin', dtype='i8', mode='r', shape=(n,))
    tv = np.memmap(cache/'tile.bin', dtype='i4', mode='r', shape=(n,))
    vertices = np.memmap(cache/'vertices.bin', dtype='f8', mode='r', shape=(n, 3))
    codes = {x['edge_code'] for x in diagnosis['examples']}
    assert len(codes) == 1
    receipt = D/'verification'/f'addendum2_recovery_merge_{stem}.json'
    previous = json.loads(receipt.read_text()) if receipt.exists() else None
    ids = np.array(previous['global_vertex_ids']) if previous else np.flatnonzero(np.isin(vc, list(codes)))
    assert len(ids) == 2 and len(np.unique(tv[ids])) == 1
    k = int(tv[ids[0]])
    # These are not shared vertices at a tile seam. The inherited fallback must
    # preserve both source vertices, with no cross-tile exact-coordinate match.
    for start in range(0, n, 100000):
        block = vertices[start:start+100000]
        other = tv[start:start+100000] != k
        for idx in ids:
            assert not (other & (block == vertices[idx]).all(1)).any()
    layout = json.loads((wd/'plan/layout.json').read_text())
    offset = 0
    for tile in layout['tiles']:
        if tile['k'] == k:
            break
        offset += json.loads((wd/'tiles'/f"tile{tile['k']}.json").read_text())['kept']['vertices']
    local_ids = ids-offset
    source = wd/'tiles'/f'tile{k}.npz'
    source_sha = sha(source)
    with np.load(source) as original:
        assert (original['V'][local_ids] == vertices[ids]).all()
        assert np.isin(original['vcode'][local_ids], list(codes)).all()
    record = dict(at=now(), site=site, prior=prior, status='IDENTITY_REPAIR_PREPARED',
        source=str(source), source_sha256=source_sha, tile=k, local_vertex_ids=local_ids.tolist(),
        global_vertex_ids=ids.tolist(),
        original_global_edge_codes=sorted(codes), new_identity='unsettled; inherited exact-coordinate fallback',
        across_tile_coordinate_matches=0, source_npz_modified=False,
        vertex_coordinates_modified=False, vertex_colours_modified=False, faces_modified=False,
        tolerance_changed=False, diagnosis_sha256=sha(evidence), scientific_verdict=None)
    if previous:
        assert previous['source_sha256'] == source_sha
    dump(receipt, record)
    del vc, tv, vertices
    merger = module('bounded_merge')
    merger.np = NumpyView({str(source): local_ids})
    result = merger.merge(wd, wd/'merged.ply', wd/'merged.json')
    assert sha(source) == source_sha
    vinfo = result['tiled']['vertices']
    assert vinfo['copies_with_other_coordinates'] == vinfo['copies_with_other_colours'] == 0
    representatives = np.memmap(cache/'representative.bin', dtype='i8', mode='r', shape=(n,))
    assert (representatives[ids] == ids).all()
    result['identity_repair'] = record
    dump(wd/'merged.json', result)
    record.update(status='PASS', merged_mesh_sha256=result['mesh_sha256'],
                  exact_seam_check='PASS', distinct_source_vertices_preserved=True,
                  script_sha256=sha(__file__))
    dump(receipt, record)
    print('PASS_IDENTITY_REPAIR_EXACT_SEAMS', stem, flush=True)


if __name__ == '__main__':
    main(*sys.argv[1:])
