"""Build interactive E2 LoD2 O/X dashboard HTML from classification CSV."""
import csv, json, os

BASE = os.environ.get("JBGS_GATE5_WORK", "/tmp/jbgs_gate5_work")
SRC = os.path.join(BASE, "e2_lod2_success_failure_v0.csv")
OUT = os.path.join(BASE, "e2_ox_dashboard.html")

CLS = {"SUCCESS": "S", "BORDERLINE": "B", "FAIL_QUALITY": "FQ", "FAIL_GENERATION": "FG",
       "NOT_ASSESSED_REFERENCE_GAP": "RG", "NOT_IN_AOI": "AOI"}
E1B = {"O_CANDIDATE": "O", "REVIEW": "R", "X_CANDIDATE": "X", "NOT_ASSESSED": "NA"}

rows = []
for r in csv.DictReader(open(SRC)):
    def num(k):
        v = r[k]
        return round(float(v), 3) if v not in ("", None) else None
    m = [num("g3_completeness"), num("g3_correctness"), num("g3_quality"),
         num("g4_coverage"), num("g4_rmse_z_m"), num("g4_p95_abs_z_m"), num("g4_median_bias_z_m")]
    e1 = "GF" if r["e1_status"] == "ASSESSED_OUTPUT_MISSING" else E1B.get(r["e1_band"], "NA")
    rows.append([int(r["population_index"]), r["stable_id"], CLS[r["e2_class"]], r["v0p1_band"], m, e1])
rows.sort(key=lambda x: x[0])

# per-condition 5-gate inputs from the full v16 CSV + per-condition normal angles
VISD = json.load(open(os.path.join(BASE, "visuals.json")))
V16CSV = ("/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/p2/"
          "e1_e6_roofer_ox_review_v1/P2-E1-E6-ROOFER-OX-REVIEW-v16-G3G4-DEV0P1/"
          "development_g3_g4_building_condition_v0.csv")
ST = {"ASSESSED_DEVELOPMENT_PROXY": "P", "ASSESSED_OUTPUT_MISSING": "M",
      "NOT_ASSESSED_AOI": "A", "NOT_ASSESSED_REFERENCE_GAP": "R"}
cond = {}
for r in csv.DictReader(open(V16CSV)):
    idx = int(r["population_index"])
    def n(k):
        v = r[k]
        return round(float(v), 3) if v not in ("", None) else None
    l2 = VISD.get(str(idx), {}).get("l2", {}).get(r["condition_id"])
    st = ST.get(r["assessment_status"], "R")
    if st == "R" and l2 and n("g4_rmse_z_m") is not None:
        st = "P"  # E1 무효로 미판정이던 건물: 원본 LoD2 참조로 판정 가능
    cond.setdefault(idx, {})[r["condition_id"]] = [
        l2[0] if l2 else None, l2[1] if l2 else None, n("g4_coverage"),
        n("g4_rmse_z_m"), l2[3] if l2 else None, st]
# redesign arms (r0p25 readouts): l2 metrics from visuals + G4 from the S3/S3C evaluations
ARTP = "/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/p2/"
IDX_OF = {}
for r in csv.DictReader(open(V16CSV)):
    IDX_OF[r["stable_id"]] = int(r["population_index"])
ARM_LABEL = {"E4_V2_STATIC": "E4v2", "E5_V2_F1": "E5v2",
             "E4_V3_TIN025": "E4v3", "E5_V3_F1_TIN025": "E5v3"}
for eval_csv in (ARTP + "e4_e6_redesign_s3_v1/P2-E4-E6-REDESIGN-S3-v1/evaluation/s3_building_condition_v1.csv",
                 ARTP + "e4_e6_redesign_s3c_v1/P2-E4-E6-REDESIGN-S3C-v1/evaluation/s3c_building_condition_v1.csv"):
    for r in csv.DictReader(open(eval_csv)):
        if r["criterion"] != "O50":
            continue
        idx = IDX_OF.get(r["stable_id"])
        if idx is None:
            continue
        cn = ARM_LABEL[r["condition_id"]]
        def nv(k):
            v = r.get(k)
            return round(float(v), 3) if v not in ("", None, "None") else None
        l2 = VISD.get(str(idx), {}).get("l2", {}).get(cn)
        g4cov, g4rmse = nv("g4_coverage"), nv("g4_rmse_z_m")
        st = "P" if (l2 or g4rmse is not None) else "M"
        cond.setdefault(idx, {})[cn] = [
            l2[0] if l2 else None, l2[1] if l2 else None, g4cov, g4rmse,
            l2[3] if l2 else None, st]

for row in rows:
    l2e2 = VISD.get(str(row[0]), {}).get("l2", {}).get("E2")
    row[4][0] = l2e2[0] if l2e2 else None
    row[4][1] = l2e2[1] if l2e2 else None
    row[4][2] = l2e2[2] if l2e2 else None
    row.append(cond.get(row[0], {}))

DATA = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
VISJ = open(os.path.join(BASE, "visuals.json")).read()

# per-building asset paths for on-demand 3D loading (local server mode)
MAN = json.load(open(os.path.dirname(V16CSV) + "/viewer_manifest.json"))
ap = {}
for b_ in MAN["buildings"]:
    idx_ = int(b_["population_index"])
    cp = b_.get("comparison_priors", {})
    e_ = {}
    if (cp.get("PRIOR_LOD2") or {}).get("roofer"):
        e_["L2"] = [cp["PRIOR_LOD2"]["roofer"], None]
    if (cp.get("PRIOR_ALS") or {}).get("points"):
        e_["ALS"] = [None, cp["PRIOR_ALS"]["points"]]
    for cn_, sp_ in [("E1", b_["lidar"]), ("E2", b_["mvs"])] + [
            (c_, (b_.get("conditions") or {}).get(c_) or {}) for c_ in ("E3", "E4", "E5", "E6")]:
        e_[cn_] = [sp_.get("roofer"), sp_.get("points")]
    for cn_, root_, arm_ in (("E4v2", "assets_redesign", "E4_V2_STATIC"), ("E5v2", "assets_redesign", "E5_V2_F1"),
                             ("E4v3", "assets_redesign_v3", "E4_V3_TIN025"), ("E5v3", "assets_redesign_v3", "E5_V3_F1_TIN025")):
        base_ = f"{root_}/{arm_}/B{idx_:03d}_{b_['stable_id']}"
        e_[cn_] = [base_ + ".roofer.obj", base_ + ".points.ply"]
    # every sealed condition's point display = its actual roofer-input view
    for cn_ in ("E1", "E2", "E3", "E4", "E5", "E6"):
        if cn_ in e_:
            e_[cn_][1] = f"assets_roofer_input/{cn_}/B{idx_:03d}_{b_['stable_id']}.points.ply"
    ap[idx_] = e_
APJ = json.dumps(ap, separators=(",", ":"))

# footprint map data (local frame = EPSG:25832 minus scene origin)
ORIGIN = (690700.0, 5335700.0)
FPSRC = ("/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/p2/"
         "c1_c2_shared_footprint_199_v3/P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3-replay-20260806a/"
         "freeze/shared_footprints_199.geojson")
fpj = {}
for f in json.load(open(FPSRC))["features"]:
    idx = int(f["properties"]["population_index"])
    g = f["geometry"]
    polys = g["coordinates"] if g["type"] == "Polygon" else [p for mp in g["coordinates"] for p in mp]
    rings = []
    for ring in polys:
        rings.append([[round(x - ORIGIN[0], 1), round(y - ORIGIN[1], 1)] for x, y in ring])
    fpj[idx] = rings
AOI_LOCAL = [round(690791.740 - ORIGIN[0], 1), round(5335864.050 - ORIGIN[1], 1),
             round(691154.650 - ORIGIN[0], 1), round(5336353.850 - ORIGIN[1], 1)]
FPJ = json.dumps({"fp": fpj, "aoi": AOI_LOCAL}, separators=(",", ":"))

