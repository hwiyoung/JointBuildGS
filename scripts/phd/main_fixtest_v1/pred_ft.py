"""PHD-MAIN-FIXTEST-v1 10 (예측의 판정; jointbuildgs:dev, CPU; run_step_ft.sh). Each prediction of order 10 (written into the configuration
before training, predictions_verbatim) is judged from the tables of this task with one fixed rule, for the two readings of fix A apart:
  - a prediction that names a change in a direction is 맞음 when the value moved that way beyond the criterion (grade 확인 or
    가능·근거 불완전 of order 9.2), 틀림 when the reading is 같음 or the value moved the other way beyond the criterion, 판단 불가 when the
    result does not exist (gate, not trained), the samples are under 100 (표본 부족) or the part is about a case that was not trained;
  - a prediction that says 'within the criterion' is 맞음 when every named value reads 같음, 틀림 when one reads beyond the criterion
    (the values are listed);
  - the grade written beside 맞음 / 틀림 is the weakest grade among the values that decided it (samples under 10,000 cap it at
    가능·근거 불완전, as the tables do).
  - '폭이 좁아진 경우' (order 7): trained fix-A cases with w / tau < 0.8 (roof for LoD2), per reading, from prep/w_decision_<rd>.json.
  - R1 항공 LiDAR has w = tau in both readings; its one training (fixA_ALS_s0) stands for both readings.
Inputs: FT/tables/eval_ft.json (tables_ft.py), FT/tables/curve_ft.json (curve_ft.py), FT/mech/bands_<site>_<prior>_<rd>.json (band_w.py),
FT/mech/mech_b.json (mech_b.py).
  python pred_ft.py
Writes FT/tables/predictions_ft.json and predictions_ft.md. scientific_verdict: null."""
import json
import math
from pathlib import Path

PH = Path("/ph")
FTP = PH / "main_fixtest_v1/PHD-MAIN-FIXTEST-v1"
T = FTP / "tables"
CFG = json.loads(Path("/repo/configs/phd/main_fixtest_v1/fixtest_v1.json").read_text())
WD = {rd: json.loads((FTP / f"prep/w_decision_{rd}.json").read_text())["cases"] for rd in ("L", "T")}
CASES = [(s, p) for s in ("B0_b10", "B173nb_b10", "R1rep_b10") for p in ("LoD2", "ALS")]
SITE_KO = {"B0_b10": "B0", "B173nb_b10": "B173 주변", "R1rep_b10": "R1"}
PRIOR_KO = {"LoD2": "LoD2", "ALS": "항공 LiDAR"}
PLACE_KO = {"all": "전체", "c11": "사전 정보가 틀린 곳", "c11s": "조금 틀린 곳", "c2": "두 자료가 모두 맞는 곳", "img": "영상이 틀린 곳",
            "c4": "결측 영역", "c5": "비가시 영역"}
MKO = {"dist": "거리", "R_tau": "R(τ)", "R_0.2": "R(0.2 m)", "bias": "치우침", "infl11": "유입률(코드 11)", "infl13": "결측 유입률(코드 13)"}
GRADE_ORDER = {"확인": 2, "가능·근거 불완전": 1, "같음": 0}
NAMES = ("lt_w", "w_tau", "tau_2tau", "2tau_4tau", "ge_4tau")


def jl(p):
    p = Path(p)
    return json.loads(p.read_text()) if p.exists() else None


E = jl(T / "eval_ft.json")["cases"]
CURVE = (jl(T / "curve_ft.json") or {}).get("data", {})
MECHB = (jl(FTP / "mech/mech_b.json") or {}).get("cases", {})


def ck(site, prior):
    return f"{SITE_KO[site]} {PRIOR_KO[prior]}"


def acol(site, prior, rd):
    """the fix-A column of a reading; R1 항공 LiDAR's reading T is its reading-L training."""
    if rd == "T" and (site, prior) == ("R1rep_b10", "ALS"):
        return "A"
    return "A" if rd == "L" else "AT"


def a_trained(site, prior, rd):
    return bool(WD[rd][f"{site}/{prior}"]["train"])


def narrowed(site, prior, rd):
    return bool(WD[rd][f"{site}/{prior}"]["narrowed"])


