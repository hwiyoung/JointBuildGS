# C1/C2 oracle 및 C3 comparison Local Technical Closure v1

- task_id: `P2-C1-C2-ORACLE-C3-EXTRACT-RECOVERY-v13`
- execution_record_id: `P2-LOCAL-C1-C2-ORACLE-C3-EXTRACT-RECOVERY-v13`
- source_commit: `3c7bbfdfdacfdc606716b3848e390a9d7e264458`
- status: `LOCAL_TECHNICAL_CLOSED`
- execution_host_role: `experiment_host`
- write_ownership_transfer_performed: `false`
- two_host_receipts_created: `false`
- scientific_verdict: `null`

사용자의 직접 지시에 따른 single Experiment Host 실행이며 Work→Experiment write ownership
transfer는 없었다. 따라서 실제 역할을 허위로 주장하는 `000-offered/100-accepted/200-verified/
300-closed` receipt를 만들지 않는다. 이 문서는 해당 receipt를 대체하지 않는 로컬 기술 종료
기록이다.

종료 검증:

- clean execution `HEAD == origin/main == 3c7bbfdfdacfdc606716b3848e390a9d7e264458`
- pinned project image `sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`
- final artifact manifest: 208 records, SHA-256 failures 0
- C1/C2: 3 sheets, 72 panels
- C3: 3 combined sheets, 144 panels, each 4140×8740
- C3 Roofer: 4 completed, 2 explicit pre-Roofer insufficient-evidence records
- recovery-v13 Roofer/G2/GS training/depth extraction/mesh postprocess/metric/C4-C5:
  `0/0/0/0/0/0/0`
- lineage completed Roofer: 8
- original-resolution C3 visual review: 3/3 sheets
- official G3/G4/PASS and scientific verdict: `null`

Artifact resolver는 `artifacts/manifests/p2_c1_c2_oracle_c3_extract_recovery_v13.json`이다.
