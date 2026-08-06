# P2 qualitative row 1 frozen-v6-v4 full-199 technical return

- Task: `P2-QUALITATIVE-ROW1-CURRENT-RAW-v6-RENDER199-v1`
- Date: 2026-08-06
- Decisions: `DEC-P1-016`, `DEC-P1-018`
- State: complete technical artifact
- Scientific verdict: `null`

## Frozen renderer binding

사람이 10동으로 검토·확정한 정본 entrypoint는
`scripts/p2/qualitative_row1_current_raw_v6/preview10_v4.py`다.

| Binding | Bytes | SHA-256 |
|---|---:|---|
| `preview10_v4.py` | 7,882 | `dc9c589b99744904662f9ade2d9851d56ca16de728ac272b9ac518a00e6cc92d` |
| `preview10_v4.json` | 4,106 | `9db3695825b5cb0f5bbd75b1725728c24279f3b24bd13598d054dee1a8f3702c` |
| `preview10.py` | 33,064 | `e8cf2a26b2c23cc9e7c9f4b25e15fdb81678d61a0dde0971d065974d167d287a` |
| `preview10_v2.py` | 5,561 | `62ff7e9e04230a8b970ae3e6b0247b21e420eba6076fbefd1312d9cbfc0f6fa2` |
| `preview10_v3.py` | 9,979 | `45cf50e6cea9e113ddc2b37ffdd5f86a7b32a8816b4843cead604fbc9319f098` |

`render199_v1.py`는 위 파일을 대체 구현하지 않고 import하여 호출한다. 변경된 것은
검토 모집단을 fixed 10에서 ordered 199로 확장한 것뿐이다. camera selection, pose
validation, representative roof component, crop, PNG render, terminal photo-only fallback은
동결 contract를 따른다.

## Full-199 result

- Building count: 199
- Panel slots: 796 (`199 × 4`)
- Selected/rendered projection panels: 749
- Explicit missing panels: 47
- Unique raw images used: 287
- TOP status: `NEAR_NADIR` 85, `BEST_AVAILABLE_NO_NEAR_NADIR` 77,
  `GEOMETRY_ONLY_NO_BUILDING_SPARSE_CONFIRMATION` 37
- Keypoints rendered: false
- Frozen preview-10 selection match: 10/10
- Frozen preview-10 final PNG byte match: 10/10

Artifact root:

`phase-payloads/p2/qualitative_row1_current_raw_v6/P2-QUALITATIVE-ROW1-CURRENT-RAW-v6-RENDER199-v1`

| Record | Bytes | SHA-256 |
|---|---:|---|
| `control/artifact_manifest_render199_v1.json` | 29,475 | `b8c868dd2a19f2a3dc2a6ceef4260e56167c3b896f4357b9f00e797e40e92431` |
| `preview/preview_manifest_render199_v1.json` | 985,021 | `7f0932562c48204dad2b453f3c03782f1f0b74e9f11c9e3ce9f97fc2f532d1ed` |
| `control/summary_render199_v1.json` | 1,509 | `4d3b077977a88adbd62cc3d03dd5591e43057b8cbe95288c97f550ae1b1968d9` |

Manifest의 206개 material record는 실행 후 bytes/SHA-256 재검증에서 모두 일치했다.

## Web consumption boundary

Web package task는
`P2-C1-C2-ORIGINAL-GLOBAL-v3-WEB-REVIEW199-EXACT-V6V4-ROWS-COMPACT-FIT-v11`이다. 199개 row
PNG를 full-199 artifact에서 byte-for-byte 복사한다. source JPEG와 projection 좌표를
브라우저에 전달해 SVG/canvas로 roofline을 다시 그리지 않는다.

- Copied row byte mismatches: 0/199
- Browser redraw: false
- Web manifest SHA-256:
  `dda2e211091e2b0a5bd11a73a5efa42724c0cc44ce04cab89c2bb639c3eefbaa`
- Display: 220 px desktop/170 px narrow-screen row. The image uses an explicit
  210 px/160 px box and `object-fit: contain`, preserving the exact PNG without
  overflow while reserving vertical space for the 3D view.
- Existing O/X localStorage key retained:
  `jointbuildgs-c1-c2-roofer-ox-v1`

과거 `qualitative_row1_current_raw_v7` JPEG/SVG 경로와
`web_review199_photo_v1`–`v4`는 실패 분석과 provenance를 위해 보존하지만 활성 실행 및
서빙 경로에서는 제외한다.
