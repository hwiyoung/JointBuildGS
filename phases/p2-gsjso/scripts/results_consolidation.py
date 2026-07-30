#!/usr/bin/env python3
"""P2 — READ-ONLY consolidation of repo-only result numbers for the paper's canonical progression table.
Computes every cell DIRECTLY from on-disk eval_*.json / ref_rms_*.csv / TB / Roofer cityjson / val3dity.json
(NO transcription). Observation only — no interpretation/framing. Output = markdown to stdout.

Arms (canonical training runs with full eval JSONs): v6_protect -> D (prior_full) -> D4.
Diagnostics of the D run: D2 = read-out/training attribution (2x2), D3 = quality/topology (val3dity tally).
Baselines reused: img(raw_dense/acmp), LiDAR(raw_lidar), ref(baselines.json GT roof polys).
Facet counts = TARGET-ONLY (filter Roofer CityObjects to the target building_id; validated vs W_D4).
"""
import csv, glob, json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
M = REPO / "results/tum_transfer/mob"
A = REPO / "results/tum_transfer/mob_analysis"
EVALROOT = REPO / "phases/p0-audit/runs/mob_eval"
CFGDIR = REPO / "configs/tum_mob"

TARGETS = ["4906972", "4907182", "4906969", "4908023", "4907510", "42364659",
           "42364663", "42364609", "4908050", "4908166", "4908176"]
RECOVERY = ["42364609", "42364659", "42364663", "4907182", "4907510", "4908050", "4908166", "4908176"]
RMS_FOCUS = ["4906972", "4906969", "4908023"]

# canonical arms: label -> dict(eval json, dense cfg, acmp cfg, rms csv, tb cfg map, readout note)
ARMS = [
    ("v6_protect", "eval_v6_protect.json", "gs_seed_dense_protect", "gs_seed_acmp_protect", "ref_rms_protect.csv", "smrf"),
    ("D",          "eval_prior_full_gssem.json", "gs_prior_full_dense", "gs_prior_full_acmp", "ref_rms_D.csv", "gssem"),
    ("D4",         "eval_d4_gssem.json", "gs_d4_dense", "gs_d4_acmp", "ref_rms_d4.csv", "gssem"),
]
BASE = [  # baseline comparison arms (reused)
    ("img(raw_dense)", "eval_v6_raw.json", "raw_dense", None, "ref_rms_raw.csv", "smrf"),
    ("img(raw_acmp)",  "eval_v6_raw.json", "raw_acmp",  None, "ref_rms_raw.csv", "smrf"),
    ("LiDAR",          "eval_v6_raw.json", "raw_lidar", None, "ref_rms_raw.csv", "als"),
]


def load_eval(fn):
    p = M / fn
    d = {}
    if p.exists():
        for r in json.loads(p.read_text()):
            d[(r["config"], r["bid"], r.get("tag", "orig"))] = r
    return d


def load_rms(fn):
    p = A / fn
    d = {}
    if p.exists():
        for r in csv.DictReader(open(p)):
            try:
                v = float(r["rms_to_ref_m"])
            except (TypeError, ValueError, KeyError):
                v = None
            d[(r["config"], r["bid"], r.get("tag", "orig"))] = v
    return d


def assembled(r):
    return bool(r and r.get("roofer_ok") and (r.get("roof_surfaces") or 0) > 0)


def valid_solid(r):
    return bool(r and r.get("val3dity_valid") and (r.get("roof_surfaces") or 0) > 0)


def target_roofs(config, bid):
    """TARGET-ONLY RoofSurface count: keep CityObjects == bid or bid-child; drop neighbours."""
    full = f"DEBY_LOD2_{bid}"
    g = glob.glob(str(EVALROOT / config / f"roofer_{full}_orig" / "*.city.jsonl"))
    if not g:
        return None
    n = 0
    for ln in open(g[0]):
        if not ln.strip():
            continue
        for cid, o in json.loads(ln).get("CityObjects", {}).items():
            if cid == full or cid.startswith(full + "-"):
                for geom in o.get("geometry", []):
                    for s in geom.get("semantics", {}).get("surfaces", []):
                        if s.get("type") == "RoofSurface":
                            n += 1
    return n


def psnr_train(cfg):
    g = glob.glob(str(M / cfg / "tb" / "events*"))
    if not g:
        return None
    try:
        from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
        ea = EventAccumulator(sorted(g)[-1], size_guidance={"scalars": 0}); ea.Reload()
        sc = ea.Scalars("metric/psnr_train")
        return sc[-1].value if sc else None
    except Exception:
        return None


