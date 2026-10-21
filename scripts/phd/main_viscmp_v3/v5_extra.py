"""PHD-MAIN-VISCMP-v3 the values of the two places request 3 lists without drawing: the V5 auxiliary piece and the fill task's rule place
(SL/prep/figpos/obs_masked.json 'main'): per panel the median |d_g| of the place's region rows (stored distance files; the image depth =
the camera of v5_select's rule, its training MVS depth map as a pixel-grid mesh) [이 발주에서 냄].
  python v5_extra.py -> /docs/tables/V5_extra.json   scientific_verdict: null"""
import numpy as np

import vc_common  # noqa: F401
import p0_places as P0
import vd_dist as VD
from v5_select import camera_for
from vc_common import CFG, DOCS, S0, jdump, jl, log, now, res_name

PANELS = ["학습 전 사전 정보", "영상 깊이", "2DGS", "GeoGS", "결합", "CDGS", "본 방법", "본 방법 씨앗 1"]


def values(site, prior, patches):
    C = VD.Case(site, prior)
    ri = C.rows_of(patches)
    out = dict(site=site, prior=prior, patches=int(len(patches)), rows=int(len(ri)))
    cam = camera_for(site, prior, P0.patch_corners(P0.store(site, prior), np.asarray(patches, int)))
    out["camera"] = cam
    for m in PANELS:
        if m == "영상 깊이":
            if not cam:
                out[m] = None; continue
            dep = np.load(S0 / "fork_inputs/s61" / site / "maps/mvs" / f"{cam['view']}.npy")
            V, F, _ = VD.depth_mesh(cam["view"], dep)
            d = C.dg_rows(V, F, ri)
        else:
            st = C.stored(res_name(m, prior))
            if st is None:
                out[m] = None; continue
            d = st["rows"][ri]
        out[m] = dict(value_cm=round(100 * float(np.median(np.abs(d))), 1), signed_cm=round(100 * float(np.median(d)), 1))
        log(site, prior, m, out[m])
    return out


def main():
    P = jl(CFG)["places"]["V5"]
    res = dict(made=now(), scientific_verdict=None,
               auxiliary=dict(P["auxiliary"], values=values(P["site"], P["prior"], P["auxiliary_patches"])),
               fill_rule_place=dict(P["fill_rule_place"]["main"], source=P["fill_rule_place"]["source"],
                                    values=values(P["fill_rule_place"]["main"]["site"], P["fill_rule_place"]["main"]["prior"], P["fill_rule_place"]["patch_list"])))
    jdump(DOCS / "tables/V5_extra.json", res)


if __name__ == "__main__":
    main()
