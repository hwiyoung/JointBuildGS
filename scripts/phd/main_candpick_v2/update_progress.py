"""Report designed/complete/stopped separately, without implying a scientific result."""
from cp2_common import *

def main():
    rows=[]
    for v in 'abcd':
        for u in UNITS:
            for s in ['equal','right']:
                arm=f'cp2_{v}_{s}_{u}';root=OUT/'runs'/arm
                gate=OUT/'preflight'/(arm+'.json')
                status='STOP_UNIT_CHECK' if gate.exists() and json.loads(gate.read_text())['status']!='PASS' else 'NOT_STARTED';step=0
                for file in ['progress.json','stopped.json','complete.json']:
                    if (root/file).exists():
                        r=json.loads((root/file).read_text());status=r['status'];step=r.get('iterations',r.get('iteration',step))
                failures=list(root.glob('failure_*.json'))
                if failures and status!='COMPLETE':status='FAILED'
                rows.append(dict(arm=arm,status=status,iteration=step))
    counts={k:sum(r['status']==k for r in rows) for k in sorted({r['status'] for r in rows})}
    depth=len(list((OUT/'depth').glob('*/complete.json')))
    text=f'# 후보 고르기 원인 확인 진행\n\n갱신: {now()}\n\n'
    text+=f'설계 24판. 학습 완료 {counts.get("COMPLETE",0)}판, 단위 점검 중단 {counts.get("STOP_UNIT_CHECK",0)}판, 실행 중 {counts.get("RUNNING",0)}판. [이 발주에서 냄]\n\n'
    text+=f'깊이 채점 완료 {depth}/30판. 사진 다시 셈은 photo_dl/complete.json으로 별도 확인한다.\n\n'
    text+='| 판 | 상태 | 반복 |\n|---|---|---:|\n'
    text+='\n'.join(f'| {r["arm"]} | {r["status"]} | {r["iteration"]} |' for r in rows)
    text+='\n\n설정: candpick_v2.json과 잠금 SHA-256. 앞 작업은 읽기 전용. 중단은 성공이나 0값으로 바꾸지 않는다.\n\nscientific_verdict: null\n'
    (DOC/'progress.md').write_text(text)
    save(DOC/'tables/progress.json',dict(at=now(),rows=rows,counts=counts,depth_complete=depth,scientific_verdict=None),replace=True)
    print(counts,'depth',depth,flush=True)

if __name__=='__main__':main()
