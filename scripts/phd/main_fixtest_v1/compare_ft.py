"""PHD-MAIN-FIXTEST-v1 6.4: comparison of the GPU checks (jointbuildgs:dev, CPU; run_cpu_ft.sh; reads /out/checks and the stage-1 region
files). Stage 2's machinery (every array of monitor/{locations, init_points, unplanted, gate_check}.npz and the decision numbers of
init_report.json for the dry inits; every array of probe.npz and the numbers of probe.json for the probes; each difference classified
against the expected set written below BEFORE any comparison was run -> 'expected' or 'UNEXPECTED') plus deep checks per fix.

What must hold:
  r16 default vs r15: nothing differs but the r16 records (dry and probe).
  fix A vs r16 default: at the initialisation nothing but the records; at the fixed checkpoint only the pixels the depth term pulls
    change, and they are exactly the pixels with g_p > 0 and w_p < |D - P| <= tau_p (wtau); protection, density exemption, reset
    exemption, prune candidates, E and the MVS term are equal.
  fix B vs r16 default: patch states, votes, E, the initial geometry and the confidence / patch / mark maps are equal; judgments change
    only on missing patches, only from conflict (0) or mixed (2), only to agree (1); planted changes only False -> True and only on points
    of missing patches whose previous judgment was conflict; g_p changes only 0 -> 1 and exactly at the pixels of those patches; at the
    fixed checkpoint the protection changes only on Gaussians sitting on missing patches (and is only added), the depth-term pixels change
    only inside missing patches; prune candidates, E and the MVS term are equal.
  fix A + B: the Gaussian decisions equal fix B's; the pixels that change contain those of A and of B and lie inside wtau or the missing
    pixels (the rest, if any, is recorded as the interaction).
  python compare_ft.py dry|probe      -> /out/checks/compare_<kind>.json, .md
scientific_verdict: null."""
import json
import sys
from pathlib import Path

import numpy as np

D = Path("/out/checks")
S1 = Path("/s1")
UNITS6 = [("B0_b10", "LoD2"), ("B0_b10", "ALS"), ("B173nb_b10", "LoD2"), ("B173nb_b10", "ALS"), ("R1rep_b10", "LoD2"), ("R1rep_b10", "ALS")]
AB_UNITS = [("B173nb_b10", "ALS"), ("R1rep_b10", "ALS")]
NPZ = ("locations", "init_points", "unplanted", "gate_check")
SKIP_REPORT = {"seconds", "init_seconds", "prop_seconds", "revision", "ablations", "store", "orientation"}
REC16 = {"report:fixes", "report:prior_width", "report:own_depth"}
EXPECTED_DRY = {
    "r16d": set(REC16),
    "r16A": set(REC16),
    "r16B": REC16 | {"locations:judgment", "locations:unit_judgment", "locations:why", "locations:judgment_before_own_depth", "locations:own_depth_changed",
                     "init_points:judgment", "init_points:unit_judgment", "init_points:planted", "init_points:reason", "unplanted:", "gate_check:J",
                     "gate_check:J_loc", "gate_check:g_", "report:init", "report:first_E", "report:protection", "report:prior_weight",
                     "report:reread_method_vs_product_E", "report:prior_term.n_prior_now", "report:reread_test"},
}
EXPECTED_DRY["r16AB"] = EXPECTED_DRY["r16B"] | EXPECTED_DRY["r16A"]
EXPECTED_DRY["r16AT"] = EXPECTED_DRY["r16A"]
PROBE_REC = {"json:fixes", "json:no_floor"}        # records only (no_floor: added to the probe at 10:5x for the NF check)
EXPECTED_PROBE = {
    "r16d": set(PROBE_REC),
    "r16A": PROBE_REC | {"probe:on_", "probe:grad_abs_sum", "probe:prior_loss", "probe:wtau_", "json:depth_term", "json:loss_sums.prior"},
    "r16B": PROBE_REC | {"probe:on_", "probe:grad_abs_sum", "probe:prior_loss", "probe:miss_", "probe:lock", "probe:dens", "probe:reset_ex", "probe:conflict",
                         "probe:init_id", "probe:g_Jl", "json:depth_term", "json:loss_sums.prior", "json:decisions", "json:re_read.n_locked",
                         "json:re_read.n_conflict_excluded", "json:checkpoint"},
}
EXPECTED_PROBE["r16AB"] = EXPECTED_PROBE["r16A"] | EXPECTED_PROBE["r16B"]
EXPECTED_PROBE["r16AT"] = EXPECTED_PROBE["r16A"]
# fix B at a re-read protects Gaussians on missing patches and applies the opacity floor to them: the render of that iteration changes a
# little (the MVS term, the prune candidates by opacity, the pixel masks that read the render). Written after the first comparison
# (10-20 10:5x): the clean check is the pair without the floor (NF), where these must not change.
EXPECTED_PROBE["r16B"] |= {"probe:gw_", "probe:gthi_", "probe:mvs_loss", "probe:prune_cand", "json:loss_sums.mvs"}
EXPECTED_PROBE["r16AB"] |= {"probe:gw_", "probe:gthi_", "probe:mvs_loss", "probe:prune_cand", "json:loss_sums.mvs"}
EXPECTED_PROBE["r16BNF"] = EXPECTED_PROBE["r16B"] - {"probe:gthi_", "probe:mvs_loss", "probe:prune_cand", "json:loss_sums.mvs"} | {"json:no_floor"}


