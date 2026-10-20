#!/usr/bin/env python3
"""PHD-MAIN-FIXTEST-v1 3.3: the configuration saved BEFORE any training (host, stdlib) -> configs/phd/main_fixtest_v1/fixtest_v1.json and
fixtest_v1.sha256.json (saving time and sha256; run_ft.py refuses to start when the file changed after saving).
Contents: the item-1 w table and the item-3 gate (FT/tables/w_table.json, FT/prep/w_decision.json), the narrowed cases, the switches,
every training (inputs, command, result name, lane, train flag), the figure places (FT/prep/figpos.json), the reading rules (order 9) and
the predictions (order 10) copied word for word from the saved order, the reference columns, the item-2 check summaries.
  python3 config_ft.py [--amend "<why>"]     (--amend: a recorded change after saving; the previous file is kept as fixtest_v1.<time>.json)
scientific_verdict: null."""
import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ft_plan as P  # noqa: E402

REPO = P.REPO
FT = P.FT
OUT = REPO / "configs/phd/main_fixtest_v1/fixtest_v1.json"
ORDER = REPO / "docs/experiments/phd/main_fixtest_v1/본실험_고친판시험_발주문_v1.md"


def section(text, head, nxt):
    a = text.index(head)
    b = text.index(nxt, a + len(head))
    return text[a:b].rstrip() + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--amend", default=None)
    ap.add_argument("--dry", action="store_true", help="print the runs and the sizes, write nothing")
    a = ap.parse_args()
    order = ORDER.read_text()
    reading_rules = section(order, "### 9.2 읽는 규칙", "## 10. 예측")
    predictions = section(order, "## 10. 예측", "## 11. 일 6: 그림")
    figure_rules = section(order, "### 11.1 규칙", "## 12. 일 7")
    wt = json.loads((FT / "tables/w_table.json").read_text())
    wdL = json.loads((FT / "prep/w_decision_L.json").read_text())
    wdT = json.loads((FT / "prep/w_decision_T.json").read_text())
    figpos = json.loads((FT / "prep/figpos.json").read_text()) if (FT / "prep/figpos.json").exists() else None
    cmp_dry = json.loads((FT / "checks/compare_dry.json").read_text()) if (FT / "checks/compare_dry.json").exists() else None
    cmp_probe = json.loads((FT / "checks/compare_probe.json").read_text()) if (FT / "checks/compare_probe.json").exists() else None
    runs = []
    for r in P.RUNS:
        key = f"{r['site']}/{r['prior']}"
        cL, cT = wdL["cases"][key], wdT["cases"][key]
        c = cT if r["fix"] == "AT" else cL
        if r["fix"] == "B":
            train, why = True, "판 B는 관문과 상관없음"
        elif r["fix"] == "AT":
            same = cL["train"] and abs(cT["w_roof"] - cL["w_roof"]) < 1e-9 and abs(cT["w_wall"] - cL["w_wall"]) < 1e-9
            train = bool(cT["train"] and not same)
            why = ("관문(읽기 T): " + ", ".join(cT["failed"])) if not cT["train"] else ("읽기 L과 w가 같아 같은 설정 — 판 A(읽기 L)로 갈음" if same else "관문 통과(읽기 T)")
        else:
            train = bool(cL["train"])
            why = ("관문 통과(읽기 L)" if train else "관문(읽기 L): " + ", ".join(cL["failed"])) + (" — 함께 켠 판은 판 A(읽기 L)를 따름" if r["fix"] == "AB" else "")
        name, cmd = P.command(r, r["lane"])
        isA = r["fix"].startswith("A")
        runs.append(dict(order=r["order"], lane_gpu=r["lane"], site=r["site"], prior=r["prior"], fix=r["fix"], result=r["result"], what=r["what"],
                         train=train, why=why, reading=P.reading_of(r["fix"]) if isA else None,
                         w_maps=str(P.wmap_dir(r["site"], r["prior"], container=False, reading=P.reading_of(r["fix"]))) if isA else None,
                         w_roof_m=c["w_roof"] if isA else None, w_wall_m=c["w_wall"] if isA else None,
                         narrowed=c["narrowed"] if isA else None, command=cmd, payload_dir=str(FT / "runs" / r["site"] / r["result"])))
    cfg = dict(
        task_id="PHD-MAIN-FIXTEST-v1", version="fixtest_v1", order=str(ORDER.relative_to(REPO)), branch="exp/main-experiment",
        saved_before_any_training=True, scientific_verdict=None,
        fork=dict(r16="src/phd/forks/GeoGS-conf-guided-v1-r16 (r15 + jbgs_judgment.py; build report docs/experiments/phd/main_fixtest_v1/provenance/build_report_r16.json)",
                  image=P.IMG, renderer="the image's compiled diff-surfel-rasterization (as stage 1)", records="--data_device cpu, memory record every 500, out-of-memory record (stage 3's)"),
        switches={"--jbgs_sw_prior_share_band": "판 A. 0 (기본) = 손실의 허용 구간 끝 τ (r15와 같음); 1 = 허용 구간 끝 w (--jbgs_prior_width_dir의 화소 지도, τ 지도와 같은 환산). 당김 구간 w~4τ, 절단 4τ, 판정·충돌 문턱·보호 한계 4τ는 그대로",
                  "--jbgs_prior_width_dir": "판 A의 w 지도 폴더 (학습 영상마다, prep/wmaps/<site>/<prior>)",
                  "--jbgs_sw_own_depth_release": "판 B. 0 (기본) = r15와 같음; 1 = 결측 패치(상태 2)의 빌린 판정이 충돌(0)·섞임(2)이면 일치(1)로 읽음(전파 표 J와 패치 표 J_loc를 한 번 고쳐 모든 통로가 같은 표를 읽음), 결측 패치 화소는 깊이 항에서 4τ를 넘어도 절단하지 않음(근거 부족·판정 없음 결측 패치 포함). 지지·비가시 패치와 패치 없는 화소는 그대로"},
        item1=dict(table="FT/tables/w_table.json (docs/experiments/phd/main_fixtest_v1/tables/w_table.md)", reading_used=wt["reading_used"], readings=wt["readings"],
                   rows=[dict(region=e["region"], kind=e["kind_ko"], tau=e["tau"], NMAD=e["NMAD"], **{rd: dict(sigma_image=e[rd]["sigma_image"], sigma_image_ci95=e[rd]["sigma_image_ci95"],
                                                                                                         separable=e[rd]["separable"], sigma_prior=e[rd]["sigma_prior"], w=e[rd]["w"],
                                                                                                         w_ci95=e[rd]["w_ci95"], gate=e[rd]["gate"]) for rd in ("L", "T")})
                         for e in wt["rows"]],
                   procedure="scripts/phd/main_fixtest_v1/w1_shares.py (residual = one pixel of one view, s03_stage1.py:145; image share by the patch-centre pairs of views)"),
        item3=dict(reading_L=wdL["cases"], reading_T=wdT["cases"],
                   narrowed=dict(L=[k for k, v in wdL["cases"].items() if v["narrowed"]], T=[k for k, v in wdT["cases"].items() if v["narrowed"]]),
                   trained_fix_a=dict(L=[k for k, v in wdL["cases"].items() if v["train"]], T=[k for k, v in wdT["cases"].items() if v["train"]]),
                   both_readings_trained="판 A는 두 읽기를 모두 학습한다(발주의 판 A 6회 안). 읽기 L = 발주 5.2 식의 NMAD(지우기 없음, 주 읽기), 읽기 T = τ의 통계(3 NMAD 한 번 지운 뒤). '폭이 좁아진 경우'와 예측의 판단은 읽기마다 따로 한다.",
                   rule="order 7: 가 (참값 두 몫이 1.25배 넘게 다르면 참값 없이 구한 두 몫도 같은 쪽이 작다), 나 (항공 LiDAR σ_사전 ≥ 사전 정보 면 평면 맞춤 흔들림), 다 (σ_영상 < NMAD, 아니면 w = τ)"),
        runs=runs,
        reference_columns={"본 방법": "prop_<prior>_s0, prop_<prior>_s1 (1단계 r12; B173 주변은 0단계 b1/b2)", "판정만 끈 본 방법": "nojudge_<prior>_s0 (S3/runs, r15)",
                           "영상만": "imgonly_s0 (S1)", "사전 정보 신뢰": "trust_ALS (S1)", "허용 구간 없애기": "S2/runs/B173nb_b10/abl_band_ALS_s0, S2/runs/R1rep_b10/abl_band_LoD2_s0 (2단계 r13 --jbgs_ablate_tolerance_band 1)",
                           "MVS 기반 결합": "mvsfuse_<prior> (SB)", "학습 전 사전 정보": "samepath_<prior> (S1)"},
        metrics=dict(distance="scripts/phd/main_dist71_v1 (d2_dist → d3 블록: R(0.2, τ), P(셈 가), F1, 거리, 치우침, 퍼짐, 표본); 출력은 이 페이로드 dist/",
                     influx="metrics_s2 (metrics_s1.spread, lines.four_way: 참값 쪽/틀린 쪽/양쪽/어느 쪽도 아님; 유입 = 틀린 쪽 + 양쪽): 코드 11 prior_error.main.spread, 코드 13 missing_prior_error_record.main.spread",
                     places="dm_common.Unit (S1 영역 v3, obs_masked; 조금 틀린 곳 = 코드 11 중 1 ≤ |gt_med|/τ < 4)", band_w="렌더 깊이 구간 몫: 30,000회 덤프 학습 영상, g_p = 1 화소의 |D − P|를 w, τ, 2τ, 4τ로 나눔"),
        reading_rules_verbatim=reading_rules, predictions_verbatim=predictions, figure_rules_verbatim=figure_rules,
        figure_places=figpos,
        figure_places_added=dict(fig1b=dict(
            why="그림 1의 자리(B173 주변 항공 LiDAR 면 1)는 두 읽기 모두 관문에 걸려 판 A 결과가 없다. 폭이 좁아진 유일한 경우(B0 항공 LiDAR, 읽기 T)에 같은 꼴의 그림을 학습 전에 더한다 (그림 1은 발주의 자리 그대로 판 A 없이 그린다).",
            see="판 A(읽기 T)에서 결과의 봉우리가 사전 정보 쪽으로 옮겨 갔는가", site="B0_b10", prior="ALS",
            rows_rule="2단계 measure_s2의 gentle_row(코드 2, 지붕, 띠 v2 밖, 기울기 17° 이하, 솎은 행) 가운데 surf_ext == 0인 행 — 이 경우에서 완만한 지붕 행이 가장 많은 면(4,446행 가운데 3,848행; S2/measure/B0_b10/ALS__prop_ALS_s0.npz와 S1/defs/B0_b10/rows_ALS.npz)",
            face=0, n_rows=3848, curve="new = 참값 점을 지나는 연직선이 결과 메시와 만나는 점 가운데 z_GT ± 1 m 안 가장 높은 점의 z − z_GT (그림 1과 같은 셈)",
            lines=["prop_ALS_s0", "prop_ALS_s1", "fixAT_ALS_s0 (읽기 T, w 8.08 cm)", "fixA_ALS_s0 (읽기 L, w = τ)", "samepath_ALS"],
            verticals="학습 전 사전 정보의 봉우리에서 ± w(8.08 cm)와 ± τ(12.66 cm)")),
        item2=dict(compare_dry=None if cmp_dry is None else dict(pairs=[dict(b=e["b"], n=e["n_differences"], unexpected=e["unexpected"]) for e in cmp_dry["pairs"]],
                                                                  deep_B={k: v["ok"] for k, v in cmp_dry["deep_B"].items()}),
                   compare_probe=None if cmp_probe is None else dict(pairs=[dict(b=e["b"], n=e["n_differences"], unexpected=e["unexpected"]) for e in cmp_probe["pairs"]],
                                                                      deep={k: v["ok"] for k, v in cmp_probe["deep"].items()})),
    )
    if a.dry:
        for r in runs:
            print(r["order"], r["lane_gpu"], r["fix"], r["site"], r["prior"], r["result"], "TRAIN" if r["train"] else "-", r["why"], r["w_roof_m"], r["w_wall_m"])
        print("predictions chars", len(predictions), "reading rules chars", len(reading_rules), "figure places", bool(figpos))
        return
    now = dt.datetime.now().astimezone()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    shaf = OUT.parent / "fixtest_v1.sha256.json"
    hist = []
    if OUT.exists():
        if not a.amend:
            raise SystemExit(f"{OUT} exists: a change after saving needs --amend '<why>'")
        prev = json.loads(shaf.read_text())
        keep = OUT.parent / f"fixtest_v1.{now.strftime('%Y%m%dT%H%M%S')}.json"
        shutil.copy2(OUT, keep)
        hist = prev.get("history", []) + [dict(at=prev["saved_at"], sha256=prev["sha256"], kept_as=keep.name)]
        cfg["amendments"] = json.loads(OUT.read_text()).get("amendments", []) + [dict(at=now.isoformat(), why=a.amend, previous=keep.name)]
    OUT.write_text(json.dumps(cfg, indent=1, ensure_ascii=False, default=float))
    sha = hashlib.sha256(OUT.read_bytes()).hexdigest()
    shaf.write_text(json.dumps(dict(file=str(OUT.relative_to(REPO)), saved_at=now.isoformat(), sha256=sha, history=hist), indent=1))
    print("saved", OUT, sha[:12], now.isoformat(), "runs to train", sum(r["train"] for r in runs))


if __name__ == "__main__":
    main()