def cell(site, prior, place, m, col):
    row = E[f"{site}/{prior}"]["places"][place].get(m)
    if row is None:
        return None
    x, r = row.get(col, {}), row.get(f"read_{col}", {})
    return dict(case=ck(site, prior), place=PLACE_KO[place], metric=MKO.get(m, m), col=col, value=x.get("v"), n=x.get("n"), status=x.get("status"),
                mean=row["mean"]["v"], s0=row["s0"]["v"], s1=row["s1"]["v"], grade=r.get("grade"), side=r.get("side"), diff=r.get("diff"),
                criterion=r.get("criterion"), refs={k: row.get(k, {}).get("v") for k in ("samepath", "nojudge", "trust", "ablband", "imgonly") if k in row})


def usable(c):
    return c is not None and c["status"] == "있음" and c["grade"] not in (None, "—", "표본 부족")


def change(c, want):
    """want: '나음' / '못함' / '위로' / '아래로' -> ('맞음'|'틀림'|'판단 불가', grade)."""
    if c is None or c["status"] != "있음":
        return "판단 불가", (c or {}).get("status") or "결과 없음"
    if c["grade"] in (None, "—"):
        return "판단 불가", "결과 없음"
    if c["grade"] == "표본 부족":
        return "판단 불가", "표본 부족"
    if c["grade"] == "같음":
        return "틀림", "같음"
    return ("맞음" if c["side"] == want else "틀림"), c["grade"]


def within(cells):
    used = [c for c in cells if usable(c)]
    if not used:
        return "판단 불가", "결과 없음", []
    beyond = [c for c in used if c["grade"] != "같음"]
    if beyond:
        g = max(beyond, key=lambda c: GRADE_ORDER[c["grade"]])["grade"]
        return "틀림", g, beyond
    return "맞음", "같음", []


def weakest(grades):
    gs = [g for g in grades if g in GRADE_ORDER]
    return min(gs, key=lambda g: GRADE_ORDER[g]) if gs else None


def combine(parts):
    """parts: list of (verdict, grade). 틀림 if any 틀림; 맞음 if every judged part is 맞음; else 판단 불가."""
    judged = [p for p in parts if p[0] != "판단 불가"]
    if not judged:
        return "판단 불가", None
    if any(p[0] == "틀림" for p in judged):
        return "틀림", weakest([p[1] for p in judged if p[0] == "틀림"]) or [p[1] for p in judged if p[0] == "틀림"][0]
    return "맞음", weakest([p[1] for p in judged])


def fmtc(c):
    if c is None:
        return "—"
    if c["status"] != "있음":
        return f"{c['case']} {c['place']} {c['metric']}: {c['status']}"
    def num(x, spec):
        return "—" if x is None else format(x, spec)
    v = c["value"]
    s = (f"{c['case']} {c['place']} {c['metric']} {num(v, '.2f')} (본 방법 평균 {num(c['mean'], '.2f')}, 차 {num(c['diff'], '+.2f')}, "
         f"기준 {num(c['criterion'], '.2f')}, {c['grade']}")
    return s + (f", {c['side']}" if c["grade"] not in ("같음", "표본 부족", "—", None) and c.get("side") else "") + \
        (f"; 표본 {c['n']:,})" if c.get("n") is not None else "; 표본 —)")


def short(c):
    if c is None:
        return "—"
    if c["status"] != "있음" or c["value"] is None or c["mean"] is None:
        return f"{c['case']} {c['place']} {c['metric']} {c['status'] or '결과 없음'}"
    return f"{c['case']} {c['place']} {c['metric']} {c['mean']:.1f}→{c['value']:.1f}" + ("*" if (c["n"] or 0) < 10000 else "")


def f1(x):
    return "—" if x is None else f"{x:.1f}"


GROUP_KO = {"wrong_release_c4": "잘못 놓았던 패치(코드 4)", "right_release_c13": "맞게 놓았던 패치(코드 13)"}


def none_or(cells, beyond):
    """evidence of a 'within' prediction: the values beyond the criterion, or the count read, or that nothing could be read."""
    n = sum(usable(c) for c in cells)
    if beyond:
        return [fmtc(c) for c in beyond]
    return [f"{n}개 값 모두 같음"] if n else ["읽을 값 없음(결과 없음)"]


def count_key(cells, beyond):
    used = [c for c in cells if usable(c)]
    if not used:
        return "읽을 값 없음"
    return f"{len(beyond)}/{len(used)}개 값이 기준 밖" + ("" if not beyond else ": " + "; ".join(short(c) for c in beyond[:3]) + (" 외" if len(beyond) > 3 else ""))


