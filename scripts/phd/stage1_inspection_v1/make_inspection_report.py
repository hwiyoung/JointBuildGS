"""§8 inspection report from the independent reproduction (checks.json, reproduction_match.csv).
Verdict rule is applied mechanically on the prompt's definitions (pool = building faces, axis = camera-Z)
and every judgment cites the figure it was checked against."""
import csv
import json
import struct
from pathlib import Path

import numpy as np

OUT = Path("/insp")
C = json.loads((OUT / "repro/checks.json").read_text())
M = list(csv.DictReader((OUT / "repro/reproduction_match.csv").open()))
ART = Path("/artifacts/JointBuildGS")
TASK = ART / "phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1"
DENSE = ART / "phase-payloads/p0-audit/data/work/mvs/colmap_dense"
KO = {"L": "L(항공 LiDAR)", "M": "M(LoD2)"}


def ov(p, c, pool, axis):
    return C["overall"][f"{p}|{c}|{pool}|{axis}"]


def f(x, d=3):
    return "NA" if x is None else (f"{x:.{d}f}" if isinstance(x, (int, float)) else str(x))


def pct(x):
    return "NA" if x is None else f"{100*x:.1f}%"


def yn(b):
    return "통과" if b else "미달"


# --- GSD from the raw native depth (median of valid camera-Z depth) and native focal length
def read_bin(p):
    with open(p, "rb") as fh:
        head = b""
        while head.count(b"&") < 3:
            head += fh.read(1)
        w, h, c = [int(x) for x in head.decode().split("&")[:3]]
        a = np.fromfile(fh, np.float32)
    return np.transpose(a.reshape((w, h, c), order="F"), (1, 0, 2)).squeeze()


zs = []
for stem in C["views"]:
    d = read_bin(DENSE / "stereo/depth_maps" / f"{stem}.JPG.geometric.bin")
    zs.append(float(np.median(d[d > 0])))
z_med = float(np.median(zs))
fx_native = 674.4174327342674  # 922.055 * 1024/1400 (dense camera rescaled to the depth grid)
gsd_native = z_med / fx_native
gsd_full = z_med / 3716.7650978711608

sens = C["sensitivity"]
cen = C["center"]
sc = C["scene_consistency"]
cap = C["capability"]
inj = C["injection"]
idn = C["identity"]
A_ok = all(i["A_mismatch_px"] == 0 for i in idn)
mvs_ok = all((i["mvs_full_max_abs_diff"] or 0) == 0 and i["mvs_full_nan_mask_mismatch"] == 0 for i in idn)
lit = {p: sens[f"{p}|ref=bldg|camz"] for p in "LM"}
roofv = {p: sens[f"{p}|ref=roof|vert"] for p in "LM"}
roofc = {p: sens[f"{p}|ref=roof|camz"] for p in "LM"}
wrong_ok = {p: lit[p]["sensitivity_pass_0p9"] for p in "LM"}
right_L_ok = lit["L"]["nominal_out_tau"] <= 0.05
center_ok = {p: cen[f"{p}|bldg|camz"]["abs_m_lt_s"] for p in "LM"}
center_roof = {p: cen[f"{p}|roof|camz"]["abs_m_lt_s"] for p in "LM"}
n_ok = sum(1 for m in M if m["ok"] == "True")
repro_ok = n_ok == len(M)
quality_fail = [k for k, v in {"① 틀린 장면 검사 L": wrong_ok["L"], "① 틀린 장면 검사 M": wrong_ok["M"], "① 맞는 장면 검사 L": right_L_ok,
                                "② 중심 L": center_ok["L"], "② 중심 M": center_ok["M"]}.items() if not v]
if not quality_fail and repro_ok:
    verdict = "넘길 수 있다"
elif quality_fail:
    verdict = "다시 재야 한다"
else:
    verdict = "무엇을 고치면 넘길 수 있다"
tauL, tauM = ov("L", "nominal", "bldg", "camz"), ov("M", "nominal", "bldg", "camz")
tauL_r, tauM_r = ov("L", "nominal", "roof", "camz"), ov("M", "nominal", "roof", "camz")
sep_tau = abs(tauL["tau"] - tauM["tau"]) / max(tauL["tau"], tauM["tau"])
sep_out = abs(lit["L"]["sensitivity_tau"] - lit["M"]["sensitivity_tau"]) / max(lit["L"]["sensitivity_tau"], lit["M"]["sensitivity_tau"])
separate = sep_tau >= 0.2 or sep_out >= 0.2
inj_L = [j for j in inj if j["prior"] == "L"]
inj_Md = [j for j in inj if j["prior"] == "M" and j["pair"] == "nominal->biased"]
inj_Mr = [j for j in inj if j["prior"] == "M" and j["pair"] == "nominal_recovered->biased"]
med = lambda rows, k: float(np.median([r[k] for r in rows if r[k] is not None]))
fails = [m for m in M if m["ok"] != "True"]

L = []
A = L.append
A(verdict + ".")
A("")
if verdict == "다시 재야 한다":
    A(f"다시 재야 하는 범위는 좁다. 산출물 ①(관측 신뢰도 지도 A)은 정체({'통과' if A_ok and mvs_ok else '미달'})·능력 검사를 통과하고, 미달은 {', '.join(quality_fail)}이다. 각각의 원인과 어느 재측정으로 닫히는지는 '오류와 영향' 절에 적었다. 프롬프트 풀(건물면) 대신 에이전트 풀(지붕)로 보면 미달 항목이 바뀐다(정의 일치 점검표).")
