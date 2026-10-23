"""PHD-MAIN-UNCERT-v1 the per-patch definitions of order 1.1, 1.2 and 1.5 (pure functions; numpy only). Every number comes from the locked
config (configs/phd/main_uncert_v1/uncert_v1.json 'defs'), passed in as `D`.

  column_coords   lateral distance (to c, in the plane normal to n) and signed normal distance (outward +) of points
  find_face       1.1 '자료의 면 찾기': layers of thickness 0.3 m stepped 0.05 m from the + end inward; the first layer holding >= 20 % of
                  the gathered points (lateral <= 0.5 m, normal distance within the column range) is the face; o = the layer's middle.
                  Also the number of runs of qualifying layers (1.5 '여러 층' = two runs or more)
  lmeds_plane     1.2-1: 500 random triples (seeded), candidates whose normal is more than 45 deg from n removed, least median of squares;
                  s0 = 1.4826 (1 + 5 / (N - 3)) sqrt(median r^2); least-squares refit on the points within 2.5 s0; normal on n's side
  stats           1.2-3: a = |median d|, s = 1.4826 median |d - median d|, u = sqrt(a^2 + s^2), q = the 68.3 % value of |d|
  real_error      1.5: the same form against the GT plane, its 68.3 % value and the share of |e| > 0.2 m
scientific_verdict: null."""
import numpy as np

NMAD_K = 1.4826


def unit(v):
    v = np.asarray(v, np.float64)
    return v / np.linalg.norm(v)


