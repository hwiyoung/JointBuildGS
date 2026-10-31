"""Four bounded candidate interventions on the exact v1 gsplat image loss."""
import hashlib
import torch
from plyfile import PlyData
from scipy.spatial import cKDTree
from gsplat import rasterization_2dgs
from gsplat.cuda._wrapper import spherical_harmonics
from frozen_engine import Scene as FrozenScene, tensor, photo, LOSS
from cp2_common import *

class Scene(FrozenScene):
    def __init__(self, unit, variant, start):
        super().__init__(unit, start=start, sh_degree=3)
        self.variant=variant; self.start=start
        self.d=arrays(CP1/'places'/(unit+'.npz'))
        self.npoints=len(self.d['point_id'])
        self.original_ids=torch.arange(len(self.opacity),device='cuda')
        self.background_ids=torch.empty(0,dtype=torch.long,device='cuda')
        self.extra={}
        if variant=='a':
            front=(self.d['mvs_p']>0).astype(int)
            ids=(np.arange(self.npoints)[:,None]*8+front[:,None]*4+np.arange(4)).ravel()
            self.original_ids=torch.as_tensor(ids,device='cuda')
            self.geometry={k:v[self.original_ids].clone() for k,v in self.geometry.items()}
            for k in ['opacity','dc','rest']: setattr(self,k,torch.nn.Parameter(getattr(self,k).detach()[self.original_ids].clone()))
        elif variant=='c':
            b=arrays(OUT/'bounds'/(unit+'.npz'))
            assert np.isfinite(b['prior_sigma_m']).all() and np.isfinite(b['image_sigma_m']).all(), 'STOP_MISSING_CANDIDATE_SIGMA'
            self.extra['means']=torch.nn.Parameter(self.geometry['means'].clone())
            self.extra['quats']=torch.nn.Parameter(self.geometry['quats'].clone())
            self.extra['log_scales']=torch.nn.Parameter(self.geometry['scales'][:,:2].log())
            self.origin=tensor(np.repeat(self.d['centre'],8,axis=0))
            self.axes=[tensor(np.repeat(self.d[k],8,axis=0)) for k in ['tangent1','tangent2','normal']]
            self.heights=tensor(np.repeat(np.stack([np.zeros(self.npoints),self.d['mvs_p']],1),4,axis=1).ravel())
            self.limits=tensor(1.96*np.repeat(np.stack([b['prior_sigma_m'],b['image_sigma_m']],1),4,axis=1).ravel())
        elif variant=='d':
            xyz=self.base['means'].cpu().numpy()
            distances=cKDTree(self.d['centre'][:,:2]).query(xyz[:,:2],k=1,workers=2)[0]
            ids=np.flatnonzero(distances<=3.)
            self.background_ids=torch.as_tensor(ids,device='cuda')
            # Read original logits: sigmoid(float32) can round to 1, whose inverse is infinite.
            raw=PlyData.read(CP1/'scenes'/unit/'background.ply',mmap='r')['vertex'].data
            self.extra['background_opacity']=torch.nn.Parameter(tensor(np.array(raw['opacity'][ids],copy=True)))
            del raw
            self.extra['background_dc']=torch.nn.Parameter(self.base['sh'][self.background_ids,:1].clone())
            self.extra['background_rest']=torch.nn.Parameter(self.base['sh'][self.background_ids,1:].clone())
            assert torch.isfinite(self.extra['background_opacity']).all(), 'STOP_NONFINITE_BACKGROUND_LOGIT'
        self.all_geometry={k:torch.cat([self.base[k],self.geometry[k]]) for k in self.geometry}

    def candidate_geometry(self):
        if self.variant!='c': return self.geometry
        return dict(means=self.extra['means'],quats=self.extra['quats'],
            scales=torch.cat([self.extra['log_scales'].exp(),self.geometry['scales'][:,2:]],1))

    def named_parameters(self):
        return dict(opacity=self.opacity,dc=self.dc,rest=self.rest,**self.extra)

    def setup_optimizer(self,cfg):
        lr=dict(opacity=cfg['learning_rates']['opacity'],dc=cfg['learning_rates']['dc'],rest=cfg['learning_rates']['sh_rest'],
            means=.00016,quats=.001,log_scales=.005,background_opacity=.05,background_dc=.0025,background_rest=.000125)
        return torch.optim.Adam([dict(params=[p],lr=lr[k],name=k) for k,p in self.named_parameters().items()],
            lr=0.,betas=tuple(cfg['adam']['betas']),eps=cfg['adam']['eps'],weight_decay=0)

    def update_schedule(self,optimizer,step,spatial_lr_scale):
        self.opacity.requires_grad_(not (self.variant=='b' and step<=1000))
        if self.variant=='c':
            t=min(max(step/30000.,0.),1.)
            lr=float(np.exp(np.log(.00016)*(1-t)+np.log(.0000016)*t)*spatial_lr_scale)
            for g in optimizer.param_groups:
                if g['name']=='means':g['lr']=lr

    @torch.no_grad()
    def project_bounds(self):
        if self.variant!='c':return
        delta=self.extra['means']-self.origin
        u=(delta*self.axes[0]).sum(1).clamp(-.25,.25)
        v=(delta*self.axes[1]).sum(1).clamp(-.25,.25)
        h=(delta*self.axes[2]).sum(1)
        h=torch.maximum(torch.minimum(h,self.heights+self.limits),self.heights-self.limits)
        self.extra['means'].copy_(self.origin+u[:,None]*self.axes[0]+v[:,None]*self.axes[1]+h[:,None]*self.axes[2])

    @torch.no_grad()
    def bound_status(self):
        if self.variant!='c':return None
        delta=self.extra['means']-self.origin
        u=(delta*self.axes[0]).sum(1);v=(delta*self.axes[1]).sum(1);h=(delta*self.axes[2]).sum(1)-self.heights
        return dict(max_tangent_excess_m=float(torch.maximum(u.abs()-.25,v.abs()-.25).max()),
                    max_normal_excess_m=float((h.abs()-self.limits).max()),finite=bool(torch.isfinite(delta).all()))

    def render(self,camera,background_only=False,candidates_only=False,depth=False):
        position=tensor(camera['position']);g=self.candidate_geometry()
        with torch.no_grad():
            base_colors=(spherical_harmonics(3,self.base['means']-position,self.base['sh'])+.5).clamp_min(0)
        bop=self.base['opacity']
        if self.variant=='d':
            bid=self.background_ids
            bsh=torch.cat([self.extra['background_dc'],self.extra['background_rest']],1)
            train_colors=(spherical_harmonics(3,self.base['means'][bid]-position,bsh)+.5).clamp_min(0)
            base_colors=base_colors.index_copy(0,bid,train_colors)
            bop=bop.index_copy(0,bid,self.extra['background_opacity'].sigmoid())
        sh=torch.cat([self.dc,self.rest],1)
        colors=(spherical_harmonics(3,g['means']-position,sh)+.5).clamp_min(0)
        if background_only: geom,colors,opacity=self.base,base_colors,bop
        elif candidates_only: geom,opacity=g,self.opacity.sigmoid()
        else:
            geom={k:torch.cat([self.base[k],g[k]]) for k in g} if self.variant=='c' else self.all_geometry
            colors=torch.cat([base_colors,colors]);opacity=torch.cat([bop,self.opacity.sigmoid()])
        return rasterization_2dgs(means=geom['means'],quats=geom['quats'],scales=geom['scales'],opacities=opacity,
            colors=colors,viewmats=tensor(camera['E'])[None],Ks=tensor(camera['K'])[None],width=camera['width'],
            height=camera['height'],render_mode='RGB+ED' if depth else 'RGB',packed=False,sh_degree=None,near_plane=.01,backgrounds=None)

    @torch.no_grad()
    def full_opacity(self):
        a=torch.zeros(self.npoints*8,device='cuda');a[self.original_ids]=self.opacity.sigmoid()
        return a.reshape(self.npoints,2,4).cpu().numpy()

    @torch.no_grad()
    def frozen_hashes(self):
        values={'base.'+k:v for k,v in self.base.items()}
        if self.variant!='c':values.update({'geometry.'+k:v for k,v in self.geometry.items()})
        result={}
        for k,v in values.items():
            assert not v.requires_grad and v.grad is None,k
            a=v.cpu().contiguous().numpy();result[k]=hashlib.sha256(memoryview(a).cast('B')).hexdigest()
        return result

    @torch.no_grad()
    def snapshot(self,path,step):
        values={k:p.detach().cpu().numpy() for k,p in self.named_parameters().items()}
        values.update(iteration=np.array(step),opacity_pair=self.full_opacity(),original_ids=self.original_ids.cpu().numpy(),
                      background_ids=self.background_ids.cpu().numpy())
        values.update({'geometry_'+k:v.detach().cpu().numpy() for k,v in self.candidate_geometry().items()})
        np.savez_compressed(path,**values)

    @torch.no_grad()
    def load_snapshot(self,path,baseline=False):
        with np.load(path) as z:
            if baseline:
                for k,old in [('opacity','opacity_logits'),('dc','color_dc'),('rest','color_sh')]:getattr(self,k).copy_(tensor(z[old]))
            else:
                assert np.array_equal(z['original_ids'],self.original_ids.cpu().numpy())
                assert np.array_equal(z['background_ids'],self.background_ids.cpu().numpy())
                for k,p in self.named_parameters().items():p.copy_(tensor(z[k]))