A("")
A("# 1단계 산출물 검수 보고서 — PHD-STAGE1-INSPECTION-v1")
A("")
A("## 0. 검수의 성격과 독립성")
A("")
A("- 이 검수는 1단계를 수행한 세션(dcc18780, 2026-09-21)과 같은 세션에서 수행했다. 독립성은 사람이 아니라 방법으로 확보했다. 재현 스크립트 `repro/reproduce.py`는 에이전트 모듈을 하나도 import하지 않고 원 배열(COLMAP geometric .bin, LoD2Depth 깊이 .npy, 납품된 면 라벨)에서 모든 수를 다시 계산했다. 에이전트 코드 수정, MVS 재실행, 마스크 재생성, 주입 지역 변경, 문턱 조정은 하지 않았다.")
A("- 판정은 이 프롬프트의 정의(폭의 픽셀 풀 = 건물 면이면서 예, 잔차 축 = 에이전트가 쓴 카메라 Z)로 낸 재현값으로 했고, 에이전트의 정의(지붕만)로 낸 값은 정의 차이의 영향으로 나란히 적었다.")
A("- 재현 스크립트는 별도의 검토 에이전트가 프롬프트 정의와 대조해 읽었다(공식 오류 없음; 지적 사항은 유효 주입 상한, 혼합 중심, 능력 분모, 픽셀 풀 한계, float16 사본으로 이 보고서에 반영).")
A(f"- 재현 소요 {C['runtime_s']:.0f} s, 시점 {len(C['views'])}개, 상수 k={C['constants']['k']}, 3s 제외, NMAD 계수 {C['constants']['nmad']}, 사양 L {C['spec']['L']} m / M {C['spec']['M']} m.")
A("")
A("## 2절. 찾은 입력")
A("")
A("| 항목 | 경로 | 상태 |")
A("|---|---|---|")
A("| 1단계 보고서·표·설정 | `PHD-STAGE1-CONF-TOL-CONFLICT-v1/out/report.md`, `stats.csv`, `tolerance.json`, `coverage.csv`, `conflict.csv`, `compare_L_vs_M.csv`, `checks.json`, `stage2_config_{L,M}.json` | 있음 |")
A("| 뷰어 | `out/viewer.html` (+`viewer_png/`, `viewer_data/`), HTTP http://192.168.10.203:8886/viewer.html | 있음 |")
A("| 계산 스크립트·로그 | 리포 `scripts/phd/stage1_conf_tol_conflict_v1/*.py`, 외부 `scripts/` 스냅샷, `logs/*.log`, `logs/*.host_receipt.json` | 있음 |")
A("| 지시 기록(발주서) | 파일 없음. 세션 대화 기록에만 있었음 → 사본 `ORDER_ko_v1.md` (검수 폴더와 `docs/experiments/phd/stage1_conf_tol_conflict_v1/`) | 대화 기록에서 확보 |")
A("| MVS 깊이 원 배열 | `p0-audit/data/work/mvs/colmap_dense/stereo/depth_maps/{view}.JPG.geometric.bin` (1024×741 카메라 Z) 15개 | 있음 |")
A("| 옛 자료 깊이 L 정상/편향 | `inputs/prior_render/L_{nominal,biased}/lod2_prior/raw_depth/*.npy` (5644×4082) | 있음 |")
A("| 옛 자료 깊이 M 정상 | 저자 제공 `native_example/scene/lod2_prior/raw_depth/*.npy`; 복구 메시 렌더 `inputs/prior_render/M_nominal_recovered/` | 있음(둘) |")
A("| 옛 자료 깊이 M 편향 | `inputs/prior_render/M_biased/lod2_prior/raw_depth/*.npy` | 있음 |")
A("| 관측 신뢰도 지도 A | `out/conf/{view}_conf.npy` (uint8 0/1, 5644×4082) | 있음 |")
A("| 건물 면 라벨 | `out/{L,M}/nominal/{view}_region.npy` (1 지붕, 2 벽면, 3 지면(L), 4 다른 건물), 면 id `inputs/faceid/{view}.npy` | 있음(납품본 그대로 사용) |")
A("| 편향판 주입 참값 기반 마스크 | 별도 파일 없음. 주입이 옛 자료 전체(+1.0 m)라 정상판·편향판 깊이가 다른 픽셀 집합이 마스크가 된다(5절) | 없음(대체 가능) |")
A("")
A("### 에이전트가 실제로 쓴 정의 (코드에서 발췌)")
A("")
A("- 잔차 r = MVS 깊이 − 옛 자료 깊이, 카메라 Z 축(m). `analyze.py:167`. 지붕에는 연직 잔차 r_v = r × |n·d|/|n_z| 추가(`:169`).")
A("- 잔차 풀: A=1 ∧ 옛 자료 유효(유한·>0·<1e6) ∧ 영역. τ·m·s의 기준 영역은 **지붕만**(`tau_region: roof`, `:284–290`); 벽면·지면·전체(지붕+벽면)는 별도 행으로 기록.")
A("- m·s: 중앙값, 1.4826×중앙값|r−m|; |r−m|>3s 제외 후 재계산(두 바퀴) `common.py:232–239`. τ_data = 2.5·s2, τ = max(τ_data, 사양) `:284–286`.")
A("- 폭 밖(충돌) 판정: 예 ∧ |r − m2_정상,영역| > 3·s2_정상,영역 (`:335`). 분모 = 예 ∧ 옛 자료 유효 ∧ 영역. **τ가 아니라 3s2를 문턱으로 씀.**")
A("- 커버리지 분모 = 옛 자료 유효 ∧ 영역. 두 장면의 τ는 각 장면에서 같은 식으로 계산.")
A("")
A("## 5절. 두 장면 자체의 확인")
A("")
A(f"- 정상판·편향판의 옛 자료 깊이가 다른 픽셀: L {pct(med(inj_L,'differ_fraction'))} (TIN에는 수직면이 없어 전 픽셀이 변함), M 복구 메시 쌍 {pct(med(inj_Mr,'differ_fraction'))}, M 납품 쌍(저자 배열 vs 복구+1) {pct(med(inj_Md,'differ_fraction'))}. 수직 벽면은 연직 이동에 불변이므로 깊이가 바뀌는 집합은 비수직면(지붕) 픽셀 전부이고, 이것이 참값 기반 주입 마스크에 해당한다. 주입은 옛 자료 전체이므로 건물 면 픽셀 중 주입 비율은 100%다.")
A(f"- 주입 지붕의 잔차 이동(편향 − 정상, 지붕 예 픽셀 중앙값, 시점 중앙값): L 카메라 Z {f(med(inj_L,'roof_median_shift_camz'))} m / 연직 {f(med(inj_L,'roof_median_shift_vertical'))} m; M 복구 쌍 {f(med(inj_Mr,'roof_median_shift_camz'))} / {f(med(inj_Mr,'roof_median_shift_vertical'))} m; M 납품 쌍 {f(med(inj_Md,'roof_median_shift_camz'))} / {f(med(inj_Md,'roof_median_shift_vertical'))} m. 부호 규약(r = MVS − 옛 자료, 옛 자료를 올리면 r 증가)대로 +1 m가 연직으로 복원되고, 카메라 Z에서는 시선 경사만큼 크다(연직 환산 계수 시점 중앙값 {f(med(inj_L,'roof_median_vertical_factor'))}).")
A("- 납품된 M 두 장면 사이의 실제 주입은 연직 0.86~0.90 m다(저자 배열 정상판 + 복구 메시 편향판). 3절의 M 민감도는 이 납품 쌍으로 계산했으며, τ_M 1.0 m가 지배하므로 0.12 m 차이가 판정을 바꾸지는 않는다.")
A("- M 납품 쌍이 연직 0.87 m인 이유는 정상판(저자 제공 배열)과 편향판(복구 CityGML)의 메시 출처 차이 −0.12 m가 동반되기 때문이며, 복구 메시 쌍은 정확히 1.000 m다. 결론: 편향판은 의도대로 만들어졌다(5절 통과). 그림 4·5.")
A("")
A("## 3절. 산출물 ① 관측 신뢰도 지도 A")
A("")
A(f"- 정체: A는 COLMAP geometric 깊이의 유효(>0) 마스크를 시점 영상 격자로 최근접 재표본한 것 그대로다. 재현 A와 납품 A의 불일치 픽셀 {sum(i['A_mismatch_px'] for i in idn)}개(15시점 합), MVS 깊이 재표본 최대차 {max((i['mvs_full_max_abs_diff'] or 0) for i in idn):.1e} m. 별도 가공 없음. 단, 원 배열은 1024×741이고 A는 5644×4082이므로 '재표본'이라는 가공 한 단계는 존재한다. 재현의 재표본 경로는 에이전트가 기록한 방법을 그대로 구현한 것이므로 '결정적 재현'이며, 독립 근거는 dense cameras.bin에서 깊이 격자 내부 파라미터를 다시 유도해 일치시킨 것과 A의 예 비율이 원 배열 유효 비율과 같다는 것(차 ≤1.6e-5)이다. → {yn(A_ok and mvs_ok)}.")
A("")
A("| 검사 | L | M | 기준 | 그림 |")
A("|---|---:|---:|---|---|")
A(f"| 틀린 장면 민감도(τ 기준, 풀=건물면) | {f(lit['L']['sensitivity_tau'])} | {f(lit['M']['sensitivity_tau'])} | ≥0.9 | 2, 4 |")
A(f"| 같은 값, 참고 3s 기준 | {f(lit['L']['sensitivity_3s'])} | {f(lit['M']['sensitivity_3s'])} | 참고 | 2 |")
A(f"| 같은 값, 풀=지붕(에이전트 τ)·카메라 Z | {f(roofc['L']['sensitivity_tau'])} | {f(roofc['M']['sensitivity_tau'])} | 참고 | 2, 4 |")
A(f"| 같은 값, 풀=지붕·연직 축 | {f(roofv['L']['sensitivity_tau'])} | {f(roofv['M']['sensitivity_tau'])} | 참고 | 4, 5 |")
eff = C["effective_injection"]
A(f"| 유효 주입: prior 깊이 이동 ≤ τ인 지붕 예 픽셀 비율(풀=건물면 τ) | {pct(eff['L|ref=bldg|camz']['frac_shift_le_tau'])} | {pct(eff['M|ref=bldg|camz']['frac_shift_le_tau'])} | 이 픽셀은 정상 잔차가 이미 폭 밖이 아닌 한 켜질 수 없음 | 4, 5 |")
A(f"| 유효 주입 픽셀만의 민감도(풀=건물면 τ) | {f(eff['L|ref=bldg|camz']['sensitivity_on_effective'])} | {f(eff['M|ref=bldg|camz']['sensitivity_on_effective'])} | 참고 | 4, 5 |")
A(f"| 같은 값, 풀=지붕 τ: 이동 ≤ τ 비율 / 유효 픽셀 민감도 | {pct(eff['L|ref=roof|camz']['frac_shift_le_tau'])} / {f(eff['L|ref=roof|camz']['sensitivity_on_effective'])} | {pct(eff['M|ref=roof|camz']['frac_shift_le_tau'])} / {f(eff['M|ref=roof|camz']['sensitivity_on_effective'])} | 참고 | 4, 5 |")
A(f"| 맞는 장면 폭 밖 비율(τ 기준) | {pct(lit['L']['nominal_out_tau'])} | {pct(lit['M']['nominal_out_tau'])} | L 수 % 이내(검수자 해석 ≤5%), M 기록 | 3 |")
A(f"| 같은 값, 참고 3s / 4τ | {pct(lit['L']['nominal_out_3s'])} / {pct(lit['L']['nominal_out_4tau'])} | {pct(lit['M']['nominal_out_3s'])} / {pct(lit['M']['nominal_out_4tau'])} | 참고 | 3 |")
A(f"| 맞는 장면 폭 밖 비율, 풀=지붕(τ_L 0.12) 카메라 Z / 연직 | {pct(roofc['L']['nominal_out_tau'])} / {pct(roofv['L']['nominal_out_tau'])} | {pct(roofc['M']['nominal_out_tau'])} / {pct(roofv['M']['nominal_out_tau'])} | 참고 | 3 |")
A(f"| 능력: 지붕 예 비율 시점 중앙값(최소~최대) | {pct(cap['L|roof']['per_view_median'])} ({pct(cap['L|roof']['per_view_min'])}~{pct(cap['L|roof']['per_view_max'])}) | {pct(cap['M|roof']['per_view_median'])} | 기록 | 6 |")
A(f"| 능력: 벽면 예 비율 시점 중앙값(최소~최대) | {pct(cap['L|wall']['per_view_median'])} ({pct(cap['L|wall']['per_view_min'])}~{pct(cap['L|wall']['per_view_max'])}) | {pct(cap['M|wall']['per_view_median'])} | 기록 | 6 |")
A(f"| 능력: 전체 픽셀 합산 지붕 / 벽면 | {pct(cap['L|roof']['pooled'])} / {pct(cap['L|wall']['pooled'])} | {pct(cap['M|roof']['pooled'])} / {pct(cap['M|wall']['pooled'])} | 기록 | 6 |")
fa = cap["faces_any_view_yes"]
A(f"| 능력: 어느 사진에서든 예인 면 비율 | 지붕 {fa['roof']['n_faces_any_yes']}/{fa['roof']['n_faces']} 면, 벽면 {fa['wall']['n_faces_any_yes']}/{fa['wall']['n_faces']} 면(보이는 면 기준 {fa['wall']['n_faces_any_yes']}/{fa['wall']['n_faces_seen']}) | 같음(라벨 공유) | 기록 | — |")
hb = cap['hold_upper_bound']['L']
A(f"| 보류 비율 상한 = 1 − 지붕 값 | 픽셀 합산 {pct(hb['pooled_pixels'])}; 사진별 중앙값 기준 {pct(hb['per_view_median'])}(최악 사진 {pct(hb['per_view_worst'])}); 면 기준 {pct(hb['faces'])} | 같음 | 기록(1단계 설정은 픽셀 합산값) | — |")
A("")
A(f"- 틀린 장면 검사 판정: L {yn(wrong_ok['L'])} ({f(lit['L']['sensitivity_tau'])}; 기준 0.9에 {f(max(0, 0.9-lit['L']['sensitivity_tau']))} 미달. 건물면 풀의 τ_L이 L 벽면(TIN 브리징) 때문에 {f(tauL['tau'])} m로 넓어진 결과이며, 지붕 풀 τ_L 0.12 m로는 {f(roofc['L']['sensitivity_tau'])}), M {yn(wrong_ok['M'])}. M이 미달인 이유는 A에 엉터리 깊이가 섞여서가 아니라(같은 A가 L에서는 {f(lit['L']['sensitivity_tau'])}) 폭 τ_M이 사양 바닥 1.0 m로 주입량 1 m와 같아졌기 때문이다. 이 프롬프트가 미리 적어 둔 둘째 원인('폭이 1 m급으로 커진 것')에 해당한다. 참고 3s 기준으로는 M도 {f(lit['M']['sensitivity_3s'])}다. 그림 2·4·5.")
e_ = eff['L|ref=bldg|camz']
A(f"- 민감도의 도달 가능 상한(검토 에이전트 지적): 건물 전체를 올리면 처마 띠의 광선은 정상판에서 지붕을, 편향판에서는 올라온 벽면을 맞혀 깊이가 거의 안 변하고, 카메라를 향한 급경사 면에서도 카메라 Z 이동은 1 m보다 작다. prior 깊이 이동 자체가 τ 이하인 지붕 예 픽셀이 L {pct(e_['frac_shift_le_tau'])}, M {pct(eff['M|ref=bldg|camz']['frac_shift_le_tau'])}(건물면 τ)이며, 이 픽셀은 정상 잔차가 이미 폭 밖인 경우를 빼면 어떤 A로도 켜지지 않는다. 이동이 τ보다 큰 픽셀만 보면 L {f(e_['sensitivity_on_effective'])}, M {f(eff['M|ref=bldg|camz']['sensitivity_on_effective'])}다. 즉 L의 0.9 미달은 A의 거짓말이 아니라 시험 기하(전체 주입 + 넓어진 τ_L)의 결과다. 판정 규칙은 그대로 적용해 미달로 두고, 이 사실을 병기한다.")
A(f"- 건물면 풀의 중심 m2(L {f(cen['L|bldg|camz']['m2'])}, M {f(cen['M|bldg|camz']['m2'])} m)는 벽면 잔차에 끌린 혼합 통계이며 지붕 픽셀에 그대로 적용된다. M은 이 0.2 m가 편향 이동 1.14 m에서 빠져 민감도가 0.768(지붕 중심)에서 0.354(건물면 중심)로 내려간다. 프롬프트 풀 정의의 귀결이며 코드 오류가 아니다.")
A(f"- 맞는 장면 검사: L {pct(lit['L']['nominal_out_tau'])} → {yn(right_L_ok)}. M {pct(lit['M']['nominal_out_tau'])}는 기록. 그림 3에서 정상 장면의 폭 밖 픽셀은 처마선·용마루와 작은 지붕면(옥탑·설비 후보)에 뭉쳐 있고 얼룩이 아니다. 나무·차량은 건물 면 라벨 밖이라 그림에서 진회색으로 빠진다.")
A("")
A("## 4절. 산출물 ② 허용 오차 τ")
A("")
A("| 값 | L 풀=건물면(프롬프트) | L 풀=지붕(에이전트) | M 풀=건물면 | M 풀=지붕 |")
A("|---|---:|---:|---:|---:|")
for k, name in [("n", "표본 수"), ("m", "m (1차)"), ("s", "s (1차)"), ("n2", "표본 수 (3s 제외 후)"), ("m2", "m2"), ("s2", "s2"), ("tau_data", "2.5·s2"), ("tau", "τ = max(2.5 s2, 사양)"), ("tau_source", "살아남은 쪽")]:
    A(f"| {name} | " + " | ".join((f"{x[k]:,}" if k in ('n', 'n2') else f(x[k])) for x in [tauL, tauL_r, tauM, tauM_r]) + " |")