def in_plane_basis(n):
    """two unit vectors orthogonal to n (for the quadrant test of 1.2-5; a computing detail)."""
    a = np.array([0.0, 0.0, 1.0]) if abs(n[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    e1 = unit(np.cross(a, n))
    return e1, np.cross(n, e1)


def column_coords(V, n):
    """V = points - c [N, 3] (float64); returns (t = normal distance, rho = lateral distance, lateral vectors)."""
    t = V @ n
    L = V - t[:, None] * n[None, :]
    return t, np.sqrt(np.einsum("ij,ij->i", L, L)), L


def find_face(t, H, D):
    """t: normal distances of the gathered points (lateral <= inner radius, |t| <= H). Returns (o or None, n_layers_runs, M)."""
    M = len(t)
    if M == 0:
        return None, 0, 0
    thick, step, frac = D["layer_thickness_m"], D["layer_step_m"], D["layer_share"]
    ts = np.sort(t)
    K = int(round((2 * H - thick) / step)) + 1
    tops = H - step * np.arange(K)
    bots = tops - thick
    cnt = np.searchsorted(ts, tops + 1e-9, "right") - np.searchsorted(ts, bots - 1e-9, "left")
    ok = cnt >= frac * M
    if not ok.any():
        return None, 0, M
    k = int(np.argmax(ok))
    runs = int(ok[0]) + int(np.count_nonzero(ok[1:] & ~ok[:-1]))
    return float(tops[k] - 0.5 * thick), runs, M


def distinct_triples(rng, N, h):
    """h triples of three distinct indices in [0, N), uniform."""
    i0 = rng.integers(0, N, h)
    i1 = rng.integers(0, N - 1, h)
    i1 = i1 + (i1 >= i0)
    lo, hi = np.minimum(i0, i1), np.maximum(i0, i1)
    i2 = rng.integers(0, N - 2, h)
    i2 = i2 + (i2 >= lo)
    i2 = i2 + (i2 >= hi)
    return i0, i1, i2


def lmeds_argmin_brute(P, m, A):
    """np.argmin over the hypotheses of np.median(r^2) (float32 residuals): the reference of lmeds_argmin."""
    r = (m.astype(np.float32) @ P.astype(np.float32).T) - np.einsum("ij,ij->i", A, m).astype(np.float32)[:, None]
    med = np.median(r * r, axis=1)
    j = int(np.argmin(med))
    return j, float(med[j])


def lmeds_argmin(P, m, A):
    """the same answer as lmeds_argmin_brute, faster: the exact median of a guess (the best hypothesis on an every-k-th subsample) is m*;
    a hypothesis can have median <= m* only if at least N/2 of its r^2 are <= m* (numpy's median of an even count is the mean of the two
    middle values), so the exact medians are computed only for those, and the first minimum among them is np.argmin's answer."""
    N = len(P)
    r = (m.astype(np.float32) @ P.astype(np.float32).T) - np.einsum("ij,ij->i", A, m).astype(np.float32)[:, None]
    r2 = r * r
    if N <= 1200:
        med = np.median(r2, axis=1)
        j = int(np.argmin(med))
        return j, float(med[j])
    sub = r2[:, :: max(1, N // 1000)]
    g = int(np.argmin(np.median(sub, axis=1)))
    mstar = np.median(r2[g])
    cnt = np.count_nonzero(r2 <= mstar, axis=1)
    cand = np.nonzero(2 * cnt >= N)[0]
    med = np.median(r2[cand], axis=1)
    k = int(np.argmin(med))
    return int(cand[k]), float(med[k])


def lmeds_plane(P, n, rng, D):
    """P [N, 3] (relative to c, float64), n unit. Returns dict or None ('면 없음': no candidate left)."""
    N = len(P)
    h = D["lmeds_triples"]
    i0, i1, i2 = distinct_triples(rng, N, h)
    A = P[i0]
    m = np.cross(P[i1] - A, P[i2] - A)
    L = np.linalg.norm(m, axis=1)
    ok = L > 1e-12
    m[ok] /= L[ok, None]
    ok &= np.abs(m @ n) >= np.cos(np.radians(D["max_normal_angle_deg"]))
    if not ok.any():
        return None
    m, A = m[ok], A[ok]
    j, med_j = lmeds_argmin(P, m, A)
    s0 = NMAD_K * (1.0 + 5.0 / (N - 3)) * np.sqrt(max(med_j, 0.0))
    rj = (P - A[j]) @ m[j]
    inl = np.abs(rj) <= D["inlier_k"] * s0
    Q = P[inl]
    cen = Q.mean(0)
    if len(Q) >= 3:
        _, _, vt = np.linalg.svd(Q - cen, full_matrices=False)
        mf = vt[-1]
    else:                                                       # fewer than 3 inliers: keep the LMedS plane (recorded by n_inliers)
        mf, cen = m[j].copy(), A[j].copy()
    if mf @ n < 0:
        mf = -mf
    rf = (P - cen) @ mf
    return dict(normal=mf, point=cen, offset=float(cen @ mf), s0=float(s0), n_inliers=int(inl.sum()),
                support_lmeds=float(inl.mean()), support_final=float(np.mean(np.abs(rf) <= D["inlier_k"] * s0)),
                angle_deg=float(np.degrees(np.arccos(np.clip(abs(mf @ n), 0, 1)))), n_candidates=int(ok.sum()))


def stats(d, D):
    """a, s, u, q of signed distances d (m)."""
    med = float(np.median(d))
    s = NMAD_K * float(np.median(np.abs(d - med)))
    a = abs(med)
    return dict(a=a, s=s, u=float(np.hypot(a, s)), q=float(np.quantile(np.abs(d), D["q_level"])), med=med)


def real_error(d, D):
    """1.5: bias, spread, e, its 68.3 % value and the share of wrong points (|e| > threshold) of signed distances d to the GT plane."""
    st = stats(d, D)
    return dict(bias=st["med"], spread=st["s"], e=st["u"], qe=st["q"], f=float(np.mean(np.abs(d) > D["wrong_m"])))


def quadrants(Lr, e1, e2):
    """number of the four quadrants around c holding at least one ring point."""
    x, y = Lr @ e1, Lr @ e2
    qd = (x >= 0).astype(np.int8) + 2 * (y >= 0).astype(np.int8)
    return int(np.unique(qd).size)
