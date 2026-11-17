"""PHD-MAIN-JUDGEABL-v1 5절 (기존 4 결합, 전 건물): 옮겨 온 결합 구현(inherited/, BASELINES-v1 handover 와 바이트 같음)을 지역 설정으로
돌리기 위한 경로 층. 판정 규칙(mf_common.RULE, detect.decide 등)은 하나도 바꾸지 않는다. 바꾸는 것은 입력을 어디서 읽는지뿐:
  views      Views() (937 영상 모델, 격자 1024 x 741 K) + 설정의 학습 영상 (기하 깊이 지도가 있는 것만, s03 과 같음)
  'mvs'      설정의 COLMAP 작업 폴더 stereo/depth_maps/<영상>.geometric.bin, 유한하고 > 0 인 화소 (= s03 v6 내보내기 mvs 지도)
  'prior'    정합한 사전 정보 메시를 그 영상에서 다시 던진 깊이 (= s03 v6 내보내기 prior 지도; judge 는 원래도 다시 던져 대조함)
  'tau'      만들지 않음 (NaN): 색 참고 히스토그램에만 쓰이고 판정에는 쓰이지 않는다
  영상       설정의 영상 폴더 (상자: STAGE0 fork 입력, 지역: 이 작업이 fork_inputs_v6 와 같은 방법(INTER_AREA, JPEG 95)으로 만든 것)
  메시·범위  설정의 메시 폴더 (lod2_mesh.npz / als_mesh.npz / range.json), 정합 이동 = 설정의 summary.json registration.shift_applied
  격자       range.json polygon_local + 10 m, 0.25 m (원래와 같음); 평가 범위는 판정에 쓰이지 않으므로 전부 참
쓰는 곳: /res (PH/main_judgeabl_v1/PHD-MAIN-JUDGEABL-v1/fusion_all) 만. scientific_verdict: null."""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "inherited"))
import mf_common as M  # noqa: E402
import detect as DT  # noqa: E402
from common import Views, read_depth_bin  # noqa: E402  (/repo/scripts/phd/main_stage0_v1, mf_common 이 넣은 경로)

RES = Path("/res")
CFGP = Path("/cfg/judgeabl_v1_fusion_all.json")
LOCK = Path("/cfg/judgeabl_v1_fusion_all.lock.json")


def sha(p):
    import hashlib
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def cfg():
    lock = json.loads(LOCK.read_text())
    assert sha(CFGP) == lock["config_sha256"], "config changed after lock"
    for k, v in lock["inherited_sha256"].items():
        assert sha(HERE / "inherited" / k) == v, ("inherited code changed", k)
    return json.loads(CFGP.read_text())


C = cfg()
SITES = C["sites"]
M.SB = RES / "sb"                      # pairs_<site>.json 를 쓰고 읽는 곳 (원래 SB/prep/mvsfuse)
_V = None


def site_cfg(site):
    return SITES[site]


class GridViews(Views):
    """Views() (937 영상 모델) 의 이름을 '<stem>.jpg' 로 (fork 장면의 이름 규칙; 자세·K 는 같다)."""

    def __init__(self):
        super().__init__()
        self.ims = {k.rsplit(".", 1)[0] + ".jpg": v for k, v in self.ims.items()}
        self.names = sorted(self.ims)


def _views():
    global _V
    if _V is None:
        _V = GridViews()
    return _V


def train_views(site):
    s = site_cfg(site)
    lst = json.loads(Path(s["views_file"]).read_text())
    lst = lst[s.get("views_key", "train")] if isinstance(lst, dict) else lst
    stems = [n.rsplit(".", 1)[0] for n in lst]
    have = [x for x in stems if (Path(s["mvs_dir"]) / "stereo/depth_maps" / f"{x}.JPG.geometric.bin").exists()]
    return have, sorted(set(stems) - set(have))


def views(site):
    tr, _ = train_views(site)
    return _views(), tr, []


def mvs_map(site, stem):
    d = read_depth_bin(Path(site_cfg(site)["mvs_dir"]) / "stereo/depth_maps" / f"{stem}.JPG.geometric.bin")
    assert d.shape == (M.H, M.W), (stem, d.shape)
    return np.where(np.isfinite(d) & (d > 0), d, np.nan).astype(np.float32)


