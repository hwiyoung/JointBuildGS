"""PHD-MAIN-UNCERT-v1 table helpers: the per-patch values of a ring radius (patch_values) as one store, statistics with their samples,
md/json writers. Values in cm unless named otherwise. scientific_verdict: null."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/repo/scripts/phd/main_uncert_v1")
import uc_common as U  # noqa: E402

MINP = U.CFG["tables"]["min_patches"]
DATAS = {"LoD2": ("mvs_a", "mvs_b"), "ALS": ("mvs_a", "mvs_b", "als")}


class Store:
    def __init__(self, R):
        self.R = R
        self._c = {}

    def get(self, site, pset):
        k = (site, pset)
        if k not in self._c:
            with np.load(U.PV / f"{site}__{pset}__R{self.R}.npz", allow_pickle=False) as z:
                self._c[k] = {kk: z[kk] for kk in z.files}
        return self._c[k]

    def pooled(self, pset, sites=U.SITES):
        """the patch arrays of several sites concatenated (a 'site' array added)."""
        parts = [self.get(s, pset) for s in sites]
        keys = set.intersection(*[set(p) for p in parts])
        out = {k: np.concatenate([p[k] for p in parts]) for k in keys if parts[0][k].ndim >= 1 and len(parts[0][k]) == len(parts[0]["centre"])}
        out["site"] = np.concatenate([np.full(len(p["centre"]), s) for s, p in zip(sites, parts)])
        return out


def units(site_or_pool, pset):
    """(label, site list) of the case rows and the pooled row of a prior."""
    return [(U.case_ko(s, pset), [s]) for s in U.SITES] + [(f"세 지역 합 · {U.PRIOR_KO[pset]}", list(U.SITES))]


def val(z, d, f):
    """values of field f of data d where the data has a value (status 0), else NaN (float64)."""
    return np.where(z[f"{d}_status"] == 0, z[f"{d}_{f}"], np.nan).astype(np.float64)


def has(z, d):
    return z[f"{d}_status"] == 0


def ev(z):
    return z["in_eval"].astype(bool)


def q(x, p):
    x = np.asarray(x, np.float64)
    x = x[np.isfinite(x)]
    return float(np.quantile(x, p)) if len(x) else None


def med(x):
    return q(x, 0.5)


def nmad(x):
    x = np.asarray(x, np.float64)
    x = x[np.isfinite(x)]
    if not len(x):
        return None
    m = np.median(x)
    return float(1.4826 * np.median(np.abs(x - m)))


def spearman(a, b):
    from scipy.stats import spearmanr
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 3:
        return None, int(m.sum())
    r = spearmanr(a[m], b[m]).statistic
    return (float(r) if np.isfinite(r) else None), int(m.sum())


def auc(score, pos, neg):
    """Mann-Whitney AUC (ties half), and the false-positive share at the threshold catching half of the positives."""
    from scipy.stats import rankdata
    sp, sn = score[pos & np.isfinite(score)], score[neg & np.isfinite(score)]
    if len(sp) < 1 or len(sn) < 1:
        return dict(auc=None, n_pos=int(len(sp)), n_neg=int(len(sn)), fpr_half=None, thr_half_cm=None)
    r = rankdata(np.concatenate([sp, sn]))
    a = (r[:len(sp)].sum() - len(sp) * (len(sp) + 1) / 2) / (len(sp) * len(sn))
    thr = float(np.median(sp))
    return dict(auc=float(a), n_pos=int(len(sp)), n_neg=int(len(sn)), fpr_half=float(np.mean(sn >= thr)), thr_half_cm=100 * thr,
                excluded_pos_no_value=int((pos & ~np.isfinite(score)).sum()), excluded_neg_no_value=int((neg & ~np.isfinite(score)).sum()))


def roc_curve(score, pos, neg, n=101):
    sp, sn = score[pos & np.isfinite(score)], score[neg & np.isfinite(score)]
    if not len(sp) or not len(sn):
        return None
    thr = np.unique(np.quantile(np.concatenate([sp, sn]), np.linspace(0, 1, n)))[::-1]
    tpr = [float(np.mean(sp >= t)) for t in thr]
    fpr = [float(np.mean(sn >= t)) for t in thr]
    return dict(fpr=[0.0] + fpr + [1.0], tpr=[0.0] + tpr + [1.0])


def dist(x, area=None, mask=None, cm=True):
    """median, p25, p75, p90 of x (m -> cm) with the sample."""
    x = np.asarray(x, np.float64)
    m = np.isfinite(x) if mask is None else (mask & np.isfinite(x))
    k = 100.0 if cm else 1.0
    v = x[m] * k
    return dict(n=int(m.sum()), area_m2=float(area[m].sum()) if area is not None else None,
                p50=float(np.median(v)) if len(v) else None, p25=float(np.quantile(v, .25)) if len(v) else None,
                p75=float(np.quantile(v, .75)) if len(v) else None, p90=float(np.quantile(v, .9)) if len(v) else None)


# ------------------------------------------------------------------------------------------------ writing
def fmt(v, kind="v", n=None):
    if n is not None and n < MINP:
        return "표본 부족"
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "결과 없음"
    if kind == "rank":
        return f"{v:.2f}"
    if kind == "pct":
        return f"{100 * v:.1f} %"
    if kind == "int":
        return f"{int(v):,}"
    return f"{v:.1f}"


def md_table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] + ["---:"] * (len(head) - 1)) + "|"]
    out += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    return "\n".join(out)


def write(folder, name, title, md_body, js, note=None):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    txt = f"# {title}\n\n" + (f"{note}\n\n" if note else "") + md_body + "\n"
    (folder / f"{name}.md").write_text(txt)
    U.jdump(folder / f"{name}.json", dict(title=title, note=note, made=U.now(), config_sha256=U.sha256(U.CFGP), values=js, scientific_verdict=None))
    return txt


def face_masks(z):
    rl = z["roof_like"].astype(bool)
    return [("전체", np.ones(len(rl), bool)), ("지붕꼴", rl), ("벽꼴", ~rl)]


def cell_keys():
    return [("all", "전체")] + [(c, U.CELL_KO[c]) for c in U.CELLS] + [(k, v[0]) for k, v in U.SUMS.items()]
