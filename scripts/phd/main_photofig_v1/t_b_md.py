"""PHD-MAIN-PHOTOFIG-v1: md tables of figure 6 (per site) and table B from f6_cover.py's json (host python, json only).
  python3 -I t_b_md.py   scientific_verdict: null"""
import datetime as dt
import json
from pathlib import Path

T = Path(__file__).resolve().parents[3] / "docs/experiments/phd/main_photofig_v1/tables"
KO = {"B0_b10": "B0", "B173nb_b10": "B173 주변", "R1rep_b10": "R1"}
GPS0 = dt.datetime(1980, 1, 6)


def utc(t):
    return (GPS0 + dt.timedelta(seconds=float(t) + 1e9 - 18)).strftime("%H:%M")


def mm(x):
    return "—" if x is None else f"{x*1000:+.1f}"


def main():
    rowsB = []
    for site, ko in KO.items():
        p = T / f"fig6_{site}.json"
        if not p.exists():
            continue
        d = json.loads(p.read_text())
        L = [f"# 그림 6 숫자: {ko}의 벽과 지붕을 세 자료가 덮는 정도 [이 발주에서 냄]", "",
             "- 지금 참값의 벽 점 = 연직 비행(이 연구가 쓴 판 1.1.0)의 수직면 단일 반사 점(이 연구의 벽 규칙). 수동 비행 = 판 1.2.0의 모든 점. 5 mm 처리본 = 판 1.2.0. 정리 전, 비교 좌표.",
             "- 벽 공간 = 벽면에서 수평 1.0 m 안, 아래 끝 + 0.5 m ~ 위 끝 − 0.5 m, 평가 범위 안(B0 주 참값 확인 3.3과 같음). 점이 있는 칸의 몫 = 0.25 m 칸 수 × 0.0625 m² ÷ 공간 넓이.", "",
             "| 벽면 | 건물 | 향한 쪽 | 공간 넓이 (m²) | 지금 참값 (점/m²) | 수동 비행 | 5 mm 처리본 | 점이 있는 칸: 지금 · 수동 · 5 mm | 어긋남 수동 − 연직 (mm, 칸) |",
             "|---:|---|---|---:|---:|---:|---:|---|---|"]
        for r in d["walls"][:15]:
            L.append(f"| {r['ext']} | {r['building'][-7:]} | {r['facing']} ({r['azimuth']:.0f}°) | {r['area_space_m2']:,.1f} | {r['gt_wall_per_m2']:,.1f} | {r['manual_per_m2']:,.1f} | {r['fill_per_m2']:,.1f} | "
                     f"{r['gt_wall_cell_share']*100:.0f} · {r['manual_cell_share']*100:.0f} · {r['fill_cell_share']*100:.0f} % | {mm(r['offset_median_m'])} ({r['offset_cells']}) |")
        if len(d["walls"]) > 15:
            L.append(f"| … | 벽면 {len(d['walls']) - 15}개 더(json) | | | | | | | |")
        rt = d["roofs_total"]
        L += ["", f"- 지붕(LoD2 지붕면, 법선 방향 1.0 m 안, 평가 범위): 연직 비행 {rt['nadir']['per_m2']:,.1f} · 수동 비행 {rt['manual']['per_m2']:,.1f} · 5 mm 처리본 {rt['fill']['per_m2']:,.1f} 점/m²."]
        tb = d["table_B"]
        L += [f"- 두 비행의 어긋남(수동 − 연직, 0.5 m 칸 중앙값의 차): 벽 {mm(tb['walls']['median_m'])} mm (NMAD {mm(tb['walls']['nmad_m'])}, {tb['walls']['cells']}칸), 지붕 {mm(tb['roofs']['median_m'])} mm (NMAD {mm(tb['roofs']['nmad_m'])}, {tb['roofs']['cells']}칸)."]
        if "walls_target_building" in tb:
            w = tb["walls_target_building"]
            L.append(f"- B0 대상 건물의 벽만: {mm(w['median_m'])} mm (NMAD {mm(w['nmad_m'])}, {w['cells']}칸). B0 주 참값 확인 4.3: −26.5 mm (NMAD 26.4 mm, 2,179칸; 그쪽은 GeoGS 점군 − 연직 비행).")
        g = d["gps_seconds_of_week_adjusted"]
        L.append("- 측정 때(UTC, 2024-12-17, 이 지역 상자의 점): " + ", ".join(f"{dict(nadir='연직 비행', manual='수동 비행', fill='5 mm 처리본')[k]} {utc(v['min'])}~{utc(v['max'])}" for k, v in g.items()) + ". 학습 영상의 촬영 때는 표 A.")
        L += ["", "참값이 있는 패치(점 5개 이상) [근사: 수동 비행 점의 패치 대응은 연구 규칙을 줄인 꼴]", "",
              "| 사전 정보 | 곳 | 패치(평가 범위) | 지금 참값 | 수동 비행을 더하면 |", "|---|---|---:|---:|---:|"]
        for prior, gr in d["patches_with_gt"].items():
            for name, q in gr.items():
                L.append(f"| {'LoD2' if prior == 'LoD2' else '항공 LiDAR'} | {name} | {q['patches']:,} | {q['with_gt_now']:,} | {q['with_gt_plus_manual']:,} |")
        (T / f"fig6_{site}.md").write_text("\n".join(L) + "\n")
        rowsB.append((ko, tb))
    if rowsB:
        L = ["# 표 B. 두 비행의 어긋남: 수동 비행(판 1.2.0) − 연직 비행(판 1.1.0) [이 발주에서 냄]", "",
             "- 0.5 m 칸(벽: 면을 따라 × 높이, 지붕: 면 위 두 축)마다 두 비행 모두 3점 이상인 칸의 바깥 법선 방향 거리 중앙값의 차. 높이 맞춤 없이 같은 좌표. 평가 범위의 모든 LoD2 면.", "",
             "| 지역 | 벽: 중앙값 (mm) | 벽: NMAD (mm) | 벽: 칸 | 지붕: 중앙값 (mm) | 지붕: NMAD (mm) | 지붕: 칸 |", "|---|---:|---:|---:|---:|---:|---:|"]
        for ko, tb in rowsB:
            L.append(f"| {ko} | {mm(tb['walls']['median_m'])} | {mm(tb['walls']['nmad_m'])} | {tb['walls']['cells']:,} | {mm(tb['roofs']['median_m'])} | {mm(tb['roofs']['nmad_m'])} | {tb['roofs']['cells']:,} |")
            if "walls_target_building" in tb:
                w = tb["walls_target_building"]
                L.append(f"| {ko} 대상 건물 벽만 | {mm(w['median_m'])} | {mm(w['nmad_m'])} | {w['cells']:,} | | | |")
        L += ["", "- B0 주 참값 확인 4.3의 −26.5 mm(NMAD 26.4 mm, 2,179칸)는 GeoGS 점군(수동 비행 판 1.2.0을 2 cm로 솎은 것) − 연직 비행의 같은 셈이다."]
        (T / "table_B_offsets.md").write_text("\n".join(L) + "\n")
        (T / "table_B_offsets.json").write_text(json.dumps(dict(rows={ko: tb for ko, tb in rowsB}, scientific_verdict=None), indent=1, ensure_ascii=False))
    print("ok", [k for k, _ in rowsB])


if __name__ == "__main__":
    main()
