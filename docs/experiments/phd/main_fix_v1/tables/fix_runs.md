| 지역 | 학습 (결과 이름) | 이번: 코드 · 상태 | GPU | 걸린 시간 (분) | nvidia-smi 최대 (GiB) | PyTorch 할당 최대 (GiB) | 원래 학습: 코드 · 상태 · 시간 (분) · nvidia-smi · PyTorch (GiB) |
|---|---|---|---|---|---|---|---|
| B173 주변 | 사전 정보 신뢰(GeoGS) LoD2, 고친 GeoGS (`trust_LoD2_fix1`) | 고친 GeoGS(fix1) · PASS | 0 | 71 | 17.8 | — | GeoGS 1단계 원본 · PASS · 64 · 11.0 · — |
| R1 | 사전 정보 신뢰(GeoGS) LoD2, 고친 GeoGS (`trust_LoD2_fix1`) | 고친 GeoGS(fix1) · PASS | 0 | 53 | 10.8 | — | GeoGS 1단계 원본 · PASS · 56 · 15.9 · — |
| B0 | 사전 정보 신뢰(GeoGS) LoD2, 고친 GeoGS (`trust_LoD2_fix1`) | 고친 GeoGS(fix1) · PASS | 0 | 54 | 9.2 | — | GeoGS 1단계 원본 · PASS · 53 · 10.4 · — |
| B173만 | 사전 정보 신뢰(GeoGS) LoD2, 고친 GeoGS (`trust_LoD2_fix1`) | 고친 GeoGS(fix1) · PASS | 1 | 196 | 21.2 | — | GeoGS 1단계 원본 · PASS · 139 · 16.4 · — |
| B173 주변 | 판정 빌려 오기 끄기 LoD2 (`abl_prop_LoD2_s0`) | 아직 돌지 않음 | | | | | r13 · OOM · 23 · 18.9 · 22.0 (마지막 기록 14,400회) |
| R1 | 절단 배수 8배 LoD2 (`sens_trunc8_LoD2_s0`) | 아직 돌지 않음 | | | | | r13 · OOM · 24 · 15.6 · 19.6 (마지막 기록 14,300회) |
| B173만 | 본 방법 LoD2 씨앗 0 (`prop_LoD2_s0`) | 아직 돌지 않음 | | | | | r12 · OOM · 24 · 23.5 · 22.0 (마지막 기록 14,800회) |
| B173만 | 영상만 씨앗 0 (`imgonly_s0`) | 아직 돌지 않음 | | | | | r12 · OOM · 23 · 21.9 · 20.8 (마지막 기록 13,600회) |

- nvidia-smi 최대 = 대기열이 30초마다 잰 GPU 사용량의 최대 − 시작 전 사용량(초기화 포함). 짧은 순간의 큰 요청은 놓칠 수 있다.
- PyTorch 할당 최대 = 판정 모듈이 100회마다 적는 `torch.cuda.max_memory_allocated`의 최대(포크 학습만; GeoGS 원본은 적지 않음).
