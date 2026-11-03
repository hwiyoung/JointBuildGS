"""Saved-state loss replay, using immutable native pure loss functions; no controllers/optimizer."""
import ast,types
import torch,numpy as np,cv2
from pathlib import Path
from utils.loss_utils import l1_loss,ssim
from common import *
def functions(path,names):
 tree=ast.parse(Path(path).read_text());nodes=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name in names];assert len(nodes)==len(names)
 env={'torch':torch};exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),env);return env
class Loss:
 def __init__(self,row):
  self.row=row;self.family=('baseline' if row['family']=='base' else row['family']);self.files=[]
  if self.family=='baseline':
   p=Path('/source/jbgs_judgment.py');self.native=functions(p,['weighted_l1','rho_truncated','truncated_prior_loss']);self.files.append(p)
  elif self.family=='geogs':
   p=Path('/source/train.py');self.native=functions(p,['compute_depth_loss']);self.files.append(p)
  self.maps={}
 def input_paths(self,name):
  fam=self.family;r=self.row;root=S0/'fork_inputs/s61/B173nb_b10/maps'
  if fam=='baseline':return {k:root/v/(name+'.npy') for k,v in [('M','mvs'),('A','conf'),('P','prior_'+r['prior']),('TAU','tau_'+r['prior'])]}
  if fam in ['r7','r8']:
   root=OUT/fam/'stage1'/('B173nb_b10_'+r['prior'])/'maps';idx=json.loads((root/'index.json').read_text());return {'target':root/idx['views'][name]['file']}
  if fam=='geogs':return {'prior':Path('/scene/lod2_prior/raw_depth')/(name+'.npy'),'mvs':Path('/scene/da3_prior/raw_depth')/(name+'.npy')}
  assert fam=='image_only';return {}
 def for_view(self,cam):
  data={};H,W=cam.image_height,cam.image_width
  for k,p in self.input_paths(cam.image_name).items():
   assert p.exists(),str(p)
   if k=='target':
    with np.load(p) as z:data={k:torch.as_tensor(z[k].copy(),device='cuda') for k in ['depth','weight']}
   else:
    a=np.load(p).astype('f4')
    if a.shape!=(H,W):a=cv2.resize(a,(W,H),interpolation=cv2.INTER_NEAREST)
    data[k]=torch.as_tensor(a,device='cuda')
  return data
 def __call__(self,cam,pkg,data):
  image=pkg['render'];gt=cam.original_image.cuda();ll1=l1_loss(image,gt);rgb=.8*ll1+.2*(1.-ssim(image,gt));normal=.05*(1-(pkg['rend_normal']*pkg['surf_normal']).sum(dim=0))[None].mean();dist=0.*pkg['rend_dist'].mean();loss=rgb+dist+normal;D=pkg['surf_depth'].squeeze(0)
  if self.family=='baseline':
   m=self.native['weighted_l1'](D,data['M'],data['A'],float(D.numel()))[0];p=self.native['truncated_prior_loss'](D,data['P'],data['TAU'],torch.ones_like(D),4.,float(D.numel()))[0];loss=loss+.05*m+.05*p
  elif self.family in ['r7','r8']:
   target,w=data['depth'],data['weight'];valid=torch.isfinite(target)&(target>0)&torch.isfinite(D)&(D>0)&(w>0);term=(torch.abs(D[valid]-target[valid])*w[valid]).sum()/float(D.numel());loss=loss+.05*term
  elif self.family=='geogs':
   p=self.native['compute_depth_loss'](pkg['surf_depth'],data['prior']);m=self.native['compute_depth_loss'](pkg['surf_depth'],data['mvs']);loss=loss+.005*p+.05*m
  return loss
