"""PHD-MAIN-PHOTOFIG-v1 table A: the training and evaluation images of each experiment site by flight and camera tilt. (jointbuildgs:dev, CPU)

  python t_a_images.py   -> /docs/tables/table_A_images.md|json
Images = S0/fork_inputs/s61/<site>/split.json (train, test). Capture time = XMP drone-dji:UTCAtExposure of the original image in the
TUM2TWIN Images.zip; flight by time (2024-12-17 UTC): nadir 07:42-08:12, manual 08:37-09:36 (drone LiDAR GPS ranges, B0REF), else other.
Tilt = angle between the optical axis and the vertical (the 937-image model, scripts/phd/main_stage0_v1/common.py Views.tilt);
vertical image = tilt <= 20 deg (thesis 6.3). [이 발주에서 냄] scientific_verdict: null"""
import datetime as dt
import re
import zipfile
from pathlib import Path

import numpy as np

import pf_geo as G
from pf_common import DOCS, S0, jdump, jl, now

ZIP = Path("/art/phase-payloads/p0-audit/data/raw/uav/Images.zip")
SITES = [("B0_b10", "B0"), ("B173nb_b10", "B173 주변"), ("B173_b0", "B173만"), ("R1rep_b10", "R1")]
NADIR = (dt.datetime(2024, 12, 17, 7, 42), dt.datetime(2024, 12, 17, 8, 13))
MANUAL = (dt.datetime(2024, 12, 17, 8, 37), dt.datetime(2024, 12, 17, 9, 37))


def main():
    zf = zipfile.ZipFile(ZIP)
    members = {Path(n).stem: n for n in zf.namelist() if n.upper().endswith(".JPG")}
    cache = {}
    def utc(stem):
        if stem not in cache:
            with zf.open(members[stem]) as f:
                raw = f.read(250000)
            m = re.search(rb'drone-dji:UTCAtExposure="([^"]*)"', raw)
            cache[stem] = dt.datetime.fromisoformat(m.group(1).decode()[:19]) if m else None
        return cache[stem]
    V = G.views()
    out, rows = {}, []
    for site, ko in SITES:
        sp = jl(S0 / "fork_inputs/s61" / site / "split.json")
        for part, names in (("학습", sp["train"]), ("평가", sp["test"])):
            rec = dict(total=len(names), nadir_vertical=0, nadir_oblique=0, manual_vertical=0, manual_oblique=0, other=0, no_time=0)
            tilts = []
            for n in names:
                t = V.tilt(G.vkey(n)); tilts.append(t)
                u = utc(n) if n in members else None
                if u is None:
                    rec["no_time"] += 1; rec["other"] += 1; continue
                vert = t <= 20.0
                if NADIR[0] <= u <= NADIR[1]:
                    rec["nadir_vertical" if vert else "nadir_oblique"] += 1
                elif MANUAL[0] <= u <= MANUAL[1]:
                    rec["manual_vertical" if vert else "manual_oblique"] += 1
                else:
                    rec["other"] += 1
            tilts = np.array(tilts)
            rec.update(tilt_median=float(np.median(tilts)), tilt_min=float(tilts.min()), tilt_max=float(tilts.max()),
                       utc_first=min((utc(n) for n in names if n in members and utc(n)), default=None), utc_last=max((utc(n) for n in names if n in members and utc(n)), default=None))
            out[f"{site}/{part}"] = rec
            rows.append((ko, part, rec))
    jdump(DOCS / "tables/table_A_images.json", dict(rows=out, rule=__doc__.split("\n\n")[1], made=now(), scientific_verdict=None))
    L = ["# 표 A. 실험 지역마다 학습 영상과 평가 영상: 비행과 촬영 각 [이 발주에서 냄]", "",
         "- 비행은 원본 영상의 촬영 시각(UTC)으로 나눔: 연직 비행 07:42~08:12, 수동 비행 08:37~09:36(2024-12-17). 연직 영상 = 광축이 연직에서 20° 안.", "",
         "| 지역 | 영상 | 전체 | 연직 비행·연직 | 연직 비행·경사 | 수동 비행·연직 | 수동 비행·경사 | 그 밖 | 촬영 각 중앙값 (°) | 촬영 각 범위 (°) | 촬영 시각(UTC) |",
         "|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|"]
    for ko, part, r in rows:
        L.append(f"| {ko} | {part} | {r['total']} | {r['nadir_vertical']} | {r['nadir_oblique']} | {r['manual_vertical']} | {r['manual_oblique']} | {r['other']} | "
                 f"{r['tilt_median']:.1f} | {r['tilt_min']:.1f} ~ {r['tilt_max']:.1f} | {str(r['utc_first'])[11:16]} ~ {str(r['utc_last'])[11:16]} |")
    (DOCS / "tables/table_A_images.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
