"""Addendum 2 input check (read-only): validate the seed/child order rule (original seeds = prefix of rows with strictly increasing init_id) against the record runs' true lineage (born_at == 0)."""
import sys; sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1')
from common import *
for run in ['B0_b10/tl_B0_LoD2_own', 'B0_b10/tl_B0_LoD2_gt', 'R1rep_b10/tl_R1_ALS_own', 'R1rep_b10/tl_R1_ALS_gt']:
    s = loadz(O/'runs'/run/'attempt1/model/trainlog/states/30000.npz'); o = np.argsort(s['full_gaussian_index']); fi = s['full_gaussian_index'][o]; ii = s['init_id'][o]; seed_true = s['born_at'][o] == 0
    # full-scene prefix length from the full model ply init_id is not stored; use the subset: within the prefix, full index order and init order agree
    first_child_full = int(fi[~seed_true].min()) if (~seed_true).any() else None; last_seed_full = int(fi[seed_true].max()) if seed_true.any() else None
    print(run, 'rows', len(fi), 'true seeds', int(seed_true.sum()), 'last seed full index', last_seed_full, 'first child full index', first_child_full, 'seeds all before children', last_seed_full < first_child_full if None not in (last_seed_full, first_child_full) else None,
          'born_how values', np.unique(s['born_how'], return_counts=True))
