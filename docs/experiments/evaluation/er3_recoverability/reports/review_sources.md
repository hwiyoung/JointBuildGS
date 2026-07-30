# ER3 review — source extract (GS-JSO / P2)

> **읽기 전용 추출.** 코드는 한 줄도 수정하지 않았다. 각 블록 머리에 `파일경로:라인범위`.
> 거대한 파일(`mutual.py`, `train.py`)은 관련부만 발췌하고 생략 구간을 표기했다.

- **git commit:** `3af7babca84461f1c28a495e74922e0351f76844` (branch `feature/p2-gsjso`)

**추출한 파일 목록**
- `src/stage2/loss/mutual.py` — L_mutual 계산 (1)
- `src/stage2/loss/data_fitting.py` — L_sem 등 데이터항 (2,4)
- `src/stage2/loss/structure.py` — L_structure 계산 (4)
- `src/stage2/renderer.py` — render_semantic + 기하 detach (2)
- `src/stage2/model.py` — SfM 점 → 가우시안 초기화 (3a)
- `src/stage2/densification.py` — gsplat DefaultStrategy 래퍼: 임계·옵티마이저 (3b)
- `src/stage2/train.py` — 모델 생성·loss 집계·mutual/structure 호출·densify 훅 (1,3,4)
- `configs/tum_mob/{vanilla,baseline,mutual,structure,both}.yaml` — 토글 키 (5)
- `configs/input_and_alignment/tum_gravity.json` — e_gravity (1)

> **densify/clone/split/prune 알고리즘 본체는 외부 라이브러리 `gsplat.strategy.DefaultStrategy`에 있다**
> (이 레포 아님). 레포는 `densification.py:build_strategy`로 임계만 주입하고, `train.py`에서 훅을 호출한다.

---

## 1) L_mutual (의미↔기하 결합 / 벽 법선 수직화)

#### `src/stage2/loss/mutual.py:60-94` — 함수 시그니처 (가중치·토글 인자)
```python
def l_mutual(
    normals: torch.Tensor,          # (N, 3) per-primitive normals in world frame
    centers: torch.Tensor,          # (N, 3) per-primitive centers in world frame
    sem_logits: torch.Tensor,       # (N, K=4) raw semantic logits
    e_gravity: torch.Tensor,        # (3,) unit gravity vector, e.g. (0,0,-1)
    tau: float = 0.15,
    height_th: float = 0.15,        # world-height threshold separating Terrain / Roof
    w_vert: float = 1.0,
    w_slope: float = 1.0,
    w_horiz: float = 1.0,
    w_height: float = 1.0,
    w_height_roof: float = 1.0,
    w_height_terrain: float = 1.0,
    mode: str = "full",             # "full" | "sem2geo" | "geo2sem"
    enable_wall_vertical: bool = True,
    enable_roof_nonwall: bool = True,
    enable_terrain_normal: bool = True,
    enable_terrain_height: bool = True,
    enable_height_roof_side: bool = True,
    enable_height_terrain_side: bool = True,
    terrain_gate_mode: str = "none",
    terrain_gate_conf_min: float = 0.0,
    terrain_gate_mass_min: float = 0.0,
    terrain_gate_entropy_max: float = 1.0,
    terrain_height_reference: str = "fixed",
    terrain_height_quantile: float = 0.5,
    terrain_height_margin: float = 0.0,
    enable_sem_geom_calib: bool = False,
    semcal_classes: str = "roof_wall",
    semcal_tau: float = 0.05,
    semcal_weight_beta: float = 0.0,
    semcal_reliability_gate: str = "conf_entropy",
    semcal_entropy_tau: float = 0.75,
    semcal_entropy_alpha: float = 0.10,
) -> dict:
```
> (95–124 생략: 인자 검증 only.)