class Monitor:
    def __init__(self,scene):
        self.scene=scene;self.d=scene.d
        root=CP1/'render_masks'/scene.unit
        self.index=json.loads((root/'index.json').read_text());self.photos={}
        self.cameras={c['name']:c for c in scene.cams};self.masks={}
        with np.load(root/'masks.npz') as z:packed=z['packed_masks']
        for i,c in enumerate(scene.cams):
            self.masks[c['name']]=np.unpackbits(packed[i],count=c['height']*c['width']).reshape(c['height'],c['width']).astype(bool)

    def target(self,cam):
        if cam['name'] not in self.photos:self.photos[cam['name']]=photo(cam)
        return tensor(self.photos[cam['name']]/255.)

    def loss(self,image,cam):
        target=self.target(cam)
        return .8*(image-target).abs().mean()+.2*(1-LOSS.ssim(image.permute(2,0,1),target.permute(2,0,1)))

    @torch.no_grad()
    def errors(self,all_views=False):
        names=list(self.cameras) if all_views else list(dict.fromkeys(self.index['error_monitor_views']+self.index['psnr_monitor_views']))
        absolute=0.;squared=0.;count=0;psnr=[]
        for name in names:
            cam=self.cameras[name];diff=self.scene.render(cam)[0][0]-self.target(cam)
            if name in self.index['psnr_monitor_views']:psnr.append(float(-10*torch.log10(diff.square().mean())))
            if all_views or name in self.index['error_monitor_views']:
                mask=torch.as_tensor(self.masks[name],device='cuda')
                absolute+=float(diff[mask].abs().sum());squared+=float(diff[mask].square().sum());count+=int(mask.sum())*3
        return dict(candidate_l1=absolute/count if count else None,candidate_mse=squared/count if count else None,
                    candidate_pixel_observations=count//3,first_five_train_psnr_db=float(np.mean(psnr)))

    @torch.no_grad()
    def opacity(self):
        d=self.d;pair=self.scene.full_opacity().mean(2);ix=np.arange(len(pair));ri=(d['right']=='image').astype(int)
        right=pair[ix,ri];wrong=pair[ix,1-ri];fi=(d['mvs_p']>0).astype(int)
        front=pair[ix,fi];back=pair[ix,1-fi];both=1-(1-right)*(1-wrong)
        rows=[]
        for group in ['a','b','c']:
            for side in ['front','back']:
                m=(d['group']==group)&(d['side']==side)
                rows.append(dict(group=group,side=side,points=int(m.sum()),area_m2=float(d['area'][m].sum()),
                    mean_right_minus_wrong=float(np.mean(right[m]-wrong[m])) if m.any() else None,
                    area_weighted_right_minus_wrong=float(np.average(right[m]-wrong[m],weights=d['area'][m])) if m.any() else None,
                    front_opacity_median=float(np.median(front[m])) if m.any() else None,
                    back_opacity_median=float(np.median(back[m])) if m.any() else None,
                    combined_coverage_median=float(np.median(both[m])) if m.any() else None))
        return rows