def pred_A(rd):
    out = {}
    trained = [(s, p) for s, p in CASES if a_trained(s, p, rd)]
    narrow = [(s, p) for s, p in trained if narrowed(s, p, rd)]
    wide = [(s, p) for s, p in trained if not narrowed(s, p, rd)]
    # A1
    parts, ev = [], []
    for s, p in narrow:
        if (s, p) == ("R1rep_b10", "ALS"):
            continue
        col = acol(s, p, rd)
        cd = cell(s, p, "c2", "dist", col)
        v1 = change(cd, "나음")
        cb = cell(s, p, "c2", "bias", col)
        prior_b = cb["refs"].get("samepath") if cb else None
        if cb is None or prior_b is None or cb["mean"] is None:
            v2 = ("판단 불가", "결과 없음")
        else:
            toward = "위로" if prior_b > cb["mean"] else "아래로"
            v2 = change(cb, toward)
        parts += [v1, v2]
        ev += [f"거리: {fmtc(cd)} → {v1[0]}", f"치우침: {fmtc(cb)}; 학습 전 사전 정보 {prior_b if prior_b is None else f'{prior_b:.2f}'} cm → {v2[0]}"]
    b173 = "B173 주변 항공 LiDAR 부분(6.7 cm에서 5 cm 아래로)은 판 A가 관문에 걸려 학습하지 않아 판단 불가"
    v = combine(parts)
    keys = [short(cell(s, p, "c2", m, acol(s, p, rd))) for s, p in narrow if (s, p) != ("R1rep_b10", "ALS") for m in ("dist", "bias")]
    out["A1"] = dict(verdict=v[0] if narrow else "판단 불가", grade=v[1], cases=[ck(s, p) for s, p in narrow],
                     evidence=ev + [b173] if narrow else [f"읽기 {rd}에서 폭이 좁아진 경우가 없다", b173],
                     key=("; ".join(keys) if keys else f"읽기 {rd}: 폭이 좁아진 경우 없음") + "; B173 주변 항공 LiDAR 관문")
    # A2
    parts, ev = [], []
    for s, p in narrow:
        c = cell(s, p, "img", "dist", acol(s, p, rd))
        vv = change(c, "나음")
        parts.append(vv)
        ev.append(f"{fmtc(c)} → {vv[0]}")
    v = combine(parts)
    out["A2"] = dict(verdict=v[0] if narrow else "판단 불가", grade=v[1], cases=[ck(s, p) for s, p in narrow], evidence=ev or [f"읽기 {rd}에서 폭이 좁아진 경우가 없다"],
                     key="; ".join(short(cell(s, p, "img", "dist", acol(s, p, rd))) for s, p in narrow) or f"읽기 {rd}: 폭이 좁아진 경우 없음")
    # A3
    cells = [cell(s, p, pl, m, acol(s, p, rd)) for s, p in wide for pl in PLACE_KO for m in ("dist", "R_tau")]
    v, g, beyond = within(cells)
    out["A3"] = dict(verdict=v, grade=g, cases=[ck(s, p) for s, p in wide], values_read=sum(usable(c) for c in cells),
                     evidence=none_or(cells, beyond), key=count_key(cells, beyond))
    # A4
    c = cell("R1rep_b10", "ALS", "c2", "dist", "A") if a_trained("R1rep_b10", "ALS", rd) else None
    if c is None or not usable(c):
        out["A4"] = dict(verdict="판단 불가", grade=(c or {}).get("status"), evidence=[fmtc(c)])
    else:
        ok = c["grade"] == "같음" or c["side"] == "못함"
        cb = cell("R1rep_b10", "ALS", "c2", "bias", "A")
        out["A4"] = dict(verdict="맞음" if ok else "틀림", grade=c["grade"], evidence=[fmtc(c), "치우침: " + fmtc(cb)], key=short(c) + "; " + short(cb))
    # A5
    parts, ev = [], []
    for s, p in narrow:
        if p != "ALS":
            continue
        cv = CURVE.get(f"{s}/{p}", {})
        x = cv.get("results", {}).get(acol(s, p, rd), {})
        if "raw" not in x:
            parts.append(("판단 불가", x.get("status", "결과 없음")))
            ev.append(f"{ck(s, p)}: 판 A(읽기 {rd}) {x.get('status', '결과 없음')}")
            continue
        for i, b in enumerate(x["raw"]):
            r = x["read_raw"][i]["R_tau"]
            if r.get("grade") in (None, "—"):
                vv = ("판단 불가", "결과 없음")
            elif r["grade"] == "표본 부족":
                vv = ("판단 불가", "표본 부족")
            elif r["grade"] == "같음":
                vv = ("틀림", "같음")
            else:
                vv = ("맞음" if r["side"] == "못함" else "틀림", r["grade"])
            parts.append(vv)
            r0, r1 = cv["results"]["s0"]["raw"][i]["R_tau"], cv["results"]["s1"]["raw"][i]["R_tau"]
            mtxt = "—" if r0 is None or r1 is None else f"{50 * (r0 + r1):.1f}"
            ftxt = "—" if b["R_tau"] is None else f"{100 * b['R_tau']:.1f}"
            ev.append(f"{ck(s, p)} {b['bin']}: 판 A {ftxt} %, 본 방법 평균 {mtxt} % (행 {b['n']:,}) → {vv[0]} ({vv[1]})")
        for i, b in enumerate(x["curve"]):
            if b["range"][0] == 1.0:
                r = x["read"][i]["R_tau"]
                ev.append(f"{ck(s, p)} 묶은 구간 {b['bin']} (행 {b['n']:,}): 판 A {100 * b['R_tau']:.1f} %, 읽기 {r.get('grade')}" + (f" {r.get('side')}" if r.get("side") else ""))
    v = combine(parts)
    out["A5"] = dict(verdict=v[0] if parts else "판단 불가", grade=v[1], evidence=ev or [f"읽기 {rd}에서 폭이 좁아진 항공 LiDAR 경우가 없다"],
                     key="; ".join(e.split(" → ")[0] for e in ev[:2]) if ev else f"읽기 {rd}: 폭이 좁아진 항공 LiDAR 경우 없음")
    # A6
    cells = [cell(s, p, "c11", m, acol(s, p, rd)) for s, p in trained for m in ("dist", "infl11")]
    v, g, beyond = within(cells)
    out["A6"] = dict(verdict=v, grade=g, cases=[ck(s, p) for s, p in trained], evidence=none_or(cells, beyond),
                     key=count_key(cells, beyond))
    # A7
    parts, ev = [], []
    for s, p in (("B173nb_b10", "ALS"), ("R1rep_b10", "ALS"), ("R1rep_b10", "LoD2")):
        if not a_trained(s, p, rd):
            parts.append(("판단 불가", "관문"))
            ev.append(f"{ck(s, p)}: 관문")
            continue
        c = cell(s, p, "c4", "R_0.2", acol(s, p, rd))
        if not usable(c):
            parts.append(("판단 불가", (c or {}).get("grade") or "결과 없음"))
        elif c["grade"] == "같음" or (c["grade"] == "가능·근거 불완전" and c["side"] == "나음"):
            parts.append(("맞음", c["grade"]))
        else:
            parts.append(("틀림", c["grade"]))
        ev.append(fmtc(c) + f" → {parts[-1][0]}")
    v = combine(parts)
    out["A7"] = dict(verdict=v[0], grade=v[1], evidence=ev, rule="'기준 안이거나 조금 오른다' = 같음, 또는 오른 쪽의 가능·근거 불완전. 오른 쪽의 확인(큰 실패를 고침)이나 내려간 쪽은 틀림",
                     key="; ".join(short(cell(s, p, "c4", "R_0.2", acol(s, p, rd))) if a_trained(s, p, rd) else f"{ck(s, p)} 관문"
                                   for s, p in (("B173nb_b10", "ALS"), ("R1rep_b10", "ALS"), ("R1rep_b10", "LoD2"))))
    # A8
    parts, ev = [], []
    for s, p in trained:
        w = WD[rd][f"{s}/{p}"]
        if abs(w["w_roof"] - w["tau_roof"]) < 1e-9 and abs(w["w_wall"] - w["tau_wall"]) < 1e-9:
            parts.append(("판단 불가", "w = τ"))
            ev.append(f"{ck(s, p)}: w = τ라 w~τ 구간이 비어 있다")
            continue
        b = jl(FTP / "mech" / f"bands_{s}_{p}_{rd}.json")
        res = f"fix{acol(s, p, rd)}_{p}_s0"
        if not b or res not in b["results"] or f"prop_{p}_s0" not in b["results"] or f"prop_{p}_s1" not in b["results"]:
            parts.append(("판단 불가", "결과 없음"))
            ev.append(f"{ck(s, p)}: 구간 몫 결과 없음")
            continue
        sh = {k: b["results"][k]["agree"] for k in (f"prop_{p}_s0", f"prop_{p}_s1", res)}
        vv = []
        for key, want in (("w_tau", "아래"), ("lt_w", "위")):
            a0, a1, fx = (100 * sh[k]["shares"][key] for k in (f"prop_{p}_s0", f"prop_{p}_s1", res))
            n = sh[res]["n"]
            crit = max(2.8 * abs(a0 - a1) / math.sqrt(2), 300.0 / max(n, 1))
            d = fx - 0.5 * (a0 + a1)
            g = "확인" if abs(d) > 2 * crit else ("가능·근거 불완전" if abs(d) > crit else "같음")
            ok = g != "같음" and ((d < 0) == (want == "아래"))
            vv.append(("맞음" if ok else "틀림", g))
            ev.append(f"{ck(s, p)} {'w~τ' if key == 'w_tau' else 'w 안'} 몫: 판 A {fx:.2f} %, 본 방법 {a0:.2f}·{a1:.2f} %, 차 {d:+.2f} %p, 기준 {crit:.2f} → {vv[-1][0]} ({g}; 화소 {n:,})")
        parts.append(combine(vv))
    v = combine(parts)
    out["A8"] = dict(verdict=v[0], grade=v[1], evidence=ev, key="; ".join(e.split(" → ")[0].split(":")[0] + ":" + e.split(":")[1].split(",")[0] for e in ev if "몫:" in e) or "—")
    return out