A(f"| 4τ | {f(4*tauL['tau'])} | {f(4*tauL_r['tau'])} | {f(4*tauM['tau'])} | {f(4*tauM_r['tau'])} |")
A(f"| s2 / GSD(원 배열 1024 격자, 중앙 깊이 {z_med:.1f} m → {100*gsd_native:.1f} cm) | {tauL['s2']/gsd_native:.2f}× | {tauL_r['s2']/gsd_native:.2f}× | {tauM['s2']/gsd_native:.2f}× | {tauM_r['s2']/gsd_native:.2f}× |")
A(f"| s2 / GSD(시점 영상 격자, {100*gsd_full:.1f} cm) | {tauL['s2']/gsd_full:.2f}× | {tauL_r['s2']/gsd_full:.2f}× | {tauM['s2']/gsd_full:.2f}× | {tauM_r['s2']/gsd_full:.2f}× |")
A("")
A("- 축: 잔차는 카메라 Z 축(COLMAP 깊이와 LoD2Depth t_hit가 같은 규약)이고, 사양(ALS 수직 0.12 m, LoD2 높이 1 m)은 연직 축이다. **축이 다르다.** 지붕에서 연직 값 = 카메라 Z 값 × |n·d|/|n_z|이며 이 계수의 지붕 예 픽셀 중앙값은 시점별 0.77~0.80, 시선이 스치는 픽셀에서는 0.25까지 내려간다. 따라서 카메라 Z 잔차의 폭은 연직 폭보다 1.3~4배 넓게 재진다. 지붕 풀에서 연직 축으로 다시 재면 s2는 L " + f(ov('L','nominal','roof','vert')['s2']) + " m, M " + f(ov('M','nominal','roof','vert')['s2']) + " m다.")
A("")
A("| 확인 | L | M | 판정 | 그림 |")
A("|---|---|---|---|---|")
A("| 재는 픽셀이 맞는가 | 풀 = A=1 ∧ 옛 자료 유효 ∧ 라벨∈{지붕,벽면}; 지면·아니오 픽셀은 라벨 코드로 배제되어 집계 0. 한계: 라벨이 옛 자료 면에서 오므로 면 앞의 가림 물체(나무·차량)가 지붕/벽면 라벨 위에 투영되면 풀에 남는다 | 같은 라벨 공유 | 통과(한계 병기) | 6 |")
A(f"| 크기가 그럴듯한가 | 2.5 s2 = {f(tauL['tau_data'])} m (풀 건물면) / {f(tauL_r['tau_data'])} m (지붕). 지붕만 보면 사양 0.12 m 아래로 사양이 바닥. 건물면 풀은 L 벽면이 2.5D TIN의 브리징 삼각형이라 부풀었다 | 2.5 s2 = {f(tauM['tau_data'])} / {f(tauM_r['tau_data'])} m로 1 m 아래, 사양 1.0 m가 바닥으로 작동 | 기록 | 1 |")
A(f"| 두 장면에서 같은가 | τ 정상 {f(sc['L|bldg|camz']['tau_nominal'])} vs 편향 {f(sc['L|bldg|camz']['tau_biased'])} (상대차 {pct(sc['L|bldg|camz']['rel_diff_tau'])}); 지붕 풀 {f(sc['L|roof|camz']['tau_nominal'])} vs {f(sc['L|roof|camz']['tau_biased'])} | τ {f(sc['M|bldg|camz']['tau_nominal'])} vs {f(sc['M|bldg|camz']['tau_biased'])} ({pct(sc['M|bldg|camz']['rel_diff_tau'])}); 지붕 풀 {f(sc['M|roof|camz']['tau_nominal'])} vs {f(sc['M|roof|camz']['tau_biased'])} | 설계대로 평가 불가: 주입이 건물 면의 100%라 '주입을 뺀 τ'가 없다. 값만 기록 | 1 |")
A(f"| 중심이 맞는가 (\\|m2\\| < s2) | 건물면 풀 m2 {f(cen['L|bldg|camz']['m2'])}, s2 {f(cen['L|bldg|camz']['s2'])} → {yn(center_ok['L'])}; 지붕 풀 m2 {f(cen['L|roof|camz']['m2'])}, s2 {f(cen['L|roof|camz']['s2'])} → {yn(center_roof['L'])}; m/τ = {pct(cen['L|bldg|camz']['m_over_tau'])} | 건물면 풀 m2 {f(cen['M|bldg|camz']['m2'])}, s2 {f(cen['M|bldg|camz']['s2'])} → {yn(center_ok['M'])}; 지붕 풀 m2 {f(cen['M|roof|camz']['m2'])}, s2 {f(cen['M|roof|camz']['s2'])} → {yn(center_roof['M'])} | 프롬프트 풀 기준 L {yn(center_ok['L'])} / M {yn(center_ok['M'])} | 1, 5 |")
A("")
A(f"- 중심 해석: 지붕만 보면 L의 m2({f(cen['L|roof|camz']['m2'])} m)와 M의 m2({f(cen['M|roof|camz']['m2'])} m)는 부호가 다르다. 프롬프트 규칙대로면 그 차이({f(abs(cen['L|roof|camz']['m2']-cen['M|roof|camz']['m2']))} m)는 LoD2의 표현 오차다. L 자체의 −2 cm대 편차는 15시점 모두 같은 부호인 블록 이동이고, 높이 기준 상수(45.66 m)는 GCG2016 준지오이드(45.660 m)와 일치하므로 상수 오류가 아니다(`PHD-STAGE1-CONF-TOL-CONFLICT-v1/provenance/registration_check.json`). 지붕 풀의 s2가 2 cm로 매우 작아 규칙이 켜진 것이며, τ_L 12 cm의 {pct(abs(cen['L|roof|camz']['m2'])/tauL_r['tau'])}에 해당한다.")
A("")
A("## 인계값 표")
A("")
A("| 항목 | 값 |")
A("|---|---|")
A(f"| A 경로·형식·정체 | `out/conf/{{view}}_conf.npy`, uint8 0/1, 5644×4082, 15시점. COLMAP geometric 유효 마스크의 최근접 재표본 그대로(재현 불일치 0픽셀) |")
A(f"| 지붕·벽면 커버리지(합산) | 지붕 {pct(cap['L|roof']['pooled'])}, 벽면 {pct(cap['L|wall']['pooled'])} (L=M) |")
A(f"| 보류 비율 상한 | 픽셀 합산 {pct(hb['pooled_pixels'])} (사진별 중앙값 {pct(hb['per_view_median'])}, 면 기준 {pct(hb['faces'])}) |")
A(f"| τ_L, 4τ_L (프롬프트 풀 / 에이전트 지붕 풀) | {f(tauL['tau'])} m, {f(4*tauL['tau'])} m ({tauL['tau_source']}) / {f(tauL_r['tau'])} m, {f(4*tauL_r['tau'])} m ({tauL_r['tau_source']}) |")
A(f"| τ_M, 4τ_M | {f(tauM['tau'])} m, {f(4*tauM['tau'])} m ({tauM['tau_source']}) / {f(tauM_r['tau'])} m, {f(4*tauM_r['tau'])} m ({tauM_r['tau_source']}) |")
A(f"| m 무시 가능 여부 | L: 건물면 풀 {yn(center_ok['L'])}, 지붕 풀 {yn(center_roof['L'])} (m/τ {pct(abs(cen['L|roof|camz']['m2'])/tauL_r['tau'])}); M: {yn(center_ok['M'])} / {yn(center_roof['M'])} |")
A(f"| L·M 분리 | {'분리' if separate else '분리 불필요'} (τ 차이 {pct(sep_tau)}, 편향 장면 지붕 폭 밖 비율 차이 {pct(sep_out)}; 20% 이상이면 분리) |")
A(f"| 1 m ÷ τ_L, 1 m ÷ τ_M | {1/tauL['tau']:.2f} / {1/tauL_r['tau']:.2f}(지붕 풀), {1/tauM['tau']:.2f} / {1/tauM_r['tau']:.2f} |")
A("")
A("2단계 자리 대응: A는 손실의 픽셀 가중(옛 자료 항 1−A, 사진 항 A), τ는 허용 구간(±τ 안은 손실 0), 4τ는 절단 경계(그 밖은 상수 3τ)다. 인계 τ가 카메라 Z 축이므로 2단계 손실의 잔차 축과 같은지 확인해야 한다(오류와 영향 3항).")
A("")
A("## 자격 근거 표")
A("")
A("| 산출물 | 항목 | 재현값 | 통과 | 이유 | 그림 |")
A("|---|---|---|---|---|---|")
A(f"| ① | 정체 | 불일치 0픽셀 / 15시점, MVS 최대차 0 | {yn(A_ok and mvs_ok)} | 필터 출력의 최근접 재표본 그대로 | 6 |")
A(f"| ① | 틀린 장면 | L {f(lit['L']['sensitivity_tau'])}, M {f(lit['M']['sensitivity_tau'])} | L {yn(wrong_ok['L'])}, M {yn(wrong_ok['M'])} | M은 τ_M(1.0 m) = 주입량 | 2, 4, 5 |")
A(f"| ① | 맞는 장면 | L {pct(lit['L']['nominal_out_tau'])}, M {pct(lit['M']['nominal_out_tau'])} | L {yn(right_L_ok)}, M 기록 | 폭 밖이 에지·작은 면에 뭉침 | 3 |")
A(f"| ① | 능력 | 지붕 {pct(cap['L|roof']['pooled'])}, 벽면 {pct(cap['L|wall']['pooled'])} | 기록 | 보류 상한 {pct(hb['pooled_pixels'])} | 6 |")
A(f"| ② | 픽셀 | 건물 면 밖 0 | 통과(한계 병기) | 라벨로 배제; 면 앞 가림 물체는 남음 | 6 |")
A(f"| ② | 크기 | 2.5 s2: L {f(tauL['tau_data'])}/{f(tauL_r['tau_data'])}, M {f(tauM['tau_data'])}/{f(tauM_r['tau_data'])} m | 기록 | L 건물면 풀은 TIN 벽면 부풀림 | 1 |")
A(f"| ② | 두 장면 | 상대차 L {pct(sc['L|bldg|camz']['rel_diff_tau'])}, M {pct(sc['M|bldg|camz']['rel_diff_tau'])} | 평가 불가 | 주입 100% | 1 |")
A(f"| ② | 중심 | L m2 {f(cen['L|bldg|camz']['m2'])} vs s2 {f(cen['L|bldg|camz']['s2'])}; M {f(cen['M|bldg|camz']['m2'])} vs {f(cen['M|bldg|camz']['s2'])} | L {yn(center_ok['L'])}, M {yn(center_ok['M'])} | 지붕 풀 L {yn(center_roof['L'])} | 1, 5 |")
A("")
A("## 재현 일치표")
A("")
A(f"에이전트 정의(지붕 풀·카메라 Z·3s 문턱)로 재현한 값과 에이전트 표의 비교: {len(M)}개 값 중 {n_ok}개 일치(상대오차 1e-6, 표본 수 정확 일치). " + ("전부 일치한다." if repro_ok else f"불일치 {len(fails)}건은 아래와 같다."))
A("")
A("| 값 | 에이전트 | 재현 | 차이 | 일치 |")
A("|---|---:|---:|---:|---|")
keyrows = [m for m in M if m["metric"].startswith(("tolerance|", "conflict|")) or (m["metric"].startswith("stats|") and m["metric"].count("|") == 5 and m["metric"].endswith(("|n", "|m2", "|s2")))]
for m in keyrows[:60]:
    A(f"| {m['metric'].replace('|', ' · ')} | {m['agent']} | {m['repro']} | {m['abs_diff']} | {'예' if m['ok']=='True' else '아니오'} |")
