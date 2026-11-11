"""RESCORE bounded_merge.merge unchanged except the copy-consistency check: coordinates of edge-vertex copies must agree
within 1e-12 m instead of bit-exactly. Exact mismatches and their largest size are recorded in merged.json.
Used only where the unchanged merge stopped on a floating-point roundoff (issues.md).

  python tu_merge_tol.py <site> <prior> <family>        (inside a GTJUDGE container: /gtjudge, /repo/scripts/phd from exp)
"""
import sys
import types

sys.path.insert(0, '/repo/scripts/phd/main_gtjudge_v1')
from inherited import *  # noqa: F401,F403  (binds common to /gtjudge)
import inherited

OLD = "vinfo['copies_with_other_coordinates']+=int((V[ri]!=V[ix]).any(1).sum())"
NEW = ("d_=np.abs(V[ri]-V[ix]);vinfo['copies_with_other_coordinates']+=int((d_>1e-12).any(1).sum());"
       "vinfo['copies_exact_coordinate_mismatch']=vinfo.get('copies_exact_coordinate_mismatch',0)+int((d_>0).any(1).sum());"
       "vinfo['max_coordinate_mismatch_m']=max(vinfo.get('max_coordinate_mismatch_m',0.),float(d_.max()) if len(ix) else 0.);"
       "vinfo['coordinate_tolerance_m']=1e-12")


def main(site, prior, family):
    path = inherited.R / 'scripts/phd/main_rescore_v1/bounded_merge.py'
    src = path.read_text()
    assert src.count(OLD) == 1
    mod = types.ModuleType('inherited_bounded_merge_tol')
    mod.__file__ = str(path)
    exec(compile(src.replace(OLD, NEW), str(path) + ' [tolerance 1e-12 m]', 'exec'), mod.__dict__)
    wd = inherited.O / 'meshes' / f'{site}__{prior}__{family}' / 'final_work'
    mod.merge(wd, wd / 'merged.ply', wd / 'merged.json')
    rec = json.loads((wd / 'merged.json').read_text())
    rec.update(merge_variant='TRAINUNIT tolerance merge (1e-12 m copy coordinate check)', source_sha256=sha(path))
    dump(wd / 'merged.json', rec)
    print('MERGED_TOL', site, prior, family, flush=True)


if __name__ == '__main__':
    main(*sys.argv[1:])