def pred_B():
    out = {}
    # B1
    parts, ev = [], []
    for s, p, trust in (("B173nb_b10", "ALS", 63.1), ("R1rep_b10", "ALS", 91.9)):
        c = cell(s, p, "c4", "R_0.2", "B")
        if not usable(c):
            parts.append(("판단 불가", (c or {}).get("grade") or "결과 없음"))
            ev.append(fmtc(c))
            continue
        big = c["diff"] > 2 * c["criterion"]
        under = c["value"] <= (c["refs"].get("trust") if c["refs"].get("trust") is not None else trust) + 1e-9
        parts.append(("맞음" if big and under else "틀림", c["grade"]))
        ev.append(fmtc(c) + f"; 기준의 두 배 {2 * c['criterion']:.2f} {'넘음' if big else '못 넘음'}; 사전 정보 신뢰 "
                  f"{c['refs'].get('trust') if c['refs'].get('trust') is not None else trust:.1f} % {'이하' if under else '초과'} → {parts[-1][0]}")
    c = cell("B0_b10", "ALS", "c4", "R_0.2", "B")
    if usable(c):
        ok = c["grade"] == "같음" or c["side"] == "나음"
        parts.append(("맞음" if ok else "틀림", c["grade"]))
        ev.append(fmtc(c) + f" (B0 항공 LiDAR: 같거나 오른다) → {parts[-1][0]}")
    else:
        parts.append(("판단 불가", (c or {}).get("grade") or "결과 없음"))
        ev.append(fmtc(c))
    v = combine(parts)
    out["B1"] = dict(verdict=v[0], grade=v[1], evidence=ev, key="; ".join(short(cell(s, p, "c4", "R_0.2", "B")) for s, p in (("B173nb_b10", "ALS"), ("R1rep_b10", "ALS"), ("B0_b10", "ALS"))))
    # B2
    c1 = cell("R1rep_b10", "LoD2", "c4", "R_0.2", "B")
    c2 = cell("R1rep_b10", "LoD2", "c4", "infl13", "B")
    p1, p2 = change(c1, "나음"), change(c2, "못함")
    v = combine([p1, p2])
    out["B2"] = dict(verdict=v[0], grade=v[1], evidence=[fmtc(c1) + f"; 판정만 끈 본 방법 {f1(c1['refs'].get('nojudge') if c1 else None)} → {p1[0]}",
                                                        fmtc(c2) + f"; 판정만 끈 본 방법 {f1(c2['refs'].get('nojudge') if c2 else None)} → {p2[0]}"],
                     key=short(c1) + "; " + short(c2))
    # B3
    parts, ev = [], []
    for s, p in (("B0_b10", "LoD2"), ("B173nb_b10", "LoD2")):
        c = cell(s, p, "c4", "R_0.2", "B")
        if usable(c):
            ok = c["grade"] == "같음" or c["side"] == "나음"
            parts.append(("맞음" if ok else "틀림", c["grade"]))
        else:
            parts.append(("판단 불가", (c or {}).get("grade") or "결과 없음"))
        ev.append(fmtc(c) + f" → {parts[-1][0]}")
        ci = cell(s, p, "c4", "infl13", "B")
        ev.append("유입률(값만 적음, '오를 수 있다'): " + fmtc(ci) + f"; 판정만 끈 본 방법 {f1(ci['refs'].get('nojudge') if ci else None)}")
    v = combine(parts)
    out["B3"] = dict(verdict=v[0], grade=v[1], evidence=ev, key="; ".join(short(cell(s, p, "c4", m, "B")) for s, p in (("B0_b10", "LoD2"), ("B173nb_b10", "LoD2"))
                                                                         for m in ("R_0.2", "infl13")))
    # B4
    cells = [cell(s, p, pl, m, "B") for s, p in CASES for pl in ("c2", "img", "c11", "c11s") for m in ("dist", "R_tau")]
    v, g, beyond = within(cells)
    out["B4"] = dict(verdict=v, grade=g, evidence=none_or(cells, beyond), key=count_key(cells, beyond))
    # B5
    parts, ev = [], []
    for u, e in MECHB.items():
        s, p = u.split("/")
        for grp, key, want in (("wrong_release_c4", "R_0_2", "up"), ("right_release_c13", "inflow", "up")):
            gdat = e.get(grp, {})
            vals = gdat.get("values", {})
            fx, a0, a1 = (vals.get(r, {}) for r in (f"fixB_{p}_s0", f"prop_{p}_s0", f"prop_{p}_s1"))
            if gdat.get("patches", 0) == 0:
                continue
            if fx.get(key) is None or a0.get(key) is None or a1.get(key) is None:
                parts.append(("판단 불가", "결과 없음"))
                ev.append(f"{ck(s, p)} {GROUP_KO[grp]}: 결과 없음")
                continue
            n = fx.get("n") or 0
            if n < 100:
                parts.append(("판단 불가", "표본 부족"))
                ev.append(f"{ck(s, p)} {GROUP_KO[grp]}: 패치 {gdat['patches']}, 행 {n} → 표본 부족")
                continue
            x0, x1, xf = 100 * a0[key], 100 * a1[key], 100 * fx[key]
            crit = max(2.8 * abs(x0 - x1) / math.sqrt(2), 300.0 / n)
            d = xf - 0.5 * (x0 + x1)
            g = "확인" if abs(d) > 2 * crit else ("가능·근거 불완전" if abs(d) > crit else "같음")
            if g == "확인" and n < 10000:
                g = "가능·근거 불완전"
            ok = g != "같음" and d > 0
            parts.append(("맞음" if ok else "틀림", g))
            ev.append(f"{ck(s, p)} {GROUP_KO[grp]} ({'R(0.2 m)' if key == 'R_0_2' else '유입률'}): 판 B {xf:.1f} %, 본 방법 {x0:.1f}·{x1:.1f} %, 차 {d:+.1f} %p, 기준 {crit:.1f}, "
                      f"패치 {gdat['patches']}, 넓이 {gdat['area_m2']:.1f} m², 행 {n:,} → {parts[-1][0]} ({g})")
    v = combine(parts)
    out["B5"] = dict(verdict=v[0], grade=v[1], evidence=ev, key="; ".join(e.split(", 패치")[0] for e in ev if "판 B" in e)[:400] or "—")
    return out


