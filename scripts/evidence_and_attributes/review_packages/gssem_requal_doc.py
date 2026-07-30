#!/usr/bin/env python3
"""P2 gssem re-qual — build the gssem|smrf comparison doc for D/D4 (READ-ONLY; observe only, no interpretation).
Reads numbers_{smrf,gssem}.json (gssem_requal_numbers.py output) and writes docs/experiments/evaluation/w_gssem_requal/reports/W_gssem_requal.md:
RMS->ref (mean + 4906972/4906969/4908023), target-only facets (11 bldg), val3dity error codes, all gssem|smrf.
"""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BK = REPO / "results/tum_transfer/mob/gssem_requal_backup"
M = REPO / "results/tum_transfer/mob"
TARGETS = ["4906972", "4907182", "4906969", "4908023", "4907510", "42364659",
           "42364663", "42364609", "4908050", "4908166", "4908176"]
FOCUS = ["4906972", "4906969", "4908023"]
ARM_ORDER = ["gs_prior_full_dense", "gs_prior_full_acmp", "gs_d4_dense", "gs_d4_acmp"]
NICE = {"gs_prior_full_dense": "D dense", "gs_prior_full_acmp": "D acmp",
        "gs_d4_dense": "D4 dense", "gs_d4_acmp": "D4 acmp"}

S = json.loads((BK / "numbers_smrf.json").read_text())["arms"]
G = json.loads((BK / "numbers_gssem.json").read_text())["arms"]
BASE = json.loads((M / "baselines.json").read_text())
L = []
def w(s=""):
    L.append(s)

def fnum(x, p="{:.2f}"):
    return p.format(x) if isinstance(x, (int, float)) else "-"

w("# W_gssem_requal — D·D4 gssem read-out 재정합 (gssem | smrf 병기, 관찰만·판정 없음)")
w("")
w("> 배경: eval 이 arm 당 **gssem→smrf 순차**라 per-building cityjson/las/val3dity 가 smrf 로 덮였었음 → D·D4 의 RMS·면수·val3dity 가 smrf 기하였음.")
w("> 본 작업(PART 1)은 그 산출물을 **gssem(thesis 정본 read-out)으로 재생성**하고 smrf 는 백업 보존. EPSG:25832 · Docker · 학습/D5 무중단(CPU만). 관찰만·해석 금지.")
w("> 출처: `gssem_requal_numbers.py` → `numbers_{smrf,gssem}.json`; smrf 원본 = `gssem_requal_backup/perbuilding_smrf.tar`(cityjson+val3dity) + `ref_rms_{D,d4}_smrf.csv`. 디스크 최종 = **gssem**.")
w("")

# §0 generation unchanged
w("## §0 생성(assembled/valid-solid, REC 8동) — gssem 재-eval 불변 확인")
w("| arm | assembled/8 (gssem) | valid-solid/8 (gssem) | (참고) smrf assembled/valid |")
w("|---|---:|---:|---:|")
for cfg in ARM_ORDER:
    g = G[cfg]; s = S[cfg]
    w(f"| {NICE[cfg]} | {g['assembled_REC']} | {g['valid_solid_REC']} | {s['assembled_REC']} / {s['valid_solid_REC']} |")
w("\n(gssem 생성수치는 재-eval 전후 동일 — `gssem_requal.log` [verify] 라인 참조. smrf 는 read-out 차이로 다름, 대조용.)")
w("")

# §1 RMS
w("## §1 RMS→ref (m, orig) — gssem | smrf · mean(11동 中) + 초점 4906972·4906969·4908023")
w("| arm | mean gssem | mean smrf | 4906972 g\\|s | 4906969 g\\|s | 4908023 g\\|s |")
w("|---|---:|---:|---:|---:|---:|")
for cfg in ARM_ORDER:
    g = G[cfg]; s = S[cfg]
    foc = " | ".join(f"{fnum(g['rms_focus'][t])}\\|{fnum(s['rms_focus'][t])}" for t in FOCUS)
    w(f"| {NICE[cfg]} | {fnum(g['rms_mean'])}(n{g['rms_n']}) | {fnum(s['rms_mean'])}(n{s['rms_n']}) | {foc} |")
w("\n출처: gssem = `ref_rms_{D,d4}_gssem.csv`; smrf = `ref_rms_{D,d4}_smrf.csv`.")
w("")