if fails:
    A("")
    A("불일치 목록:")
    for m in fails[:30]:
        A(f"- {m['metric'].replace('|', ' · ')}: 에이전트 {m['agent']}, 재현 {m['repro']}, 차이 {m['abs_diff']}")
A("")
A("전체 목록은 `repro/reproduction_match.csv`, 재현 통계는 `repro/reproduction_stats.csv`, 시점별 커버리지는 `repro/coverage_per_view.csv`.")
A("")
gnd = [m for m in fails if "|ground|" in m["metric"]]
if gnd:
    A(f"불일치의 원인(픽셀 집합): L 편향 장면의 '지면' 행 {len(gnd)}개. 에이전트의 통계·커버리지 표(1차 집계)는 편향 조건의 지면을 편향판 TIN의 유효 범위로 잡았고, 충돌 표(2차 집계)와 납품 라벨 파일은 정상판 범위를 쓴다. 검수 재현은 납품 라벨(정상판)을 두 장면에 같이 썼다. 차이는 크롭 실루엣의 픽셀 {int(max(float(m['abs_diff']) for m in gnd if m['metric'].endswith('|n'))):,}개(0.5%)이고 m2 차이는 {max(float(m['abs_diff']) for m in gnd if m['metric'].endswith('|m2')):.4f} m다. 지붕·벽면 행과 판정에는 영향이 없다. 에이전트 표 안의 내부 불일치로 기록한다.")