def jdump(p, o):
    Path(p).write_text(json.dumps(o, indent=1, default=lambda x: x.item() if hasattr(x, "item") else str(x)))


def flat(d, p=""):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            if k in SKIP_REPORT:
                continue
            out.update(flat(v, f"{p}.{k}" if p else k))
    else:
        out[p] = d
    return out


def cmp_npz(a, b, name):
    res = {}
    za, zb = np.load(a, allow_pickle=False), np.load(b, allow_pickle=False)
    for k in sorted(set(za.files) | set(zb.files)):
        if k not in za.files or k not in zb.files:
            res[f"{name}:{k}"] = "missing in one"
            continue
        x, y = za[k], zb[k]
        if x.shape != y.shape:
            res[f"{name}:{k}"] = f"shape {x.shape} vs {y.shape}"
            continue
        eq = (x == y) | (np.isnan(x) & np.isnan(y)) if x.dtype.kind == "f" else (x == y)
        nd = int((~eq).sum())
        if nd:
            res[f"{name}:{k}"] = nd
    return res


def cmp_json(fa, fb, prefix):
    res = {}
    for k in sorted(set(fa) | set(fb)):
        va, vb = fa.get(k, "<none>"), fb.get(k, "<none>")
        if json.dumps(va, sort_keys=True, default=str) != json.dumps(vb, sort_keys=True, default=str):
            res[f"{prefix}:{k}"] = dict(a=va, b=vb) if not isinstance(va, (list, dict)) else "differs"
    return res


REC_SUFFIX = (".w_lt_tau_px", ".missing_px", ".missing_px_g1")      # r16 per-view record counts of init_report.prior_weight (records only)


def classify(diff, expected):
    return {k: dict(diff=v, status="expected" if (any(k.startswith(e) for e in expected) or k.endswith(REC_SUFFIX)) else "UNEXPECTED")
            for k, v in diff.items()}


def pair_result(a, b, c):
    return dict(a=a, b=b, n_differences=len(c), unexpected=[k for k, v in c.items() if v["status"] == "UNEXPECTED"], differences=c)