#### `src/stage2/loss/mutual.py:125-197` — 핵심: 클래스 확률 · 법선 dot · 기하항 · 가중합
```python
    # Class probabilities
    p = F.softmax(sem_logits, dim=-1)       # (N, 4)
    p_roof = p[:, 1]
    p_wall = p[:, 2]
    p_terrain = p[:, 3]
    terrain_gate = torch.ones_like(p_terrain)
    if terrain_gate_mode == "confidence":
        with torch.no_grad():
            terrain_gate = (p_terrain >= float(terrain_gate_conf_min)).to(p_terrain.dtype)
    elif terrain_gate_mode in {"class_mass", "mass_entropy"}:
        with torch.no_grad():
            entropy = -(p * (p.clamp_min(1e-8).log())).sum(dim=-1)
            entropy = entropy / torch.log(torch.tensor(float(p.shape[-1]), device=p.device))
            terrain_mass = p_terrain.mean()
            terrain_entropy = (p_terrain * entropy).sum() / p_terrain.sum().clamp_min(1e-8)
            gate_value = terrain_mass >= float(terrain_gate_mass_min)
            if terrain_gate_mode == "mass_entropy":
                gate_value = gate_value and terrain_entropy <= float(terrain_gate_entropy_max)
        terrain_gate = torch.full_like(p_terrain, float(gate_value))

    if mode == "sem2geo":
        p_roof = p_roof.detach()
        p_wall = p_wall.detach()
        p_terrain = p_terrain.detach()
        terrain_gate = terrain_gate.detach()

    # Normalize and dot with gravity
    n = F.normalize(normals, dim=-1, eps=1e-6)
    c = centers
    e_g = e_gravity.to(n.device)
    if mode == "geo2sem":
        n = n.detach()
        c = c.detach()

    dot = (n * e_g).sum(dim=-1)             # (N,)

    # Geometric terms
    L_vert  = dot ** 2                       # wall: 0 when horizontal
    L_horiz = (1.0 - dot.abs()) ** 2         # terrain: 0 when vertical (|n·g|=1)
    L_slope = F.relu(tau - dot ** 2) ** 2    # roof: penalty if too horizontal (wall-like)

    # Height term — uses component along gravity's magnitude direction
    # World Z-up: e_g ≈ (0,0,-1), so "height" = centers along +gravity opposite = -c·e_g
    # Equivalently: height = (-c) · e_g, but cleaner to use the axis with largest |e_g|
    ax = _height_axis(e_g)
    sign = -torch.sign(e_g[ax])              # +1 if e_g points in -Z (Z-up world)
    height = sign * c[:, ax]                 # (N,) larger = higher altitude

    # Roof should be above height_th, Terrain below
    L_h_roof = F.relu(height_th - height) ** 2
    terrain_height_th = torch.tensor(float(height_th), device=height.device, dtype=height.dtype)
    if terrain_height_reference == "terrain_quantile":
        with torch.no_grad():
            weights = (p_terrain * terrain_gate).clamp_min(0)
            total_weight = weights.sum()
            if total_weight > 1e-8 and height.numel() > 0:
                order = torch.argsort(height)
                h_sorted = height[order]
                w_sorted = weights[order]
                cdf = torch.cumsum(w_sorted, dim=0) / total_weight
                q = float(min(max(terrain_height_quantile, 0.0), 1.0))
                q_tensor = torch.tensor(q, device=height.device, dtype=height.dtype)
                idx = torch.searchsorted(cdf, q_tensor).clamp(max=len(h_sorted) - 1)
                terrain_height_th = h_sorted[idx].detach() + float(terrain_height_margin)
    L_h_terrain = F.relu(height - terrain_height_th) ** 2

    # Weighted sum per primitive, mean over all primitives
    loss_vert_raw = (p_wall * L_vert).mean()
    loss_slope_raw = (p_roof * L_slope).mean()
    loss_horiz_raw = (p_terrain * terrain_gate * L_horiz).mean()
    loss_h_roof_raw = (p_roof * L_h_roof).mean()
    loss_h_terrain_raw = (p_terrain * terrain_gate * L_h_terrain).mean()
    loss_height_raw = (p_roof * L_h_roof + p_terrain * terrain_gate * L_h_terrain).mean()
```
> (199–241 생략: 선택적 `enable_sem_geom_calib` (FC-S6E semcal) — 본 P2 ablation에선 비활성.)

