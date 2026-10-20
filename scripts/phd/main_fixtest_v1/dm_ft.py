"""PHD-MAIN-FIXTEST-v1 일 5: the new distance metric of the dist71 task (scripts/phd/main_dist71_v1: d2_dist, d2b_b0gt, d3_metrics.one) on
this task's results and on the reference results the dist71 task did not count (jointbuildgs:dev, CPU; run_step_ft.sh: /out = stage 1 (ro),
/ph ro with this payload rw at /ph/main_fixtest_v1/PHD-MAIN-FIXTEST-v1). The dist71 functions run unchanged; only three names are re-pointed
in their modules: the result list of a site, the mesh paths and the output folder (FT/dist). The patch normals of the scene GT are the
dist71 task's (SD/work/normals_<site>.npz, read only).

Results counted here (each with the priors it is read on):
  this task  FT/runs/<site>/<result> with a PASS receipt: fixA_*, fixAT_*, fixB_*, fixAB_* (training-view mesh post/mesh_tsdf.ply,
             virtual-view mesh gpu/virtual/mesh_virtual.ply where made)
  reference  nojudge_<prior>_s0 (S3/runs, stage 3 r15), imgonly_s0 (stage 1; both priors), abl_band_ALS_s0 (B173 주변) and
             abl_band_LoD2_s0 (R1) (S2/runs, stage 2 '허용 구간 없애기'), trust_ALS (stage 1, 항공 LiDAR)
The method's two seeds, the comparison methods and the prior before training stay in SD/dist (read there by d3).
  python dm_ft.py d2 <site> [result ...]     python dm_ft.py d2b [result ...]     python dm_ft.py d3
scientific_verdict: null."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/repo/scripts/phd/main_dist71_v1")
sys.path.insert(0, "/repo/scripts/phd/main_stage1_v1")
import dm_common as DC  # noqa: E402

FTP = DC.PH / "main_fixtest_v1/PHD-MAIN-FIXTEST-v1"
DIST_FT = FTP / "dist"
DIST_FT.mkdir(parents=True, exist_ok=True)
SD_DIST = DC.DIST
REF = {"nojudge": lambda p: [f"nojudge_{p}_s0"], "imgonly": lambda p: ["imgonly_s0"], "trust": lambda p: ["trust_ALS"] if p == "ALS" else [],
       "ablband": lambda p: []}
ABL_BAND = {("B173nb_b10", "ALS"): "abl_band_ALS_s0", ("R1rep_b10", "LoD2"): "abl_band_LoD2_s0"}


def own_results(site):
    out = []
    R = FTP / "runs" / site
    if R.exists():
        for d in sorted(R.iterdir()):
            f = d / "receipt.json"
            if d.is_dir() and f.exists() and json.loads(f.read_text()).get("status") == "PASS":
                prior = "ALS" if "_ALS_" in d.name else "LoD2"
                out.append((d.name, "fix", [prior]))
    return out


def ref_results(site):
    out = []
    for p in DC.PRIORS:
        for m, f in REF.items():
            for r in f(p):
                e = next((x for x in out if x[0] == r), None)
                if e is None:
                    out.append((r, m, [p]))
                else:
                    e[2].append(p)
        if (site, p) in ABL_BAND:
            out.append((ABL_BAND[(site, p)], "ablband", [p]))
    return out


def site_results(site):
    return own_results(site) + ref_results(site)


_mesh_paths = DC.mesh_paths


def mesh_paths(site, res):
    if res.startswith("fix"):
        R = FTP / "runs" / site / res
        return R / "post/mesh_tsdf.ply", R / "gpu/virtual/mesh_virtual.ply", "FT/runs (이 발주)"
    if res.startswith("nojudge_"):
        R = DC.S3 / "runs" / site / res
        return R / "post/mesh_tsdf.ply", R / "gpu/virtual/mesh_virtual.ply", "S3/runs (3단계 판정만 끈 본 방법)"
    if res.startswith("abl_band_"):
        R = DC.S2 / "runs" / site / res
        return R / "post/mesh_tsdf.ply", R / "gpu/virtual/mesh_virtual.ply", "S2/runs (2단계 허용 구간 없애기)"
    return _mesh_paths(site, res)


def main():
    cmd = sys.argv[1]
    if cmd == "d2":
        import d2_dist as D2
        D2.DIST, D2.site_results, D2.mesh_paths = DIST_FT, site_results, mesh_paths
        D2.main(sys.argv[2], sys.argv[3:] or None)
    elif cmd == "d2b":
        import d2b_b0gt as D2B
        D2B.DIST, D2B.site_results, D2B.mesh_paths = DIST_FT, site_results, mesh_paths
        D2B.main(sys.argv[2:] or None)
    elif cmd == "d3":
        import d3_metrics as D3
        data = {}
        for site, prior in DC.CASES:
            R = np.load(DC.S1 / "regions_v3" / f"regions_ext_v3_{site}_{prior}.npz")
            tau_patch = R["tau"].astype(np.float64)
            tau_als = float(np.unique(tau_patch)[0]) if prior == "ALS" else None
            vals = {}
            D3.DIST = SD_DIST                      # the dist71 task's results: the method's two seeds, the prior before training, comparisons
            for r in ("prop_%s_s0" % prior, "prop_%s_s1" % prior, "samepath_%s" % prior, "mvsfuse_%s" % prior):
                vals[r] = dict(source="SD/dist", places=D3.one(site, prior, r, tau_als, tau_patch))
            D3.DIST = DIST_FT
            for r, m, priors in site_results(site):
                if prior in priors:
                    vals[r] = dict(source="FT/dist", places=D3.one(site, prior, r, tau_als, tau_patch))
            data[f"{site}/{prior}"] = vals
        DC.jdump(FTP / "tables/d3_ft.json", dict(task="PHD-MAIN-FIXTEST-v1", made=DC.now(), rule="d3_metrics.one of the dist71 task, unchanged",
                                                 places=DC.PLACE_KO, data=data, scientific_verdict=None))
        print("d3 ft done", {k: sorted(v) for k, v in data.items()})
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
