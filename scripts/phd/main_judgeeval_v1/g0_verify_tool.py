"""셈 도구 evcols 새 모드(imgk, colk, cylk)를 검증된 모드(img, col)와 numpy 직접 셈에 맞대기 (무작위 점)."""
from common import *
def main():
    build(); rng = np.random.default_rng(20261126); X = np.r_[rng.uniform([-3, -3, -11], [3, 3, 11], (40000, 3)), rng.normal(size=(20000, 3))*[1, 1, .03] + [0, 0, 1.2], rng.normal(size=(8000, 3))*[1, 1, .02] + [0, 0, -2.]]
    p = O/'tmp/verify_pts.npy'; p.parent.mkdir(exist_ok=True, parents=True); np.save(p, X); n = 40
    c = rng.uniform(-.5, .5, (n, 3)); nr = rng.normal(size=(n, 3)); nr /= np.linalg.norm(nr, axis=1)[:, None]; nr[:3] = np.eye(3); t1 = rng.normal(size=(n, 3)); H = rng.choice([5., 10.], n)
    taus = [.1, .15, .2, .3, .5, 1.]; bad = 0
    ik = run('imgk', p, np.c_[c, nr, t1, np.full(n, .125), H, np.tile(taus + [np.nan]*(KW - len(taus)), (n, 1))], 'v_imgk')
    for k, tau in enumerate(taus):
        im = run('img', p, np.c_[c, nr, t1, np.full(n, .125), H, np.full(n, tau)], f'v_img{k}')
        bad += int(not np.allclose(ik[:, 1+5*k:6+5*k][:, [0, 1, 2, 3, 4]], im[:, [1, 2, 3, 4, 5]], equal_nan=True)) + int(not np.array_equal(ik[:, 0], im[:, 0]))
        hI = im[:, 2]; co = run('col', p, np.c_[c, nr, t1, np.full(n, .125), H, np.full(n, tau), hI], f'v_col{k}')
        trip = np.full((n, 3*KW), np.nan); trip[:, 0] = tau; trip[:, 1] = hI; trip[:, 2] = tau
        ck = run('colk', p, np.c_[c, nr, t1, np.full(n, .125), H, trip], f'v_colk{k}')
        bad += int(not np.array_equal(ck[:, 0], co[:, 0])) + int(not np.array_equal(ck[:, 1], co[:, 3])) + int(not np.array_equal(ck[:, 2], co[:, 1])) + int(not np.array_equal(ck[:, 3], co[:, 2]))
    r = rng.choice([.075, .125], n); Hs = np.array([3., 5., 10.]); cy = run('cylk', p, np.c_[c, nr, r, np.tile(Hs, (n, 1))], 'v_cylk')
    for i in range(n):
        d = X - c[i]; t = d@nr[i]; rr = np.linalg.norm(d - t[:, None]*nr[i], axis=1)
        for h, Hh in enumerate(Hs):
            s = t[(np.abs(t) <= Hh) & (rr <= r[i])]; e = [len(s), s.mean() if len(s) else np.nan, np.median(s) if len(s) else np.nan, s.std(ddof=1) if len(s) > 1 else np.nan]
            bad += int(not np.allclose(cy[i, 4*h:4*h+4], e, equal_nan=True))
    rec = dict(at=now(), cores=n, points=len(X), mismatches=bad, status='PASS' if bad == 0 else 'FAIL', scientific_verdict=None); dump(O/'bin/evcols_verify.json', rec); print(rec); p.unlink()
if __name__ == '__main__': main()