#### `src/stage2/loss/mutual.py:242-271` — 항 on/off + total 합성
```python
    loss_vert = loss_vert_raw if enable_wall_vertical else zero
    loss_slope = loss_slope_raw if enable_roof_nonwall else zero
    loss_horiz = loss_horiz_raw if enable_terrain_normal else zero
    loss_h_roof = loss_h_roof_raw if enable_height_roof_side else zero
    loss_h_terrain = (
        loss_h_terrain_raw
        if (enable_terrain_height and enable_height_terrain_side)
        else zero
    )
    legacy_height_path = (
        enable_height_roof_side
        and enable_terrain_height
        and enable_height_terrain_side
        and terrain_height_reference == "fixed"
        and float(w_height_roof) == 1.0
        and float(w_height_terrain) == 1.0
    )
    if legacy_height_path:
        # Preserve the legacy reduction exactly when all height controls are on.
        loss_height = loss_height_raw
    else:
        loss_height = float(w_height_roof) * loss_h_roof + float(w_height_terrain) * loss_h_terrain

    total = (
        w_vert * loss_vert
        + w_slope * loss_slope
        + w_horiz * loss_horiz
        + w_height * loss_height
        + float(semcal_weight_beta) * loss_semcal
    )
```

#### `src/stage2/train.py:455-506` — l_mutual 호출 + **total loss에 더해지는 라인과 가중치 키** (`w_mutual`)
```python
        mutual_weight_scale = _mutual_weight_scale(it, mutual_warmup, mutual_schedule, mutual_ramp_steps)
        if (w_mutual > 0 and mutual_weight_scale > 0
                and e_gravity is not None and hasattr(model, "sem_logits")):
            mut = l_mutual(
                normals=model.normals(),
                centers=model.means,
                sem_logits=model.sem_logits,
                e_gravity=e_gravity,
                tau=mutual_tau,
                height_th=mutual_height_th,
                w_vert=mutual_w_wall_vertical,
                w_slope=mutual_w_roof_nonwall,
                w_horiz=mutual_w_terrain_normal,
                w_height=mutual_w_height,
                w_height_roof=mutual_w_height_roof,
                w_height_terrain=mutual_w_height_terrain,
                mode=mutual_mode,
                enable_wall_vertical=mutual_enable_wall_vertical,
                # ... (enable_*/terrain_gate_*/semcal_* 인자 생략) ...
            )
            loss_mut_total = mut["total"]
            # ... (per-term unpack 생략) ...
            loss_total = loss_total + (w_mutual * mutual_weight_scale) * loss_mut_total
```
> 가중치 키 = **`w_mutual`** (× warmup ramp `mutual_weight_scale`). 호출 게이트: `w_mutual>0 AND e_gravity 존재 AND model.sem_logits 존재`.

#### `configs/input_and_alignment/tum_gravity.json` — `e_gravity`
```json
{
  "up": [0.0, 0.0, 1.0],
  "e_gravity": [0.0, 0.0, -1.0],
  "source": "EPSG:25832 Z-up (orthometric height); GS-local = EPSG - [690953,5336071,604] is a pure translation, so Z stays up.",
  "note": "TUM aerial scene. Gravity direction (e_gravity) points -Z (down). Wall normals should be horizontal (perp to e_gravity); roof above terrain along +Z."
}
```

---

## 2) 의미 렌더 + 기하 detach (라벨이 기하를 못 끌어오는 핵심)

