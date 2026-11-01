from common import *
from report_stage0 import plt
files=sorted((DOC/'figures').glob('r6_*.png'));root=OUT/'r6/visual_review';root.mkdir(exist_ok=True)
for page,start in enumerate(range(0,len(files),12)):
 group=files[start:start+12];fig,axes=plt.subplots(4,3,figsize=(15,14))
 for ax in axes.flat:ax.axis('off')
 for ax,p in zip(axes.flat,group):ax.imshow(plt.imread(p));ax.set_title(p.stem,fontsize=7)
 fig.subplots_adjust(left=.01,right=.99,bottom=.01,top=.98,wspace=.04,hspace=.08);fig.savefig(root/f'sheet_{page}.png',dpi=120);plt.close(fig)
 dump(root/f'sheet_{page}.json',dict(files=[dict(file=p.name,sha256=sha(p)) for p in group],scientific_verdict=None))
print('SHEETS',len(files),(len(files)+11)//12)
