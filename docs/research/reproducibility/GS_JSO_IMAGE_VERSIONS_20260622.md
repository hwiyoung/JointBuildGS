# GS-JSO 루트 이미지 버전 기록 (§4 규칙 9)

> GS-JSO 코어(Stage 2 학습·P2 보조 도구) Docker 이미지의 태그·ID·base·빌드일 기록.
> P0 audit 이미지(colmap/openmvs/roofer/tools/city3d)는 `phases/p0-audit/env/versions.md` 참조.
> 갱신 2026-06-22 (commit fcb79fe 시점). 로컬 빌드 이미지 → 레지스트리 digest 없음(`<none>`),
> 대신 로컬 이미지 config **ID(sha256)** 를 고정값으로 기록한다.

## GS-JSO 코어 이미지

| 용도 | 태그 | 이미지 ID (sha256) | base | 빌드일 | 크기 |
|---|---|---|---|---|---|
| Stage 2 학습 / GS-JSO dev (gsplat·2DGS·open3d) | `jointbuildgs:dev` | `926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396` | `nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04` | 2026-04-21 | 21.4 GB |
| ACMP/ACMMP plane-prior PatchMatch MVS (P2 무텍스처 신호진단·P0c) | `jointbuildgs-acmp:t0` | `06f84e32230d6cf3324502af872139b574e0f51a888d3b816793d46dafd54c0e` | `nvidia/cuda:12.1.1-devel-ubuntu22.04` | 2026-06-22 | 8 GB |

- Dockerfile 위치: GS-JSO dev = 루트 `Dockerfile` + `docker-compose.yml`; ACMP = `phases/p2-gsjso/env/Dockerfile.acmp`.
- `stage2`로 분리된 별도 이미지는 없음 — Stage 2 학습은 `jointbuildgs:dev`로 실행한다.
- 레지스트리 미푸시(로컬 빌드)이므로 `--digests`는 `<none>`. 재현 시 위 ID로 동일 이미지 확인.

## 참조 (P0 audit 이미지)

`phases/p0-audit/env/versions.md` — `colmap/colmap`(digest 고정), `jointbuildgs-p0-openmvs:t0`,
`3dgi/roofer`(digest 고정), `jointbuildgs-p0-tools:t0`, `jointbuildgs-p0-city3d:w2`.
P0c(완전성/조립 진단)는 위 P0 tools·roofer + 본 문서 ACMP 이미지를 함께 사용.
