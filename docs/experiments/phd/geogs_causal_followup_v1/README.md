# P1·P2 변화와 P2 골의 원인 검토

2026-09-10 · `task_id: PHD-GEOGS-CAUSAL-FOLLOWUP-v1` · `scientific_verdict: null`

기존 학습·평가 산출물을 읽어 P1의 불완전한 구조 수정, P2의 큰 구조 수정 성공, P2 골의 국소 잔여를 구분했다. DA3 단독 원인과 업데이트 mask 필요성을 미리 전제하지 않는다.

- [통합 검토와 다음 세션 인계](CAUSAL_REVIEW_ko_v1.md)
- [실제 입력·저장 깊이 감사](DA3_INPUT_AUDIT_ko_v1.md)
- [GeoGS 보호 제어와 관련 업데이트 연구](MASK_DESIGN_AUDIT_ko_v1.md)
- [P2 골 그림](figures/valley_panels.png), [골 확대](figures/valley_zooms.png), [P1·P2 큰 변화 비교](figures/change_contrast.png)
- [제한과 실행 예외](ISSUES_ko_v1.md)

깊이 분석의 최종 근거는 `analysis/da3_convention_corrected_v2/`다. 최초 `analysis/da3_evidence.json`과 CSV는 수정 계보를 위해 보존했으며 world endpoint 해석에 사용하지 않는다. camera-Z 조회값은 동일하다.

재현 코드는 [scripts](../../../../scripts/phd/geogs_causal_followup_v1/), 입력·선택 규약은 [configs](../../../../configs/phd/geogs_causal_followup_v1/)에 분리했다. 각 receipt에 원자료 SHA와 실행 환경을 기록했다. Docker에서 기존 표본을 집계·도식화하고 저장 배열을 조회했다. 새 학습·장면 렌더·DA3 추론·메쉬 추출·정합은 0회이며, 기술 점검 PASS는 과학적 판정이 아니다.
