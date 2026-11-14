"""r27: opt-in training-process log for PHD-MAIN-TRAINLOG-v1 (`--jbgs_trainlog on`).

Decisions inherit r23 FinalTrain unchanged. Every method here only reads model
tensors or writes the extra `tl_*` bookkeeping arrays: no model/optimizer tensor
is written, no random number is drawn, and r23 control flow is preserved. With
`--jbgs_trainlog off` this module is not imported.

Release-event fields copy r24 jbgs_release.Release.record (PHD-MAIN-RELEASE-v1).
Range = locked PROCFIG-v1 building scope: buffered footprint XY x [z_min, z_max].
Every event row carries a global sequence number `seq`; each saved state records
the sequence at saving, so (after) = (before) + born - deleted + in - out holds
over (seq_before, seq_after] exactly.
"""
import json, os, time
from pathlib import Path
import numpy as np
import torch
from jbgs_finaltrain import FinalTrain
from jbgs_target import write
from utils.general_utils import build_rotation

TL = ('tl_uid', 'tl_parent', 'tl_born', 'tl_how', 'tl_inside', 'tl_last_xyz', 'tl_parent_scale', 'tl_parent_normal', 'tl_event')
TEMP = ('tl_parent_xyz', 'tl_parent_scale2')
# born_how: 0 patch seed, 1 initial background, 2 clone, 3 split
# delete reason: 1 opacity threshold, 2 world size, 3 screen size, 4 other cull, 5 split parent replaced
REASON = {1: 'opacity', 2: 'world_size', 3: 'screen_size', 4: 'other', 5: 'split_parent'}


def rings(geometry):
    polys = geometry['coordinates'] if geometry['type'] == 'MultiPolygon' else [geometry['coordinates']]
    out = []
    for poly in polys:
        for ring in poly:
            r = np.asarray(ring, np.float64)[:, :2]
            out.append(np.c_[r[:-1], r[1:]])
    return np.concatenate(out)


