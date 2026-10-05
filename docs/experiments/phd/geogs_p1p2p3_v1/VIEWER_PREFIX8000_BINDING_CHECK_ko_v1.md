# ④ 원설정 최종과⑤ SfM·Anchor 생략의 표시 연결 재확인

2026-09-10 · 실제 파일/브라우저 읽기 감사 · `scientific_verdict: null`

사용자가 현재8k viewer에서④ 원설정과⑤ SfM·Anchor 생략이 비슷해 보인다며 연결 정확성을 질문했다. 같은 manifest를 새 브라우저에서 열고 세 지역의 raw/post6조합을 확인했다. **서로 다른 실제 결과를 표시한다. P1/P3의 일부 기하 수치가 가까운 것은 실제 저장된 결과다.** 앞선 답변의③ Anchor8k 대비 표를④ 원설정 최종30k 대비 표로 읽으면 차이를 과장하게 되므로 비교 기준을 구분한다.

## 실제 연결과 표시

Manifest는 `evaluation/no_anchor_sfm_prefix8000_v1/profiles/viewer_v1/manifest.json`, SHA`67596c8b240b079a92c78605a5365cead5ee7473928b5ab6058d5b636c7a85e0`다. 최초 지역은P1이고 세 지역 모두 기본 변경 조건은 `SFM_noanchor_D005_Pnative_PREFIX8000`이다. 사용자 앱의 전달 포트2611 대신 원 서비스8902에서 같은 manifest를 검증했으며 사용자 탭의 현재 선택·캐시를 직접 읽었다고 주장하지 않는다.

④는 `D005_Pnative.mesh_512.{raw,post}`의 기존30k,⑤는 `SFM_noanchor_D005_Pnative_PREFIX8000.mesh_512.{raw,post}`의 역사적8k다. 세 지역×raw/post6쌍의 표시 JSON, 메시 메타데이터, 정점/삼각형 binary, 원 TSDF PLY가 각각 다르고 선언 SHA와 일치한다. 지표 JSON도 각자의 원 PLY SHA와 iteration을 가리킨다. 원자료·manifest·viewer source·서비스는 변경하지 않았다.

`prefix8000_v1/browser_qa.sh viewer_v1 binding_recheck_20260910_v1 8902`를 Docker에서 실행했다. 실제 로드된 metadata가 선언과 같고, binary SHA/bytes 검증과 WebGL의 해당 삼각형 draw를 확인했다. 결과는 `PASS_PREFIX8000_BROWSER_QA`,208검사·9스크린샷이다. receipt는 `evaluation/no_anchor_sfm_prefix8000_v1/qa/binding_recheck_20260910_v1/receipt.json`, SHA`b1f12fb847fbe8a2ee773ce639f133dd99fb3827325caca5bf0ac38ae07d3821`이다. code/app snapshot·명령·image ID·로그도 같은 경로에 있다. root는 P1 raw 실제 화면을 열어 큰 형상이 유사하지만 다른 연결임을 함께 확인했다.

| 지역 | raw 실제 표시 삼각형:④ →⑤ | 전체 평가 표본:④ →⑤ | 점 표시 표본:④ →⑤ |
|---|---:|---:|---:|
| P1 |74,254 →85,003 |261,480 →292,193 |169,009 →187,929 |
| P2 |65,559 →65,005 |543,784 →534,044 |200,000 →200,000 |
| P3 |271,093 →267,976 |807,583 →794,752 |200,000 →200,000 |

P2/P3의20만 표본은 표시 상한을 동일하게 적용한 값이며 같은 원자료나 같은 최종 표면을 뜻하지 않는다. 현재 URL의 height는 공통 Z 범위를 색으로 바꾼 표시이므로 비슷한 높이는 같은 색이다. 사진 렌더 품질을 보여주는 색상은 아니다.

## 기존 수치의 올바른 비교 기준

공식 TSDF512 raw, `sample0.1_reference0.1`, F1@0.5m의 기존 저장값이다. 새 scoring은 수행하지 않았다.

| 지역 |③ Anchor8k |④ 원설정 최종30k |⑤ SfM·Anchor 생략8k |
|---|---:|---:|---:|
| P1 |0.640809 |0.499435 |0.483900 |
| P2 |0.465087 |0.534577 |0.377779 |
| P3 |0.701764 |0.588058 |0.554260 |

P1/P3에서는⑤가③보다④에 가깝다. P2는④와도 차이가 있다. raw/post 구분과 임계값을 유지해야 하며, 표면 개수·면적이 비슷해도 표면 위치의 참조 근접도는 달라질 수 있다. 사진 ROI PSNR의④→⑤도P1 19.1807→17.1127, P2 16.4402→14.8572, P3 21.2664→19.1870dB로 동일하지 않다. 수치 출처는 지역별 `summary/Px/R8000/{geometry_comparison.csv,render_comparison.csv}`다.

이 화면은8k와30k를 함께 보여주는 진단이다.④와⑤의 근접한 F1만으로 같은 형상·동등한 전체 품질·Anchor 불필요를 확정하지 않는다. 반대로③ 대비 감소를④ 대비 동일한 규모의 악화로 설명해서도 안 된다. 초기화·단계·일정·보호 집합이 함께 다르며, SfM 경로에도 ALS depth0.005와 native 보호가 남는다. 전체22k/30k의 자원 실패와 이8k의 실제 제공을 구분한다.

[실제 비교 뷰어](http://127.0.0.1:8902/app/index.html?manifest=/task/evaluation/no_anchor_sfm_prefix8000_v1/profiles/viewer_v1/manifest.json&color=height) · [실험 통합 분석](SFM_NO_ANCHOR_RESULTS_ko_v1.md)
