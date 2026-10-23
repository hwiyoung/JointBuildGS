"""Source-backed intermediate report and scope map, without patch outcomes."""
import datetime as dt
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Polygon as Patch,Patch as Legend
from shapely.geometry import shape
from preflight import dump,sha

O,D=Path('/out'),Path('/docs')

def main():
    for f in Path('/fonts').glob('*.ttc'):font_manager.fontManager.addfont(f)
    plt.rcParams['font.family']=['Noto Sans CJK JP','DejaVu Sans']
    plt.rcParams['axes.unicode_minus']=False
    s=json.loads((O/'scope_split.json').read_text());im=json.loads((D/'tables/image_inventory.json').read_text())
    sp=json.loads((O/'building_split.json').read_text());cfg=json.loads(Path('/cfg/widen0_v2.json').read_text())
    cover=np.load(O/'inputs/coverage.npz');g=s['grid']
    blds=json.loads((O/'inputs/lod2_buildings.json').read_text())
    held=set(sp['holdout'])
    rgba=np.zeros((*cover['common'].shape,4),float)
    rgba[cover['uls']>0]=[.42,.69,.83,.65]
    rgba[cover['common']]=[.63,.84,.69,.9]
    fig,ax=plt.subplots(figsize=(9,10))
    extent=[g['e0'],g['e1'],g['n0'],g['n1']]
    ax.imshow(rgba,origin='lower',extent=extent,interpolation='nearest')
    for b in blds:
        for p in b['surfaces']['ground']:
            xy=np.array(p['ext'])[:,:2]
            ax.add_patch(Patch(xy,closed=True,facecolor='#dddddd' if b['id'] in held else 'none',
                edgecolor='#555555',linewidth=.45,hatch='////' if b['id'] in held else None,zorder=3))
    for name,geo in s['regions'].items():
        po=shape(geo);xy=np.array(po.exterior.coords)
        ev=name in cfg['scope']['evaluation_regions']
        ax.plot(xy[:,0],xy[:,1],color='#7b3294' if ev else '#d95f02',linewidth=1.2 if ev else .8,zorder=4)
        ax.text(po.centroid.x,po.centroid.y,name.replace('_b10','').replace('_b0',''),fontsize=6,color='#582369' if ev else '#8b3e02')
    ax.set(xlim=extent[:2],ylim=extent[2:],aspect='equal',xlabel='동쪽 좌표 (m)',ylabel='북쪽 좌표 (m)',title='사진·연직 LiDAR·사전 정보 공통 범위')
    ax.ticklabel_format(style='plain',useOffset=False)
    ax.tick_params(labelsize=8)
    ax.annotate('북',xy=(.95,.94),xytext=(.95,.86),xycoords='axes fraction',ha='center',arrowprops=dict(arrowstyle='->'))
    ax.legend(handles=[Legend(facecolor=(.63,.84,.69),label='공통 범위'),Legend(facecolor=(.42,.69,.83),label='연직 LiDAR'),
        Legend(facecolor='#dddddd',edgecolor='#555555',hatch='////',label='확인용 건물'),
        Legend(facecolor='none',edgecolor='#7b3294',label='평가 지역'),Legend(facecolor='none',edgecolor='#d95f02',label='탐색 지역')],loc='lower left',fontsize=8)
    fig.text(.5,.025,'EPSG:25832 · 사진 범위는 지형 투영 · 항공 LiDAR와 LoD2 자료 범위는 지도 전체 포함',ha='center',fontsize=8)
    fig.tight_layout(rect=(0,.04,1,1));(D/'figures').mkdir(exist_ok=True)
    for ext in ['png','pdf']:fig.savefig(D/f'figures/범위와_건물나눔.{ext}',dpi=300)
    plt.close(fig)
    dump(D/'figures/범위와_건물나눔.json',dict(source=str(O/'scope_split.json'),scope_sha256=sha(O/'scope_split.json'),
        building_split_sha256=sha(O/'building_split.json'),dpi=300,holdout_outcomes=False,scientific_verdict=None))
    est=im['mvs_estimate'];now=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
    lines=[f"범위: 사진·연직 LiDAR·두 사전 정보의 공통 XY 범위 {s['scope_area_m2']:,.2f} m², LoD2 건물 {s['buildings']}개. [이 발주에서 냄]",
        f"나눔: 정하는 곳 {s['development']['buildings']}개 / 공통 범위 안 바닥 넓이 {s['development']['common_footprint_area_m2']:,.2f} m², 확인용 {s['holdout']['buildings']}개 / {s['holdout']['common_footprint_area_m2']:,.2f} m². [이 발주에서 냄]",
        '확인 불가: 새 영역의 등록된 사전 정보 − 참값과 시험 자리 수는 아직 계산하지 않음. 학습 영상만의 MVS 생성 뒤 CPU로 계산한다.',
        '', '# PHD-MAIN-WIDEN0-v2 중간 보고 v1', '',f'- 작성: {now}', '- 상태: PARTIAL — 입력·범위·나눔 완료, 패치 측정 진행 전.',
        '- scientific_verdict: null','- 학습 없음. 이 보고를 만들 때까지 GPU 계산 없음.', '',
        '## 범위와 나눔','', '![범위와 건물 나눔](figures/범위와_건물나눔.png)', '',
        f"연직 비행 원자료 {s['raw_sources']['/art/phase-payloads/p0-audit/data/raw/tum2twin/TUM_Downtown_ULS_20241217_nadir.laz']['points']:,}점을 전부 읽었다. 0.5 m 격자의 자료 도달 범위를 사용했다. 사진은 카메라에 ALS 지형이 투영되는지를 계산했다. MVS 존재 여부로 범위를 제한하지 않았다. 공통 범위 중 기존 MVS가 없는 넓이는 {s['common_without_existing_MVS_m2']:,.2f} m²이다. [이 발주에서 냄]",
        '',f"강제 정하는 곳은 {s['forced_development_buildings']}개다. 나머지 {s['random_pool_buildings']}개를 건물 번호 순서로 놓고 씨앗 20261023으로 floor(30%)={s['holdout']['buildings']}개를 확인용으로 선택했다. 패치 결과는 읽지 않았다. 100 m 구역 {s['tiles']}개, 둘레 겹침 10 m를 사용한다. [이 발주에서 냄]",
        '',f"건물 나눔 SHA-256: `{sha(O/'building_split.json')}`. 확인용 패치 측정 파일은 아직 없다. 확인용의 칸별 넓이·자리·패치값은 이 보고에 없다.",
        '', '## 영상·입력·MVS 시간','',f"전체 영상 {im['model_images']}장과 표정이 모두 있으며, 후보 영상 {im['candidates']}장 전부가 범위에 걸친다. 감사 규칙으로 학습 {im['train']}장·평가 {im['evaluation']}장이다. 평가 지역 네 곳의 회전·이동과 전체 모델의 값이 일치한다. [이 발주에서 냄]",'',
        '| 영상 나눔 | 촬영 비행 | 수 | 연직 | 비스듬함 | 촬영 시각 UTC | 상대 고도 중앙값 m |','|---|---|---:|---:|---:|---|---:|']
    for r in im['groups']:
        if not r['images']:continue
        lines.append(f"| {r['split']} | {r['flight']} | {r['images']} | {r['nadir']} | {r['oblique']} | {r['utc_first']} ~ {r['utc_last']} | {r['relative_altitude_m']['median']} |")
    lines += ['', '영상의 비행 구분은 기존 사진 보고의 촬영 시각 구간을 사용했다. 상대 고도는 원본 XMP의 값이며 지면에서의 높이로 바꾸지 않았다. 수동 비행 **LiDAR**는 쓰지 않는다. 영상은 본 실험의 전체 카메라 모델을 사용한다.', '',
        f"기존 실행 네 건: 제출 영상 924장, 총 11,205초, 영상당 {est['seconds_per_image']:.9f}초. 학습 {im['train']}장으로 단일 GPU {est['single_gpu_hours']:.6f}시간, 두 GPU의 이상적 분담 {est['two_gpu_ideal_hours']:.6f}시간이다. 최초 어림은 출력 영상 919장으로 나누어 2.773817시간이었고, 실행 로그의 제출 수를 확인하여 924장으로 정정했다. 실제 두 GPU 분담을 검증한 값은 아니다. 48시간 중단 기준 안이므로 별도 결정을 기다리지 않고 MVS로 이어 간다. [이 발주에서 냄]",'',
        '기존 기하 깊이·신뢰도·사전 정보 렌더·영역·패치값은 평가 지역에 있다. 전체 819장 학습 목록으로 만든 깊이는 없다. 기존 전체 937장 MVS에는 평가 영상이 섞여 있으므로 범위 입력 현황에만 사용했다. 상세 출처와 반올림 전 값은 `tables/input_preflight.json`, `tables/image_inventory.json`, `tables/scope_split.json`에 있다.', '',
        '## 사전 정보 패치·참값·시험 자리','',
        '0.25 m 패치는 기존 면 생성·패치 생성 함수를 사용해 구역마다 준비 중이다. 새 영역의 정합은 학습 영상만의 깊이를 필요로 한다. 이에 이 중간 보고의 사전 정보 − 참값 표와 시험 자리 목록은 미완료다. MVS 생성 뒤 같은 정합 함수와 참값 정의로 CPU 계산하고 최종 보고에 채운다. 기존 전체 MVS로 이 값을 대신 구하지 않는다.', '',
        '참값은 연직 비행만 사용하고, 기존 1단계의 공통 높이 이동 및 제외 규칙을 적용한다. B0의 앞 불확실도 값은 수동 비행도 포함했으므로 별도 비교 출처로 남긴다.', '',
        '## τ와 설정 잠금','',
        '이번 τ: 항공 LiDAR 12.66 cm, LoD2 지붕·벽 모두 20 cm. LoD2는 2026-10-24 사용자 답변을 반영했다. 앞 τ와 결과는 수정하지 않으며, 원래 τ와 이번 τ의 교차표를 낸다.', '',
        f"현재 설정 SHA-256: `{sha('/cfg/widen0_v2.json')}`. 첫 잠금과 수정 전 설정은 `configs/phd/main_widen0_v2/`에 보존했다. 건물 나눔·영상 나눔의 잠금에는 당시 설정 해시가 있다.", '',
        '## 예외와 다음 계산','',
        '- MVS로 사진 범위를 정한 잠정 설정은 MVS 없는 자리를 제외하는 문제가 있어 패치 결과 계산 전에 폐기했다. 원자료 기반 사진 투영으로 수정하고 건물 나눔을 다시 잠갔다.',
        '- 새 영역 정합의 입력 의존성 때문에 사전 정보 오차 측정은 MVS 생성 뒤 CPU로 마무리한다.',
        '- 편집 실수로 허용 경로 밖 루트에 빈 `interim.tmp`가 잠시 생겼고 즉시 제거했다. 기존 파일은 바뀌지 않았다. 경로 준수 점검은 이 예외를 포함한다.',
        '- 실패·수정 기록은 `issues.md`에 남겼다. 확인용의 결과는 생성 시부터 외부 `holdout/`에만 저장한다.',
        '', '이 보고는 입력·절차 기록이다. 해석과 과학적 판정은 포함하지 않는다.']
    (D/'중간보고_v1.md').write_text('\n'.join(lines)+'\n')
    (D/'progress.md').write_text('\n'.join(['# PHD-MAIN-WIDEN0-v2 진행 기록','',f'- {now}',
        '- 입력·범위·건물 나눔·영상 나눔 완료. 설정과 목록의 해시 저장.',
        '- 중간 보고 PARTIAL: 새 영역의 정합·오차·시험 자리는 학습 영상만의 MVS 뒤 CPU로 완료 예정.',
        '- 다음: MVS 819장, 패치 측정, 확인용 봉인 검증, 표·그림·묶음, 지정 경로 커밋·푸시.',
        '- scientific_verdict: null','']) )
    print('intermediate report and map written')

if __name__=='__main__':main()
