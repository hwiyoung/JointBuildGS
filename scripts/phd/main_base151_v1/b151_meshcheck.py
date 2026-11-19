"""PHD-MAIN-BASE151-v1 4.2 mesh checks (GTJUDGE environment, CPU; /gtjudge = OUT/gt; writes /gtjudge/meshcheck/).

  python b151_meshcheck.py elat              # e_lat of streamed_tsdf (0.5 z sqrt(fx^-2 + fy^-2), the box + 1.1 m) for every unit, from its views
  python b151_meshcheck.py dup <key>         # one-tile work folder: Open3D vertices that share a global edge code, by kind
Why: streamed_tsdf.plan stops when e_lat >= 0.5 m and bounded_merge stops when two vertices with one edge code differ; both are checks of
the equivalence of tiles with the one-piece volume. scientific_verdict: null
"""
import json
import sys

import numpy as np

sys.path.insert(0, '/repo/scripts/phd/main_gtjudge_v1')
from inherited import O, dump, now  # noqa: E402


def elat():
    lay = json.loads((O / 'units/layout.json').read_text())['units']
    rows = []
    for u in lay:
        B = np.asarray(u['box'], float)
        corners = np.array([[x, y, z] for x in (B[0, 0] - 1.1, B[1, 0] + 1.1) for y in (B[0, 1] - 1.1, B[1, 1] + 1.1) for z in (B[0, 2] - 1.1, B[1, 2] + 1.1)])
        worst, at = 0.0, None
        for v in json.loads((O / 'views' / f'{u["unit"]}.json').read_text())['views']:
            K, E = np.asarray(v['K'], float), np.asarray(v['W2C'], float)
            e = 0.5 * float((corners @ E[2, :3] + E[2, 3]).max()) * float(np.sqrt(K[0, 0] ** -2 + K[1, 1] ** -2))
            if e > worst:
                worst, at = e, v['name']
        rows.append(dict(unit=u['unit'], views=u['views'], e_lat_m=round(worst, 4), worst_view=at, over_0_5=bool(worst >= 0.5)))
    dump(O / 'meshcheck/elat.json', dict(at=now(), rows=rows, rule='streamed_tsdf.e_lat from the views json (W2C row 3, K)', scientific_verdict=None))
    for r in rows:
        print(r['unit'], r['views'], r['e_lat_m'], r['worst_view'], 'OVER' if r['over_0_5'] else '')


def dup(key):
    wd = O / 'meshes' / key / 'final_work'
    lay = json.loads((wd / 'plan/layout.json').read_text())
    assert len(lay['tiles']) == 1, 'one-tile folders only'
    with np.load(wd / 'tiles/tile0.npz') as z:
        V, C, vc, F = z['V'], z['C'], z['vcode'], z['F']
    known = np.flatnonzero(vc >= 0)
    order = known[np.argsort(vc[known], kind='stable')]
    s = vc[order]
    same = np.flatnonzero(s[1:] == s[:-1])
    a, b = order[same], order[same + 1]
    dxyz = np.linalg.norm(V[a] - V[b], axis=1)
    dcol = np.abs(C[a] - C[b]).max(1)
    used = np.zeros(len(V), np.int64)
    np.add.at(used, F.ravel(), 1)
    out = dict(at=now(), key=key, vertices=int(len(V)), triangles=int(len(F)), with_edge=int(len(known)), pairs_one_code=int(len(same)),
               pairs_other_coordinates=int((dxyz > 0).sum()), pairs_other_colours=int((dcol > 0).sum()),
               distance_m=dict(max=float(dxyz.max()) if len(dxyz) else None, median=float(np.median(dxyz)) if len(dxyz) else None),
               triangles_using_them=int(used[np.unique(np.r_[a, b])].sum()), scientific_verdict=None)
    dump(O / 'meshcheck' / f'dup_{key}.json', out)
    print(json.dumps(out))


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'elat':
        elat()
    elif a[0] == 'dup':
        dup(a[1])
