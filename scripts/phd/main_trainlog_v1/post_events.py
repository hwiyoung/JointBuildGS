"""Merge raw event chunks into events/<kind>.csv.gz and classify releases with the RELEASE-v1 rule (CPU).
Release case A/B: exact tangent nearest target (RELEASE-v1 release_search.so binary, read-only), d<=0.5 m -> B(1) else A(0).
Birth category: 0 initial seed, 1 clone at this event, 2 split at this event, 3 earlier (RELEASE-v1 event_report.py codes)."""
import sys, gzip
from common import *
os.environ.setdefault('JBGS_RELEASE_SEARCH', str(PH/'main_release_v1/PHD-MAIN-RELEASE-v1/bin/release_search.so'))
sys.path.append(str(R/'src/phd/forks/GeoGS-conf-guided-v1-r24'))
import pandas as pd

def load(root, kind):
    parts = [loadz(f) for f in sorted((root/'events').glob(f'{kind}_*.npz'))]
    if not parts: return {}
    return {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}

def flat(d):
    out = {}
    for k, v in d.items():
        if v.ndim == 2:
            for j in range(v.shape[1]): out[f'{k}_{"xyz"[j] if v.shape[1] == 3 else j}'] = v[:, j]
        else: out[k] = v
    return out

def main(root=None):
    from release_search import TangentTree
    root = Path(root) if root else O/'runs'/SITE/RUN/'attempt1/model/trainlog'; out = root.parent.parent.parent/'derived'/'events'; out.mkdir(parents=True, exist_ok=True)
    t = loadz(FT/'targets'/f'{STEM}.npz'); valid = np.flatnonzero((t['region'] >= 0) & np.isfinite(t['target']).all(1) & np.isfinite(t['normal']).all(1) & np.isfinite(t['sigma']) & (t['sigma'] > 0))
    anchor = t['target'][valid].astype(float); norm = t['normal'][valid].astype(float); norm /= np.linalg.norm(norm, axis=1)[:, None]; width = (np.float32(1.96)*t['sigma'][valid].astype('f4')).astype(float)
    rec = {}
    for kind in ['birth', 'delete', 'release', 'retarget', 'range', 'opacity_reset']:
        a = load(root, kind)
        if not a: rec[kind] = 0; continue
        if kind == 'release':
            tree = TangentTree(anchor, norm, width, valid); d, e, j = tree.query(a['xyz']); old = a['previous_target_index']; ok = old >= 0
            a['case'] = np.where(d <= .5, 1, 0).astype('i1'); a['nearest_target_index'] = j; a['nearest_tangent_m'] = d; a['nearest_normal_excess_m'] = e
            a['previous_judgment'] = np.where(ok, t['judge_region'][valid[old.clip(0)]], -1).astype('i1'); a['nearest_judgment'] = t['judge_region'][valid[j]].astype('i1')
            diff = np.full(len(d), np.nan); diff[ok] = ((anchor[j[ok]]-anchor[old[ok]])*norm[old[ok]]).sum(1); a['target_normal_height_difference_m'] = diff
            pn = a['parent_disk_normal'].astype(float); a['parent_normal_angle_degrees'] = np.rad2deg(np.arccos(np.clip(abs((pn*norm[j]).sum(1)), 0, 1)))
            a['birth_category'] = np.where(a['birth_iteration'] == 0, 0, np.where(a['birth_iteration'] == a['iteration'], np.where(a['born_how'] == 3, 2, 1), 3)).astype('i1')
        if kind == 'retarget':
            a['old_judgment'] = t['judge_region'][valid[a['old']]].astype('i1'); a['new_judgment'] = t['judge_region'][valid[a['new']]].astype('i1')
            a['target_height_difference_m'] = (anchor[a['new'], 2]-anchor[a['old'], 2]).astype('f4')
            a['target_normal_height_difference_m'] = ((anchor[a['new']]-anchor[a['old']])*norm[a['old']]).sum(1).astype('f4')
        savez(out/f'{kind}.npz', **a)
        df = pd.DataFrame(flat(a)); df.to_csv(out/f'{kind}.csv.gz', index=False, compression='gzip')
        rec[kind] = dict(rows=len(df), npz_sha256=sha(out/f'{kind}.npz'), csv_sha256=sha(out/f'{kind}.csv.gz'), columns=list(df.columns))
        print('EVENTS', kind, len(df), flush=True)
    dump(out/'events_receipt.json', dict(at=now(), source=str(root/'events'), kinds=rec, release_search=os.environ['JBGS_RELEASE_SEARCH'], release_search_sha256=sha(os.environ['JBGS_RELEASE_SEARCH']),
        codes=dict(delete_reason={1: 'opacity', 2: 'world_size', 3: 'screen_size', 4: 'other', 5: 'split_parent'}, born_how={0: 'patch seed', 1: 'initial background', 2: 'clone', 3: 'split'},
                   release_case={0: 'A (no target within 0.5 m tangent)', 1: 'B'}, cause={0: 'density control', 1: '100-step check'}, birth_category={0: 'initial', 1: 'clone now', 2: 'split now', 3: 'earlier'}),
        scientific_verdict=None))
if __name__ == '__main__': main(*sys.argv[1:])
