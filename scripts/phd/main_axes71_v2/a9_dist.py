"""PHD-MAIN-AXES71-v2 일 9: the per-point distances of the earlier trainings (jointbuildgs:dev, CPU; no GPU, no training).

  python a9_dist.py [bundle-or-result ...]   -> AX/dist9/<geom site>_<prior>__<run>.npz (the distance task's form, where no file exists yet)
                                               and __x.npz (this task's result-side extras), AX/dist9/done9.json

The trainings come from the ledger AX/work/ledger9/ledger9.json (rows with a training-view mesh). A training on a stage-3 image condition
(B0a15, B0a9, B0a3, B0n13, B0n8, B0n2) uses the B0_b10 patches, GT and region rows (checked: rows_<prior>.npz of the condition = B0_b10's,
the region file's centre, tau, area, kind, in_eval the same; only the codes differ), so its distances are counted on B0_b10 and named
<condition>__<result>; the cells come later from the condition's own region file (a9_metrics.py). A per-point file that the fix test already
made (FT/dist) is used as it is (the result sample is regenerated and checked against it). The invisible cells on the virtual-view mesh are
counted for the rows of codes 5 and 14 of the region file the training used (in range, with GT, code not 0). [이 발주에서 냄]
scientific_verdict: null."""
import sys
import time

import numpy as np
from scipy.spatial import cKDTree

import a2x_sample as AXS
from ax_common import AX, FT, PRIORS, SiteGT, Unit, jdump, jl, log, now, short
import dm_common as DMC
from d2_dist import oriented_sign
from src.phd.metrics_v3.surface import MeshScene

DIST9 = AX / "dist9"
DIST9.mkdir(exist_ok=True)
ROOT = {"S0": "/s0", "S1": "/out", "S2": "/ph/main_stage2_v1/PHD-MAIN-STAGE2-v1", "SF": "/ph/main_fix_v1/PHD-MAIN-FIX-v1", "S3": "/ph/main_stage3_v1/PHD-MAIN-STAGE3-v1",
        "FT": "/ph/main_fixtest_v1/PHD-MAIN-FIXTEST-v1", "SB": "/ph/main_baselines_v1/PHD-MAIN-BASELINES-v1", "SL": "/ph/main_fill_v1/PHD-MAIN-FILL-v1",
        "D71": "/ph/main_dist71_v1/PHD-MAIN-DIST71-v1", "MF": "/mf", "MT": "/mt", "DR": "/dr", "AX": str(AX)}
SITES = ("B0_b10", "B173nb_b10", "R1rep_b10")


def P(rel):
    if rel is None:
        return None
    a, b = rel.split("/", 1)
    from pathlib import Path
    return Path(ROOT[a]) / b


def region_of(row):
    return P(row["unit_inputs"]["region_file"]["path"])


def jobs(sel=None):
    L = jl(AX / "work/ledger9/ledger9.json")["rows"]
    out = []
    for r in L:
        mt = r.get("mesh_train") or {}
        if not mt.get("exists"):
            continue
        if not region_of(r).exists():           # no region file of the training (stage-3 ALS cases): 정의 없음, not counted
            continue
        if sel and r["bundle"] not in sel and r["result"] not in sel:
            continue
        cond = r["site"] if r["site"] not in SITES else None
        geom = r["site"] if cond is None else "B0_b10"
        run = r["result"] if cond is None else f"{cond}__{r['result']}"
        out.append(dict(bundle=r["bundle"], geom=geom, cond=cond, prior=r["case_prior"], run=run, result=r["result"], mesh=P(mt["path"]),
                        virtual=P((r.get("mesh_virtual") or {}).get("path")) if (r.get("mesh_virtual") or {}).get("exists") else None, region=region_of(r)))
    return out


def vcell_of(region, has):
    R = np.load(region)
    c = R["code_ext_v3"].astype(np.int64)
    return R["in_eval"].astype(bool) & has & (c != 0) & np.isin(c, (5, 14))


