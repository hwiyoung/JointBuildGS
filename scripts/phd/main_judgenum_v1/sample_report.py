"""Section 2.1 evidence only; explicitly not a completed judgment report."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Polygon as Patch,Patch as LegendPatch
from lock_config import dump,sha,stamp
O=Path('/out');C=Path('/cfg');D=Path('/docs')

def setup():
    fonts=list(Path('/fonts').glob('*SansCJK*Regular*.ttc'))
    if fonts:
        font_manager.fontManager.addfont(str(fonts[0]));plt.rcParams['font.family']=font_manager.FontProperties(fname=str(fonts[0])).get_name()
    plt.rcParams.update({'axes.unicode_minus':False,'font.size':10,'axes.spines.top':False,'axes.spines.right':False})

def main():
    setup();g=json.loads((O/'sample_gate.json').read_text());rows=g['rows'];cfg=json.loads((C/'judgenum_v1.json').read_text())
    figs=D/'figures';figs.mkdir(exist_ok=True)
    fig,ax=plt.subplots(figsize=(9,4));rr=[r for r in rows if r['kind']==1];xx=np.arange(2)
    for off,cell,col in [(-.18,1,'#0072b2'),(.18,2,'#d55e00')]:
        vals=[r[f'cell{cell}_buildings_gt1m2'] for r in rr]
        bars=ax.bar(xx+off,vals,.33,color=col,label=f'칸 {cell}')
        ax.bar_label(bars,padding=4)
    ax.axhline(5,color='#444444',ls='--',label='기준 5동');ax.set_xticks(xx,['LoD2','항공 LiDAR'])
    ax.set_ylim(0,105);ax.set_ylabel('1 m² 넘는 건물 수');ax.set_title('평가 지역 제외 뒤 지붕 표본');ax.legend(ncol=3,loc='upper left')
    fig.tight_layout();fig.savefig(figs/'sample_gate.png',dpi=300);plt.close(fig)
    dump(figs/'sample_gate.json',{'rows':rr,'source':'tables/sample_counts.json','photos':[],
      'selection':'kind == 1; inherited cell area strictly greater than 1 m2 per building',
      'source_sha256':sha(D/'tables/sample_counts.json'),'scientific_verdict':None})
    geometry=json.loads((C/'scope_geometry.json').read_text())['features']
    for prior in ['LoD2','ALS']:
        fig,axs=plt.subplots(1,2,figsize=(11,8),sharex=True,sharey=True)
        refs=[]
        for p in sorted((O/'scope_selection').glob(f'*__{prior}__R1.5.npz')):
            with np.load(p) as z:
                x=z['centre'][:,:2];k=z['kind'];cell=z['cell']
                for ax,kind in zip(axs,[1,2]):
                    for ci,color,size in [(-1,'#dddddd',.13),(1,'#0072b2',.35),(2,'#d55e00',.35)]:
                        m=(k==kind)&((cell==ci) if ci>=0 else ~np.isin(cell,[1,2]))
                        ax.scatter(x[m,0],x[m,1],s=size,c=color,rasterized=True,linewidths=0)
            refs.append({'file':str(p),'sha256':sha(p),'patch_id_member':'patch_id','coords_member':'centre',
                'value_member':'cell','selection':'kind=1 left; kind=2 right; all eligible patches; no thinning'})
        for ax,kind in zip(axs,[1,2]):
            for ft in geometry:
                state=ft['properties']['split']
                if state not in ['evaluation','holdout']:continue
                geo=ft['geometry'];polys=[geo['coordinates']] if geo['type']=='Polygon' else geo['coordinates']
                for poly in polys:
                    xy=np.asarray(poly[0])-np.array([690953,5336071])
                    ax.add_patch(Patch(xy,closed=True,fill=state=='holdout',facecolor='#eeeeee',
                        edgecolor='#555555' if state=='evaluation' else '#999999',linewidth=.6,
                        hatch='////' if state=='holdout' else None))
            ax.set_aspect('equal');ax.set_xlabel('동쪽 좌표 − 690953 (m)');ax.set_title('지붕 패치' if kind==1 else '벽 패치')
            if prior=='ALS' and kind==2:ax.text(.5,.5,'벽 패치 없음',transform=ax.transAxes,ha='center',va='center',bbox={'facecolor':'white','edgecolor':'none'})
        axs[0].set_ylabel('북쪽 좌표 − 5336071 (m)')
        handles=[LegendPatch(color='#0072b2',label='칸 1'),LegendPatch(color='#d55e00',label='칸 2'),
                 LegendPatch(facecolor='none',edgecolor='#555555',label='평가 지역 건물'),
                 LegendPatch(facecolor='#eeeeee',edgecolor='#999999',hatch='////',label='확인용')]
        fig.legend(handles=handles,loc='lower center',ncol=4)
        fig.suptitle(('항공 LiDAR' if prior=='ALS' else prior)+' · 표본의 자리')
        fig.tight_layout(rect=[0,.05,1,.96]);fig.savefig(figs/f'sample_scope_{prior}.png',dpi=300);plt.close(fig)
        dump(figs/f'sample_scope_{prior}.json',{'source_arrays':refs,'photos':[],
          'crs':'EPSG:25832','shift_xy_m':[690953,5336071],
          'note':'Inherited cells, not judgment 1. Holdout outlines have no outcomes.',
          'config_sha256':sha(C/'judgenum_v1.json'),'scientific_verdict':None})
    lines=['# 판단 숫자 셈 — 중간 보고 v1','',
      '표본 검사 통과. 평가 지역 건물 10동을 제외했다. [이 발주에서 냄]',
      'LoD2 125동, 핵심점 2,129,735개. 항공 LiDAR 122동, 핵심점 501,913개.',
      '고른 값: 원통 반지름·최소 넓이·사진 조합·threshold2는 아직 정하지 않았다.',
      '확인 불가: 원자료의 법선 1,091개, 항공 LiDAR 흔들림 9,192개.',
      f"표본 셈 {g['seconds']:.2f}초. 원통 셈 시간 검사는 진행 중이다.",
      '', '## 범위와 표본 수', '',
      '| 사전 정보 | 패치 | 건물 수 | 핵심점 수 | 넓이 m² | 칸 1 넓이 m² | 칸 1 >1 m² 건물 | 칸 1 상위 3동 비율 | 칸 2 넓이 m² | 칸 2 >1 m² 건물 | 칸 2 상위 3동 비율 |',
      '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        f=lambda x:'해당 없음' if x is None else f'{x*100:.2f}%'
        lines.append(f"| {r['prior']} | {'지붕' if r['kind']==1 else '벽'} | {r['building_count']} | {r['patch_count']:,} | {r['area_m2']:.6f} | {r['cell1_area_m2']:.6f} | {r['cell1_buildings_gt1m2']} | {f(r['cell1_top3_fraction'])} | {r['cell2_area_m2']:.6f} | {r['cell2_buildings_gt1m2']} | {f(r['cell2_top3_fraction'])} |")
    lines += ['', '지붕에서 두 칸 모두 5동 이상이어야 한다. 네 조건 모두 통과했다. 비율의 분모는 해당 칸 전체 넓이다.',
      '', '![표본 기준](figures/sample_gate.png)', '',
      '![LoD2 표본의 자리](figures/sample_scope_LoD2.png)', '',
      '![항공 LiDAR 표본의 자리](figures/sample_scope_ALS.png)', '',
      '위 그림의 색은 넓히기 v2의 참값 칸이다. 아직 계산하지 않은 판단 1을 나타내지 않는다.', '',
      '## 제외한 건물', '',
      '| 건물 | 평가 범위 |','|---|---|']
    lines += [f"| {r['building']} | {', '.join(r['regions'])} |" for r in cfg['scope']['excluded']]
    lines += ['', '제외 목록과 외곽 표시에는 건물 번호와 GroundSurface XY만 썼다. 평가 지역과 확인용의 패치 측정 행은 해석하거나 집계하지 않았다. 압축 파일의 건너뛰기 과정에서 압축 바이트가 풀릴 수 있으므로 물리적인 디스크 읽기 자체가 없었다는 뜻은 아니다.',
      '', '## 입력 연결', '',
      '설정용 2,631,648개 패치를 기존 사진 판단과 patch_id로 연결했다. 판단이 없는 설정용 패치는 0개다. 새 사진 검사는 하지 않았다.',
      '', '## 잠금과 진행 범위', '',
      '후보 목록과 선택 규칙을 최초 표본 셈 전에 잠갔다. 단면 좌표는 잠긴 규칙으로 표본 셈 뒤 확정했고 원통 셈 전에 추가로 잠갔다. 이전 설정과 SHA-256을 보존했다. 최초 표본 셈 전에 단면 좌표까지 확정한 것은 아니다.',
      '', '원통 반지름, 검출 한계, 판단 1, 최소 넓이, 처음 선택, 민감도, 확인용 셈은 완료 결과로 보고하지 않는다. 이후 계산 결과에 따라 이 중간 보고를 갱신한다.',
      '', '원자료·앞 작업 코드는 수정하지 않았다. CPU 컨테이너, nice 19, GPU 장치 없음, 메모리 상한 32 GB로 실행한다.',
      '', '`scientific_verdict: null`', '',
      '근거: [표본 수](tables/sample_counts.json), [건물별 표](tables/sample_buildings.csv), [입력 연결](tables/input_join.json), [확인 불가와 수정 기록](issues.md).']
    (D/'중간보고_v1.md').write_text('\n'.join(lines)+'\n')
    (D/'progress.md').write_text('# PHD-MAIN-JUDGENUM-v1 진행\n\n'+f'- 갱신: {stamp()}\n- 표본 검사: PASS\n- 사진 판단 연결: PASS\n- 모의 원통 960개 직접 비교: PASS\n- 실제 자료 한 구역 시간 검사: 진행 중\n- 단계 나·다: 아직 실행하지 않음\n- scientific_verdict: null\n')
    print('SAMPLE_REPORT_READY')

if __name__=='__main__':main()
