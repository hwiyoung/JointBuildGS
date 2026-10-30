"""One-time inherited evidence-space cleanup and exact candidate cell columns.

Original checkpoints are read-only. GT is not read by the cleanup or candidate
geometry path; only the separately stored right-side flag initializes opacity.
"""
import gc
import json
import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import torch
from plyfile import PlyData, PlyElement
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation
from input_audit import PH, S0, S3, sha, bind
from prepare_places import save, SITES, TAU
from rules import in_candidate_column
sys.path.insert(0, '/repo/scripts/phd/main_farpull_v1')
from prune_support import Support

OUT = Path('/out')


def prepare_support(site, prior, dest):
    existing = PH / 'main_farpull_v1/PHD-MAIN-FARPULL-v1/evidence_prune_v1' / site
    if prior == 'ALS':
        return existing
    folder = dest / 'support'; folder.mkdir()
    # The train cameras, training depths and confidence maps are shared by the
    # two priors in this regional source. Reuse the exact all-pixel MVS cloud.
    meta = json.loads((existing / 'support.json').read_text())
    initial = S0 / 'fork_inputs/s61' / site
    mesh_path = PH / 'main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1/s02_box' / site / 'lod2_mesh.npz'
    fork_path = initial / 'fork_inputs.json'
    shift = np.asarray(json.loads(fork_path.read_text())['LoD2']['shift'])
    with np.load(mesh_path) as z:
        vertices = (z['V'] + shift).astype(np.float32); faces = z['F'].astype(np.uint32)
    np.savez_compressed(folder / 'prior.npz', vertices=vertices, faces=faces)
    values = PH / 'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/direct_stage1_v2' / (site + '__LoD2') / 'values.npz'
    with np.load(values) as z:
        centre = z['centre']; sm = z['sigma_mvs'].astype(float)
    valid = np.isfinite(sm) & (sm > 0); median = float(np.median(sm[valid])); sm[~valid] = median
    np.savez_compressed(folder / 'patch_sigma.npz', centre=centre,
                        sigma_prior=np.full(len(centre), .2), sigma_mvs=sm)
    (folder / 'mvs_points.npy').symlink_to(existing / 'mvs_points.npy')
    meta.update(prior='LoD2', tau_m=.2, prior_triangles=len(faces),
                sigma_assignment='LoD2 sigma=0.2 m from inherited FARPULL config; MVS nearest same-prior patch; missing finite unit median.',
                new_inputs=[bind(mesh_path), bind(fork_path), bind(values)],
                mvs_reuse=bind(existing / 'support.json'), GT_used=False)
    meta['payload_sha256'] = {name: sha(folder / name) for name in
                             ['prior.npz', 'patch_sigma.npz', 'mvs_points.npy']}
    save(folder / 'support.json', meta)
    return folder


