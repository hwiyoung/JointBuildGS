"""PHD-MAIN-AXES71-v2 일 1 '참값 밀도와 법선' (part): the GT normals of one site for the result-side distance (셈 마·바).

  python a1_normals.py <site> [...]      -> AX/work/normals_<site>.npz, AX/work/normals_<site>.json

Order 1.1: per GT point, a plane through the GT points within 0.5 m (fewer than 10 -> the nearest 10, the point itself included).
Per GT source (ULS; B0 also the primary GT) every point the evaluation uses (gt_classes 'use', as the distance task's d2_normals.py) gets
the covariance of its neighbours (Open3D estimate_point_covariances: radius search, every neighbour; KNN 10 for the points with fewer than
10 neighbours); normal = eigenvector of the smallest eigenvalue, plane residual (RMS of the neighbours' distances to the plane) = sqrt of
the smallest eigenvalue. The sign is not set (the result-side distance is unsigned). Check: the angle to the distance task's normals
(DM/work/normals_<site>.npz, radius 0.5 m, no normal under 10 neighbours) where both exist. [새로 셈] scientific_verdict: null."""
import sys
import time

import numpy as np
from scipy.spatial import cKDTree

from ax_common import DM, WORK, SiteGT, jdump, log, now


def covs(X, param):
    import open3d as o3d
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(X)
    return np.asarray(o3d.geometry.PointCloud.estimate_point_covariances(pc, param))


def plane_of(C, chunk=2_000_000):
    N = np.zeros((len(C), 3), np.float32)
    res = np.zeros(len(C), np.float32)
    for b in range(0, len(C), chunk):
        w, v = np.linalg.eigh(C[b:b + chunk])
        N[b:b + chunk] = v[:, :, 0]
        res[b:b + chunk] = np.sqrt(np.clip(w[:, 0], 0, None))
    return N, res


def main(site):
    import open3d as o3d
    t0 = time.time()
    gt = SiteGT(site)
    old = np.load(DM / "work" / f"normals_{site}.npz")
    out, meta = {}, {}
    for s, X in gt.X.items():
        nm = "gt_points" if s == 0 else "gt_primary"
        use = np.nonzero(gt.G[f"use_{nm}"])[0]
        P = X[use]
        cnt = cKDTree(P).query_ball_point(P, 0.5, workers=-1, return_length=True)
        C = covs(P, o3d.geometry.KDTreeSearchParamRadius(0.5))
        few = cnt < 10
        if few.any():
            # the nearest 10 of the whole source (the point itself included) for the points with fewer than 10 neighbours
            C_knn = covs(P, o3d.geometry.KDTreeSearchParamKNN(10))
            C[few] = C_knn[few]
            del C_knn
        N, res = plane_of(C)
        del C
        out[f"use_{s}"] = use.astype(np.int64)
        out[f"normal_{s}"] = N
        out[f"resid_{s}"] = res
        out[f"count_{s}"] = cnt.astype(np.int32)
        # check against the distance task's normals
        assert np.array_equal(old[f"use_{s}"], use)
        no = old[f"normal_{s}"].astype(np.float64)
        ok = np.isfinite(no).all(1)
        cosv = np.abs((no[ok] * N[ok].astype(np.float64)).sum(1))
        ang = np.degrees(np.arccos(np.clip(cosv, 0, 1)))
        q = lambda a, p: float(np.percentile(a, p))
        meta[nm] = dict(points=int(len(use)), knn_fallback=int(few.sum()), knn_fallback_share=float(few.mean()),
                        resid_cm=dict(p50=100 * q(res, 50), p90=100 * q(res, 90), p95=100 * q(res, 95), p99=100 * q(res, 99), mean=100 * float(res.mean())),
                        neighbours=dict(p50=q(cnt, 50), p10=q(cnt, 10), p1=q(cnt, 1)),
                        vs_distance_task=dict(compared=int(ok.sum()), angle_deg_p50=q(ang, 50), angle_deg_p99=q(ang, 99), angle_deg_max=float(ang.max()),
                                              share_over_1deg=float((ang > 1.0).mean())))
        log(site, nm, len(use), "knn", int(few.sum()), f"{time.time() - t0:.0f}s")
    np.savez_compressed(WORK / f"normals_{site}.npz", **out)
    jdump(WORK / f"normals_{site}.json", dict(site=site, rule=__doc__.split("\n\n")[1], sources=meta, seconds=round(time.time() - t0, 1), made=now(),
                                            scientific_verdict=None))
    log(site, "normals done", f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    for s in sys.argv[1:]:
        main(s)