def main():
    P = {"L": pred_A("L"), "T": pred_A("T"), "B": pred_B()}
    (T / "predictions_ft.json").write_text(json.dumps(dict(task="PHD-MAIN-FIXTEST-v1", rule=__doc__.split("\n\n")[0], predictions=P, scientific_verdict=None),
                                                       indent=1, ensure_ascii=False, default=float))
    L = ["# 예측의 판정 [이 발주에서 냄]", "", "판정 규칙: 방향을 말한 예측은 그 방향으로 기준을 넘으면 맞음, 같음이거나 반대 방향이면 틀림, 결과가 없거나(관문) 표본이 100점 "
         "미만이면 판단 불가. '기준 안'을 말한 예측은 모든 값이 같음이면 맞음. 등급은 판정을 정한 값 가운데 가장 약한 읽기다.", ""]
    for part, title in (("L", "판 A, 읽기 L"), ("T", "판 A, 읽기 T"), ("B", "판 B")):
        L += [f"## {title}", "", "| 예측 | 판정 | 등급 | 근거 |", "|---|---|---|---|"]
        for k, v in P[part].items():
            L.append(f"| {k} | {v['verdict']} | {v.get('grade') or '—'} | " + "<br>".join(str(x) for x in v.get("evidence", [])) + " |")
        L.append("")
    (T / "predictions_ft.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
