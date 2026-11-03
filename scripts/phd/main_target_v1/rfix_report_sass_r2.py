"""Clarify actual recorded-training binary versus the locked native reference."""
import rfix_report_sass as original
from common import *
def main():
 original.main();p=DOC/'렌더러_화면상자_고침.md';text=p.read_text();guard=json.loads((OUT/'rfix/guard_binding/result.json').read_text())
 note=f'''r8 LoD2의 **기록용 이어 학습**은 기본 설치 바이너리와 별도로 `jbgs_r8_record_guard.so`를 사용했다(SHA256 `{guard['actual_recorded_renderer_sha256']}`). 이번 원본 A/B 대조는 이전 모의와 같은 기본 설치 바이너리를 썼다. 두 바이너리를 같다고 표시하지 않는다. 실제 감시 빌드의 네 원본 소스와 네 sm_86 수치 커널 명령어는 기본 빌드와 같음을 추가 확인했다. 이 출처 확인은 첫 rfix 렌더 뒤에 수행했으며 기존 감시 빌드의 이전 잠금을 따로 보존했다. [구분 기록](rfix/실행빌드_기록감시.md)에 경로·해시·확인 범위를 적었다. 이 추가 코드 확인은 현재 기울기 실패 판정을 바꾸지 않는다.\n\n'''
 marker='## 5. 단위 점검과 기울기 차이의 기록';assert text.count(marker)==1;text=text.replace(marker,note+marker)
 text=text.replace('`per_view` 원시 결과와 상태 요약','`per_view_full_load.*`와 상태 요약')
 marker='## 4. 별도 렌더러의 수정 범위';assert text.count(marker)==1;text=text.replace(marker,'표의 d는 원본이 반환한 변환행렬에서 같은 식으로 float32 재계산한 진단값이다. 원본 CUDA 전처리의 내부 d를 바꾸거나 잘라서 사용한 값이 아니다.\n\n'+marker)
 p.write_text(text);print('RFIX_RECORDED_BUILD_NOTE_DONE',flush=True)
if __name__=='__main__':main()
