"""Add observed binary-kernel comparison without changing the locked numerical gate."""
import csv
from common import *
ROOT=OUT/'rfix';DEST=DOC/'rfix'
def main():
 rows=[]
 for label in ['target','imageonly','geogs']:
  data=json.loads((ROOT/'sass_audit'/label/'result.json').read_text())
  for r in data['rows']:
   if 'renderCUDA' in r['kernel'] or 'preprocessCUDA' in r['kernel']:rows.append(dict(build=label,**r))
 assert len(rows)==12 and all(r['instruction_listing_equal'] for r in rows)
 p=DEST/'tables/native_kernel_sass';dump(p.with_suffix('.json'),dict(rows=rows,scientific_verdict=None));keys=list(rows[0])
 with p.with_suffix('.csv').open('w',newline='') as f:w=csv.DictWriter(f,keys);w.writeheader();w.writerows(rows)
 p.with_suffix('.md').write_text('\n'.join(['| '+' | '.join(keys)+' |','|'+'|'.join(['---']*len(keys))+'|']+['| '+' | '.join(str(r[k]) for k in keys)+' |' for r in rows])+'\n')
 report=DOC/'렌더러_화면상자_고침.md';text=report.read_text();marker='## 6. 기존 GeoGS·2DGS 채점의 메시 출처';assert text.count(marker)==1
 note='''컴파일된 바이너리도 CPU 도구 `cuobjdump --dump-sass`로 대조했다. 세 빌드 모두 sm_86의 원본/고침 `renderCUDA` 두 함수와 `preprocessCUDA` 두 함수의 명령어 목록과 인코딩이 정확히 같았다(총 12개 비교). 원문과 함수별 SHA256은 `sass_audit/`, 표는 `native_kernel_sass.*`에 있다. 바뀐 타일 목록과 실행 순서는 이 코드 동일성의 검사 대상이 아니며, 이 관측으로 기울기 수치 실패 판정을 대체하지 않는다.\n\n'''
 report.write_text(text.replace(marker,note+marker));print('RFIX_SASS_NOTE_DONE',flush=True)
if __name__=='__main__':main()
