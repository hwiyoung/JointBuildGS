"""Data of the 'explain' view of the 3D viewer: the old surface as the mesh the stage-2 prior maps were rendered from, the real
surface as photo-coloured points, and the numbered places where the two disagree, each with its physical reading and a
section to look at (jointbuildgs:dev, CPU). scientific_verdict: null.

  python export_explain.py [--points 500000]
Mounts: /s2 (payload, rw for dashboard/surfels/), /artifacts/JointBuildGS (ro).

mesh_<prior>_<scene>.bin  magic JBMS3D1, uint32 n_vertices, uint32 n_triangles, float32 xyz[n_v*3], uint32 idx[n_t*3],
                          float32 region[n_t] (1 roof-like, 2 wall-like): LoD2 = the registered v2 mesh (+0.12 m) of the
                          target building (its 6 roof + 12 wall faces); ALS = the registered v2 2.5D TIN (global OBJ + the stage-1
                          shift to the local frame) cropped to the target building box + 3 m (region by the triangle normal, |n_z| >= 0.5 roof-like).
photo_points.bin          magic JBPH3D1, uint32 count, uint32 floats (= 11): xyz (MVS depth lifted, A=1), rgb (photo),
                          class under M_N, M_B, L_N, L_B (1 agree, 2 conflict), region: a uniform sample of the target pixels
                          the photos measured (15 views, training resolution).
places.json               per setting: the numbered places (anchor xyz, section orientation, zoom) and their text, with the
                          numbers taken from eval/anatomy_breakdown_30000.csv and dashboard/intent/anatomy.js."""
import argparse
import csv
import json
from pathlib import Path

import cv2
import numpy as np

S2 = Path("/s2"); MAPS = S2 / "inputs/maps"; OUT = S2 / "dashboard/surfels"
ART = Path("/artifacts/JointBuildGS")
S1 = ART / "phase-payloads/phd/stage1_conf_tol_conflict_v1"
V2 = S1 / "PHD-STAGE1-VERIFY-v2/inputs_v2"
PJ = {p["poly_index"]: p for p in json.loads((S1 / "PHD-STAGE1-CONF-TOL-CONFLICT-v1/inputs/lod2_polygons.json").read_text())["polygons"]}
SPARSE = ART / "phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921/conditions/B+1.0/scene/sparse_txt"
PHOTOS = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/scene/images"
TRAIN = (1600, 1157)
SETS = ["M_N", "M_B", "L_N", "L_B"]
ap = argparse.ArgumentParser()
ap.add_argument("--points", type=int, default=500_000)
a = ap.parse_args()
faces = json.loads((MAPS / "faces.json").read_text())
ROOF, WALL = [int(f) for f in faces["roof"]], [int(f) for f in faces["wall"]]
TGT = ROOF + WALL


def q2R(q):
    w, x, y, z = q
    return np.array([[1 - 2*y*y - 2*z*z, 2*x*y - 2*z*w, 2*x*z + 2*y*w], [2*x*y + 2*z*w, 1 - 2*x*x - 2*z*z, 2*y*z - 2*x*w],
                     [2*x*z - 2*y*w, 2*y*z + 2*x*w, 1 - 2*x*x - 2*y*y]])


calib = json.loads((S2 / "runs/P_M_N/scene/jbgs_calibration.json").read_text())["images"]
CAMS = {}
for line in (SPARSE / "images.txt").read_text().splitlines():
    t = line.split()
    if len(t) >= 10 and not line.startswith("#") and t[9].lower().endswith(".jpg"):
        name = Path(t[9]).stem
        CAMS[name] = dict(R=q2R([float(v) for v in t[1:5]]), t=np.array([float(v) for v in t[5:8]]), K=np.array(calib[name]["K"]))
VIEWS = sorted(CAMS)


def load(setname, view, dtype=np.float32):
    p = MAPS / setname / "raw_depth" / f"{view}.npy"
    x = np.load(p if p.exists() else MAPS / setname / f"{view}.npy")
    return cv2.resize(x.astype(np.float32), TRAIN, interpolation=cv2.INTER_NEAREST).astype(dtype)


def write_mesh(path, V, T, region):
    with path.open("wb") as fh:
        fh.write(b"JBMS3D1\0"); fh.write(np.uint32(len(V)).tobytes()); fh.write(np.uint32(len(T)).tobytes())
        V.astype(np.float32).tofile(fh); T.astype(np.uint32).tofile(fh); region.astype(np.float32).tofile(fh)


