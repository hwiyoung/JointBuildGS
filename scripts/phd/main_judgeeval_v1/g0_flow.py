"""3절 순서도: figures/fig0_flow_current.json(코드 옮겨 적기의 마디 목록)을 실행 순서대로 그림. 사용: g0_flow.py"""
from common import *
import textwrap
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; from matplotlib import font_manager as fm
from matplotlib.patches import FancyBboxPatch
for f in ['/fonts/NotoSansCJK-Regular.ttc', '/fonts/NotoSansCJK-Bold.ttc']: fm.fontManager.addfont(f)
plt.rcParams.update({'font.family': 'Noto Sans CJK JP'})
def main():
    J = json.loads((D/'figures/fig0_flow_current.json').read_text()); M = J['methods']; nmax = max(len(v) for v in M.values())
    fig, axs = plt.subplots(1, len(M), figsize=(8.2*len(M), 1.55*nmax + 1)); axs = np.atleast_1d(axs)
    for ax, (name, nodes) in zip(axs, M.items()):
        ax.set_xlim(0, 10); ax.set_ylim(-len(nodes)*1.55 - .3, .9); ax.axis('off'); ax.text(0, .55, name, fontsize=13, fontweight='bold')
        for k, nd in enumerate(nodes):
            y = -k*1.55; ax.add_patch(FancyBboxPatch((0, y - 1.15), 6.4, 1.05, boxstyle='round,pad=0.02,rounding_size=0.08', fc='#F1EFE8', ec='#5F5E5A', lw=.8))
            ax.text(.12, y - .22, f"{nd['id']}. {nd['label']}", fontsize=9.5, fontweight='bold', va='top')
            ax.text(.12, y - .52, '\n'.join(textwrap.wrap(str(nd.get('detail', '')), 62))[:420], fontsize=6.2, va='top', color='#2C2C2A')
            yes, no = str(nd.get('yes', '')), str(nd.get('no', ''))
            br = f'예 → {yes}' if yes == no else f'예 → {yes}\n아니오 → {no}'
            ax.text(6.6, y - .6, '\n'.join(textwrap.wrap(br, 34)), fontsize=7, va='center', color='#185FA5')
            if k < len(nodes) - 1: ax.annotate('', xy=(3.2, y - 1.2 - .3), xytext=(3.2, y - 1.15), arrowprops=dict(arrowstyle='->', lw=.8, color='#5F5E5A'))
    fig.suptitle('지금 판단 코드의 실행 순서(본 방법 · 11/22 새 구조), 판단코드_옮겨적기.md 에서', fontsize=12)
    fig.savefig(D/'figures/fig0_flow_current.png', dpi=300, bbox_inches='tight', pad_inches=.1); plt.close(fig)
    meta = dict(J); meta.update(at=now(), figure='fig0_flow_current.png', source='판단코드_옮겨적기.md (하위 에이전트가 코드를 읽어 적음; 줄 번호 넷을 직접 맞대 확인)', scientific_verdict=None); dump(D/'figures/fig0_flow_current.json', meta); print('FLOW')
if __name__ == '__main__': main()
