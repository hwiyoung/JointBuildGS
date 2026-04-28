# Codex Prompt — Figure 1 (L_mutual visual evidence)

## Context (research)

박사 연구 "도시 규모 건물의 구조적 3D 복원 — 기하-의미론 공동 최적화" 의 Phase 2.
2DGS primitive (Gaussian disk) 위에 도메인 규칙 손실 `L_mutual` 을 추가하면 벽 primitive 의 normal 이 수평으로(=벽이 수직으로), 지붕 primitive 의 normal 이 수직으로(=지붕이 수평으로) 정렬돼야 함.

4-condition ablation 결과는 정량적으로 명확:

| 조건       | Wall vert-frac | Wall mean tilt | Roof flat-frac | Roof mean tilt |
|------------|----------------|----------------|----------------|----------------|
| baseline   | 28%            | 13.2°          | 68%            | 15.3°          |
| mutual     | 80%            | 5.1°           | 92%            | 7.8°           |
| structure  | 30%            | 12.9°          | 70%            | 14.6°          |
| both       | 82%            | 5.0°           | 93%            | 7.5°           |

(Wall tilt = `arcsin(|n.y|)`, Roof tilt = `arccos(|n.y|)`, Y-down scene.)

## Goal

이 정량 결과를 한눈에 보이는 **figure** 를 만든다. 4-panel side-by-side (4 conditions). 3D 가 우선 (논문 주제가 3D 복원), 잘 안되면 2D fallback.

## What's been tried (기준점 + 실패 사례)

기준점: `scripts/phase2_synthesis/diag_mech1_on_building.py` 가 가장 사용자 의도에 가까웠음.
- 가장 큰 GT wall face 하나를 2D 평면(u,v)으로 펼치고
- 그 면 근처의 모든 wall primitive 를 작은 회전 사각형으로 (회전각 = tilt)
- 4 condition side-by-side
- 단점: 한 벽만 보여줌 + roof 안 보여줌 + "옆에서 본 형태" 인지 직관적이지 않음

실패한 7가지 시도 (`scripts/phase2_synthesis/diag_mech1_*.py`):
1. `diag_step2_mechanism_viz.py` — 5-panel (cluster, plane, polytope) — 의도 혼탁
2. `diag_mech1_wall_disks.py` v1 — 전체 disk 렌더 — 위치 어긋남, building 기울어짐
3. `diag_mech1_wall_disks_v2.py` — top-down + side projection — 위치 정렬 안됨
4. `diag_mech1_closeup.py` — 한 벽 ~35 disk 3D — 컨텍스트 부족
5. `diag_mech1_final.py` — histogram + 30 random rotated rect — building 컨텍스트 없음
6. `diag_mech1_3d_normals.py` — 3D 건물 + normal 을 line segment 로 — 막대로 보여서 어색
7. `diag_mech1_3d_disks.py` — 3D 건물 + face-proximity 필터 + disk — disk 가 산만하게 흩뿌려진 느낌

근본 한계: 5° vs 13° tilt 차이는 building scale 의 100+ disk 를 모아 놓으면 시각적으로 거의 안 보임. 평균돼서 사라짐.

## Data location

- Repo root: `/workspace/JointBuildGS` (Docker 안). 호스트는 `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS`.
- Checkpoints (4 condition × `final.pt`):
  - `results/phase2_ablation_citygml/baseline/ckpt/final.pt`
  - `results/phase2_ablation_citygml/mutual/ckpt/final.pt`
  - `results/phase2_ablation_citygml/structure/ckpt/final.pt`
  - `results/phase2_ablation_citygml/both/ckpt/final.pt`
- GT scene: `results/phase2_synthesis/scene.obj` — `parse_scene_obj` (`scripts/phase2_synthesis/obj_gt.py`) 로 로드. Returns `{"buildings": [{"building_id", "type", "faces": [{"vertices": (N,3), "normal": (3,), "semantic_class", "area"}, ...]}]}`. Bid 2 = "Flat" 단순 건물 (추천).

## Primitive 데이터 형식

`final.pt` 의 `state_dict`:
- `means` (N,3) — primitive center, 좌표계 = scene Y-down (Y=0 ground, Y<0 위).
- `quats` (N,4) — w,x,y,z; rotation R = quat_to_rotation(quats); columns: `tu = R[:,:,0]`, `tv = R[:,:,1]`, `n = R[:,:,2]`.
- `log_scales` (N,2) — `su = exp(log_scales[:,0])`, `sv = exp(log_scales[:,1])`. Disk 크기 (m). Clip 1.0~2.0 권장.
- `sem_logits` (N,4) — softmax → label (0=BG, 1=Roof, 2=Wall, 3=Terrain).
- `opacities_raw` (N,) — sigmoid → opacity. ≥ 0.05 인 primitive 만 사용.

기존 helper: `scripts/phase2_synthesis/diag_mech1_3d_disks.py` 에 `quat_to_rotation`, `load_primitives`, `to_display` (Y-down→Z-up: `X=X, Y=Z, Z=-Y`), `make_disk_polygon_disp` 다 있음. 그대로 import 해서 써도 되고 새로 짜도 됨.

## 사용자 피드백 (반복된 패턴)

