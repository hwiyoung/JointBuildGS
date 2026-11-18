"""PHD-MAIN-JUDGEABL-v1 5절 보고 표: 지역별 걸린 시간, 덮인 범위와 결합 구분, 검산. /res 와 /res 위 표에서만 읽는다.
  python fa_tables.py -> /docs/fusion_all/tables/{fa_time,fa_cover,fa_check,fa_scores}.{csv,md}"""
import json
from pathlib import Path

import pandas as pd

import fa_common as FC

T = Path("/docs/fusion_all/tables"); T.mkdir(parents=True, exist_ok=True)


def write(name, df, note=""):
    df.to_csv(T / f"{name}.csv", index=False)
    lines = ["| " + " | ".join(map(str, df.columns)) + " |", "|" + "---|" * len(df.columns)]
    for r in df.itertuples(index=False):
        lines.append("| " + " | ".join(f"{x:.3f}" if isinstance(x, float) else str(x) for x in r) + " |")
    (T / f"{name}.md").write_text((note + "\n\n" if note else "") + "\n".join(lines) + "\n")


rows = [json.loads(l) for l in (FC.RES / "timing.jsonl").read_text().splitlines() if l.strip()]
tm = {}
for r in rows:      # 같은 단계를 다시 돌렸으면 마지막 값
    tm[(r["site"], r["mode"], r["prior"])] = r["seconds"]
out = []
for site, s in FC.SITES.items():
    g = lambda m, p=None: tm.get((site, m, p))
    dj = {p: FC.RES / "sites" / site / p / "detect.json" for p in ("LoD2", "ALS")}
    dd = {p: json.loads(f.read_text()) if f.exists() else None for p, f in dj.items()}
    r = dict(site=site, kind=s["kind"], views=dd["LoD2"]["training_views"] if dd["LoD2"] else None, paired=dd["LoD2"]["paired_views"] if dd["LoD2"] else None,
             images_s=g("images"), pairs_s=g("pairs"), LoD2_s=g("run", "LoD2"), ALS_s=g("run", "ALS"))
    r["total_s"] = round(sum(v for v in (r["images_s"], r["pairs_s"], r["LoD2_s"], r["ALS_s"]) if v), 1)
    for p in ("LoD2", "ALS"):
        r[f"{p}_final_m2"] = dd[p]["areas_m2"]["final"] if dd[p] else None
    out.append(r)
write("fa_time", pd.DataFrame(out), "자리마다 걸린 시간(초, 컨테이너 안 벽시계; 영상 줄이기·짝·LoD2 판정·항공 LiDAR 판정). GPU 단계 없음(COLMAP 은 DISCARD-RULE-v1 에 이미 있음).")
L = json.loads((FC.RES / "link_summary.json").read_text())
write("fa_cover", pd.DataFrame(L["rows"]), "JC 패치를 결합 칸에 이은 결과. image = 영상 깊이 사용(2), prior = 사전정보 사용(1). 참값 읽지 않음.")
C = json.loads((FC.RES / "check/check.json").read_text())
write("fa_check", pd.DataFrame(C["rows"]), "세 실험 지역 상자 검산: 이 구현의 최종 칸 = BASELINES-v1 저장 칸, 구분 = JUDGEAPPLY region[4] (넓이 비율).")
print("tables", sorted(p.name for p in T.glob("*.md")))