# --------------------------------------------------------------------------------------------------------- dry
def dry_pair(a, b, expected):
    A, B = D / "dry" / a / "model/monitor", D / "dry" / b / "model/monitor"
    diff = {}
    for n in NPZ:
        if (A / f"{n}.npz").exists() or (B / f"{n}.npz").exists():
            diff.update(cmp_npz(A / f"{n}.npz", B / f"{n}.npz", n))
    diff.update(cmp_json(flat(json.loads((A / "init_report.json").read_text())), flat(json.loads((B / "init_report.json").read_text())), "report"))
    return pair_result(a, b, classify(diff, expected))


def region(site, prior):
    return np.load(S1 / "regions_v3" / f"regions_ext_v3_{site}_{prior}.npz")


def deep_dry_B(a, b, site, prior):
    """a = r16 default, b = fix B (or A + B)."""
    M = lambda t: D / "dry" / t / "model/monitor"
    La, Lb = np.load(M(a) / "locations.npz"), np.load(M(b) / "locations.npz")
    st = La["state"]
    jb = Lb["judgment_before_own_depth"]; chg = Lb["own_depth_changed"]
    e = dict(states_equal=bool(np.array_equal(La["state"], Lb["state"])), E_equal=bool(np.array_equal(La["E"], Lb["E"])),
             votes_equal=bool(np.array_equal(La["vote"], Lb["vote"])), before_equals_default=bool(np.array_equal(jb, La["judgment"])))
    dj = La["judgment"] != Lb["judgment"]
    e["judgment"] = dict(changed=int(dj.sum()), changed_not_missing=int((dj & (st != 2)).sum()), changed_not_from_conflict_or_mixed=int((dj & ~np.isin(La["judgment"], (0, 2))).sum()),
                         changed_not_to_agree=int((dj & (Lb["judgment"] != 1)).sum()), equals_record=bool(np.array_equal(dj, chg)),
                         from_conflict=int((dj & (La["judgment"] == 0)).sum()), from_mixed=int((dj & (La["judgment"] == 2)).sum()),
                         left_conflict_or_mixed_on_missing=int(((st == 2) & np.isin(Lb["judgment"], (0, 2))).sum()))
    du = La["unit_judgment"] != Lb["unit_judgment"]
    e["unit_judgment"] = dict(changed=int(du.sum()), changed_not_missing=int((du & (st != 2)).sum()), changed_not_to_agree=int((du & (Lb["unit_judgment"] != 1)).sum()))
    Ia, Ib = np.load(M(a) / "init_points.npz"), np.load(M(b) / "init_points.npz")
    geo = {k: bool(np.array_equal(Ia[k], Ib[k])) for k in ("xyz", "origin", "seat", "surface", "location", "state", "E_first", "category")}
    e["init_geometry_equal"] = geo
    dp = Ia["planted"] != Ib["planted"]
    cand = (Ia["state"] == 2) & (Ia["judgment"] == 0)
    e["planted"] = dict(changed=int(dp.sum()), false_to_true=int((~Ia["planted"] & Ib["planted"]).sum()), changed_not_missing_conflict=int((dp & ~cand).sum()),
                        all_missing_conflict_now_planted=bool(Ib["planted"][cand].all()))
    Ga, Gb = np.load(M(a) / "gate_check.npz"), np.load(M(b) / "gate_check.npz")
    z1 = o1 = maps_changed = not_on_target = target_unchanged = 0
    for k in Ga.files:
        if k.startswith("g_"):
            nm = k[2:]
            lm = Ga[f"lm_{nm}"].astype(np.int64)
            loc_ok = lm >= 0
            tgt = np.zeros(lm.shape, bool)
            tgt[loc_ok] = (st[lm[loc_ok]] == 2) & (jb[lm[loc_ok]] == 0)
            ch = Ga[k] != Gb[k]
            z1 += int((~Ga[k] & Gb[k]).sum()); o1 += int((Ga[k] & ~Gb[k]).sum())
            not_on_target += int((ch & ~tgt).sum()); target_unchanged += int((tgt & ~ch).sum())
        elif k.startswith(("A_", "lm_", "mk_")) and not np.array_equal(Ga[k], Gb[k]):
            maps_changed += 1
    e["g_p"] = dict(zero_to_one=z1, one_to_zero=o1, changed_outside_target=not_on_target, target_unchanged=target_unchanged,
                    target="pixels whose patch is missing with a previous judgment conflict")
    e["maps_changed"] = maps_changed
    ra, rb = flat(json.loads((M(a) / "init_report.json").read_text())), flat(json.loads((M(b) / "init_report.json").read_text()))
    e["n_locked_first"] = [ra.get("first_E.n_locked"), rb.get("first_E.n_locked")]
    e["n_dropped_conflict"] = [ra.get("init.n_dropped_conflict"), rb.get("init.n_dropped_conflict")]
    # against the fill task's table 2 (evaluation range, region codes 4 / 13)
    G = region(site, prior)
    same_rows = len(G["state"]) == len(st) and bool(np.array_equal(G["state"], st))
    t2 = dict(region_rows_equal_patches=same_rows)
    if same_rows:
        code = G["code_ext_v3"]; ev = G["in_eval"].astype(bool)
        fc, fm = chg & (jb == 0), chg & (jb == 2)
        t2.update(eval_conflict_code4=int((fc & ev & (code == 4)).sum()), eval_conflict_code13=int((fc & ev & (code == 13)).sum()),
                  eval_conflict_other=int((fc & ev & ~np.isin(code, (4, 13))).sum()), eval_mixed_code4=int((fm & ev & (code == 4)).sum()),
                  eval_mixed_code13=int((fm & ev & (code == 13)).sum()), eval_mixed_other=int((fm & ev & ~np.isin(code, (4, 13))).sum()),
                  unit_conflict=int(fc.sum()), unit_mixed=int(fm.sum()), unit_changed_area_m2=float(np.asarray(La["area"])[chg].sum()),
                  eval_changed_area_m2=float(np.asarray(La["area"])[chg & ev].sum()))
    e["table2"] = t2
    e["ok"] = (e["states_equal"] and e["E_equal"] and e["votes_equal"] and e["before_equals_default"] and e["judgment"]["changed_not_missing"] == 0
               and e["judgment"]["changed_not_from_conflict_or_mixed"] == 0 and e["judgment"]["changed_not_to_agree"] == 0 and e["judgment"]["equals_record"]
               and e["judgment"]["left_conflict_or_mixed_on_missing"] == 0 and e["unit_judgment"]["changed_not_missing"] == 0
               and e["unit_judgment"]["changed_not_to_agree"] == 0 and all(geo.values()) and e["planted"]["changed"] == e["planted"]["false_to_true"]
               and e["planted"]["changed_not_missing_conflict"] == 0 and e["planted"]["all_missing_conflict_now_planted"] and o1 == 0
               and not_on_target == 0 and target_unchanged == 0 and maps_changed == 0)
    return e


