"""Independently verify the stopped input audit and publish its spatial evidence only."""
import csv
import math
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt, font_manager
from scipy.spatial import cKDTree
from common import *

NAMES = {'B0_b10':'B0','B173nb_b10':'B173 주변','B173_b0':'B173만','R1rep_b10':'R1'}


def main():
    cfg, lock = locked()
    audit = json.loads((OUT/'input_audit.json').read_text())
    assert audit['status']=='STOP_STAGE0'
    out = []; masks = {}; inputs = []
    for row in audit['rows']:
        rp,up = Path(row['region_path']),Path(row['uncertainty_path'])
        assert sha(rp)==row['region_sha256'] and sha(up)==row['uncertainty_sha256']
        inputs += [{'path':str(p),'sha256':sha(p)} for p in [rp,up]]
        with np.load(rp) as r:
            xyz,area,ev = r['centre'],r['area'],r['in_eval'].astype(bool)
        v = dict(site=row['site'],prior=row['prior'],patches=len(area),area_m2=math.fsum(area),
                 status=row['status'],matched_patches=row['matched_patches'],unmatched_patches=row['unmatched_patches'])
        with np.load(up) as u:
            if row['direct_source_exists']:
                assert np.array_equal(xyz,u['centre'])
                n = u['normal']
                badnormal = ~np.isfinite(n).all(1) | (np.abs(np.sqrt(np.einsum('ij,ij->i',n,n))-1)>1e-6)
                badsigma = ~np.isfinite(u['u_prior']) if row['prior']=='ALS' else np.zeros(len(area),bool)
                missing = badnormal | badsigma
                frac = math.fsum(area[missing])/math.fsum(area)
                assert math.isclose(frac,row['unavailable_area_fraction'],rel_tol=1e-12,abs_tol=1e-14)
                assert int(missing.sum()) == row['unavailable_patches']
                v.update(missing_normal_count=int(badnormal.sum()),missing_normal_area_m2=math.fsum(area[badnormal]),
                    missing_sigma_count=int(badsigma.sum()),missing_sigma_area_m2=math.fsum(area[badsigma]),
                    unavailable_count=int(missing.sum()),unavailable_area_m2=math.fsum(area[missing]),
                    unavailable_fraction=frac,eval_unavailable_fraction=math.fsum(area[missing&ev])/math.fsum(area[ev]),
                    band_unavailable_fraction=math.fsum(area[missing&~ev])/math.fsum(area[~ev]) if (~ev).any() else None)
                if row['prior']=='ALS':
                    statuses=u['als_status']
                    v['missing_sigma_by_als_status']={str(k):{'patches':int((badsigma&(statuses==k)).sum()),
                        'area_m2':math.fsum(area[badsigma&(statuses==k)])} for k in np.unique(statuses[badsigma])}
                    assert bool(frac>.1)
                masks[(row['site'],row['prior'])]=(xyz,missing)
            else:
                # Independent grid-index exact lookup, then coordinate confirmation.
                tol=cfg['uncertainty']['coordinate_tolerance_m']
                src=u['centre']; grid={}
                for i,key in enumerate(map(tuple,np.rint(src/tol).astype(np.int64))):
                    grid.setdefault(key,[]).append(i)
                found=np.zeros(len(xyz),bool)
                for i,key in enumerate(map(tuple,np.rint(xyz/tol).astype(np.int64))):
                    js=grid.get(key,[])
                    if len(js)==1 and np.linalg.norm(src[js[0]]-xyz[i])<=tol:
                        found[i]=True
                # All remaining nearest distances are independently confirmed as positive.
                dist,_=cKDTree(src).query(xyz,k=1,workers=1)
                assert int((dist<=tol).sum())==row['unregistered_exact_centres']
                assert np.array_equal(found,dist<=tol)
                assert (~found).any()
                v.update(exact_coordinate_count=int(found.sum()),missing_coordinate_count=int((~found).sum()),
                    missing_coordinate_area_m2=math.fsum(area[~found]))
                masks[(row['site'],row['prior'])]=(xyz,~found)
        out.append(v)
    verification={'status':'PASS_STOP_EVIDENCE','at':stamp(),'rows':out,'input_hashes':inputs,
        'config_sha256':lock['config_sha256'],'validation':'Independent fsum areas, direct missing source fields, exact grid coordinate lookup and nearest-distance cross-check',
        'scientific_verdict':None,'source_tag':'[이 발주에서 냄]'}
    dump(DOC/'tables/stop_verification.json',verification)
    dump(OUT/'stop_verification.json',verification)
    fonts=sorted(Path('/fonts').glob('*CJK*Regular*'))
    if fonts:
        font_manager.fontManager.addfont(str(fonts[0]))
        plt.rcParams['font.family']=font_manager.FontProperties(fname=str(fonts[0])).get_name()
    plt.rcParams.update({'axes.unicode_minus':False,'font.size':11,'axes.spines.top':False,'axes.spines.right':False})
    (DOC/'figures').mkdir(exist_ok=True)
    for prior in ['ALS','LoD2']:
        items=[v for v in out if v['prior']==prior and v['site']!='B173_b0']
        fig,axes=plt.subplots(1,3,figsize=(14.5,5.5))
        title='항공 LiDAR 세 지역에서 셀 수 없는 넓이가 10%를 넘는다' if prior=='ALS' else 'LoD2 세 지역은 입력 연결과 10% 기준을 통과했다'
        fig.suptitle(title,fontsize=17,y=.98)
        for ax,v in zip(axes,items):
            xyz,bad=masks[(v['site'],prior)]
            ax.scatter(xyz[:,0],xyz[:,1],s=.45,c='#b7bcc2',rasterized=True)
            ax.scatter(xyz[bad,0],xyz[bad,1],s=1.7,c='#c75a22',marker='x',linewidths=.45,rasterized=True)
            ax.set_aspect('equal');ax.set_title(NAMES[v['site']]);ax.set_xlabel('동쪽 좌표 (m)');ax.set_ylabel('북쪽 좌표 (m)')
            ax.text(.5,-.21,f"{v['unavailable_area_m2']:,.2f} / {v['area_m2']:,.2f} m² · {100*v['unavailable_fraction']:.3f}%",transform=ax.transAxes,ha='center',fontsize=10)
        fig.text(.5,.025,'주황 ×: 셀 수 없음 · 회색: 나머지 패치 · 평가 범위와 저장된 둘레 띠 · 좌표: 공통 원점 기준 · [이 발주에서 냄]',ha='center',fontsize=10)
        fig.subplots_adjust(left=.06,right=.99,bottom=.22,top=.86,wspace=.32)
        name=f'input_missing_{prior}'
        fig.savefig(DOC/'figures'/f'{name}.png',dpi=170);plt.close(fig)
        dump(DOC/'figures'/f'{name}.json',{'title':title,'rows':items,'source':'tables/stop_verification.json',
            'frame':cfg['frame'],'plot':'all patches; no statistical thinning','scientific_verdict':None})
    items=[v for v in out if v['site']=='B173_b0']
    fig,axes=plt.subplots(1,2,figsize=(11,6))
    title='B173만의 패치 전체를 B173 주변의 고리 불확실도에 연결할 수 없다'
    fig.suptitle(title,fontsize=15,y=.98)
    for ax,v in zip(axes,items):
        xyz,bad=masks[(v['site'],v['prior'])]
        ax.scatter(xyz[:,0],xyz[:,1],s=.6,c='#b7bcc2',rasterized=True)
        ax.scatter(xyz[bad,0],xyz[bad,1],s=4,c='#c75a22',marker='x',linewidths=.6,rasterized=True)
        ax.set_aspect('equal');ax.set_title('항공 LiDAR' if v['prior']=='ALS' else 'LoD2')
        ax.set_xlabel('동쪽 좌표 (m)');ax.set_ylabel('북쪽 좌표 (m)')
        ax.text(.5,-.17,f"좌표 미연결 {v['missing_coordinate_count']:,} / {v['patches']:,}개",transform=ax.transAxes,ha='center',fontsize=11)
    fig.text(.5,.04,'주황 ×: 같은 중심 없음 · 회색: 같은 중심 있음 · 두 지역의 학습 영상 목록도 다름 · [이 발주에서 냄]',ha='center',fontsize=10)
    fig.subplots_adjust(left=.07,right=.98,bottom=.20,top=.86,wspace=.3)
    fig.savefig(DOC/'figures/input_join_B173.png',dpi=170);plt.close(fig)
    dump(DOC/'figures/input_join_B173.json',{'title':title,'rows':items,'source':'tables/stop_verification.json',
        'frame':cfg['frame'],'meaning':'coordinate equality only, not accepted uncertainty transfer','scientific_verdict':None})
    table=['| 지역 | 사전 정보 | 전체 넓이 m² | 셀 수 없음 m² | 비율 | 입력 상태 |','|---|---|---:|---:|---:|---|']
    for v in out:
        a=f"{v['unavailable_area_m2']:.2f}" if 'unavailable_area_m2' in v else '확인 불가'
        f=f"{100*v['unavailable_fraction']:.3f}%" if 'unavailable_fraction' in v else '확인 불가'
        status='통과' if v['status']=='PASS_INPUT_JOIN' else ('불확실도 연결 실패' if 'JOIN' in v['status'] else '10% 초과')
        table.append(f"| {NAMES[v['site']]} | {'항공 LiDAR' if v['prior']=='ALS' else 'LoD2'} | {v['area_m2']:.2f} | {a} | {f} | {status} |")
    tabletext='\n'.join(table)
    (DOC/'tables/input_audit.md').write_text(tabletext+'\n\n[이 발주에서 냄]. 공간 근거: ../figures/input_missing_ALS.png, input_missing_LoD2.png, input_join_B173.png.\n')
    with (DOC/'tables/input_audit.csv').open('w') as f:
        fields=['site','prior','patches','area_m2','unavailable_count','unavailable_area_m2','unavailable_fraction','matched_patches','unmatched_patches','status']
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(out)
    report=f'''# 영역별 목표 학습 — 단계 0 중단 보고

판단 정확도: 개발용·확인용·실험 지역 모두 미실행. 단계 0 입력에서 중단했다.
7,000회 점검: 미실행. 학습 0판이다.
8판의 네 값: 확인 불가. 목표와 모델을 만들지 않았다.
GS와 목표로 바로 만든 메시 비교: 미실행.
확인 불가: 항공 LiDAR 사전 정보 정밀도 누락, B173만 고리 불확실도 연결. 입력 감사 실행 {audit['seconds']:.2f}초. scientific_verdict: null.

## 단계 0: 입력 중단 근거

발주문 2.8의 두 조건에 걸렸다. 설정을 {lock['at']}에 잠갔으며, 해시는 `{lock['config_sha256']}`이다.
기준의 분모는 영역 파일의 모든 패치 넓이(평가 범위와 저장된 둘레 띠)이다. MVS 고리 u가 없는 경우의 허용 대체(a 또는 0)와 사전 정보 σ_P가 없는 경우를 구별했다. 후자는 발주문 2.5에 따라 셀 수 없음이다.

{tabletext}

[이 발주에서 냄]. B173만의 빈 값은 0이 아니다. 다른 세 지역의 LoD2 통과는 입력 검사 통과이며 판단 확정 완료를 뜻하지 않는다.

![항공 LiDAR 입력 누락](figures/input_missing_ALS.png)

![LoD2 입력 누락](figures/input_missing_LoD2.png)

![B173만 연결 검사](figures/input_join_B173.png)

항공 LiDAR의 원본 `u_prior`는 UNCERT `u2_merge.py`에서 `als_status == 0`일 때만 `als_u`를 넣고, 나머지는 NaN으로 남긴다. 그 값을 √(u_prior²+0.0275²)로 바꾸어도 NaN은 남는다. 법선 없음과 정밀도 없음의 각각의 수·넓이, 평가 범위·둘레 띠 비율, 원본 상태 번호는 `tables/stop_verification.json`에 있다. 과거 LOSSTRAIN의 단위 중앙값 대체는 이번 발주에 없으므로 적용하지 않았다.

B173만 항공 LiDAR는 29,955개 중 같은 중심이 36개이고, LoD2는 119,384개 중 11개의 같은 중심이 없다. B173만과 B173 주변의 학습 영상 목록도 같지 않다. 같은 중심이 있는 것만으로 같은 MVS 불확실도를 보장하지 않으며, 이번에는 전달하지 않았다.

T2 혼합, 사진 판단 재계산, 깊이 목표 생성은 미실행이다. 확인용 건물의 판단 정확도도 열지 않았다. 민감도 판으로 바꾸지 않았다.

## LoD2 정밀도 값의 출처

수치 연결은 JUDGENUM `detection.prior_sigma` → PHOTOCHECK `uncertainty`와 `prepare.py` → PHOTOCHECK 발주문 부록 C의 2026-10-26 새 값까지 확인했다. LOSSTRAIN `direct_stage1_v2.json`에는 소수 여섯 자리의 값과 2026-10-26 사용자 수정안 출처가 있다. 이 파일들에는 최초 추정 계산과 모집단, 참값 사용 여부가 기록되어 있지 않다. 따라서 구축 기준인지, 자료 추정인지, 참값을 사용했는지는 **확인 불가**다. 참값을 쓰지 않았다고 인증하지 않는다. 이번 중단 상태에서 이 값을 사용한 목표·학습은 없다.

## 단계 1과 단계 2

최신 바탕 후보는 `GeoGS-conf-guided-v1-r18`이다. 해당 폴더의 마지막 추적 변경 커밋은 `f614090ab5444090182890c6c43505a3a4e5af8f`이며, 현재 폴더에는 미추적 파일도 있어 그 커밋을 전체 코드의 바이트 식별자로 삼지 않았다. 새 r19 구현과 학습 전 단위 점검, 7,000회 점검은 단계 0에서 중단하여 시작하지 않았다. 목표 메시·최종 메시·채점·비교 방법 표와 대표 자리 결과 그림은 모두 미실행이다.

## 재개에 필요한 결정

1. 항공 LiDAR 정밀도가 없는 패치의 처리: 현재 규칙을 유지할지, 참값 없이 다시 구하는 절차를 추가할지, 명시적인 대체 규칙을 승인할지 결정이 필요하다.
2. B173만의 고리 불확실도: 해당 단위의 MVS 입력으로 같은 정의의 u를 별도로 구하는 추가 작업이 필요하다. 주변 단위의 최근접 값을 복사하지 않는다.
3. LoD2 정밀도의 원 추정 근거를 확보해야 참값 미사용을 확인할 수 있다.

발주문 1.8과 2.8의 중단 뒤 질문 규칙 때문에 후속 계산을 보류한다. 방법의 효과나 과학적 결론은 내리지 않는다.

## 바꾼 것과 검증

이번 작업의 설정·CPU 실행기·입력 감사·검산·보고서·그림만 새로 만들었다. 기존 설정·결과·포크는 수정하지 않았다. Docker에서 GPU 없이 실행했으며 원본은 읽기 전용으로 연결했다. 별도 검산에서 원본 해시, 넓이 합, 누락 조건, B173 좌표 대응을 확인했다. 그림은 전체 패치로 그렸고 숫자 원본은 같은 이름의 JSON에 남겼다. 확인용 패치 값은 공개 산출물에 없다.

재현: `bash scripts/phd/main_target_v1/run_cpu.sh audit audit_inputs.py`, 이어서 `bash scripts/phd/main_target_v1/run_cpu.sh verify verify_stop_report.py`. 원본 외부 자료가 필요하다. 이 재현은 중단 근거만 재계산하며 학습을 실행하지 않는다.
'''
    (DOC/'영역별목표학습_보고_v1.md').write_text(report)
    progress=f'''# PHD-MAIN-TARGET-v1

{stamp()} — STOP_STAGE0. 발주문 2.8에 따른 사용자 결정 대기.

- 항공 LiDAR 셀 수 없음: B0 26.53%, B173 주변 31.04%, R1 21.16% (기준 10%).
- B173만: 두 사전 정보 모두 고리 불확실도의 전체 입력 연결 실패.
- 검산: PASS_STOP_EVIDENCE. 판단 정확도·T2·목표·학습·메시·채점 미실행.
- 예상 재개 시각: 사용자 결정과 입력 보완 전에는 확인 불가.
- scientific_verdict: null.
'''
    (DOC/'progress.md').write_text(progress);(OUT/'progress.md').write_text(progress)
    (DOC/'issues.md').write_text('''# PHD-MAIN-TARGET-v1 문제 기록

- STOP_STAGE0_UNAVAILABLE_AREA: 항공 LiDAR 세 단위에서 원본 정밀도·법선 누락의 합집합 넓이가 10% 초과. 해결되지 않음. 임의 대체 없음.
- STOP_STAGE0_UNCERTAINTY_JOIN: B173만 두 사전 정보에 직접 고리 값 없음. 주변 단위와 전체 패치 대응 및 동일 MVS 근거 부족. 해결되지 않음.
- SIGMA_PROVENANCE_UNAVAILABLE: LoD2 형태별 수치의 상속 경로는 확인했으나 원 추정 과정의 참값 사용 여부는 확인 불가.
- 모든 후속 판단 계산·학습은 미실행. scientific_verdict: null.
''')
    print('PASS_STOP_EVIDENCE',[(v['site'],v['prior'],v.get('missing_sigma_count'),v.get('missing_normal_count')) for v in out],flush=True)


if __name__=='__main__':
    main()