class TrainLog(FinalTrain):
    def __init__(self, args, scene, g):
        self.trainlog_on = False
        self.tl_region_file = getattr(args, 'jbgs_trainlog_region', None)  # r28 PHD-MAIN-TRAINERR-v1: voxelised box range
        self.trainlog_grads_on = getattr(args, 'jbgs_trainlog_grads', 'off') == 'on'  # r28: per-loss gradient magnitudes
        import jbgs_a4; self.a4_signed = jbgs_a4.grad_signed(args)  # [jbgs r31] default off
        super().__init__(args, scene, g)
        self.init_log(Path(args.model_path), g)

    def init_log(self, model_path, g):
        cfg = json.loads(Path(os.environ['JBGS_TRAINLOG_CONFIG']).read_text())
        self.cfg = cfg['training_log']
        dev = g._xyz.device
        self.voxel = None
        if self.tl_region_file:  # r28: union of boxes snapped outward to the region voxel grid
            reg = json.loads(Path(self.tl_region_file).read_text()); v = float(reg['voxel_m'])
            lo = np.asarray(reg['grid_origin'], np.float64); shape = tuple(int(x) for x in reg['grid_shape']); occ = np.zeros(shape, bool)
            for b in reg['boxes']:
                b = np.asarray(b[:6], np.float64)
                i0 = np.floor((b[[0, 2, 4]] - lo) / v + 1e-9).astype(int); i1 = np.ceil((b[[1, 3, 5]] - lo) / v - 1e-9).astype(int)
                occ[i0[0]:i1[0], i0[1]:i1[1], i0[2]:i1[2]] = True
            assert int(occ.sum()) == int(reg['occupied_voxels']), 'TRAINERR region voxel count mismatch'
            self.voxel = (torch.tensor(occ, device=dev), torch.tensor(lo, device=dev, dtype=torch.float64), v)
            e = np.zeros((1, 4)); hi = lo + np.asarray(shape) * v
            self.box = (float(lo[0]), float(hi[0]), float(lo[1]), float(hi[1])); self.zr = (float(lo[2]), float(hi[2]))
            self.edges = None
        else:
            sc = cfg['scope']
            e = rings(sc['buffered_footprint'])
            self.edges = torch.tensor(e, device=dev, dtype=torch.float64)
            self.box = (float(e[:, [0, 2]].min()), float(e[:, [0, 2]].max()), float(e[:, [1, 3]].min()), float(e[:, [1, 3]].max()))
            self.zr = (float(sc['z_min']), float(sc['z_max']))
        self.up = torch.tensor(cfg['coordinates']['up'], device=dev, dtype=torch.float32)
        self.save_set = set(int(i) for i in self.cfg['save_iterations'])
        sd = self.cfg['scene_dump']  # r28: bool (r27) or list of state names
        self.scene_dump = sd if isinstance(sd, bool) else set(str(x) for x in sd)
        self.flush_every = int(self.cfg['flush_every'])
        self.out = Path(model_path) / 'trainlog'
        for d in ['states', 'scene', 'events', 'debug'] + (['grads'] if self.trainlog_grads_on else []):
            (self.out / d).mkdir(parents=True, exist_ok=False)
        n = len(g._xyz)
        g.tl_uid = torch.arange(n, device=dev, dtype=torch.int64)
        g.tl_parent = torch.full((n,), -1, device=dev, dtype=torch.int64)
        g.tl_born = torch.zeros(n, device=dev, dtype=torch.int32)
        g.tl_how = torch.where(g.origin == 1, 0, 1).to(torch.int8)
        g.tl_inside = self.inside(g._xyz)
        g.tl_last_xyz = g._xyz.detach().clone()
        g.tl_parent_scale = torch.full((n,), float('nan'), device=dev)
        g.tl_parent_normal = torch.full((n, 3), float('nan'), device=dev)
        g.tl_event = torch.full((n,), -1, device=dev, dtype=torch.int64)  # last release event id, inherited by children (r24 rl_event)
        self.next_uid = n; self.seq = 0; self.next_event = 0; self.chunk = 0
        self.buf = {}; self.ctx = None; self.g = g
        self.t_last = None; self.it_last = None; self.saves = []
        self.self_check = os.environ.get('JBGS_TRAINLOG_SELFCHECK') == '1'
        self._wrap(g)
        self.trainlog_on = True
        write(self.out / 'start.json', dict(gaussians=n, inside=int(g.tl_inside.sum()), edges=len(e), box=self.box, z=self.zr,
            save_iterations=sorted(self.save_set), scene_dump=self.scene_dump if isinstance(self.scene_dump, bool) else sorted(self.scene_dump),
            region_file=self.tl_region_file, gradients=self.trainlog_grads_on, scientific_verdict=None))

    # ---------- geometry ----------
    @torch.no_grad()
    def inside(self, xyz):
        x = xyz.detach().double(); n = len(x)
        out = torch.zeros(n, device=x.device, dtype=torch.bool)
        b = self.box
        c = (x[:, 0] >= b[0]) & (x[:, 0] <= b[1]) & (x[:, 1] >= b[2]) & (x[:, 1] <= b[3]) & (x[:, 2] >= self.zr[0]) & (x[:, 2] <= self.zr[1])
        idx = torch.nonzero(c).squeeze(1)
        if not len(idx): return out
        if self.voxel is not None:  # r28 voxel lookup
            occ, lo, v = self.voxel; k = torch.floor((x[idx] - lo) / v).long()
            for a in range(3): k[:, a] = k[:, a].clamp(0, occ.shape[a] - 1)
            out[idx] = occ[k[:, 0], k[:, 1], k[:, 2]]
            return out
        e = self.edges; x1, y1, x2, y2 = e[:, 0], e[:, 1], e[:, 2], e[:, 3]
        for s in range(0, len(idx), 16384):
            j = idx[s:s + 16384]; px = x[j, 0:1]; py = x[j, 1:2]
            cond = (y1 > py) != (y2 > py)
            xi = x1 + (py - y1) * (x2 - x1) / (y2 - y1)
            cross = cond & (px < xi)
            out[j] = (cross.sum(1) % 2) == 1
        return out

    # ---------- event buffers ----------
    def push(self, kind, **cols):
        n = len(next(iter(cols.values())))
        if not n: return
        cols['seq'] = np.arange(self.seq + 1, self.seq + n + 1, dtype=np.int64); self.seq += n
        cols['iteration'] = np.full(n, self.iteration, np.int32)
        self.buf.setdefault(kind, []).append({k: (v.detach().cpu().numpy() if torch.is_tensor(v) else np.asarray(v)) for k, v in cols.items()})

    def flush(self):
        for kind, parts in self.buf.items():
            data = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
            np.savez_compressed(self.out / 'events' / f'{kind}_{self.chunk:05d}.npz', **data)
        self.buf = {}; self.chunk += 1

    # ---------- wrappers around density control (read-only) ----------
    def _wrap(self, g):
        dap, das, pp = g.densify_and_prune, g.densify_and_split, g.prune_points
        def densify_and_prune(max_grad, min_opacity, extent, max_screen_size):
            self.ctx = ('cull', min_opacity, extent, max_screen_size)
            try: return dap(max_grad, min_opacity, extent, max_screen_size)
            finally: self.ctx = None
        def densify_and_split(*a, **k):
            old = self.ctx; self.ctx = ('split',) + (old[1:] if old else ())
            try: return das(*a, **k)
            finally: self.ctx = old
        def prune_points(mask, opacity_mask=None):  # r28: r25 prune signature (opacity_mask only used by preserve_freespace)
            self.before_prune(g, mask)
            return pp(mask, opacity_mask=opacity_mask)
        g.densify_and_prune, g.densify_and_split, g.prune_points = densify_and_prune, densify_and_split, prune_points

    @torch.no_grad()
    def before_prune(self, g, mask):
        rows = torch.nonzero(mask).squeeze(1)
        if not len(rows): return
        n = len(rows); flags = torch.zeros(n, device=rows.device, dtype=torch.int8)
        if self.ctx is not None and self.ctx[0] == 'split':
            reason = torch.full((n,), 5, device=rows.device, dtype=torch.int8)
        else:
            reason = torch.full((n,), 4, device=rows.device, dtype=torch.int8)
            if self.ctx is not None and self.ctx[0] == 'cull':
                _, min_opacity, extent, max_screen = self.ctx
                low = g.get_opacity[rows, 0] < min_opacity
                ws = g.get_scaling[rows].max(1).values > .1 * extent if max_screen else torch.zeros_like(low)
                vs = g.max_radii2D[rows] > max_screen if max_screen else torch.zeros_like(low)
                flags = low.to(torch.int8) + 2 * ws.to(torch.int8) + 4 * vs.to(torch.int8)
                reason = torch.where(low, 1, torch.where(ws, 2, torch.where(vs, 3, 4))).to(torch.int8)
        ins = g.tl_inside[rows]
        r = rows[ins]
        if len(r):
            self.push('delete', uid=g.tl_uid[r], reason=reason[ins], flags=flags[ins], opacity=g.get_opacity[r, 0], scale=g.get_scaling[r],
                xyz=g._xyz[r], tag=g.target_tag[r], target_index=g.target_index[r], init_id=g.init_id[r], how=g.tl_how[r], born=g.tl_born[r])
        self.deleted_scene = getattr(self, 'deleted_scene', 0) + n

    # ---------- r6 metadata hooks ----------
    def child_metadata(self, g, selected, n):
        data = super().child_metadata(g, selected, n)
        if not self.trainlog_on: return data
        count = int(selected.sum()) * n; dev = g._xyz.device
        for k in TL:
            v = getattr(g, k)[selected]
            data[k] = v.repeat((n, 1)) if v.ndim == 2 else v.repeat(n)
        data['tl_parent'] = g.tl_uid[selected].repeat(n)
        data['tl_uid'] = torch.arange(self.next_uid, self.next_uid + count, device=dev, dtype=torch.int64); self.next_uid += count
        data['tl_born'] = torch.full((count,), self.iteration, device=dev, dtype=torch.int32)
        data['tl_how'] = torch.full((count,), 3 if n > 1 else 2, device=dev, dtype=torch.int8)
        data['tl_parent_scale'] = g.get_scaling[selected].max(1).values.repeat(n)
        data['tl_parent_normal'] = build_rotation(g._rotation[selected])[:, :, 2].repeat(n, 1)
        data['tl_parent_xyz'] = g.get_xyz[selected].detach().repeat(n, 1)
        data['tl_parent_scale2'] = g.get_scaling[selected].detach().repeat(n, 1)
        data['tl_parent_tag'] = g.target_tag[selected].repeat(n)
        return data

    @torch.no_grad()
    def extended(self, g, meta):
        if not self.trainlog_on: return super().extended(g, meta)
        pxyz, pscale, ptag = meta.pop('tl_parent_xyz'), meta.pop('tl_parent_scale2'), meta.pop('tl_parent_tag')
        count = len(meta['tl_uid'])
        for k in TL: setattr(g, k, torch.cat([getattr(g, k), meta[k]]))
        new = torch.arange(len(g._xyz) - count, len(g._xyz), device=g._xyz.device)
        self.push('link', uid=g.tl_uid[new], parent_uid=g.tl_parent[new], how=g.tl_how[new])  # scene-wide birth links
        ins = self.inside(g._xyz[new]); g.tl_inside[new] = ins
        r = new[ins]
        if len(r):
            self.push('birth', uid=g.tl_uid[r], parent_uid=g.tl_parent[r], how=g.tl_how[r], tag=ptag[ins], xyz=g._xyz[r],
                scale=g.get_scaling[r], parent_xyz=pxyz[ins], parent_scale=pscale[ins], init_id=g.init_id[r], origin=g.origin[r])
        super().extended(g, meta)

    @torch.no_grad()
    def pruned(self, g, keep):
        if self.trainlog_on:
            for k in TL: setattr(g, k, getattr(g, k)[keep])
        super().pruned(g, keep)

    @torch.no_grad()
    def reattach(self, g, reason):
        if not self.trainlog_on: return super().reattach(g, reason)
        rows = torch.where(g.target_tag == 1)[0]
        before = g.target_index[rows].clone()
        super().reattach(g, reason)
        if not len(rows): return
        bound = g.target_tag[rows] == 1
        lost = rows[~bound]
        if len(lost): self.record_release(g, lost, reason, before[~bound])
        ch = bound & (g.target_index[rows] != before) & g.tl_inside[rows]
        if ch.any():
            r = rows[ch]
            self.push('retarget', uid=g.tl_uid[r], old=before[ch], new=g.target_index[r], cause=np.full(len(r), 1 if reason == 'periodic' else 0, np.int8), xyz=g._xyz[r])
        g.tl_last_xyz[rows] = g._xyz[rows].detach()

    @torch.no_grad()
    def record_release(self, g, rows, reason, old):
        # Same fields as r24 jbgs_release.Release.record (action='release').
        n = len(rows); ids = torch.arange(self.next_event, self.next_event + n, device=rows.device, dtype=torch.int64); self.next_event += n
        g.tl_event[rows] = ids
        valid = old >= 0; normal = torch.zeros((n, 3), device=rows.device, dtype=torch.float64)
        normal[valid] = self.patch_normal[old[valid]].double()
        delta = g._xyz[rows].double() - g.tl_last_xyz[rows].double(); hn = (delta * normal).sum(1)
        self.push('release', event_id=ids, uid=g.tl_uid[rows], init_id=g.init_id[rows], xyz=g._xyz[rows], previous_check_xyz=g.tl_last_xyz[rows],
            previous_target_index=old, birth_iteration=g.tl_born[rows], born_how=g.tl_how[rows],
            movement_normal_m=hn, movement_tangent_m=torch.linalg.vector_norm(delta - hn[:, None] * normal, dim=1),
            longest_axis_m=g.get_scaling[rows].max(1).values, opacity=g.get_opacity[rows, 0],
            parent_longest_axis_m=g.tl_parent_scale[rows], parent_disk_normal=g.tl_parent_normal[rows],
            cause=np.full(n, 1 if reason == 'periodic' else 0, np.int8), inside=g.tl_inside[rows])

    # ---------- train.py hooks ----------
    @torch.no_grad()
    def trainlog_begin(self, g):
        self.iteration = 0; self.t_last = time.perf_counter(); self.it_last = 0
        self.save_state(g, '0')

    @torch.no_grad()
    def trainlog_pre_reset(self, iteration, g):
        self.push('opacity_reset', marker=np.zeros(1, np.int8))
        self.update_range(g)
        self.save_state(g, f'{iteration}_pre_reset')

    @torch.no_grad()
    def update_range(self, g):
        ins = self.inside(g._xyz); flip = ins ^ g.tl_inside
        if bool(flip.any()):
            r = torch.nonzero(flip).squeeze(1)
            self.push('range', uid=g.tl_uid[r], enter=ins[r], xyz=g._xyz[r], tag=g.target_tag[r])
        g.tl_inside = ins

    @torch.no_grad()
    def trainlog_end(self, iteration, g, losses, camera):
        if self.self_check: before = self.fingerprint(g)
        self.update_range(g)
        if iteration % 100 == 0:
            now = time.perf_counter(); ins = g.tl_inside
            wall = (build_rotation(g._rotation)[:, :, 2] @ self.up).abs() < .5
            counts = {f'tag{t}_{"wall" if w else "roof"}': int((ins & (g.target_tag == t) & (wall if w else ~wall)).sum()) for t in range(3) for w in [0, 1]}
            row = dict(iteration=iteration, camera=camera, **{k: float(v) for k, v in losses.items()}, gaussians=len(g._xyz), inside=int(ins.sum()), **counts,
                allocated_bytes=torch.cuda.memory_allocated(), reserved_bytes=torch.cuda.memory_reserved(), peak_allocated_bytes=torch.cuda.max_memory_allocated(),
                seconds_per_iteration=(now - self.t_last) / max(1, iteration - self.it_last), seq=self.seq, scientific_verdict=None)
            with (self.out / 'curve.jsonl').open('a') as f: f.write(json.dumps(row) + '\n')
            self.t_last = now; self.it_last = iteration
        if iteration in self.save_set: self.save_state(g, str(iteration))
        if iteration % self.flush_every == 0 or iteration in self.save_set: self.flush()
        if self.self_check:
            after = self.fingerprint(g)
            assert before == after, ('TRAINLOG_SELFCHECK_CHANGED', iteration)

    def trainlog_grads(self, iteration, g, terms):
        """r28: |dL_term/dxyz| and |dL_term/d opacity logit| of in-range Gaussians before the normal backward.
        torch.autograd.grad returns values only: no .grad, optimizer, densification statistic or RNG is touched."""
        if not self.trainlog_grads_on or iteration not in self.save_set: return
        t0 = time.perf_counter()
        with torch.no_grad(): ins = self.inside(g._xyz); r = torch.nonzero(ins).squeeze(1)
        data = dict(uid=g.tl_uid[r].detach().cpu().numpy(), iteration=np.int32(iteration))
        for name, term in terms.items():
            if torch.is_tensor(term) and term.requires_grad:
                gx, go = torch.autograd.grad(term, [g._xyz, g._opacity], retain_graph=True, allow_unused=True)
            else: gx = go = None
            with torch.no_grad():
                data[name + '_xyz'] = (torch.linalg.vector_norm(gx[r], dim=1) if gx is not None else torch.zeros(len(r), device=r.device)).float().cpu().numpy()
                data[name + '_opacity'] = (go[r, 0].abs() if go is not None else torch.zeros(len(r), device=r.device)).float().cpu().numpy()
                data[name + '_value'] = np.float64(float(term)) if torch.is_tensor(term) else np.float64(term)
                if self.a4_signed:  # [jbgs r31] signed vectors (addendum 4); the fields above are unchanged
                    data[name + '_xyzvec'] = (gx[r] if gx is not None else torch.zeros((len(r), 3), device=r.device)).float().cpu().numpy()
                    data[name + '_opacity_signed'] = (go[r, 0] if go is not None else torch.zeros(len(r), device=r.device)).float().cpu().numpy()
        np.savez_compressed(self.out / 'grads' / f'{iteration}.npz', **data)
        with (self.out / 'grads.jsonl').open('a') as f: f.write(json.dumps(dict(iteration=iteration, inside=len(r), seconds=time.perf_counter() - t0)) + '\n')

    def fingerprint(self, g):
        import random
        vals = [float(getattr(g, a).detach().double().sum()) for a in ['_xyz', '_scaling', '_opacity', '_rotation', '_features_dc']]
        vals += [int(g.target_tag.long().sum()), int(g.target_index.sum()), len(g._xyz)]
        return (tuple(vals), hash(random.getstate()), hash(torch.get_rng_state().numpy().tobytes()), hash(torch.cuda.get_rng_state().numpy().tobytes()))

    @torch.no_grad()
    def save_state(self, g, name):
        t0 = time.perf_counter(); ins = g.tl_inside; r = torch.nonzero(ins).squeeze(1)
        data = dict(xyz=g._xyz[r], rotation=g.get_rotation[r], scale=g.get_scaling[r], opacity=g.get_opacity[r, 0], origin=g.origin[r], init_id=g.init_id[r],
            target_tag=g.target_tag[r], target_index=g.target_index[r], target_released_at=g.target_released_at[r], full_gaussian_index=r,
            uid=g.tl_uid[r], parent_uid=g.tl_parent[r], born_at=g.tl_born[r], born_how=g.tl_how[r], release_event=g.tl_event[r])
        np.savez(self.out / 'states' / f'{name}.npz', **{k: v.detach().cpu().numpy() for k, v in data.items()})
        if self.scene_dump is True or (not isinstance(self.scene_dump, bool) and name in self.scene_dump):
            torch.save(dict(iteration=self.iteration, name=name, active_sh_degree=g.active_sh_degree,
                xyz=g._xyz.detach().cpu(), f_dc=g._features_dc.detach().cpu(), f_rest=g._features_rest.detach().cpu(),
                opacity=g._opacity.detach().cpu(), scaling=g._scaling.detach().cpu(), rotation=g._rotation.detach().cpu(),
                origin=g.origin.cpu(), init_id=g.init_id.cpu(), target_tag=g.target_tag.cpu(), target_index=g.target_index.cpu(),
                uid=g.tl_uid.cpu(), inside=g.tl_inside.cpu(), parent_uid=g.tl_parent.cpu(), born_at=g.tl_born.cpu(), born_how=g.tl_how.cpu(),
                release_event=g.tl_event.cpu(), target_released_at=g.target_released_at.cpu()), self.out / 'scene' / f'{name}.pt')
        rec = dict(name=name, iteration=self.iteration, seq=self.seq, gaussians=len(g._xyz), inside=len(r), seconds=time.perf_counter() - t0,
            phase='pre opacity reset, after this iteration densify/prune' if name.endswith('pre_reset') else
                  ('before first iteration, after r23 initialization' if name == '0' else 'end of iteration after update, densify/prune, opacity reset, 100-step check and final projection'))
        self.saves.append(rec)
        with (self.out / 'saves.jsonl').open('a') as f: f.write(json.dumps(rec) + '\n')
