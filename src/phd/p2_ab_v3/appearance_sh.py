"""SH3 color capacity diagnostic; geometry remains the frozen v2 representation."""
import torch
from src.phd.p2_ab_v2.reconstruction import StructuredGaussians as BaseGaussians
from src.phd.p2_ab_v2.reconstruction import render_view as base_render_view
from src.stage2.renderer import render


class StructuredGaussians(BaseGaussians):
    active_sh_degree = 3

    def __init__(self, seed, cfg, device="cuda"):
        super().__init__(seed,cfg,device)
        self.sh_rest=torch.nn.Parameter(torch.zeros((len(self.base),15,3),device=device))

    def colors_sh(self):return torch.cat((self.sh0,self.sh_rest),dim=1)

    @torch.no_grad()
    def state_arrays(self,seed):
        values=super().state_arrays(seed)
        values["sh_rest"]=self.sh_rest.detach().cpu().numpy()
        values["sh_degree"]=3
        return values


def freeze_except_color(model):
    for name,p in model.named_parameters():p.requires_grad_(name in {"sh0","sh_rest"})
    return [model.sh0,model.sh_rest]


def render_view(model,view):
    # Preserve the verified geometry path byte-for-byte. The additional standard
    # gsplat call evaluates only view-dependent SH3 RGB; it has identical geometry.
    out=base_render_view(model,view)
    appearance=render(model,view.viewmat,view.K,view.width,view.height,sh_degree=3,
        render_mode="RGB+ED",bg_color=torch.zeros(3,device=model.base.device),
        surface_normal_depth_mode="gsplat_expected")
    out["rgb"]=appearance["rgb"]
    out["alpha"]=appearance["alpha"]
    return out
