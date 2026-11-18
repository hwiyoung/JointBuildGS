"""PHD-MAIN-JUDGEABL-v1 5절 캠퍼스 판 보고 표 -> /docs/fusion_all/campus/tables/. FA_CFG=judgeabl_v1_fusion_campus.json"""
import json
from pathlib import Path
import pandas as pd
import fa_common as FC
T = Path("/docs/fusion_all/campus/tables"); T.mkdir(parents=True, exist_ok=True)
def write(name, df, note):
    df.to_csv(T / f"{name}.csv", index=False)
    L = ["| " + " | ".join(map(str, df.columns)) + " |", "|" + "---|" * len(df.columns)]
    L += ["| " + " | ".join(f"{x:.3f}" if isinstance(x, float) else str(x) for x in r) + " |" for r in df.itertuples(index=False)]
    (T / f"{name}.md").write_text(note + "\n\n" + "\n".join(L) + "\n")
tm = {}
for l in (FC.RES / "timing.jsonl").read_text().splitlines():
    r = json.loads(l); tm[(r["site"], r["mode"], r["prior"])] = r["seconds"]
S = json.loads((FC.RES / "sites.json").read_text())
rows = []
for r0 in S["rows"]:
    g = r0["group"]; r = dict(group=g, region=r0["region"], buildings=r0["buildings"], tiles=r0["tiles"], views=r0["views"],
                              images_s=tm.get((g, "images", None)), pairs_s=tm.get((g, "pairs", None)), LoD2_s=tm.get((g, "run", "LoD2")), ALS_s=tm.get((g, "run", "ALS")))
    r["total_s"] = round(sum(v for v in (r["images_s"], r["pairs_s"], r["LoD2_s"], r["ALS_s"]) if v), 1); rows.append(r)
df = pd.DataFrame(rows); write("campus_time", df, f"묶음마다 걸린 시간(초, 컨테이너 안). 준비(메시 합치기·시점 고르기) {S['seconds']} 초 별도. 합 {df['total_s'].sum():.0f} 초.")
L = json.loads((FC.RES / "link_summary.json").read_text())
write("campus_cover", pd.DataFrame(L["rows"]), "JC 패치를 캠퍼스 판 결합 칸에 이은 결과 (image = 영상 깊이 사용).")
C = json.loads((FC.RES / "check.json").read_text())
write("campus_check_box", pd.DataFrame(C["box"]), "세 실험 지역 상자(JUDGEAPPLY region[4], 상자 MVS) 와 캠퍼스 판 구분의 차이 (넓이).")
write("campus_check_regional", pd.DataFrame(C["regional_patches"]), "지역 MVS 판과 캠퍼스 판: 둘 다 덮은 JC 패치 구분 차이 (넓이).")
write("campus_check_cells", pd.DataFrame(C["regional_cells"]), "지역 MVS 판과 캠퍼스 판: 두 판 모두 사전 정보가 있는 0.25 m 칸의 최종 변화 칸 차이.")
print(df[["group", "views", "total_s"]].to_string()); print(L["LoD2_covered"], L["ALS_covered"])