# ---- the prior meshes
xy = np.concatenate([np.array(PJ[f]["ring_local_xy"]) for f in TGT])
BOX = (xy[:, 0].min() - 3, xy[:, 0].max() + 3, xy[:, 1].min() - 3, xy[:, 1].max() + 3)
anchors_mesh = {}
for scene, name in (("N", "lod2_v2_nominal_local.npz"), ("B", "lod2_v2_biased_main_local.npz")):
    d = np.load(V2 / name)
    keep = np.isin(d["poly_of_tri"], TGT)
    T = d["faces"][keep]; used = np.unique(T); remap = -np.ones(len(d["vertices_local"]), np.int64); remap[used] = np.arange(len(used))
    V = d["vertices_local"][used]; T = remap[T]
    region = np.where(np.isin(d["poly_of_tri"][keep], ROOF), 1, 2)
    write_mesh(OUT / f"mesh_M_{scene}.bin", V, T, region)
    if scene == "N":
        for f in (3403, 3404, 3387, 3389, 3396, 3391):
            tri = d["faces"][d["poly_of_tri"] == f]
            anchors_mesh[f] = d["vertices_local"][np.unique(tri)].mean(0)
    print("mesh M", scene, len(V), "vertices", len(T), "triangles", flush=True)


def read_obj(path):
    v, f = [], []
    with open(path) as fh:
        for line in fh:
            if line.startswith("v "):
                v.append(line.split()[1:4])
            elif line.startswith("f "):
                f.append([int(x.split("/")[0]) - 1 for x in line.split()[1:4]])
    return np.array(v, np.float64), np.array(f, np.int64)


SHIFT = np.array(json.loads((S1 / "PHD-STAGE1-CONF-TOL-CONFLICT-v1/inputs/lod2_polygons.json").read_text())["shift_global_to_local"])
for scene, name in (("N", "als_v2_nominal.obj"), ("B", "als_v2_biased_main.obj")):
    V, T = read_obj(V2 / name)
    V = V + SHIFT                                                          # the v2 OBJ files are in global coordinates
    c = V[T].mean(1)
    keep = (c[:, 0] > BOX[0]) & (c[:, 0] < BOX[1]) & (c[:, 1] > BOX[2]) & (c[:, 1] < BOX[3])
    T = T[keep]; used = np.unique(T); remap = -np.ones(len(V), np.int64); remap[used] = np.arange(len(used))
    Vk = V[used]; Tk = remap[T]
    nrm = np.cross(Vk[Tk[:, 1]] - Vk[Tk[:, 0]], Vk[Tk[:, 2]] - Vk[Tk[:, 0]])
    nz = np.abs(nrm[:, 2]) / np.maximum(np.linalg.norm(nrm, axis=1), 1e-12)
    write_mesh(OUT / f"mesh_L_{scene}.bin", Vk, Tk, np.where(nz >= 0.5, 1, 2))
    print("mesh L", scene, len(Vk), "vertices", len(Tk), "triangles", flush=True)

# check: the lifted LoD2 prior depth lies on the mesh (vertical offset on the main roof 3396)
d = np.load(V2 / "lod2_v2_nominal_local.npz"); tri = d["faces"][d["poly_of_tri"] == 3396]; vv = d["vertices_local"][np.unique(tri)]
nrm = np.cross(vv[1] - vv[0], vv[2] - vv[0]); nrm /= np.linalg.norm(nrm)
off = []
for v in VIEWS[:5]:
    P, F = load("prior_M_N", v), load("faceid", v, np.int32)
    ys, xs = np.nonzero((F == 3396) & np.isfinite(P))
    k = np.random.default_rng(0).choice(len(ys), size=min(2000, len(ys)), replace=False); ys, xs = ys[k], xs[k]
    cam = CAMS[v]; K = cam["K"]; dd = P[ys, xs]
    X = (np.stack([(xs - K[0, 2]) / K[0, 0] * dd, (ys - K[1, 2]) / K[1, 1] * dd, dd], 1) - cam["t"]) @ cam["R"]
    off.append(((X - vv[0]) @ nrm) / abs(nrm[2]))
