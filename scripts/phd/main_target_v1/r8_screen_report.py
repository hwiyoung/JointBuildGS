"""Factual tables/figures from locked read-only measurements; no causal verdict."""
import csv,shutil
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager,colors
from common import *
ROOT=OUT/'r8_screen_prune';D=DOC/'screen_prune_r8_lod2';F=D/'figures';T=D/'tables'
HOST=Path('/media/innopam/InnoPAM-8TB/hwiyoung/code');R=HOST/'JointBuildGS-exp';A=HOST/'JointBuildGS-artifacts';O=A/'phase-payloads/phd/main_target_v1/PHD-MAIN-TARGET-v1'
LABELS={'base_LoD2_30000':'기준선 LoD2 30,000','r7_LoD2_30000':'r7 LoD2 30,000','r8_ALS_30000':'r8 항공 LiDAR 30,000','r8_LoD2_stop':'r8 LoD2 중단 (14,030 완료)'}
NAMES={'baseline_ALS':'기준선 항공 LiDAR (r15)','baseline_LoD2':'기준선 LoD2 (r15)','image_only_2DGS':'2DGS 영상만','GeoGS_ALS':'GeoGS 항공 LiDAR','GeoGS_LoD2':'GeoGS LoD2','r22_r8':'본 방법 r8 (r22)','original_2DGS':'원래 2DGS (참조)','CDGS_prepared_only':'CDGS (학습 없음)'}
def read(p):return json.loads(Path(p).read_text())
def rows(n):return read(ROOT/(n+'.json'))['rows']
def host(p):
 p=str(p)
 for prefix,base in [('/repo',R),('/docs',R/'docs/experiments/phd/main_target_v1'),('/cfg',R/'configs/phd/main_target_v1'),('/out',O),('/ph',A/'phase-payloads/phd'),('/art',A)]:
  if p.startswith(prefix+'/'):return str(base/p[len(prefix)+1:])
 return p
def link(p,line=None,label=None):return f'[{label or Path(p).name}]({host(p)}'+(f':{line}' if line else '')+')'
def table(header,data):return ['| '+' | '.join(header)+' |','|'+'|'.join(['---']*len(header))+'|']+['| '+' | '.join(map(str,r))+' |' for r in data]
def save(fig,name,data,caption):
 fig.savefig(F/(name+'.png'),dpi=180,bbox_inches='tight');fig.savefig(F/(name+'.pdf'),bbox_inches='tight');plt.close(fig);dump(F/(name+'.json'),dict(at=stamp(),caption=caption,data=data,scientific_verdict=None))