def main(unit):
    short, prior = unit.split('_'); site = SITES[short]
    dest = OUT / 'scenes' / unit
    assert not dest.exists(), 'preserve scene attempt'
    dest.mkdir(parents=True)
    cfg_path = Path('/config/places_v1.json'); cfg = json.loads(cfg_path.read_text())
    assert sha(cfg_path) == json.loads(Path('/config/places_v1.lock.json').read_text())['sha256']
    p = OUT / 'places' / (unit + '.npz')
    assert sha(p) == cfg['units'][unit]['payload']['sha256']
    with np.load(p) as z:
        # Explicit allowlist: no GT height, GT geometry, or GT patch values.
        places = {k: z[k] for k in ['point_id', 'centre', 'normal', 'tangent1', 'tangent2', 'mvs_p']}
        right = z['right']  # user-authorized initial-opacity assignment only
    model = S3 / 'runs' / site / f'nojudge_{prior}_s0/model'
    path = model / 'point_cloud/iteration_30000/point_cloud.ply'
    original = PlyData.read(path, mmap='r')['vertex'].data
    xyz = np.column_stack([original[k] for k in ['x', 'y', 'z']])
    checkpoint = model / 'jbgs_complete/iteration_30000/checkpoint.pth'
    state = torch.load(checkpoint, map_location='cpu', weights_only=False)
    assert state['iteration'] == 30000
    assert np.array_equal(xyz, state['model'][1].detach().numpy())
    protected = state['frozen_mask'].detach().numpy().astype(bool)
    assert len(protected) == len(xyz)
    del state; gc.collect()
    support_path = prepare_support(site, prior, dest)
    support = Support(support_path)
    inside, in_prior, in_mvs = support.query(xyz)
    delete1 = inside & ~protected & ~in_prior & ~in_mvs
    del support; gc.collect()
    print(unit, 'cleanup1', int(delete1.sum()), '/', len(xyz), flush=True)
    delete2 = np.zeros(len(xyz), bool)
    tree = cKDTree(xyz)
    for i in range(len(places['point_id'])):
        m = float(places['mvs_p'][i]); low = min(0., m) - TAU[prior]; high = max(0., m) + 3.
        centre, normal = places['centre'][i], places['normal'][i]
        middle = centre + normal * ((low + high) / 2)
        radius = np.sqrt(((high - low) / 2)**2 + .25**2 * 2) + 1e-6
        indices = np.asarray(tree.query_ball_point(middle, radius), dtype=int)
        hit = in_candidate_column(xyz[indices], centre, places['tangent1'][i],
                                  places['tangent2'][i], normal, m, TAU[prior])
        delete2[indices[hit]] = True
    keep = ~(delete1 | delete2)
    kept_path = dest / 'background.ply'
    PlyData([PlyElement.describe(original[keep].copy(), 'vertex')], text=False).write(kept_path)
    np.savez_compressed(dest / 'cleanup_masks.npz', delete_evidence=delete1,
                        delete_column=delete2, original_protected=protected, keep=keep)
    offsets = np.array([[-.125, -.125], [-.125, .125], [.125, -.125], [.125, .125]])
    local = (places['centre'][:, None] + places['tangent1'][:, None] * offsets[None, :, :1] +
             places['tangent2'][:, None] * offsets[None, :, 1:])
    # P x 2 candidates x 4 Gaussians x 3; prior first, image second.
    means = np.stack([local, local + places['normal'][:, None] * places['mvs_p'][:, None, None]], 1)
    basis = np.stack([places['tangent1'], places['tangent2'], places['normal']], axis=-1)
    assert np.allclose(basis.swapaxes(-1, -2) @ basis, np.eye(3), atol=1e-6)
    q = Rotation.from_matrix(basis).as_quat()[:, [3, 0, 1, 2]]
    quats = np.repeat(q[:, None], 8, axis=1).reshape(-1, 4)
    arrays = dict(means=means.reshape(-1, 3).astype(np.float32), quats=quats.astype(np.float32),
                  scales=np.full((len(quats), 3), [.125, .125, 1e-8], np.float32),
                  point_index=np.repeat(np.arange(len(means)), 8),
                  candidate=np.tile(np.repeat([0, 1], 4), len(means)))
    np.savez_compressed(dest / 'candidate_geometry.npz', **arrays)
    np.savez_compressed(dest / 'initial_right_candidate.npz', right_candidate=(right == 'image').astype(np.int8))
    report = dict(unit=unit, at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        original=bind(path), places_sha256=sha(cfg_path), support=bind(support_path / 'support.json'),
        protected_mask_source=bind(checkpoint), original_count=len(xyz),
        deleted_evidence=int(delete1.sum()), deleted_columns_after_evidence=int((delete2 & ~delete1).sum()),
        deleted_column_union=int(delete2.sum()), remaining=int(keep.sum()),
        candidates=len(quats), background=bind(kept_path), geometry=bind(dest / 'candidate_geometry.npz'),
        candidate_inplane_sigma_m=.125, sigma_rule='Half 25cm lattice spacing; identical on both heights. Gaussian tails are retained.',
        GT_used_in_cleanup_or_geometry=False, optimizer_steps=0, scientific_verdict=None)
    save(dest / 'scene.json', report)
    save(Path('/docs') / 'scenes' / (unit + '.json'), report)
    print(unit, 'cleanup2', report['deleted_columns_after_evidence'], 'remaining', report['remaining'], flush=True)


if __name__ == '__main__':
    for unit in sys.argv[1:]:
        main(unit)
