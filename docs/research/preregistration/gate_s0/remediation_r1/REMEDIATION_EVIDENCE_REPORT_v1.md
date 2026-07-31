# Gate S0 Remediation R1 Evidence Report v1

- handoff_id: `P2-W2C-GATE-S0-REMEDIATION-R1-v1`
- task_id: `P2-GATE-S0-REMEDIATION-R1-v1`
- proposed_status: `BLOCKED_FOR_GATE_S0_REMEDIATION_REVIEW`
- scientific_verdict: null
- evidence_time: `2026-07-31T22:10:00+09:00`

## 결론

R1–R6의 제한된 기술 증거 수집은 완료했으며, 제안 상태는
`BLOCKED_FOR_GATE_S0_REMEDIATION_REVIEW`다. 가장 중요한 개선은 verified
`opf.zip` 안에서 C3–C5가 공통으로 사용할 수 있는 sparse SfM 원본을 찾고 archive/member
단위로 결속한 것이다. 이 원본은 `4,131,648` sparse points와 `937`개의 unique camera
UID를 포함하며, UID 집합은 OPF calibrated camera ID 집합과 정확히 일치한다.

그러나 independent LoD1 bytes는 여전히 `MISSING`이고, 좌표·수직 datum·registration,
건물별 current-image/condition coverage, class-2/6 derivatives, 공통 `R_derived`, gravity,
Roofer/CityGML/val3dity/G0–G4 toolchain이 실행 가능하게 동결되지 않았다. 따라서
`U_target`, `E_paired`, split과 cost ceiling을 동결하거나 P2 performance를 시작할 수 없다.
이 상태는 사람의 Gate 또는 과학적 판정이 아니다.

## R1 — independent LoD1

- 고정 local artifact search는 기존과 동일한 13개 regular files를 재현했고, inventory
  SHA-256은 `fdf6e30400394cbb8b35e78609b407dc8a07ad1f95d71d8cbfc00d617c78d6f5`다.
- Git-owned manifest tree에는 과거 LoD1 search JSON만 있고, 실제 LoD1 byte record는 없다.
- TUM2TWIN building catalog는 LoD3, textured LoD2와 LoD2를 열거하지만 LoD1 payload를
  제공하지 않는다.
- official Bavarian LoD1은 후보 자체는 존재하지만 주문 시 updated LoD2 stock에서 파생되고,
  같은 ALKIS footprint와 최고 용마루 높이의 flat roof를 사용한다. 따라서 scored LoD2와
  독립적인 C5 prior로 사용할 수 없고, 이 task는 license를 수락하거나 bytes를 받지 않았다.
- 결론: discovery metadata는 `PARTIAL`, admissible independent bytes는 `MISSING`이다.
  이는 고정 범위 결과이며 provider/world-wide absence 주장이 아니다.

