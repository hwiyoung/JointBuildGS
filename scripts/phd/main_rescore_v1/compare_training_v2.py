"""Check any newly delivered JUDGEAPPLY v2 target files once before publication."""
from common import *
def main():
 rows=[]
 for p in sorted((D/'tables').glob('target_diagnostics_*.json')):
  records=json.loads(p.read_text())['rows']
  for r in records:
   stem=f"{r['site']}__{r['prior']}";target=loadz(O/'targets_v2'/f'{stem}.npz',['patch_id','source_index','target_height_m']);candidates=[]
   for folder in JA.glob('*training*'):
    if folder.is_dir():candidates.extend(q for q in folder.glob('*.npz') if r['site'] in q.name and r['prior'] in q.name and ('v2' in folder.name or 'v2' in q.stem))
   comparisons=[]
   for q in sorted(candidates):
    d=loadz(q);height=next((k for k in ['target_height_m','h_no_r','h'] if k in d),None)
    if height is None or not any(k in d for k in ['patch_id','source_index']):comparisons.append(dict(file=str(q),status='확인 불가',reason='명시된 높이 또는 정확 연결 열 없음'));continue
    join='patch_id' if 'patch_id' in d else 'source_index';lookup={str(k):i for i,k in enumerate(d[join])}
    if not all(str(k) in lookup for k in target[join]):comparisons.append(dict(file=str(q),status='확인 불가',reason='핵심점 연결 불완전'));continue
    ix=np.array([lookup[str(k)] for k in target[join]]);a=d[height][ix];b=target['target_height_m'];finite=np.isfinite(a)&np.isfinite(b);same=bool(np.array_equal(np.isfinite(a),np.isfinite(b)));maximum=float(abs(a[finite]-b[finite]).max()) if finite.any() else None;passed=same and maximum is not None and maximum<=.001;comparisons.append(dict(file=str(q),sha256=sha(q),height_field=height,join=join,status='PASS' if passed else 'FAIL',finite_mask_equal=same,max_height_difference_m=maximum,n=int(finite.sum())))
   if comparisons:
    passed=all(c['status']=='PASS' for c in comparisons);r['training_v2_comparison']=dict(status='PASS' if passed else '확인 불가 또는 차이 있음',comparisons=comparisons,max_height_difference_m=max([c.get('max_height_difference_m') or 0 for c in comparisons]) if passed else None)
   else:r['training_v2_comparison']=dict(status='확인 전',reason='JUDGEAPPLY 학습용 v2 파일 미도착; FINALTRAIN 대조는 별도 기록')
   rows.append(dict(site=r['site'],prior=r['prior'],**r['training_v2_comparison']))
  table(p.stem,records)
 table('training_v2_comparison',rows)
if __name__=='__main__':main()