#### `src/stage2/renderer.py:97-138` — render_semantic (**기하 means/quats/scales/opacities를 detach**, 119-123)
```python
def render_semantic(
    model: GaussianModel2D,
    viewmat: torch.Tensor,
    K: torch.Tensor,
    width: int,
    height: int,
    near_plane: float = 0.01,
    far_plane: float = 1e10,
) -> torch.Tensor:
    """Render per-pixel semantic logits by alpha-compositing model.sem_logits.

    Gradient isolation: geometry params (means, quats, scales, opacities, SH) are
    detached inside this function, so L_sem's gradient flows ONLY back through
    model.sem_logits. This keeps L_sem from corrupting geometry optimization.

    Returns:
        (H, W, K) float — raw logits (not softmaxed).
    """
    device = model.means.device
    viewmats = viewmat.unsqueeze(0).to(device)
    Ks = K.unsqueeze(0).to(device)

    # Detach geometry so only sem_logits receives gradient.
    means = model.means.detach()
    quats = model.quats.detach()
    scales = model.scales.detach()
    opacities = model.opacities.detach()
    # gsplat 1.5 expects non-SH feature colors to carry the camera batch
    # dimension, i.e. (C, N, D), even for a single view.
    colors_feat = model.sem_logits.unsqueeze(0) if model.sem_logits.ndim == 2 else model.sem_logits

    out = rasterization_2dgs(
        means=means, quats=quats, scales=scales, opacities=opacities,
        colors=colors_feat,
        viewmats=viewmats, Ks=Ks,
        width=width, height=height,
        near_plane=near_plane, far_plane=far_plane,
        render_mode="RGB",  # just feature alpha blending
        sh_degree=None,
    )
    render_feat = out[0][0]  # (H, W, K)
    return render_feat
```
> **→ ER3 핵심 제약:** `means/quats/scales/opacities`가 detach 되어 `L_sem`(아래 호출)의 gradient는 `model.sem_logits`로만 흐른다. 라벨이 기하를 생성/이동시키지 못하는 구조적 원인.

#### `src/stage2/train.py:428-434` — L_sem 호출 (위 detach된 sem_pred 사용)
```python
        # Semantic (only if GT provided and w_sem > 0)
        if "semantic" in batch and w_sem > 0 and hasattr(model, "sem_logits"):
            from .renderer import render_semantic
            sem_pred = render_semantic(model, w2c, K, W, H)
            sem_gt = batch["semantic"].to(device)
            loss_sem = L.l_sem(sem_pred, sem_gt, ignore_index=0)
            loss_total = loss_total + w_sem * loss_sem
```

#### `src/stage2/loss/data_fitting.py:72-81` — l_sem (CE, ignore_index=0)
```python
def l_sem(
    sem_pred: torch.Tensor,       # (H, W, K) raw logits
    sem_gt: torch.Tensor,         # (H, W) int64 labels
    ignore_index: int = 0,
) -> torch.Tensor:
    """CrossEntropy with ignore_index. sem_gt values outside [0, K-1] are ignored."""
    H, W, K = sem_pred.shape
    logits = sem_pred.reshape(-1, K)      # (H*W, K)
    labels = sem_gt.reshape(-1).long()    # (H*W,)
    return F.cross_entropy(logits, labels, ignore_index=ignore_index)
```

---

## 3) Densification & 초기화

### 3a) SfM/COLMAP 점 → 가우시안 초기화