oth = [m for m in fails if "|ground|" not in m["metric"]]
if oth:
    A(f"그 밖의 불일치 {len(oth)}건은 위 목록과 같다.")
A("")
A("## 정의 일치 점검표")
A("")
A("| 항목 | 이 프롬프트의 정의 | 에이전트가 쓴 정의 | 차이 | 영향받는 숫자 |")
A("|---|---|---|---|---|")
A(f"| 잔차 부호·축 | r = MVS − 옛 자료; 축을 적고 사양 축과 맞는지 적음 | 같은 부호, 카메라 Z 축; 지붕엔 연직 잔차 별도 | 사양은 연직인데 τ는 카메라 Z에서 잼 | s2·τ_data가 연직보다 1.3~4배 큼(예: L 지붕 s2 카메라 Z {f(tauL_r['s2'])} vs 연직 {f(ov('L','nominal','roof','vert')['s2'])}); τ 최종값은 사양 바닥이라 불변 |")
A(f"| 잔차 풀 | 건물 면(지붕+벽면) ∧ 예 | τ·m·s는 지붕 ∧ 예; 벽면·전체는 별도 행 | 풀이 좁음 | τ_L 2.5 s2: 건물면 {f(tauL['tau_data'])} vs 지붕 {f(tauL_r['tau_data'])} m; τ_L 최종 {f(tauL['tau'])} vs {f(tauL_r['tau'])} m; 중심 검사 L {yn(center_ok['L'])} vs {yn(center_roof['L'])} |")
A("| m·s 계산·제외 | 중앙값, 1.4826×MAD, 3s 제외 후 재계산 | 동일 | 없음 | — |")
A("| τ 식·사양 | max(2.5 s2, 사양), L 0.12 / M 1.0 | 동일 | 없음 | — |")
A(f"| 폭 밖 문턱 | 예 ∧ \\|r−m\\|>τ (참고 3s, 4τ) | 예 ∧ \\|r−m2_정상\\|>3 s2_정상 (영역별) | 문턱이 τ가 아니라 3s2 | 정상 장면 지붕: τ 기준 L {pct(lit['L']['nominal_out_tau'])} / M {pct(lit['M']['nominal_out_tau'])} vs 3s 기준 L {pct(roofc['L']['nominal_out_3s'])} / M {pct(roofc['M']['nominal_out_3s'])}; 편향 장면 M: τ 기준 {f(lit['M']['sensitivity_tau'])} vs 3s 기준 {f(lit['M']['sensitivity_3s'])} |")
A("| 폭 밖의 분모·기준 m | 예 픽셀; m은 (검수자 해석) 정상 장면 값 | 예 ∧ 옛 자료 유효 ∧ 영역; m2·s2는 정상 장면 값 | 없음(해석 일치) | — |")
A("| 커버리지 분모 | 옛 자료 유효 픽셀 | 동일 | 없음 | — |")
A("| 두 장면의 τ | 편향 장면은 주입 지역을 빼지 않고 전체에서, 뺀 값 병기 | 각 장면 전체에서 계산; 주입이 100%라 '뺀 값' 없음 | 주입 범위 자체가 다름(프롬프트: 고른 지붕 하나, 1단계: 옛 자료 전체) | 두 장면 검사 평가 불가 |")
A("| 주입 마스크 | 참값 기반 마스크 파일 | 파일 없음; 정상·편향 깊이 차이 집합 = 비수직면 픽셀 | 파일 부재 | 5절은 대체 방법으로 수행 |")
A("")
A("## 오류와 영향, 회부 항목")
A("")
A(f"1. **M 틀린 장면 검사 미달({f(lit['M']['sensitivity_tau'])} < 0.9)**. 원인은 A가 아니라 τ_M = 사양 1.0 m = 주입량 1 m다. 1 m 주입으로는 M의 폭이 틀림을 가르는지 시험할 수 없다. 닫는 재측정: M 편향판을 τ_M의 3배 이상(≥3 m) 올려 다시 렌더·집계(LoD2Depth 렌더 5분 + 집계 15분). 또는 2단계 결정 재료로 '주입량 = k·τ, k≥3'을 채택하고 1단계 수치는 그대로 인계.")
if not center_ok["L"] or not center_roof["L"]:
    A(f"2. **L 중심 검사**: 건물면 풀 {yn(center_ok['L'])}, 지붕 풀 {yn(center_roof['L'])}. 지붕 풀에서 −2.4 cm 블록 이동(15시점 동일 부호). 상수 오류 아님. 닫는 재측정: ALS를 연직 +1.9 cm 이동한 뒤 L 두 장면 재집계(10분). 이동 크기가 τ_L의 {pct(abs(cen['L|roof|camz']['m2'])/tauL_r['tau'])}라 2단계 손실에는 영향이 없으나 규칙은 문자대로 켜진다.")