print("check: prior_M_N depth vs v2 mesh plane on 3396, vertical offset median %.4f m" % np.median(np.concatenate(off)), flush=True)

# ---- photo-coloured real surface: the pixels the photos measured (A=1) on the target building
cand = []
for vi, v in enumerate(VIEWS):
    A, M, F = load("conf", v), load("mvs", v), load("faceid", v, np.int32)
    ys, xs = np.nonzero(np.isin(F, TGT) & (A > 0) & np.isfinite(M) & (M > 0))
    cand.append(np.stack([np.full(ys.size, vi), ys, xs], 1))
cand = np.concatenate(cand)
sel = cand[np.sort(np.random.default_rng(1).choice(len(cand), size=min(a.points, len(cand)), replace=False))]
rec = []
for vi, v in enumerate(VIEWS):
    s = sel[sel[:, 0] == vi]; ys, xs = s[:, 1], s[:, 2]
    A, M, FV, F = load("conf", v), load("mvs", v), load("fvert", v), load("faceid", v, np.int32)
    photo = cv2.cvtColor(cv2.resize(cv2.imread(str(next(PHOTOS.glob(f"{v}.*")))), TRAIN, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
    cam = CAMS[v]; K = cam["K"]; dd = M[ys, xs]
    r = np.zeros((ys.size, 11), np.float32)
    r[:, 0:3] = (np.stack([(xs - K[0, 2]) / K[0, 0] * dd, (ys - K[1, 2]) / K[1, 1] * dd, dd], 1) - cam["t"]) @ cam["R"]
    r[:, 3:6] = photo[ys, xs] / 255.0
    for j, st in enumerate(SETS):
        pr, sc = st.split("_")
        P, T = load(f"prior_{pr}_{sc}", v), load(f"tau_{pr}", v)
        p, t = P[ys, xs], T[ys, xs]
        r[:, 6 + j] = np.where(np.isfinite(p) & (p > 0) & np.isfinite(t), np.where(np.abs(dd - p) <= t, 1, 2), 0)
    r[:, 10] = np.where(np.isin(F[ys, xs], ROOF), 1, 2)
    rec.append(r)
rec = np.concatenate(rec)
with (OUT / "photo_points.bin").open("wb") as fh:
    fh.write(b"JBPH3D1\0"); fh.write(np.uint32(len(rec)).tobytes()); fh.write(np.uint32(11).tobytes()); rec.tofile(fh)
print("photo points", len(rec), "of", len(cand), flush=True)

# ---- places and their reading (numbers from the anatomy outputs)
BD = {}
with (S2 / "eval/anatomy_breakdown_30000.csv").open() as fh:
    for r in csv.DictReader(fh):
        BD[(r["setting"], r["region"], r["place"].split(" (")[0])] = r
anat = json.loads((S2 / "dashboard/intent/anatomy.js").read_text().split("=", 1)[1].rstrip().rstrip(";"))
f3 = PJ[3403]; r3 = np.array(f3["ring_local_xy"]); n3 = np.array(f3["normal"])[:2]; n3 /= np.linalg.norm(n3); al3 = np.array([-n3[1], n3[0]])
z0 = float(anat["height_reference_scene_z"])
facade = np.r_[r3.mean(0) + al3 * float(anat["facade_cut_offset_m"]), z0 + 9.0]


def g(st, reg, place, key, cast=float):
    r = BD.get((st, reg, place)); return cast(r[key]) if r and r[key] not in ("", "None") else None


def share(st, reg, *places):
    return sum(g(st, reg, p, "share_of_region_conflicts") or 0 for p in places)


places = {}
for st in SETS:
    pr, sc = st.split("_"); P = "LoD2" if pr == "M" else "ALS"
    fw = BD.get((st, "wall", "정면 벽"))
    items = []
    if pr == "M":
        items.append(dict(n=1, anchor=facade.tolist(), slab="across", dist=5.0,
                          title="정면 벽", text=f"LoD2 벽면이 실제 평벽보다 약 {float(fw['prior_minus_photo_cm']):.0f} cm 바깥 — 정면 벽 전체에 걸친 일정한 차이",
                          share=f"벽 충돌의 {float(fw['share_of_region_conflicts']):.0%}"))
        hip = anat["priors"]["M"]["facts"]["hip_max_excess_m"]
        items.append(dict(n=2, anchor=anchors_mesh[3404].tolist(), slab="along", dist=16.0,
                          title="건물 끝 경사면", text=f"LoD2의 끝 경사면이 실제보다 짧고 가팔라 최대 {hip:.1f} m 위 — 실제 경사면은 약 6 m 더 안쪽에서 시작",
                          share=f"지붕 충돌의 {share(st, 'roof', '건물 끝 경사면', '본지붕 중 건물 끝 9 m'):.0%}"))
        items.append(dict(n=3, anchor=((anchors_mesh[3387] + anchors_mesh[3389]) / 2).tolist(), slab="along", dist=14.0,
                          title="뒤쪽 날개 지붕", text=f"LoD2가 실제 지붕보다 약 {-g(st, 'roof', '뒤쪽 날개 지붕', 'prior_minus_photo_cm'):.0f} cm 아래",
                          share=f"지붕 충돌의 {share(st, 'roof', '뒤쪽 날개 지붕'):.0%}"))
        rest = BD.get((st, "roof", "본지붕 나머지"))
        items.append(dict(n=4, anchor=anchors_mesh[3396].tolist(), slab="across", dist=24.0,
                          title="본지붕", text=(f"대부분 LoD2와 사진이 같은 자리(일치). 충돌은 두 입력이 약 {float(rest['prior_minus_photo_cm']):.0f} cm 달라 τ(5.7 cm)를 살짝 넘는 경계선 — "
                                              f"참값에서 사진 {float(rest['err_photo_cm']):.0f} cm, LoD2 {float(rest['err_prior_cm']):.0f} cm로 둘 다 가까워 어느 쪽이 틀렸다고 가를 수 없다")
                          if sc == "N" else "옛 자료의 본지붕을 일부러 1 m 올린 장면 — 본지붕 전체가 충돌",
                          share=f"지붕 충돌의 {share(st, 'roof', '본지붕 나머지') if sc == 'N' else share(st, 'roof', '본지붕 나머지', '본지붕 중 건물 끝 9 m'):.0%}"))
    else:
        items.append(dict(n=1, anchor=facade.tolist(), slab="across", dist=5.0,
                          title="정면 벽", text="ALS(2.5D TIN)에는 수직 벽이 없다 — 지붕 가장자리 점과 건물 앞 땅 점을 잇는 삼각형이 벽 자리: 밑동은 실제 벽보다 약 30 cm, 꼭대기는 약 3 cm 바깥으로 기운 면",
                          share=f"벽 충돌의 {float(fw['share_of_region_conflicts']):.0%}"))
        items.append(dict(n=2, anchor=anchors_mesh[3404].tolist(), slab="along", dist=16.0,
                          title="건물 끝 경사면", text="ALS는 실제 경사면을 따라간다(LoD2와 달리 2 m 쐐기가 없음). 충돌은 용마루·처마처럼 TIN이 모서리를 깎는 곳",
                          share=f"지붕 충돌의 {share(st, 'roof', '건물 끝 경사면', '본지붕 중 건물 끝 9 m'):.0%}"))
        items.append(dict(n=3, anchor=((anchors_mesh[3387] + anchors_mesh[3389]) / 2).tolist(), slab="along", dist=14.0,
                          title="뒤쪽 날개 지붕", text="ALS는 모양을 따라간다. 충돌은 면 가장자리와 지붕 위 구조물",
                          share=f"지붕 충돌의 {share(st, 'roof', '뒤쪽 날개 지붕'):.0%}"))
        items.append(dict(n=4, anchor=anchors_mesh[3396].tolist(), slab="across", dist=24.0,
                          title="본지붕", text=("ALS와 사진이 거의 같다(가운데 차이 0 cm). 충돌은 τ(4.1 cm)를 살짝 넘는 가장자리 띠" if sc == "N"
                                              else "옛 자료의 본지붕을 일부러 1 m 올린 장면 — 본지붕 전체가 충돌"),
                          share=f"지붕 충돌의 {share(st, 'roof', '본지붕 나머지') if sc == 'N' else share(st, 'roof', '본지붕 나머지', '본지붕 중 건물 끝 9 m'):.0%}"))
    places[st] = items
(OUT / "places.json").write_text(json.dumps(dict(places=places, base_z=z0), ensure_ascii=False, indent=1))
print(json.dumps(places["M_N"], ensure_ascii=False)[:600])
print("done")