def dry():
    out = dict(pairs=[], deep_B={}, missing=[])
    for s, p in UNITS6:
        base = f"r16d_{s}_{p}"
        for a_, b_, v in ((f"r15_{s}_{p}", base, "r16d"), (base, f"r16B_{s}_{p}", "r16B"), (base, f"r16A_{s}_{p}", "r16A"), (base, f"r16AT_{s}_{p}", "r16AT"),
                          (base, f"r16AB_{s}_{p}", "r16AB")):
            if not ((D / "dry" / a_ / "model/monitor/init_report.json").exists() and (D / "dry" / b_ / "model/monitor/init_report.json").exists()):
                out["missing"].append(b_)
                continue
            out["pairs"].append(dict(var=v, site=s, prior=p, **dry_pair(a_, b_, EXPECTED_DRY[v])))
            if v in ("r16B", "r16AB"):
                out["deep_B"][f"{v}/{s}/{p}"] = deep_dry_B(a_, b_, s, p)
    jdump(D / "compare_dry.json", dict(rule=__doc__.split("\n\n")[1], **out, scientific_verdict=None))
    md = ["| 비교 | 경우 | 다른 배열·값 | 예상 밖 | 깊은 점검 |", "|---|---|---|---|---|"]
    for e in out["pairs"]:
        deep = out["deep_B"].get(f"{e['var']}/{e['site']}/{e['prior']}")
        dtxt = "—"
        if deep:
            t2 = deep["table2"]
            dtxt = (f"{'통과' if deep['ok'] else '실패'}: 결측 판정 바뀜 {deep['judgment']['changed']:,} (충돌 {deep['judgment']['from_conflict']:,}, 섞임 "
                    f"{deep['judgment']['from_mixed']:,}), 더 심는 점 {deep['planted']['false_to_true']:,}, g_p 0→1 {deep['g_p']['zero_to_one']:,}화소, "
                    f"첫 보호 {deep['n_locked_first'][0]}→{deep['n_locked_first'][1]}; 평가 범위 충돌 코드 4·13 = {t2.get('eval_conflict_code4')}·{t2.get('eval_conflict_code13')}, "
                    f"섞임 코드 4·13 = {t2.get('eval_mixed_code4')}·{t2.get('eval_mixed_code13')}")
        md.append(f"| {e['b']} ↔ {e['a']} | {e['site']} {e['prior']} | {e['n_differences']} | {', '.join(e['unexpected']) or '없음'} | {dtxt} |")
    (D / "compare_dry.md").write_text("\n".join(md) + "\n")
    print("dry compare", json.dumps({e["b"]: (e["n_differences"], len(e["unexpected"])) for e in out["pairs"]}),
          json.dumps({k: v["ok"] for k, v in out["deep_B"].items()}), "missing", out["missing"])


