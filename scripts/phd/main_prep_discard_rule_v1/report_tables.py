"""PHD-MAIN-PREP-DISCARD-RULE-v1: the report's tables as Markdown, generated from the result files (jointbuildgs:dev, CPU).

  python report_tables.py       -> tables/report_tables.md (one section per table, Korean headers)
scientific_verdict: null."""
import json
from pathlib import Path

from common import OUT, PREP, REPO, jdump

KO = {"current": "지금 규칙", "margin_all_1.5": "여유(모두) 1.5", "margin_all_2": "여유(모두) 2", "margin_all_3": "여유(모두) 3",
      "margin_prop_1.5": "여유(전파만) 1.5", "margin_prop_2": "여유(전파만) 2", "margin_prop_3": "여유(전파만) 3", "asymmetric": "비대칭",
      "tau_0.5": "허용 오차 0.5배", "tau_2": "허용 오차 2배"}
PART = {"measured": "잰 곳", "unmeasured": "재지 못한 곳"}
SITE_KO = {"B173_wings": "B173 양 날개", "B173_middle": "B173 가운데", "R1_hall": "R1 긴 홀", "R3_wall": "R3 벽", "R4_flat": "R4 평지붕",
           "R3E_flat": "R3E 평지붕", "R5_wall_trees": "R5 벽 앞 나무", "B0_facade": "B0 정면"}
BOX_KO = {"B0_b10": "B0", "B173nb_b10": "B173과 이웃", "B173_b0": "B173만", "R1rep_b10": "R1 부채꼴"}
PRIOR_KO = {"LoD2": "LoD2", "ALS": "항공 LiDAR"}


def ko(key):
    """'site/prior', 'box/prior', 'box_prior' or a plain name -> plain-language label for the report tables."""
    for sep in ("/", "_"):
        if sep in key:
            a, b = key.rsplit(sep, 1)
            if b in PRIOR_KO:
                return f"{SITE_KO.get(a, BOX_KO.get(a, a))} · {PRIOR_KO[b]}"
    return SITE_KO.get(key, BOX_KO.get(key, PRIOR_KO.get(key, key)))


def fmt(x):
    return f"{x:,}" if isinstance(x, int) else (f"{x:.3f}" if isinstance(x, float) else str(x))


def table(head, rows):
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * len(head)) + "|"] + ["| " + " | ".join(fmt(c) for c in r) + " |" for r in rows])


