"""Stage A factual report, mandatory gate and expectation/value comparison only."""
import json
from common import *
from reduce_diagnostics import table

def read(name):return json.loads((DOC/'tables'/name).read_text())['rows']
def fmt(x):return '확인 불가' if x is None else f'{x:.4g}' if isinstance(x,float) else str(x)
def main():
    forces=sum([read(f'forces_{s}.json') for s in SITES],[]);grads=sum([read(f'gradients_{s}.json') for s in SITES],[])
    gauss=sum([read(f'gaussians_{s}_ALS.json') for s in SITES],[]);photos=sum([read(f'photo_{s}.json') for s in SITES],[])
    one=lambda rows,**kw:next(r for r in rows if all(r.get(k)==v for k,v in kw.items()))
    gates=[]
    for site in ['R1rep_b10','B173nb_b10']:
        res='lt_dynnow_ALS_s0';r=json.loads((OUT/'diagnostics'/site/res/'receipt.json').read_text())['gate_counts']
        g=one(gauss,site=site,result=res,case='전체',kind='floating');grad=one(grads,site=site,result=res,case='전체',kind='roof')
        gates.append(dict(site=site,gate1_floating_pixels=r['floating_pixels'],gate1_both_dead=r['all_own_dead'],
            gate1_fraction=r['all_own_dead_fraction'],gate1_threshold=.7,gate1_pass=r['all_own_dead_fraction']>=.7,
            gate2_densified_opacity_fraction=g['densified_opacity_fraction'],gate3_roof_depth_over_photo=grad['depth_over_photo'],
            gate3_below_10pct=grad['depth_over_photo']<.1 if grad['depth_over_photo'] is not None else None,scientific_verdict=None))
    save(DOC/'tables/gate.json',dict(rows=gates,gate1_status='PASS' if all(r['gate1_pass'] for r in gates) else 'FAIL',
        definition_unchanged=True,stage_B='NOT_RUN_USER_DECISION',scientific_verdict=None))
    table(DOC/'tables/gate_values',gates,'관문 · 정의 유지, 단계 나 실행 안 함')
    case_rows=[]
    for site in SITES:
        for c in json.loads((DOC/'보기'/f'A2_{site}.json').read_text())['cases']:
            for x in c['values']:
                row=dict(site=site,case=c['case'],result=x['result'],**{k:v for k,v in x['geometric'].items() if k not in ['case','result','source','source_sha256','domain','origin']})
                for prefix,key in [('gaussian','lineage'),('gradient','gradient'),('own_force','force_own'),('opposite_force','force_other'),('photo_floating','photo_floating'),('photo_roof','photo_roof')]:
                    for k,v in x[key].items():
                        if k not in ['site','case','result','source']:row[prefix+'_'+k]=v
                d=x['four_depth'];row['depth_comparison_status']=d['status'] if d else 'NOT_REQUESTED'
                for k in ['q25','median','q75','p90','n']:
                    row['surf_minus_mesh_'+k]=d['surf_minus_mesh'][k] if d and d['status']=='MEASURED' else None
                row['figure']=c['plate'];row['scientific_verdict']=None;case_rows.append(row)
    keys=list(dict.fromkeys(k for r in case_rows for k in r));case_rows=[{k:r.get(k) for k in keys} for r in case_rows]
    table(DOC/'tables/cases_complete',case_rows,'사례 일곱의 숫자 · 단위 전체 값은 각 사례 판과 원표 참조')
    compact=['site','case','result','within_tau_pct','floating_area_m2','floating_pct','gaussian_count','gaussian_densified_opacity_fraction','own_force_all_terms_dead_fraction','gradient_depth_over_photo','surf_minus_mesh_median','surf_minus_mesh_n']
    lines=['# 사례 숫자 요약','','전체 열·반올림 전 값·출처는 cases_complete.json과 CSV에 있다.','',
        '| '+' | '.join(compact)+' |','|'+'|'.join(['---']*len(compact))+'|']
    lines+=['| '+' | '.join(fmt(r.get(k)) for k in compact)+' |' for r in case_rows]
    (DOC/'tables/cases_complete.md').write_text('\n'.join(lines)+'\n')
    expect=[]
    for site in SITES:
        for res in ['lt_dyngt_ALS_s0','lt_dynnow_ALS_s0']:
            g=one(gauss,site=site,result=res,case='전체',kind='floating')
            f=one(forces,site=site,result=res,case='전체',kind='floating',loss='dynamic',term='prior')
            m=one(forces,site=site,result=res,case='전체',kind='floating',loss='current',term='mvs')
            grad=one(grads,site=site,result=res,case='전체',kind='roof')
            for no,rule,value,n,fig in [('가','밀도 제어 생성 비율 > 0.8',g['densified_opacity_fraction'],g['count'],{'B173nb_b10':'B173-뜬면-1','B0_b10':'B0-뜬면-1','R1rep_b10':'R1-뜬면-1'}[site]+'_plate_A2.jpg'),
                ('나','자기 깊이 항 모두 힘 없음 > 0.9',f['all_terms_dead_fraction'],f['group_pixels'],site+'_forces_A2.jpg'),
                ('다','마스크 유효 MVS 힘 0.05',m['force_median'],m['pixels'],site+'_forces_A2.jpg'),
                ('라','지붕 깊이/사진 기울기 > 0.1',grad['depth_over_photo'],grad['count'],site+'_gradients_A2_v2.jpg')]:
                expect.append(dict(expectation=no,site=site,result=res,case='전체',prewritten_rule=rule,value=value,n=n,figure='보기/img/'+fig,verdict=None))
    for p in [r for r in photos if r['case']!='전체' and r['kind']=='floating']:
        roof=one(photos,site=p['site'],result=p['result'],case=p['case'],kind='roof')
        ratio=p['colour_L1_mean']/roof['colour_L1_mean'] if p['colour_L1_mean'] is not None and roof['colour_L1_mean'] else None
        expect.append(dict(expectation='마',site=p['site'],result=p['result'],case=p['case'],prewritten_rule='뜬 면 / 둘레 색 오차 0.8~1.2',
            value=ratio,n=p['pixels'],figure='보기/img/'+p['case']+'_plate_A2.jpg',verdict=None))
    for r in read('formation_onsets.json'):
        expect.append(dict(expectation='바',site='R1rep_b10',result=r['result'],case=r['case'],prewritten_rule='3,000회 초기화 뒤 7,000회 안 발생; 당시 자료와 0.2 m 초과',
            value=r['earliest_observed_nonzero_iteration'],n=r['last_saved_iteration'],figure='보기/img/'+r['case']+'_formation_A2.jpg',verdict=None))
        for d in r['target_distances']:
            expect.append(dict(expectation='바·'+d['term'],site='R1rep_b10',result=r['result'],case=r['case'],prewritten_rule='처음 저장된 뜬 면 화소의 자료 법선 거리 중앙값 > 0.2 m',
                value=d['normal_abs_q25_q50_q75_q90'][1] if d['pixels'] else None,n=d['pixels'],figure='보기/img/'+r['case']+'_formation_A2.jpg',verdict=None))
    table(DOC/'tables/expectations',expect,'진단 전 기대와 측정값 · 판정하지 않음')
    replays=[]
    for res in ['fd_dynnow_ALS_s0','fd_current_ALS_s0','fd_current_ALS_s0_record_only']:
        rec=json.loads((OUT/'runs/R1rep_b10'/res/'receipt.json').read_text());replays.append(dict(result=res,**rec))
    for r in replays:assert r['status'] in ['PASS','STOP']
    replay_check=json.loads((DOC/'provenance/replay_results.json').read_text())
    lines=['한 일: 단계 가의 저장 모델 진단, 사례 일곱의 3차원 보기·완성 판, 조건부 재실행 두 건과 사용자 승인 재시도 한 건, 네 깊이·모든 학습 사진 확인을 냈다.',
        '관문: R1 11.6356%, B173 주변 30.5879%로 각각 70% 기준 미달. 정의를 유지하며 사용자 지시에 따라 단계 나는 실행하지 않았다.',
        '확인 불가: R1 보존 띠의 기준 통과 사진·실사 판독, 기존 모델의 생성 반복, 판정 끔의 생성 계보. scientific_verdict: null.','',
        '# 뜬 면 진단 보고 v1','',
        '모든 새 측정값은 [이 발주에서 냄]이다. 이 문서는 값과 출처를 기록하며 가설과 논문 주장을 판정하지 않는다. 좌표는 EPSG:25832에서 [690953, 5336071, 604] m를 뺀 값이다.','',
        '## 사례 판','',
        '![R1 뜬 면](보기/img/R1-뜬면-1_plate_A2.jpg)','',
        '![B173 날개](보기/img/B173-날개_plate_A2.jpg)','',
        '[인터넷 없이 여는 전체 보기](보기/index.html) · [일곱 사례 값](tables/cases_complete.md)','',
        '## 점검','',
        '- 부록 C의 34개 비율 비교가 모두 0.5 %p 기준 안이다. 최대 차이는 2.84×10⁻¹⁴ %p이다.',
        '- 9개 모델의 모든 학습·평가 사진 PSNR이 원래 기록과 동일하다. 최대 차이 0 dB이다.',
        '- 기존 손실·다이내믹 손실의 진단 어댑터를 r17과 비교해 손실과 기울기 일치를 확인했다. 관문 값은 별도 float64 계산으로도 확인했다.',
        '- r18·단계 나 학습은 실행하지 않았다. 해당 동작·고친 손실 식 점검은 적용 대상이 아니다.',
        '- 설정·출처·검증 기록은 provenance와 전달 묶음의 configs 폴더에 있다.','',
        '## 다섯 구분','',
        '[반올림 전 전체 표](tables/recount_ALS.json) · [표](tables/recount_ALS.md). 분모는 칸별 채점 허용 패치 넓이이다. 사례 범위는 서로 겹치므로 합산하지 않는다.','']
    for site in SITES:
        lines += [f'![{site} 다섯 구분](보기/img/{site}_classes_A2.jpg)','',f'## {site} 진단','',
            f'[힘과 r/σ](tables/forces_{site}.md) · [기울기](tables/gradients_{site}.md) · [가우시안·계보](tables/gaussians_{site}_ALS.md) · [사진](tables/photo_{site}.md)',
            f'![힘](보기/img/{site}_forces_A2.jpg)',f'![기울기](보기/img/{site}_gradients_A2_v2.jpg)','']
    lines += ['## 네 깊이의 비교','',
        '① 학습 손실의 `surf_depth`, ② 같은 화소 광선과 원래 결과 메시의 첫 교차 깊이, ③ 렌더러의 누적 불투명도가 0.5에 닿은 깊이, ④ 불투명도 가중 평균을 같은 화소에서 구했다. 깊이는 카메라 Z의 m 단위다.',
        '메시를 만들 때 넣은 값은 **①이며, 이 실행에서는 ④와 정확히 같다.** 기본 `depth_ratio=0.0`이고 원래 학습 명령과 후처리 로더에 이를 바꾸는 설정이 없다. `GaussianExtractor.reconstruction`은 `render_pkg["surf_depth"]`를 읽어 TSDF에 넣는다. r14·r15·r17의 관련 렌더·인자·메시 코드도 같은 바이트다.',
        '③은 원래 렌더러의 기여 순서로 누적한다. 최종 불투명도가 0.5 미만이면 미도달이다. 메시와 만나지 않은 광선은 미교차이다. 이 둘은 0으로 채우지 않는다. ②는 줄이지 않은 원래 채점 메시 전체를 사용하여 사례 밖 물체의 가림도 포함한다.',
        '추가 표의 화소는 판 4의 뜬 면 패치에서 잠갔다. 판정 끔에도 같은 화소를 사용한다. 단위 표의 분모는 선택된 고유 주 시점의 화소이며, 모든 학습 시점의 관문 분모와 다르다. 사례 판 (사)에 ①−②의 Q25·중앙값·Q75·P90과 유효 쌍 수를 적었다.',
        '[코드·명령·실행 근거](provenance/mesh_depth_source.json) · [실제로 저장된 TSDF 입력 깊이 비교](provenance/actual_tsdf_depth_comparison.json)','']
    for site in SITES:lines.append(f'- [{site} 네 깊이](tables/four_depths_{site}_ALS.md)')
    lines+=['','## 사진마다 보는 추가 확인','',
        '사용자가 고른 ① 방식이다. 각 결과 자신의 뜬 면 패치의 저장된 첫 만남 점(패치 중심 + z×법선)을 모든 학습 사진에 투영한 가장 가까운 한 화소에서 사진 수를 센다. 화면 안 사진을 가림·불투명도로 미리 제외하지 않는다. surf_depth를 세계 좌표로 되돌려 해당 참값 패치 평면에 대한 부호 있는 법선 거리로 비교한다. |거리|≤τ는 지붕, 거리>τ는 뜬 면, 나머지는 그 밖이다. 깊이 0·비유한은 별도 결측이다.',
        '힘 비율은 대표 화소가 아닌 **기존 관문과 같은 전체 학습 패치 화소**에서 구한다. 각 결과 자신의 뜬 면 패치 화소 중 surf_depth가 참값+τ보다 위인 화소만 남기고, 그 판 자신의 깊이 항 모두가 힘 없는 비율을 센다. 사진별 고유 화소를 한 번씩 센다. 기존 관문의 정확한 힘 없음 표지를 재사용했으며 원래 관문 분모와 계산 결과는 보존했다.',
        '사진 예시는 결과·사례·구분마다 해당 대표 패치 수가 많은 순서, 파일명 순으로 최대 세 장을 고른다. 전체 통계에는 고르지 않은 사진도 모두 들어간다. 사례 범위는 기존 경계 상자+3 m이다. 이 분류는 그 광선의 렌더가 해당 패치 평면 위에 있는지를 뜻하며, 같은 물리적 표면을 실제 사진에서 확인했다는 뜻은 아니다.','']
    for site in SITES:
        for r in read(f'multiview_summary_{site}_ALS.json'):
            if r['case']=='전체':lines.append(f"- {site} {r['result']}: 뜬 면 패치 {r['patches']:,}, 한 장 이상 본 패치 넓이 {100*r['at_least_one_float_photo_area_fraction']:.4f}%, 그 화소의 힘 없음 {r['all_own_dead']:,}/{r['float_observed_pixels']:,}={100*r['own_all_dead_fraction']:.4f}%.")
        lines.append(f'[패치 분포와 넓이·힘](tables/multiview_summary_{site}_ALS.md) · [사진 수 분포](tables/multiview_histogram_{site}_ALS.md) · [모든 사진](tables/multiview_views_{site}_ALS.csv)')
    for c in json.loads((CFG/'cases_ALS.json').read_text())['cases']:
        lines.append(f"- {c['id']}: [사진 수 지도](보기/img/{c['id']}_multiview_map_A2.jpg) · [색·깊이 예시 줄](보기/img/{c['id']}_multiview_examples_A2.jpg)")
    lines+=['','## TSDF가 갱신하는 칸','',
        '실제 후처리의 Open3D 0.19.0 ScalableTSDFVolume은 현재 사진의 stride-4 깊이 점 ±절단 거리(0.25 m)가 닿는 블록만 그 사진으로 갱신한다. 블록 길이는 0.8 m(복셀 0.05 m×16)다. **이전 사진에서 이미 열렸어도 현재 사진의 이 목록에 없는 블록은 갱신하지 않는다.** 광선 앞의 모든 빈 공간을 훑는 방식이 아니다. 같은 블록 안에서는 사진 깊이 앞쪽 복셀이 양의 TSDF를 받을 수 있고, sdf≤−절단 거리인 뒤쪽 복셀은 갱신하지 않는다.',
        '실제 이미지와 같은 Open3D 런타임으로 작은 평면 시험을 했다. 2 m를 넣은 뒤 4 m를 넣자 앞쪽 6,588개 TSDF 표본이 정확히 같았다. 2.1 m처럼 블록이 겹치는 깊이는 값을 바꿨다. 조밀한 블록 대조 시험은 3,328개 기존 복셀의 가중치가 1씩 늘어, 블록을 갱신 대상으로 제출했을 때와의 차이를 확인했다. Scalable API의 관찰값은 영점 주변 TSDF이며 전체 가중치는 직접 노출되지 않는 한계도 기록했다.',
        '[Open3D ScalableTSDFVolume 원문](https://github.com/isl-org/Open3D/blob/v0.19.0/cpp/open3d/pipelines/integration/ScalableTSDFVolume.cpp) · [블록 내부 적분 원문](https://github.com/isl-org/Open3D/blob/v0.19.0/cpp/open3d/pipelines/integration/UniformTSDFVolume.cpp) · [실행 시험과 코드 해시](provenance/tsdf_update_behavior.json). 이 동작 확인만으로 각 뜬 면의 원인을 판정하지 않는다.','']
    lines+=['','## 생기는 과정','',
        '기존 저장본은 15,000회와 30,000회였다. 판 2·판 4에 1,000~7,000회 저장본이 없어 발주문 4.7의 두 재실행을 했다. r17, 씨앗 0, 원래 초기화·보호·밀도 제어·λ를 유지했다. 첫 두 실행은 원래 건강 기준을 유지했고, 기존 손실 재시도만 아래 승인한 예외를 적용했다. 500회마다 저장하며 생성 반복 관찰 기록을 더했다.',
        '앞 반복의 뜬 면은 주 시점 렌더 점이 해당 패치의 참값 평면보다 τ 넘게 위인 화소다. 가우시안 구분에는 패치별 렌더 높이 중앙값을 쓴다. 이 화소 비율은 TSDF의 면적 점수가 아니다. 저장 반복 사이의 발생 시각은 확인할 수 없고, 짧은 재실행은 30,000회 결과와 같다고 가정하지 않는다.','']
    for r in replays:lines.append(f"- {r['result']}: {r['status']}, {r['seconds']:.1f}초, 종료 코드 {r['exit_code']}, 건강 중단 사유 {r['health_reason']}.")
    for c in ['R1-뜬면-1','R1-뜬면-2']:lines += ['',f'![생기는 과정](보기/img/{c}_formation_A2.jpg)',f'![깊이 띠](보기/img/{c}_formation_depth_A2.jpg)',f'![가우시안 생성 과정](보기/img/{c}_formation_population_A2.jpg)']
    lines += ['','[각 저장 반복의 자료까지 거리와 20 cm 초과 비율](tables/formation_target_distances.md). 시선 Z 거리와 실제 법선 거리를 함께 냈다. 처음 저장된 비영 화소는 정확한 생성 시각이 아니며, 기대 바의 판정은 하지 않았다.','',
        '## 바꾼 것','',
        '기존 손실 fd_current_ALS_s0는 3,100회에 전체 불투명도 중앙값 0.03778748959302902로 원래 0.05 건강 기준에 걸렸다. 이 실행의 기록과 500~3,000회 저장본을 그대로 보존했다. 이후 사용자가 명시적으로 한 번의 재시도를 승인했다. fd_current_ALS_s0_record_only에서는 유한한 전체 불투명도 중앙값이 낮다는 조건만 기록 전용으로 바꿨다. NaN·실행 오류와 다른 원래 검사(PSNR 포함)는 유지했다.',
        '변경 이유는 “생기는 과정 비교 구간 3,000~7,000회 확보, 같은 손실의 원래 학습은 30,000회 정상 완료”다. 재시도에서도 3,100회 전후 값을 floatdiag_opacity_record_only.jsonl에 기록했다. 손실·λ·초기화·보호·밀도 제어·원래 r17 파일은 바꾸지 않았다. 재시도는 진단용이며 메시 채점을 하지 않았다. [승인·정책 검증](provenance/current_retry_policy_check.json).','']
    for event in replay_check['retry_opacity_events_around_reset']:
        if event['iteration'] in [3100,6100]:lines.append(f"- 재시도 {event['iteration']:,}회 전체 불투명도 중앙값: {event['whole_opacity_median']}; 원래 중단 조건: {event['original_stop']}.")
    lines += [f"- 재시도에서 불투명도 중단 조건을 기록만 하고 통과시킨 호출 수: {replay_check['record_only_trigger_calls']}. 정책 설정과 실제 발동 여부를 구분한다.",
        '같은 씨앗 0에서도 두 기존 손실 실행의 500회 저장본부터 바이트 차이가 있다. 바뀐 불투명도 중단 규칙이 적용될 수 있는 시점보다 앞이다. 수치 경로가 달라진 원인은 이번 발주에서 확정하지 않았다. 따라서 중단본과 재시도를 같은 궤적의 연속 또는 정책 효과의 통제 비교로 해석하지 않는다. [저장본·초기 배열·건강 기록 대조](provenance/replay_results.json).','']
    lines+=['','## R1 보존 띠','',
        '잠근 90%·50% 가시성 기준을 통과하는 주 시점과 빗각 시점이 없다. 최대 보이는 넓이는 1.7223%다. 난간·차양·식생 등 구조물 종류는 확인 불가로 둔다. 메시·참값·사전·MVS·가우시안은 같은 사례 범위로 제공한다.',
        '![R1 보존 띠](보기/img/R1-보존띠-1_plate_A2.jpg)','',
        '## 관문과 진단 전 기대','',
        '[관문 기록](tables/gate_values.md) · [기대와 값](tables/expectations.md). 관문 2·3은 기록만 한다. 가설의 성립 여부는 판정하지 않았다.','']
    for g in gates:
        lines.append(f"- {g['site']}: 관문 1 {g['gate1_both_dead']:,}/{g['gate1_floating_pixels']:,}={100*g['gate1_fraction']:.4f}%, 계보 {fmt(g['gate2_densified_opacity_fraction'])}, 지붕 깊이/사진 기울기 {fmt(g['gate3_roof_depth_over_photo'])}.")
        if g['gate3_below_10pct']:lines.append('  **깊이/사진 기울기 비가 10% 아래다.**')
    lines+=['','고친 판의 8.6 표는 실행하지 않아 해당 없음이다. 추가 실험은 사용자에게 단계 가 결과를 전달한 뒤 새 발주로 정한다.','',
        '## 변경·확인 불가·전달','',
        '단면의 표시 높이는 이미 잠근 3차원 자르기 높이에 맞췄다. 범위 밖 점 수는 그림 JSON에 남겼고 원래 배열과 수치는 보존했다. 원자료·기존 결과·기존 학습 코드는 고치지 않았다. 새 측정과 렌더만 이 발주 폴더에 썼다. 초기 스크립트 오류와 보기용 메시 크기 조정 등은 [문제 기록](issues.md)에 남겼다. 보기용 메시만 줄였으며 모든 메시 캡처·광선 교차·채점에는 줄이지 않은 면을 썼다.',
        '기존 모델의 생성 반복은 기록 없음이다. 판정 끔의 origin·init_id는 생성 여부를 판별하지 못하므로 계보를 추정하지 않았다. 생성 시각을 기록한 재실행과 기존 모델을 구분한다. 패치 100개 미만은 표본 부족으로 표시했다.',
        '묶음 ①을 먼저 전달하고 묶음 ②를 마무리했다. 각 ZIP의 CRC와 모든 파일 SHA-256을 다시 읽어 확인한다. 원래 자른 PLY와 화소·가우시안 배열은 외부 산출물에 보관하며 전달 목록에서 정확한 경로와 해시를 제공한다.','']
    frozen=json.loads((CFG/'floatdiag_v1.lock.json').read_text())['frozen_at'];ended=now()
    elapsed=(datetime.fromisoformat(ended)-datetime.fromisoformat(frozen)).total_seconds()
    lines+=['','## 걸린 시간','',f'설정 잠금 {frozen}, 이 보고서 표 생성 {ended}. 그 사이 {elapsed/3600:.2f}시간(계산·대기·검증 포함). 재실행별 실제 초는 위 실행 기록에 적었다. ZIP 검증과 전달 시각은 전달 명세에 별도로 남긴다.','']
    text='\n'.join(lines);assert len(text)<20000
    (DOC/'뜬면진단_보고_v1.md').write_text(text+'\n')
    print('final tables and report built',len(text),'characters',flush=True)

if __name__=='__main__':main()