def existing(geom, prior, res, cond):
    if cond is None:
        f = FT / "dist" / f"{geom}_{prior}__{res}.npz"
        if f.exists():
            return f
    f = DIST9 / f"{geom}_{prior}__{(cond + '__' + res) if cond else res}.npz"
    return f if f.exists() else None


def main(sel=None):
    import os
    T0 = time.time()
    J = sorted(jobs(sel), key=lambda j: (j["geom"], j["prior"], j["run"]))
    nsh, ish = int(os.environ.get("SHARDS", "1")), int(os.environ.get("SHARD", "0"))
    J = [j for k, j in enumerate(J) if k % nsh == ish]          # disjoint shards (run in parallel containers)
    log("jobs", len(J))
    done = dict(log=[])
    import os as _os
    donef = DIST9 / f"done9_shard{_os.environ.get('SHARD', '0')}of{_os.environ.get('SHARDS', '1')}.json"
    ctx = {}
    for j in J:
        geom, prior = j["geom"], j["prior"]
        xf = DIST9 / f"{geom}_{prior}__{j['run']}__x.npz"
        if xf.exists():
            log(j["run"], geom, prior, "있음 (건너뜀)")
            continue
        if geom not in ctx:
            ctx.clear()
            gt = SiteGT(geom)
            U = {p: Unit(geom, p, gt) for p in PRIORS}
            Nfull = AXS.normals_full(geom, gt)
            refS = AXS.Ref(gt.Gb, Nfull[0][gt.bs_idx])
            refB = None
            if geom == "B0_b10":
                m1 = gt.G["use_gt_primary"].astype(bool)
                P1, N1 = gt.X[1][m1], Nfull[1][m1]
                k = gt.in_cells(P1)
                refB = AXS.Ref(np.vstack([gt.Gb, P1[k]]), np.vstack([Nfull[0][gt.bs_idx], N1[k]]))
            trees = {p: cKDTree(U[p].centre) for p in PRIORS}
            own = {p: DMC.owner_of_scene_points(geom, p, gt) for p in PRIORS}
            near = {p: trees[p].query(gt.Gb, workers=-1)[1].astype(np.int64) for p in PRIORS}
            ctx[geom] = dict(gt=gt, U=U, Nfull=Nfull, refS=refS, refB=refB, trees=trees, own=own, near=near)
        c = ctx[geom]
        gt, u = c["gt"], c["U"][prior]
        t0 = time.time()
        V, F = DMC.read_mesh(j["mesh"])
        n_tri = int(len(F))
        ex = existing(geom, prior, j["result"], j["cond"])
        sc = MeshScene(V, F) if ex is None else None
        smp = DMC.result_sample(V, F, gt)
        del V, F
        np.save(DIST9 / f"{geom}__{j['run']}__xyz.npy", smp.astype(np.float32))
        z0 = np.load(ex) if ex is not None else None
        bS = z0["q_d"] if (z0 is not None and len(z0["q_d"]) == len(smp)) else None
        dr, nd, lat, _ = c["refS"].query(smp, bS)
        if c["refB"] is not None:
            fb0 = (FT / "dist" / f"{geom}_{prior}__{j['result']}__b0gt.npz") if ex is not None else None
            bB = np.load(fb0)["q_d_b0gt"] if (fb0 is not None and fb0.exists() and bS is not None) else None
            drb, ndb, latb, _ = c["refB"].query(smp, bB)
        if ex is None:
            AXS.DIST = DIST9
            AXS.full_dist(geom, prior, j["run"], j["bundle"], u, gt, sc, smp, c["Nfull"][0][gt.bs_idx], c["Nfull"], c["own"], c["near"], c["refS"].tree, j["mesh"],
                          j["bundle"], j["virtual"])
            if geom == "B0_b10":
                np.savez_compressed(DIST9 / f"{geom}_{prior}__{j['run']}__b0gt.npz", q_d_b0gt=drb.astype(np.float32))
            ex = DIST9 / f"{geom}_{prior}__{j['run']}.npz"
        z = np.load(ex)
        if len(z["q_d"]) != len(smp):
            raise RuntimeError(f"{j['run']}: sample differs from {ex}")
        chk = dict(n=int(len(smp)), max_abs_dr_diff_m=float(np.max(np.abs(z["q_d"].astype(np.float64) - dr))) if len(smp) else None, file=short(ex))
        pa = z["q_patch"].astype(np.int64)
        pd = np.linalg.norm(smp - u.centre[pa], axis=1) if len(smp) else np.zeros(0)
        out = dict(dr=dr.astype(np.float32), ndist=nd.astype(np.float32), lat=lat.astype(np.float32), pd=pd.astype(np.float32))
        if c["refB"] is not None:
            out.update(dr_b=drb.astype(np.float32), ndist_b=ndb.astype(np.float32), lat_b=latb.astype(np.float32))
        meta = dict(job={k: str(v) for k, v in j.items()}, triangles=n_tri, sample_points=int(len(smp)), check=chk, virtual=None)
        if j["virtual"] is not None:
            vm = vcell_of(j["region"], u.has_gt)
            rows_v = np.nonzero(vm[u.r_pa])[0]
            Vv, Fv = DMC.read_mesh(j["virtual"])
            scv = MeshScene(Vv, Fv)
            smv = DMC.result_sample(Vv, Fv, gt)
            del Vv, Fv
            rv = scv.distance(u.r_P[rows_v]) if len(rows_v) else np.zeros(0)
            qv, _ = DMC.closest(scv, u.r_P[rows_v]) if len(rows_v) else (np.zeros((0, 3)), None)
            n_rows = np.full((len(rows_v), 3), np.nan, np.float32)
            for s_ in np.unique(u.r_src[rows_v]):
                m = u.r_src[rows_v] == s_
                n_rows[m] = c["Nfull"][int(s_)][u.r_pt[rows_v][m]]
            vs = oriented_sign(u.r_P[rows_v], qv, rv, n_rows, u.r_n[rows_v]) if len(rows_v) else np.zeros(0, np.int8)
            pav = c["trees"][prior].query(smv, workers=-1)[1].astype(np.int64) if len(smv) else np.zeros(0, np.int64)
            kv = vm[pav] if len(pav) else np.zeros(0, bool)
            R_ = c["refB"] if c["refB"] is not None else c["refS"]
            vdr, vnd, vlat, _ = R_.query(smv[kv])
            vpd = c["trees"][prior].query(smv[kv], workers=-1)[0] if kv.any() else np.zeros(0)
            out.update(v_r_idx=rows_v.astype(np.int32), v_r_d=np.asarray(rv, np.float32), v_r_sign=vs, v_q_patch=pav[kv].astype(np.int32),
                       v_q_dr=vdr.astype(np.float32), v_q_ndist=vnd.astype(np.float32), v_q_lat=vlat.astype(np.float32), v_q_pd=np.asarray(vpd, np.float32),
                       v_q_has_gt=u.has_gt[pav[kv]] if kv.any() else np.zeros(0, bool))
            meta["virtual"] = dict(mesh=short(j["virtual"]), rows=int(len(rows_v)), sample_points_in_cells=int(kv.sum()))
            del scv
        np.savez_compressed(xf, **out)
        meta.update(seconds=round(time.time() - t0, 1), made=now(), scientific_verdict=None)
        jdump(xf.with_suffix(".json"), meta)
        done["log"].append(dict(run=j["run"], geom=geom, prior=prior, seconds=meta["seconds"], full=sc is not None))
        jdump(donef, done)
        del sc, smp
        log(j["run"], geom, prior, f"tri {n_tri:,}", f"{time.time() - t0:.0f}s", "full" if ex and str(ex).startswith(str(DIST9)) else "")
    log("a9 dist done", f"{time.time() - T0:.0f}s")


if __name__ == "__main__":
    main(sys.argv[1:] or None)
