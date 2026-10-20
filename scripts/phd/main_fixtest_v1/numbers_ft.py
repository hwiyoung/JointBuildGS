"""PHD-MAIN-FIXTEST-v1 13 숫자표 (jointbuildgs:dev, CPU; run_step_ft.sh): the number table the user pastes into the conversation.
Order of the file (order 13): the prediction-vs-result table, the item-1 w table, then one table per place and metric (tables_ft.py's blocks
in FT/tables/numbers_all.md: rows = the six cases, cells = one value each, `*` under 10,000 samples, 표본 부족 under 100, 결과 없음, 관문).
Split into files of at most 20,000 characters at block boundaries.
  python numbers_ft.py
Writes FT/numbers/고친판시험_숫자표_v1.md (and _v1_2.md, ... when needed); sync_docs_ft.sh copies them to the docs folder.
scientific_verdict: null."""
import json
from pathlib import Path

PH = Path("/ph")
FTP = PH / "main_fixtest_v1/PHD-MAIN-FIXTEST-v1"
T = FTP / "tables"
OUT = FTP / "numbers"
LIMIT = 20000
SEE = {"A1": "코드 2의 거리와 치우침", "A2": "영상이 틀린 곳의 거리", "A3": "모든 곳의 거리와 R(τ)", "A4": "코드 2의 거리와 치우침",
       "A5": "곡선의 1~1.5τ, 1.5~2τ 구간", "A6": "코드 11", "A7": "코드 4", "A8": "9.1의 4번",
       "B1": "코드 4", "B2": "코드 4, 코드 13", "B3": "코드 4, 코드 13", "B4": "그 곳들의 거리와 R(τ)", "B5": "9.1의 5번"}


def vg(v):
    return v["verdict"] + (f" ({v['grade']})" if v.get("grade") else "")


def main():
    P = json.loads((T / "predictions_ft.json").read_text())["predictions"]
    W = json.loads((T / "w_table.json").read_text())
    head = ["# 고친 판 시험 숫자표 v1 (PHD-MAIN-FIXTEST-v1) [이 발주에서 냄]", "",
            "값은 소수 한 자리. `*` = 표본 1만 점 미만, `표본 부족` = 100점 미만, `결과 없음`, `관문` = 관문으로 학습하지 않음, `읽기 L과 같음` = 두 읽기의 w가 같아 "
            "판 A(읽기 L) 학습 하나로 갈음. 읽기 = 발주 9.2(확인 / 가능·근거 불완전 / 같음, 방향 나음·못함). scientific_verdict: null.", "",
            "## 예측 대 결과", "", "| 예측 | 볼 값 | 판 A 읽기 L | 판 A 읽기 T | 근거 값(짧게) |", "|---|---|---|---|---|"]
    for k in ("A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8"):
        a, b = P["L"][k], P["T"][k]
        key = "; ".join(x for x in (a.get("key"), b.get("key")) if x)
        head.append(f"| {k} | {SEE[k]} | {vg(a)} | {vg(b)} | {key or '—'} |")
    head += ["", "| 예측 | 볼 값 | 판 B | 근거 값(짧게) |", "|---|---|---|---|"]
    for k in ("B1", "B2", "B3", "B4", "B5"):
        v = P["B"][k]
        head.append(f"| {k} | {SEE[k]} | {vg(v)} | {v.get('key') or '—'} |")
    head += ["", "## 일 1의 w 표 (cm; w의 95 % 구간은 패치를 1,000번 다시 뽑은 값)", "",
             "| 탐색 지역 | 줄 | τ | σ_영상 L | σ_사전 L | w L (95 % 구간) | w ÷ τ L | σ_영상 T | σ_사전 T | w T (95 % 구간) | w ÷ τ T |",
             "|---|---|---:|---:|---:|---|---:|---:|---:|---|---:|"]

    def c(x):
        return "나누지 못함" if x is None else f"{100 * x:.1f}"
    for r in W["rows"]:
        cells = [r["region"], r["kind_ko"], c(r["tau"])]
        for rd in ("L", "T"):
            x = r[rd]
            sp = x.get("sigma_prior") if x.get("separable", True) else None
            ci = x.get("w_ci95") or [None, None]
            cells += [c(x["sigma_image"]), c(sp), f"{c(x['w'])} ({c(ci[0])}~{c(ci[1])})", f"{x['w_over_tau']:.2f}"]
        head.append("| " + " | ".join(cells) + " |")
    head += ["", "| 경우 | 판 A 학습 (읽기 L) | 판 A 학습 (읽기 T) | 폭이 좁아진 경우 |", "|---|---|---|---|"]
    dl = json.loads((FTP / "prep/w_decision_L.json").read_text())["cases"]
    dt = json.loads((FTP / "prep/w_decision_T.json").read_text())["cases"]
    ko = {"B0_b10": "B0", "B173nb_b10": "B173 주변", "R1rep_b10": "R1"}
    for key in dl:
        s, p = key.split("/")
        a, b = dl[key], dt[key]
        def tr(x):
            return "함" if x["train"] else "관문 (" + ", ".join(x["failed"]) + ")"
        nar = [rd for rd, x in (("L", a), ("T", b)) if x["narrowed"]]
        head.append(f"| {ko[s]} {'LoD2' if p == 'LoD2' else '항공 LiDAR'} | {tr(a)} | {tr(b)} | {', '.join('읽기 ' + x for x in nar) or '아니오'} |")
    head.append("")
    blocks = ["\n".join(head) + "\n"]
    body = (T / "numbers_all.md").read_text()
    for blk in body.split("\n### ")[0:]:
        if not blk.strip():
            continue
        blocks.append(("### " + blk if not blk.startswith("### ") else blk).rstrip() + "\n\n")
    parts, cur = [], ""
    for blk in blocks:
        if len(cur) + len(blk) > LIMIT and cur:
            parts.append(cur)
            cur = ""
        cur += blk
    parts.append(cur)
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("고친판시험_숫자표_v1*.md"):
        f.unlink()
    names = []
    for i, p_ in enumerate(parts, 1):
        name = "고친판시험_숫자표_v1.md" if i == 1 else f"고친판시험_숫자표_v1_{i}.md"
        txt = p_ if i == 1 else f"# 고친 판 시험 숫자표 v1 — {i}쪽 (PHD-MAIN-FIXTEST-v1)\n\n" + p_
        (OUT / name).write_text(txt)
        names.append((name, len(txt)))
    print("numbers", names)


if __name__ == "__main__":
    main()