#### `src/stage2/model.py:48-100` — GaussianModel2D.__init__ (COLMAP 점에서 means/scale/opacity/SH/sem 초기화)
```python
class GaussianModel2D(nn.Module):
    def __init__(
        self,
        points_xyz: np.ndarray,
        points_rgb: np.ndarray,
        sh_degree: int = 3,
        init_scale_factor: float = 1.0,
        device: str = "cuda",
    ):
        super().__init__()
        self.sh_degree = sh_degree
        self.max_sh_degree = sh_degree
        self.active_sh_degree = 0  # warmup

        N = points_xyz.shape[0]
        xyz = torch.from_numpy(points_xyz).float()
        rgb = torch.from_numpy(points_rgb).float()

        # --- centers ---
        self.means = nn.Parameter(xyz.to(device))

        # --- quats: identity (w=1) ---
        quats = torch.zeros(N, 4)
        quats[:, 0] = 1.0
        self.quats = nn.Parameter(quats.to(device))

        # --- scales: 3 dims for gsplat; dim 0,1 = in-plane, dim 2 ≈ 0 (planar) ---
        s0 = _estimate_init_scale(points_xyz, k=3) * init_scale_factor  # (N,)
        log_s = torch.log(torch.from_numpy(s0).float().clamp_min(1e-6))
        log_scales = torch.zeros(N, 3)
        log_scales[:, 0] = log_s
        log_scales[:, 1] = log_s
        log_scales[:, 2] = math.log(1e-6)  # near-zero thickness → planar (2DGS)
        self.log_scales = nn.Parameter(log_scales.to(device))

        # --- opacity: sigmoid^-1(0.1) ~ -2.197 ---
        opa = torch.full((N,), _inv_sigmoid(0.1))
        self.opacities_raw = nn.Parameter(opa.to(device))

        # --- SH ---
        # DC from RGB in SH0 basis: C0 = 0.2820947917 ; sh_dc = (rgb - 0.5) / C0
        C0 = 0.28209479177387814
        sh0 = ((rgb - 0.5) / C0)[:, None, :]  # (N,1,3)
        n_rest = (sh_degree + 1) ** 2 - 1
        shN = torch.zeros(N, n_rest, 3)
        self.sh0 = nn.Parameter(sh0.to(device))
        self.shN = nn.Parameter(shN.to(device))

        # --- semantic logits f_i (N, K) ---
        # K=4: BG(0), Roof(1), Wall(2), Terrain(3). Init near-uniform with small noise
        self.num_classes = 4
        sem = 0.01 * torch.randn(N, self.num_classes)
        self.sem_logits = nn.Parameter(sem.to(device))
```
> **→ ER3 핵심:** 가우시안 수 N = COLMAP SfM 점 수. 무텍스처 영역은 SfM 점이 없어 N에 안 들어가고, 이후 densify(아래)는 *기존* 점만 clone/split → 무텍스처에 새 프리미티브가 안 생긴다.

#### `src/stage2/train.py:266-272` — 모델 생성 (dataset의 SfM 점 주입)
```python
    # ---------- model ----------
    model = GaussianModel2D(
        points_xyz=ds.points_xyz,
        points_rgb=ds.points_rgb,
        sh_degree=cfg.get("sh_degree", 3),
        device=device,
    )
```
> `ds.points_xyz`는 `dataloader.py`가 `colmap_io.read_points3d_bin(sparse/points3D.bin)`로 읽은 SfM 점.

### 3b) densify / clone / split / prune

#### `src/stage2/densification.py:60-83` — build_strategy: gsplat DefaultStrategy에 임계 주입
```python
def build_strategy(
    prune_opa: float = 0.005,
    grow_grad2d: float = 2e-4,
    grow_scale3d: float = 0.01,
    prune_scale3d: float = 0.1,
    refine_start_iter: int = 500,
    refine_stop_iter: int = 15000,
    refine_every: int = 100,
    reset_every: int = 3000,
    absgrad: bool = False,
) -> DefaultStrategy:
    return DefaultStrategy(
        key_for_gradient="gradient_2dgs",   # 2DGS uses gradient_2dgs, not means2d
        prune_opa=prune_opa,
        grow_grad2d=grow_grad2d,
        grow_scale3d=grow_scale3d,
        prune_scale3d=prune_scale3d,
        refine_start_iter=refine_start_iter,
        refine_stop_iter=refine_stop_iter,
        refine_every=refine_every,
        reset_every=reset_every,
        absgrad=absgrad,
        verbose=False,
    )
```
> **clone/split/prune 본체는 외부 `gsplat.strategy.DefaultStrategy` (이 레포 아님).** grow는 `grow_grad2d`(2D 위치 gradient 임계) 기반 — 무텍스처는 photometric gradient ≈ 0 이라 grow 트리거 안 됨. prune은 `prune_opa`(opacity), `prune_scale3d`(scale).

