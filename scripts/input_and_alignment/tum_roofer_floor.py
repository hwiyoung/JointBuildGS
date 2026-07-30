"""Step 1c P-a — measure the Roofer density/noise floor (host orchestrator).
Decimate/noise classified ALS -> P0 Roofer -> val3dity, per (density,noise).
Floor = lowest density / highest noise where target reps still produce a valid roof.
Reuses P0 Roofer/val3dity (Docker). Engine logic unchanged. Observation only."""
import json, os, subprocess, importlib.util, sys
from pathlib import Path

REPO=Path.cwd()
P0=REPO/"phases/p0-audit"
COMPOSE=["docker","compose","-f",str(P0/"env/docker-compose.p0.yml")]
ENV={**os.environ,"P0_UID":str(os.getuid()),"P0_GID":str(os.getgid())}
OUT=P0/"runs/tum_floor"; OUT.mkdir(parents=True,exist_ok=True)
REPS=["DEBY_LOD2_4906972","DEBY_LOD2_4906969","DEBY_LOD2_4908023"]
BOX=[690894.0,5335911.0,690977.0,5336127.0]   # union of 3 reps + ~12 m
CONFIGS=[("d16_n0",16,0.0),("d8_n0",8,0.0),("d4_n0",4,0.0),("d2_n0",2,0.0),("d1_n0",1,0.0),
         ("d8_n0p1",8,0.1),("d8_n0p2",8,0.2),("d8_n0p5",8,0.5),("d8_n1p0",8,1.0)]

# reuse P0 combine_cityjsonseq
spec=importlib.util.spec_from_file_location("r08", P0/"scripts/08_roofer_w2.py")
r08=importlib.util.module_from_spec(spec); sys.modules["r08"]=r08
try: spec.loader.exec_module(r08); HAVE_COMBINE=hasattr(r08,"combine_cityjsonseq")
except Exception as e: print("combine import failed:",repr(e)); HAVE_COMBINE=False

def sh(cmd):
    return subprocess.run(cmd,env=ENV,cwd=REPO,text=True,capture_output=True)

def roofer_success(jsonl_dir, bid):
    """Return (model_made, n_roofsurfaces) for building bid from roofer jsonl."""
    for p in Path(jsonl_dir).glob("*.city.jsonl"):
        for line in open(p):
            try: d=json.loads(line)
            except: continue
            co=d.get("CityObjects",{})
            part=co.get(f"{bid}-0")
            if part:
                rs=0
                for g in part.get("geometry",[]):
                    if str(g.get("lod"))=="2.2":
                        rs+=sum(1 for s in g.get("semantics",{}).get("surfaces",[]) if s.get("type")=="RoofSurface")
                return (rs>0, rs)
    return (False,0)

print("## ROOFER FLOOR (decimated/noised ALS -> Roofer -> val3dity)")
print("| config | target_dens | noise | achieved_dens | "+" | ".join(b.replace('DEBY_LOD2_','')+"(roofs/valid)" for b in REPS)+" |")
print("|---|---|---|---|"+"---|"*len(REPS))
for tag,dens,noise in CONFIGS:
    las=f"/workspace/JointBuildGS/phases/p0-audit/runs/tum_floor/als_{tag}.las"
    dec=sh(["docker","run","--rm","--user",f"{os.getuid()}:{os.getgid()}",
            "-v",f"{REPO}:/workspace/JointBuildGS","-w","/workspace/JointBuildGS","jointbuildgs-p0-tools:t0",
            "python3","scripts/input_and_alignment/_als_decimate.py","--box",*map(str,BOX),
            "--density",str(dens),"--noise",str(noise),"--out",las])
    ach="?"
    for ln in dec.stdout.splitlines():
        if "achieved_density" in ln: ach=ln.split("achieved_density=")[-1].strip()
    if dec.returncode!=0:
        print(f"| {tag} | {dens} | {noise} | DECIMATE-FAIL | "+" | ".join("-" for _ in REPS)+" |"); print(dec.stderr[-300:]); continue
    rdir=f"/workspace/runs/tum_floor/roofer_{tag}"
    rf=sh(COMPOSE+["run","-T","--rm","roofer","--id-attribute","building_id","--box",*[f"{v:.3f}" for v in BOX],
                   f"/workspace/runs/tum_floor/als_{tag}.las","/workspace/data/work/w2/footprints_scene_aoi.gpkg",rdir])
    jsonl_dir=OUT/f"roofer_{tag}"
    # val3dity
    valid_by_id={}
    if HAVE_COMBINE and any(jsonl_dir.glob("*.city.jsonl")):
        cj=OUT/f"{tag}.city.json"; rep=OUT/f"{tag}.report.json"
        try:
            r08.combine_cityjsonseq(sorted(jsonl_dir.glob("*.city.jsonl")), cj)
            sh(COMPOSE+["run","-T","--rm","tools","val3dity",f"/workspace/runs/tum_floor/{tag}.city.json",
                        "--report",f"/workspace/runs/tum_floor/{tag}.report.json"])
            if rep.exists():
                for ft in json.loads(rep.read_text()).get("features",[]):
                    valid_by_id[str(ft.get("id"))]=ft.get("validity",None)
        except Exception as e: print(f"  val3dity {tag} failed: {e!r}")
    cells=[]
    for bid in REPS:
        made,rs=roofer_success(jsonl_dir,bid)
        v=valid_by_id.get(bid); v=valid_by_id.get(f"{bid}-0",v)
        vs="?" if v is None else ("valid" if v else "INVALID")
        cells.append(f"{'Y' if made else 'N'}:{rs}/{vs}")
    print(f"| {tag} | {dens} | {noise} | {ach} | "+" | ".join(cells)+" |")
print("[done floor]")
