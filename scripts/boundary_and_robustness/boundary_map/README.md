# Boundary-map execution drivers

이 디렉터리는 P2 `boundary_map` v1-v4.1의 family-specific 재현 driver를 소유한다.

- Python producer/worker: `overnight_boundary_map.py`, `boundary_map_v2.py`, `boundary_map_v3.py`, `anchor_census.py`와 대응 dense/supplement 파일
- Shell orchestration: `run_boundary_map_v3_20260719.sh`, `run_anchor_census_20260720.sh`, `run_anchor_census_supplement_20260720.sh`
- 공용 의존성: `scripts/evidence_and_attributes/`, `src/geospatial/`, `scripts/e5_c001/`의 재사용 구현
- 실행 영수증: `phases/p2-gsjso/runs/<run_id>/`
- 공개 문서: `docs/experiments/input-and-alignment/boundary_map/`

이 파일들은 과거 run receipt를 대체하지 않는다. 과거 manifest의 이전 script 경로와 SHA-256은 당시 provenance로 유지하며, 현재 실행은 이 디렉터리의 경로를 사용한다.

Driver 일부는 commit/push 단계를 포함한다. 검증 시에는 실험 driver를 실행하지 말고 Docker 컨테이너에서 Python `compile()`과 `bash -n`을 사용한다.