# ------------------------------------------------------------------------------------------------------- probe
def unpack(z, key, shape):
    return np.unpackbits(z[key])[: shape[0] * shape[1]].reshape(shape).astype(bool)


def probe_pair(a, b, expected):
    A, B = D / "probe" / a / "probe", D / "probe" / b / "probe"
    diff = cmp_npz(A / "probe.npz", B / "probe.npz", "probe")
    ja, jb = flat(json.loads((A / "probe.json").read_text())), flat(json.loads((B / "probe.json").read_text()))
    for k in ("ply", "ref_init"):
        ja.pop(k, None); jb.pop(k, None)
    diff.update(cmp_json(ja, jb, "json"))
    return pair_result(a, b, classify(diff, expected))


def deep_probe(a, b, kind, shape=(741, 1024)):
    """a = r16 default probe, b = the fix's probe. kind 'A', 'B' or 'AB'."""
    Pa, Pb = np.load(D / "probe" / a / "probe/probe.npz"), np.load(D / "probe" / b / "probe/probe.npz")
    views = [str(v) for v in Pa["views"]]
    e = dict(E_equal=bool(np.array_equal(Pa["E"], Pb["E"])), prior_equal=bool(np.array_equal(Pa["prior"], Pb["prior"])),
             prune_cand_equal=bool(np.array_equal(Pa["prune_cand"], Pb["prune_cand"])), mvs_loss_equal=bool(np.array_equal(Pa["mvs_loss"], Pb["mvs_loss"])),
             g_state_equal=bool(np.array_equal(Pa["g_state"], Pb["g_state"])), g_loc_equal=bool(np.array_equal(Pa["g_loc"], Pb["g_loc"])))
    added, removed = ~Pa["lock"] & Pb["lock"], Pa["lock"] & ~Pb["lock"]
    on_miss_patch = Pa["g_state"] == 2
    e["lock"] = dict(added=int(added.sum()), removed=int(removed.sum()), changed_not_on_missing=int(((added | removed) & ~on_miss_patch).sum()))
    e["dens_equals_lock_change"] = bool(np.array_equal(Pa["dens"] != Pb["dens"], Pa["lock"] != Pb["lock"]))
    e["reset_ex_change_equals_lock_change"] = bool(np.array_equal(Pa["reset_ex"] != Pb["reset_ex"], Pa["lock"] != Pb["lock"]))
    tot = dict(newly_on=0, newly_off=0, newly_on_in_wtau=0, wtau=0, wtau_not_on=0, newly_on_outside_target=0, newly_on_miss=0, newly_on_miss_truncation=0,
               newly_on_miss_judgment=0)
    for v in views:
        oa, ob = unpack(Pa, f"on_{v}", shape), unpack(Pb, f"on_{v}", shape)
        new_on, new_off = ob & ~oa, oa & ~ob
        tot["newly_on"] += int(new_on.sum()); tot["newly_off"] += int(new_off.sum())
        tgt = np.zeros(shape, bool)
        if "A" in kind:
            wt = unpack(Pb, f"wtau_{v}", shape)
            tot["wtau"] += int(wt.sum()); tot["newly_on_in_wtau"] += int((new_on & wt).sum()); tot["wtau_not_on"] += int((wt & ~ob).sum())
            tgt |= wt
        if "B" in kind:
            ms = unpack(Pb, f"miss_{v}", shape)
            gw_a, gthi = unpack(Pa, f"gw_{v}", shape), unpack(Pa, f"gthi_{v}", shape)
            tot["newly_on_miss"] += int((new_on & ms).sum())
            tot["newly_on_miss_truncation"] += int((new_on & ms & gw_a & gthi).sum())
            tot["newly_on_miss_judgment"] += int((new_on & ms & ~gw_a).sum())
            tgt |= ms
        tot["newly_on_outside_target"] += int((new_on & ~tgt).sum())
    e["pixels"] = tot
    ok = (e["E_equal"] and e["prior_equal"] and e["prune_cand_equal"] and e["mvs_loss_equal"] and e["g_state_equal"] and e["g_loc_equal"]
          and tot["newly_off"] == 0 and tot["newly_on_outside_target"] == 0)
    if kind in ("A", "AT"):
        ok = ok and e["lock"]["added"] == 0 and e["lock"]["removed"] == 0 and bool(np.array_equal(Pa["dens"], Pb["dens"]))
    else:
        ok = ok and e["lock"]["removed"] == 0 and e["lock"]["changed_not_on_missing"] == 0 and e["dens_equals_lock_change"]
    e["ok"] = bool(ok)
    return e