#### `src/stage2/densification.py:22-57` — 최적화 대상 파라미터 (sem_logits는 별도 Adam)
```python
def build_param_dict(model: GaussianModel2D) -> Dict[str, nn.Parameter]:
    params = {
        "means": model.means,
        "scales": model.log_scales,        # gsplat treats as raw; monotonic via exp at render
        "quats": model.quats,
        "opacities": model.opacities_raw,
        "sh0": model.sh0,
        "shN": model.shN,
    }
    if hasattr(model, "sem_logits"):
        params["sem_logits"] = model.sem_logits
    return params


def build_optimizers(
    model: GaussianModel2D,
    lr_means: float = 1.6e-4,
    lr_scales: float = 5e-3,
    lr_quats: float = 1e-3,
    lr_opacities: float = 5e-2,
    lr_sh0: float = 2.5e-3,
    lr_shN: float = 1.25e-4,
    lr_sem: float = 2.5e-3,
) -> Dict[str, torch.optim.Optimizer]:
    """One Adam per param (gsplat strategy assumption)."""
    opts = {
        "means": torch.optim.Adam([model.means], lr=lr_means),
        "scales": torch.optim.Adam([model.log_scales], lr=lr_scales),
        "quats": torch.optim.Adam([model.quats], lr=lr_quats),
        "opacities": torch.optim.Adam([model.opacities_raw], lr=lr_opacities),
        "sh0": torch.optim.Adam([model.sh0], lr=lr_sh0),
        "shN": torch.optim.Adam([model.shN], lr=lr_shN),
    }
    if hasattr(model, "sem_logits"):
        opts["sem_logits"] = torch.optim.Adam([model.sem_logits], lr=lr_sem)
    return opts
```

#### `src/stage2/train.py:289-300` — strategy 빌드 + 초기화 (config 임계 주입)
```python
    strategy = build_strategy(
        prune_opa=cfg.get("prune_opa", 0.005),
        grow_grad2d=cfg.get("grow_grad2d", 2e-4),
        grow_scale3d=cfg.get("grow_scale3d", 0.01),
        prune_scale3d=cfg.get("prune_scale3d", 0.1),
        refine_start_iter=cfg.get("refine_start_iter", 500),
        refine_stop_iter=cfg.get("refine_stop_iter", 15000),
        refine_every=cfg.get("refine_every", 100),
        reset_every=cfg.get("reset_every", 3000),
    )
    strategy.check_sanity(params, optimizers)
    strategy_state = strategy.initialize_state(scene_scale=scene_scale)
```

#### `src/stage2/train.py:399-400, 565-573` — densify 훅 (pre/post backward)
```python
        # track grad for densification (gsplat DefaultStrategy hook)
        strategy.step_pre_backward(params, optimizers, strategy_state, it, meta)
        ...
        # backward
        for opt in optimizers.values():
            opt.zero_grad(set_to_none=True)
        loss_total.backward()

        strategy.step_post_backward(params, optimizers, strategy_state, it, meta)

        # sync params dict -> model (gsplat strategy may replace nn.Parameters on grow/prune)
        _sync_params_to_model(params, model)
```

---

## 4) Loss 집계 (L_sem/L_mutual/L_structure 상대 가중)

#### `src/stage2/train.py:402-437` — base 데이터항 합산 (photo/depth/normal/nc/distort/sem)
```python
        # losses
        loss_photo = L.l_photo(rgb_pred, rgb_gt, lam=photo_lam)
        loss_total = w_photo * loss_photo

        if "depth" in batch:
            d_gt = batch["depth"].to(device)
            d_m = batch["depth_mask"].to(device)
            loss_depth = L.l_depth(depth_pred, d_gt, d_m)
            loss_total = loss_total + w_depth * loss_depth
        else:
            loss_depth = torch.tensor(0.0, device=device)

        if "normal" in batch:
            n_gt = batch["normal"].to(device)
            n_m = batch["normal_mask"].to(device)
            loss_n = L.l_normal(n_render, n_gt, w2c, n_m)
            loss_total = loss_total + w_normal * loss_n
        else:
            loss_n = torch.tensor(0.0, device=device)

        loss_nc = L.l_nc(n_render, n_surf, alpha=alpha.detach())
        loss_total = loss_total + w_nc * loss_nc

        loss_dist = distort.mean()
        loss_total = loss_total + w_distort * loss_dist

        # Semantic (only if GT provided and w_sem > 0)
        if "semantic" in batch and w_sem > 0 and hasattr(model, "sem_logits"):
            from .renderer import render_semantic
            sem_pred = render_semantic(model, w2c, K, W, H)
            sem_gt = batch["semantic"].to(device)
            loss_sem = L.l_sem(sem_pred, sem_gt, ignore_index=0)
            loss_total = loss_total + w_sem * loss_sem
        else:
            loss_sem = torch.tensor(0.0, device=device)
        loss_base_for_grad = loss_total
```