# §2 facets
w("## §2 target-only 지붕 면수 (11동) — gssem | smrf · ref")
w("| bid | ref | D dn g\\|s | D ac g\\|s | D4 dn g\\|s | D4 ac g\\|s |")
w("|---|---:|---:|---:|---:|---:|")
def fc(cfg, t):
    g = G[cfg]["facets_target_only"].get(t); s = S[cfg]["facets_target_only"].get(t)
    gs = "-" if g is None else str(g); ss = "-" if s is None else str(s)
    return f"{gs}\\|{ss}"
for t in TARGETS:
    ref = BASE[f"DEBY_LOD2_{t}"]["ref_roof_surfaces"]
    w(f"| {t} | {ref} | {fc('gs_prior_full_dense',t)} | {fc('gs_prior_full_acmp',t)} | "
      f"{fc('gs_d4_dense',t)} | {fc('gs_d4_acmp',t)} |")
w("\n출처: target-only = Roofer cityjson(이웃 제외). gssem = 현 디스크(재생성); smrf = `perbuilding_smrf.tar` 스냅샷.")
w("")

# §3 val3dity codes
w("## §3 val3dity — 무효동 오류코드 (gssem | smrf), arm 별 (valid=False 인 동만)")
for cfg in ARM_ORDER:
    w(f"\n**{NICE[cfg]}**")
    w("| bid | gssem valid·codes | smrf valid·codes |")
    w("|---|---|---|")
    any_row = False
    for t in TARGETS:
        gv = G[cfg]["val3dity"].get(t); sv = S[cfg]["val3dity"].get(t)
        def fmt(v):
            if v is None:
                return "(no report)"
            return f"{'valid' if v.get('valid') else 'INVALID'}·{v.get('codes') or '[]'}"
        # show rows where either is invalid or has codes
        g_inv = gv is not None and (not gv.get("valid") or gv.get("codes"))
        s_inv = sv is not None and (not sv.get("valid") or sv.get("codes"))
        if g_inv or s_inv:
            any_row = True
            w(f"| {t} | {fmt(gv)} | {fmt(sv)} |")
    if not any_row:
        w("| (모두 valid) | — | — |")
w("\n> ⚠ **clip-level 주의**: valid/codes 는 combined clip(타깃+이웃) 리포트 기준 = eval 의 valid_solid 정의와 동일. 일부 코드는 **클립된 이웃 건물**에서 발생할 수 있음")
w("> (검증 예: gs_d4_dense 4906972 clip=INVALID·302 이나 이는 이웃 `DEBY_LOD2_4906973`의 SHELL_NOT_CLOSED 이고 타깃 4906972 feature 자체는 valid). 타깃-feature 단위 validity 는 동일 리포트의 features[] 에서 추출 가능.")
w("\n출처: gssem = 현 디스크 val3dity.json(재생성); smrf = `perbuilding_smrf.tar`. 코드: 301·302 비폐합·303 비-다양체·306/405 방향 등(val3dity 2.6.0).")
w("")

# §4 figures + §5 reproduce
w("## §4 정성 그림 — gssem 모델 렌더 (`docs/figs/W_gssem_requal/`)")
w("4906972·4906969·4908023 의 gssem 조립모델(면별색) [D-gssem | D4-gssem | LiDAR | ref]. smrf 모델은 `perbuilding_smrf.tar` 에 보존.")
w("\n## §5 재현/출처")
w("- 재-eval: `scripts/evidence_and_attributes/diagnostic_tables/run_gssem_requal.sh` (백업→gssem eval→ref_rms→numbers→verify; CPU/도커, NO GPU, gs_d5* 미접촉).")
w("- 숫자: `gssem_requal_numbers.py {smrf,gssem}` → `numbers_{smrf,gssem}.json`. 본 표: `gssem_requal_doc.py`.")
w("- 그림: `gssem_requal_figs.py`. smrf 백업: `gssem_requal_backup/perbuilding_smrf.tar` + `ref_rms_{D,d4}_smrf.csv` + `eval_*_smrf.json`.")
w("- 디스크 최종 read-out = **gssem**(이후 smrf 재실행 금지). 생성 assembled/valid-solid 불변(§0).")

(REPO / "docs/experiments/evaluation/w_gssem_requal/reports/W_gssem_requal.md").write_text("\n".join(L) + "\n")
print(f"[done] -> {REPO/'docs/experiments/evaluation/w_gssem_requal/reports/W_gssem_requal.md'}")