EV = {fn: load_eval(fn) for fn in set(a[1] for a in ARMS + BASE) |
      {"eval_v6sem_gssem.json", "eval_prior_full_smrf.json"}}
RMS = {fn: load_rms(fn) for fn in set(a[4] for a in ARMS + BASE)}
BASEJSON = json.loads((M / "baselines.json").read_text())
OUT = []
def w(s=""):
    OUT.append(s); print(s)


def gen_counts(ev, cfg):
    asm = sum(assembled(ev.get((cfg, f"DEBY_LOD2_{t}", "orig"))) for t in RECOVERY)
    val = sum(valid_solid(ev.get((cfg, f"DEBY_LOD2_{t}", "orig"))) for t in RECOVERY)
    rv = [RMS_ALL.get((cfg, f"DEBY_LOD2_{t}", "orig")) for t in RECOVERY]
    rv = [x for x in rv if x is not None]
    mr = f"{sum(rv)/len(rv):.2f}(n{len(rv)})" if rv else "-"
    return asm, val, mr

# merge all rms into one lookup keyed by config (csvs are per-arm but configs are unique)
RMS_ALL = {}
for fn, d in RMS.items():
    RMS_ALL.update(d)


# ---------- header ----------
w("# W_results_consolidation — 레포 전용 수치 통합 (READ-ONLY 추출, 관찰만·판정 없음)")
w("")
w("> 생성 = `phases/p2-gsjso/scripts/results_consolidation.py` (on-disk eval_*.json / ref_rms_*.csv / TB / Roofer cityjson 에서 **직접 산출**, 전사 없음).")
w("> EPSG:25832. 관찰만·판정 금지·해석/프레이밍 없음. 셀별 출처 명시. 비교 LiDAR·img(raw)·ref 는 기존값 재사용.")
w("> arm = {v6_protect, D=prior_full, D4} (full eval JSON) + D2(귀속 §5)·D3(무효 §6)는 D run 진단(별도 학습 arm 아님).")
w("")
w("## ⚠ §0 출처 무결성 경고 (읽기전용 발견 — 김휘영 확인 필요)")
w("D-수트 eval 은 한 arm 당 **gssem → smrf 순차**로 돌며 per-building `*_classified.las` · Roofer cityjson · val3dity 를 **덮어쓴다**.")
w("→ 현재 디스크의 per-building 산출물은 **마지막=smrf read-out**. (mtime: roofer cityjsonl 23:42 · `*_val3dity.json` 23:42 · `ref_rms_d4.csv` 23:49 모두 > `eval_d4_gssem.json` 23:41, < `eval_d4_smrf.json` 23:44.)")
w("| 메트릭 | read-out 정합? | 비고 |")
w("|---|---|---|")
w("| 생성 assembled/valid-solid (§1,§5,§6) | ✅ gssem 정합 | 결과 JSON `eval_*_gssem.json` 은 안 덮어써짐 |")
w("| PSNR(train) (§4) | ✅ read-out 무관 | Stage-2 렌더 지표(분류 전) |")
w("| **RMS→ref (§3)** | ⚠ **smrf 기준** | `ref_rms_{D,d4}.csv` = smrf 분류 .las 에서 산출 |")
w("| **target-only 면수 (§2)** | ⚠ **smrf 기하** | on-disk roofer cityjson = smrf; gssem 은 CLIP(오염)만 |")
w("| val3dity 오류코드 (§6) | ⚠ **복원불가** | gssem 리포트가 smrf 로 덮임 |")
w("→ **gssem-정합 RMS·target-only 면수·val3dity 코드가 필요하면 gssem 재-eval(`tum_mob_eval --classifier gssem`, CPU/도커, ~20분, GPU·학습 무관) 1회 필요.** (현 작업=읽기전용이라 미실행; 승인 시 실행.)")
w("")
# ---------- §1 generation ----------
w("## §1 생성 (조립안됨 REC 8동, tag=orig) — assembled/8 · valid-solid/8 · meanRMS→ref(REC)")
w("| arm | density | assembled/8 | valid-solid/8 | meanRMS→ref(REC) | 출처(eval / rms) |")
w("|---|---|---:|---:|---:|---|")
for label, ej, cd, ca, rcsv, ro in ARMS:
    for dens, cfg in [("dense", cd), ("acmp", ca)]:
        if not cfg:
            continue
        a, v, mr = gen_counts(EV[ej], cfg)
        w(f"| {label} ({ro}) | {dens} | {a} | {v} | {mr} | {ej} / {rcsv} |")