def main():
 assert read(ROOT/'verification.json')['status']=='PASS_WITH_PRE_RADIUS_NOT_SAVED';F.mkdir(parents=True,exist_ok=True);T.mkdir(exist_ok=True)
 for font in Path('/fonts').glob('*Sans*CJK*Regular*.ttc'):font_manager.fontManager.addfont(str(font));plt.rcParams['font.family']=font_manager.FontProperties(fname=str(font)).get_name();break
 plt.rcParams.update({'font.size':10,'axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False,'figure.facecolor':'white'})
 for p in ROOT.iterdir():
  if p.suffix in ['.csv','.json'] and 'command' not in p.name:shutil.copy2(p,T/p.name)
 c=read(CFG/'r8_screen.json');rules=rows('rules');ext={r['implementation']:r for r in rows('source_extents')};th=rows('screen_thresholds');pre=[r for r in th if r['group']=='per_state_top1'];cams=rows('camera_distance');near=rows('camera_near_gaussians');top=rows('camera_near_top10');b=read(c['boundaries']);uv=np.array([[b['lo'][0],b['lo'][1]],[b['hi'][0],b['lo'][1]],[b['hi'][0],b['hi'][1]],[b['lo'][0],b['hi'][1]],[b['lo'][0],b['lo'][1]]]);poly=uv@np.array(b['basis']);centers=np.array([[r['x'],r['y']] for r in cams]);distance=np.array([r['eval_box_xy_distance_m'] for r in cams]);settings=read(ROOT/'settings.json');alpha=read(ROOT/'alpha_measure.json');black=read(ROOT/'black_render.json')
 # Rule table: configured branch versus actual order are distinct columns.
 fig,ax=plt.subplots(figsize=(14,4.8));ax.axis('off');cells=[]
 for r in rules:cells.append([NAMES[r['implementation']],'3,100~14,900','20 px',f'{ext[r["implementation"]]["world_size_threshold_m"]:.3f} m' if r['implementation'] in ext else '실행 없음',f'{r["min_opacity"]:g}','검사 전 0 초기화',str(r['postfix_reset_line'])+' → '+str(r['screen_test_line'])])
 tb=ax.table(cellText=cells,colLabels=['구현','크기 검사 반복','화면 문턱','장면 크기 문턱','불투명도','화면 기록 처리','모델 코드 줄'],loc='center',cellLoc='center',colWidths=[.21,.15,.08,.13,.09,.17,.15]);tb.auto_set_font_size(False);tb.set_fontsize(10);tb.scale(1,1.8);ax.set_title('밀도 제어 정리 규칙 — 설정과 실행 순서\nCDGS는 준비 코드만 확인, 원래 2DGS는 고정 소스 참조',pad=12);save(fig,'rule_comparison',rules,'실행 여부·보호 예외·원본 줄은 규칙 표와 JSON 참조. 크기 검사 주기는 100회.')
 fig,axes=plt.subplots(1,2,figsize=(13,5.5));sc=axes[0].scatter(centers[:,0],centers[:,1],c=distance,cmap='viridis',s=28);axes[0].plot(poly[:,0],poly[:,1],c='#d73027',lw=2,label='평가 상자');axes[0].set_aspect('equal');axes[0].set(xlabel='지역 X (m)',ylabel='지역 Y (m)',title='학습 카메라 203장 / 평가 상자');axes[0].legend();fig.colorbar(sc,ax=axes[0],label='평가 상자까지 XY 거리 (m)')
 axes[1].hist(distance,bins=np.r_[np.arange(0,301,25),max(325,float(distance.max())+1)],color='#4477aa',edgecolor='white');axes[1].set(xlabel='평가 상자까지 XY 거리 (m)',ylabel='카메라 수',title='중첩 누계: >50 m 104 / >100 m 65 / >200 m 41');save(fig,'camera_distance',dict(cameras=cams,polygon=poly.tolist(),counts=settings['counts_farther']),'평가 상자 안 거리는 0. 세 초과 수는 중첩 누계다. EPSG:25832의 기존 지역 좌표 사용.')
 maximum=max(r['gaussians_within30m'] for r in near);fig,axes=plt.subplots(2,2,figsize=(12,10),sharex=True,sharey=True);norm=colors.Normalize(0,maximum)
 for ax,key in zip(axes.ravel(),LABELS):
  cc={r['camera']:r['gaussians_within30m'] for r in near if r['state']==key};sc=ax.scatter(centers[:,0],centers[:,1],c=[cc[r['camera']] for r in cams],norm=norm,cmap='magma',s=35);ax.plot(poly[:,0],poly[:,1],c='#20b2aa',lw=1.5);ax.set_aspect('equal');ax.set_title(LABELS[key]);ax.set(xlabel='지역 X (m)',ylabel='지역 Y (m)')
 fig.subplots_adjust(right=.88,wspace=.22,hspace=.25);fig.colorbar(sc,cax=fig.add_axes([.91,.15,.02,.7]),label='카메라 중심에서 3차원 거리 ≤30 m 가우시안 수');save(fig,'camera_near_counts',dict(rows=near,polygon=poly.tolist(),color_limits=[0,maximum]),'4개 상태의 같은 203개 카메라, 같은 색 범위. 중복 구에 속하는 가우시안은 카메라마다 센다.')
 cc=rows('camera_counts_100');names=list(dict.fromkeys(r['camera'] for r in cc));starts=sorted(set(r['start_exclusive'] for r in cc));matrix=np.array([[next(r['chosen_count'] for r in cc if r['camera']==n and r['start_exclusive']==s) for s in starts] for n in names]);fig,ax=plt.subplots(figsize=(15,3.4));im=ax.imshow(matrix,aspect='auto',interpolation='nearest',cmap='Blues',vmin=0,vmax=max(2,int(matrix.max())));ax.set_yticks(range(3),[n.split('_')[-2] for n in names]);ticks=list(range(0,len(starts),5));ax.set_xticks(ticks,[f'{starts[i]+1:,}' for i in ticks],rotation=45,ha='right');ax.set(xlabel='구간 첫 반복 (각 100회, 마지막만 14,001~14,030)',ylabel='영상 번호',title='저장 난수·영상 목록으로 재생하고 다음 체크포인트에 대조한 선택 횟수');fig.colorbar(im,ax=ax,label='선택 횟수',ticks=range(int(matrix.max())+1));save(fig,'camera_selection_100',dict(rows=cc,replay=read(ROOT/'camera_replay_verification.json')),'14,031회 시도는 포함하지 않는다. 해당 영상 미선택과 전체 max_radii2D=0은 같은 뜻이 아니다.')
 fig,axes=plt.subplots(1,3,figsize=(15,4.4));its=[r['iteration'] for r in pre];axes[0].plot(its,[r['current_0020_radius_median'] for r in pre],marker='o',label='0020 재렌더 중앙값');axes[0].axhline(20,c='red',ls='--',label='20 px');axes[0].set_yscale('log');axes[0].set(ylabel='화면 반지름 (px)',title='현재 저장 모델의 0020 반지름');axes[0].legend();axes[1].plot(its,[r['size_median_m'] for r in pre],marker='o',label='상위 1% 중앙값');axes[1].axhline(settings['world_size_threshold_m'],c='red',ls='--',label='27.235 m');axes[1].set(ylabel='긴 축 (m)',title='장면 크기 문턱과 긴 축');axes[1].legend();axes[2].plot(its[:-1],[r['world_above'] for r in pre[:-1]],marker='o',label='문턱 초과');axes[2].plot(its[:-1],[r['world_above_parent_survivors'] for r in pre[:-1]],marker='s',label='그중 직후 원행 생존');axes[2].set(ylabel='가우시안 수',title='장면 크기 문턱 초과와 원행 생존');axes[2].legend()
 for ax in axes:ax.set_xlabel('반복');ax.ticklabel_format(axis='x',style='plain')
 for j,field in [(0,'current_0020_radius_median'),(1,'size_median_m')]:
  axes[j].plot(its[-1],pre[-1][field],marker='*',color='#cc3311',ms=12);axes[j].annotate('중단 상태',xy=(its[-1],pre[-1][field]),xytext=(-5,25),textcoords='offset points',ha='right',color='#cc3311')
 save(fig,'size_thresholds',pre,'직전 저장 max_radii2D는 없음. 재렌더 반지름은 해당 기록을 대신하지 않는다. 직후 생존은 원행 유지 수이며 분할 자손 수가 아니다.')
 z=dict(np.load(ROOT/'top1_depth_alpha.npz'));con=dict(np.load(ROOT/'alpha_replay.npz'));fig,axes=plt.subplots(1,3,figsize=(14,4.4));axes[0].hist(z['center_depth'],bins=np.geomspace(.2,80,40),color='#4477aa');axes[0].set_xscale('log');axes[0].axvline(.2,c='red',ls='--');axes[0].set(xlabel='카메라 좌표 중심 Z (m)',ylabel='가우시안 수',title='상위 1% 중심 깊이');axes[1].bar(['0','0 초과'],[alpha['zero_max'],alpha['nonzero_max']],color=['#999999','#cc6677']);axes[1].set_yscale('log');axes[1].set(ylabel='가우시안 수 (로그)',title='최대 알파 기여: 35,048 / 1');axes[2].hist(con['max_alphaT'],bins=[0,1e-8,.001,.003,.006],color='#cc6677',edgecolor='white');axes[2].set_yscale('log');axes[2].set(xlabel='화소별 alpha × T의 가우시안별 최댓값',ylabel='가우시안 수 (로그)',title='최대 0.00535042 / 중앙값 0');save(fig,'depth_alpha',dict(center_depth=black['center_depth_m'],alpha=alpha,near_m=.2,behind=black['center_behind_or_on_camera'],inside_near=black['center_front_inside_near']),'전체 장면에서의 실제 합성 기여. 원래 forward와 최대 절대 오차 2.24e-7로 대조했다.')
 # Report contains observations and code order, not an experiment verdict.
 notes=['# r8 LoD2 화면 크기 정리 규칙 확인','',f'작성: {stamp()} · `scientific_verdict: null` · 추가 학습 0회 · 학습 소스 변경 없음.','',
 '[이 발주에서 냄] 아래 추가 집계·검산·그림은 이번 읽기 전용 점검에서 냈다. 저장 상태와 실제 실행 소스를 읽었다. r8 LoD2는 14,030회 완료 / 14,031회 렌더 직전 중단 상태로 보존했다. 아래는 코드의 실행 순서와 측정값이다. 결론·과학적 해석은 작성하지 않았다.','',
 '## 1. 정리 규칙과 실제 코드','',
 'r22는 화면 반지름 `>20 px`, 긴 축 `>0.1 × cameras_extent`, 불투명도 `<0.05`를 정리 조건으로 둔다. 밀도 제어는 600~14,900회, 100회마다다. 화면·장면 크기 분기는 `iteration > 3000`이라 3,100회부터 켜진다. 3,000회 자체에는 크기 분기가 꺼져 있으며 이후 불투명도 초기화 주기마다 다시 꺼지는 규칙은 아니다.','',
 f'저장된 `cameras_extent`는 **{settings["cameras_extent_m"]:.12f} m**, 장면 크기 문턱은 **{settings["world_size_threshold_m"]:.12f} m**다. 학습 카메라 중심의 평균으로부터 최대 거리 ×1.1이며, 평가 상자의 크기가 아니다. 실제 실행 6개 줄의 카메라 중심과 범위가 같음을 확인했다. 원래 2DGS 참조·미실행 CDGS에는 실행 범위를 만들어 넣지 않았다.','',
 '화면 반지름은 학습 영상에서 보이는 행에 대해 최댓값으로 쌓는다. 하지만 `densify_and_prune`는 **복제 → 분할 → 화면 크기 비교** 순서이고, 복제·분할의 `densification_postfix`가 각각 **모든 행의 `max_radii2D`를 0으로 만든다**. 자식이 0개일 때도 이 함수 호출은 생략되지 않는다. 이 경로의 화면 비교는 0이 된 기록을 읽는다. 장면 크기·불투명도 비교는 별도 값으로 수행한다.','']
 notes+=table(['구현 / 실제 실행','화면 / 켜지는 반복','장면 문턱 m','불투명도','초기화 → 화면 비교 코드 줄'],[[NAMES[r['implementation']]+(' / 실행' if r['execution']=='EXECUTED' else ' / 참조만' if r['execution']=='NOT_EXECUTED_REFERENCE' else ' / 준비 중단'),'20 px / 3,100~14,900',f'{ext[r["implementation"]]["world_size_threshold_m"]:.6f}' if r['implementation'] in ext else '실행 없음',str(r['min_opacity']),link(r['source']+'/scene/gaussian_model.py',r['postfix_reset_line'],str(r['postfix_reset_line']))+' → '+link(r['source']+'/scene/gaussian_model.py',r['screen_test_line'],str(r['screen_test_line']))] for r in rules])
 notes+=['','원래 2DGS는 로컬 고정 커밋 `f3e3b9fa67bbd1c75e05167ff37391d8dab2a678`의 [공식 소스](https://github.com/hbb1/2d-gaussian-splatting/blob/f3e3b9fa67bbd1c75e05167ff37391d8dab2a678/scene/gaussian_model.py#L390)를 확인했다. CDGS의 불투명도 문턱은 호출부의 0.005이며 실행된 결과로 취급하지 않았다.','',
 'r22의 줄별 근거: '+link('/repo/src/phd/forks/GeoGS-conf-guided-v1-r22/train.py',1173,'화면 반지름 누적')+', '+link('/repo/src/phd/forks/GeoGS-conf-guided-v1-r22/train.py',1179,'20 px와 호출')+', '+link('/repo/src/phd/forks/GeoGS-conf-guided-v1-r22/scene/gaussian_model.py',521,'복제·분할 먼저 호출')+', '+link('/repo/src/phd/forks/GeoGS-conf-guided-v1-r22/scene/gaussian_model.py',446,'반지름 0 초기화')+', '+link('/repo/src/phd/forks/GeoGS-conf-guided-v1-r22/scene/gaussian_model.py',524,'불투명도·화면·장면 정리')+', '+link('/repo/src/phd/forks/GeoGS-conf-guided-v1-r22/scene/dataset_readers.py',271,'장면 범위 계산')+'.','',
 '최초 생성 때는 `gaussian_model.py:159` 및 목표 초기화 코드에서 0을 둔다. 완전 상태 복구 때 저장 반지름을 읽고(`gaussian_model.py:98`), 행 삭제 때는 남은 행으로 좁힌다(`:386`). 불투명도 되돌리기 함수(`:244`) 자체는 반지름을 비우지 않는다. 밀도 제어가 끝나는 15,000회 이후에는 이 누적 분기도 수행되지 않는다. 각 구현의 누적·초기화·검사 줄 전부는 `rule_evidence.json`에 있다.','',
 '## 2. 출신별 적용과 보호 마스크','']
 notes+=table(['구현','적용 / 예외'],[[NAMES[r['implementation']],r['exemption']] for r in rules])
 notes+=['','r8 저장 상태 8,000~14,000회 직후 7개와 중단 상태의 `frozen_mask`는 모두 0이다. 배경·패치·풀림마다 정리 문턱을 달리 적용하는 분기는 없다. 기준선은 실제 실행 인자에서 `judgment=0`, `protection=1`이었다. 기준선 30,000회의 보호 행은 항공 LiDAR 20,992개, LoD2 41,204개다. GeoGS는 8,000회 이후 건물 보호 행을 제외하며, `freeze_onlybldg` 분기로 나머지 밀도 제어는 계속된다.','',
 '## 3. 0020 상위 1%와 저장 상태','',
 '상위 1%는 매 저장 상태의 전체 행 수를 분모로 `ceil(0.01 × N)`개를, 0020 타일 겹침 내림차순·행 번호 오름차순으로 선택했다. 중단 상태의 상위 1%와 같은 처음 씨앗 5개를 공유하는 모든 자손도 별도 줄로 냈다. 저장된 직접 부모 ID가 없으므로 과거 상태의 정확한 부모 계보를 추정하지 않았다.','',
 '**8,000~14,000회 밀도 제어 직전에는 `max_radii2D`가 저장되지 않았다.** 직전 PLY·목표 스냅숏·기울기 NPZ 모두 해당 필드가 없다. 아래 ‘없음’은 0이 아니다. 직후 완전 상태 7개에는 값이 있으며 전부 0이었다. 현재 저장 모델을 0020으로 다시 그린 반지름을 별도 참고 열에 두었다.','']
 notes+=table(['반복 / 시점','상위 1% 수','직전 저장 max 반지름','0020 재렌더 중앙값 px','긴 축 중앙값 m / 문턱 비','장면 문턱 초과','그중 직후 원행 생존'],[[f'{r["iteration"]:,}'+(' 직전' if r['population']=='pre_density' else ' 중단'),f'{r["n"]:,}','없음' if r['saved_max_radii_above20'] is None else f'20 px 초과 {r["saved_max_radii_above20"]:,}',f'{r["current_0020_radius_median"]:,.0f}',f'{r["size_median_m"]:.4f} / {r["size_ratio_median"]:.4f}',r['world_above'],'다음 상태 없음' if r['world_above_parent_survivors'] is None else r['world_above_parent_survivors']] for r in pre])
 notes+=['','원행 생존은 같은 반복의 **직전 → 직후**를 비교했다. 저장 기울기·크기·불투명도와 원래 분할/정리 조건으로 남는 원행의 순서를 만들고, 직후 행 앞부분의 `init_id`를 전부 대조했다. 배경·풀림의 XYZ·원시 크기도 바이트 단위로 같았다. 패치 행은 목표 재투영이 있으므로 XYZ 동일성으로 검사하지 않았다. 분할된 부모는 원행 생존에 포함하지 않으며 자손 생존으로 바꿔 세지 않았다.','',
 '저장된 화면 기록을 기준으로 ‘20 px 초과 및 생존’인 수는 직전 값이 없어서 확인 불가다. 재렌더 반지름 >20인 원행의 직후 생존 수는 8,000회부터 차례로 13,281 / 17,303 / 13,324 / 18,319 / 25,506 / 19,775 / 32,385개다. 이 값은 과거 학습에서 쌓인 최대 반지름의 대체값이 아니다.','',
 '14,001~14,030회 구간에서 0019·0020·0043의 선택 횟수는 각각 0회다. 중단 상태는 그 30회 동안 쌓인 화면 기록을 보존했다. 상위 1%의 저장 반지름 중앙값 44 px, 20 px 초과 30,151개, 최댓값 34,204,976 px다. 14,031회 시도의 0020 반지름은 이 저장 기록에 포함되지 않는다. 다음 학습 상태는 없다.','',
 '## 4. 100회 구간 영상 선택','',
 '7,001~14,030회 영상 순서는 저장된 Python 난수 상태·남은 영상 목록·203장 순서로 재생했다. 각 1,000회 체크포인트와 마지막 중단 상태에서 다음 난수 상태와 남은 목록이 정확히 같았고, 100회마다 저장된 실제 영상 이름 70개도 모두 같았다. 학습을 재실행한 값이 아니다.','',
 '각 100회 구간의 0019·0020·0043 선택 횟수 전체는 '+link(str(T/'camera_counts_100.csv'))+'와 같은 이름 JSON에 있다. 마지막 14,001~14,030은 30회 부분 구간이다.','',
 '해당 영상이 뽑히지 않은 구간에는 그 영상에서 나온 반지름으로 누적하지 않는다. 다른 학습 영상도 같은 가우시안의 반지름을 갱신할 수 있다. 따라서 세 영상의 미선택만으로 그 무리의 저장 반지름이 0이라고 판단할 수 없다. 100회 직전의 반지름 배열이 없어 구간별 직접 대조는 확인 불가다.','',
 '## 5. 카메라 배치와 30 m 안 가우시안','',
 '카메라 203장 중 평가 상자에서 XY 거리 50 m 초과 104장, 100 m 초과 65장, 200 m 초과 41장이다. 세 수는 중첩 누계다. 카메라 둘레 가우시안 수는 각 중심에서 **3차원 거리 30 m 이하**로 세었다. 서로 겹치는 구에 들어간 행은 카메라마다 센다.','']
 for key in LABELS:
  notes+=['',f'### {LABELS[key]} — 많은 카메라 10장',''];notes+=table(['순위','카메라','30 m 안 가우시안','상자까지 XY 거리 m'],[[r['rank'],r['camera'],f'{r["gaussians_within30m"]:,}',f'{r["eval_box_xy_distance_m"]:.3f}'] for r in top if r['state']==key])
 notes+=['','전체 4 × 203행은 `camera_near_gaussians.csv/json`에 있다. 독립 검산으로 상태마다 두 카메라를 전체 행과 직접 거리 비교했고 공간 트리 결과와 같았다. 상자 거리도 다른 선분 거리식으로 대조했다.','',
 '## 6. 검게 보인 무리의 깊이와 실제 색 기여','',
 '중단 상태 0020 상위 1% 35,049개의 카메라 좌표 중심 Z는 최소 0.200098 m, 중앙값 1.351868 m, 95백분위 3.950757 m, 최대 73.418910 m다. 중심이 카메라 뒤 또는 같은 깊이에 있는 수 0개, 카메라 앞 near(0~0.2 m) 안에 있는 수 0개다. 이 중심 Z와 앞서 보고한 3차원 중심 거리 중앙값 약 18 m는 다른 값이다.','',
 '원래 CUDA forward의 정렬된 타일 목록·사영 계수·불투명도·색을 읽고, 실제 합성식 `w = alpha × T`를 화소별로 재생했다. 전체 장면/선택 무리 렌더의 RGB·알파와 최대 절대 오차 2.24×10⁻⁷ 이내로 일치했다(사전 허용 오차 10⁻⁴). CUDA 코드와 학습 소스는 고치지 않았다. 전체 렌더 RGB는 앞선 저장 렌더와 바이트 단위로 같았다.','',
 f'**가우시안별 최대 알파 기여가 0인 수 {alpha["zero_max"]:,}개, 0 초과인 수 {alpha["nonzero_max"]}개다.** 중앙값·95·99백분위는 모두 0이고 최댓값은 {alpha["max_alphaT"]["max"]:.9f}이다. 이 1개가 453화소에서 기여했다. 무리만 그린 RGB의 최댓값은 {black["subset_rgb_max"]:.9f}이다. 검게 보이는 영상이 수치적으로 전부 0인 것은 아니다.','',
 '원래 렌더러는 중심의 near 검사와 화소 광선/원반 교차 깊이의 near 검사를 따로 한다. `alpha < 1/255`는 합성하지 않고, 남은 투과율이 0.0001 미만이 되는 항부터 종료한다. 화면 타일 겹침 수는 이 최종 합성 기여와 별도로 센다. 개별 행의 중간 탈락 이유는 이번 요청의 중심 Z와 최대 기여로 대신 추정하지 않았다.','',
 '실제 코드: '+link('/out/r8_recorded_continue/runtime/rasterizer/cuda_rasterizer/auxiliary.h',200,'중심 near 검사')+', '+link('/out/r8_recorded_continue/runtime/rasterizer/cuda_rasterizer/forward.cu',372,'교차 깊이 near 검사')+', '+link('/out/r8_recorded_continue/runtime/rasterizer/cuda_rasterizer/forward.cu',388,'알파 문턱과 투과율')+'. 전체 분포·오차는 `black_render.json`, `alpha_measure.json`, 개별 최대 기여는 외부 `alpha_replay.npz`에 있다. 초기 `black_render.json`의 ‘개별 기여 미저장’ 상태는 후속 `alpha_measure.json`의 검증된 재생 결과로 보완했다. 초기 파일의 조건부 all-zero 설명은 관측 결론으로 사용하지 않았다.','',
 '## 7. 그림','']
 for name,title in [('rule_comparison','구현별 규칙'),('size_thresholds','반복별 반지름과 크기'),('camera_selection_100','100회 구간 영상 선택'),('camera_distance','카메라와 평가 상자'),('camera_near_counts','카메라 둘레 가우시안 수'),('depth_alpha','중심 깊이와 최대 알파 기여')]:notes+=['',f'![{title}]({host(F/(name+".png"))})','']
 notes+=['## 8. 검증과 재계산 경계','',
 '잠금된 입력·소스 115개 SHA-256을 다시 확인했다. 원래 7,000회와 중단 상태를 보존했다. GPU는 저장 모델의 읽기 전용 forward 1회에만 사용했고 최적화 호출은 없다. 관측한 정렬 버퍼는 7,796,493,183바이트, 렌더 최대 CUDA 할당은 9,840,448,512바이트였다.','',
 '처음 범위 검산은 camera JSON을 float64로 계산해 원래 float32 행렬 역산 결과와 약 9.8 μm 달라 중단했다. 분석 드라이버 r1에서 원래 카메라 정규화의 연산 순서를 재현해 저장 범위와 정확히 일치함을 확인했다. 학습값이나 정리 문턱은 바꾸지 않았다. 실패한 첫 분석 드라이버와 잠금도 남겼다.','',
 '직전 반지름 기록, 구간별 역사 반지름, 중단 이후 상태는 확인 불가로 남겼다. 정리 코드 수정과 학습 재실행, 나머지 여섯 판 실행은 하지 않았다. ZIP에는 표·그림·JSON·분석 스크립트·설정·해시를 넣으며 대형 체크포인트·PLY는 경로와 해시로 연결한다. 패키지 무결성 검사는 과학적 판정이 아니다.','']
 report=DOC/'화면크기_정리규칙_점검_r8_LoD2.md';report.write_text('\n'.join(notes));dump(D/'report_receipt.json',dict(at=stamp(),report=str(report),figures=6,scientific_verdict=None,training=False));print('SCREEN_REPORT_COMPLETE',report,flush=True)
if __name__=='__main__':main()
