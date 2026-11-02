from r8_heavy_figures import *
def main():
 c=read(CFG/'r8_heavy.json');receipt=read(H/'subset/receipt.json');cam=c['heavy_camera'];full=np.load(H/'states/r8_14031_stop'/(cam+'.npz'))['rgb'];fig,axs=plt.subplots(1,3,figsize=(18,5.2))
 for ax,image,title in zip(axs,[full,*[np.load(H/'subset'/f'top{q}.npz')['rgb'] for q in [1,10]]],['중단 상태 전체','겹침 상위 1%만 렌더','겹침 상위 10%만 렌더']):ax.imshow(np.clip(image.transpose(1,2,0),0,1));ax.set_title(title);ax.axis('off')
 fig.suptitle(cam+' · 같은 카메라 · 저장된 색과 불투명도 · 검정 배경');fig.tight_layout();save(fig,'top_groups_rgb',receipt)
if __name__=='__main__':main()
