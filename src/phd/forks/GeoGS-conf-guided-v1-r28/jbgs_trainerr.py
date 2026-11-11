"""r28 PHD-MAIN-TRAINERR-v1: three diagnostic intervention switches (all default off). No reference geometry is read.

--jbgs_bind_background on : at every periodic 100-step check, after the inherited reattach, unbound background
                             Gaussians (origin==0, target_tag==0) meeting the inherited reattach rule
                             (TargetR7.candidates: tangent <= 0.5 m, normal excess beyond 1.96 sigma <= 0.5 m) are bound.
--jbgs_rebind_released on  : the same for released Gaussians (target_tag==2).
--jbgs_reassign_same on    : in every reattach, a bound Gaussian may only be reassigned to a patch with the same
                             judgment (patch_region) as its current patch and |n_cur.(anchor_new - anchor_cur)| <= 1.96 sigma_cur;
                             no candidate = released (inherited release path).
With every switch off this module is not imported (r23 / r25 / r27 classes are used unchanged).
"""
import json
import numpy as np
import torch
from jbgs_finaltrain import FinalTrain
from jbgs_target_r7 import TargetR7
from jbgs_target import normal_projection

SWITCHES = ('jbgs_bind_background', 'jbgs_rebind_released', 'jbgs_reassign_same')


def any_switch(args):
    return any(getattr(args, k, 'off') == 'on' for k in SWITCHES)


class Intervene:
    def init_intervene(self, args):
        self.iv_bind_bg = getattr(args, 'jbgs_bind_background', 'off') == 'on'
        self.iv_rebind = getattr(args, 'jbgs_rebind_released', 'off') == 'on'
        self.iv_same = getattr(args, 'jbgs_reassign_same', 'off') == 'on'
        self._iv_cur = None

    def candidates(self, xyz):
        if self._iv_cur is None: return super().candidates(xyz)
        return self.candidates_same(xyz, self._iv_cur)

    def candidates_same(self, xyz, cur):
        """TargetR7.candidates with the extra same-judgment / height-within-interval filter per query row."""
        q = xyz.detach().double().cpu().numpy(); n = len(q); assert len(cur) == n
        chosen = np.zeros(n, np.int64); best_t = np.full(n, np.inf); best_e = np.full(n, np.inf)
        TargetR7.candidates(self, xyz[:0])  # build the inherited cache (normal, width, groups) without queries
        normal, width, groups = self._candidate_cache
        region = self.patch_region.cpu().numpy()
        for start in range(0, n, 512):
            stop = min(n, start + 512); x = q[start:stop]; cc = cur[start:stop]
            for ids, tree, radius in groups:
                lists = tree.query_ball_point(x, radius, workers=1); lengths = np.fromiter(map(len, lists), dtype=np.int64, count=len(x))
                if not lengths.sum(): continue
                row = np.repeat(np.arange(len(x)), lengths); idx = ids[np.concatenate(lists).astype(np.int64)]
                delta = x[row] - self.points[idx]; h = np.einsum('ij,ij->i', delta, normal[idx]); tan = np.linalg.norm(delta - h[:, None] * normal[idx], axis=1)
                excess = np.maximum(abs(h) - width[idx], 0); ok = (tan <= .5) & (excess <= .5)
                c0 = cc[row]
                same = region[idx] == region[c0]
                dh = np.abs(np.einsum('ij,ij->i', self.points[idx] - self.points[c0], normal[c0]))
                ok &= same & (dh <= width[c0])
                row, idx, tan, excess = row[ok], idx[ok], tan[ok], excess[ok]
                if not len(row): continue
                order = np.lexsort((self.valid_patch[idx], excess, tan, row)); row, idx, tan, excess = row[order], idx[order], tan[order], excess[order]
                first = np.r_[True, row[1:] != row[:-1]]; row, idx, tan, excess = row[first] + start, idx[first], tan[first], excess[first]
                better = (tan < best_t[row]) | ((tan == best_t[row]) & ((excess < best_e[row]) | ((excess == best_e[row]) & (self.valid_patch[idx] < self.valid_patch[chosen[row]]))))
                rr = row[better]; chosen[rr] = idx[better]; best_t[rr] = tan[better]; best_e[rr] = excess[better]
        return best_t, best_e, chosen

    @torch.no_grad()
    def reattach(self, g, reason):
        if self.iv_same:
            rows = torch.where(g.target_tag == 1)[0]
            self._iv_cur = g.target_index[rows].detach().cpu().numpy().astype(np.int64)
        try:
            super().reattach(g, reason)
        finally:
            self._iv_cur = None
        if reason == 'periodic' and (self.iv_bind_bg or self.iv_rebind): self.bind_unbound(g)

    @torch.no_grad()
    def bind_unbound(self, g):
        sel = torch.zeros(len(g._xyz), dtype=torch.bool, device=g._xyz.device)
        if self.iv_bind_bg: sel |= (g.target_tag == 0) & (g.origin == 0)
        if self.iv_rebind: sel |= g.target_tag == 2
        rows = torch.where(sel)[0]
        if not len(rows): return
        tangent, excess, idx = TargetR7.candidates(self, g._xyz[rows])
        ok = torch.tensor(np.isfinite(tangent), device=rows.device); r = rows[ok]
        was = g.target_tag[r].clone()
        g.target_tag[r] = 1; g.target_index[r] = torch.tensor(idx, device=rows.device)[ok]
        before = g._xyz[r].clone()
        if len(r):  # project only the newly bound rows (a second whole-scene projection would round other bound rows)
            idx = g.target_index[r]; g._xyz[r] = normal_projection(g._xyz[r], self.patch_anchor[idx], self.patch_normal[idx], self.patch_sigma[idx])
        move = float(torch.linalg.vector_norm(g._xyz[r].double() - before.double(), dim=1).max()) if len(r) else 0.
        if move > .5 + 3e-5: raise RuntimeError('R28_BIND_PROJECTION_GT_HALF_METRE')
        row = dict(iteration=self.iteration, queried=len(rows), bound=len(r), from_background=int((was == 0).sum()), from_released=int((was == 2).sum()),
                   max_projection_m=move, current_patch=int((g.target_tag == 1).sum()), rule='TargetR7.candidates (tangent<=0.5, normal excess<=0.5)')
        if getattr(self, 'trainlog_on', False):
            self.push('bind', uid=g.tl_uid[r], was=was, new=g.target_index[r], xyz=g._xyz[r]); g.tl_last_xyz[r] = g._xyz[r].detach()
        with (self.mon / 'intervene.jsonl').open('a') as f: f.write(json.dumps(row) + '\n')


class FinalTrainX(Intervene, FinalTrain):
    def __init__(self, args, scene, g):
        self.init_intervene(args)
        FinalTrain.__init__(self, args, scene, g)


def trainlog_class():
    from jbgs_trainlog import TrainLog

    class TrainLogX(Intervene, TrainLog):
        def __init__(self, args, scene, g):
            self.init_intervene(args)
            TrainLog.__init__(self, args, scene, g)
    return TrainLogX