- "건물이 기울어져 있다" → `to_display` 좌표 변환 누락. **모든 3D 좌표를 한 번씩만** 변환해야 함 (정합 필수).
- "차이가 안 보인다" → 100+ disk 를 작게 그리면 5° tilt 가 평균돼 사라짐. 적은 수 (≤ 60) 를 크게 보여주는 게 효과적.
- "프리미티브 자체를 보고 싶다" → 화살표/막대 X. 실제 disk 형태 (ellipse) 로.
- "실제 건물 위에서 보고 싶다" → schematic, 추상적 sample-only 거부. GT 건물 컨텍스트 필요.
- "정합이 안 맞는다" → primitive center 와 GT building wireframe 이 같은 좌표계 (display) 에서 그려져야 함. 디버깅 시 `print(centers.min/max)` vs `gt_v.min/max` 확인 필수.

## What might work (시도해볼 만한 방향)

(자유롭게 새로 시도하되 아래 중 하나라도 만족하면 좋음)

A. **3D + 화면 quality**: 3D 건물 위에 disk 를 그리되 disk 를 "key 부위"에만 (예: 한 면당 5~10 개) 큼지막하게. View angle: 건물 옆모서리에서 보면 일부 벽은 face-on, 일부는 edge-on 되어 비교 자연스러움.

B. **2D unfolded box ("blueprint" view)**: 건물의 6 면을 종이접기 펼치듯 2D 로 펴서 한 캔버스에 — top (roof), front/back/left/right (walls). 각 면에 그 면의 primitive 를 작은 disk 로. Ascii sketch:
```
            +-----+
            | top |  ← roof primitives
   +------+------+------+------+
   | left | front| right| back |  ← wall primitives, 각 wall face 별로
   +------+------+------+------+
```

C. **Cross-section (top-down slice)**: 건물을 mid-height 에서 수평 절단. 그 slice 와 교차하는 wall primitive 들을 top-down 평면에 ellipse 로. **수직 벽 → 매우 얇은 line, 기울어진 벽 → 두꺼운 ellipse**. 시각적 차이가 가장 극적.

D. **Splat-rendered normal map** (이미 있을 수 있음): 4 condition 의 evaluation rendering 에서 normal map 만 추출해 side-by-side. Wall 영역의 색이 condition 별로 달라야 함.

E. **Hybrid 3D + inset**: 3D 건물 small thumbnail + 큰 panel 은 한 wall close-up. context + detail 동시에.

## 명시적 요구사항

1. **4-panel side-by-side** (baseline / mutual / structure / both). 같은 view, 같은 scale, 같은 색 코딩.
2. **Color code (반드시 일치)**:
   - Wall vertical (<5° tilt): GREEN `#22a55a`
   - Wall tilted: RED `#d63d3d`
   - Roof flat (<18° tilt): BLUE `#3182ce`
   - Roof tilted: ORANGE `#e67700`
3. **Roof + Wall 둘 다** 보여주기. (이전 시도들은 wall 만)
4. **Self-explanatory title** — 그림만 보고 의도 파악 가능. Sub-title 에 % 수치 (Wall vert%, Roof flat%, mean tilt) 표기.
5. **Building context** — abstract sample-only 안 됨. GT 건물 윤곽 (wireframe / outline) 이 보여야.
6. **출력**: `results/phase2_ablation_citygml/figures/fig_mech1_<approach_name>_bid002.png`, `dpi >= 130`, `figsize` 충분히 크게.
7. **CLI**: `python scripts/phase2_synthesis/<your_script>.py --bid 2`. 다른 building (bid=22 IndustrialBuilding, bid=6, bid=21) 도 돌아가야 함.

## 평가 기준 (figure 가 좋은가)

- Baseline panel 과 Mutual panel 을 나란히 놓고 봤을 때 **3 초 안에** "Mutual 이 더 정렬돼 있다" 가 보이는가?
- Wall 28%→80% 차이가 정성적으로 visible 한가? (수치만 의지하지 않고)
- Roof 68%→92% 차이도 같이 보이는가?
- 4 condition 이 동일한 view 로 fair comparison 인가?

## 기술 메모

- Y-down scene: scene Y axis 가 위(아래?) — 정확히는 "Y=0 ground, Y<0 above ground" (gravity = +Y).  Wall normal 수평 = `n.y ≈ 0`. Roof normal 수직 = `|n.y| ≈ 1`.
- `to_display(pts)`: `out[...,0]=pts[...,0]; out[...,1]=pts[...,2]; out[...,2]=-pts[...,1]` — display 는 Z-up.
- 모든 3D 양 (centers, tu, tv, vertices) 을 같은 변환을 거쳐야 정합. **딱 한 번씩만** 변환.
- matplotlib 3D 의 `set_box_aspect((1,1,1))` + 동일 길이 xyz lim 으로 isotropic.
- Tilt 계산: `wall_tilt = degrees(arcsin(clip(abs(n[:,1]), 0, 1)))`, `roof_tilt = degrees(arccos(clip(abs(n[:,1]), 0, 1)))`.
- Filter: `opacity ≥ 0.05` AND `centers in bbox(GT_bld) ± 1m` AND (선택) `near_face` (perp < 0.8m, lateral < face_extent + 0.8m).
- Disk polygon: `theta in [0, 2π]`, `pts[i] = c + su*cos(theta_i)*tu + sv*sin(theta_i)*tv`. n_pts=18 충분.

## Deliverable

새 script `scripts/phase2_synthesis/diag_mech1_<approach>.py` 1~2 개. 각각 다른 시각화 패러다임. 결과 PNG 를 출력. Brief commit message 도 함께.

가능하면 **B (unfolded blueprint)** 또는 **C (cross-section)** 를 우선 시도해줘 — 둘 다 위에서 안 시도된 방향이고 정성적 차이가 크게 드러날 가능성이 높음. 3D 우선이니 A 도 좋음. D 는 supplementary.