Evidence: [TUM2TWIN building catalog](https://tum2t.win/datasets/cm-buildings),
[LDBV LoD1 documentation](https://www.ldbv.bayern.de/file/pdf/4211/Faltblatt_LoD1.pdf).

## R2 — sparse SfM initialization

Verified archive:

- URI: `artifact://JointBuildGS/phase-payloads/p0-audit/data/raw/uav/opf.zip`
- bytes: `1,936,493,976`
- SHA-256: `ae83a054cf2f338874ff7bac7b3e17895b8e4405d429674790da3801a0352daa`

`opf/project.opf`의 calibration item이 `opf/sparse/pcl.gltf`와 12개 `.glbin`을 직접
resource로 가리킨다. 13개 sparse members의 decompressed bytes 합은 `469,147,486`이고,
각 member의 bytes/SHA-256은 `sfm_sparse_initialization_v1.json`에 기록했다. glTF producer는
`Pix4D PCL IO 2.1.2`, OPF asset version은 `1.0`, project version은 `1.1-draft1`이다.
scene frame은 `EPSG:32632`, base-to-canonical scale `[1,1,1]`, shift
`[-690953,-5336071,-604]`, `swap_xy=false`이며 glTF node matrix도 보존했다. vertical datum은
OPF에서 확인되지 않는다.

따라서 exact sparse source identity와 camera binding은 `READY`다. 다만 현재 main image에서
pinned `pyopf/opf2colmap` conversion과 undistortion replay가 실행 가능하지 않고 canonical
converted derivative/hash도 없으므로 C3–C5 integration readiness는 `PARTIAL`이다. C2 dense
MVS를 대신 사용하지 않았다. 제공자 절차도 OPF가 camera calibration과 sparse reconstruction을
포함하고 `opf2colmap`을 통해 cameras/images/points3D를 만든다고 설명한다.
[TUM2TWIN OPF tutorial](https://tum2t.win/tutorials/im-gaussiannerf)

## R3 — coordinate, datum, registration and reference

| Scope | Evidence state | Remaining gate |
|---|---|---|
| C1 current UAS LiDAR | horizontal `EPSG:32632` exact; current nadir primary candidate | vertical datum, 25832/DHHN2016 transform, residual and building coverage |
| C2 dense MVS | `EPSG:32632 + EGM96/EPSG:5773`, Pix4Dmatic 1.58.1 | validated EGM96→DHHN2016 path, residual, class derivative |
| C3–C5 OPF sparse | EPSG:32632/local shift/node transform exact | vertical datum and converter replay |
| C4 existing ALS | provider `EPSG:25832/DHHN2016`; exact four tiles | file CRS VLR absent, acquisition epoch/residual/confidence/coverage |
| structure reference | exact CityGML 1.0 bytes, `ETRS89_UTM32*DE_DHHN2016_NH` | snapshot/version and per-building production-source lineage |

Current UAS LiDAR를 geometry reference로 쓰면 C1은 `SELF_REFERENCE`다. 같은 2024 campaign의
C2/C3와 current-image를 공유하는 C4는 geometry reference에 대해 `PARTIALLY_SHARED`다.
Official LoD2 structure reference는 provider 설명상 ALKIS footprint와 당시 ALS/measurement/
image-DSM으로 생산되지만 exact local tile/version/epoch와 건물별 source는 미결속이다. 따라서
C2/C3 overlap은 `UNKNOWN`, C4 overlap은 `UNKNOWN_OR_PARTIALLY_SHARED`다. LDBV LoD1 후보는
`PROHIBITED_DERIVATIVE_CANDIDATE`다. 공식 LoD2 문서는 ALKIS footprint와 ALS·3D survey·image
DSM을 생산 기초로 설명하고, horizontal accuracy는 ALKIS에 따르며 일반적 height accuracy는
약 1 m라고 명시한다.
[LDBV LoD2 documentation](https://www.ldbv.bayern.de/produkte/liegenschaftsinformationen/gebaeudemodell.html)

## R4 — condition provenance

- C1과 C4의 asset/source 구분은 입증됐다. C1은 2024 UAS LiDAR이고 C4는 Bavarian regional
  ALS four-tile prior다. Local manual UAS candidate는 legacy Zenodo v1.0 bytes이며 current
  v1.2 manual과 다르므로 latest로 부르지 않는다. `NADIR_ONLY` primary proposal은 유지한다.
- C2 exact-937 common base는 단순 미입증이 아니라 source-confirmed mismatch다. 제공자 문서는
  published photogrammetric 3D가 1,104 acquired images에서 생성됐고 privacy filtering 뒤 962
  images가 공개됐다고 기록한다. 공개 OPF calibrated set은 937이다. C2는
  `sensor-processing-bundle baseline`으로만 유지하며 C2-vs-C3를 method-only contrast로
  해석하지 않는다.
- C4의 C1 대비 별도 bytes/provider/regime는 `READY`지만, exact ALS acquisition epoch,
  registration, per-building overlap, confidence metadata와 future prior interface는 미동결이다.
- C3–C5는 frozen `962/937/25` image/camera ledger와 R2 sparse source를 공유한다.

Evidence: [TUM2TWIN UAS LiDAR](https://tum2t.win/datasets/pc-uas),
[UAS photogrammetry](https://tum2t.win/datasets/pc-uasp),
[real ALS](https://tum2t.win/datasets/pc-als),
[official v1.2 metadata](https://zenodo.org/api/records/15282970/files/TUM_Downtown_ULS_Photogrammetry_20241217_docu.pdf/content).

## R5 — Stage 3/common toolchain

Current image digest is
`sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`.
`cjio 0.10.1` and the repository CityJSON builder import are available, so CityJSON is `PARTIAL`.
Roofer, standalone cjval, val3dity, ogr2ogr and PDAL executables are absent. P0 history pins Roofer
1.0.0, val3dity 2.6.0 and citygml-tools 2.5.0, but those images are not locally available and no
pull/build was authorized. The existing `citygml_export.py` produces CityJSON, not a trusted
CityGML serializer.

Canonical terrain-MVS-normal gravity, campaign-wide non-GT `R_derived`, common C1–C5 writer and
G0–G4/PASS_usable field writer are missing. Historical/GT-dependent Stage 3 scripts were not
promoted as current execution authority. No adapter or numerical threshold was selected.

## R6 — outcome-free stable-ID funnel

Streaming XML inspection used only score-reference `gml:id`, provider external object ID and
`GroundSurface` XY. `RoofSurface`, roof type, semantic labels, Z-based scores and method results
were not used. The two exact reference tiles contain 12,049 unique buildings; candidate AOI
intersection yields `35 + 164 = 199` unique rows.

- sorted `gml:id\n` SHA-256:
  `047717a5d678aeed540602a2d4fc9a57a076e2ac9205b22a4de75315c1622fe5`
- sorted `gml_id|provider_external_id\n` SHA-256:
  `330598a07840972e1371aa77b21ee42f19065c8c401fa8f1b78b3bb82f6f44da`
- provisional, unregistered numeric bbox full-containment: C1 `187/199`, C2 `197/199`,
  C4 provider tile union `199/199`

이 bbox 수치는 서로 다른/미검증 frame의 diagnostic일 뿐 eligibility가 아니다. OPF에 건물별
visibility/coverage member가 없으므로 937 global camera ledger를 building coverage로 승격하지
않았다. 199개 각 row의 C1–C4 eligibility는 `UNKNOWN`, C5 availability/eligibility는
`MISSING/false`, `U_target`과 `E_paired`는 `UNKNOWN`, `held_out_accessed=false`다.

## Resolved and remaining blockers

Resolved or narrowed:

1. `S0-R13` sparse source identity/camera binding: `READY`; integration remains `PARTIAL`.
2. C2 exact-937 question: resolved as `MISMATCH`, with sensor-processing-bundle interpretation.
3. C1/C4 asset identity separation: distinct sensor/source/bytes roles established.
4. Stable reference candidate IDs: 199 exact IDs and provider IDs published as diagnostic.

Still blocking Gate S0/P2 entry:

1. admissible independent C5 LoD1 bytes;
2. C1 vertical datum, class-2/6 derivative, registration and building coverage;
3. C2 adapter/transform/class derivative and non-method-only interpretation guard;
4. C4 acquisition/version binding, registration, overlap, confidence semantics and interface;
5. independent geometry/reference uncertainty and structure-reference production lineage;
6. building-level current-image join, hence `U_target`/`E_paired`;
7. canonical gravity, `R_derived`, Roofer/CityGML/validation/G0–G4 toolchain;
8. cost ceilings and split, which remain unsafe before the above readiness fields are complete.

## Next safe step

Work Host should cross-review this immutable package and prepare a new, separately approved
data/toolchain remediation packet. That packet may acquire and hash-bind an independent LoD1,
freeze datum/registration/classification/coverage lineage, and make the pinned common toolchain
callable. Only after those fields are complete may a bounded non-held-out cost calibration be
authorized. Performance baseline, GS training, production derivative, held-out, Fusion W1 and
`R_ext` remain prohibited.

No joint-prior synergy claim is made. P2/P3 continue to use the same future
development+validation building pool, and P4 first opens the isolated held-out buildings for the
frozen C1–C5 matrix.