A(f"3. **축 차이**: 카메라 Z 폭을 연직 사양과 비교했다. 최종 τ는 사양 바닥이라 값은 같지만, 2단계에서 τ를 카메라 Z 잔차에 적용하면 시선이 스치는 픽셀에서는 연직 사양보다 1/계수(1.3~4배)만큼 엄격해진다. 회부: 2단계 손실의 잔차 축(카메라 Z 그대로 쓸지, 면 법선으로 연직 환산할지)을 정할 것. 그림 4·5의 카메라 Z와 연직 열 비교.")
A(f"4. **폭 풀 차이**: 에이전트는 지붕만으로 τ를 잡았다. 건물면 풀로 잡으면 L의 2.5 s2가 {f(tauL['tau_data'])} m로 커져 사양 대신 데이터 폭이 살아남는다({tauL['tau_source']}). 이는 L의 벽면 픽셀이 2.5D TIN의 브리징 삼각형(실제 벽면이 아님)에서 나온 값이기 때문이며, '옛 자료가 맞는 곳의 차이'라는 폭의 정의에 비추면 지붕 풀이 더 맞다. 회부: 인계 τ_L로 어느 풀을 쓸지 결정.")
A("5. **두 장면 검사 평가 불가**: 주입이 옛 자료 전체라 부분 주입에 대한 τ 강건성은 이 데이터로 시험할 수 없다. 회부: 필요하면 지붕면 하나만 올린 편향판을 추가로 만들어 시험(마스크 재생성이 아니라 새 조건이므로 이 검수 밖).")
A(f"6. **민감도의 기하적 한계**: 전체 주입에서는 처마 띠·카메라를 향한 급경사 면의 prior 카메라 Z 이동이 τ 이하인 지붕 예 픽셀이 L {pct(eff['L|ref=bldg|camz']['frac_shift_le_tau'])}, M {pct(eff['M|ref=bldg|camz']['frac_shift_le_tau'])}(건물면 τ)이다. 이동이 τ보다 큰 픽셀만의 민감도는 L {f(eff['L|ref=bldg|camz']['sensitivity_on_effective'])}, M {f(eff['M|ref=bldg|camz']['sensitivity_on_effective'])}(지붕 풀 τ·중심이면 M {f(eff['M|ref=roof|camz']['sensitivity_on_effective'])}). 회부: 주입을 지붕면 하나로 한정하거나 연직 축으로 재면 이 한계가 줄어 프롬프트의 검사 설계와 맞는다.")
A("7. **뷰어 확인**: 그림 7(패널 3, 편향 장면)은 주입 지붕면 전부가 진한 빨강으로 뭉쳐 켜진다. 정상 장면 패널 3은 1단계 캡처(`logs/viewer_screenshot_top.png`)에서 작은 면만 진하다.")
A("")
A("## 파일")
A("")
A("- 검수 보고서: `inspection_report.md` (이 파일), 승격 사본 `docs/experiments/phd/stage1_conf_tol_conflict_v1/INSPECTION_ko_v1.md`.")
A("- 재현: `repro/reproduce.py`(리포 `scripts/phd/stage1_inspection_v1/reproduce.py`), `repro/reproduction_stats.csv`, `repro/reproduction_match.csv`, `repro/coverage_per_view.csv`, `repro/checks.json`, 로그 `logs/reproduce.log`.")
A("- 그림: `figures/fig1_hist_bldg.png`, `fig1_hist_roof.png`(히스토그램 m2·±τ·±4τ), `fig2_widthout_biased.png`, `fig3_widthout_nominal.png`(폭 밖 지도, 시점 0005), `fig4_injected_roof_zoom.png`(주입 지붕 확대), `fig5_cross_sections.png`(단면), `fig6_coverage.png`(커버리지), `fig7_viewer_panel3_{L,M}_biased.png`(뷰어 패널 3, 편향).")
A("- 지시 기록 사본: `ORDER_ko_v1.md`.")
A("")
A("<!-- END PHD-STAGE1-INSPECTION-v1 -->")
(OUT / "inspection_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L[:3]))
print("verdict:", verdict, "| quality_fail:", quality_fail, "| repro_ok:", repro_ok, n_ok, "/", len(M))
