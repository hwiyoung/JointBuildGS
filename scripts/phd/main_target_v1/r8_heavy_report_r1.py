"""Add completed independent checks and direct subset-camera figures to locked report."""
from r8_heavy_report import *
from r8_heavy_report import build as original_build
def build():
 check=read(H/'independent_verification.json');assert check['status']=='PASS';subset=read(H/'subset/receipt.json');assert len(subset['rows'])==2 and all(r['individual_tiles_match_full_selection'] for r in subset['rows'])
 report,dest=original_build();s=report.read_text();s=s.replace('결론과 원인 해석은 쓰지 않고','새 수치에는 [이 발주에서 냄]을 적용한다. 결론과 원인 해석은 쓰지 않고')
 s=s.replace('## 그림과 개별 계보 자료','## 독립 검증\n\n20개 상태·영상 조합의 상위 합을 정렬과 다른 partition 계산으로 재확인했다. 압축 CSV의 모든 행을 원본 행 번호·겹침·처음 씨앗 ID·출신과 대조했고 순위·동률 순서·합계가 일치했다. 상위 1%·10%만 별도로 렌더한 개별 겹침 배열도 전체 렌더에서 선택한 배열과 같았다. 중단 완전 상태의 난수·영상 스택으로 다음 영상이 중단 영상임을 확인했고 모델·Adam의 유한값과 저장 반복 경계를 검증했다.\n\n## 그림과 개별 계보 자료')
 s=s.replace('![상위 1% 위치]', '![상위 무리만 실제 렌더](heavy_r8_lod2/figures/top_groups_rgb.png)\n\n![처음 씨앗을 고정한 자손](heavy_r8_lod2/figures/fixed_initial_seed_cohorts.png)\n\n![상위 1% 위치]')
 report.write_text(s);shutil.copy2(H/'independent_verification.json',dest/'independent_verification.json');shutil.copy2(H/'subset/receipt.json',dest/'subset_render_verification.json');return report,dest
if __name__=='__main__':build()