#### `src/stage2/train.py:506` — L_mutual 가산 (가중치 `w_mutual` × warmup ramp)
```python
            loss_total = loss_total + (w_mutual * mutual_weight_scale) * loss_mut_total
```

#### `src/stage2/train.py:533-547` — L_structure 계산 + 가산 (가중치 `w_structure`)
```python
                sd = l_structure(
                    normals=model.normals(),
                    centers=model.means,
                    group_ids=_grp["group_ids"],
                    rep_normals=_grp["rep_n"],
                    rep_d=_grp["rep_d"],
                    w_normal_align=w_structure_na,
                    w_coplanar=w_structure_cp,
                )
                loss_str_total = sd["total"]
                loss_str_na = sd["normal_align"]
                loss_str_cp = sd["coplanar"]
                n_in_group = sd["n_used"]
                n_groups = _grp["rep_n"].shape[0]
                loss_total = loss_total + w_structure * loss_str_total
```

#### `src/stage2/loss/structure.py:20-60` — l_structure (normal_align + coplanar; rep는 detach)
```python
def l_structure(
    normals: torch.Tensor,     # (N, 3) primitive normals, world (from quats)
    centers: torch.Tensor,     # (N, 3)
    group_ids: torch.Tensor,   # (N,) int64, -1 for ungrouped
    rep_normals: torch.Tensor, # (G, 3) detached
    rep_d: torch.Tensor,       # (G,)  detached
    w_normal_align: float = 1.0,
    w_coplanar: float = 1.0,
):
    zero = torch.zeros((), device=normals.device)
    if rep_normals.shape[0] == 0 or (group_ids >= 0).sum() == 0:
        return {"total": zero, "normal_align": zero, "coplanar": zero, "n_used": 0}

    mask = group_ids >= 0
    g = group_ids[mask]              # (M,) in [0..G-1]
    n_i = normals[mask]              # (M, 3)
    c_i = centers[mask]              # (M, 3)
    # Gather rep per primitive (detach to block gradient into rep)
    n_k = rep_normals[g].detach()    # (M, 3)
    d_k = rep_d[g].detach()          # (M,)

    cos = (n_i * n_k).sum(dim=-1)    # (M,)
    err_align = (1.0 - cos.abs()) ** 2
    loss_align = err_align.mean()

    sd = (n_k * c_i).sum(dim=-1) + d_k
    loss_coplanar = (sd ** 2).mean()

    total = w_normal_align * loss_align + w_coplanar * loss_coplanar
    return {"total": total, "normal_align": loss_align.detach(),
            "coplanar": loss_coplanar.detach(), "n_used": int(mask.sum().item())}
```

> **상대 가중 요약 (loss_total):** `w_photo·L_photo + w_depth·L_depth + w_normal·L_normal + w_nc·L_nc + w_distort·L_dist + w_sem·L_sem + (w_mutual·ramp)·L_mutual + w_structure·L_structure`.
> P2 make-or-break 값: w_photo 1.0 / w_nc 0.05 / w_sem 0.1 / w_mutual 0.1 / w_structure 0.1 (w_depth=w_normal=w_distort=0).

#### `src/stage2/train.py:306-328` — config 키 읽기 (기본값)
```python
    # ---------- loss weights ----------
    w_photo = cfg.get("w_photo", 1.0)
    w_depth = cfg.get("w_depth", 1.0)
    w_normal = cfg.get("w_normal", 0.05)
    w_nc = cfg.get("w_nc", 0.05)
    w_distort = cfg.get("w_distort", 100.0)   # 2DGS distortion reg
    w_sem = cfg.get("w_sem", 0.1)
    w_structure = cfg.get("w_structure", 0.0)
    w_structure_na = cfg.get("w_structure_na", 1.0)
    w_structure_cp = cfg.get("w_structure_cp", 1.0)
    structure_warmup = int(cfg.get("structure_warmup", 15000))
    structure_regroup_every = int(cfg.get("structure_regroup_every", 500))
    structure_voxel_size = float(cfg.get("structure_voxel_size", 0.05))
    structure_n_directions = int(cfg.get("structure_n_directions", 12))
    structure_min_group = int(cfg.get("structure_min_group", 5))
    # group state (updated every T iters after warmup)
    _grp = {"group_ids": None, "rep_n": None, "rep_d": None}
    w_mutual = cfg.get("w_mutual", 0.0)
    mutual_warmup = int(cfg.get("mutual_warmup", 10000))
    mutual_schedule = cfg.get("mutual_schedule", "constant")
    mutual_ramp_steps = int(cfg.get("mutual_ramp_steps", 0))
    mutual_tau = float(cfg.get("mutual_tau", 0.15))
    mutual_height_th = float(cfg.get("mutual_height_th", 0.15))
    mutual_mode = cfg.get("mutual_mode", "full")
```

