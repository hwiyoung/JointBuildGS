"""Promote numerical evidence and screenshots; preserve the entire original release."""
import os
import platform
import time
import zipfile
import sys
sys.path.insert(0,'/repo/scripts/phd/main_uncert_view_v1')
from common import *
from verify_v11 import md

TD=DOC/'tables_v1_1'

def fmt(x):
    if x is None:return '없음'
    if isinstance(x,float):return f'{x:.5g}'
    return str(x)

def table(headers,rows):
    return '| '+' | '.join(headers)+' |\n|'+'|'.join(['---']*len(headers))+'|\n'+''.join('| '+' | '.join(fmt(x) for x in row)+' |\n' for row in rows)+'\n'

def main():
    start=time.perf_counter();config=load(CFG/'view_v1_1.json');assert sha(CFG/'view_v1_1.json')==load(CFG/'view_v1_1.lock.json')['sha256']
    browser=load(TD/'browser_full.json');assert not browser.get('fatal') and not browser['errors'] and not browser['failures']
    final=load(TD/'browser_final.json');assert not final.get('fatal') and not final['errors'] and not final['failures']
    inputs=load(TD/'input_receipt.json')['files'];previous=load(DOC/'tables/input_audit.json')['inputs']
    receipts={r['path']:r for r in inputs+previous};changed=[]
    for path,r in receipts.items():
        if not Path(path).is_file() or sha(path)!=r['sha256']:changed.append(path)
    dump(TD/'integrity.json',dict(made=now(),checked=len(receipts),changed=changed,config_sha256=sha(CFG/'view_v1_1.json'),scientific_verdict=None))
    assert not changed,changed
    curves=load(TD/'reference_charts.json')['results'];ref=load(TD/'face_reference.json');assignment=load(TD/'face_assignment.json')['rows'];pairs=load(TD/'pair_reference.json')['rows'];comparison=load(TD/'report61_comparison.json')
    dump(TD/'calibration.json',dict(rows=[dict(case=key,exclude=r['exclude'],**p) for key,r in curves.items() for p in r['calibration']],scientific_verdict=None))
    sparse_rows=[dict(case=key,source=source,**r) for key,r in curves.items() for source,s in r['sparse'].items() for r in s.get('rows',[])]
    dump(TD/'sparsification.json',dict(values=sparse_rows,areas=[dict(case=key,source=source,**{k:v for k,v in s.items() if k!='rows'}) for key,r in curves.items() for source,s in r['sparse'].items()],scientific_verdict=None))
    md(TD/'sparsification_values.md',['경우','자료','뺀 비율 %','남은 패치','실제 오차 평균 cm','이상적 평균 cm','정규화 곡선','정규화 이상적'],[[r[k] for k in ['case','source','percent','remaining','mean_cm','ideal_mean_cm','curve','ideal']] for r in sparse_rows])
    frows=[]
    for f in ref['samples']:
        actual=next(x['actual'] for x in browser['faces'] if x['case']==f['case'] and x['face_id']==f['face_id'])
        for layer,stat in f['stats'].items():
            a,b=stat['p50'],actual[layer]['p50'];diff=abs(a-b) if a is not None and b is not None else None
            frows.append(dict(case=f['case'],face=f['face_id'],layer=layer,n=stat['n'],source_median_cm=a,browser_median_cm=b,difference_cm=diff,mark='!' if ((a is None)!=(b is None) or diff is not None and diff>.1) else ''))
    dump(TD/'face_comparison.json',dict(rows=frows,seed=config['seed'],scientific_verdict=None))
    md(TD/'face_comparison.md',['경우','면','층','값 있음','독립 중앙값 cm','화면 중앙값 cm','차이 cm','표시'],[[r[k] for k in ['case','face','layer','n','source_median_cm','browser_median_cm','difference_cm','mark']] for r in frows])
    v1=load(DOC/'tables/table_recount.json');dump(TD/'v1_recount.json',v1)
    md(TD/'v1_recount.md',['항목','범위','앞 보고','v1 다시 셈','단위','차이','표시'],[[r['label'],json.dumps(r['context'],ensure_ascii=False),r['report'],r['recount'],r['unit'],r['difference'],'' if r['match'] else '!'] for r in v1['rows']])
    oldqa=load(DOC/'tables/browser_full.json');oldrows=[]
    for check in oldqa['checks']:
        for r in check.get('result',{}).get('comparisons',[]):oldrows.append(dict(question=check['test'],**r))
    dump(TD/'v1_browser_comparison.json',dict(rows=oldrows,scientific_verdict=None))
    md(TD/'v1_browser_comparison.md',['물음','항목','앞 보고','v1 화면','단위'],[[r.get(k) for k in ['question','label','report','now','unit']] for r in oldrows])
    web=OUT/'web_v1_1';files=[dict(path=str(p.relative_to(web)),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(web.rglob('*')) if p.is_file() and 'downloads' not in p.relative_to(web).parts]
    archive=OUT/'PHD-MAIN-UNCERT-VIEW-v1.1_web.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for r in files:z.write(web/r['path'],'web/'+r['path'])
    package=dict(made=now(),web_bytes=sum(r['bytes'] for r in files),zip_bytes=archive.stat().st_size,zip_sha256=sha(archive),files=files,v1_preserved=True,scientific_verdict=None)
    dump(TD/'package.json',package)
    label=lambda s:s.replace('pool__','세 지역 합 · ').replace('B0_b10','B0').replace('B173nb_b10','B173 주변').replace('R1rep_b10','R1').replace('__',' · ').replace('ALS','항공 LiDAR')
    lines=['# 불확실도 보기 보고 v1.1','',
        '보정 그림·희소화 곡선, LoD2 면 단위 보기, 지도 짝 세 가지와 부호 있는 색을 추가·수정했다.',
        '여는 주소: [불확실도 지도 v1.1](http://192.168.10.203:8912/) — 연구실 네트워크·VPN에서 파일 실행 없이 접속한다.',
        '판정 그림과 면 값은 화면에서 다시 셈이며 참값 관련 값은 참값 점검용이다. `scientific_verdict: null`.','',
        '## 1. 바꾼 것과 여는 법','',
        '- 위쪽의 보는 단위에서 패치·면을 바꾼다. 지도 짝 단추는 면과 0~50 cm를 선택하며 양쪽 색 범위를 함께 바꾼다.',
        '- 판정 그림은 왼쪽 걸러 보기와 범위를 따르며 항상 패치로 센다. 세 지역 합은 B0 1 m, B173 주변·R1 1.5 m다.',
        '- 크게 틀린 곳 빼기는 사전 정보의 보정 · 4τ 넘음만 제외한다. MVS·지도에는 적용하지 않는다. 보정 · 1~4τ는 남는다.',
        '- 면 중앙값·25·75 % 값과 값 있음 비율은 면 카드에서 확인한다. 이 면의 패치 보기로 더 작은 곳을 확인한다.',
        '- 부호 있는 두 층은 −50~+50 cm, 0은 흰색이다. 지붕 형태는 LoD2 속성으로 표시한다.','',
        '## 2. 판정 그림의 숫자','',
        '화면에서 다시 셈 · 참값 점검용. 아래는 평가 범위, 지역마다 고른 고리 크기, MVS 판 가, 걸러 보기 없음이다. 30개 미만 구간도 표에는 남겼다. 길이는 cm, 비율과 넓이는 단위 없음이다.','',
        '[보정 그림 전체 표](tables_v1_1/calibration.md) · [JSON](tables_v1_1/calibration.json) · [희소화 곡선 값](tables_v1_1/sparsification_values.md) · [두 넓이](tables_v1_1/sparsification.md) · [JSON](tables_v1_1/sparsification.json)','']
    for key,r in curves.items():
        if '__exclude_' not in key:continue
        lines+=['### '+label(key.split('__exclude_')[0])+' · 크게 틀린 곳 빼기 '+('켬' if r['exclude'] else '끔'),'']
        lines.append(table(['자료','구간 / 면','패치 수','u 중앙값','e 중앙값','e 25 %','e 75 %','e ÷ u 중앙값'],
            [['MVS' if p['source']=='mvs' else '사전 정보',label(p['label']),p['n'],p['u_median_cm'],p['e_median_cm'],p['e_p25_cm'],p['e_p75_cm'],p['median_e_over_u']] for p in r['calibration']]))
        lines.append(table(['자료','곡선−이상적 넓이','무작위−이상적 넓이'],[['MVS' if src=='mvs' else '사전 정보',p.get('area_curve_ideal'),p.get('area_random_ideal')] for src,p in r['sparse'].items()]))
        if r['prior']=='LoD2':lines.append('LoD2는 20 cm 한 값이어서 희소화 곡선을 그리지 않는다.\n')
    lines+=['## 3. 맞춰 보기 표','',
        table(['점검','수','허용 기준','차이'],[['앞 보고 6.1 구간별 패치 수·25·50·75 %',len(comparison['rows']),'길이 0.1 cm, 패치 수 0개',comparison['differences']],['무작위 면 중앙값',len(frows),'길이 0.1 cm',sum(bool(r['mark']) for r in frows)],['브라우저 수치·조작',len(browser['checks']),'수치 0.000001 또는 개수 일치',len(browser['failures'])]]),
        '[앞 보고 / 다시 셈 전체 비교](tables_v1_1/report61_comparison.md) · [JSON](tables_v1_1/report61_comparison.json) · [60개 면의 독립 / 화면 중앙값 비교](tables_v1_1/face_comparison.md) · [브라우저 기록](tables_v1_1/browser_full.json)','',
        f"추가 조작 점검 {len(final['checks'])}개: 점 선택 후 패치 표시, 세 지역 합의 지역별 고리 적용, 다른 지역 선택 시 필터 유지, 비스듬히 보기의 면 클릭, 오프라인 묶음. [기록](tables_v1_1/browser_final.json).",'',
        '## 4. 면 붙이기 결과','',
        '면 목록은 `PH/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1/s02_box/<지역>/lod2_surfaces.json`, 같은 폴더의 `lod2_mesh.npz`에서 삼각형을 읽었다. 좌표는 EPSG:25832에서 원래 world shift를 뺀 COLMAP 모델 좌표다. 면 번호와 LoD2 영역 파일의 `surf_ext`를 맞췄다. 항공 LiDAR는 지붕의 XY 포함·가장 가까운 높이, 벽은 1 m 안의 가장 가까운 삼각형으로 붙였다. 나머지는 2 m 격자다.','',
        table(['경우','연결된 면 수','전체 패치','면 패치 %','격자 패치 %','평가 범위 면 / 격자 패치','평가 범위 면 수','표본 부족 MVS 짝 / 사전 정보 짝'],
            [[label(a['case']),a['faces'],a['total'],100*a['attached_fraction'],100*(1-a['attached_fraction']),f"{a['eval_attached']} / {a['eval_grid']}",c['eval_faces'],f"{c['insufficient_mvs_pair']} / {c['insufficient_prior_pair']}"] for a in assignment for c in ref['coverage'] if a['case']==c['case']]),
        '표본 부족은 현재 범위·필터를 통과한 면 패치 중 해당 층의 값이 10개 미만 또는 30 % 미만인 경우다. 두 지도는 각 층의 표본 부족을 따로 표시한다.','',
        '## 5. 지도 짝의 숫자 줄','',
        '화면에서 다시 셈. 두 층 모두 표본이 충분한 LoD2 면만 센다. 격자는 제외한다. 같은 값뿐인 층의 순위 상관은 없음이다.','',
        table(['경우','짝','면 수','순위 상관','오른쪽 ÷ 왼쪽 중앙값'],[[label(p['case']),next(c['label'] for c in config['pairs'] if c['id']==p['pair']),p['n'],p['rho'],p['median_right_over_left']] for p in pairs]),
        '## 6. 화면 사진','',
        '요청한 34장과 시작 화면·부호 색·좁은 화면 3장을 저장했다. 사진마다 촬영 상태와 숫자 한 줄을 적었다. 숫자는 화면에서 다시 셈이다.','']
    for shot in browser['screens']:
        st=shot['state'];ps=st['pairStats'];counts=st['counts'];nm=shot['name']
        lines+=['### '+nm,'',f'![{nm}](screens_v1_1/{nm}.png)','',
          f"{label(st['case'])} · 고리 {st['r']} m · MVS 판 {'가' if st['v']=='a' else '나'} · {'평가 범위' if st['scope']=='eval' else '둘레 띠 포함'} · {'면' if st['unit']=='face' else '패치'} · {'세 지역 합' if st['pool'] else '지금 경우'} · 크게 틀린 곳 빼기 {'켬' if st['exclude'] else '끔'}. 화면에서 다시 셈: 그림의 MVS {counts['mvs']}개 / 사전 정보 {counts['prior']}개; 지도 면 {ps['n']}개, 순위 상관 {fmt(ps['rho'])}, 오른쪽 ÷ 왼쪽 {fmt(ps['median_right_over_left'])}.",'']
    lock=load(CFG/'view_v1_1.lock.json');elapsed=(dt.datetime.fromisoformat(now())-dt.datetime.fromisoformat(lock['made'])).total_seconds()
    lines+=['## 7. v1 맞춰 보기와 다시 셈 점검 표','',
        'v1 보고에는 전체 행의 맞춰 보기 표가 링크된 JSON 중심으로 남아 있어, 이번에 같은 기록을 Markdown 표로 함께 제공한다. 새 수치로 바꾸지 않았다.','',
        f"- [v1 독립 다시 셈 전체 {v1['comparisons']}행](tables_v1_1/v1_recount.md) · [JSON](tables_v1_1/v1_recount.json). 당시 일치 {v1['matched']}행.",
        f'- [v1 여섯 확인 물음의 보고 / 화면 비교 {len(oldrows)}행](tables_v1_1/v1_browser_comparison.md) · [JSON](tables_v1_1/v1_browser_comparison.json).','',
        '## 8. 변경·확인 불가·시간','',
        f"- 첫 빌드 전 잠금: {lock['made']}. SHA-256 `{lock['sha256']}`. 설정 변경 이력은 비어 있으며 최초 정의를 유지했다.",
        f'- 원본·v1 보존: {len(receipts)}개 입력의 SHA-256 일치. v1 웹과 ZIP은 그대로 남았다. [보존 점검](tables_v1_1/integrity.json).',
        f"- v1.1 웹 {package['web_bytes']/1e6:.2f} MB, ZIP {package['zip_bytes']/1e6:.2f} MB. 정밀도·표본 수를 줄이지 않았다.",
        '- 학습 없음, GPU 없음. 계산은 Docker CPU의 NumPy·SciPy, 화면은 Chromium의 CPU 표시를 사용했다. 원래 불확실도 값·설정·방법 코드는 변경하지 않았다.',
        '- 확인 불가: Windows Chrome·Edge 직접 실행. Linux Chromium에서 계산·지도 선택·면 카드·필터·색 범위 연결을 확인했다.',
        f'- 설정 잠금부터 보고 생성까지 {elapsed/60:.1f}분. 브라우저 점검 {browser["started"]} ~ {browser["finished"]}.',
        '- 표시 수정과 예외는 [점검 기록](issues_v1_1.md)에 적었다. 유효 확률과 과학적 판정은 추가하지 않았다.','']
    (DOC/'불확실도보기_보고_v1_1.md').write_text('\n'.join(lines))
    import scipy
    code=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in sorted((ROOT/'scripts/phd/main_uncert_view_v1').glob('*')) if p.is_file()]
    dump(TD/'receipt_task.json',dict(task_id=config['task_id'],made=now(),commit=os.environ.get('VIEW_COMMIT'),image=os.environ.get('VIEW_IMAGE'),
         versions=dict(python=platform.python_version(),numpy=np.__version__,scipy=scipy.__version__),implementation_files=code,
         config_sha256=sha(CFG/'view_v1_1.json'),url='http://192.168.10.203:8912/',source_files_unchanged=len(receipts),browser_checks=len(browser['checks'])+len(final['checks']),screens=len(browser['screens']),scientific_verdict=None))
    progress(f'v1.1 일 4: 브라우저 {len(browser["checks"])}개 점검 통과, 사진 {len(browser["screens"])}장과 보고·숫자 표·ZIP 저장. 원본과 v1 {len(receipts)}개 SHA-256 일치. scientific_verdict: null.')
    print('Report complete',len(receipts),'unchanged files; web bytes',package['web_bytes'],'zip',package['zip_bytes'],'seconds',time.perf_counter()-start)

if __name__=='__main__':main()
