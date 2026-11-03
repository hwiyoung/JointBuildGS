"""Metadata receipt after the agent opened each of the eight PNGs once."""
from common import *
from PIL import Image
rows=[]
for p in sorted((D/'figures').glob('*.png')):
    with Image.open(p) as im:
        dpi=im.info.get('dpi');assert dpi and all(abs(x-300)<.1 for x in dpi)
        size=list(im.size)
    assert p.with_suffix('.json').exists()
    rows.append(dict(file=p.name,pixels=size,dpi=list(dpi),sha256=sha(p),json_sha256=sha(p.with_suffix('.json'))))
assert len(rows)==8
dump(D/'figure_review.json',dict(at=now(),status='PASS_SINGLE_VISUAL_REVIEW',files=rows,opened_once=True,
     observations=['Two 3x5 mosaics and six regional rows opened together once','Korean labels, captions and common legends readable; no text clipping observed','All five panels share each regional background','Unknown caption values and unavailable hatching retained; no inferred percentages'],scientific_verdict=None))
progress('그림 8개를 한 번 생성하고 모두 한 번 열어 확인: 3×5 합성 2개, 지역별 행6개. 제목·숫자/확인 불가·범례 잘림 없음. 300dpi와 JSON 대응 확인. record_visual_review.py 추가; 설정 재잠금 없음.')
issue('최종 u_M 확인 불가 67,882개. 본 방법 6개 지역/사전정보 조합 모두 칸1·2 분모 내 영역9가 있어 전체 오판율 단일값은 확인 불가. 공통분모는 유지하며 알려진 오판과 미판정 넓이, 산술 하한/상한을 별도로 기록.')
issue('B0/R1의 별도 TARGET r8 영역 파일은 없어 r8 교차는 확인 불가. 단계0 패치와 r7의 동일 원본 source_index를 사용하며 r8 입력 생성 코드의 복사 계보는 source_changes.md에 기록.')
print('VISUAL_REVIEW_RECEIPT',len(rows),flush=True)
