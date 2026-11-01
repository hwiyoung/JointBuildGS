"""User FARPULL addendum 3: train-view affine colour; never used by render.py."""
import json
from pathlib import Path
import torch

def register_args(parser):
    parser.add_argument('--jbgs_appearance',choices=['off','affine'],default='off')
    parser.add_argument('--jbgs_appearance_health',choices=['raw','corrected'],default='raw')

class Affine:
    def __init__(self,cameras,device):
        self.names=[c.image_name for c in cameras]
        assert len(set(self.names))==len(self.names)
        self.index={name:i for i,name in enumerate(self.names)}
        self.identity=torch.eye(3,device=device)
        self.matrix=torch.nn.Parameter(self.identity.repeat(len(self.names),1,1))
        self.bias=torch.nn.Parameter(torch.zeros((len(self.names),3),device=device))
        self.optimizer=torch.optim.Adam([self.matrix,self.bias],lr=1e-3)

    def apply(self,name,image):
        i=self.index[name]
        return torch.einsum('ij,jhw->ihw',self.matrix[i],image)+self.bias[i,:,None,None]

    def penalty(self,name):
        i=self.index[name]
        # Mean of the twelve squared deviations, frozen before any run.
        return 1e-4*((self.matrix[i]-self.identity).square().sum()+self.bias[i].square().sum())/12

    def save(self,path,iteration):
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        torch.save(dict(names=self.names,matrix=self.matrix.detach().cpu(),bias=self.bias.detach().cpu(),optimizer=self.optimizer.state_dict(),iteration=iteration,lr=1e-3,l2=1e-4,l2_definition='mean over 12 selected-view affine deviations',training_only=True),path)
        summary=dict(iteration=iteration,views=len(self.names),matrix_max_abs_identity_difference=float((self.matrix-self.identity).abs().max()),bias_max_abs=float(self.bias.abs().max()),finite=bool(torch.isfinite(self.matrix).all() and torch.isfinite(self.bias).all()),scientific_verdict=None)
        path.with_suffix('.json').write_text(json.dumps(summary,indent=2)+'\n')
        assert summary['finite'],'Nonfinite appearance transform'

    def restore(self,path):
        state=torch.load(path,map_location=self.matrix.device,weights_only=False)
        assert state['names']==self.names
        with torch.no_grad():self.matrix.copy_(state['matrix']);self.bias.copy_(state['bias'])
        self.optimizer.load_state_dict(state['optimizer'])

def create(args,scene,gaussians):
    if args.jbgs_appearance=='off':return None
    return Affine(scene.getTrainCameras(),gaussians.get_xyz.device)
