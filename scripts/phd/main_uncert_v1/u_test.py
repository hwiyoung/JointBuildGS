"""PHD-MAIN-UNCERT-v1 checks of u_core on simulated points (no data): the face finding, the LMedS plane, the statistics, the timing of one
patch at the caps (8,000 ring points, 2,000 inner points). Writes /out/work/u_test.json. scientific_verdict: null."""
import json
import sys
import time

import numpy as np

sys.path.insert(0, "/repo/scripts/phd/main_uncert_v1")
import u_core as C  # noqa: E402

D = dict(layer_thickness_m=0.3, layer_step_m=0.05, layer_share=0.2, lmeds_triples=500, max_normal_angle_deg=45.0, inlier_k=2.5, q_level=0.683,
         wrong_m=0.2)
out = {}
rng = np.random.default_rng(0)
n = C.unit([0.2, 0.1, 1.0])
e1, e2 = C.in_plane_basis(n)


def disk(N, r0, r1, sig, off=0.0):
    rr = np.sqrt(rng.uniform(r0 ** 2, r1 ** 2, N)); th = rng.uniform(0, 2 * np.pi, N)
    return (rr * np.cos(th))[:, None] * e1 + (rr * np.sin(th))[:, None] * e2 + (off + rng.normal(0, sig, N))[:, None] * n


# 1. a clean plane with 3 cm noise: u ~ 3 cm, a ~ 0
ring, inner = disk(8000, 0.5, 1.5, 0.03), disk(2000, 0.0, 0.5, 0.03)
t0 = time.time()
pl = C.lmeds_plane(ring, n, np.random.default_rng(1), D)
out["seconds_lmeds_8000x500"] = round(time.time() - t0, 4)
d = (inner - pl["point"]) @ pl["normal"]
out["clean"] = dict(C.stats(d, D), angle=pl["angle_deg"], support=pl["support_lmeds"], support_final=pl["support_final"])
# 2. the order's mixture: 35 % of the inner points 40 cm lower (noise 2.5 cm) -> u small, q large
inner2 = np.vstack([disk(1300, 0, 0.5, 0.025), disk(700, 0, 0.5, 0.025, -0.40)])
ring2 = disk(8000, 0.5, 1.5, 0.025)
pl2 = C.lmeds_plane(ring2, n, np.random.default_rng(2), D)
d2 = (inner2 - pl2["point"]) @ pl2["normal"]
out["mixture_35pc_40cm"] = C.stats(d2, D)
# 3. a ridge: the ring half on another plane tilted 30 deg -> the majority plane is kept
R3 = disk(8000, 0.5, 1.5, 0.02)
side = (R3 @ e1) > 0
R3[side] += np.outer((R3[side] @ e1) * np.tan(np.radians(30)), n)
pl3 = C.lmeds_plane(R3, n, np.random.default_rng(3), D)
out["ridge"] = dict(angle=pl3["angle_deg"], support_lmeds=pl3["support_lmeds"], support_final=pl3["support_final"], s0=pl3["s0"])
# 4. face finding: a roof at +0.4 m (60 % of points), ground at -8 m (40 %), stray points above
t = np.concatenate([rng.normal(0.4, 0.03, 600), rng.normal(-8, 0.05, 400), rng.uniform(1, 10, 30)])
o, runs, M = C.find_face(t, 10.0, D)
out["face"] = dict(o=o, runs=runs, M=M)
o2, runs2, _ = C.find_face(np.concatenate([rng.normal(0.4, 0.03, 600), rng.normal(-3, 0.03, 600)]), 10.0, D)
out["face_two_layers"] = dict(o=o2, runs=runs2)
# 5. distinct triples
i0, i1, i2 = C.distinct_triples(np.random.default_rng(4), 5, 100000)
out["triples_distinct"] = bool(((i0 != i1) & (i0 != i2) & (i1 != i2)).all())
out["triples_cover"] = sorted(set(np.concatenate([i0, i1, i2]).tolist()))
# 6. the literal 'support' of the LMedS plane is >= 0.5 by construction
sup = []
for k in range(200):
    P = np.vstack([disk(60, 0.5, 1.5, 0.02), disk(40, 0.5, 1.5, 0.5)])
    p = C.lmeds_plane(P, n, np.random.default_rng(100 + k), D)
    sup.append(p["support_lmeds"])
out["support_lmeds_min_over_200_mixed"] = float(np.min(sup))
# 7. quadrants
out["quadrants_full"] = C.quadrants(disk(500, 0.5, 1.5, 0.0), e1, e2)
half = disk(500, 0.5, 1.5, 0.0); half = half[(half @ e1) > 0]
out["quadrants_half"] = C.quadrants(half, e1, e2)
print(json.dumps(out, indent=1))
json.dump(out, open("/out/work/u_test.json", "w"), indent=1)
# 8. lmeds_argmin == brute force (np.argmin of np.median) on mixed sets, and timing
agree, tf, tb = 0, 0.0, 0.0
for k in range(300):
    g = np.random.default_rng(1000 + k)
    N = int(g.choice([25, 300, 1500, 8000]))
    frac = g.uniform(0.3, 1.0)
    P = np.vstack([disk(int(N * frac), 0.5, 1.5, g.uniform(0.005, 0.1)), disk(N - int(N * frac), 0.5, 1.5, 0.6)])
    P = P + np.round(g.normal(0, 1, (1, 3)), 1) * 0  # relative to c already
    i0, i1, i2 = C.distinct_triples(g, len(P), 500)
    A = P[i0]; m = np.cross(P[i1] - A, P[i2] - A); L = np.linalg.norm(m, axis=1); ok = L > 1e-12; m = m[ok] / L[ok, None]; A = A[ok]
    t0 = time.time(); a = C.lmeds_argmin(P, m, A); tf += time.time() - t0
    t0 = time.time(); b = C.lmeds_argmin_brute(P, m, A); tb += time.time() - t0
    agree += int(a[0] == b[0] and a[1] == b[1])
out["argmin_agree_of_300"] = agree
out["argmin_seconds_fast_brute"] = [round(tf, 2), round(tb, 2)]
P = disk(8000, 0.5, 1.5, 0.03)
t0 = time.time()
for k in range(20):
    C.lmeds_plane(P, n, np.random.default_rng(k), D)
out["seconds_lmeds_plane_8000_fast"] = round((time.time() - t0) / 20, 4)
print(json.dumps({k: out[k] for k in ("argmin_agree_of_300", "argmin_seconds_fast_brute", "seconds_lmeds_plane_8000_fast")}))
json.dump(out, open("/out/work/u_test.json", "w"), indent=1)