---

## 5) 1~4를 토글하는 config 키 (`configs/tum_mob/*`)

#### `configs/mutual_loss/tum_mob/both.yaml:1-54` — 전부 ON (모든 토글 키가 보이는 대표 config)
```yaml
# P2 make-or-break ablation #5 BOTH = base + L_sem + L_mutual + L_structure (target config).
seed: 0
device: cuda
data_root: /workspace/JointBuildGS/results/tum_transfer/data
downscale: 1.0
sh_degree: 3
sh_up_every: 1000
w_photo: 1.0
w_depth: 0.0
w_normal: 0.0
w_nc: 0.05
w_distort: 0.0            # FALLBACK off (sweep collapses on TUM metric depth)
photo_lam: 0.2
lr_means: 1.6e-4
lr_scales: 5.0e-3
lr_quats: 1.0e-3
lr_opacities: 5.0e-2
lr_sh0: 2.5e-3
lr_shN: 1.25e-4
lr_sem: 2.5e-3
prune_opa: 0.005
grow_grad2d: 5.0e-4
grow_scale3d: 0.01
prune_scale3d: 0.1
refine_start_iter: 500
refine_stop_iter: 25000
refine_every: 100
reset_every: 3000
max_iter: 30000
eval_every: 2000
ckpt_every: 10000
out_dir: /workspace/JointBuildGS/results/tum_transfer/mob/both
load_semantic: true       # (1) 의미 라벨 로드 → L_sem 활성 전제
w_sem: 0.1                # (2) L_sem on
w_mutual: 0.1            # (1) L_mutual on
mutual_warmup: 10000
mutual_tau: 0.15
mutual_height_th: 0.15
mutual_mode: full
gravity_file: /workspace/JointBuildGS/configs/input_and_alignment/tum_gravity.json   # L_mutual 필수
w_structure: 0.1        # (4) L_structure on
w_structure_na: 1.0
w_structure_cp: 1.0
structure_warmup: 20000
structure_regroup_every: 500
structure_voxel_size: 2.0    # metric (G1 기본 0.05는 500m 장면 무력화)
structure_n_directions: 12
structure_min_group: 5
```

#### 5구성 ablation 토글 차이 (각 `configs/tum_mob/<arm>.yaml`)
```yaml
# vanilla.yaml   : load_semantic: false   (w_sem/w_mutual/w_structure 없음 → 전부 off)
# baseline.yaml  : load_semantic: true,  w_sem: 0.1
# mutual.yaml    : baseline + w_mutual: 0.1 (+ mutual_* + gravity_file)
# structure.yaml : baseline + w_structure: 0.1 (+ structure_* ; structure_voxel_size: 2.0)
# both.yaml      : baseline + w_mutual + w_structure (위 both.yaml)
```
> 토글 매핑: **(1) L_mutual** = `w_mutual`(+`gravity_file`,`mutual_*`); **(2) 의미/detach** = `load_semantic`+`w_sem` (detach는 코드 고정, config 토글 아님);
> **(3) densify/init** = `grow_grad2d`/`prune_opa`/`grow_scale3d`/`prune_scale3d`/`refine_*`/`reset_every` (init은 SfM 점 수로 고정, config 아님); **(4) L_structure** = `w_structure`(+`structure_*`).