for label, ej, cd, ca, rcsv, ro in BASE:
    a, v, mr = gen_counts(EV[ej], cd)
    w(f"| {label} | - | {a} | {v} | {mr} | {ej} / {rcsv} |")

# ---------- §2 target-only facets ----------
w("\n## §2 품질 — 지붕 면수 (11동) · ref=baselines.json")
w("> ⚠ **출처 주의(읽기전용 관찰)**: on-disk per-building Roofer cityjson 은 각 arm 의 **smrf eval 이 gssem eval 직후 덮어씀**")
w("> (mtime: roofer cityjsonl 23:42 / eval_d4_gssem.json 23:41 / eval_d4_smrf.json 23:44). 따라서 아래 **target-only 면수 = smrf read-out 기하**다(gssem 아님).")
w("> **gssem CLIP** 열은 `eval_*_gssem.json` 의 roof_surfaces(=gssem, 단 이웃 건물 포함=오염). gssem **target-only** 면수는 현재 디스크에서 복원 불가(재-eval 필요).")
w("")
w("| bid | ref | D gssemCLIP | D4 gssemCLIP | D tgt(smrf) | D4 tgt(smrf) | v6p tgt(smrf) | img tgt | LiDAR tgt |")
w("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
EVD = EV["eval_prior_full_gssem.json"]; EVD4 = EV["eval_d4_gssem.json"]
def clip(ev, cfg, t):
    r = ev.get((cfg, f"DEBY_LOD2_{t}", "orig"))
    return r.get("roof_surfaces") if r else None
def cell(x):
    return "-" if x is None else str(x)
for t in TARGETS:
    ref = BASEJSON[f"DEBY_LOD2_{t}"]["ref_roof_surfaces"]
    w(f"| {t} | {ref} | {cell(clip(EVD,'gs_prior_full_dense',t))} | {cell(clip(EVD4,'gs_d4_dense',t))} | "
      f"{cell(target_roofs('gs_prior_full_dense',t))} | {cell(target_roofs('gs_d4_dense',t))} | "
      f"{cell(target_roofs('gs_seed_dense_protect',t))} | {cell(target_roofs('raw_dense',t))} | {cell(target_roofs('raw_lidar',t))} |")
w("\n출처: gssemCLIP = `eval_{prior_full,d4}_gssem.json` roof_surfaces(이웃 오염); tgt(smrf) = `runs/mob_eval/<cfg>/roofer_*_orig/*.city.jsonl`(이웃 제외, **smrf 기하**); ref = `baselines.json`.")

# ---------- §3 RMS->ref ----------
w("\n## §3 RMS→ref (m, orig) — meanRMS(11동 中 산출가능) + 초점 4906972·4906969·4908023")
w("> ⚠ **출처 주의**: `ref_rms_{D,d4}.csv` 는 `tum_mob_ref_rms.py` 가 `runs/mob_eval/<cfg>/<bid>_orig_classified.las` 를 읽어 산출(line 98).")
w("> 그 .las 는 smrf eval 이 덮어쓴 것(ref_rms_d4.csv mtime 23:49 > smrf eval 23:44). 즉 **D·D4 의 RMS→ref = smrf-분류 지붕점 기준**(gssem 아님).")
w("> v6(`ref_rms_protect.csv`)=v6 정본 read-out=smrf 이라 정합; raw/LiDAR=단일 분류라 무관.")
w("| arm | density | meanRMS(all) | 4906972 | 4906969 | 4908023 | 출처(csv) |")
w("|---|---|---:|---:|---:|---:|---|")
def rms_row(label, cfg, rcsv):
    allv = [RMS_ALL.get((cfg, f"DEBY_LOD2_{t}", "orig")) for t in TARGETS]
    allv = [x for x in allv if x is not None]
    mr = f"{sum(allv)/len(allv):.2f}(n{len(allv)})" if allv else "-"
    foc = []
    for t in RMS_FOCUS:
        v = RMS_ALL.get((cfg, f"DEBY_LOD2_{t}", "orig"))
        foc.append(f"{v:.2f}" if v is not None else "-")
    return f"| {label} | {mr} | {foc[0]} | {foc[1]} | {foc[2]} | {rcsv} |"
for label, ej, cd, ca, rcsv, ro in ARMS:
    for dens, cfg in [("dense", cd), ("acmp", ca)]:
        r = rms_row(f"{label}", cfg, rcsv).split("|")
        w(f"| {label} | {dens} |" + "|".join(r[2:]))
for label, ej, cd, ca, rcsv, ro in BASE:
    r = rms_row(label, cd, rcsv).split("|")
    w(f"| {label} | - |" + "|".join(r[2:]))

# ---------- §4 PSNR(train) ----------
w("\n## §4 PSNR(train, final) — TB metric/psnr_train")
w("| arm | dense | acmp | 출처 |")
w("|---|---:|---:|---|")
for label, ej, cd, ca, rcsv, ro in ARMS:
    pd = psnr_train(cd); pa = psnr_train(ca) if ca else None
    fp = lambda x: f"{x:.2f}" if x is not None else "-"
    w(f"| {label} | {fp(pd)} | {fp(pa)} | `{cd}/tb`, `{ca}/tb` |")

# ---------- §5 D2 attribution 2x2 ----------
w("\n## §5 (D2) 조립 귀속 — 분류(read-out) × 학습(training-prior), assembled/8 · valid-solid/8 (REC)")
w("| 학습 | 분류 | arm(config) | assembled/8 | valid-solid/8 | 출처 |")
w("|:---:|:---:|---|---:|---:|---|")
d2 = [
    ("✗", "smrf",  "v6 (gs_seed_*_protect)", EV["eval_v6_protect.json"], "gs_seed_dense_protect", "gs_seed_acmp_protect", "eval_v6_protect.json"),
    ("✗", "gssem", "v6sem (v6sem_*)",        EV["eval_v6sem_gssem.json"], "v6sem_dense", "v6sem_acmp", "eval_v6sem_gssem.json"),
    ("✓", "smrf",  "D-smrf (gs_prior_full_*)", EV["eval_prior_full_smrf.json"], "gs_prior_full_dense", "gs_prior_full_acmp", "eval_prior_full_smrf.json"),
    ("✓", "gssem", "D-gssem (gs_prior_full_*)", EV["eval_prior_full_gssem.json"], "gs_prior_full_dense", "gs_prior_full_acmp", "eval_prior_full_gssem.json"),
]
for tr, cl, name, ev, cd, ca, src in d2:
    for dens, cfg in [("dense", cd), ("acmp", ca)]:
        a = sum(assembled(ev.get((cfg, f"DEBY_LOD2_{t}", "orig"))) for t in RECOVERY)
        v = sum(valid_solid(ev.get((cfg, f"DEBY_LOD2_{t}", "orig"))) for t in RECOVERY)
        w(f"| {tr} | {cl} | {name} [{dens}] | {a} | {v} | {src} |")

# ---------- §6 val3dity invalid solids (D3) ----------
w("\n## §6 (D3) 무효 solid — canonical D4 gssem (eval_d4_gssem.json 기준), tag=orig, 11동")
w("> ⚠ **오류유형 집계 불가(읽기전용)**: eval 의 `val3dity_valid` 는 gssem 시점 combined cityjson 으로 판정됐으나,")
w("> 그 per-building val3dity 리포트는 smrf eval 이 덮어씀(현 디스크 val3dity.json = 전부 validity:True = smrf 기하). → **gssem 무효동의 오류코드는 현 디스크서 복원 불가**.")
w("> 무효 '개수'는 gssem 결과 JSON 에 남아있어 아래 표로 보고. 코드(302/303/306/405)는 §8 인용(W_D2_D3 §D3가, D run) 참조 또는 gssem 재-eval 필요.")
w("")
w("| arm | assembled(REC)/8 | valid-solid/8 | 무효-but-assembled 동(REC) | 출처 |")
w("|---|---:|---:|---|---|")
for cfg, dens in [("gs_d4_dense", "dense"), ("gs_d4_acmp", "acmp")]:
    ev = EV["eval_d4_gssem.json"]
    asm = [t for t in RECOVERY if assembled(ev.get((cfg, f"DEBY_LOD2_{t}", "orig")))]
    val = [t for t in RECOVERY if valid_solid(ev.get((cfg, f"DEBY_LOD2_{t}", "orig")))]
    inval = [t for t in asm if t not in val]
    w(f"| D4 {dens} | {len(asm)} | {len(val)} | {', '.join(inval) if inval else '(none)'} | eval_d4_gssem.json |")
# also list invalid across full 11 (incl curved/flat) for completeness
w("")
for cfg, dens in [("gs_d4_dense", "dense"), ("gs_d4_acmp", "acmp")]:
    ev = EV["eval_d4_gssem.json"]
    inval11 = [t for t in TARGETS if assembled(ev.get((cfg, f"DEBY_LOD2_{t}", "orig")))
               and not valid_solid(ev.get((cfg, f"DEBY_LOD2_{t}", "orig")))]
    w(f"- D4 {dens} 전체 11동 中 assembled-but-invalid: {', '.join(inval11) if inval11 else '(none)'}")
w("\n출처: `eval_d4_gssem.json`(무효 개수, gssem). per-building 오류코드 디스크 파일은 smrf-덮어쓰기로 무효(§ 위 주의).")

# ---------- §7 geoid check ----------
w("\n## §7 geoid 확인 — 각 arm config의 data_root")
for label, ej, cd, ca, rcsv, ro in ARMS:
    for cfg in [cd, ca]:
        p = CFGDIR / f"{cfg}.yaml"
        dr = "?"
        if p.exists():
            for ln in p.read_text().splitlines():
                if ln.strip().startswith("data_root:"):
                    dr = ln.split(":", 1)[1].split("#")[0].strip()
        w(f"- {label} `{cfg}`: data_root = `{dr}`")
w("\n→ 통합 arm(v6_protect·D·D2·D3·D4) **전부 `data_geoidfix`(post-fix)**. pre-fix 잔존 수치는 통합 arm 에 **없음**.")
w("  (알려진 pre-fix geoid 이슈 = 초기 make-or-break 5-way ablation `eval_results.json`(vanilla/baseline/mutual/structure/both)의 LABEL ~48 m geoid 혼입 — **본 통합 범위 밖**, 메모리/`SESSION_HANDOFF` [[p2-makeorbreak-run]] 기록. 출처: 메모리, 디스크 미검증.)")

# ---------- §8 verbatim quotes ----------
w("\n## §8 인용문 (원문 그대로 — read-out·학습 귀속 정정)")
w("")
w("### (a) 원 주장 — `docs/experiments/joint-optimization/w_d_prior_full/reports/W_D_prior_full.md` §2 (조립 회복 = read-out 단독)")
w("> **핵심 귀속(read-out vs 학습-prior 분리)**: 동일 D 학습에 read-out만 바꾼 D-smrf(2–3/8) ≈ v6(2/8) ≪ "
  "D-gssem(7/8). → **조립 회복 = 레버 3(GS-의미가 SMRF 대체)**. depth/normal/structure 학습-prior 단독으론 "
  "조립 미회복. 이는 P0c \"SMRF가 ACMP 지붕을 ground로 먹음\" 진단을 직접 확증·연장한다.")
w(">")
w("> (동 문서 §0) 단 이 회복은 GS-의미 read-out(레버 3, SMRF 제거) 효과이고 depth/normal/structure 학습-prior은 "
  "**무효**(같은 학습에 SMRF read-out인 D-smrf는 2–3/8 ≈ v6 2/8).")
w("")
w("### (b) 정정/철회 — `docs/experiments/evaluation/w_d2_d3/reports/W_D2_D3.md` (분류+학습 초가산적 시너지)")
w("> **정정**: [[W_D_prior_full]] §2의 \"회복=read-out 단독, 학습-prior 무효\"는 **과단순화**였다. D-smrf≈v6는 "
  "\"SMRF 하 학습 무효\"만 말하고, v6+gssem(3–5/8)이 분류 단독 한계를 드러낸다. 정확히는 **분류+학습 둘 다 필요(시너지)**. "
  "단 valid-solid는 D 3–4/8로 LiDAR 7/8 여전히 미달(위상 과제는 불변).")
w(">")
w("> **둘 다(D_gssem) = 7/8**: 가산 예측(2 + 학습기여 ~1 + 분류기여 ~1–3 = 4–5)을 **초과(7)** → "
  "**초가산적(super-additive) 시너지**. 분류는 학습이 키운 조밀·정합 점군 위에서만 7/8로 작동하고, 학습은 분류가 "
  "SMRF처럼 지붕을 먹지 않을 때만 조립으로 이어진다.")
w("")
w("출처: (a) `docs/experiments/joint-optimization/w_d_prior_full/reports/W_D_prior_full.md` §0·§2 · (b) `docs/experiments/evaluation/w_d2_d3/reports/W_D2_D3.md` D2 \"관찰 — 초가산적 시너지\". 원문 그대로 인용.")

# write the consolidated doc
DOC = REPO / "docs/experiments/research-operations/w_results_consolidation/reports/W_results_consolidation.md"
DOC.write_text("\n".join(OUT) + "\n")
print(f"\n[done] consolidation computed -> {DOC}")