def main():
    out = []
    C = json.loads((OUT / "rules/counts.json").read_text())
    agg = C["selection_aggregate"]
    # 0. compact two-error table for section 1: wrong discard / wrong keep per rule, with the change against the current rule in %
    def pc(v, c):
        return f"{v:,} ({'+' if v - c >= 0 else '−'}{abs(v - c) / c * 100:.0f} %)" if c else f"{v:,}"
    for part in ("measured", "unmeasured"):
        rows = []
        for n in KO:
            r = [KO[n]]
            for prior, kind in (("LoD2", "roof"), ("LoD2", "wall"), ("ALS", "roof")):
                d = agg[prior][f"{kind}_{part}"]; v, c = d[n], d["current"]
                if n == "current":
                    r += [f"{v['wrong_discard']:,}", f"{v['wrong_keep']:,}"]
                else:
                    r += [pc(v["wrong_discard"], c["wrong_discard"]), pc(v["wrong_keep"], c["wrong_keep"])]
            rows.append(r)
        cur = {{("LoD2", "roof"): "LoD2 지붕", ("LoD2", "wall"): "LoD2 벽", ("ALS", "roof"): "항공 LiDAR 지붕"}[(p_, k_)]: agg[p_][f"{k_}_{part}"]["current"]
               for p_, k_ in (("LoD2", "roof"), ("LoD2", "wall"), ("ALS", "roof"))}
        note = "; ".join(f"{k_}: 패치 {v['n']:,}, 참 충돌 {v['true_conflict']:,}, 지금 규칙 맞게 버림 {v['correct_discard']:,}" for k_, v in cur.items())
        out.append(f"### T0-{part}: 두 잘못, 고르는 곳, {PART[part]} (괄호 = 지금 규칙 대비)\n\n" + table(
            ["규칙", "LoD2 지붕 잘못 버림", "LoD2 지붕 잘못 지킴", "LoD2 벽 잘못 버림", "LoD2 벽 잘못 지킴", "항공 LiDAR 지붕 잘못 버림", "항공 LiDAR 지붕 잘못 지킴"], rows)
            + f"\n\n({note})")
    # 1. two errors per rule (selection), per prior / kind / part, with the change against the current rule
    for prior, kind in (("LoD2", "roof"), ("LoD2", "wall"), ("ALS", "roof")):
        rows = []
        for part in ("measured", "unmeasured"):
            d = agg[prior][f"{kind}_{part}"]; cur = d["current"]
            for n in d:
                v = d[n]
                wk = v["wrong_keep_by_ratio"]
                rows.append([PART[part], KO[n], v["n"], v["true_conflict"], v["wrong_discard"], v["wrong_discard"] - cur["wrong_discard"], v["wrong_keep"],
                             v["wrong_keep"] - cur["wrong_keep"], wk["1-2"], wk["2-4"], wk["4-inf"]])
        out.append(f"### T1-{prior}-{kind}: 고르는 곳, {prior} {'지붕' if kind == 'roof' else '벽'}\n\n" + table(
            ["곳", "규칙", "패치", "참 충돌", "잘못 버림", "지금 대비", "잘못 지킴", "지금 대비", "잘못 지킴 1~2τ", "2~4τ", ">4τ"], rows))
    # unplanted (selection, per range summed)
    rows = []
    for key, v in C["selection"].items():
        rid, prior = key.split("/")
        rows.append([rid, prior] + [v["aggregate_part"][n]["unplanted"].get("patches", v["aggregate_part"][n]["unplanted"].get("points")) for n in KO])
    out.append("### T2: 심지 않을 점 (고르는 곳, LoD2 = 패치, 항공 LiDAR = 점)\n\n" + table(["범위", "사전 정보"] + [KO[n] for n in KO], rows))
    # 3. confirmation
    rows = []
    for key, v in C["confirmation"].items():
        box, prior = key.split("/")
        c = v["counts"]
        for n in KO:
            parts = [p for p in c[n] if p.endswith(("_measured", "_unmeasured"))]
            wd = sum(c[n][p]["wrong_discard"] for p in parts); cd = sum(c[n][p]["correct_discard"] for p in parts)
            wk = sum(c[n][p]["wrong_keep"] for p in parts); ck = sum(c[n][p]["correct_keep"] for p in parts)
            up = c[n]["unplanted"].get("patches", c[n]["unplanted"].get("points"))
            rows.append([box, prior, KO[n], cd, wd, ck, wk, up])
    out.append("### T3: 확인하는 곳 (상자 넷의 평가 범위)\n\n" + table(["상자", "사전 정보", "규칙", "맞게 버림", "잘못 버림", "맞게 지킴", "잘못 지킴", "심지 않을 점"], rows))
    # compact: wrong discard / wrong keep (unplanted) for the main rules
    main_rules = ["current", "margin_all_1.5", "margin_all_2", "margin_all_3", "margin_prop_2", "margin_prop_3", "asymmetric"]
    rows = []
    for key, v in C["confirmation"].items():
        c = v["counts"]
        def tot(n, f):
            return sum(c[n][p][f] for p in c[n] if p.endswith(("_measured", "_unmeasured")))
        tc = tot("current", "correct_discard") + tot("current", "wrong_keep"); ta = tot("current", "wrong_discard") + tot("current", "correct_keep")
        row = [ko(key), f"{tc + ta:,}", f"{tc / max(tc + ta, 1) * 100:.0f} %"]
        for n in main_rules:
            up = c[n]["unplanted"].get("patches", c[n]["unplanted"].get("points"))
            row.append(f"{tot(n, 'wrong_discard'):,} / {tot(n, 'wrong_keep'):,} ({up:,})")
        rows.append(row)
    out.append("### T3c: 확인하는 곳, 잘못 버림 / 잘못 지킴 (심지 않을 점)\n\n" + table(["상자 · 사전 정보", "참 라벨 패치", "참 충돌 몫"] + [KO[n] for n in main_rules], rows))
    # 4. sites
    if (OUT / "rules/sites.json").exists():
        S = json.loads((OUT / "rules/sites.json").read_text())["sites"]
        rows = []
        for key, v in S.items():
            for n in KO:
                r = v["rules"][n]; m, u = r["measured"], r["unmeasured"]
                rows.append([key, v["expected"], KO[n], f"{m['discard']}/{m['n']}", f"{u['discard']}/{u['n']}",
                             m["discard_true_conflict"] + u["discard_true_conflict"], m["discard_true_agree"] + u["discard_true_agree"],
                             m["keep_true_agree"] + u["keep_true_agree"], m["keep_true_conflict"] + u["keep_true_conflict"]])
        out.append("### T4: 대표 자리\n\n" + table(["자리/사전 정보", "기대", "규칙", "잰 곳 버림", "재지 못한 곳 버림", "맞게 버림", "잘못 버림", "맞게 지킴", "잘못 지킴"], rows))
        # compact: true-conflict share and wrong discard / wrong keep for the main rules
        EXP = {"discard": "버림", "keep": "지킴"}
        main_rules = ["current", "margin_all_1.5", "margin_all_2", "margin_all_3", "margin_prop_2", "margin_prop_3", "asymmetric"]
        rows = []
        for key, v in S.items():
            r0 = v["rules"]["current"]; m0, u0 = r0["measured"], r0["unmeasured"]
            tc = sum(x[f] for x in (m0, u0) for f in ("discard_true_conflict", "keep_true_conflict"))
            ta = sum(x[f] for x in (m0, u0) for f in ("discard_true_agree", "keep_true_agree"))
            row = [ko(key), EXP.get(v["expected"], "판단만"), tc + ta, f"{tc / max(tc + ta, 1) * 100:.0f} %"]
            for n in main_rules:
                r = v["rules"][n]; m, u = r["measured"], r["unmeasured"]
                row.append(f"{m['discard_true_agree'] + u['discard_true_agree']:,} / {m['keep_true_conflict'] + u['keep_true_conflict']:,}")
            rows.append(row)
        out.append("### T4c: 대표 자리, 잘못 버림 / 잘못 지킴\n\n" + table(["자리 · 사전 정보", "발주의 맞는 판단", "참 라벨 패치", "참 충돌 몫"] + [KO[n] for n in main_rules], rows))
    # 5. tolerance and registration
    if (OUT / "tables/tau_registration.json").exists():
        Tt = json.loads((OUT / "tables/tau_registration.json").read_text())
        rows = [[r["range"], PRIOR_KO[r["prior"]], r["views_v11"], r["views_new"], r["tau_roof_v11"], r["tau_roof_new"], r["tau_wall_v11"], r["tau_wall_new"],
                 r["shift_v11"], r["shift_new"], r["gt_alignment_v11"], r["gt_alignment_new"]] for r in Tt]
        out.append("### T5: 허용 오차와 정합 (준비 측정 v1.1 = 평가 영상이 섞인 MVS, 새 값 = 학습 영상만의 MVS)\n\n" + table(
            ["범위", "사전 정보", "영상 v1.1", "영상 새", "τ 지붕 v1.1", "τ 지붕 새", "τ 벽 v1.1", "τ 벽 새", "정합 v1.1", "정합 새", "참값 맞춤 v1.1", "참값 맞춤 새"], rows))
    # 5b. the four boxes re-scored (current rule): prep v1.1 values against the new fixed values
    if (OUT / "tables/box_rescore.json").exists():
        rr = json.loads((OUT / "tables/box_rescore.json").read_text())["rows"]
        by = {(r["box"], r["prior"], r["values"]): r for r in rr}
        rows = []
        for (box, prior) in dict.fromkeys((r["box"], r["prior"]) for r in rr):
            a, b = by[(box, prior, "v1.1")], by[(box, prior, "new")]
            ar = lambda k: f"{a[k]:,} → {b[k]:,}"
            rows.append([BOX_KO[box], PRIOR_KO[prior], f"{a['tau_roof']} → {b['tau_roof']}", f"{a['shift'][:2]} → {b['shift'][:2]}", ar("patches"), ar("correct_discard"), ar("wrong_discard"),
                         ar("correct_keep"), ar("wrong_keep"), ar("unplanted")])
        out.append("### T5b: 상자 넷 다시 채점 (지금 규칙, 평가 범위, v1.1 값 → 새 값)\n\n" + table(
            ["상자", "사전 정보", "τ 지붕 (m)", "수평 정합 (m)", "참 라벨 패치", "맞게 버림", "잘못 버림", "맞게 지킴", "잘못 지킴", "심지 않을 점"], rows))
    # 6. B0 conditions
    if (OUT / "tables/b0_conditions.json").exists():
        B = json.loads((OUT / "tables/b0_conditions.json").read_text())
        RG = {"target": "대상 건물+2 m", "crop": "크롭 전체"}
        for reg in ("target", "crop"):
            rows = [[r["condition"], r["prior"], r["kind"], r["views"], r["patches"], r.get("labelled", "-"), r["support"], r["missing"], r["invisible"], r["inherit_share"],
                     r["support_conflict"], r["correct_discard"], r["wrong_discard"], r["correct_keep"], r["wrong_keep"], r["inherit_true_agree"], r["inherit_true_conflict"]]
                    for r in B if r.get("region", "target") == reg]
            out.append(f"### T6-{reg}: B0 관측의 양, {RG[reg]} (허용 오차·정합 = 새 B0 크롭 값)\n\n" + table(
                ["조건", "사전 정보", "면", "학습 영상", "패치", "참 라벨 패치", "지지", "결측", "비가시", "이어받는 몫", "지지 중 충돌", "맞게 버림", "잘못 버림", "맞게 지킴", "잘못 지킴",
                 "이어받음·참 일치", "이어받음·참 충돌"], rows))
    # 6c. compact B0 table (target building + 2 m)
    if (OUT / "tables/b0_conditions.json").exists():
        B = json.loads((OUT / "tables/b0_conditions.json").read_text())
        KN = {("LoD2", "roof"): "LoD2 지붕", ("LoD2", "wall"): "LoD2 벽", ("ALS", "roof"): "항공 LiDAR 지붕"}
        rows = [[r["condition"], r["views"], KN[(r["prior"], r["kind"])], f"{r['support']:.2f} / {r['missing']:.2f} / {r['invisible']:.2f}", f"{r['inherit_share']:.2f}",
                 f"{r['support_conflict']:.2f}", r["wrong_discard"], r["wrong_keep"], r["inherit_true_conflict"]]
                for r in B if r.get("region", "target") == "target"]
        out.append("### T6c: B0 관측의 양, 대상 건물+2 m (요약)\n\n" + table(
            ["조건", "학습 영상", "사전 정보·면", "지지 / 결측 / 비가시", "이어받는 몫", "지지 중 충돌", "잘못 버림", "잘못 지킴", "이어받음·참 충돌"], rows))
    # 7. equivalence and switches
    E1 = json.loads((OUT / "eq1/compare.json").read_text())
    rows = [[f"{BOX_KO[it]} 상자" if it in BOX_KO else f"{it} 범위", v.get("mesh_equal"), v["stage1"]["LoD2"].get("equal"), v["stage1"]["ALS"].get("equal")] for it, v in E1["items"].items()]
    out.append("### T7: 같은 판정 확인 1 (준비 측정 v1.1 입력, 원소 단위)\n\n" + table(["범위/상자", "메시·저장소", "LoD2 첫째 단계", "항공 LiDAR 첫째 단계"], rows))
    fc = OUT / "fork_checks/s52.json"
    if fc.exists():
        F = json.loads(fc.read_text())
        rows = [[ko(k), v.get("state"), v.get("vote"), v.get("J"), v.get("J_loc"), v.get("planted"), v.get("n_unplanted")] for k, v in F["check2"].items()]
        out.append("### T8: 같은 판정 확인 2 (포크 r11 초기화 = 측정)\n\n" + table(["상자/사전 정보", "상태", "표", "전파 판정", "패치 판정", "심지 않을 점", "개수 (포크, 측정)"], rows))
        rows = []
        for s, d in F["switches"].items():
            for k, v in d.items():
                extra = {kk: vv for kk, vv in v.items() if kk not in ("changed", "unexpected", "not_applicable", "states_on", "states_off")}
                rows.append([s, k, ", ".join(v.get("changed", [])), ", ".join(v.get("unexpected", [])) or "-", json.dumps(extra, ensure_ascii=False)[:160]])
        out.append("### T9: 장치 끄기 스위치 (모두 켬과 견줘 바뀐 것)\n\n" + table(["스위치", "상자/사전 정보", "바뀐 출력", "예상 밖", "확인 항목"], rows))
        # summary per switch over the eight runs (4 boxes x 2 priors)
        DC = json.loads((REPO / "configs/phd/main_prep_discard_rule_v1/discard_v1.json").read_text())["switches"]
        SWKO = {"confidence_mask": "관측 신뢰도 마스크", "judgment": "판정", "propagation": "판정 빌려 오기", "prior_band": "사전 정보 당김의 구간",
                "protection": "보호", "init_exclusion": "초기화에서 빼기", "prior": "사전 정보"}
        rows = []
        for sw_, d in F["switches"].items():
            runs = list(d.values())
            changed = sorted({c for v in runs for c in v.get("changed", [])})
            unexp = sorted({c for v in runs for c in v.get("unexpected", [])})
            checks = []
            for kk in sorted({k for v in runs for k in v} - {"changed", "unexpected", "not_applicable", "states_on", "states_off"}):
                vals = [v[kk] for v in runs if kk in v]
                if all(isinstance(x, bool) for x in vals):
                    checks.append(f"{kk} {sum(vals)}/{len(vals)}")
                else:
                    checks.append(f"{kk} = {sorted(set(json.dumps(x) for x in vals))}"[:80])
            if sw_ == "confidence_mask":
                sup = [(v["states_on"]["support"] / max(sum(v["states_on"].values()), 1), v["states_off"]["support"] / max(sum(v["states_off"].values()), 1)) for v in runs if "states_on" in v]
                if sup:
                    checks.append(f"지지 몫 {min(a for a, b in sup):.2f}~{max(a for a, b in sup):.2f} → {min(b for a, b in sup):.2f}~{max(b for a, b in sup):.2f}")
            rows.append([SWKO.get(sw_, sw_), len(runs), ", ".join(DC["expected_changed_outputs"].get(sw_, [])), ", ".join(changed) or "(없음)", ", ".join(unexp) or "없음", "; ".join(checks)])
        out.append("### T9s: 스위치 요약 (상자 넷 × 사전 정보 둘, 초기화까지만)\n\n" + table(["스위치", "돌린 수", "끄면 바뀌는 것(설정)", "실제로 바뀐 것", "예상 밖", "확인 항목"], rows))
    (OUT / "tables").mkdir(exist_ok=True)
    (OUT / "tables/report_tables.md").write_text("\n\n".join(out) + "\n")
    print("tables", len(out))


if __name__ == "__main__":
    main()
