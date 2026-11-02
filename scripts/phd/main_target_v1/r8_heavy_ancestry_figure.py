"""Track saved descendants sharing initial IDs of the stopped top groups."""
from r8_heavy_figures import *
def main():
 rows=read(T/'fixed_initial_seed_cohorts.json')['rows'];fig,axs=plt.subplots(2,1,figsize=(12,8),sharex=True)
 for q,col in [(.01,'#317fa0'),(.1,'#9c438a')]:
  for stage,ls,lab in [('pre','--','직전'),('post','-','직후')]:
   rr=[r for r in rows if r['final_top_fraction']==q and r['stage']==stage];xx=[r['iteration'] for r in rr];axs[0].plot(xx,[r['gaussians'] for r in rr],ls=ls,marker='o',color=col,label=f'중단 상위 {q*100:g}%의 처음 씨앗 · {lab}');axs[1].plot(xx,[r['overlaps'] for r in rr],ls=ls,marker='o',color=col)
  stop=next(r for r in rows if r['final_top_fraction']==q and r['stage']=='before_attempt');axs[0].scatter([14031],[stop['gaussians']],marker='x',color=col);axs[1].scatter([14031],[stop['overlaps']],marker='x',color=col)
 axs[0].set_ylabel('같은 처음 씨앗을 공유하는 가우시안 수');axs[1].set(xlabel='반복',ylabel='같은 처음 씨앗을 공유하는 겹침 수');axs[0].legend(fontsize=8);[a.grid(alpha=.2) for a in axs];fig.suptitle('처음 씨앗 ID를 고정한 자손 집계 · 직접 부모 경로 아님');fig.tight_layout();save(fig,'fixed_initial_seed_cohorts',rows)
if __name__=='__main__':main()