HTML = r"""<title>E2 LoD2 판정 대시보드 — 199동</title>
<style>
:root{
  --bg:#F6F7F8; --card:#FFFFFF; --ink:#1B2026; --ink2:#57616C; --ink3:#8B95A0;
  --line:#E2E6EA; --line2:#EDF0F3; --o:#2E6BA8; --x:#C2453A; --amber:#A8721F;
  --maroon:#8E3A46; --gray:#6E7880; --o-soft:#E8F0F8; --x-soft:#F9ECEA;
  --amber-soft:#F7EFE2; --maroon-soft:#F3E8EA; --gray-soft:#EEF0F2;
  --shadow:0 1px 2px rgba(24,32,40,.06),0 2px 8px rgba(24,32,40,.05);
}
@media (prefers-color-scheme: dark){:root{
  --bg:#14171A; --card:#1C2126; --ink:#E6EAEE; --ink2:#9AA4AE; --ink3:#6E7880;
  --line:#2A3138; --line2:#232930; --o:#4A8FD6; --x:#E06A50; --amber:#C99245;
  --maroon:#B06A75; --gray:#7E8890; --o-soft:#1E2E3F; --x-soft:#3A241F;
  --amber-soft:#332A1B; --maroon-soft:#33232A; --gray-soft:#242A30;
  --shadow:0 1px 2px rgba(0,0,0,.4);
}}
:root[data-theme="dark"]{
  --bg:#14171A; --card:#1C2126; --ink:#E6EAEE; --ink2:#9AA4AE; --ink3:#6E7880;
  --line:#2A3138; --line2:#232930; --o:#4A8FD6; --x:#E06A50; --amber:#C99245;
  --maroon:#B06A75; --gray:#7E8890; --o-soft:#1E2E3F; --x-soft:#3A241F;
  --amber-soft:#332A1B; --maroon-soft:#33232A; --gray-soft:#242A30;
  --shadow:0 1px 2px rgba(0,0,0,.4);
}
:root[data-theme="light"]{
  --bg:#F6F7F8; --card:#FFFFFF; --ink:#1B2026; --ink2:#57616C; --ink3:#8B95A0;
  --line:#E2E6EA; --line2:#EDF0F3; --o:#2E6BA8; --x:#C2453A; --amber:#A8721F;
  --maroon:#8E3A46; --gray:#6E7880; --o-soft:#E8F0F8; --x-soft:#F9ECEA;
  --amber-soft:#F7EFE2; --maroon-soft:#F3E8EA; --gray-soft:#EEF0F2;
  --shadow:0 1px 2px rgba(24,32,40,.06),0 2px 8px rgba(24,32,40,.05);
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:14px/1.55 "Pretendard Variable",Pretendard,"Noto Sans KR",system-ui,-apple-system,"Segoe UI",sans-serif;
  -webkit-font-smoothing:antialiased}
.mono{font-family:"JetBrains Mono",ui-monospace,"SF Mono",Consolas,monospace;font-variant-numeric:tabular-nums}
.wrap{max-width:1240px;margin:0 auto;padding:28px 24px 64px;display:flex;flex-direction:column;gap:16px}
header{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin-bottom:2px}
h1{font-size:21px;font-weight:700;letter-spacing:-.01em;margin:0;text-wrap:balance}
.tag{font-size:11px;letter-spacing:.06em;color:var(--ink2);border:1px solid var(--line);
  border-radius:999px;padding:3px 10px;white-space:nowrap}
.tag.warn{color:var(--amber);border-color:var(--amber)}
header .sp{flex:1}
a.viewer-btn{font-size:13px;font-weight:600;color:var(--o);text-decoration:none;
  border:1.5px solid var(--o);border-radius:8px;padding:6px 14px;white-space:nowrap}
a.viewer-btn:hover{background:var(--o-soft)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;
  padding:12px 16px;box-shadow:var(--shadow)}
.kpi .lb{font-size:11px;letter-spacing:.05em;color:var(--ink2);text-transform:uppercase}
.kpi .v{font-size:26px;font-weight:700;letter-spacing:-.02em;margin-top:2px}
.kpi .sub{font-size:11.5px;color:var(--ink3);margin-top:1px}
.kpi.o .v{color:var(--o)} .kpi.x .v{color:var(--x)} .kpi.g .v{color:var(--maroon)} .kpi.n .v{color:var(--gray)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:16px 18px;box-shadow:var(--shadow)}
.card h2{font-size:13px;font-weight:700;letter-spacing:.03em;margin:0 0 4px;color:var(--ink)}
.card .note{font-size:12px;color:var(--ink3);margin:0 0 12px}
.presets{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}
.presets button{font:600 12px/1 inherit;font-family:inherit;color:var(--ink2);background:none;
  border:1px solid var(--line);border-radius:999px;padding:6px 12px;cursor:pointer}
.presets button:hover{border-color:var(--o);color:var(--o)}
.presets button.on{background:var(--o);border-color:var(--o);color:#fff}
:root[data-theme="dark"] .presets button.on,:root:not([data-theme="light"]) .presets button.on{color:#fff}
.sliders{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px 22px}
.sl{display:grid;grid-template-columns:1fr auto;align-items:center;gap:2px 10px}
.sl label{font-size:12px;color:var(--ink2)}
.sl .val{font-size:12.5px;font-weight:700}
.sl input[type=range]{grid-column:1/3;width:100%;accent-color:var(--o);height:22px;margin:0}
.midrow{display:grid;grid-template-columns:minmax(0,3fr) minmax(0,2fr);gap:16px}
@media (max-width:900px){.midrow{grid-template-columns:1fr}}
.legend{display:flex;gap:14px;font-size:12px;color:var(--ink2);margin-bottom:6px;flex-wrap:wrap}
.legend .it{display:flex;align-items:center;gap:6px}
.dot{width:9px;height:9px;border-radius:50%;display:inline-block}
svg text{font-family:inherit;fill:var(--ink2);font-size:11px}
svg .axis line,svg .axis path{stroke:var(--line)}
svg .grid line{stroke:var(--line2)}
.tooltip{position:fixed;pointer-events:none;background:var(--card);border:1px solid var(--line);
  border-radius:8px;padding:8px 11px;font-size:12px;box-shadow:var(--shadow);z-index:20;
  display:none;max-width:260px}
.tooltip .tid{font-weight:700}
.chips{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.chips button{font:600 12px/1 inherit;font-family:inherit;background:none;border:1px solid var(--line);
  color:var(--ink2);border-radius:999px;padding:6px 11px;cursor:pointer}
.chips button.on{border-width:1.5px}
.chips button[data-f="all"].on{border-color:var(--ink2);color:var(--ink)}
.chips button[data-f="O"].on{border-color:var(--o);color:var(--o);background:var(--o-soft)}
.chips button[data-f="XQ"].on{border-color:var(--x);color:var(--x);background:var(--x-soft)}
.chips button[data-f="FG"].on{border-color:var(--maroon);color:var(--maroon);background:var(--maroon-soft)}
.chips button[data-f="NA"].on{border-color:var(--gray);color:var(--gray);background:var(--gray-soft)}
.chips input{margin-left:auto;font:13px/1.4 inherit;font-family:inherit;color:var(--ink);
  background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:7px 11px;min-width:180px}
.tblwrap{overflow:auto;max-height:600px;border:1px solid var(--line);border-radius:10px;margin-top:10px}
table{border-collapse:collapse;width:100%;font-size:12.5px;min-width:1150px}
thead th{position:sticky;top:0;background:var(--card);z-index:2;font-size:11px;letter-spacing:.04em;
  color:var(--ink2);text-align:right;padding:9px 10px;border-bottom:1.5px solid var(--line);
  white-space:nowrap;cursor:pointer;user-select:none}
thead th.l{text-align:left}
thead th:hover{color:var(--o)}
tbody td{padding:7px 10px;border-bottom:1px solid var(--line2);text-align:right;white-space:nowrap}
tbody td.l{text-align:left}
tbody tr:hover{background:var(--bg)}
tbody tr.rx td:first-child{box-shadow:inset 3px 0 0 var(--x)}
tbody tr.rg td:first-child{box-shadow:inset 3px 0 0 var(--maroon)}
tbody tr.rn{color:var(--ink3)}
.cstrip{display:inline-flex;gap:2px}
.cstrip i{display:inline-block;width:15px;height:15px;border-radius:3.5px;font:700 9.5px/15px "JetBrains Mono",monospace;
  font-style:normal;text-align:center;color:#fff;cursor:default}
.cstrip .cO{background:var(--o)} .cstrip .cX{background:var(--x)}
.cstrip .cG{background:var(--maroon)} .cstrip .cN{background:var(--line);color:var(--ink3)}
#map{width:100%;max-width:720px;display:block;margin:0 auto;background:var(--bg);border-radius:10px}
#map path.mapb{cursor:pointer;stroke:var(--card);stroke-width:0.6}
#map path.mapb:hover{stroke:var(--ink);stroke-width:1.2}
#mapConds{margin-bottom:10px}
#mapConds button.on{border-color:var(--o);color:var(--o);background:var(--o-soft)}
.mcond{margin-top:14px;overflow-x:auto}
.mcond table{border-collapse:collapse;font-size:12px;min-width:640px;width:100%}
.mcond th{font-size:10.5px;letter-spacing:.04em;color:var(--ink2);text-align:right;padding:5px 9px;border-bottom:1.5px solid var(--line)}
.mcond th.l,.mcond td.l{text-align:left}
.mcond td{padding:5px 9px;border-bottom:1px solid var(--line2);text-align:right;white-space:nowrap}
th.diag,td.diag{color:var(--ink3)}
th.diag i{font-style:normal;font-size:9px;letter-spacing:.03em;display:block;line-height:1}
.badge{display:inline-block;font-size:11px;font-weight:700;border-radius:6px;padding:2.5px 8px}
.bO{color:var(--o);background:var(--o-soft)} .bX{color:var(--x);background:var(--x-soft)}
.bB{color:var(--amber);background:var(--amber-soft)} .bG{color:var(--maroon);background:var(--maroon-soft)}
.bN{color:var(--gray);background:var(--gray-soft)}
.miss{color:var(--ink3)}
.fails{font-size:11px;color:var(--x);max-width:210px;overflow:hidden;text-overflow:ellipsis}
td a{color:var(--o);text-decoration:none;font-weight:600}
td a:hover{text-decoration:underline}
.foot{font-size:11.5px;color:var(--ink3);line-height:1.7}
.foot code{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:10.5px}
button:focus-visible,input:focus-visible,a:focus-visible{outline:2px solid var(--o);outline-offset:2px}
@media (prefers-reduced-motion:no-preference){.kpi .v{transition:color .15s}}
details.expl summary{cursor:pointer;font-size:13px;font-weight:700;padding:2px 0}
.grow{display:grid;grid-template-columns:180px 1fr;gap:16px;padding:13px 0;border-bottom:1px solid var(--line2);align-items:start}
.grow:last-of-type{border-bottom:none}
.grow svg{width:180px;height:auto;background:var(--bg);border:1px solid var(--line2);border-radius:8px}
.grow h4{font-size:13px;font-weight:700;margin:0 0 5px}
.gk{font-size:10.5px;font-weight:600;color:var(--ink2);border:1px solid var(--line);border-radius:999px;padding:2px 8px;margin-left:6px;vertical-align:1px}
.gf{background:var(--bg);border-radius:6px;padding:6px 10px;font-size:12px;margin:0 0 6px;display:inline-block}
.gm{font-size:12.5px;color:var(--ink2);margin:0 0 7px;line-height:1.6;max-width:640px}
.exbtn{font:600 11.5px/1 inherit;font-family:inherit;color:var(--o);background:var(--o-soft);border:none;border-radius:999px;padding:6px 11px;cursor:pointer}
@media (max-width:700px){.grow{grid-template-columns:1fr}.grow svg{width:100%;max-width:240px}}
details.expl summary::marker{color:var(--o)}
.expl table{font-size:12.5px;border-collapse:collapse;margin-top:10px;min-width:760px}
.expl th{text-align:left;font-size:11px;letter-spacing:.04em;color:var(--ink2);padding:6px 12px 6px 0;border-bottom:1.5px solid var(--line)}
.expl td{padding:7px 12px 7px 0;border-bottom:1px solid var(--line2);vertical-align:top;line-height:1.5}
.expl td:first-child{font-weight:700;white-space:nowrap}
.expl .src{color:var(--ink3);font-size:11.5px}
.modal{position:fixed;inset:0;background:rgba(10,14,18,.5);display:none;z-index:40;
  align-items:flex-start;justify-content:center;overflow:auto;padding:34px 16px}
.modal.on{display:flex}
.mbox{background:var(--card);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);
  max-width:min(1860px,97vw);width:100%;padding:20px 24px 22px}
.mhead{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:4px}
.mhead .mid{font-size:16px;font-weight:700}
.mhead .sp{flex:1}
.mclose{font:700 14px/1 inherit;font-family:inherit;background:none;border:1px solid var(--line);
  color:var(--ink2);border-radius:8px;padding:7px 12px;cursor:pointer}
.mclose:hover{border-color:var(--x);color:var(--x)}
.mgrid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:12px}

@media (max-width:820px){.mgrid{grid-template-columns:1fr}}
.mcell h3{font-size:12px;font-weight:700;letter-spacing:.03em;margin:0 0 6px;color:var(--ink)}
.mcell img,.mcell .ovsvg svg{width:100%;max-width:460px;height:auto;display:block;
  background:#F6F7F8;border:1px solid var(--line);border-radius:8px}
.mcell img{image-rendering:pixelated}
.mleg{display:flex;gap:12px;flex-wrap:wrap;font-size:11.5px;color:var(--ink2);margin-top:7px;align-items:center}
.mleg .sw{width:11px;height:11px;border-radius:3px;display:inline-block;vertical-align:-1px}
.grad{width:130px;height:10px;border-radius:5px;display:inline-block;
  background:linear-gradient(90deg,#2E6BA8,#9EA3A8,#C2453A)}
.mmet{display:flex;gap:7px;flex-wrap:wrap;margin-top:14px}
.mmet .mchip{font-size:11.5px;border-radius:7px;padding:4px 9px;border:1px solid var(--line)}
.mmet .ok{color:var(--o);background:var(--o-soft);border-color:transparent}
.mmet .ng{color:var(--x);background:var(--x-soft);border-color:transparent;font-weight:700}
.mmet .na{color:var(--ink3)}
.mnote{font-size:12px;color:var(--ink3);margin-top:10px}
.m3d{margin-top:12px;border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:var(--bg)}
.m3d h3{font-size:12px;font-weight:700;letter-spacing:.03em;margin:0 0 8px;color:var(--ink)}
.mtoggles{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px;align-items:center}
.mtoggles button{font:600 12px/1 inherit;font-family:inherit;background:var(--card);border:1.5px solid var(--line);
  color:var(--ink2);border-radius:999px;padding:6px 12px;cursor:pointer;display:flex;align-items:center;gap:6px}
.mtoggles button .sw{width:10px;height:10px;border-radius:3px}
.mtoggles button.off{opacity:.4}
.mtoggles button:disabled{opacity:.3;cursor:default}
.mtoggles .hint{font-size:11.5px;color:var(--ink3);margin-left:auto}
#m3dRow{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
@media (max-width:1000px){#m3dRow{grid-template-columns:repeat(2,minmax(0,1fr))}}
.m3p h4{font-size:11.5px;font-weight:700;margin:0 0 4px;color:var(--ink2)}
.m3p canvas{width:100%;height:390px;display:block;touch-action:none;cursor:grab;border:1px solid var(--line2);border-radius:8px;background:#0B0F14}
</style>

<div class="wrap">
<header>
  <h1>E2 · MVS→Roofer LoD2 건물별 판정</h1>
  <span class="tag">U_target = 199동</span>
  <span class="tag warn">ROOFER_G3G4_DEVELOPMENT_V0P1 · 비동결 · 비확증</span>
  <span class="sp"></span>
  <a class="viewer-btn" href="http://localhost:8880/" target="_blank" rel="noopener">3D 뷰어 (v16) ↗</a>
</header>

<div class="cards">
  <div class="kpi o"><div class="lb">O · 성공</div><div class="v" id="kO">–</div><div class="sub" id="kOs"></div></div>
  <div class="kpi x"><div class="lb">X · 품질 미달</div><div class="v" id="kX">–</div><div class="sub">생성됐지만 컷 불통과</div></div>
  <div class="kpi g"><div class="lb">X · 생성 실패</div><div class="v">65</div><div class="sub">57동은 E1(LiDAR)도 실패 · E2측 8동</div></div>
  <div class="kpi n"><div class="lb">판정 불가</div><div class="v" id="kN">–</div><div class="sub" id="kNs"></div></div>
  <div class="kpi"><div class="lb">성공률 (판정가능 161)</div><div class="v" id="kR">–</div><div class="sub" id="kRs"></div></div>
  <div class="kpi"><div class="lb">E2 대비 전이 (X→O / O→X)</div><div class="v" style="font-size:14px;line-height:1.9" id="kT">–</div><div class="sub">공통 판정가능 건물 · legacy-base 참고용</div></div>
</div>

<div class="card">
  <h2>판정 컷 — 직접 움직여 보세요</h2>
  <p class="note"><b>게이트 5개</b>(completeness · correctness · coverage · RMSZ · 방향) 모두 통과 = O, 하나라도 미달 = X — 전부 독립 참조 대비(참조 검증 스탠스) · quality는 C×C 합성 요약, P95·bias는 진단으로 강등(판정 미사용) · 게이트 지표 결측은 불통과 · 생성 실패 65동은 컷과 무관하게 X · 판정 불가 38동은 분모 제외 · 같은 컷이 E1–E6 전 조건에 동일 적용(조건별 판정은 표의 E1–E6 열과 건물 상세에서) · <b>주의</b>: G3·방향 참조 = 기구축 LoD2(변화X 가정) — <b>E6는 참조=prior 순환이라 G3 해석 금지</b> · E4–E6는 legacy-base 교차계보 기술 증거(DEC-P1-022) · E1의 G4는 자기참조 — 전이 수치는 개발 참고용, 확증 아님</p>
  <div class="presets" id="presets">
    <button data-p="strict">더 엄격</button><button data-p="v01" class="on">v0.1 기본</button>
    <button data-p="loose">느슨</button><button data-p="looser">더 느슨</button><button data-p="loosest">매우 느슨</button>
    <button data-p="e1a" title="E1(LiDAR) 분포로 coverage(P10)·RMSZ(P90)만 앵커 — comp/corr/방향은 E1이 G3 참조 자신이라 퇴화(1.0/0°)하므로 앵커 불가, 참조 승격 필요">E1 분포 앵커 (전 게이트)</button>
  </div>
  <div class="sliders" id="sliders"></div>
</div>

<div class="card">
  <h2>조건별 종합 — 건수와 게이트 중앙값 (현재 컷 연동)</h2>
  <p class="note">O/생성실패/품질X/판정불가 건수 + 판정가능 건물의 게이트별 중앙값 · E4–E6 legacy-base, E6 순환 주의</p>
  <div style="overflow-x:auto"><table id="condSum" style="min-width:820px"></table></div>
</div>


<div class="card">
<details class="expl" open>
<summary>게이트 5 해부 — 질문 · 수식 · 단면 개념도 (모든 게이트는 독립 참조 대비)</summary>
<p class="note" style="margin-top:8px">공통 기호: R = <b>원본 CityGML LoD2 RoofSurface</b>(EPSG:25832, 1차 참조 — 199동 전부) → 유효 E1(2차) · 매칭: 법선 15° 호환 union 피복(1:M 허용, robust), P = 모델 지붕면들, 매칭 σ = XY 겹침이 상호 ≥0.5인 쌍을 IoU 순으로 1:1 · C_ref = footprint 내부(0.5 m inset) <b>현시점 UAS</b> 지붕점의 0.5 m 셀(G4는 시점 정합성 때문에 계속 UAS) · 점선 = 정답, 파랑 = 모델. 각 그림은 <b>그 게이트만 단독으로 걸리는</b> 이상화된 실패입니다.</p>

<div class="grow"><svg viewBox="0 0 170 100"><rect x="25" y="60" width="120" height="26" fill="var(--line2)"/><path d="M25,60 L85,26 L145,60" fill="none" stroke="var(--ink3)" stroke-width="1.6" stroke-dasharray="4 3"/><path d="M25,60 L85,26" fill="none" stroke="var(--o)" stroke-width="3"/><path d="M85,26 l10,9 l8,-4 l11,10 l8,-3 l13,11 l10,11" fill="none" stroke="var(--o)" stroke-width="1.3" opacity=".65"/><text x="30" y="97" font-size="8" fill="var(--ink3)">왼면 = 회복 · 오른면 = 난립 조각(면 아님)</text></svg>
<div><h4>1 · completeness — 있어야 할 면을 만들었나 <span class="gk">면 · 재현율</span></h4>
<p class="gf mono">C = Σ매칭 |Rᵢ∩P<sub>σ(i)</sub>| ÷ Σ|Rᵢ| &nbsp;≥ 0.80</p>
<p class="gm">분모 = <b>정답</b> 면적. 정답 면 목록 중 매칭으로 회복된 면적 비율. 그림처럼 표면 자체는 덮여 있어도(coverage 통과) 난립 조각이라 상호 겹침 0.5를 만족하는 '면'이 없으면 C가 무너집니다 — "LoD2로서의 재현" 실패.</p>
<button class="exbtn" data-g="comp"></button></div></div>

<div class="grow"><svg viewBox="0 0 170 100"><rect x="25" y="60" width="120" height="26" fill="var(--line2)"/><path d="M25,60 L85,26 L145,60" fill="none" stroke="var(--ink3)" stroke-width="1.6" stroke-dasharray="4 3"/><path d="M25,60 L85,26 L145,60" fill="none" stroke="var(--o)" stroke-width="3"/><path d="M55,43 L95,15 L112,30 Z" fill="var(--o)" opacity=".38" stroke="var(--o)" stroke-width="1"/><text x="97" y="13" font-size="8" fill="var(--ink3)">가짜 면</text></svg>
<div><h4>2 · correctness — 만든 면이 진짜인가 <span class="gk">면 · 정밀도</span></h4>
<p class="gf mono">Corr = Σ매칭 |Rᵢ∩P<sub>σ(i)</sub>| ÷ Σ|Pⱼ| &nbsp;≥ 0.80</p>
<p class="gm">분모 = <b>예측</b> 면적 — completeness와 분모만 다릅니다. 정답 두 면을 다 재현해도(C 통과) 정답에 없는 큰 면을 발명하면 Corr가 깎입니다. MVS 노이즈가 만드는 유령 평면·과분할이 여기 잡힙니다. quality는 이 둘의 합성(교집합/합집합)이라 요약으로만 씁니다.</p>
<button class="exbtn" data-g="corr"></button></div></div>

<div class="grow"><svg viewBox="0 0 170 100"><rect x="25" y="60" width="120" height="26" fill="var(--line2)"/><path d="M25,60 L85,26 L145,60" fill="none" stroke="var(--ink3)" stroke-width="1.6" stroke-dasharray="4 3"/><path d="M25,60 L85,26 L103,37" fill="none" stroke="var(--o)" stroke-width="3"/><path d="M122,48 L145,60" fill="none" stroke="var(--o)" stroke-width="3"/><rect x="104" y="64" width="5" height="5" fill="var(--amber)"/><rect x="110" y="64" width="5" height="5" fill="var(--amber)"/><rect x="116" y="64" width="5" height="5" fill="var(--amber)"/><text x="98" y="80" font-size="8" fill="var(--ink3)">미커버 셀</text></svg>
<div><h4>3 · coverage — 지붕 표면이 빠짐없이 있나 <span class="gk">셀 · 재현율</span></h4>
<p class="gf mono">Cov = |{c∈C_ref : z_model(c) 존재}| ÷ |C_ref| &nbsp;≥ 0.80</p>
<p class="gm">completeness의 셀 버전 — 단 10 m² 문턱이 없어 <b>소면적 결손·구멍</b>을 잡고(주요 면은 완벽해도 걸림), RMSZ가 "커버된 셀에서만" 계산된다는 구멍을 막는 분모 가드입니다. ΔZ 히트맵의 주황 셀이 이 게이트의 실물입니다.</p>
<button class="exbtn" data-g="cov"></button></div></div>

<div class="grow"><svg viewBox="0 0 170 100"><rect x="25" y="60" width="120" height="26" fill="var(--line2)"/><path d="M25,60 L85,26 L145,60" fill="none" stroke="var(--ink3)" stroke-width="1.6" stroke-dasharray="4 3"/><path d="M25,46 L85,12 L145,46" fill="none" stroke="var(--o)" stroke-width="3"/><path d="M85,26 L85,12" stroke="var(--x)" stroke-width="1.4"/><path d="M82,23 L85,26 L88,23 M82,15 L85,12 L88,15" fill="none" stroke="var(--x)" stroke-width="1.4"/><text x="92" y="21" font-size="8" fill="var(--x)">ΔZ</text></svg>
<div><h4>4 · RMSZ — 잡은 표면의 높이가 맞나 <span class="gk">셀 · 잔차(높이)</span></h4>
<p class="gf mono">RMSZ = √( mean<sub>c 커버</sub> (z_model(c) − z_UAS(c))² ) &nbsp;≤ 1.0 m</p>
<p class="gm">면 매칭은 XY 겹침만 보므로 <b>배치·방향이 완벽해도 통째로 떠 있는 모델</b>은 1–3번을 전부 통과합니다 — 그걸 잡는 유일한 게이트. 참조가 E2 입력과 독립인 현시점 UAS 점(셀 P90 z)이므로 자기 일관성이 아니라 검증입니다. P95는 국소 파탄, bias는 계통 오프셋을 가리키는 진단 부속.</p>
<button class="exbtn" data-g="rmse"></button></div></div>

<div class="grow"><svg viewBox="0 0 170 100"><rect x="25" y="60" width="120" height="26" fill="var(--line2)"/><path d="M25,60 L85,26 L145,60" fill="none" stroke="var(--ink3)" stroke-width="1.6" stroke-dasharray="4 3"/><path d="M25,56 L85,44 L145,56" fill="none" stroke="var(--o)" stroke-width="3"/><path d="M46,49 A14,14 0 0 1 49,45" fill="none" stroke="var(--x)" stroke-width="1.4"/><text x="52" y="46" font-size="8" fill="var(--x)">θ</text></svg>
<div><h4>5 · 방향 각오차 — 잡은 면의 기울기·방위가 맞나 <span class="gk">면 · 잔차(방향)</span></h4>
<p class="gf mono">θ̄ = Σ매칭 wᵢ·arccos(n̂_Rᵢ · n̂_Pᵢ) ÷ Σwᵢ,&nbsp; wᵢ=|Rᵢ∩Pᵢ| &nbsp;≤ 10°</p>
<p class="gm">매칭된 면끼리 법선각의 겹침면적 가중 평균. XY는 같은 자리인데 <b>경사가 누운 지붕</b>(MVS 평탄화의 전형)을 잡습니다 — 경사가 약간만 틀리면 RMSZ는 통과할 수 있어서 별도 게이트가 필요. 매칭 생존자만 재는 조건부 지표이며 난립은 1·2번 담당. 태양광 등 LoD2 소비 속성(기울기·방위)의 직접 검증.</p>
<button class="exbtn" data-g="nrm"></button></div></div>

<p class="mnote">종합: <b>O ⇔ C≥0.80 ∧ Corr≥0.80 ∧ Cov≥0.80 ∧ RMSZ≤1.0 m ∧ θ̄≤10°</b> (컷은 비동결 개발값 — 슬라이더로 탐색). 1·2 = 면 수준 "LoD2로서 맞나", 3·4 = 셀 수준 "표면으로서 맞나", 5 = 매칭면의 방향. 다섯이 서로의 맹점을 하나씩 막습니다.</p>
</details>
</div>

<div class="card">
<details class="expl">
<summary>지표의 의미와 출처 — 표준 LoD2 평가 계보와의 대응</summary>
<div style="overflow-x:auto"><table>
<tr><th>지표</th><th>묻는 질문</th><th>낮으면/크면 무슨 뜻</th><th>시각적 대응물 (건물 클릭)</th><th>표준 계보</th></tr>
<tr><td>G3 completeness</td><td>정답 지붕면 면적 중 얼마나 회복했나</td><td>지붕면 누락 — 있어야 할 면을 못 만듦</td><td>평면 매칭도의 <b style="color:var(--amber)">주황 면</b>(놓친 정답면)</td><td class="src">ISPRS building reconstruction protocol의 per-plane completeness</td></tr>
<tr><td>G3 correctness</td><td>예측한 지붕면 면적 중 얼마나 정답에 대응하나</td><td>가짜 면 생성 — 과분할·노이즈 평면</td><td>평면 매칭도의 <b style="color:var(--x)">빨강 면</b>(대응 없는 예측면)</td><td class="src">동 프로토콜의 correctness</td></tr>
<tr><td>G3 quality</td><td>교집합/합집합 종합 (area TP/(TP+FP+FN))</td><td>구조 전반 불일치</td><td>파랑(매칭) 대비 주황+빨강 비율</td><td class="src">동 프로토콜의 quality (IoU형)</td></tr>
<tr><td>G4 coverage</td><td>정답 셀 위에 모델 표면이 존재하나</td><td>지붕 일부가 아예 없음(구멍·부분 생성) · <b>RMSZ의 분모 가드</b>: RMSZ는 커버된 셀에서만 계산되므로 coverage 없으면 부분 모델이 좋은 RMSZ로 통과 가능</td><td>ΔZ 히트맵의 <b style="color:var(--amber)">주황 셀</b>(미커버)</td><td class="src">roofer도 데이터 결손 비율(nodata fraction)을 자체 품질 속성으로 추적</td></tr>
<tr><td>G4 RMSZ</td><td>셀별 높이 오차의 RMS</td><td>전반적 높이·형상 오차</td><td>히트맵의 색 진하기 전반</td><td class="src"><b>roofer가 건물별 자체 계산·배포</b> (rf_rmse_lod22 → 3D BAG b3_rmse_lod22)</td></tr>
<tr><td>G4 P95 |ΔZ|</td><td>최악 5% 높이 오차</td><td>국소 파탄(잘못된 용마루·스파이크)</td><td>히트맵의 진한 <b style="color:var(--x)">빨강</b>/<b style="color:var(--o)">파랑</b> 반점</td><td class="src">DEM/높이 검증 표준(LE95 계열) — roofer 속성은 아님</td></tr>
<tr><td>G4 median bias</td><td>부호 있는 중앙값 오차</td><td>계통 오프셋 — 전체가 일정하게 높거나 낮음(정합 신호)</td><td>히트맵 전체가 한쪽 색으로 치우침</td><td class="src">계통/우연 오차 분리 관행 — roofer 속성은 아님</td></tr>
<tr><td>방향 각오차</td><td>매칭된 지붕면끼리 기울기·방위가 일치하나</td><td>구조는 겹치지만 방향이 틀림 — 평평한 슬래브 vs 경사 지붕 같은 혼동</td><td>3D 비교에서 지붕 경사 차이 · 매칭도 헤더의 면별 각도</td><td class="src">계약 G4의 "optional normal angular error" 슬롯 — <b>v0.1에 없던 추가 후보</b> (매칭 평면 법선각, 겹침면적 가중 평균)</td></tr>
</table></div>
<p class="mnote"><b>확정 판정 세트(참조 검증 스탠스)</b>: 게이트 5 = completeness·correctness(면, vs 참조 평면) + coverage·RMSZ(셀, vs 독립 current-UAS 점군) + 방향 각오차(매칭 면 법선). quality는 C×C 합성 요약, P95는 RMSZ의 로버스트 짝, bias는 정합 신호 — 셋 다 표시만 하고 판정에 쓰지 않음. G0(생성)·G1(schema)·G2(val3dity)는 앞단 게이트(여기선 G0만 반영, 생성실패 65동). 현행 참조는 E1 Roofer proxy(비독립)이며 저널용은 TLS/기구축 LoD2로 승격 예정. RMSXY(경계 평면 잔차)는 미구현 후보.</p>
</details>
</div>

<div class="midrow">
  <div class="card">
    <h2>구조 품질 × 높이 오차 — 컷 라인이 갈라놓는 분포</h2>
    <p class="note">생성·판정가능 건물 중 지표 완전 <span id="scN"></span>동 · 점 클릭 = 건물 상세(3D)</p>
    <div class="legend">
      <span class="it"><span class="dot" style="background:var(--o)"></span>O <b id="legO" class="mono"></b></span>
      <span class="it"><span class="dot" style="background:var(--x)"></span>X <b id="legX" class="mono"></b></span>
      <span class="it"><span class="dot" style="background:none;border:1.5px solid var(--x);width:7px;height:7px"></span>RMSZ &gt; 4 m 클램프 <b id="legC" class="mono"></b></span>
    </div>
    <svg id="scatter" viewBox="0 0 640 430" role="img" aria-label="G3 품질 대 G4 RMSZ 산점도"></svg>
  </div>
  <div class="card">
    <h2>어느 지표가 X를 만들었나</h2>
    <p class="note">현재 컷 기준, X(품질 미달) 건물의 미달 지표 빈도</p>
    <svg id="bars" viewBox="0 0 400 330" role="img" aria-label="미달 지표 빈도"></svg>
  </div>
</div>

<div class="card">
  <h2>판정 지도 — 199동 footprint와 Roofer 대상 AOI</h2>
  <p class="note">건물 색 = 선택 조건의 현재 컷 판정 · <b>회색 = 판정불가(레퍼런스 부족)</b> · <b>연회색 점선 = AOI 밖(이번 census 미실행)</b> · 점선 사각형 = 동결 Roofer 대상 AOI · 건물 클릭 = 상세 열기</p>
  <div class="chips" id="mapConds"></div>
  <div style="overflow:auto"><svg id="map" role="img" aria-label="판정 지도"></svg></div>
</div>

<div class="card">
  <h2>건물별 판정표 — 199동 전수</h2>
  <p class="note">행 클릭 = 판정 근거 시각화(ΔZ 히트맵·평면 매칭) · 열 머리글 클릭 = 정렬 · [3D] = 로컬 뷰어(<span class="mono">localhost:8880</span>)</p>
  <div class="chips" id="chips">
    <button data-f="all" class="on">전체 199</button>
    <button data-f="O">O <span id="cO"></span></button>
    <button data-f="XQ">X 품질 <span id="cX"></span></button>
    <button data-f="FG">생성실패 65</button>
    <button data-f="NA">판정불가 38</button>
    <input id="q" type="search" placeholder="stable_id 검색">
  </div>
  <div class="tblwrap"><table id="tbl">
    <thead><tr>
      <th class="l" data-k="idx">#</th><th class="l" data-k="sid">stable_id</th>
      <th data-k="live">판정</th><th data-k="band">v0.1 밴드</th>
      <th data-k="m0">comp</th><th data-k="m1">corr</th><th data-k="m2" class="diag">qual<i>요약</i></th>
      <th data-k="m3">cov</th><th data-k="m4">RMSZ m</th><th data-k="m5" class="diag">P95<i>진단</i></th><th data-k="m6" class="diag">bias<i>진단</i></th><th data-k="m7">방향°</th>
      <th class="l" data-k="fails">미달 게이트</th><th class="l">E1–E6 판정</th><th>3D</th>
    </tr></thead>
    <tbody></tbody>
  </table></div>
</div>

<p class="foot">
  기준 버전 <code>ROOFER_G3G4_DEVELOPMENT_V0P1_NOT_FROZEN</code> 파생 개발 설정 — 공식 G3/G4·PASS_usable·확증 추론이 아님 ·
  G3·방향 레퍼런스: 원본 CityGML LoD2 RoofSurface(1차, 변화X 가정 — E6엔 순환 주의)·유효 E1(2차) · G4 레퍼런스: shared footprint 내 현시점 UAS class-6 points(0.5 m cell) ·
  원자료 <code>development_g3_g4_building_condition_v0.csv</code> (v16) · footprint <code>DEC-P1-019</code> shared GroundSurface XY ·
  v0.1 밴드 O 31 vs 슬라이더 기본 O 32: 밴드는 plane-count gross mismatch 등 추가 규칙 포함 · 3D 링크는 8880 서버가 도는 머신에서만 동작 · 2026-08-11
</p>
</div>
<div class="tooltip" id="tip"></div>
<div class="modal" id="modal" role="dialog" aria-modal="true"><div class="mbox">
  <div class="mhead">
    <span class="mid mono" id="mId"></span><span id="mBadges"></span><span class="sp"></span>
    <a class="viewer-btn" id="mViewer" href="#" target="_blank" rel="noopener">3D 뷰어 ↗</a>
    <button class="mclose" id="mClose">닫기 ✕</button>
  </div>
  <div class="mcond" id="mCond"></div>
  <div class="m3d">
    <h3 style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">3D 비교 — 드래그 회전 · 휠 줌 · 우클릭/Shift 이동 (카메라 동기화)
      <label style="font-size:12px;font-weight:600;color:var(--ink2)"><input type="checkbox" id="tgMesh" checked> Roofer 면</label>
      <label style="font-size:12px;font-weight:600;color:var(--ink2)"><input type="checkbox" id="tgPts"> Point cloud</label>
      <label style="font-size:12px;font-weight:600;color:var(--ink2)"><input type="checkbox" id="tgCls" checked> Roofer 입력색 (시안=building·갈색=ground·회색=미사용)</label>
      <button id="camReset" style="font:600 11.5px/1 inherit;font-family:inherit;color:var(--o);background:var(--o-soft);border:none;border-radius:999px;padding:5px 11px;cursor:pointer">시야 원복</button>
      <span id="m3dNote" style="font-size:11px;color:var(--ink3);font-weight:400"></span></h3>
    <div id="m3dRow"></div>
  </div>
  <details class="expl" style="margin-top:10px"><summary>판정 근거 시각화 — ΔZ 히트맵 · 평면 매칭 (G3 참조: 기구축 LoD2)</summary>
  <div class="mgrid" id="mGrid"></div></details>
  <div class="mmet" id="mMet"></div>
  <p class="mnote" id="mNote"></p>
</div></div>

<script>
const D = __DATA__;
const VIS = __VIS__;
D.forEach(r=>{const v=VIS[r[0]];r[4].push(v&&v.na!=null?v.na:null);});
// claude.ai 아티팩트에서 열리면 로컬 서버 절대주소로, 8880 통합 뷰어에서 열리면 상대경로로
const EMBEDDED=location.hostname.includes("claude");
const VIEWER=EMBEDDED?"http://localhost:8880/v22/?building=B":"v22/?building=B";
const FPD=__FP__;
const AP=__AP__;
const MET = [
  {k:"comp", n:"G3 completeness ≥", d:0.80, lo:0.30, hi:1.00, st:0.01, dir:1},
  {k:"corr", n:"G3 correctness ≥",  d:0.80, lo:0.30, hi:1.00, st:0.01, dir:1},
  {k:"qual", n:"G3 quality ≥",      d:0.70, lo:0.20, hi:1.00, st:0.01, dir:1},
  {k:"cov",  n:"G4 coverage ≥",     d:0.80, lo:0.30, hi:1.00, st:0.01, dir:1},
  {k:"rmse", n:"G4 RMSZ ≤ (m)",     d:1.00, lo:0.20, hi:3.00, st:0.05, dir:-1},
  {k:"p95",  n:"G4 P95 |Z| ≤ (m)",  d:2.00, lo:0.40, hi:6.00, st:0.10, dir:-1},
  {k:"bias", n:"G4 |median bias| ≤ (m)", d:0.50, lo:0.10, hi:2.00, st:0.05, dir:-1},
  {k:"nrm",  n:"방향 각오차 ≤ (°)", d:10.0, lo:2.00, hi:45.0, st:0.50, dir:-1},
];
// gate = 판정 기준(5), 나머지는 요약/진단 표시 전용
const GATES=[0,1,3,4,7];             // comp, corr, cov, rmse, nrm
const DIAG={2:"요약",5:"진단",6:"진단"}; // quality=C×C 합성, P95=RMSZ 로버스트 짝, bias=정합 신호
const CONDS=["E1","E2","E3","E4","E5","E6","E4v2","E5v2","E4v3","E5v3"];
const CNAME={E1:"E1 · LiDAR→Roofer",E2:"E2 · MVS→Roofer",E3:"E3 · image-only GS",
             E4:"E4 · GS+기구축 ALS(레거시)",E5:"E5 · GS+가중 ALS(레거시)",E6:"E6 · GS+기구축 LoD2(레거시)",
             E4v2:"E4 · 재설계v2(TIN 0.5m)",E5v2:"E5 · 재설계v2(TIN 0.5m)",
             E4v3:"E4 · 재설계v3(TIN 0.25m)",E5v3:"E5 · 재설계v3(TIN 0.25m)"};
const cuts5=()=>[cuts[0],cuts[1],cuts[3],cuts[4],cuts[7]];
const DIR5=[1,1,1,-1,-1];
// per-condition 5-gate classify: 'O','X'(품질),'G'(생성실패),'N'(판정불가)
function classify5(a){
  if(!a)return"N";
  const st=a[5];
  if(st==="M")return"G";
  if(st==="A"||st==="R")return"N";
  const c5=cuts5();
  for(let i=0;i<5;i++){
    const v=a[i];
    if(v==null)return"X";
    if(DIR5[i]>0?v<c5[i]:v>c5[i])return"X";
  }
  return"O";
}
const PRESET = {strict:[1.1,0.8], v01:[1,1], loose:[0.9,1.25], looser:[0.8,1.5], loosest:[0.6,2]};
const cuts = MET.map(m=>m.d);
// scored = 생성됐고 판정 가능한 건물 (RG였어도 LoD2 참조+UAS 기하가 있으면 승격)
const SCORED = D.filter(r=>["S","B","FQ"].includes(r[2])||(r[2]==="RG"&&r[4][0]!=null&&r[4][4]!=null));
const fmt=(v,dp=2)=>v==null?"–":v.toFixed(dp);

function passFails(m){ // gate 5개만 판정에 사용. returns [pass(bool), failList]
  const f=[];
  for(const i of GATES){
    const v=m[i];
    if(v==null){f.push(MET[i].k+" 결측");continue;}
    const c=cuts[i];
    if(MET[i].dir>0 ? v<c : (i===6?Math.abs(v)>c:v>c)) f.push(MET[i].k);
  }
  return [f.length===0,f];
}

// ---------- sliders ----------
const slBox=document.getElementById("sliders");
MET.forEach((m,i)=>{
  if(!GATES.includes(i))return;
  const d=document.createElement("div");d.className="sl";
  d.innerHTML=`<label for="s${i}">${m.n}</label><span class="val mono" id="v${i}"></span>
   <input type="range" id="s${i}" min="${m.lo}" max="${m.hi}" step="${m.st}" value="${m.d}">`;
  slBox.appendChild(d);
  d.querySelector("input").addEventListener("input",e=>{
    cuts[i]=+e.target.value; document.querySelectorAll("#presets button").forEach(b=>b.classList.remove("on"));
    clearTimeout(window.__rt); window.__rt=setTimeout(render,120);
  });
});
function quantile(arr,q){
  const a=arr.filter(v=>v!=null).sort((x,y)=>x-y);
  if(!a.length)return null;
  return a[Math.min(a.length-1,Math.floor(q*a.length))];
}
document.getElementById("presets").addEventListener("click",e=>{
  const key=e.target.dataset.p; if(!key)return;
  if(key==="e1a"){
    // E1 성과 분포 앵커 (참조가 원본 LoD2로 바뀌어 전 게이트 유효): min 지표 P10, max 지표 P90
    const e1=D.map(r=>r[6]&&r[6].E1).filter(a=>a&&a[5]==="P");
    [[0,quantile(e1.map(a=>a[0]),0.10)],[1,quantile(e1.map(a=>a[1]),0.10)],
     [3,quantile(e1.map(a=>a[2]),0.10)],[4,quantile(e1.map(a=>a[3]),0.90)],
     [7,quantile(e1.map(a=>a[4]),0.90)]].forEach(([i,v])=>{
      if(v==null)return;
      cuts[i]=Math.max(MET[i].lo,Math.min(MET[i].hi,Math.round(v/MET[i].st)*MET[i].st));
    });
  }else{
    const p=PRESET[key]; if(!p)return;
    const [mn,mx]=p;
    MET.forEach((m,i)=>{
      cuts[i]=m.dir>0?Math.min(1,m.d*mn):m.d*mx;
      cuts[i]=Math.max(m.lo,Math.min(m.hi,Math.round(cuts[i]/m.st)*m.st));
    });
  }
  document.querySelectorAll("#presets button").forEach(b=>b.classList.toggle("on",b===e.target));
  render();
});

// ---------- scatter ----------
const S={W:640,H:430,L:52,R:14,T:12,B:40};
const sx=v=>S.L+v*(S.W-S.L-S.R);
const sy=v=>S.T+(1-Math.min(v,4)/4)*(S.H-S.T-S.B);
const tip=document.getElementById("tip");
function showTip(ev,r,live){
  const m=r[4];
  tip.innerHTML=`<div class="tid mono">B${String(r[0]).padStart(3,"0")} · ${r[1]}</div>
   판정 <b>${live?"O":"X"}</b> · v0.1 밴드 ${r[3]||"–"}<br>
   G3 c/c/q ${fmt(m[0])} / ${fmt(m[1])} / ${fmt(m[2])}<br>
   G4 cov ${fmt(m[3])} · RMSZ ${fmt(m[4])} m · P95 ${fmt(m[5])} m · bias ${fmt(m[6])} m<br>
   <span style="color:var(--ink3)">클릭 → 3D 뷰어</span>`;
  tip.style.display="block";
  const w=tip.offsetWidth,h=tip.offsetHeight;
  tip.style.left=Math.min(ev.clientX+14,innerWidth-w-8)+"px";
  tip.style.top=Math.min(ev.clientY+14,innerHeight-h-8)+"px";
}
function drawScatter(){
  const svg=document.getElementById("scatter");
  const cs=getComputedStyle(document.body);
  const cO=cs.getPropertyValue("--o").trim(),cX=cs.getPropertyValue("--x").trim(),
        cCard=cs.getPropertyValue("--card").trim();
  let g=`<g class="grid">`;
  for(let i=0;i<=4;i++){const y=sy(i);g+=`<line x1="${S.L}" x2="${S.W-S.R}" y1="${y}" y2="${y}"/>
    <text x="${S.L-8}" y="${y+4}" text-anchor="end" class="mono">${i}</text>`;}
  for(let i=0;i<=5;i++){const v=i*0.2,x=sx(v);g+=`<line y1="${S.T}" y2="${S.H-S.B}" x1="${x}" x2="${x}"/>
    <text x="${x}" y="${S.H-S.B+16}" text-anchor="middle" class="mono">${v.toFixed(1)}</text>`;}
  g+=`</g>`;
  g+=`<text x="${(S.L+S.W-S.R)/2}" y="${S.H-6}" text-anchor="middle">G3 area quality (레퍼런스 plane 대비)</text>`;
  g+=`<text transform="rotate(-90)" x="${-(S.T+(S.H-S.T-S.B)/2)}" y="14" text-anchor="middle">G4 RMSZ (m)</text>`;
  const xq=sx(cuts[2]),yr=sy(cuts[4]);
  g+=`<line x1="${xq}" x2="${xq}" y1="${S.T}" y2="${S.H-S.B}" stroke="${cO}" stroke-dasharray="5 4" stroke-width="1.5" opacity=".75"/>
      <text x="${xq+5}" y="${S.T+12}" style="fill:${cO};font-weight:700">qual ${cuts[2].toFixed(2)}</text>
      <line x1="${S.L}" x2="${S.W-S.R}" y1="${yr}" y2="${yr}" stroke="${cX}" stroke-dasharray="5 4" stroke-width="1.5" opacity=".75"/>
      <text x="${S.W-S.R-4}" y="${yr-6}" text-anchor="end" style="fill:${cX};font-weight:700">RMSZ ${cuts[4].toFixed(2)}</text>`;
  let pts="",n=0,nO=0,nX=0,nC=0;
  SCORED.forEach(r=>{
    const m=r[4]; if(m[2]==null||m[4]==null)return; n++;
    const [ok]=passFails(m);
    const clamp=m[4]>4;
    ok?nO++:nX++; if(clamp)nC++;
    const x=sx(m[2]),y=sy(m[4]),c=ok?cO:cX;
    pts+=clamp
      ?`<path d="M${x} ${y-5}L${x+5} ${y+4}L${x-5} ${y+4}Z" fill="none" stroke="${c}" stroke-width="1.8" data-i="${r[0]}"/>`
      :`<circle cx="${x}" cy="${y}" r="4.4" fill="${c}" stroke="${cCard}" stroke-width="1.6" data-i="${r[0]}"/>`;
    pts+=`<circle cx="${x}" cy="${y}" r="10" fill="transparent" data-i="${r[0]}" style="cursor:pointer"/>`;
  });
  document.getElementById("scN").textContent=n;
  document.getElementById("legO").textContent=nO;
  document.getElementById("legX").textContent=nX;
  document.getElementById("legC").textContent=nC;
  svg.innerHTML=g+pts;
}
document.getElementById("scatter").addEventListener("pointermove",e=>{
  const i=e.target.dataset&&e.target.dataset.i;
  if(!i){tip.style.display="none";return;}
  const r=D.find(r=>r[0]==i); const [ok]=passFails(r[4]); showTip(e,r,ok);
});
document.getElementById("scatter").addEventListener("pointerleave",()=>tip.style.display="none");
document.getElementById("scatter").addEventListener("click",e=>{
  const i=e.target.dataset&&e.target.dataset.i;
  if(i)openDetail(+i);
});

// ---------- minimal 3D mesh viewer (no deps; CSP-safe) ----------
let m3dState=null;
function fpCenter(idx){
  const ring=(FPD.fp[idx]||[[]])[0]||[];
  let A=0,X=0,Y=0;
  for(let i=0;i<ring.length-1;i++){
    const cr=ring[i][0]*ring[i+1][1]-ring[i+1][0]*ring[i][1];
    A+=cr;X+=(ring[i][0]+ring[i+1][0])*cr;Y+=(ring[i][1]+ring[i+1][1])*cr;}
  A*=0.5;return A?[X/(6*A),Y/(6*A),0]:[0,0,0];
}
async function loadOBJ(url,c){
  const t=await (await fetch(url)).text();
  const V=[],F=[];
  for(const line of t.split("\n")){
    if(line.startsWith("v ")){const p=line.trim().split(/\s+/);V.push(+p[1]-c[0],+p[2]-c[1],+p[3]-c[2]);}
    else if(line.startsWith("f ")){
      const idx=line.trim().split(/\s+/).slice(1).map(x=>parseInt(x)-1);
      for(let k=1;k<idx.length-1;k++)F.push(idx[0],idx[k],idx[k+1]);}
  }
  return V.length&&F.length?{v:V,f:F}:null;
}
async function loadPLY(url,c,limit){
  const buf=await (await fetch(url)).arrayBuffer();
  const u8=new Uint8Array(buf);
  const head=new TextDecoder().decode(u8.subarray(0,Math.min(4096,u8.length)));
  const he=head.indexOf("end_header\n");if(he<0)return null;
  const n=+((/element vertex (\d+)/.exec(head)||[])[1]||0);if(!n)return null;
  const off=he+11,stride=16,dv=new DataView(buf);
  const step=Math.max(1,Math.ceil(n/limit));
  const pts=[],cols=[],cls=[];
  for(let i=0;i<n;i+=step){const b=off+i*stride;
    if(b+16>buf.byteLength)break;
    pts.push(dv.getFloat32(b,true)-c[0],dv.getFloat32(b+4,true)-c[1],dv.getFloat32(b+8,true)-c[2]);
    cols.push(u8[b+12],u8[b+13],u8[b+14]);cls.push(u8[b+15]);}
  return {pts,cols,cls};
}
function setup3D(entry,dark,idx){
  const row=document.getElementById("m3dRow"); if(!row)return;
  row.innerHTML="";
  const cs=getComputedStyle(document.body);
  const colO=cs.getPropertyValue("--o").trim(),colAm=cs.getPropertyValue("--amber").trim(),
        ink=dark?"#C8D2DC":"#5A646E";
  const ap=AP[idx]||{};
  const cc=fpCenter(idx);
  const tgM=document.getElementById("tgMesh"),tgP=document.getElementById("tgPts"),
        tgC=document.getElementById("tgCls"),note=document.getElementById("m3dNote");
  if(EMBEDDED){note.textContent="웹 게시판은 내장 mesh만 표시 — 전체 자산은 로컬 8880에서";}
  else note.textContent="Point cloud는 토글을 켜면 로드됩니다 (E1·E2 원본 점군은 수 초)";
  // v22 색 체계: E1 초록, E2 마젠타, GS(E3–E6) 보라, 기구축 LoD2 황색
  const V22={L2:"#EAB308",E1:"#19DC64",E2:"#E62DD2",GS:"#8B5CF6"};
  const DEFS=[["L2","기구축 LoD2",V22.L2],["ALS","기구축 ALS 점군",V22.L2],
              ["E1","E1 · LiDAR",V22.E1],["E2","E2 · MVS",V22.E2],
              ["E3","E3 · GS",V22.GS],["E4","E4 · +ALS",V22.GS],
              ["E5","E5 · +ALS(w)",V22.GS],["E6","E6 · +LoD2",V22.GS],
              ["E4v2","E4 · 재설계v2",V22.GS],["E5v2","E5 · 재설계v2",V22.GS],
              ["E4v3","E4 · 재설계v3",V22.GS],["E5v3","E5 · 재설계v3",V22.GS]];
  // 기구축 LoD2 표시 mesh는 인접 건물까지 포함 → footprint(+8% 버퍼) 안 삼각형만 표시
  function cropToFp(mesh){
    const ring=((FPD.fp[idx]||[])[0]||[]).map(([x,y])=>[(x-cc[0])*1.08,(y-cc[1])*1.08]);
    if(!mesh||ring.length<3)return mesh;
    const inside=(px,py)=>{let c2=false;
      for(let i=0,j=ring.length-1;i<ring.length;j=i++){
        const xi=ring[i][0],yi=ring[i][1],xj=ring[j][0],yj=ring[j][1];
        if(((yi>py)!==(yj>py))&&(px<(xj-xi)*(py-yi)/(yj-yi)+xi))c2=!c2;}
      return c2;};
    const v=mesh.v,f=mesh.f,nf=[];
    for(let i=0;i<f.length;i+=3){
      const cx=(v[f[i]*3]+v[f[i+1]*3]+v[f[i+2]*3])/3,
            cy=(v[f[i]*3+1]+v[f[i+1]*3+1]+v[f[i+2]*3+1])/3;
      if(inside(cx,cy))nf.push(f[i],f[i+1],f[i+2]);
    }
    return nf.length?{v:v,f:nf}:mesh;   // 전부 잘리면(정합 이상) 원본 유지
  }
  const EMB={L2:cropToFp(entry.mp),E1:entry.m1,E2:entry.m2};
  const rb=document.getElementById("camReset");
  if(rb)rb.onclick=()=>{cam.yaw=-0.85;cam.pitch=0.62;cam.zoom=1;cam.pan=[0,0];renderAll();};
  const panels=[];
  DEFS.forEach(([key,name,col])=>{
    const paths=ap[key]||[null,null];
    panels.push({key,name,col,mesh:EMB[key]||null,pts:null,
      meshPath:paths[0],ptsPath:paths[1],ldM:false,ldP:false,cv:null,ctx:null,W:0,H:0});
  });
  // 공유 카메라·경계 (내장 mesh + footprint 기반, 이후 고정)
  let mn=[1e9,1e9,1e9],mx=[-1e9,-1e9,-1e9];
  let any=false;
  panels.forEach(p=>{if(!p.mesh)return;any=true;const v=p.mesh.v;
    for(let i=0;i<v.length;i+=3){for(let k=0;k<3;k++){mn[k]=Math.min(mn[k],v[i+k]);mx[k]=Math.max(mx[k],v[i+k]);}}});
  if(!any){const ring=(FPD.fp[idx]||[[]])[0]||[];
    ring.forEach(([x,y])=>{mn[0]=Math.min(mn[0],x-cc[0]);mn[1]=Math.min(mn[1],y-cc[1]);
      mx[0]=Math.max(mx[0],x-cc[0]);mx[1]=Math.max(mx[1],y-cc[1]);});
    mn[2]=0;mx[2]=12;}
  const c=[(mn[0]+mx[0])/2,(mn[1]+mx[1])/2,(mn[2]+mx[2])/2];
  const R=Math.max(mx[0]-mn[0],mx[1]-mn[1],mx[2]-mn[2],6)/2;
  const cam={yaw:-0.85,pitch:0.62,zoom:1,pan:[0,0]};
  const LGT=[0.28,0.45,0.85],ln=Math.hypot(...LGT);
  const shade=(hex,lum)=>{
    const r=parseInt(hex.slice(1,3),16),g=parseInt(hex.slice(3,5),16),b=parseInt(hex.slice(5,7),16);
    const f=x=>Math.max(0,Math.min(255,Math.round(x*lum+16*(1-lum))));
    return `rgb(${f(r)},${f(g)},${f(b)})`;};
  const fpR=(FPD.fp[idx]||[]).map(r_=>r_.map(([x,y])=>[x-cc[0],y-cc[1]]));
  const gz=(mn[2]<1e8?mn[2]:0);
  function renderPanel(p){
    if(!p.ctx)return;
    const ctx=p.ctx,W=p.W,H=p.H;
    ctx.clearRect(0,0,W,H);
    const sc=Math.min(W,H)/(2.6*R)*cam.zoom;
    const cy=Math.cos(cam.yaw),sy=Math.sin(cam.yaw),cp=Math.cos(cam.pitch),sp=Math.sin(cam.pitch);
    const pr=(x,y,z)=>{x-=c[0];y-=c[1];z-=c[2];
      const xr=x*cy-y*sy,yr=x*sy+y*cy;
      return [W/2+cam.pan[0]+xr*sc,H*0.55+cam.pan[1]-(-yr*sp+z*cp)*sc,yr*cp+z*sp];};
    // shared footprint — 패널별 건물 바닥 높이에 부착 (mesh 최저 z → 점군 하위 2% z → 전역)
    let pgz=gz;
    if(p.mesh){
      if(p._gz===undefined){let mz=1e9;const vv=p.mesh.v;
        for(let i=2;i<vv.length;i+=3)if(vv[i]<mz)mz=vv[i];p._gz=mz;}
      pgz=p._gz;
    }else if(p.pts&&p.pts.pts.length){
      if(p._gzp===undefined){const zs=[];const vv=p.pts.pts;
        for(let i=2;i<vv.length;i+=3)zs.push(vv[i]);
        zs.sort((x,y)=>x-y);p._gzp=zs[Math.floor(zs.length*0.02)];}
      pgz=p._gzp;
    }
    if(fpR.length){
      ctx.setLineDash([5,4]);ctx.strokeStyle="#9FB0C4";ctx.lineWidth=1.2;
      fpR.forEach(r_=>{ctx.beginPath();
        r_.forEach(([x,y],i)=>{const q=pr(x,y,pgz);i?ctx.lineTo(q[0],q[1]):ctx.moveTo(q[0],q[1]);});
        ctx.closePath();ctx.stroke();});
      ctx.setLineDash([]);
    }
    // mesh: painter 렌더 + 저해상 z-buffer (점 가림 판정용)
    let zb=null;const ZS=3;let ZW=0,ZH=0;
    if(tgM.checked&&p.mesh){
      const rn=n=>{const xr=n[0]*cy-n[1]*sy,yr=n[0]*sy+n[1]*cy;
        return [xr,-yr*sp+n[2]*cp,yr*cp+n[2]*sp];};
      const v=p.mesh.v,f=p.mesh.f,solids=[];
      for(let i=0;i<f.length;i+=3){
        const A=[v[f[i]*3],v[f[i]*3+1],v[f[i]*3+2]],
              B=[v[f[i+1]*3],v[f[i+1]*3+1],v[f[i+1]*3+2]],
              C=[v[f[i+2]*3],v[f[i+2]*3+1],v[f[i+2]*3+2]];
        const a=pr(...A),b2=pr(...B),d2=pr(...C);
        let n=[(B[1]-A[1])*(C[2]-A[2])-(B[2]-A[2])*(C[1]-A[1]),
               (B[2]-A[2])*(C[0]-A[0])-(B[0]-A[0])*(C[2]-A[2]),
               (B[0]-A[0])*(C[1]-A[1])-(B[1]-A[1])*(C[0]-A[0])];
        const nl=Math.hypot(...n)||1;n=n.map(x=>x/nl);
        const nv=rn(n);
        const lum=0.52+0.44*Math.abs((nv[0]*LGT[0]+nv[1]*LGT[1]+nv[2]*LGT[2])/ln);
        solids.push([(a[2]+b2[2]+d2[2])/3,a,b2,d2,lum]);
      }
      ZW=Math.ceil(W/ZS);ZH=Math.ceil(H/ZS);
      zb=new Float32Array(ZW*ZH).fill(-1e9);
      for(const [,a,b2,d2] of solids){
        const den=(b2[1]-d2[1])*(a[0]-d2[0])+(d2[0]-b2[0])*(a[1]-d2[1]);
        if(Math.abs(den)<1e-9)continue;
        const x0=Math.max(0,Math.floor(Math.min(a[0],b2[0],d2[0])/ZS)),
              x1=Math.min(ZW-1,Math.ceil(Math.max(a[0],b2[0],d2[0])/ZS)),
              y0=Math.max(0,Math.floor(Math.min(a[1],b2[1],d2[1])/ZS)),
              y1=Math.min(ZH-1,Math.ceil(Math.max(a[1],b2[1],d2[1])/ZS));
        for(let py=y0;py<=y1;py++)for(let px=x0;px<=x1;px++){
          const X=px*ZS+ZS/2,Y=py*ZS+ZS/2;
          const w1=((b2[1]-d2[1])*(X-d2[0])+(d2[0]-b2[0])*(Y-d2[1]))/den;
          const w2=((d2[1]-a[1])*(X-d2[0])+(a[0]-d2[0])*(Y-d2[1]))/den;
          const w3=1-w1-w2;
          if(w1<-0.03||w2<-0.03||w3<-0.03)continue;
          const z=w1*a[2]+w2*b2[2]+w3*d2[2];
          const zi=py*ZW+px;
          if(z>zb[zi])zb[zi]=z;
        }
      }
      solids.sort((u,w)=>u[0]-w[0]);
      for(const [,a,b2,d2,lum] of solids){
        ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b2[0],b2[1]);ctx.lineTo(d2[0],d2[1]);ctx.closePath();
        ctx.fillStyle=shade(p.col,lum);ctx.fill();
        ctx.strokeStyle=shade(p.col,lum*0.55);ctx.lineWidth=0.7;ctx.stroke();
      }
    }
    // points: mesh 뒤에 있으면 가림 (표면 위 점은 0.4 m 허용)
    if(tgP.checked&&p.pts){
      const v=p.pts.pts,col=p.pts.cols,cl=p.pts.cls||[];
      const useCls=tgC&&tgC.checked;
      const cB="#22D3EE",cG="#8B7355",cO2="rgba(148,163,178,0.35)";
      for(let i=0,k=0,m=0;i<v.length;i+=3,k+=3,m++){
        const q=pr(v[i],v[i+1],v[i+2]);
        if(q[0]<-2||q[0]>W+2||q[1]<-2||q[1]>H+2)continue;
        if(zb){
          const zi=(q[1]/ZS|0)*ZW+(q[0]/ZS|0);
          if(zi>=0&&zi<zb.length&&q[2]<zb[zi]-0.4)continue;
        }
        if(useCls){
          const c9=cl[m];
          ctx.fillStyle=c9===6?cB:c9===2?cG:cO2;
        }else ctx.fillStyle=`rgb(${col[k]},${col[k+1]},${col[k+2]})`;
        ctx.fillRect(q[0]-0.8,q[1]-0.8,1.6,1.6);
      }
    }
    if(!p.mesh&&!p.pts){
      ctx.fillStyle="#9FB0C4";ctx.font="12px sans-serif";ctx.textAlign="center";
      ctx.fillText(p.note||"자산 없음",W/2,H/2);
    }
  }
  const renderAll=()=>panels.forEach(renderPanel);
  panels.forEach(p=>{
    const cell=document.createElement("div");cell.className="m3p";
    cell.innerHTML=`<h4>${p.name} <span class="mono" style="font-weight:400;color:var(--ink3)" id="st_${p.key}"></span></h4><canvas></canvas>`;
    row.appendChild(cell);
    p.cv=cell.querySelector("canvas");
    const attach=cv=>{
      let drag=null,panDrag=null;
      cv.addEventListener("contextmenu",e=>e.preventDefault());
      cv.addEventListener("pointerdown",e=>{
        if(e.button===2||e.shiftKey)panDrag=[e.clientX,e.clientY];
        else drag=[e.clientX,e.clientY];
        cv.setPointerCapture(e.pointerId);cv.style.cursor="grabbing";});
      cv.addEventListener("pointermove",e=>{
        if(panDrag){cam.pan[0]+=e.clientX-panDrag[0];cam.pan[1]+=e.clientY-panDrag[1];
          panDrag=[e.clientX,e.clientY];renderAll();return;}
        if(!drag)return;
        cam.yaw+=(e.clientX-drag[0])*0.011;
        cam.pitch=Math.max(0.05,Math.min(1.52,cam.pitch+(e.clientY-drag[1])*0.008));
        drag=[e.clientX,e.clientY];renderAll();});
      cv.addEventListener("pointerup",()=>{drag=null;panDrag=null;cv.style.cursor="grab";});
      cv.addEventListener("wheel",e=>{e.preventDefault();
        cam.zoom=Math.max(0.3,Math.min(8,cam.zoom*(e.deltaY<0?1.12:0.89)));renderAll();},{passive:false});
    };
    attach(p.cv);
  });
  requestAnimationFrame(()=>{
    panels.forEach(p=>{
      const rect=p.cv.getBoundingClientRect();
      const dpr=devicePixelRatio||1;
      p.W=rect.width||300;p.H=rect.height||290;
      p.cv.width=p.W*dpr;p.cv.height=p.H*dpr;
      p.ctx=p.cv.getContext("2d");p.ctx.scale(dpr,dpr);
    });
    renderAll();
    if(!EMBEDDED){
      panels.forEach(p=>{
        if(!p.mesh&&p.meshPath&&!p.ldM){p.ldM=true;
          const st=document.getElementById("st_"+p.key);st.textContent="…";
          loadOBJ((p.meshPath.startsWith("assets_")?"":"v16/")+p.meshPath,cc).then(m=>{p.mesh=m;st.textContent=m?"":"mesh 없음";renderPanel(p);})
            .catch(()=>{st.textContent="로드 실패";});}
        else if(!p.mesh&&!p.meshPath&&!p.ptsPath){p.note="자산 없음";renderPanel(p);}
        else if(!p.mesh&&!p.meshPath){p.note="mesh 없음(점군만)";renderPanel(p);}
      });
    }
  });
  function ensurePts(){
    if(EMBEDDED)return;
    panels.forEach(p=>{
      if(p.ldP||!p.ptsPath)return;
      p.ldP=true;
      const st=document.getElementById("st_"+p.key);st.textContent="점군 로딩…";
      loadPLY((p.ptsPath.startsWith("assets_")?"":"v16/")+p.ptsPath,cc,
              p.ptsPath.startsWith("assets_")?1e9:150000).then(d=>{p.pts=d;st.textContent=d?`${(d.pts.length/3)|0}pt (roofer 입력)`:"점군 없음";renderPanel(p);})
        .catch(()=>{st.textContent="점군 로드 실패";});
    });
  }
  tgM.onchange=renderAll;
  if(tgC)tgC.onchange=renderAll;
  tgP.onchange=()=>{if(tgP.checked)ensurePts();renderAll();};
  m3dState={render:renderAll};
}

// ---------- detail modal ----------
const modal=document.getElementById("modal");
const M3D_TPL=document.querySelector(".m3d").innerHTML;
function metricChips(r){
  const m=r[4],names=["comp","corr","qual","cov","RMSZ","P95","bias","방향°"];
  return m.map((v,i)=>{
    const sh=v==null?"결측":i===6?(v>0?"+":"")+v.toFixed(2):i===7?v.toFixed(1):v.toFixed(2);
    if(!GATES.includes(i))
      return `<span class="mchip na mono">${names[i]} ${sh} <span style="opacity:.6">${DIAG[i]}</span></span>`;
    if(v==null)return `<span class="mchip ng">${names[i]} 결측</span>`;
    const c=cuts[i],bad=MET[i].dir>0?v<c:(i===6?Math.abs(v)>c:v>c);
    const cut=(MET[i].dir>0?"≥":"≤")+(i===7?c.toFixed(1):c.toFixed(2));
    return `<span class="mchip ${bad?"ng":"ok"} mono">${names[i]} ${sh} <span style="opacity:.6">(${cut})</span></span>`;
  }).join("");
}
function openDetail(idx){
  const r=D.find(x=>x[0]===idx); if(!r)return;
  const v=VIS[idx]||{};
  const lv=liveOf(r);
  const dark=document.documentElement.dataset.theme==="dark"||
    (!document.documentElement.dataset.theme&&matchMedia("(prefers-color-scheme: dark)").matches);
  document.getElementById("mId").textContent=`B${String(r[0]).padStart(3,"0")} · ${r[1]}`;
  document.getElementById("mBadges").innerHTML=
    (lv==="O"?'<span class="badge bO">O</span>':lv==="X"?(r[2]==="FG"?CLSB.FG:'<span class="badge bX">X</span>'):CLSB[r[2]])+
    ' <span class="badge bN mono">v0.1 '+({O_CANDIDATE:"O*",REVIEW:"REVIEW*",X_CANDIDATE:"X*"}[r[3]]||"–")+"</span>";
  document.getElementById("mViewer").href=VIEWER+String(r[0]).padStart(3,"0");
  let left="",right="";
  if(v.dz){
    left=`<div class="mcell"><h3>G4 · ΔZ 히트맵 — 모델 상면 − UAS 지붕점 (0.5 m 셀)</h3>
      <img src="${v.dz}" alt="dZ heatmap">
      <div class="mleg"><span class="mono">−2 m</span><span class="grad"></span><span class="mono">+2 m</span>
      <span class="it"><span class="sw" style="background:#E1C878"></span>미커버(모델 표면 없음 → coverage↓)</span></div></div>`;
  }else if(v.ref){
    left=`<div class="mcell"><h3>UAS 지붕 높이 (참고) — E2 Roofer 출력 없음</h3>
      <img src="${v.ref}" alt="reference roof height">
      <div class="mleg">진할수록 높음 · 이 지붕이 존재하지만 E2 LoD2가 생성되지 않음 (G0 실패)</div></div>`;
  }else{
    left=`<div class="mcell"><h3>G4 시각화 불가</h3><p class="mnote">footprint 안 UAS 레퍼런스 셀이 없어 높이 비교를 그릴 수 없습니다.</p></div>`;
  }
  if(v.ov){
    const svg=dark?v.ov.replaceAll("#1B2026","#E6EAEE"):v.ov;
    const pn=v.pn||[0,0,0];
    const naTxt=v.na!=null?` · 방향 오차 ${v.na.toFixed(1)}°${v.nap&&v.nap.length>1?" (면별 "+v.nap.join("/")+"°)":""}`:"";
    right=`<div class="mcell"><h3>G3 · 지붕 평면 매칭 (상공 시점) — 정답 ${pn[0]} · 예측 ${pn[1]} · 매칭 ${pn[2]}${naTxt}</h3>
      <div class="ovsvg">${svg}</div>
      <div class="mleg">
        <span class="it"><span class="sw" style="background:#2E6BA8;opacity:.55"></span>매칭된 예측면</span>
        <span class="it"><span class="sw" style="background:#C2453A;opacity:.55"></span>대응 없는 예측면 → correctness↓</span>
        <span class="it"><span class="sw" style="background:#C98A1F;opacity:.55"></span>놓친 정답면 → completeness↓</span>
        <span class="it"><span class="sw" style="border:1.5px dashed var(--ink3);background:none"></span>footprint / 매칭 정답 외곽</span>
      </div></div>`;
  }else{
    right=`<div class="mcell"><h3>G3 시각화 불가</h3><p class="mnote">${r[2]==="FG"?"E2 모델이 없고 E1 정답 평면도 추출되지 않았습니다.":"정답/예측 평면이 추출되지 않았습니다."}</p></div>`;
  }
  document.getElementById("mGrid").innerHTML=left+right;
  document.getElementById("mMet").innerHTML=(r[2]==="S"||r[2]==="B"||r[2]==="FQ")?metricChips(r):"";
  const notes={FG:"생성 실패: Roofer LoD2 출력이 없어 컷과 무관하게 X입니다."+(r[5]==="GF"?" E1(LiDAR 입력)도 같은 건물에서 생성 실패 — 원인이 영상 품질이 아닐 가능성이 높습니다.":" E1(LiDAR)은 이 건물을 생성함 — E2측(영상 유래) 실패."),
    RG:"UAS 레퍼런스 부족으로 판정 불가(NOT_ASSESSED). X로 집계하지 않습니다.",
    AOI:"footprint가 동결된 Roofer 대상 AOI 밖 — 이번 census에서 실행되지 않았습니다."};
  document.getElementById("mNote").textContent=notes[r[2]]||"지표 칩의 괄호는 현재 슬라이더 컷. 빨강 = 미달.";
  // E1–E6 condition matrix (5-gate, current cuts)
  const BD={O:'<span class="badge bO">O</span>',X:'<span class="badge bX">X</span>',
            G:'<span class="badge bG">생성실패</span>',N:'<span class="badge bN">판정불가</span>'};
  const fm=(v,dp)=>v==null?"–":v.toFixed(dp);
  document.getElementById("mCond").innerHTML=
    `<table><tr><th class="l">조건 (5게이트 동일 컷)</th><th>판정</th><th>comp</th><th>corr</th><th>cov</th><th>RMSZ</th><th>방향°</th></tr>`+
    CONDS.map(c=>{
      const a=r[6]&&r[6][c],k=classify5(a);
      const leg=c==="E6"?' <span style="color:var(--x);font-size:10px">(legacy · 순환: G3참조=prior)</span>'
        :(c==="E4"||c==="E5")?' <span style="color:var(--ink3);font-size:10px">(legacy-base)</span>':"";
      // per-cell X-cause marking: paint the metric cell red when it fails the CURRENT cut
      const cc5=cuts5();
      const bad=i=>{const v=a&&a[i];if(v==null)return true;
        return DIR5[i]>0?v<cc5[i]:v>cc5[i];};
      const cell=(i,dp)=>{const isBad=a&&bad(i);
        return `<td class="mono"${isBad?' style="background:var(--x-soft);color:var(--x);font-weight:700"':""}>${fm(a[i],dp)}${isBad?" ✗":""}</td>`;};
      return `<tr><td class="l">${CNAME[c]}${leg}</td><td>${BD[k]}</td>`+
        (a?cell(0,2)+cell(1,2)+cell(2,2)+cell(3,2)+cell(4,1)
          :`<td colspan="5" class="mono" style="color:var(--ink3)">지표 없음</td>`)+`</tr>`;
    }).join("")+`</table>`;
  modal.classList.add("on");
  const m3dBox=document.querySelector(".m3d");
  m3dBox.innerHTML=M3D_TPL;
  setup3D(v,dark,r[0]);
}
document.getElementById("mClose").addEventListener("click",()=>modal.classList.remove("on"));
modal.addEventListener("click",e=>{if(e.target===modal)modal.classList.remove("on");});
addEventListener("keydown",e=>{if(e.key==="Escape")modal.classList.remove("on");});

// ---------- failed-metric bars ----------
function drawBars(){
  const svg=document.getElementById("bars");
  const cs=getComputedStyle(document.body);
  const cX=cs.getPropertyValue("--x").trim();
  const cnt={};GATES.forEach(i=>cnt[MET[i].k]=0);let miss=0;
  SCORED.forEach(r=>{
    const [ok,f]=passFails(r[4]); if(ok)return;
    f.forEach(k=>{if(k.endsWith("결측"))miss++;else cnt[k]++;});
  });
  const items=GATES.map(i=>({k:MET[i].k,v:cnt[MET[i].k]})).sort((a,b)=>b.v-a.v);
  const max=Math.max(1,...items.map(i=>i.v));
  const BW=400,L=88,R=40,rowH=34,T=10;
  let s="";
  items.forEach((it,i)=>{
    const y=T+i*rowH,w=(BW-L-R)*it.v/max;
    s+=`<text x="${L-8}" y="${y+16}" text-anchor="end" class="mono">${it.k}</text>
        <rect x="${L}" y="${y+6}" width="${Math.max(w,2)}" height="13" rx="4" fill="${cX}" opacity="${it.v?0.88:0.18}"/>
        <text x="${L+Math.max(w,2)+7}" y="${y+16}" class="mono" style="fill:var(--ink);font-weight:700">${it.v}</text>`;
  });
  s+=`<text x="${L-8}" y="${T+GATES.length*rowH+16}" text-anchor="end">결측</text>
      <text x="${L+7}" y="${T+GATES.length*rowH+16}" class="mono" style="fill:var(--ink3)">${miss}건 (게이트 지표 없음→X)</text>`;
  svg.innerHTML=s;
}

// ---------- table ----------
let filter="all",query="",sortK="idx",sortAsc=true;
const rowsBody=document.querySelector("#tbl tbody");
const CLSB={S:'<span class="badge bO">O</span>',B:'<span class="badge bB">경계</span>',
  FQ:'<span class="badge bX">X 품질</span>',FG:'<span class="badge bG">생성실패</span>',
  RG:'<span class="badge bN">레퍼런스 부족</span>',AOI:'<span class="badge bN">AOI 밖</span>'};
const E1B={GF:'<span class="badge bG">E1도 생성실패</span>',O:'<span class="badge bO">E1 O*</span>',
  R:'<span class="badge bB">E1 경계</span>',X:'<span class="badge bX">E1 X*</span>',
  NA:'<span class="badge bN">E1 판정불가</span>'};
function liveOf(r){
  if(r[2]==="FG")return"X";
  if(r[2]==="RG")return (r[4][0]!=null&&r[4][4]!=null)?(passFails(r[4])[0]?"O":"X"):null;
  if(r[2]==="AOI")return null;
  return passFails(r[4])[0]?"O":"X";
}
function sortVal(r,k){
  if(k==="idx")return r[0]; if(k==="sid")return r[1];
  if(k==="live")return liveOf(r)||"zz"; if(k==="band")return r[3];
  if(k==="e1")return r[5];
  if(k==="fails")return passFails(r[4])[1].length;
  if(k.startsWith("m")){const v=r[4][+k[1]];return v==null?1e9:v;}
  return 0;
}
function drawTable(){
  let list=D.filter(r=>{
    if(query&&!r[1].toLowerCase().includes(query))return false;
    const lv=liveOf(r);
    if(filter==="all")return true;
    if(filter==="O")return lv==="O";
    if(filter==="XQ")return lv==="X"&&r[2]!=="FG";
    if(filter==="FG")return r[2]==="FG";
    if(filter==="NA")return lv===null;
    return true;
  });
  list=list.slice().sort((a,b)=>{
    const va=sortVal(a,sortK),vb=sortVal(b,sortK);
    return (va<vb?-1:va>vb?1:0)*(sortAsc?1:-1);
  });
  rowsBody.innerHTML=list.map(r=>{
    const lv=liveOf(r),m=r[4];
    const [_,fails]=(r[2]==="S"||r[2]==="B"||r[2]==="FQ")?passFails(m):[null,[]];
    const rowCls=lv==="X"?(r[2]==="FG"?"rg":"rx"):(lv===null?"rn":"");
    const lvB=lv==="O"?'<span class="badge bO">O</span>':lv==="X"?(r[2]==="FG"?CLSB.FG:'<span class="badge bX">X</span>'):CLSB[r[2]];
    const cells=m.map((v,i)=>{
      const t=v==null?"–":i===6?(v>0?"+":"")+v.toFixed(2):i===7?v.toFixed(1):v.toFixed(2);
      return `<td class="mono ${v==null?"miss":""} ${DIAG[i]?"diag":""}">${t}</td>`;}).join("");
    return `<tr class="${rowCls}" data-i="${r[0]}" style="cursor:pointer">
      <td class="l mono">B${String(r[0]).padStart(3,"0")}</td>
      <td class="l mono" title="${r[1]}">${r[1].replace("DEBY_LOD2_","…")}</td>
      <td>${lvB}</td><td class="mono">${{O_CANDIDATE:"O*",REVIEW:"REVIEW*",X_CANDIDATE:"X*",NOT_ASSESSED:"–"}[r[3]]||"–"}</td>
      ${cells}
      <td class="l"><span class="fails">${fails.join(", ")||(lv==="O"?"—":"")}</span></td>
      <td class="l"><span class="cstrip">${CONDS.map(c=>{
        const k=classify5(r[6]&&r[6][c]);
        return `<i class="c${k}" title="${CNAME[c]}: ${{O:"O",X:"X 품질",G:"생성실패",N:"판정불가"}[k]}">${c[1]}</i>`;
      }).join("")}</span></td>
      <td><a href="${VIEWER+String(r[0]).padStart(3,"0")}" target="_blank" rel="noopener">3D</a></td>
    </tr>`;
  }).join("");
}
document.querySelectorAll("thead th[data-k]").forEach(th=>th.addEventListener("click",()=>{
  const k=th.dataset.k;
  if(sortK===k)sortAsc=!sortAsc;else{sortK=k;sortAsc=true;}
  drawTable();
}));
document.getElementById("chips").addEventListener("click",e=>{
  const f=e.target.dataset&&e.target.dataset.f;if(!f)return;
  filter=f;
  document.querySelectorAll("#chips button").forEach(b=>b.classList.toggle("on",b.dataset.f===f));
  drawTable();
});
document.getElementById("q").addEventListener("input",e=>{query=e.target.value.trim().toLowerCase();drawTable();});
rowsBody.addEventListener("click",e=>{
  if(e.target.closest("a"))return;
  const tr=e.target.closest("tr[data-i]");
  if(tr)openDetail(+tr.dataset.i);
});

// ---------- judgment map ----------
let mapCond="E2";
const mapChipBox=document.getElementById("mapConds");
CONDS.forEach(c=>{
  const b=document.createElement("button");
  b.textContent=CNAME[c];b.dataset.c=c;
  if(c===mapCond)b.classList.add("on");
  b.addEventListener("click",()=>{mapCond=c;
    mapChipBox.querySelectorAll("button").forEach(x=>x.classList.toggle("on",x===b));
    drawMap();});
  mapChipBox.appendChild(b);
});
function drawMap(){
  const svg=document.getElementById("map");
  let mn=[1e9,1e9],mx=[-1e9,-1e9];
  Object.values(FPD.fp).forEach(rings=>rings.forEach(r=>r.forEach(([x,y])=>{
    mn[0]=Math.min(mn[0],x);mn[1]=Math.min(mn[1],y);
    mx[0]=Math.max(mx[0],x);mx[1]=Math.max(mx[1],y);})));
  const pad=18,W=mx[0]-mn[0]+2*pad,H=mx[1]-mn[1]+2*pad;
  svg.setAttribute("viewBox",`0 0 ${W.toFixed(0)} ${H.toFixed(0)}`);
  const [ax0,ay0,ax1,ay1]=FPD.aoi;
  let s=`<g transform="translate(${(-mn[0]+pad).toFixed(1)},${(mx[1]+pad).toFixed(1)}) scale(1,-1)">`;
  s+=`<rect x="${ax0}" y="${ay0}" width="${(ax1-ax0).toFixed(1)}" height="${(ay1-ay0).toFixed(1)}"
       fill="none" stroke="var(--ink2)" stroke-width="1.6" stroke-dasharray="8 5"/>`;
  D.forEach(r=>{
    const rings=FPD.fp[r[0]]; if(!rings)return;
    const a=r[6]&&r[6][mapCond], k=classify5(a), st=a?a[5]:"A";
    let fill,extra="";
    if(k==="O")fill="var(--o)";
    else if(k==="X")fill="var(--x)";
    else if(k==="G")fill="var(--maroon)";
    else if(st==="A"){fill="var(--gray-soft)";extra=`stroke-dasharray="2 1.5" stroke="var(--ink3)" stroke-width="0.8"`;}
    else fill="var(--gray)";
    const d=rings.map(ring=>"M"+ring.map(p=>p[0]+","+p[1]).join("L")+"Z").join("");
    s+=`<path class="mapb" d="${d}" fill="${fill}" fill-opacity="${k==="N"?0.75:0.9}" ${extra} data-i="${r[0]}"/>`;
  });
  s+=`<text transform="scale(1,-1)" x="${ax0+4}" y="${(-ay1-6).toFixed(1)}"
      style="font-size:11px;fill:var(--ink2)">Roofer 대상 AOI (동결)</text></g>`;
  svg.innerHTML=s;
}
document.getElementById("map").addEventListener("click",e=>{
  const i=e.target.dataset&&e.target.dataset.i;
  if(i)openDetail(+i);
});
document.getElementById("map").addEventListener("pointermove",e=>{
  const i=e.target.dataset&&e.target.dataset.i;
  if(!i){return;}
  const r=D.find(x=>x[0]==i);
  const k=classify5(r[6]&&r[6][mapCond]);
  tip.innerHTML=`<span class="tid mono">B${String(r[0]).padStart(3,"0")}</span> · ${CNAME[mapCond]}<br>판정: <b>${{O:"O",X:"X 품질",G:"생성실패",N:"판정불가"}[k]}</b>`;
  tip.style.display="block";
  tip.style.left=Math.min(e.clientX+14,innerWidth-tip.offsetWidth-8)+"px";
  tip.style.top=Math.min(e.clientY+14,innerHeight-tip.offsetHeight-8)+"px";
});
document.getElementById("map").addEventListener("pointerleave",()=>tip.style.display="none");

// ---------- gate anatomy: live real-example buttons ----------
function updateExemplars(){
  const map={comp:0,corr:1,cov:3,rmse:4,nrm:7};
  for(const [g,i] of Object.entries(map)){
    const btn=document.querySelector(`.exbtn[data-g="${g}"]`); if(!btn)continue;
    const ex=SCORED.find(r=>{const [ok,f]=passFails(r[4]);return !ok&&f.length===1&&f[0]===MET[i].k;});
    if(ex){btn.style.display="";
      btn.textContent=`실제 사례 — B${String(ex[0]).padStart(3,"0")}: 현재 컷에서 이 게이트만 미달 (클릭해서 3D·히트맵 확인)`;
      btn.onclick=()=>openDetail(ex[0]);}
    else{btn.style.display="";btn.disabled=true;btn.style.opacity=.5;btn.onclick=null;
      btn.textContent="현재 컷에서 이 게이트 단독 미달 건물 없음 (다른 게이트와 동반 미달)";}
  }
}

// ---------- render ----------
function render(){
  MET.forEach((m,i)=>{
    const s=document.getElementById("s"+i);
    if(!s)return;
    s.value=cuts[i];
    document.getElementById("v"+i).textContent=cuts[i].toFixed(2);
  });
  let o=0,x=0;
  SCORED.forEach(r=>{passFails(r[4])[0]?o++:x++;});
  const naCnt=D.filter(r=>liveOf(r)===null).length;
  document.getElementById("kO").textContent=o;
  document.getElementById("kX").textContent=x;
  document.getElementById("kOs").textContent=`생성·판정가능 ${SCORED.length}동 중`;
  document.getElementById("kN").textContent=naCnt;
  document.getElementById("kNs").textContent=`UAS 점 부족 ${naCnt-20} · AOI 밖 20`;
  const rate=(100*o/(199-naCnt));
  document.getElementById("kR").textContent=rate.toFixed(0)+"%";
  document.getElementById("kRs").textContent=`O ${o} / (${x}+65) X`;
  document.getElementById("cO").textContent=o;
  document.getElementById("cX").textContent=x;
  // E2→m transitions on jointly assessable buildings (X includes 생성실패)
  const tr=["E3","E4","E5","E6","E4v2","E5v2","E4v3","E5v3"].map(m=>{
    let up=0,down=0;
    D.forEach(r=>{
      const a=classify5(r[6]&&r[6].E2),b=classify5(r[6]&&r[6][m]);
      if(a==="N"||b==="N")return;
      const aX=a!=="O",bX=b!=="O";
      if(aX&&!bX)up++; if(!aX&&bX)down++;
    });
    return `${m} <b style="color:var(--o)">+${up}</b>/<b style="color:var(--x)">−${down}</b>`;
  }).join(" · ");
  document.getElementById("kT").innerHTML=tr;
  const med=a=>{const v=a.filter(x=>x!=null).sort((x,y)=>x-y);return v.length?v[v.length>>1]:null;};
  document.getElementById("condSum").innerHTML=
    '<tr><th class="l">조건</th><th>O</th><th>품질X</th><th>생성실패</th><th>판정불가</th><th>comp</th><th>corr</th><th>cov</th><th>RMSZ</th><th>방향°</th></tr>'+
    CONDS.map(c=>{const s0={O:0,X:0,G:0,N:0},vals=[[],[],[],[],[]];
      D.forEach(r=>{const a=r[6]&&r[6][c];const k=classify5(a);s0[k]++;
        if(a&&a[5]==="P")for(let i=0;i<5;i++)vals[i].push(a[i]);});
      const m=vals.map((v,i)=>{const q=med(v);return q==null?"–":(i===4?q.toFixed(1):i===3?q.toFixed(2):q.toFixed(2));});
      return '<tr><td class="l">'+CNAME[c]+'</td><td class="mono" style="color:var(--o);font-weight:700">'+s0.O+'</td><td class="mono">'+s0.X+'</td><td class="mono">'+s0.G+'</td><td class="mono">'+s0.N+'</td><td class="mono">'+m[0]+'</td><td class="mono">'+m[1]+'</td><td class="mono">'+m[2]+'</td><td class="mono">'+m[3]+'</td><td class="mono">'+m[4]+'</td></tr>';}).join("");
  drawScatter();drawBars();drawTable();updateExemplars();drawMap();
}
render();
new MutationObserver(render).observe(document.documentElement,{attributes:true,attributeFilter:["data-theme"]});
</script>
"""

html = HTML.replace("__DATA__", DATA).replace("__VIS__", VISJ).replace("__FP__", FPJ).replace("__AP__", APJ)
open(OUT, "w").write(html)

# self-served copy needs its own charset/doctype (the Artifact wrapper adds these for the web copy)
serve_path = os.path.join(BASE, "serve", "index.html")
if os.path.isdir(os.path.dirname(serve_path)):
    open(serve_path, "w").write(
        '<!doctype html>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n' + html)
    print("wrote", serve_path)
print("wrote", OUT, len(html), "bytes,", len(rows), "buildings")
