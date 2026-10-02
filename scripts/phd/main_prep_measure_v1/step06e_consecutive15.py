"""PHD-MAIN-PREP-MEASURE-v1 step 06e (jointbuildgs:dev, CPU): consecutive-15 candidates of a box (5.5).

  python step06e_consecutive15.py select <box> [--band 10]
  python step06e_consecutive15.py share <box> --mvs <workspace under /out> --list <json under /out>

select: per training candidate of the box (band b10, sorted by name), LoD2 building-face pixels of the evaluation range and
        how many of them are confidence 1 on the current MVS; the window of 15 consecutive images with the largest share,
        every image seeing >= 5,000 evaluation building-face pixels (config boxes.consecutive_15_detail). Writes
        step06/consecutive15_<box>.json and mvs_lists/c15_<box>_train.json (13 training images; positions 0 and 8 = evaluation).
share:  the mask-1 share of the evaluation range on another MVS (the 13-image rebuild) for the listed views.
scientific_verdict: null."""
import json
import sys

import numpy as np

from common import CFG, DENSE, OUT, Views, jdump, read_depth_bin, xy_to_uv
import step03_stage1 as s3


def eval_counts(box, views, mvs_dir, V):
    R = json.loads((OUT / "step06/box_ranges.json").read_text())
    rid = f"{box}_b10" if f"{box}_b10" in R else f"{box}_b0"
    r = R[rid]
    pr = s3.Prior(OUT / "step06/mesh" / rid, "LoD2")
    summ = json.loads((OUT / "step06/stage1" / rid / "LoD2" / "summary.json").read_text())
    pr.shift = np.asarray(summ["registration"]["shift_applied"], float)
    sc, _ = pr.scene()
    out = []
    for n in views:
        Dr = V.rays(n); C = V.C(n)
        t, tri = sc.cast(C, Dr)
        hit = tri >= 0
        X = C[None, None, :] + np.where(hit, t, 0)[..., None] * Dr.astype(np.float64)
        uv = xy_to_uv(X[..., :2].reshape(-1, 2)).reshape(X.shape[0], X.shape[1], 2)
        ev = hit & (uv[..., 0] >= r["eval_u"][0]) & (uv[..., 0] <= r["eval_u"][1]) & (uv[..., 1] >= r["eval_v"][0]) & (uv[..., 1] <= r["eval_v"][1])
        p = mvs_dir / "stereo/depth_maps" / f"{n}.geometric.bin"
        a1 = np.zeros_like(ev)
        if p.exists():
            d = read_depth_bin(p); a1 = np.isfinite(d) & (d > 0)
        out.append(dict(view=n, eval_px=int(ev.sum()), eval_a1=int((ev & a1).sum())))
    return rid, out


def main():
    mode, box = sys.argv[1], sys.argv[2]
    V = Views()
    if mode == "select":
        BV = json.loads((OUT / "step06/box_views.json").read_text())["views"]
        rid = f"{box}_b10"
        views = sorted(BV[rid]["train"])
        _, cnt = eval_counts(box, views, DENSE, V)
        guard = 5000
        best = None; scores = []
        for i in range(0, len(cnt) - 14):
            w = cnt[i:i + 15]
            if min(c["eval_px"] for c in w) < guard:
                continue
            sh = sum(c["eval_a1"] for c in w) / max(sum(c["eval_px"] for c in w), 1)
            scores.append((sh, i))
            if best is None or sh > best[0]:
                best = (sh, i)
        res = dict(task_id="PHD-MAIN-PREP-MEASURE-v1", box=box, band_views=rid, candidates=len(views), windows_ok=len(scores),
                   rule=CFG["boxes"]["consecutive_15_detail"], per_view=cnt, scientific_verdict=None)
        if best:
            w = cnt[best[1]:best[1] + 15]
            names = [c["view"] for c in w]
            test = [names[0], names[8]]; train = [n for k, n in enumerate(names) if k not in (0, 8)]
            res.update(window_start=best[1], views=names, test=test, train=train, share_current_mvs=best[0],
                       share_current_mvs_train13=sum(c["eval_a1"] for c in w if c["view"] in train) / max(sum(c["eval_px"] for c in w if c["view"] in train), 1),
                       share_distribution_of_windows=dict(p50=float(np.median([s for s, _ in scores])), max=best[0], min=float(min(s for s, _ in scores))))
            (OUT / "mvs_lists").mkdir(exist_ok=True)
            (OUT / f"mvs_lists/c15_{box}_train.json").write_text(json.dumps(train))
        jdump(OUT / f"step06/consecutive15_{box}.json", res)
        print("c15", box, res.get("window_start"), res.get("share_current_mvs"), res.get("views", [])[:2])
    else:
        mvs = OUT / sys.argv[sys.argv.index("--mvs") + 1]; lst = json.loads((OUT / sys.argv[sys.argv.index("--list") + 1]).read_text())
        rid, cnt = eval_counts(box, lst, mvs, V)
        p = OUT / f"step06/consecutive15_{box}.json"; res = json.loads(p.read_text())
        res["share_rebuilt_13"] = sum(c["eval_a1"] for c in cnt) / max(sum(c["eval_px"] for c in cnt), 1)
        res["rebuilt_per_view"] = cnt; res["rebuilt_mvs"] = str(mvs)
        jdump(p, res)
        print("c15 share rebuilt", box, res["share_rebuilt_13"])


if __name__ == "__main__":
    main()
