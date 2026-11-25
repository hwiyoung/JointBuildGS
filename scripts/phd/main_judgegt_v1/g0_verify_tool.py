"""셈 도구 gtcols 를 numpy 직접 셈과 맞대기 (무작위 점, 참값 아님)."""
from common import *
def main():
    build(); rng = np.random.default_rng(20261125); X = np.r_[rng.uniform([-3, -3, -11], [3, 3, 11], (40000, 3)), rng.normal(size=(20000, 3))*[1, 1, .02] + [0, 0, 1.2]]
    p = O/'tmp/verify_pts.npy'; p.parent.mkdir(exist_ok=True, parents=True); np.save(p, X); n = 40
    c = rng.uniform(-.5, .5, (n, 3)); nr = rng.normal(size=(n, 3)); nr /= np.linalg.norm(nr, axis=1)[:, None]; nr[:3] = np.eye(3); t1 = rng.normal(size=(n, 3))
    r = rng.choice([.075, .125, .5], n); H = rng.choice([5., 10.], n); tau = rng.uniform(.05, .6, n); hM = rng.uniform(-2, 2, n); hM[::7] = np.nan
    cy = run('cyl', p, np.c_[c, nr, r, H], 'v_cyl'); co = run('col', p, np.c_[c, nr, t1, np.full(n, .125), H, tau, hM], 'v_col'); pc = run('pca', p, c, 'v_pca'); bad = 0
    for i in range(n):
        d = X - c[i]; t = d@nr[i]; rr = np.linalg.norm(d - t[:, None]*nr[i], axis=1); s = t[(np.abs(t) <= H[i]) & (rr <= r[i])]
        bad += int(len(s) != cy[i, 0]) + int(len(s) and not np.isclose(np.median(s), cy[i, 1]))
        u = t1[i] - (t1[i]@nr[i])*nr[i]; u /= np.linalg.norm(u); v = np.cross(nr[i], u); s = np.sort(t[(np.abs(t) <= H[i]) & (np.abs(d@u) <= .125) & (np.abs(d@v) <= .125)])
        exp = [len(s), (np.abs(s) <= tau[i]).sum(), (np.abs(s - hM[i]) <= tau[i]).sum() if np.isfinite(hM[i]) else -1, (np.abs(s) <= 1).sum()]
        cuts = np.flatnonzero(np.diff(s) > 4*tau[i]) + 1; seg = np.split(s, cuts) if len(s) else []; exp.append(len(seg))
        bad += int(not np.allclose(co[i, :5], exp)); bad += sum(int(not (co[i, 5+2*k] == len(g) and np.isclose(co[i, 6+2*k], np.median(g)))) for k, g in enumerate(seg[:6]))
        q = np.linalg.norm(X - c[i], axis=1)
        for j, rad in enumerate([.5, 1.]):
            Q = X[q <= rad]; bad += int(len(Q) != pc[i, 4*j])
            if len(Q) >= 3:
                w, V_ = np.linalg.eigh(np.cov(Q.T)); bad += int(abs(abs(V_[:, 0]@pc[i, 4*j+1:4*j+4]) - 1) > 1e-6)
    rec = dict(at=now(), cores=n, points=len(X), mismatches=bad, status='PASS' if bad == 0 else 'FAIL', scientific_verdict=None)
    dump(O/'bin/gtcols_verify.json', rec); print(rec); p.unlink()
if __name__ == '__main__': main()
