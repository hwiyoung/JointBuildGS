"""PHD-MAIN-BASELINES-v1 MVS-based fusion (reproduced), order 5.6 item 3 and 6.5 '영상': one pair per training view of a site.
The pair of training view i is a training view j of the same flight (capture time from the image name; mf_common.flights) whose optical
axis differs from i's by less than 20 deg and whose overlap with i is closest to 60 % (overlap = share of view i's MVS points, every 4th
pixel, that project inside view j's frame; MVS maps are the first stage's export, the same for both priors (checked), so both priors get
the same pairs). A training view without a candidate is not judged (counted). jointbuildgs:dev through run_cpu_bl.sh.
  python mvsfuse/pairs.py <site> [...]   -> SB/prep/mvsfuse/pairs_<site>.json, SB/prep/mvsfuse/flights.json (the flight table and the time
                                           rule against the DJI counter, reference)
scientific_verdict: null."""
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mf_common as M  # noqa: E402

R = M.RULE["pairs"]


def main(site):
    t0 = time.time()
    fl, table = M.flights()
    V, train, test = M.views(site)
    st = R["overlap_stride_px"]
    pts, same_mvs, nmvs = {}, 0, {}
    for s in train:
        n = f"{s}.jpg"
        m = M.load_map(site, "LoD2", "mvs", s)
        same_mvs += int(np.array_equal(m, M.load_map(site, "ALS", "mvs", s), equal_nan=True))
        sub = m[::st, ::st].astype(np.float64)
        ok = np.isfinite(sub) & (sub > 0)
        rays = V.rays(n, np.float64)[::st, ::st]
        pts[s] = V.C(n)[None, :] + sub[ok][:, None] * rays[ok]
        nmvs[s] = int(ok.sum())
    axis = {s: V.R(f"{s}.jpg").T @ np.array([0.0, 0.0, 1.0]) for s in train}
    rows, no_pair = [], []
    for s in train:
        if s not in fl:
            raise SystemExit(f"{s} is not among the 937 posed images")
        cand = []
        for j in train:
            if j == s or fl[j] != fl[s]:
                continue
            ang = float(np.degrees(np.arccos(np.clip(axis[s] @ axis[j], -1.0, 1.0))))
            if ang >= R["max_view_angle_deg"]:
                continue
            ov = None
            if nmvs[s] >= R["min_overlap_points"]:
                u, v, z = V.project(f"{j}.jpg", pts[s])
                ins = (z > 0) & (u >= 0) & (u < M.W) & (v >= 0) & (v < M.H)
                ov = float(ins.mean())
            cand.append((j, ang, ov))
        ok = [c for c in cand if c[2] is not None and c[2] > 0]
        if not ok:
            no_pair.append(dict(view=s, flight=fl[s], candidates_same_flight_under_20deg=len(cand), mvs_points=nmvs[s],
                                why="no candidate" if not cand else ("too few MVS points for the overlap" if nmvs[s] < R["min_overlap_points"] else "zero overlap")))
            rows.append(dict(view=s, flight=fl[s], pair=None, angle_deg=None, overlap=None, candidates=len(cand), mvs_points=nmvs[s]))
            continue
        best = min(ok, key=lambda c: (abs(c[2] - R["target_overlap"]), c[1], c[0]))
        rows.append(dict(view=s, flight=fl[s], pair=best[0], angle_deg=round(best[1], 3), overlap=round(best[2], 4), candidates=len(ok), mvs_points=nmvs[s]))
    ov = np.array([r["overlap"] for r in rows if r["pair"]])
    an = np.array([r["angle_deg"] for r in rows if r["pair"]])
    fls = sorted({fl[s] for s in train})
    out = dict(site=site, rule=R, training_views=len(train), paired=int(len(ov)), without_pair=len(no_pair), without_pair_views=no_pair,
               mvs_maps_equal_between_priors=f"{same_mvs}/{len(train)}",
               overlap_quantiles_5_25_50_75_95=np.percentile(ov, [5, 25, 50, 75, 95]).round(4).tolist() if len(ov) else None,
               angle_quantiles_5_50_95=np.percentile(an, [5, 50, 95]).round(3).tolist() if len(an) else None,
               flights_of_training_views={str(f): int(sum(1 for s in train if fl[s] == f)) for f in fls}, flight_table=table,
               pairs=rows, seconds=round(time.time() - t0, 1), scientific_verdict=None)
    M.jdump(M.SB / "prep/mvsfuse" / f"pairs_{site}.json", out)
    M.log(site, dict(views=len(train), paired=out["paired"], without_pair=len(no_pair), overlap=out["overlap_quantiles_5_25_50_75_95"],
                     angle=out["angle_quantiles_5_50_95"], same_mvs=out["mvs_maps_equal_between_priors"], s=out["seconds"]))


def flight_check():
    """the time rule against the DJI counter in the names (reference): gaps over 20 s, whether the counter goes on or restarts."""
    names = sorted(n.rsplit(".", 1)[0] for n in M.Views().names)
    rows, prev = [], None
    for s in names:
        t, i = M.capture_time(s), int(s.split("_")[2])
        if prev is not None:
            g = (t - prev[0]).total_seconds()
            if g > 20:
                rows.append(dict(at=s, gap_s=g, counter=[prev[1], i], counter_restarts=bool(i <= prev[1]), new_flight=bool(g > R["flight_gap_s"])))
        prev = (t, i)
    fl, table = M.flights()
    M.jdump(M.SB / "prep/mvsfuse/flights.json", dict(
        rule=R["flight"], flights=table, gaps_over_20s=rows,
        note="with 60 s every gap inside a run of the DJI counter (22, 48, 54, 59 s) stays inside a flight except one 90 s gap (counter 4 -> 26); "
             "three counter restarts after 10, 24 and 37 s fall inside a flight. The order says the capture time decides (6.5 '영상'); the pair "
             "rule's view-angle limit separates the camera directions anyway",
        scientific_verdict=None))


if __name__ == "__main__":
    for a in sys.argv[1:]:
        main(a)
    flight_check()
