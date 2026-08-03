# C3 U_target=199 postprocess 렌더 recovery 기술 보고서 v1

- task: `P2-C3-UTARGET199-POSTPROCESS-RENDER-RECOVERY-v1`
- 기술 상태: `COMPLETE`
- scientific_verdict: `null`

## 결과

보존된 v1 postprocess에서 정량/Roofer/native geometry 294개 파일, 138,878,463 bytes를
tree SHA-256 `99430520825ed157658d0030101314586fba89845b9dea221453f9af898fc2ea`로
봉인해 새 namespace에 byte-identical 복사했다. 그 위에 누락됐던 actual gsplat panel
8개와 199동 case sheet, qualitative HTML index를 생성했다.

최종 namespace는 539 files, 301,922,446 bytes이고 content-tree SHA-256은
`e19834e4801b0ec8c34ffea2929c773f142fad1838e896de03a86ecd6bb6ca21`이다.
398 result rows, 25 Roofer terminal receipts, 199 case sheets, 8 render panels를 각각
실파일 수와 완료 control로 교차 확인했다.

## 왜 recovery가 필요했는가

첫 v1 postprocess는 두 checkpoint geometry freeze, Roofer 25회, 398행 finalize까지
완료했다. 이후 RGB+expected-depth 렌더에서 gsplat이 depth channel을 추가했지만 wrapper가
RGB 3-channel background만 넘겨 `torch.Size([1, 3])` assertion으로 멈췄다.

wrapper가 RGB+depth 모드에서 `[R,G,B,0-depth]` background를 넘기도록 고쳤고 Docker
focused tests 21개가 통과했다. v1 namespace는 수정·삭제하지 않았다. recovery 실행은
기존 Roofer/metric을 재수행하지 않고 새 namespace에 정확히 복사한 뒤 정성 렌더만 했다.

## 시각 검토

actual gsplat render는 exact common-base view 0, 312, 624, 936을 조건별로 표시한다.
각 패널은 current RGB, GS RGB, GS semantic, GS depth를 한 줄에 둔다. 원해상도 검토에서
두 조건 모두 RGB 구조와 semantic/depth 영상을 실제로 렌더한 것을 확인했다. peak GPU
allocation은 C3-1 255 MiB, C3-2 292 MiB로 18,000 MiB cap보다 낮다.

대표 3동 case sheet는 2185×2875 PNG이며 native Gaussian centers, oriented surfel mesh,
common 1 m Roofer input, Roofer roof + independent UAS cells, output oblique,
reference-centered section을 두 조건 열로 분리한다. `MISSING`과 `NO LoD2 OUTPUT`은 숨기지
않고 표시해 GS geometry 존재와 건물별 read-out 부재를 구분한다.

## 실행 회계와 경계

- recovery C1/C2 rerun: 0
- recovery C3 training: 0
- recovery C3 Roofer rerun: 0
- recovery metric recomputation: 0
- recovery actual gsplat render: 조건별 1회, 총 2회
- G2: 0; C4/C5 access: 0
- official G3/G4/PASS_usable: `null`
- scientific_verdict: `null`

첫 v1의 시각 렌더 결함은 C1/C2, Roofer 또는 C3 학습 실패가 아니다. 반대로 완료된
정성 산출물이 C3의 과학적 성공이나 building usability를 뜻하지도 않는다. 건물별
read-out 수량과 `null` 경계는 상위 기술 보고서에서 별도로 해석한다.