def prior_map(stem):
    P = DT.G["P"]; V = DT.G["V"]; n = f"{stem}.jpg"
    R = V.rays(n, np.float64); Cc = V.C(n)
    t, _ = DT.ocast(P.scene(), np.broadcast_to(Cc, R.shape), R)
    return np.where(np.isfinite(t), t, np.nan).reshape(M.H, M.W).astype(np.float32)


def load_map(site, prior, kind, stem):
    if kind == "mvs":
        return mvs_map(site, stem)
    if kind == "prior":
        return prior_map(stem)
    if kind == "tau":
        return np.full((M.H, M.W), np.nan, np.float32)
    raise KeyError(kind)


def read_rgb(site, stem):
    import cv2
    p = Path(site_cfg(site)["images_dir"]) / f"{stem}.jpg"
    img = cv2.imread(str(p), cv2.IMREAD_COLOR)
    if img is None or img.shape[:2] != (M.H, M.W):
        raise RuntimeError(f"image {p}: {None if img is None else img.shape}")
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32)


def shift_of(site, prior):
    f = Path(site_cfg(site)["shift_from"].format(prior=prior))
    return np.asarray(json.loads(f.read_text())["registration"]["shift_applied"], np.float64)


class Prior(M.Prior):
    """= mf_common.Prior, 메시 폴더만 설정에서 (원래 DR/s02_box/<site>)."""

    def __init__(self, site, prior):
        self.site, self.prior = site, prior
        md = Path(site_cfg(site)["mesh_dir"])
        self.shift = M.shift_of(site, prior)
        if prior == "LoD2":
            m = np.load(md / "lod2_mesh.npz")
            self.V, self.F = m["V"].astype(np.float64) + self.shift, m["F"].astype(np.int64)
            self.tri_bld = m["tri_building"].astype(np.int64)
            self.tri_type = m["tri_type"].astype(np.int64)
            self.tri_surface = m["tri_surface"].astype(np.int64)
            self.building_names = [str(x) for x in m["building_names"]]
        else:
            m = np.load(md / "als_mesh.npz")
            self.V, self.F = m["V"].astype(np.float64) + self.shift, m["F"].astype(np.int64)
            self.building_tri = m["building_tri"].astype(bool)
            self.tri_bld = M.tri_components(self.F, self.building_tri)
            self.tri_type = None
            self.tri_surface = m["tri_surface"].astype(np.int64)
            self.building_names = None
        self.n_bld = int(self.tri_bld.max()) + 1 if (self.tri_bld >= 0).any() else 0
        nrm = np.cross(self.V[self.F[:, 1]] - self.V[self.F[:, 0]], self.V[self.F[:, 2]] - self.V[self.F[:, 0]])
        self.nz = np.abs(nrm[:, 2]) / np.maximum(np.linalg.norm(nrm, axis=1), 1e-12)
        self._scene = None
        self._bscene = None


class Grid(M.Grid):
    """= mf_common.Grid, 범위 파일만 설정의 메시 폴더에서; 평가 범위(in_eval)는 판정에 쓰이지 않아 전부 참."""

    def __init__(self, site, margin=10.0):
        rng = json.loads((Path(site_cfg(site)["mesh_dir"]) / "range.json").read_text())
        P = np.asarray(rng["polygon_local"], np.float64).reshape(-1, 2)
        self.lo = np.floor((P.min(0) - margin) / M.CELL) * M.CELL
        hi = np.ceil((P.max(0) + margin) / M.CELL) * M.CELL
        self.nx, self.ny = int(round((hi[0] - self.lo[0]) / M.CELL)), int(round((hi[1] - self.lo[1]) / M.CELL))
        self.B = M.basis()
        cx = self.lo[0] + (np.arange(self.nx) + 0.5) * M.CELL
        cy = self.lo[1] + (np.arange(self.ny) + 0.5) * M.CELL
        gx, gy = np.meshgrid(cx, cy)
        self.centres = np.stack([gx, gy], -1)
        self.in_eval = np.ones((self.ny, self.nx), bool)


M.views, M.load_map, M.read_rgb, M.shift_of, M.Prior, M.Grid = views, load_map, read_rgb, shift_of, Prior, Grid


def grid_of(site):
    return Grid(site)


def jdump(p, o):
    M.jdump(p, o)


def now():
    import datetime as dt
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec="seconds")