def probe():
    out = dict(pairs=[], deep={}, missing=[], ab_union={})
    for s, p in UNITS6:
        base = f"r16d_{s}_{p}_s0"
        for a_, b_, v in ((f"r15_{s}_{p}_s0", base, "r16d"), (base, f"r16B_{s}_{p}_s0", "r16B"), (base, f"r16A_{s}_{p}_s0", "r16A"),
                          (base, f"r16AT_{s}_{p}_s0", "r16AT"), (base, f"r16AB_{s}_{p}_s0", "r16AB")):
            if not ((D / "probe" / a_ / "probe/probe.json").exists() and (D / "probe" / b_ / "probe/probe.json").exists()):
                out["missing"].append(b_)
                continue
            out["pairs"].append(dict(var=v, site=s, prior=p, **probe_pair(a_, b_, EXPECTED_PROBE[v])))
            if v != "r16d":
                out["deep"][f"{v}/{s}/{p}"] = deep_probe(a_, b_, v[3:])
        a_, b_ = f"r16dNF_{s}_{p}_s0", f"r16BNF_{s}_{p}_s0"
        if (D / "probe" / a_ / "probe/probe.json").exists() and (D / "probe" / b_ / "probe/probe.json").exists():
            out["pairs"].append(dict(var="r16BNF", site=s, prior=p, **probe_pair(a_, b_, EXPECTED_PROBE["r16BNF"])))
            out["deep"][f"r16BNF/{s}/{p}"] = deep_probe(a_, b_, "B")
        if (s, p) in AB_UNITS and all((D / "probe" / f"{x}_{s}_{p}_s0/probe/probe.npz").exists() for x in ("r16d", "r16A", "r16B", "r16AB")):
            Z = {x: np.load(D / "probe" / f"{x}_{s}_{p}_s0/probe/probe.npz") for x in ("r16d", "r16A", "r16B", "r16AB")}
            sh = (741, 1024)
            u = dict(lock_equals_B=bool(np.array_equal(Z["r16AB"]["lock"], Z["r16B"]["lock"])), contains_A_and_B=0, extra_beyond_union=0, union=0)
            for vv in [str(v) for v in Z["r16d"]["views"]]:
                o = {x: unpack(Z[x], f"on_{vv}", sh) for x in Z}
                nA, nB, nAB = o["r16A"] & ~o["r16d"], o["r16B"] & ~o["r16d"], o["r16AB"] & ~o["r16d"]
                un = nA | nB
                u["union"] += int(un.sum()); u["contains_A_and_B"] += int((un & ~nAB).sum()); u["extra_beyond_union"] += int((nAB & ~un).sum())
            u["note"] = "contains_A_and_B = union pixels NOT newly pulled by A + B (must be 0); extra_beyond_union = newly pulled only when both are on (interaction)"
            out["ab_union"][f"{s}/{p}"] = u
    jdump(D / "compare_probe.json", dict(rule=__doc__.split("\n\n")[1], **out, scientific_verdict=None))
    md = ["| 비교 | 경우 | 다른 배열·값 | 예상 밖 | 깊은 점검 |", "|---|---|---|---|---|"]
    for e in out["pairs"]:
        dp = out["deep"].get(f"{e['var']}/{e['site']}/{e['prior']}")
        dtxt = "—"
        if dp:
            px = dp["pixels"]
            dtxt = (f"{'통과' if dp['ok'] else '실패'}: 새로 당기는 화소 {px['newly_on']:,} (놓인 화소 {px['newly_off']:,}), 대상 밖 {px['newly_on_outside_target']:,}; "
                    f"보호 +{dp['lock']['added']:,}/−{dp['lock']['removed']:,} (결측 밖 {dp['lock']['changed_not_on_missing']:,}); E 같음 {dp['E_equal']}")
            if "A" in e["var"]:
                dtxt += f"; w~τ 일치 화소 {px['wtau']:,} 가운데 당김 {px['newly_on_in_wtau']:,}"
            if "B" in e["var"]:
                dtxt += f"; 결측 화소 새로 당김 {px['newly_on_miss']:,} (절단 풀림 {px['newly_on_miss_truncation']:,}, 판정 읽기 {px['newly_on_miss_judgment']:,})"
        md.append(f"| {e['b']} ↔ {e['a']} | {e['site']} {e['prior']} | {e['n_differences']} | {', '.join(e['unexpected']) or '없음'} | {dtxt} |")
    for k, u in out["ab_union"].items():
        md.append(f"| 함께 켠 판 = A ∪ B ? | {k} | — | — | 보호 = 판 B {u['lock_equals_B']}; A·B 합 {u['union']:,}화소 가운데 빠진 것 {u['contains_A_and_B']:,}; 둘을 함께 켤 때만 당김 {u['extra_beyond_union']:,} |")
    (D / "compare_probe.md").write_text("\n".join(md) + "\n")
    print("probe compare", json.dumps({e["b"]: (e["n_differences"], len(e["unexpected"])) for e in out["pairs"]}),
          json.dumps({k: v["ok"] for k, v in out["deep"].items()}), "missing", out["missing"])


if __name__ == "__main__":
    {"dry": dry, "probe": probe}[sys.argv[1]]()
