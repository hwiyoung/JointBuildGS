"""Order 4.1 definitions, identical to ref/trainlog_proto_v1.py (site, nrm, correction-site distance, band)."""
import numpy as np
from scipy.spatial import cKDTree as T
TAU = 21.2  # cm, prototype TAU

class Defs:
    def __init__(self, d0):
        """d0 = derived 0-iteration state (PROCFIG columns)."""
        sb = d0['target_tag'] == 1; self.ptx = d0['target_xyz'][sb]; self.pj = d0['judgment'][sb]; self.ptree = T(self.ptx[:, :2])
        m = (d0['target_tag'] == 1) & (d0['judgment'] == 2) & (~d0['wall']); self.tx = d0['target_xyz'][m]; self.ts = d0['target_sigma'][m]; self.tr = T(self.tx[:, :2])
        self.c2 = self.tx[:, :2].mean(0); _, _, vt = np.linalg.svd(self.tx[:, :2]-self.c2, full_matrices=False); self.a1, self.a2 = vt[0], vt[1]
        self.hw = float(np.median(1.96*self.ts))*100

    def site(self, xyz):
        dd, ii = self.ptree.query(xyz[:, :2], k=8, distance_upper_bound=.35); out = np.full(len(xyz), -1)
        for c in range(8):
            ok = (ii[:, c] < len(self.ptx)) & (out < 0)
            jj = np.where(ok)[0]; z = np.abs(xyz[jj, 2]-self.ptx[ii[jj, c], 2]) <= .5; out[jj[z]] = self.pj[ii[jj[z], c]]
        return out

    def nrm(self, p):
        ii = self.tr.query_ball_point(p[:2], .5)
        if len(ii) < 5: return np.array([0, 0, 1.])
        q = self.tx[ii]; _, _, v = np.linalg.svd(q-q.mean(0), full_matrices=False); return v[2]*(1 if v[2][2] >= 0 else -1)

    def placed(self, d):
        """Drawn site colour: bound -> own patch judgment, else site()."""
        bound = d['target_tag'] == 1; return np.where(bound, d['judgment'], self.site(d['xyz'].astype(float)))

    def section(self, d):
        """Correction-site Gaussians (non-wall, horizontal <=0.25 m to a reference target): indices, signed cm, u, v, nearest target."""
        xyz = d['xyz'].astype(float); idx = np.where(~d['wall'])[0]; dist, nn = self.tr.query(xyz[idx, :2]); g = idx[dist <= .25]; nn = nn[dist <= .25]
        sd = np.array([(xyz[i]-self.tx[j])@self.nrm(xyz[i]) for i, j in zip(g, nn)])*100 if len(g) else np.zeros(0)
        return dict(index=g, nearest=nn, sd=sd, u=(xyz[g, :2]-self.c2)@self.a1, v=(xyz[g, :2]-self.c2)@self.a2, bound=d['target_tag'][g] == 1,
                    sigma_cm=np.where(d['target_tag'][g] == 1, d['target_sigma'][g], self.ts[nn])*100)

    def signed_points(self, P):
        """Signed cm distance of arbitrary points to the reference target surface (same rule), with u/v; only points <=0.25 m horizontally."""
        P = np.asarray(P, float); dist, nn = self.tr.query(P[:, :2]); ok = dist <= .25; sd = np.full(len(P), np.nan)
        for i in np.flatnonzero(ok): sd[i] = (P[i]-self.tx[nn[i]])@self.nrm(P[i])*100
        return sd, (P[:, :2]-self.c2)@self.a1, (P[:, :2]-self.c2)@self.a2

    def band(self, sec30000):
        vv = sec30000['v'][~sec30000['bound']]; bins = np.arange(vv.min(), vv.max(), 1.); h, _ = np.histogram(vv, bins); return float(bins[h.argmax()])
