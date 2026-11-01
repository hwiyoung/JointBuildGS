"""Same axes for r6/r7 losses, opacity and counts through the 7k checkpoint."""
from common import *
from report_stage0 import plt,save
def main():
    fig,axes=plt.subplots(1,3,figsize=(14,4));values=[]
    for prior,color in [('ALS','#438bb6'),('LoD2','#a94e83')]:
        for revision,style in [('r6','--'),('r7','-')]:
            path=OUT/revision/'runs'/f'tg_B173nb_b10_{prior}_s0_{revision}/model/target_monitor/curve.jsonl';rows=[json.loads(x) for x in path.read_text().splitlines() if json.loads(x)['iteration']<=7000];values.append(dict(prior=prior,revision=revision,rows=rows))
            for ax,key,label in zip(axes,['loss','prior_opacity_median','gaussians'],['총 손실','처음 패치 계보 불투명도 중앙값','가우시안 수']):
                ax.plot([r['iteration'] for r in rows],[r[key] for r in rows],style,c=color,label=prior+' '+revision);ax.set(xlabel='반복',ylabel=label,xlim=(0,7000));ax.legend(fontsize=6)
    for iteration in [3000,6000]:axes[1].axvspan(iteration,iteration+500,color='gray',alpha=.12)
    fig.subplots_adjust(top=.8,bottom=.2,wspace=.3);save(fig,'r7_training_curves','r6과 r7: 7,000회까지 손실·불투명도·가우시안 수',values,'회색 띠: r7의 초기화 뒤 불투명도 감시 예외 · NaN·수 검사는 유지 · 곡선은 밀도 제어 뒤 기록')
    print('R7_CURVES_COMPLETE',flush=True)
if __name__=='__main__':main()
